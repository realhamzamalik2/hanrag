"""Integration test: ingest -> pgvector search -> cited answer, with a fake embedder and LLM.

Needs PostgreSQL + pgvector (DATABASE_URL). Run with:  uv run pytest -m db
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from app.config import get_settings
from app.ingestion.korean import tokenize_ko

pytestmark = pytest.mark.db


class FakeEmbedder:
    """Deterministic bag-of-morphemes hashing embedder (no model download)."""

    dim = get_settings().embed_dim

    def embed(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokenize_ko(t):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
        n = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.clip(n, 1e-12, None)

    def embed_query(self, q):
        return self.embed([q])[0]


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    from sqlalchemy import text

    from app.db.session import get_engine, init_db

    try:
        init_db()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"database not available: {e}")
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE documents, chunks, traces CASCADE"))
    yield


@pytest.fixture
def fake_models(monkeypatch, tmp_path):
    fake = FakeEmbedder()
    monkeypatch.setattr("app.ingestion.pipeline.get_embedder", lambda: fake)
    monkeypatch.setattr("app.retrieval.vector.get_embedder", lambda: fake)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIN_VECTOR_SCORE", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ingest_search_answer(db, fake_models, monkeypatch, tmp_path: Path):
    from app import rag
    from app.generation.llm import Usage
    from app.ingestion.pipeline import ingest_file

    md = tmp_path / "hangul.md"
    md.write_text(
        "# 한글\n\n한글은 조선의 세종이 1443년에 창제한 문자이다. 처음 이름은 훈민정음이다.\n\n"
        "## 김치\n\n김치는 배추와 고춧가루로 만드는 한국의 발효 음식이다.\n", encoding="utf-8")

    r = ingest_file(md)
    assert r.num_chunks >= 1 and not r.skipped
    assert ingest_file(md).skipped  # dedup by sha256

    chunks = rag.retrieve("한글은 누가 창제했나요?", k=2)
    assert "세종" in chunks[0].text

    monkeypatch.setattr(rag.llm, "generate",
                        lambda system, prompt: ("한글은 세종이 1443년에 창제했다 [1][9].", Usage(10, 5)))
    a = rag.answer_question("한글은 누가 창제했나요?", k=2)
    assert not a.refused
    assert "[9]" not in a.answer
    assert a.citations and a.citations[0].chunk.section == "한글"
    assert a.trace_id

    monkeypatch.setattr(rag.llm, "generate",
                        lambda s, p: ("[[INSUFFICIENT_CONTEXT]]", Usage(10, 1)))
    a2 = rag.answer_question("What is the GDP of Mars?", k=2)
    assert a2.refused and a2.answer.startswith("I don't know")
