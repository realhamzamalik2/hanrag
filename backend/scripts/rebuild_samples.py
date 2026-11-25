"""Re-index documents whose extracted text changed because the PDF parser improved.

- Removes index entries for non-documents that slipped in earlier (SOURCES.md, README.md).
- If the PDF parser version differs from the one the index was built with, deletes the
  indexed PDFs found in the folder and ingests them again (files on disk are untouched).

Usage (from backend/):  uv run python -m scripts.rebuild_samples [../data/samples]
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from app.config import ROOT_DIR, get_settings
from app.db.models import Document
from app.db.session import get_meta, init_db, session_scope, set_meta
from app.ingestion.parsers.pdf import PARSER_VERSION
from app.ingestion.pipeline import ingest_file
from app.logging_setup import setup_logging
from app.retrieval.bm25 import invalidate_bm25
from scripts.ingest_cli import SKIP_FILES, load_sources


def main() -> int:
    setup_logging(get_settings().log_level)
    init_db()
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT_DIR / "data" / "samples"

    with session_scope() as s:
        junk = s.scalars(select(Document).where(Document.filename.in_(SKIP_FILES))).all()
        for d in junk:
            print(f"Removing non-document from index: {d.filename}")
            s.delete(d)

    if get_meta("pdf_parser_version") == PARSER_VERSION:
        print(f"PDF index already uses parser v{PARSER_VERSION}; nothing to rebuild.")
        invalidate_bm25()
        return 0

    pdfs = sorted(folder.glob("*.pdf"))
    names = {p.name for p in pdfs}
    with session_scope() as s:
        old = s.scalars(select(Document).where(Document.filename.in_(names))).all()
        for d in old:
            for f in get_settings().uploads_dir.glob(f"{d.id}.*"):
                f.unlink(missing_ok=True)
            s.delete(d)
    print(f"Re-indexing {len(pdfs)} PDFs with parser v{PARSER_VERSION} (about 2 s per passage)")
    sources = load_sources(folder)
    failed = 0
    for p in pdfs:
        meta = sources.get(p.name, {})
        try:
            r = ingest_file(p, source_url=meta.get("url"), license=meta.get("license"))
            print(f"[done] {p.name}: {r.num_pages} pages, {r.num_chunks} chunks "
                  f"({r.elapsed_ms / 1000:.0f}s)")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[fail] {p.name}: {e}")
    invalidate_bm25()
    if not failed:
        set_meta("pdf_parser_version", PARSER_VERSION)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
