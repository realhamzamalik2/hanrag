"""Ingest files or folders into HanRAG.

Usage (from backend/):
  uv run python -m scripts.ingest_cli ../data/samples
  uv run python -m scripts.ingest_cli path/to/file.pdf another.docx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import init_db
from app.ingestion.parsers import SUPPORTED_EXTENSIONS
from app.ingestion.pipeline import ingest_file
from app.logging_setup import setup_logging


def load_sources(folder: Path) -> dict[str, dict[str, str]]:
    """Optional sources.json next to sample files: {filename: {url, license}}."""
    f = folder / "sources.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", type=Path)
    args = ap.parse_args()
    setup_logging(get_settings().log_level)
    init_db()

    files: list[Path] = []
    for p in args.paths:
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix.lower() in SUPPORTED_EXTENSIONS)
        elif p.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(p)
        else:
            print(f"skip (unsupported): {p}")

    ok = failed = 0
    for f in files:
        meta = load_sources(f.parent).get(f.name, {})
        try:
            r = ingest_file(f, source_url=meta.get("url"), license=meta.get("license"))
            tag = "skip" if r.skipped else "done"
            print(f"[{tag}] {f.name}: {r.num_pages} pages, {r.num_chunks} chunks "
                  f"({r.elapsed_ms / 1000:.1f}s)")
            ok += 1
        except Exception as e:
            print(f"[fail] {f.name}: {e}")
            failed += 1
    print(f"\n{ok} indexed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    from sqlalchemy.exc import OperationalError

    try:
        sys.exit(main())
    except OperationalError as e:
        print(f"\nDatabase not reachable: {str(e).splitlines()[0]}")
        print("Start it with:  powershell -ExecutionPolicy Bypass -File ..\\scripts\\start_db.ps1")
        sys.exit(2)
