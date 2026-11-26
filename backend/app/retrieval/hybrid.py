"""Retrieval orchestrator: BM25 + vectors -> RRF -> reranker, with every stage recorded.

Modes (also the ablation study arms):
  vector         dense only
  bm25           keyword only
  hybrid         BM25 + dense fused with RRF
  hybrid_rerank  hybrid, then cross-encoder rerank (default)

Each stage's ranked list is kept so the UI can show "How I found this" side by side.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion.korean import detect_lang
from app.retrieval.bm25 import TokenizerName, bm25_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.types import RetrievedChunk
from app.retrieval.vector import vector_search

log = logging.getLogger(__name__)

Mode = Literal["vector", "bm25", "hybrid", "hybrid_rerank"]
MODES: tuple[str, ...] = ("vector", "bm25", "hybrid", "hybrid_rerank")


@dataclass
class RetrievalResult:
    query: str
    extra_queries: list[str]
    mode: str
    tokenizer: str
    lists: dict[str, list[RetrievedChunk]] = field(default_factory=dict)
    fused: list[RetrievedChunk] = field(default_factory=list)
    reranked: list[RetrievedChunk] = field(default_factory=list)
    final: list[RetrievedChunk] = field(default_factory=list)
    stages_ms: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def top_score(self) -> float:
        return self.final[0].score if self.final else 0.0

    def to_debug(self, limit: int = 10) -> dict[str, Any]:
        """Compact structure for traces and the debug panel."""

        def pack(items: list[RetrievedChunk]) -> list[dict[str, Any]]:
            return [
                {"chunk_id": c.chunk_id, "document_id": c.document_id,
                 "doc_title": c.doc_title, "page": c.page, "section": c.section,
                 "paginated": c.paginated, "lang": c.lang, "rank": c.rank,
                 "score": round(c.score, 5),
                 "scores": {k: round(v, 5) if isinstance(v, float) else v
                            for k, v in c.scores.items()},
                 "text": c.text[:400]}
                for c in items[:limit]
            ]

        return {
            "query": self.query, "extra_queries": self.extra_queries, "mode": self.mode,
            "tokenizer": self.tokenizer,
            "lists": {name: pack(items) for name, items in self.lists.items()},
            "fused": pack(self.fused), "reranked": pack(self.reranked),
            "final": pack(self.final), "stages_ms": self.stages_ms, "warnings": self.warnings,
        }


def _timed(stages: dict[str, float], name: str, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
    t = time.perf_counter()
    try:
        return fn(*args, **kwargs)
    finally:
        stages[name] = round(stages.get(name, 0.0) + (time.perf_counter() - t) * 1000, 1)


def match_query_language(query: str, extra: list[str], chunks: list[RetrievedChunk]
                         ) -> list[str] | None:
    """Pick, per passage, the query variant written in the passage's language.

    The cross-encoder scores an English question against a Korean passage much lower than
    the same question in Korean (0.03 vs 0.9 in the eval), which made the refusal gate reject
    answerable cross-lingual questions. Same number of pairs, so no extra rerank time.
    """
    by_lang: dict[str, str] = {}
    for q in [query, *extra]:
        lang = detect_lang(q)
        if lang in ("ko", "en"):
            by_lang.setdefault(lang, q)
    if len(by_lang) < 2:
        return None
    out = []
    for c in chunks:
        lang = detect_lang(c.text)
        out.append(by_lang.get(lang, query))
    return out


def retrieve(session: Session, query: str, *, mode: Mode = "hybrid_rerank",
             tokenizer: TokenizerName = "kiwi", extra_queries: list[str] | None = None,
             k_final: int | None = None, document_ids: list[str] | None = None,
             use_reranker: bool | None = None) -> RetrievalResult:
    s = get_settings()
    k_final = k_final or s.top_k_final
    extra = [q for q in (extra_queries or []) if q and q.strip() and q != query]
    res = RetrievalResult(query=query, extra_queries=extra, mode=mode, tokenizer=tokenizer)
    queries = [("", query)] + [(f":{i + 1}", q) for i, q in enumerate(extra)]

    if mode in ("bm25", "hybrid", "hybrid_rerank"):
        for suffix, q in queries:
            hits = _timed(res.stages_ms, "bm25", bm25_search, session, q, s.top_k_bm25,
                          tokenizer)
            if document_ids:
                hits = [h for h in hits if h.document_id in document_ids]
            res.lists[f"bm25{suffix}"] = hits
    if mode in ("vector", "hybrid", "hybrid_rerank"):
        for suffix, q in queries:
            res.lists[f"vector{suffix}"] = _timed(res.stages_ms, "vector", vector_search,
                                                  session, q, s.top_k_vector, document_ids)

    if len(res.lists) == 1:
        (only,) = res.lists.values()
        res.fused = only
    else:
        res.fused = _timed(res.stages_ms, "fusion", reciprocal_rank_fusion, res.lists,
                           s.rrf_k)

    rerank = mode == "hybrid_rerank" if use_reranker is None else use_reranker
    if rerank and res.fused:
        from app.retrieval import reranker as rr

        candidates = res.fused[: s.top_k_rerank]
        pair_queries = (match_query_language(query, extra, candidates)
                        if s.rerank_match_lang and extra else None)
        try:
            res.reranked = _timed(res.stages_ms, "rerank", rr.get_reranker().rerank, query,
                                  candidates, len(candidates), pair_queries=pair_queries)
        except Exception as e:  # noqa: BLE001
            # e.g. not enough free RAM to load the cross-encoder: answer from fused results.
            log.warning("Reranker unavailable, using fused ranking: %s", e)
            res.warnings.append(f"reranker unavailable: {str(e)[:200]}")
    res.final = (res.reranked or res.fused)[:k_final]
    return res
