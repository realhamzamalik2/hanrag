"""Pydantic request/response schemas for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ModeT = Literal["vector", "bm25", "hybrid", "hybrid_rerank"]
TokenizerT = Literal["kiwi", "whitespace"]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class RetrievalOptions(BaseModel):
    mode: ModeT | None = Field(None, description="Retrieval mode; defaults to server setting")
    tokenizer: TokenizerT | None = Field(None, description="BM25 tokenizer")
    k: int | None = Field(None, ge=1, le=20, description="Passages given to the LLM")
    rewrite: bool | None = Field(None, description="Rewrite + translate the query (1 LLM call)")
    document_ids: list[str] | None = Field(None, description="Restrict to these documents")


class ChatRequest(RetrievalOptions):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class SearchRequest(RetrievalOptions):
    query: str = Field(min_length=1, max_length=2000)


class Passage(BaseModel):
    number: int | None = None
    chunk_id: str
    document_id: str
    doc_title: str
    filename: str
    page: int
    section: str
    text: str
    char_start: int
    char_end: int
    lang: str
    paginated: bool
    score: float
    rank: int
    scores: dict[str, float] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    question: str
    standalone_query: str | None
    answer: str
    refused: bool
    refusal_reason: str | None
    citations: list[Passage]
    passages: list[Passage]
    retrieval: dict[str, Any]
    stages_ms: dict[str, float]
    total_ms: float
    trace_id: str | None
    usage: dict[str, Any]


class DocumentOut(BaseModel):
    id: str
    filename: str
    title: str
    file_type: str
    lang: str
    paginated: bool
    num_pages: int
    num_chunks: int
    num_chars: int
    status: str
    error: str | None
    source_url: str | None
    license: str | None
    ingest_ms: float | None
    created_at: datetime


class ChunkOut(BaseModel):
    id: str
    chunk_index: int
    page: int
    section: str
    text: str
    char_start: int
    char_end: int
    lang: str


class JobOut(BaseModel):
    id: str
    filename: str
    status: Literal["queued", "running", "done", "failed"]
    stage: str
    progress: float
    document_id: str | None = None
    error: str | None = None
    skipped: bool = False


class StatsOut(BaseModel):
    documents: int
    chunks: int
    pages: int
    chars: int
    by_lang: dict[str, int]
    by_type: dict[str, int]
    questions: int
    refusals: int
    avg_latency_ms: float | None


class TraceOut(BaseModel):
    id: str
    created_at: datetime
    query: str
    rewritten_query: str | None
    mode: str
    answer: str | None
    refused: bool
    model: str | None
    prompt_tokens: int | None
    output_tokens: int | None
    total_ms: float | None
    stages_ms: dict[str, float]
    retrieval: dict[str, Any] | None = None
    error: str | None = None
