"""Multilingual embeddings with BAAI/bge-m3 on CPU.

Why bge-m3: one model for Korean, English and 100+ other languages in a shared vector
space, so an English question can retrieve a Korean passage (cross-lingual retrieval).

Backends:
- onnx-int8 (default): bge-m3 dynamically quantized to int8 (gpahal/bge-m3-onnx-int8,
  MIT). About 570 MB instead of 2.3 GB, so it fits on an 8 GB laptop next to the reranker.
  The graph outputs normalized [CLS] vectors directly as `dense_vecs`.
- fastembed: the official fp32 ONNX export (BAAI/bge-m3, onnx/model.onnx). Used in the
  eval to measure what int8 quantization costs in retrieval quality.
- sentence-transformers: PyTorch fallback.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)

INT8_FILES = ["model_quantized.onnx", "tokenizer.json", "config.json",
              "special_tokens_map.json", "tokenizer_config.json"]


class OnnxInt8Backend:
    """Plain onnxruntime + tokenizers; reads the `dense_vecs` output."""

    def __init__(self, repo: str, cache_dir: str, threads: int, max_length: int) -> None:
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from tokenizers import Tokenizer

        local = Path(snapshot_download(repo, cache_dir=cache_dir, allow_patterns=INT8_FILES))
        self.tokenizer = Tokenizer.from_file(str(local / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")  # XLM-R pad id
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        # The memory arena keeps peak allocations around forever; off = lower RSS.
        opts.enable_cpu_mem_arena = False
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(local / "model_quantized.onnx"), opts,
                                            providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.session.get_inputs()}
        outputs = [o.name for o in self.session.get_outputs()]
        self.output = "dense_vecs" if "dense_vecs" in outputs else outputs[0]

    def embed(self, texts: list[str], batch_size: int) -> np.ndarray:
        out: list[np.ndarray] = []
        for i in range(0, len(texts), batch_size):
            enc = self.tokenizer.encode_batch(texts[i:i + batch_size])
            feeds = {
                "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
            }
            if "token_type_ids" in self.input_names:
                feeds["token_type_ids"] = np.zeros_like(feeds["input_ids"])
            (vecs,) = self.session.run([self.output], feeds)
            if vecs.ndim == 3:  # a last_hidden_state-style output: take [CLS]
                vecs = vecs[:, 0]
            out.append(vecs)
        return np.concatenate(out, axis=0)


class Embedder:
    def __init__(self) -> None:
        s = get_settings()
        self.model_name = s.embed_model
        self.dim = s.embed_dim
        self.batch_size = s.embed_batch_size
        self.backend = s.embed_backend
        self._lock = threading.Lock()
        t0 = time.perf_counter()
        if self.backend == "onnx-int8":
            self._model = OnnxInt8Backend(s.embed_model, s.model_cache_dir, s.onnx_threads,
                                          s.embed_max_length)
        elif self.backend == "fastembed":
            self._model = self._load_fastembed(s.model_cache_dir, s.onnx_threads)
        else:
            self._model = self._load_st(s.model_cache_dir)
        log.info("Loaded embedder %s (%s) in %.1fs", self.model_name, self.backend,
                 time.perf_counter() - t0)

    def _load_fastembed(self, cache_dir: str, threads: int):  # type: ignore[no-untyped-def]
        from fastembed import TextEmbedding

        supported = {m["model"] for m in TextEmbedding.list_supported_models()}
        if self.model_name not in supported:
            from fastembed.common.model_description import ModelSource, PoolingType

            # bge-m3 publishes an official fp32 ONNX export under onnx/ in its HF repo.
            TextEmbedding.add_custom_model(
                model=self.model_name,
                pooling=PoolingType.CLS,
                normalization=True,
                sources=ModelSource(hf=self.model_name),
                dim=self.dim,
                model_file="onnx/model.onnx",
                additional_files=["onnx/model.onnx_data", "onnx/Constant_7_attr__value"],
            )
        return TextEmbedding(self.model_name, cache_dir=cache_dir, threads=threads)

    def _load_st(self, cache_dir: str):  # type: ignore[no-untyped-def]
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "EMBED_BACKEND=sentence-transformers needs: uv sync --extra st") from e
        return SentenceTransformer(self.model_name, device="cpu", cache_folder=cache_dir)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        with self._lock:
            if self.backend == "onnx-int8":
                vecs = self._model.embed(list(texts), self.batch_size)
            elif self.backend == "fastembed":
                vecs = np.array(list(self._model.embed(list(texts),
                                                       batch_size=self.batch_size)))
            else:
                vecs = self._model.encode(list(texts), batch_size=self.batch_size,
                                          normalize_embeddings=True)
        vecs = np.asarray(vecs, dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.clip(norms, 1e-12, None)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed([query])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
