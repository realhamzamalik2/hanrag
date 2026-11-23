"""End-to-end RAG: retrieve -> (gate) -> generate with citations -> trace.

Step 1 uses vector search only. Step 2 swaps in hybrid search + reranking.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.db.session import session_scope
from app.generation import llm
from app.generation.citations import (
    Citation,
    extract_citations,
    is_refusal,
    refusal_message,
    strip_invalid_citations,
)
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.observability.tracing import Tracer
from app.retrieval.types import RetrievedChunk
from app.retrieval.vector import vector_search

log = logging.getLogger(__name__)


@dataclass
class Answer:
    question: str
    answer: str
    refused: bool
    citations: list[Citation]
    chunks: list[RetrievedChunk]
    stages_ms: dict[str, float]
    total_ms: float
    trace_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


def retrieve(question: str, k: int | None = None) -> list[RetrievedChunk]:
    s = get_settings()
    with session_scope() as session:
        return vector_search(session, question, k or s.top_k_final)


def answer_question(question: str, k: int | None = None, use_llm: bool = True) -> Answer:
    s = get_settings()
    tracer = Tracer(question, mode="vector")
    with tracer.stage("retrieve_vector"):
        chunks = retrieve(question, k)
    tracer.retrieval = {"vector": [c.to_dict() for c in chunks]}

    top = chunks[0].score if chunks else 0.0
    if not chunks or top < s.min_vector_score:
        text = refusal_message(question)
        trace_id = tracer.save(answer=text, refused=True, model=None)
        return Answer(question, text, True, [], chunks, tracer.stages_ms, tracer.total_ms,
                      trace_id, {"reason": f"top score {top:.3f} < {s.min_vector_score}"})

    if not use_llm:
        trace_id = tracer.save(answer=None, refused=False)
        return Answer(question, "", False, [], chunks, tracer.stages_ms, tracer.total_ms,
                      trace_id)

    prompt = build_user_prompt(question, chunks)
    with tracer.stage("generate"):
        raw, usage = llm.generate(SYSTEM_PROMPT, prompt)

    refused = is_refusal(raw)
    text = refusal_message(question) if refused else strip_invalid_citations(raw, len(chunks))
    citations = [] if refused else extract_citations(text, chunks)
    trace_id = tracer.save(answer=text, refused=refused, model=s.gemini_model,
                           prompt_tokens=usage.prompt_tokens, output_tokens=usage.output_tokens)
    return Answer(question, text, refused, citations, chunks, tracer.stages_ms, tracer.total_ms,
                  trace_id, {"prompt_tokens": usage.prompt_tokens,
                             "output_tokens": usage.output_tokens})


def answer_question_stream(question: str, k: int | None = None) -> Iterator[dict[str, Any]]:
    """Yields events: {'type': 'retrieval'|'token'|'done', ...}. Used by the API in Step 2."""
    s = get_settings()
    tracer = Tracer(question, mode="vector")
    with tracer.stage("retrieve_vector"):
        chunks = retrieve(question, k)
    tracer.retrieval = {"vector": [c.to_dict() for c in chunks]}
    yield {"type": "retrieval", "chunks": [c.to_dict() for c in chunks]}

    if not chunks or chunks[0].score < s.min_vector_score:
        text = refusal_message(question)
        trace_id = tracer.save(answer=text, refused=True)
        yield {"type": "token", "text": text}
        yield {"type": "done", "refused": True, "citations": [], "trace_id": trace_id,
               "stages_ms": tracer.stages_ms}
        return

    result = llm.StreamResult()
    head = ""  # held back until we know the answer is not the refusal token
    decided = False
    with tracer.stage("generate"):
        for delta in llm.generate_stream(SYSTEM_PROMPT, build_user_prompt(question, chunks),
                                         result):
            if decided:
                if not is_refusal(head):
                    yield {"type": "token", "text": delta}
                continue
            head += delta
            stripped = head.lstrip()
            if len(stripped) < len("[[INSUFFICIENT") and "[[INSUFFICIENT".startswith(stripped):
                continue  # still could be the refusal token
            decided = True
            if not is_refusal(head):
                yield {"type": "token", "text": head}
    full = result.text
    refused = is_refusal(full)
    if refused:
        text = refusal_message(question)
        yield {"type": "token", "text": text}
    else:
        if not decided and head:
            yield {"type": "token", "text": head}
        text = strip_invalid_citations(full, len(chunks))
    cites = [] if refused else extract_citations(text, chunks)
    trace_id = tracer.save(answer=text, refused=refused, model=s.gemini_model,
                           prompt_tokens=result.usage.prompt_tokens,
                           output_tokens=result.usage.output_tokens)
    yield {"type": "done", "refused": refused, "trace_id": trace_id,
           "stages_ms": tracer.stages_ms,
           "citations": [{"number": c.number, **c.chunk.to_dict()} for c in cites]}
