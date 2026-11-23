"""Lightweight request tracing: per-stage timers saved to the `traces` table.

Chosen over Langfuse self-hosting (needs ClickHouse, Redis, S3) to fit an 8 GB laptop.
The same rows power the frontend's "How I found this" panel.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.db.models import Trace
from app.db.session import session_scope

log = logging.getLogger(__name__)


class Tracer:
    def __init__(self, query: str, mode: str) -> None:
        self.query = query
        self.mode = mode
        self.stages_ms: dict[str, float] = {}
        self.retrieval: dict[str, Any] = {}
        self.extra: dict[str, Any] = {}
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        t = time.perf_counter()
        try:
            yield
        finally:
            self.stages_ms[name] = round((time.perf_counter() - t) * 1000, 1)

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000, 1)

    def save(self, **fields: Any) -> str | None:
        try:
            with session_scope() as session:
                trace = Trace(query=self.query, mode=self.mode, stages_ms=self.stages_ms,
                              retrieval=self.retrieval, total_ms=self.total_ms, **fields)
                session.add(trace)
                session.flush()
                return str(trace.id)
        except Exception:  # tracing must never break answering
            log.exception("Failed to save trace")
            return None
