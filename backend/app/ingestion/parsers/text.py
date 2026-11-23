"""Plain text and Markdown parsing. Markdown headings become sections."""

from __future__ import annotations

import re
from pathlib import Path

from app.ingestion.korean import normalize_text
from app.ingestion.parsers.base import ParsedDocument, ParsedPage

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
PART_CHARS = 4000  # split long unpaginated docs into logical "pages" for citation


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def blocks_to_pages(blocks: list[tuple[str | None, str]], title: str, file_type: str
                    ) -> ParsedDocument:
    """blocks: (heading or None, paragraph text). Packs blocks into logical pages."""
    pages: list[ParsedPage] = []
    buf: list[str] = []
    sections: list[tuple[int, str]] = []
    current = ""
    size = 0

    def flush() -> None:
        nonlocal buf, sections, size
        if buf:
            pages.append(ParsedPage(page=len(pages) + 1, text="\n\n".join(buf), sections=sections))
        buf, sections, size = [], [], 0

    for heading, para in blocks:
        if heading:
            current = heading
            if size >= PART_CHARS * 0.5:
                flush()
            sections.append((size, heading))
            continue
        para = normalize_text(para)
        if not para:
            continue
        if size + len(para) > PART_CHARS and buf:
            flush()
        if not buf and current and not sections:
            sections.append((0, current))
        buf.append(para)
        size += len(para) + 2
    flush()
    if not pages:
        pages = [ParsedPage(page=1, text="", sections=[])]
    return ParsedDocument(title=title, file_type=file_type, pages=pages, paginated=False)


def parse_text(path: Path) -> ParsedDocument:
    content = read_text_file(path).replace("\r\n", "\n")
    is_md = path.suffix.lower() in {".md", ".markdown"}
    blocks: list[tuple[str | None, str]] = []
    title = path.stem
    para: list[str] = []

    def end_para() -> None:
        if para:
            blocks.append((None, "\n".join(para)))
            para.clear()

    for line in content.split("\n"):
        m = HEADING_RE.match(line) if is_md else None
        if m:
            end_para()
            heading = m.group(2).strip()
            if len(m.group(1)) == 1 and title == path.stem:
                title = heading
            blocks.append((heading, ""))
        elif not line.strip():
            end_para()
        else:
            para.append(line)
    end_para()
    return blocks_to_pages(blocks, title, "md" if is_md else "txt")
