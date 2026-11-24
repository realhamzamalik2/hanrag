"""BM25 keyword search with a Korean morphological tokenizer (Kiwi) or plain whitespace.

Why BM25 next to vectors: dense embeddings are great at meaning but weak at exact terms
(names, numbers, rare words like "훈민정음해례본", "1446년"). BM25 nails exact terms.
Why Kiwi: "한글을", "한글은", "한글이" all become "한글", so Korean queries match.
The whitespace tokenizer exists only for the ablation study.

The index is built from the chunks table and cached in memory; it is rebuilt automatically
when the set of chunks changes (ingest or delete).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import bm25s
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.ingestion.korean import tokenize_ko, tokenize_whitespace
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)

TokenizerName = Literal["kiwi", "whitespace"]
TOKENIZERS: dict[str, Callable[[str], list[str]]] = {
    "kiwi": tokenize_ko,
    "whitespace": tokenize_whitespace,
}


@dataclass
class Row:
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


class BM25Index:
    def __init__(self, tokenizer: TokenizerName) -> None:
        self.tokenizer_name = tokenizer
        self.tokenize = TOKENIZERS[tokenizer]
        self.fingerprint: tuple[int, str] | None = None
        self.rows: list[Row] = []
        self.model: bm25s.BM25 | None = None
        self.build_ms = 0.0

    def build(self, session: Session, fingerprint: tuple[int, str]) -> None:
        t0 = time.perf_counter()
        stmt = (select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
                .where(Document.status == "ready")
                .order_by(Chunk.document_id, Chunk.chunk_index))
        rows = [
            Row(str(c.id), str(d.id), d.title, d.filename, c.page, c.section, c.text,
                 c.char_start, c.char_end, c.lang, d.paginated)
            for c, d in session.execute(stmt).all()
        ]
        self.build_from_rows(rows, fingerprint)
        self.build_ms = (time.perf_counter() - t0) * 1000
        log.info("BM25[%s] built: %d chunks in %.0f ms", self.tokenizer_name, len(self.rows),
                 self.build_ms)

    def build_from_rows(self, rows: list[Row], fingerprint: tuple[int, str]) -> None:
        self.rows = rows
        if self.rows:
            corpus = [self.tokenize(f"{r.section} {r.text}") or ["_"] for r in self.rows]
            self.model = bm25s.BM25()  # Lucene-style BM25, k1=1.5, b=0.75
            self.model.index(corpus, show_progress=False)
        else:
            self.model = None
        self.fingerprint = fingerprint

    def search(self, query: str, k: int) -> list[RetrievedChunk]:
        if self.model is None or not self.rows:
            return []
        vocab = self.model.vocab_dict
        q = [t for t in self.tokenize(query) if t in vocab]
        if not q:
            return []
        k = min(k, len(self.rows))
        idx, scores = self.model.retrieve([q], k=k, show_progress=False)
        out: list[RetrievedChunk] = []
        for rank, (i, s) in enumerate(zip(idx[0], scores[0], strict=True), start=1):
            if s <= 0:
                break
            r = self.rows[int(i)]
            out.append(RetrievedChunk(
                chunk_id=r.chunk_id, document_id=r.document_id, doc_title=r.doc_title,
                filename=r.filename, page=r.page, section=r.section, text=r.text,
                char_start=r.char_start, char_end=r.char_end, lang=r.lang,
                paginated=r.paginated, score=float(s), rank=rank,
                scores={"bm25": float(s)},
            ))
        return out


_indexes: dict[str, BM25Index] = {}
_lock = threading.Lock()


def corpus_fingerprint(session: Session) -> tuple[int, str]:
    count, newest = session.execute(
        select(func.count(Chunk.id), func.max(Document.created_at))
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "ready")
    ).one()
    return int(count), str(newest)


def get_bm25(session: Session, tokenizer: TokenizerName = "kiwi") -> BM25Index:
    fp = corpus_fingerprint(session)
    with _lock:
        index = _indexes.get(tokenizer)
        if index is None or index.fingerprint != fp:
            index = BM25Index(tokenizer)
            index.build(session, fp)
            _indexes[tokenizer] = index
        return index


def invalidate_bm25() -> None:
    with _lock:
        _indexes.clear()


def bm25_search(session: Session, query: str, k: int,
                tokenizer: TokenizerName = "kiwi") -> list[RetrievedChunk]:
    return get_bm25(session, tokenizer).search(query, k)


__all__ = ["BM25Index", "bm25_search", "get_bm25", "invalidate_bm25"]
