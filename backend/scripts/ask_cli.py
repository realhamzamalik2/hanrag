"""Ask a question from the command line and print a cited answer.

Usage (from backend/):
  uv run python -m scripts.ask_cli "한글은 누가 만들었나요?"
  uv run python -m scripts.ask_cli "Who created Hangul?" --no-llm   # retrieval only, no API call
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from app.config import get_settings
from app.logging_setup import setup_logging
from app.rag import answer_question


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=None, help="passages to retrieve")
    ap.add_argument("--no-llm", action="store_true", help="show retrieval only")
    args = ap.parse_args()
    setup_logging(get_settings().log_level)

    a = answer_question(args.question, k=args.k, use_llm=not args.no_llm)

    print("\n=== Retrieved passages (vector search) ===")
    for c in a.chunks:
        loc = f"p.{c.page}" if c.paginated else (c.section or f"part {c.page}")
        print(f"#{c.rank}  score={c.score:.3f}  {c.doc_title} ({loc})")
        print(textwrap.indent(textwrap.shorten(c.text, 220, placeholder=" ..."), "     "))

    if not args.no_llm or a.refused:
        print("\n=== Answer ===")
        print(a.answer)
        if a.citations:
            print("\n=== Citations ===")
            for cit in a.citations:
                c = cit.chunk
                loc = f"page {c.page}" if c.paginated else (c.section or f"part {c.page}")
                print(f"[{cit.number}] {c.doc_title}, {loc}")
                print(textwrap.indent(textwrap.shorten(c.text, 300, placeholder=" ..."), "    "))

    stages = ", ".join(f"{k} {v:.0f}ms" for k, v in a.stages_ms.items())
    print(f"\n({stages}; total {a.total_ms:.0f}ms; trace {a.trace_id})")
    return 0


if __name__ == "__main__":
    from sqlalchemy.exc import OperationalError

    try:
        sys.exit(main())
    except OperationalError as e:
        print(f"\nDatabase not reachable: {str(e).splitlines()[0]}")
        print("Start it with:  powershell -ExecutionPolicy Bypass -File ..\\scripts\\start_db.ps1")
        sys.exit(2)
