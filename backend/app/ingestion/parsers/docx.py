"""DOCX parsing with python-docx. Heading styles become sections; tables are flattened."""

from __future__ import annotations

from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.parsers.text import blocks_to_pages


def _iter_block_items(document: docx.document.Document):  # type: ignore[name-defined]
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, document)
        elif tag == "tbl":
            yield Table(child, document)


def parse_docx(path: Path) -> ParsedDocument:
    document = docx.Document(str(path))
    title = (document.core_properties.title or "").strip() or path.stem
    blocks: list[tuple[str | None, str]] = []
    for item in _iter_block_items(document):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            style = (item.style.name if item.style is not None else "") or ""
            if style.lower().startswith(("heading", "title", "제목")):
                blocks.append((text, ""))
            else:
                blocks.append((None, text))
        else:
            rows = []
            for row in item.rows:
                cells = [c.text.strip() for c in row.cells]
                rows.append(" | ".join(cells))
            if rows:
                blocks.append((None, "\n".join(rows)))
    return blocks_to_pages(blocks, title, "docx")
