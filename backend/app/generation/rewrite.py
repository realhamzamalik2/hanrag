"""Query rewriting in ONE LLM call:

1. Multi-turn: turn a follow-up ("그럼 언제 반포됐어?") into a standalone question using the
   chat history, so retrieval does not depend on conversation state.
2. Cross-lingual: translate the standalone question into the other language (ko <-> en).
   Dense bge-m3 vectors already work across languages, but BM25 cannot match an English
   query against Korean text. Searching with both versions fixes that.

Any failure falls back to the original question (rewriting must never break answering).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from app.generation import llm
from app.ingestion.korean import detect_lang

log = logging.getLogger(__name__)

REWRITE_SYSTEM = """You rewrite search queries for a Korean/English document search engine.
Return JSON only: {"standalone": "...", "translation": "..."}
- standalone: the user's latest question rewritten to be fully self-contained, resolving
  pronouns and references from the chat history. Same language as the latest question.
  If it is already standalone, copy it unchanged.
- translation: the standalone question translated into TARGET_LANG. Keep names, numbers
  and technical terms accurate (e.g. 훈민정음 -> Hunminjeongeum, 세종 -> King Sejong).
Do not answer the question."""


@dataclass
class Rewrite:
    standalone: str
    translation: str | None
    used_llm: bool
    usage: llm.Usage


def format_history(history: list[dict[str, str]], max_turns: int = 6) -> str:
    lines = []
    for turn in history[-max_turns:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = (turn.get("content") or "").strip().replace("\n", " ")
        lines.append(f"{role}: {content[:500]}")
    return "\n".join(lines)


RETRY_WAIT_S = 2.0


def _generate_with_one_retry(system: str, prompt: str) -> tuple[str, llm.Usage]:
    """The free tier often answers 503 "high demand" for a second or two. Without the
    rewrite there is no translation, and cross-lingual questions get refused, so retry once."""
    try:
        return llm.generate_json(system, prompt)
    except Exception as e:  # noqa: BLE001
        if not any(c in str(e) for c in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
            raise
        log.info("Query rewrite busy (%s), retrying once", str(e)[:60])
        time.sleep(RETRY_WAIT_S)
        return llm.generate_json(system, prompt)


def rewrite_query(question: str, history: list[dict[str, str]] | None,
                  translate: bool = True) -> Rewrite:
    history = history or []
    if not history and not translate:
        return Rewrite(question, None, False, llm.Usage())
    target = "English" if detect_lang(question) != "en" else "Korean"
    prompt = (
        f"TARGET_LANG: {target}\n\n"
        f"Chat history:\n{format_history(history) or '(none)'}\n\n"
        f"Latest question: {question}"
    )
    try:
        text, usage = _generate_with_one_retry(REWRITE_SYSTEM.replace("TARGET_LANG", target), prompt)
        data = json.loads(text)
        standalone = str(data.get("standalone") or question).strip() or question
        translation = str(data.get("translation") or "").strip() or None
        return Rewrite(standalone, translation if translate else None, True, usage)
    except Exception as e:  # noqa: BLE001
        log.warning("Query rewrite failed, using original question: %s", e)
        return Rewrite(question, None, False, llm.Usage())
