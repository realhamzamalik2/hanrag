"""Cross-encoder reranking with BAAI/bge-reranker-v2-m3 (int8 ONNX, CPU).

Why a reranker: retrievers embed query and passage separately (fast, but coarse). A
cross-encoder reads the query and the passage together and scores true relevance, so it
fixes ordering mistakes from both BM25 and vectors. It is too slow to run on every chunk,
so we only rerank the top ~20 fused candidates. Its calibrated score also drives refusal.
"""

from __future__ import annotations

import copy
import logging
import math
import threading
import time
from functools import lru_cache

from app.config import get_settings
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class Reranker:
    def __init__(self) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        s = get_settings()
        t0 = time.perf_counter()
        self.model_name = s.rerank_model
        self._model = TextCrossEncoder(s.rerank_model, cache_dir=s.model_cache_dir,
                                       threads=s.onnx_threads)
        self._lock = threading.Lock()
        log.info("Loaded reranker %s in %.1fs", s.rerank_model, time.perf_counter() - t0)

    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int
               ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        docs = [f"{c.doc_title} {c.section}\n{c.text}" for c in chunks]
        with self._lock:
            logits = list(self._model.rerank(query, docs, batch_size=8))
        out: list[RetrievedChunk] = []
        for c, logit in zip(chunks, logits, strict=True):
            item = copy.copy(c)
            item.scores = dict(c.scores)
            item.scores["fused_rank"] = c.rank
            item.score = _sigmoid(float(logit))  # 0..1 relevance probability
            item.scores["rerank"] = item.score
            out.append(item)
        out.sort(key=lambda c: c.score, reverse=True)
        for rank, item in enumerate(out, start=1):
            item.rank = rank
        return out[:top_k]


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()
