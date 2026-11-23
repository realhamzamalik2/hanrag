"""Shared retrieval result types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    doc_title: str
    filename: str
    page: int
    section: str
    text: str
    char_start: int
    char_end: int
    lang: str
    paginated: bool
    score: float
    rank: int = 0
    scores: dict[str, float] = field(default_factory=dict)  # per-stage scores for debugging

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
