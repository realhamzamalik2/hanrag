"""PDF parsing with PyMuPDF: per-page text plus section headings from the PDF outline (TOC)."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from app.ingestion.korean import fix_spacing, normalize_text
from app.ingestion.parsers.base import ParsedDocument, ParsedPage


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
            # Join text blocks with blank lines so paragraphs (and headings) stay separate.
            blocks = page.get_text("blocks", sort=True)
            raw = "\n\n".join(b[4] for b in blocks if b[6] == 0 and b[4].strip())
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
