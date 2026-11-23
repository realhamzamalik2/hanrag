"""Korean-aware text utilities built on Kiwi (kiwipiepy).

Why this module exists:
- Korean is agglutinative: "서울과학기술대학교는" = noun + particle. Whitespace tokens almost
  never match a query term exactly, so BM25 on raw whitespace tokens performs badly.
- PDFs extracted from Korean documents often lose word spacing, or come out in NFD jamo form.
- Real documents mix Korean and English ("AI 연구", "RAG 파이프라인").
"""

from __future__ import annotations

import re
import threading
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from kiwipiepy import Kiwi

HANGUL_RE = re.compile(r"[가-힣]")
LATIN_RE = re.compile(r"[A-Za-z]")

# POS tags kept for BM25: nouns, verb/adjective stems, roots, foreign words, numbers, hanja.
# Particles (J*), endings (E*) and punctuation (S* except SL/SN/SH) are dropped.
KEEP_TAG_PREFIXES = ("NN", "NR", "NP", "VV", "VA", "XR", "SL", "SN", "SH", "MAG")

_kiwi_lock = threading.Lock()


@lru_cache(maxsize=1)
def get_kiwi() -> Kiwi:
    return Kiwi()


@dataclass(frozen=True)
class Sentence:
    text: str
    start: int
    end: int


def normalize_text(text: str) -> str:
    """NFC-normalize, fix PDF line breaks and collapse whitespace while keeping paragraphs."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace(" ", " ").replace("​", "").replace("﻿", "")
    text = re.sub(r"\r\n?", "\n", text)
    # Join English words hyphenated across line breaks: "retrie-\nval" -> "retrieval"
    text = re.sub(r"([A-Za-z])-\n([a-z])", r"\1\2", text)
    # Single newlines inside a paragraph become spaces; blank lines stay paragraph breaks.
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def hangul_ratio(text: str) -> float:
    letters = len(HANGUL_RE.findall(text)) + len(LATIN_RE.findall(text))
    return len(HANGUL_RE.findall(text)) / letters if letters else 0.0


def detect_lang(text: str) -> str:
    """Rough language tag: 'ko', 'en' or 'mixed'."""
    r = hangul_ratio(text)
    if r >= 0.7:
        return "ko"
    if r <= 0.1:
        return "en"
    return "mixed"


def needs_spacing_fix(text: str, threshold: float = 12.0) -> bool:
    """True when Hangul text has suspiciously few spaces (common in broken PDF extraction).

    Normal Korean prose has a space every 3 to 5 syllables.
    """
    hangul = len(HANGUL_RE.findall(text))
    if hangul < 30:
        return False
    spaces = text.count(" ") + 1
    return hangul / spaces > threshold


def fix_spacing(text: str) -> str:
    """Restore Korean word spacing with Kiwi, only when it looks broken."""
    if not needs_spacing_fix(text):
        return text
    with _kiwi_lock:
        return get_kiwi().space(text, reset_whitespace=False)


def split_sentences(text: str) -> list[Sentence]:
    """Sentence split that works for Korean, English and mixed text, with char offsets."""
    if not text.strip():
        return []
    out: list[Sentence] = []
    # Split paragraphs first so a sentence never spans a paragraph break.
    for m in re.finditer(r"[^\n]+", text):
        para, base = m.group(0), m.start()
        with _kiwi_lock:
            sents = get_kiwi().split_into_sents(para)
        for s in sents:
            seg = s.text.strip()
            if seg:
                out.append(Sentence(seg, base + s.start, base + s.end))
    return out


def tokenize_ko(text: str) -> list[str]:
    """Morphological tokens for BM25 (content morphemes only, English lowercased)."""
    with _kiwi_lock:
        tokens = get_kiwi().tokenize(unicodedata.normalize("NFC", text))
    out: list[str] = []
    for t in tokens:
        if t.tag.startswith(KEEP_TAG_PREFIXES):
            form = t.form.lower() if t.tag == "SL" else t.form
            if form.strip():
                out.append(form)
    return out


def tokenize_ko_batch(texts: Iterable[str]) -> list[list[str]]:
    return [tokenize_ko(t) for t in texts]


def tokenize_whitespace(text: str) -> list[str]:
    """Baseline tokenizer for the ablation study: lowercase + split on whitespace/punctuation."""
    return [t for t in re.split(r"[\s\.,!?;:()\[\]\"'“”‘’·…]+", text.lower()) if t]
