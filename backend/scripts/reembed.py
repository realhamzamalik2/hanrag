"""Recompute every chunk embedding with the current embedder (no re-parsing needed).

Run after changing EMBED_BACKEND / EMBED_MODEL, because vectors from different models
(even fp32 vs int8 of the same model) must not be mixed in one index.

Usage (from backend/):  uv run python -m scripts.reembed
"""

from __future__ import annotations

import sys
import time

from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import Chunk
from app.db.session import embedder_id, get_meta, init_db, session_scope, set_meta
from app.logging_setup import setup_logging
from app.retrieval.embedder import get_embedder

BATCH = 32


def main() -> int:
    setup_logging(get_settings().log_level)
    init_db()
    current, indexed = embedder_id(), get_meta("embedder")
    if indexed == current and "--force" not in sys.argv:
        print(f"Index already built with {current}; nothing to do (use --force to redo).")
        return 0
    print(f"Index built with: {indexed or 'unknown'}  ->  now: {current}")
    emb = get_embedder()
    with session_scope() as s:
        total = s.scalar(select(func.count(Chunk.id))) or 0
        ids = [row[0] for row in s.execute(select(Chunk.id).order_by(Chunk.id))]
    print(f"Re-embedding {total} chunks with {emb.model_name} ({emb.backend})")
    t0 = time.perf_counter()
    done = 0
    for i in range(0, len(ids), BATCH):
        with session_scope() as s:
            chunks = s.scalars(select(Chunk).where(Chunk.id.in_(ids[i:i + BATCH]))).all()
            vecs = emb.embed([c.text for c in chunks])
            for c, v in zip(chunks, vecs, strict=True):
                c.embedding = v
        done += len(chunks)
        rate = done / max(time.perf_counter() - t0, 1e-6)
        print(f"  {done}/{total} chunks  ({rate:.1f}/s, ~{(total - done) / rate:.0f}s left)",
              flush=True)
    set_meta("embedder", current)
    print(f"Done in {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
