"""Evaluation metrics for HanRAG.

Relevance is defined by evidence strings, not chunk ids: a retrieved passage is relevant
if it contains (ignoring whitespace) any evidence phrase written for the question. This
keeps the test set valid when chunking changes.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KS = (1, 3, 5, 10)


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


@dataclass
class EvalQuestion:
    id: str
    question: str
    lang: str
    type: str  # ko | en | cross_en_ko | cross_ko_en | unanswerable
    answer: str
    must: list[list[str]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)

    @property
    def answerable(self) -> bool:
        return self.type != "unanswerable"


def load_questions(path: Path) -> list[EvalQuestion]:
    with path.open(encoding="utf-8") as f:
        return [EvalQuestion(**json.loads(line)) for line in f if line.strip()]


def is_relevant(text: str, evidence: Sequence[str]) -> bool:
    t = squash(text)
    return any(squash(e) in t for e in evidence if e)


def first_relevant_rank(texts: Sequence[str], evidence: Sequence[str]) -> int | None:
    """1-based rank of the first relevant passage, or None."""
    for i, t in enumerate(texts, start=1):
        if is_relevant(t, evidence):
            return i
    return None


def retrieval_metrics(ranks: Iterable[int | None], ks: Sequence[int] = KS) -> dict[str, float]:
    """Recall@k (hit rate: at least one relevant passage in the top k) and MRR@10."""
    ranks = list(ranks)
    n = len(ranks) or 1
    out = {f"recall@{k}": sum(1 for r in ranks if r is not None and r <= k) / n for k in ks}
    out["mrr@10"] = sum(1.0 / r for r in ranks if r is not None and r <= 10) / n
    return out


def answer_matches(answer: str, must: Sequence[Sequence[str]]) -> bool:
    """Correct if every required fact group is present (any alternative, case-insensitive)."""
    a = squash(answer).lower()
    return all(any(squash(alt).lower() in a for alt in group) for group in must)


def latency_stats(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    v = sorted(values)
    p95 = v[min(len(v) - 1, round(0.95 * (len(v) - 1)))]
    return {"mean": round(statistics.fmean(v), 1), "p50": round(statistics.median(v), 1),
            "p95": round(p95, 1)}


def threshold_sweep(scores_answerable: Sequence[float], scores_unanswerable: Sequence[float],
                    thresholds: Sequence[float]) -> list[dict[str, Any]]:
    """For an early-refusal gate on the top reranker score: what share of unanswerable
    questions it refuses (good) and of answerable ones it wrongly refuses (bad)."""
    rows = []
    for t in thresholds:
        rows.append({
            "threshold": t,
            "unanswerable_refused": (sum(s < t for s in scores_unanswerable)
                                     / max(len(scores_unanswerable), 1)),
            "answerable_refused": (sum(s < t for s in scores_answerable)
                                   / max(len(scores_answerable), 1)),
        })
    return rows
