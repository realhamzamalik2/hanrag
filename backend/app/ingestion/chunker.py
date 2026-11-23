"""Korean-aware, sentence-based chunking with citation metadata.

Design choices (interview talking points):
- Split on sentences (Kiwi), never mid-sentence, so a cited passage reads cleanly.
- Chunks never cross a page boundary, so every chunk has one exact page number to cite.
- Size is measured in characters, not whitespace tokens: Korean has far fewer spaces per
  unit of meaning than English, so "N words" means very different amounts of text.
- A small sentence overlap keeps context that straddles a chunk boundary retrievable.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable
from dataclasses import dataclass

from app.ingestion.korean import Sentence, detect_lang, split_sentences
from app.ingestion.parsers.base import ParsedDocument, ParsedPage


@dataclass
class Chunk:
    chunk_index: int
    page: int
    section: str
    text: str
    char_start: int  # offset in the page text
    char_end: int
    lang: str


def _section_at(sections: list[tuple[int, str]], offset: int) -> str:
    if not sections:
        return ""
    offsets = [s[0] for s in sections]
    i = bisect.bisect_right(offsets, offset) - 1
    return sections[i][1] if i >= 0 else sections[0][1]


def _hard_split(sent: Sentence, max_chars: int) -> list[Sentence]:
    """Split an over-long 'sentence' (tables, lists, no punctuation) at spaces."""
    parts: list[Sentence] = []
    text, base = sent.text, sent.start
    pos = 0
    while pos < len(text):
        end = min(pos + max_chars, len(text))
        if end < len(text):
            space = text.rfind(" ", pos + max_chars // 2, end)
            if space > pos:
                end = space
        piece = text[pos:end].strip()
        if piece:
            parts.append(Sentence(piece, base + pos, base + end))
        pos = end
    return parts


def chunk_page(
    page: ParsedPage,
    max_chars: int,
    overlap_sentences: int,
    min_chars: int,
    start_index: int = 0,
    splitter: Callable[[str], list[Sentence]] = split_sentences,
) -> list[Chunk]:
    sentences: list[Sentence] = []
    for s in splitter(page.text):
        sentences.extend(_hard_split(s, max_chars) if len(s.text) > max_chars else [s])
    if not sentences:
        return []

    chunks: list[Chunk] = []
    i = 0
    while i < len(sentences):
        group = [sentences[i]]
        length = len(sentences[i].text)
        j = i + 1
        while j < len(sentences) and length + 1 + len(sentences[j].text) <= max_chars:
            group.append(sentences[j])
            length += 1 + len(sentences[j].text)
            j += 1
        start, end = group[0].start, group[-1].end
        text = page.text[start:end].strip()
        chunks.append(Chunk(
            chunk_index=start_index + len(chunks),
            page=page.page,
            section=_section_at(page.sections, start),
            text=text,
            char_start=start,
            char_end=end,
            lang=detect_lang(text),
        ))
        if j >= len(sentences):
            break
        # Step forward, keeping `overlap_sentences` sentences of overlap, but always advance.
        i = max(j - overlap_sentences, i + 1)

    # Merge a tiny trailing chunk into the previous one on the same page.
    if len(chunks) >= 2 and len(chunks[-1].text) < min_chars:
        last, prev = chunks.pop(), chunks[-1]
        prev.char_end = last.char_end
        prev.text = page.text[prev.char_start:prev.char_end].strip()
        prev.lang = detect_lang(prev.text)
    return chunks


def chunk_document(
    doc: ParsedDocument,
    max_chars: int = 700,
    overlap_sentences: int = 1,
    min_chars: int = 40,
    splitter: Callable[[str], list[Sentence]] = split_sentences,
) -> list[Chunk]:
    out: list[Chunk] = []
    for page in doc.pages:
        out.extend(chunk_page(page, max_chars, overlap_sentences, min_chars,
                              start_index=len(out), splitter=splitter))
    return out
