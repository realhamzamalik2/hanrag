"""HanRAG FastAPI application.

Run (from backend/):  uv run uvicorn app.main:app --port 8000
Docs:                 http://localhost:8000/docs
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app import __version__
from app.api import routes_chat, routes_documents
from app.api.deps import limiter
from app.config import get_settings
from app.generation import llm
from app.logging_setup import setup_logging

# Print a Python traceback even when a native library (Kiwi, ONNX Runtime) crashes the process.
faulthandler.enable(file=sys.stderr, all_threads=True)

log = logging.getLogger("hanrag")
_models_ready = threading.Event()


def _warm_models() -> None:
    """Load models and build the BM25 index in the background so the first question is fast."""
    try:
        from app.db.session import session_scope
        from app.retrieval.bm25 import get_bm25
        from app.retrieval.embedder import get_embedder
        from app.retrieval.reranker import get_reranker

        get_embedder().embed_query("warm up")
        with session_scope() as session:
            get_bm25(session, get_settings().bm25_tokenizer)  # type: ignore[arg-type]
        _models_ready.set()  # answering works from here; the reranker is optional
        if get_settings().retrieval_mode == "hybrid_rerank":
            try:
                get_reranker()
            except Exception as e:  # noqa: BLE001
                log.warning("Reranker not loaded (answers use hybrid ranking): %s", e)
        log.info("Models ready")
    except Exception:
        log.exception("Model warm-up failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    setup_logging(s.log_level)
    # Load Kiwi on the main thread: its native init can overflow small worker-thread stacks.
    from app.ingestion.korean import get_kiwi

    log.info("Loading Kiwi tokenizer")
    get_kiwi()
    log.info("Kiwi ready")
    try:
        from app.db.session import init_db

        init_db()
    except Exception:
        log.exception("Database init failed; is PostgreSQL running?")
    old = threading.stack_size()
    threading.stack_size(64 * 1024 * 1024)
    threading.Thread(target=_warm_models, name="warmup", daemon=True).start()
    threading.stack_size(old)
    yield


app = FastAPI(
    title="HanRAG API",
    version=__version__,
    description="Korean + English RAG with hybrid search (Kiwi BM25 + bge-m3 vectors + RRF), "
                "cross-encoder reranking, exact citations and refusal.",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origin_list,
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": f"Rate limit exceeded: {exc.detail}"}, status_code=429)


app.include_router(routes_documents.router)
app.include_router(routes_chat.router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, Any]:
    db_ok = True
    try:
        from app.db.session import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    from app.retrieval.reranker import reranker_status

    return {"status": "ok" if db_ok else "degraded", "database": db_ok,
            "models_ready": _models_ready.is_set(), "reranker": reranker_status(),
            "llm_configured": llm.is_configured()}


@app.get("/api/config", tags=["system"])
def config() -> dict[str, Any]:
    s = get_settings()
    return {
        "embed_model": s.embed_model, "rerank_model": s.rerank_model,
        "llm_model": s.gemini_model or None, "retrieval_mode": s.retrieval_mode,
        "bm25_tokenizer": s.bm25_tokenizer, "modes": ["vector", "bm25", "hybrid",
                                                       "hybrid_rerank"],
        "top_k": {"bm25": s.top_k_bm25, "vector": s.top_k_vector,
                  "rerank": s.top_k_rerank, "final": s.top_k_final},
        "rrf_k": s.rrf_k, "query_rewrite": s.query_rewrite,
    }
