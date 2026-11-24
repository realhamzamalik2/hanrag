"""Ask a question from the command line and print a cited answer plus how retrieval worked.

Usage (from backend/):
  uv run python -m scripts.ask_cli "한글은 누가 만들었나요?"
  uv run python -m scripts.ask_cli "Who created Hangul?" --mode hybrid_rerank --debug
  uv run python -m scripts.ask_cli "훈민정음 반포 연도" --mode bm25 --tokenizer whitespace --no-llm
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from app.config import get_settings
from app.logging_setup import setup_logging
from app.rag import answer_question
from app.retrieval.hybrid import MODES


def short(text: str, n: int) -> str:
    return textwrap.shorten(text.replace("\n", " "), n, placeholder=" ...")


def loc(c) -> str:  # type: ignore[no-untyped-def]
    return f"p.{c.page}" if c.paginated else (c.section or f"part {c.page}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=None, help="passages given to the LLM")
    ap.add_argument("--mode", choices=MODES, default=None)
    ap.add_argument("--tokenizer", choices=("kiwi", "whitespace"), default=None)
    ap.add_argument("--no-llm", action="store_true", help="retrieval only (no API calls)")
    ap.add_argument("--no-rewrite", action="store_true", help="skip query rewrite/translation")
    ap.add_argument("--debug", action="store_true", help="show every retrieval stage")
    args = ap.parse_args()
    setup_logging(get_settings().log_level)

    a = answer_question(args.question, mode=args.mode, tokenizer=args.tokenizer, k=args.k,
                        use_llm=not args.no_llm, rewrite=False if args.no_rewrite else None)
    r = a.retrieval
    if a.standalone_query and a.standalone_query != a.question:
        print(f"\nRewritten query: {a.standalone_query}")
    if r and r.extra_queries:
        print(f"Translated query: {r.extra_queries[0]}")

    if r and args.debug:
        for name, items in r.lists.items():
            print(f"\n--- {name} (top 5) ---")
            for c in items[:5]:
                print(f"  #{c.rank:<2} {c.score:7.3f}  {c.doc_title} ({loc(c)})  {short(c.text, 70)}")
        if r.reranked:
            print("\n--- reranked (top 5) ---")
            for c in r.reranked[:5]:
                fr = c.scores.get("fused_rank", "?")
                print(f"  #{c.rank:<2} {c.score:7.3f}  (was #{fr})  {c.doc_title} ({loc(c)})")

    print(f"\n=== Final passages ({r.mode if r else '?'}) ===")
    for c in a.chunks:
        print(f"#{c.rank}  score={c.score:.3f}  {c.doc_title} ({loc(c)})")
        print(textwrap.indent(short(c.text, 220), "     "))

    if not args.no_llm or a.refused:
        print("\n=== Answer ===")
        print(a.answer)
        if a.refusal_reason:
            print(f"(refusal reason: {a.refusal_reason})")
        if a.citations:
            print("\n=== Citations ===")
            for cit in a.citations:
                c = cit.chunk
                print(f"[{cit.number}] {c.doc_title}, {loc(c)}")
                print(textwrap.indent(short(c.text, 300), "    "))

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
