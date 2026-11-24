"""Database engine/session helpers and schema creation."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5,
                         max_overflow=5, connect_args={"connect_timeout": 5})


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create the pgvector extension and all tables (idempotent)."""
    from app.db.models import Base

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    log.info("Database schema ready")


def get_meta(key: str) -> str | None:
    from app.db.models import AppMeta

    with session_scope() as s:
        row = s.get(AppMeta, key)
        return row.value if row else None


def set_meta(key: str, value: str) -> None:
    from app.db.models import AppMeta

    with session_scope() as s:
        s.merge(AppMeta(key=key, value=value))


def embedder_id() -> str:
    st = get_settings()
    return f"{st.embed_backend}:{st.embed_model}"
