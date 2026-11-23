"""Prompt templates for grounded, cited answers with explicit refusal."""

from __future__ import annotations

from app.retrieval.types import RetrievedChunk

REFUSAL_TOKEN = "[[INSUFFICIENT_CONTEXT]]"

REFUSAL_MESSAGES = {
    "ko": "제공된 문서에서는 이 질문에 대한 답을 찾을 수 없습니다.",
    "en": "I don't know. The provided documents don't contain enough information to answer this.",
}

SYSTEM_PROMPT = f"""You are HanRAG, a careful question-answering assistant for Korean and English documents.

Rules:
1. Answer ONLY using the numbered context passages. Never use outside knowledge.
2. After every sentence that uses a passage, cite it with its number in square brackets,
   e.g. "...입니다 [2]." or "... in 1443 [1][3]." Only cite numbers that exist.
3. Answer in the SAME LANGUAGE as the question, even if the passages are in another language.
   Keep proper nouns accurate when translating.
4. If the passages do not contain enough information to answer, reply with exactly
   {REFUSAL_TOKEN} and nothing else. Do not guess. Partial support is not enough for
   facts that are missing from the passages.
5. Be concise: 1 to 5 sentences unless the question asks for a list or detail.
"""


def format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        loc = f"p.{c.page}" if c.paginated else (c.section or f"part {c.page}")
        header = f"[{i}] {c.doc_title} ({loc})"
        if c.section and c.paginated:
            header += f" - {c.section}"
        blocks.append(f"{header}\n{c.text}")
    return "\n\n".join(blocks)


def build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    return (
        f"Context passages:\n\n{format_context(chunks)}\n\n"
        f"Question: {question}\n\n"
        "Answer with citations, or the refusal token if the context is insufficient."
    )
