"""Cross-encoder reranking with BAAI/bge-reranker-v2-m3 (int8 ONNX, CPU).

Why a reranker: retrievers embed query and passage separately (fast, but coarse). A
cross-encoder reads the query and the passage together and scores true relevance, so it
fixes ordering mistakes from both BM25 and vectors. It is too slow to run on every chunk,
so we only rerank the top fused candidates. Its calibrated score also drives refusal.

The model is the int8 ONNX export published by onnx-community (the same files fastembed
uses), run directly with onnxruntime so loading can be tuned for 8 GB machines.
"""

from __future__ import annotations

import copy
import logging
import math
import threading
import time
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.retrieval.onnx_utils import make_session
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)

# Model name in settings -> (HF repo, ONNX file inside the repo)
RERANKERS = {
    "BAAI/bge-reranker-v2-m3-int8": ("onnx-community/bge-reranker-v2-m3-ONNX",
                                     "onnx/model_int8.onnx"),
    "BAAI/bge-reranker-v2-m3": ("onnx-community/bge-reranker-v2-m3-ONNX", "onnx/model.onnx"),
}
TOKENIZER_FILES = ["tokenizer.json", "config.json", "special_tokens_map.json",
                   "tokenizer_config.json"]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class Reranker:
    def __init__(self) -> None:
        from huggingface_hub import snapshot_download
        from tokenizers import Tokenizer

        s = get_settings()
        t0 = time.perf_counter()
        self.model_name = s.rerank_model
        repo, onnx_file = RERANKERS.get(s.rerank_model, (s.rerank_model, "onnx/model.onnx"))
        local = Path(snapshot_download(repo, cache_dir=s.model_cache_dir,
                                       allow_patterns=[onnx_file, *TOKENIZER_FILES]))
        self.tokenizer = Tokenizer.from_file(str(local / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        self.session = make_session(local / onnx_file, s.onnx_threads)
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.batch_size = s.rerank_batch_size
        self.max_chars = s.rerank_max_chars
        self._lock = threading.Lock()
        log.info("Loaded reranker %s in %.1fs", s.rerank_model, time.perf_counter() - t0)

    def scores(self, query: str, docs: list[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(docs), self.batch_size):
            enc = self.tokenizer.encode_batch([(query, d) for d in docs[i:i + self.batch_size]])
            feeds = {
                "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
            }
            if "token_type_ids" in self.input_names:
                feeds["token_type_ids"] = np.zeros_like(feeds["input_ids"])
            logits = self.session.run(None, feeds)[0]
            out.extend(float(x) for x in np.asarray(logits).reshape(len(enc), -1)[:, 0])
        return out

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int
               ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        # Short inputs + small batches keep peak RAM low (long pairs blow up attention memory).
        docs = [f"{c.doc_title} {c.section}\n{c.text}"[: self.max_chars] for c in chunks]
        with self._lock:
            logits = self.scores(query, docs)
        out: list[RetrievedChunk] = []
        for c, logit in zip(chunks, logits, strict=True):
            item = copy.copy(c)
            item.scores = dict(c.scores)
            item.scores["fused_rank"] = c.rank
            item.score = _sigmoid(logit)  # 0..1 relevance probability
            item.scores["rerank"] = item.score
            out.append(item)
        out.sort(key=lambda c: c.score, reverse=True)
        for rank, item in enumerate(out, start=1):
            item.rank = rank
        return out[:top_k]


_instance: Reranker | None = None
_load_lock = threading.Lock()


def get_reranker() -> Reranker:
    """Load once, even if several requests ask at the same time (others wait)."""
    global _instance
    if _instance is None:
        with _load_lock:
            if _instance is None:
                _instance = Reranker()
    return _instance
