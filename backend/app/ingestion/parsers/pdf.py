"""PDF parsing with PyMuPDF: per-page text plus section headings from the PDF outline (TOC).

PDFs store text as positioned lines, not paragraphs. Many generators put every line in its
own block, so treating blocks as paragraphs would break sentences in half. We rebuild
paragraphs: consecutive lines are joined unless the font size changes (a heading), the
vertical gap is unusually large, or the previous line already ends a sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.ingestion.korean import fix_spacing, normalize_text
from app.ingestion.parsers.base import ParsedDocument, ParsedPage

# Attribution line written by scripts/fetch_samples.py; kept in the PDF, not in passages.
# (URLs can wrap onto two lines, so allow spaces inside them.)
ATTRIBUTION_RE = re.compile(r"^Source:\s*https?://.{0,400}?\([^)]*(?:CC BY|licen[cs]e)[^)]*\)\s*$",
                            re.IGNORECASE)
PARSER_VERSION = "2"  # bump when PDF text extraction changes (scripts.rebuild_samples)
SENTENCE_END_RE = re.compile(r"[.!?。！？”’\"')\]]\s*$|[다요죠음함임됨]\.?\s*$")


@dataclass
class _Line:
    text: str
    size: float
    top: float
    bottom: float


def _lines(page: pymupdf.Page) -> list[_Line]:
    out: list[_Line] = []
    data = page.get_text("dict", sort=True)
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            size = max(s.get("size", 0.0) for s in spans)
            _x0, y0, _x1, y1 = line["bbox"]
            out.append(_Line(text, round(size, 1), y0, y1))
    return out


def _paragraphs(lines: list[_Line]) -> list[str]:
    paras: list[list[str]] = []
    prev: _Line | None = None
    for ln in lines:
        new_para = (
            prev is None
            or abs(ln.size - prev.size) > 0.6  # heading / caption / body switch
            or (ln.top - prev.bottom) > 1.2 * max(prev.bottom - prev.top, 1.0)  # big gap
            or SENTENCE_END_RE.search(prev.text) is not None
        )
        if new_para:
            paras.append([ln.text])
        else:
            paras[-1].append(ln.text)
        prev = ln
    out = []
    for p in paras:
        text = " ".join(p)
        text = re.sub(r"([A-Za-z])- ([a-z])", r"\1\2", text)  # re-join hyphenated words
        if not ATTRIBUTION_RE.match(text):
            out.append(text)
    return out


def parse_pdf(path: Path) -> ParsedDocument:
    with pymupdf.open(path) as doc:
        title = (doc.metadata or {}).get("title") or path.stem
        # Outline entries: [level, title, page(1-based)]
        toc_by_page: dict[int, list[str]] = {}
        for _level, heading, page_no in doc.get_toc(simple=True):
            if page_no >= 1:
                toc_by_page.setdefault(page_no, []).append(heading.strip())

        pages: list[ParsedPage] = []
        current_section = ""
        for i, page in enumerate(doc, start=1):
            raw = "\n\n".join(_paragraphs(_lines(page)))
            text = fix_spacing(normalize_text(raw))
            sections: list[tuple[int, str]] = []
            if current_section:
                sections.append((0, current_section))
            for heading in toc_by_page.get(i, []):
                m = re.search(rf"(?:^|\n){re.escape(heading)}(?:\n|$)", text)
                pos = m.start() if m else text.find(heading)
                sections.append((max(pos, 0), heading))
                current_section = heading
            sections.sort(key=lambda s: s[0])
            pages.append(ParsedPage(page=i, text=text, sections=sections))

    return ParsedDocument(title=title, file_type="pdf", pages=pages, paginated=True)
