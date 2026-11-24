"""End-to-end RAG pipeline.

question (+history)
  -> rewrite (standalone + ko<->en translation, 1 LLM call, optional)
  -> retrieve (BM25 + vectors -> RRF -> reranker; mode is configurable for ablations)
  -> gate (refuse early when nothing relevant was found; saves LLM quota)
  -> generate (Gemini, streamed, strict [n] citations or the refusal token)
  -> validate citations, save a trace
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
from app.generation.rewrite import Rewrite, rewrite_query
from app.observability.tracing import Tracer
from app.retrieval.hybrid import RetrievalResult, retrieve
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)
REFUSAL_PREFIX = "[[INSUFFICIENT"


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
    retrieval: RetrievalResult | None = None
    standalone_query: str | None = None
    refusal_reason: str | None = None


@dataclass
class Options:
    mode: str
    tokenizer: str
    k: int
    rewrite: bool
    document_ids: list[str] | None = None

    @classmethod
    def build(cls, mode: str | None = None, tokenizer: str | None = None, k: int | None = None,
              rewrite: bool | None = None, document_ids: list[str] | None = None) -> Options:
        s = get_settings()
        return cls(mode=mode or s.retrieval_mode, tokenizer=tokenizer or s.bm25_tokenizer,
                   k=k or s.top_k_final,
                   rewrite=s.query_rewrite if rewrite is None else rewrite,
                   document_ids=document_ids)


def gate(res: RetrievalResult) -> str | None:
    """Return a refusal reason if retrieval clearly found nothing relevant."""
    s = get_settings()
    if not res.final:
        return "no passages retrieved"
    if res.reranked:
        if res.top_score < s.min_rerank_score:
            return f"top rerank score {res.top_score:.3f} < {s.min_rerank_score}"
    elif res.mode == "vector" and res.top_score < s.min_vector_score:
        return f"top vector score {res.top_score:.3f} < {s.min_vector_score}"
    return None


def _prepare(question: str, history: list[dict[str, str]] | None, opts: Options,
             tracer: Tracer, use_llm: bool) -> tuple[Rewrite, RetrievalResult]:
    rw = Rewrite(question, None, False, llm.Usage())
    if use_llm and llm.is_configured() and (opts.rewrite or history):
        with tracer.stage("rewrite"):
            rw = rewrite_query(question, history, translate=opts.rewrite)
    extra = [rw.translation] if rw.translation else []
    with session_scope() as session:
        res = retrieve(session, rw.standalone, mode=opts.mode,  # type: ignore[arg-type]
                       tokenizer=opts.tokenizer,  # type: ignore[arg-type]
                       extra_queries=extra, k_final=opts.k, document_ids=opts.document_ids)
    for name, ms in res.stages_ms.items():
        tracer.stages_ms[f"retrieve_{name}"] = ms
    tracer.retrieval = res.to_debug()
    return rw, res


def _finish(text_raw: str, question: str, chunks: list[RetrievedChunk]
            ) -> tuple[str, bool, list[Citation]]:
    refused = is_refusal(text_raw)
    if refused:
        return refusal_message(question), True, []
    text = strip_invalid_citations(text_raw, len(chunks)).strip()
    return text, False, extract_citations(text, chunks)


def answer_question(question: str, history: list[dict[str, str]] | None = None, *,
                    mode: str | None = None, tokenizer: str | None = None,
                    k: int | None = None, use_llm: bool = True, rewrite: bool | None = None,
                    document_ids: list[str] | None = None) -> Answer:
    opts = Options.build(mode, tokenizer, k, rewrite, document_ids)
    tracer = Tracer(question, mode=opts.mode)
    rw, res = _prepare(question, history, opts, tracer, use_llm)
    chunks = res.final
    usage: dict[str, Any] = {"rewrite_prompt_tokens": rw.usage.prompt_tokens,
                             "rewrite_output_tokens": rw.usage.output_tokens}

    reason = gate(res)
    if reason or not use_llm:
        text = refusal_message(question) if reason else ""
        trace_id = tracer.save(answer=text or None, refused=bool(reason),
                               rewritten_query=rw.standalone, error=reason)
        return Answer(question, text, bool(reason), [], chunks, tracer.stages_ms,
                      tracer.total_ms, trace_id, usage, res, rw.standalone, reason)

    with tracer.stage("generate"):
        raw, u = llm.generate(SYSTEM_PROMPT, build_user_prompt(question, chunks))
    text, refused, cites = _finish(raw, question, chunks)
    usage.update(prompt_tokens=u.prompt_tokens, output_tokens=u.output_tokens)
    trace_id = tracer.save(answer=text, refused=refused, model=get_settings().gemini_model,
                           prompt_tokens=u.prompt_tokens, output_tokens=u.output_tokens,
                           rewritten_query=rw.standalone)
    return Answer(question, text, refused, cites, chunks, tracer.stages_ms, tracer.total_ms,
                  trace_id, usage, res, rw.standalone, "model refused" if refused else None)


def answer_question_stream(question: str, history: list[dict[str, str]] | None = None, *,
                           mode: str | None = None, tokenizer: str | None = None,
                           k: int | None = None, rewrite: bool | None = None,
                           document_ids: list[str] | None = None
                           ) -> Iterator[dict[str, Any]]:
    """Yield SSE-ready events:
    rewrite -> retrieval -> token* -> done   (or error at any point)."""
    opts = Options.build(mode, tokenizer, k, rewrite, document_ids)
    tracer = Tracer(question, mode=opts.mode)
    try:
        rw, res = _prepare(question, history, opts, tracer, use_llm=True)
    except Exception as e:
        log.exception("Retrieval failed")
        tracer.save(error=f"retrieval: {e}")
        yield {"type": "error", "message": f"Retrieval failed: {e}"}
        return
    yield {"type": "rewrite", "standalone": rw.standalone, "translation": rw.translation}
    chunks = res.final
    yield {"type": "retrieval", "retrieval": res.to_debug(),
           "passages": [{"number": i, **c.to_dict()} for i, c in enumerate(chunks, start=1)]}

    reason = gate(res)
    if reason:
        text = refusal_message(question)
        trace_id = tracer.save(answer=text, refused=True, rewritten_query=rw.standalone,
                               error=reason)
        yield {"type": "token", "text": text}
        yield {"type": "done", "refused": True, "refusal_reason": reason, "citations": [],
               "trace_id": trace_id, "stages_ms": tracer.stages_ms,
               "total_ms": tracer.total_ms}
        return

    result = llm.StreamResult()
    head, decided, suppress = "", False, False
    try:
        with tracer.stage("generate"):
            for delta in llm.generate_stream(SYSTEM_PROMPT, build_user_prompt(question, chunks),
                                             result):
                if decided:
                    if not suppress:
                        yield {"type": "token", "text": delta}
                    continue
                head += delta
                stripped = head.lstrip()
                # Hold output back while it could still be the refusal token.
                if len(stripped) < len(REFUSAL_PREFIX) and REFUSAL_PREFIX.startswith(stripped):
                    continue
                decided = True
                suppress = is_refusal(head) or stripped.startswith(REFUSAL_PREFIX)
                if not suppress:
                    yield {"type": "token", "text": head}
    except Exception as e:
        log.exception("Generation failed")
        tracer.save(error=f"generation: {e}", rewritten_query=rw.standalone)
        yield {"type": "error", "message": f"Generation failed: {e}"}
        return

    if not decided and head and not is_refusal(head):
        yield {"type": "token", "text": head}
    text, refused, cites = _finish(result.text, question, chunks)
    if refused:
        yield {"type": "token", "text": text}
    trace_id = tracer.save(answer=text, refused=refused, model=get_settings().gemini_model,
                           prompt_tokens=result.usage.prompt_tokens,
                           output_tokens=result.usage.output_tokens,
                           rewritten_query=rw.standalone)
    yield {"type": "done", "refused": refused, "answer": text, "trace_id": trace_id,
           "refusal_reason": "model refused" if refused else None,
           "stages_ms": tracer.stages_ms, "total_ms": tracer.total_ms,
           "citations": [{"number": c.number, **c.chunk.to_dict()} for c in cites]}
