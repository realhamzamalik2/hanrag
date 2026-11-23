"""Parse and validate [n] citations in generated answers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.generation.prompts import REFUSAL_MESSAGES, REFUSAL_TOKEN
from app.ingestion.korean import detect_lang
from app.retrieval.types import RetrievedChunk

CITE_RE = re.compile(r"\[(\d{1,2})\]")


@dataclass
class Citation:
    number: int
    chunk: RetrievedChunk


def is_refusal(answer: str) -> bool:
    return REFUSAL_TOKEN in answer or answer.strip().startswith("[[INSUFFICIENT")


def refusal_message(question: str) -> str:
    return REFUSAL_MESSAGES["en" if detect_lang(question) == "en" else "ko"]


def extract_citations(answer: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """Return cited passages in order of first appearance; ignore out-of-range numbers."""
    seen: dict[int, Citation] = {}
    for m in CITE_RE.finditer(answer):
        n = int(m.group(1))
        if 1 <= n <= len(chunks) and n not in seen:
            seen[n] = Citation(n, chunks[n - 1])
    return list(seen.values())


def strip_invalid_citations(answer: str, num_chunks: int) -> str:
    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return m.group(0) if 1 <= n <= num_chunks else ""

    return CITE_RE.sub(repl, answer)
