"""Reciprocal Rank Fusion (Cormack et al., 2009).

Why RRF: BM25 scores (unbounded, e.g. 0 to 25) and cosine similarities (0 to 1) live on
different scales, so adding them needs fragile normalization. RRF only uses ranks:

    score(d) = sum over lists of 1 / (k + rank_in_list(d))

k = 60 is the standard constant; it damps the influence of the very top ranks so one
retriever cannot dominate. No tuning, no training, robust in practice.
"""

from __future__ import annotations

import copy

from app.retrieval.types import RetrievedChunk


def reciprocal_rank_fusion(ranked_lists: dict[str, list[RetrievedChunk]], k: int = 60,
                           limit: int | None = None) -> list[RetrievedChunk]:
    fused: dict[str, RetrievedChunk] = {}
    totals: dict[str, float] = {}
    for name, results in ranked_lists.items():
        for rank, item in enumerate(results, start=1):
            key = item.chunk_id
            if key not in fused:
                fused[key] = copy.copy(item)
                fused[key].scores = dict(item.scores)
                totals[key] = 0.0
            else:
                fused[key].scores.update(item.scores)
            fused[key].scores[f"{name}_rank"] = rank
            totals[key] += 1.0 / (k + rank)

    ordered = sorted(fused.values(), key=lambda c: totals[c.chunk_id], reverse=True)
    for rank, item in enumerate(ordered, start=1):
        item.score = totals[item.chunk_id]
        item.scores["rrf"] = item.score
        item.rank = rank
    return ordered[:limit] if limit else ordered
