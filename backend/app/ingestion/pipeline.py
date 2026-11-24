"""Ingestion pipeline: file -> parse -> Korean-aware chunks -> embeddings -> PostgreSQL."""

from __future__ import annotations

import hashlib
import logging
import shutil
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Chunk, Document
from app.db.session import embedder_id, get_meta, session_scope, set_meta
from app.ingestion.chunker import chunk_document
from app.ingestion.parsers import parse_file
from app.retrieval.embedder import get_embedder

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, float], None]  # (stage, fraction 0..1)


@dataclass
class IngestResult:
    document_id: str
    title: str
    num_pages: int
    num_chunks: int
    skipped: bool
    elapsed_ms: float


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ingest_file(path: Path, *, source_url: str | None = None, license: str | None = None,
                progress: ProgressFn | None = None) -> IngestResult:
    s = get_settings()
    t0 = time.perf_counter()
    report = progress or (lambda stage, frac: None)
    digest = sha256_file(path)
    indexed_with = get_meta("embedder")
    if indexed_with and indexed_with != embedder_id():
        raise RuntimeError(f"Index was built with {indexed_with} but EMBED_* now says "
                           f"{embedder_id()}. Run: uv run python -m scripts.reembed")

    with session_scope() as session:
        existing = session.scalar(select(Document).where(Document.sha256 == digest))
        if existing is not None and existing.status == "ready":
            log.info("Skip %s (already indexed as %s)", path.name, existing.id)
            return IngestResult(str(existing.id), existing.title, existing.num_pages,
                                existing.num_chunks, True, 0.0)
        if existing is not None:
            session.delete(existing)
            session.flush()

        doc_id = uuid.uuid4()
        s.uploads_dir.mkdir(parents=True, exist_ok=True)
        stored = s.uploads_dir / f"{doc_id}{path.suffix.lower()}"
        shutil.copyfile(path, stored)

        doc = Document(id=doc_id, filename=path.name, title=path.stem,
                       file_type=path.suffix.lower().lstrip("."), sha256=digest,
                       status="pending", source_url=source_url, license=license)
        session.add(doc)
        session.flush()

        try:
            report("parsing", 0.05)
            parsed = parse_file(path)
            report("chunking", 0.15)
            chunks = chunk_document(parsed, s.chunk_max_chars, s.chunk_overlap_sentences,
                                    s.chunk_min_chars)
            if not chunks:
                raise ValueError("No extractable text (scanned PDF? OCR is not supported yet)")

            embedder = get_embedder()
            vectors = []
            batch = max(1, s.embed_batch_size * 4)
            for i in range(0, len(chunks), batch):
                vectors.extend(embedder.embed([c.text for c in chunks[i:i + batch]]))
                report("embedding", 0.15 + 0.8 * min(1.0, (i + batch) / len(chunks)))

            for c, v in zip(chunks, vectors, strict=True):
                session.add(Chunk(document_id=doc_id, chunk_index=c.chunk_index, page=c.page,
                                  section=c.section, text=c.text, char_start=c.char_start,
                                  char_end=c.char_end, lang=c.lang, embedding=v))

            langs = Counter(c.lang for c in chunks)
            doc.title = parsed.title[:500]
            doc.file_type = parsed.file_type
            doc.paginated = parsed.paginated
            doc.num_pages = parsed.num_pages
            doc.num_chunks = len(chunks)
            doc.num_chars = sum(len(p.text) for p in parsed.pages)
            doc.lang = langs.most_common(1)[0][0]
            doc.status = "ready"
            if indexed_with is None:
                set_meta("embedder", embedder_id())
            doc.ingest_ms = (time.perf_counter() - t0) * 1000
            report("done", 1.0)
            log.info("Indexed %s: %d pages, %d chunks in %.1fs", path.name, doc.num_pages,
                     len(chunks), doc.ingest_ms / 1000)
            return IngestResult(str(doc_id), doc.title, doc.num_pages, len(chunks), False,
                                doc.ingest_ms)
        except Exception as e:
            log.exception("Ingestion failed for %s", path.name)
            doc.status = "failed"
            doc.error = str(e)[:2000]
            raise
