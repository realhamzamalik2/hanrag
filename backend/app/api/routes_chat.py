"""Question answering endpoints: search (retrieval only), chat (JSON) and chat/stream (SSE)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from app.api.deps import RATE, db_session, limiter
from app.db.models import Trace
from app.generation import llm
from app.generation.rewrite import rewrite_query
from app.rag import Options, answer_question, answer_question_stream
from app.retrieval.hybrid import retrieve
from app.schemas.api import ChatRequest, ChatResponse, Passage, SearchRequest, TraceOut

router = APIRouter(prefix="/api", tags=["chat"])


def _history(req: ChatRequest) -> list[dict[str, str]]:
    return [t.model_dump() for t in req.history]


@router.post("/search", summary="Retrieval only: every stage with scores (debug panel)")
@limiter.limit(RATE)
async def search(request: Request, req: SearchRequest) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        opts = Options.build(req.mode, req.tokenizer, req.k, req.rewrite, req.document_ids)
        extra: list[str] = []
        query = req.query
        if req.rewrite and llm.is_configured():
            rw = rewrite_query(req.query, [], translate=True)
            query, extra = rw.standalone, [rw.translation] if rw.translation else []
        from app.db.session import session_scope

        with session_scope() as session:
            res = retrieve(session, query, mode=opts.mode,  # type: ignore[arg-type]
                           tokenizer=opts.tokenizer,  # type: ignore[arg-type]
                           extra_queries=extra, k_final=opts.k,
                           document_ids=opts.document_ids)
        return res.to_debug(limit=20)

    return await run_in_threadpool(run)


@router.post("/chat", response_model=ChatResponse, summary="Answer with citations (JSON)")
@limiter.limit(RATE)
async def chat(request: Request, req: ChatRequest) -> ChatResponse:
    if not llm.is_configured():
        raise HTTPException(503, "LLM not configured: set GEMINI_API_KEY and GEMINI_MODEL")
    a = await run_in_threadpool(
        answer_question, req.question, _history(req), mode=req.mode, tokenizer=req.tokenizer,
        k=req.k, rewrite=req.rewrite, document_ids=req.document_ids)
    return ChatResponse(
        question=a.question, standalone_query=a.standalone_query, answer=a.answer,
        refused=a.refused, refusal_reason=a.refusal_reason,
        citations=[Passage(number=c.number, **c.chunk.to_dict()) for c in a.citations],
        passages=[Passage(number=i, **c.to_dict()) for i, c in enumerate(a.chunks, start=1)],
        retrieval=a.retrieval.to_debug() if a.retrieval else {}, stages_ms=a.stages_ms,
        total_ms=a.total_ms, trace_id=a.trace_id, usage=a.usage)


@router.post("/chat/stream", summary="Answer with citations, streamed as Server-Sent Events",
             description="Events: `rewrite`, `retrieval`, `token` (repeated), `done`, `error`.")
@limiter.limit(RATE)
async def chat_stream(request: Request, req: ChatRequest) -> EventSourceResponse:
    if not llm.is_configured():
        raise HTTPException(503, "LLM not configured: set GEMINI_API_KEY and GEMINI_MODEL")

    async def events() -> AsyncIterator[dict[str, str]]:
        gen = answer_question_stream(req.question, _history(req), mode=req.mode,
                                     tokenizer=req.tokenizer, k=req.k, rewrite=req.rewrite,
                                     document_ids=req.document_ids)
        # The pipeline is blocking (models, DB); run it in a worker thread.
        async for ev in iterate_in_threadpool(gen):
            if await request.is_disconnected():
                break
            yield {"event": ev["type"], "data": json.dumps(ev, ensure_ascii=False, default=str)}

    return EventSourceResponse(events(), ping=15)


def _trace_out(t: Trace, with_retrieval: bool) -> TraceOut:
    return TraceOut(id=str(t.id), created_at=t.created_at, query=t.query,
                    rewritten_query=t.rewritten_query, mode=t.mode, answer=t.answer,
                    refused=t.refused, model=t.model, prompt_tokens=t.prompt_tokens,
                    output_tokens=t.output_tokens, total_ms=t.total_ms,
                    stages_ms=t.stages_ms or {}, error=t.error,
                    retrieval=t.retrieval if with_retrieval else None)


@router.get("/traces", response_model=list[TraceOut], tags=["observability"])
def list_traces(limit: int = 50, session: Session = Depends(db_session)) -> list[TraceOut]:
    rows = session.scalars(select(Trace).order_by(Trace.created_at.desc())
                           .limit(min(limit, 200))).all()
    return [_trace_out(t, False) for t in rows]


@router.get("/traces/{trace_id}", response_model=TraceOut, tags=["observability"])
def get_trace(trace_id: str, session: Session = Depends(db_session)) -> TraceOut:
    try:
        t = session.get(Trace, uuid.UUID(trace_id))
    except ValueError:
        t = None
    if t is None:
        raise HTTPException(404, "Trace not found")
    return _trace_out(t, True)
