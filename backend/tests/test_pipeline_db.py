"""Integration test: ingest -> hybrid retrieval -> cited answer, with fake models and LLM.

Needs PostgreSQL + pgvector (DATABASE_URL). Run with:  uv run pytest -m db
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.db

MD = ("# 한글\n\n한글은 조선의 세종이 1443년에 창제한 문자이다. 처음 이름은 훈민정음이다.\n\n"
      "## 김치\n\n김치는 배추와 고춧가루로 만드는 한국의 발효 음식이다.\n")


def test_ingest_retrieve_answer(clean_db, fake_models, monkeypatch, tmp_path: Path):
    from app import rag
    from app.db.session import session_scope
    from app.generation.llm import Usage
    from app.ingestion.pipeline import ingest_file
    from app.retrieval.hybrid import retrieve

    md = tmp_path / "hangul.md"
    md.write_text(MD, encoding="utf-8")
    r = ingest_file(md)
    assert r.num_chunks >= 1 and not r.skipped
    assert ingest_file(md).skipped  # dedup by sha256

    with session_scope() as s:
        for mode in ("vector", "bm25", "hybrid", "hybrid_rerank"):
            res = retrieve(s, "한글은 누가 창제했나요?", mode=mode, k_final=2)
            assert "세종" in res.final[0].text, mode
        hy = retrieve(s, "한글 창제", mode="hybrid_rerank", k_final=2)
        assert {"bm25", "vector"} <= set(hy.lists)
        assert "rrf" in hy.fused[0].scores and "rerank" in hy.reranked[0].scores

    monkeypatch.setattr(rag.llm, "is_configured", lambda: True)
    monkeypatch.setattr(rag.llm, "generate",
                        lambda system, prompt: ("한글은 세종이 1443년에 창제했다 [1][9].", Usage(10, 5)))
    a = rag.answer_question("한글은 누가 창제했나요?", k=2, rewrite=False)
    assert not a.refused and "[9]" not in a.answer
    assert a.citations and a.citations[0].chunk.section == "한글"
    assert a.trace_id

    # Gate: nothing relevant -> refuse without calling the LLM
    def boom(*a, **k):  # pragma: no cover
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr(rag.llm, "generate", boom)
    a2 = rag.answer_question("What is the GDP of Mars?", k=2, rewrite=False)
    assert a2.refused and a2.answer.startswith("I don't know")
    assert a2.refusal_reason
