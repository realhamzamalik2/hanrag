"""Multilingual embeddings with BAAI/bge-m3 on CPU.

Why bge-m3: one model for Korean, English and 100+ other languages in a shared vector
space, so an English question can retrieve a Korean passage (cross-lingual retrieval).
Why ONNX via fastembed: no PyTorch install, lower memory overhead, faster CPU inference.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from functools import lru_cache

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)


class Embedder:
    def __init__(self) -> None:
        s = get_settings()
        self.model_name = s.embed_model
        self.dim = s.embed_dim
        self.batch_size = s.embed_batch_size
        self.backend = s.embed_backend
        self._lock = threading.Lock()
        t0 = time.perf_counter()
        if self.backend == "fastembed":
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

            # bge-m3 publishes an official ONNX export under onnx/ in its HF repo.
            # Dense bge-m3 embeddings = normalized [CLS] vector.
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
            if self.backend == "fastembed":
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
