"""Shared API dependencies: rate limiter and DB session."""

from __future__ import annotations

from collections.abc import Iterator

from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import session_scope

limiter = Limiter(key_func=get_remote_address, default_limits=[])
RATE = get_settings().rate_limit


def db_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session
