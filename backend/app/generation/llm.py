"""Gemini API client (free tier) with streaming and token usage capture."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger(__name__)


class LLMNotConfigured(RuntimeError):
    pass


@dataclass
class Usage:
    prompt_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class StreamResult:
    text_parts: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


@lru_cache(maxsize=1)
def _client():  # type: ignore[no-untyped-def]
    s = get_settings()
    if not s.gemini_api_key:
        raise LLMNotConfigured("GEMINI_API_KEY is empty. Add it to .env (free key from "
                               "https://aistudio.google.com).")
    if not s.gemini_model:
        raise LLMNotConfigured("GEMINI_MODEL is empty. Copy a free-tier Flash model ID from "
                               "AI Studio into .env.")
    from google import genai

    return genai.Client(api_key=s.gemini_api_key)


def _config(system: str):  # type: ignore[no-untyped-def]
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=system,
        temperature=get_settings().llm_temperature,
    )


def is_configured() -> bool:
    s = get_settings()
    return bool(s.gemini_api_key and s.gemini_model)


def generate_json(system: str, prompt: str) -> tuple[str, Usage]:
    from google.genai import types

    config = types.GenerateContentConfig(system_instruction=system, temperature=0.0,
                                         response_mime_type="application/json")
    resp = _client().models.generate_content(
        model=get_settings().gemini_model, contents=prompt, config=config)
    um = getattr(resp, "usage_metadata", None)
    return resp.text or "{}", Usage(getattr(um, "prompt_token_count", None),
                                     getattr(um, "candidates_token_count", None))


def generate(system: str, prompt: str) -> tuple[str, Usage]:
    resp = _client().models.generate_content(
        model=get_settings().gemini_model, contents=prompt, config=_config(system))
    um = getattr(resp, "usage_metadata", None)
    usage = Usage(getattr(um, "prompt_token_count", None),
                  getattr(um, "candidates_token_count", None))
    return resp.text or "", usage


def generate_stream(system: str, prompt: str, result: StreamResult) -> Iterator[str]:
    """Yield text deltas; fills `result` with the full text and token usage."""
    stream = _client().models.generate_content_stream(
        model=get_settings().gemini_model, contents=prompt, config=_config(system))
    for chunk in stream:
        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            result.usage = Usage(getattr(um, "prompt_token_count", None),
                                 getattr(um, "candidates_token_count", None))
        delta = chunk.text or ""
        if delta:
            result.text_parts.append(delta)
            yield delta
