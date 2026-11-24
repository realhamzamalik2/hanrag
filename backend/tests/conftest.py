"""Shared test fakes: deterministic embedder and reranker so tests never download models.

DB tests run against a SEPARATE database (hanrag_test) because they truncate tables.
"""

from __future__ import annotations

import hashlib
import os
import re

# Must run before anything reads settings: point tests at the test database.
_base = os.environ.get("DATABASE_URL",
                       "postgresql+psycopg://hanrag:hanrag_dev@localhost:5432/hanrag")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL",
                                            re.sub(r"/(\w+)$", r"/\1_test", _base))

import numpy as np
import pytest

from app.config import get_settings
from app.ingestion.korean import get_kiwi, tokenize_ko


class FakeEmbedder:
    """Bag-of-morphemes hashing embedder."""

    dim = get_settings().embed_dim

    def embed(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokenize_ko(t):
                out[i, int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        n = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.clip(n, 1e-12, None)

    def embed_query(self, q):
        return self.embed([q])[0]


class FakeReranker:
    """Scores by morpheme overlap, squashed to 0..1."""

    def rerank(self, query, chunks, top_k):
        import copy

        q = set(tokenize_ko(query))
        out = []
        for c in chunks:
            item = copy.copy(c)
            item.scores = dict(c.scores)
            item.scores["fused_rank"] = c.rank
            overlap = len(q & set(tokenize_ko(c.text))) / max(len(q), 1)
            item.score = overlap
            item.scores["rerank"] = overlap
            out.append(item)
        out.sort(key=lambda c: c.score, reverse=True)
        for r, item in enumerate(out, start=1):
            item.rank = r
        return out[:top_k]


@pytest.fixture(scope="session", autouse=True)
def _load_kiwi_on_main_thread():
    get_kiwi()


@pytest.fixture
def fake_models(monkeypatch, tmp_path):
    fake, rr = FakeEmbedder(), FakeReranker()
    monkeypatch.setattr("app.ingestion.pipeline.get_embedder", lambda: fake)
    monkeypatch.setattr("app.retrieval.vector.get_embedder", lambda: fake)
    monkeypatch.setattr("app.retrieval.reranker.get_reranker", lambda: rr)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIN_VECTOR_SCORE", "0")
    monkeypatch.setenv("QUERY_REWRITE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def clean_db():
    from sqlalchemy import text

    from app.config import get_settings as gs
    from app.db.session import get_engine, init_db
    from app.retrieval.bm25 import invalidate_bm25

    assert gs().database_url.endswith("_test"), "refusing to truncate a non-test database"
    try:
        init_db()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"test database not available: {e}")
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE documents, chunks, traces, app_meta CASCADE"))
    invalidate_bm25()
    yield
