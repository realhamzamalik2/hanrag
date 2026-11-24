"""Check that everything Step 1 needs is working.

Usage (from backend/):  uv run python -m scripts.healthcheck [--skip-models]
"""

from __future__ import annotations

import argparse
import sys
import time

from app.config import get_settings
from app.logging_setup import setup_logging

OK, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-models", action="store_true", help="skip the embedding self-test")
    args = ap.parse_args()
    setup_logging("WARNING")
    s = get_settings()
    failed = False

    print(f"{OK if s.gemini_api_key else WARN} GEMINI_API_KEY "
          f"{'set' if s.gemini_api_key else 'missing (needed for answers, not for retrieval)'}")
    print(f"{OK if s.gemini_model else WARN} GEMINI_MODEL = {s.gemini_model or '(empty)'}")

    try:
        from kiwipiepy import Kiwi

        toks = [t.form for t in Kiwi().tokenize("서울과학기술대학교는 노원구에 있다")]
        print(f"{OK} Kiwi tokenizer: {toks}")
    except Exception as e:
        failed = True
        print(f"{FAIL} Kiwi: {e}")

    try:
        from sqlalchemy import text

        from app.db.session import get_engine, init_db

        init_db()
        with get_engine().connect() as conn:
            v = conn.execute(text(
                "SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
            n = conn.execute(text("SELECT count(*) FROM chunks")).scalar()
        print(f"{OK} PostgreSQL + pgvector {v} (chunks indexed: {n})")
        from app.db.session import embedder_id, get_meta

        built = get_meta("embedder")
        if n and built != embedder_id():
            print(f"{WARN} Index built with {built or 'an older model'}, settings say "
                  f"{embedder_id()}. Run: uv run python -m scripts.reembed")
    except Exception as e:
        failed = True
        print(f"{FAIL} Database ({s.database_url.split('@')[-1]}): {e}")
        print("       Is Postgres running in WSL?  wsl sudo service postgresql start")

    if not args.skip_models:
        try:
            import numpy as np

            from app.retrieval.embedder import get_embedder

            t0 = time.perf_counter()
            emb = get_embedder()
            load_s = time.perf_counter() - t0
            v = emb.embed(["세종대왕은 한글을 창제했다.",
                           "King Sejong created the Korean alphabet.",
                           "오늘 점심은 김치찌개를 먹었다."])
            same, diff = float(np.dot(v[0], v[1])), float(np.dot(v[0], v[2]))
            good = v.shape[1] == s.embed_dim and same > diff
            print(f"{OK if good else FAIL} Embedder {s.embed_model}: dim={v.shape[1]}, "
                  f"load {load_s:.1f}s, cross-lingual sim {same:.3f} vs unrelated {diff:.3f}")
            failed |= not good
        except Exception as e:
            failed = True
            print(f"{FAIL} Embedder: {e}")
            print("       Fallback: set EMBED_BACKEND=sentence-transformers in .env and run "
                  "uv sync --extra st")

    if not args.skip_models and s.retrieval_mode == "hybrid_rerank":
        try:
            from app.retrieval.reranker import get_reranker
            from app.retrieval.types import RetrievedChunk

            def rc(t: str) -> RetrievedChunk:
                return RetrievedChunk(t, "d", "", "", 1, "", t, 0, 1, "ko", True, 0.0)

            t0 = time.perf_counter()
            ranked = get_reranker().rerank("한글은 누가 만들었나요?",
                                           [rc("김치는 발효 음식이다."),
                                            rc("세종대왕이 한글을 창제했다.")], 2)
            good = ranked[0].text.startswith("세종")
            print(f"{OK if good else FAIL} Reranker {s.rerank_model}: "
                  f"relevant {ranked[0].score:.3f} vs unrelated {ranked[1].score:.3f} "
                  f"({time.perf_counter() - t0:.1f}s incl. load)")
            failed |= not good
        except Exception as e:
            failed = True
            print(f"{FAIL} Reranker: {e}")

    print("\nAll checks passed." if not failed else "\nSome checks failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
