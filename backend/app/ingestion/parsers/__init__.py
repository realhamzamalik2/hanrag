"""Dispatch a file to the right parser by extension."""

from __future__ import annotations

from pathlib import Path

from app.ingestion.parsers.base import ParsedDocument, ParsedPage, UnsupportedFileType

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".hwp", ".hwpx"}


def parse_file(path: Path) -> ParsedDocument:
    ext = path.suffix.lower()
    if ext == ".pdf":
        from app.ingestion.parsers.pdf import parse_pdf

        return parse_pdf(path)
    if ext == ".docx":
        from app.ingestion.parsers.docx import parse_docx

        return parse_docx(path)
    if ext in {".txt", ".md", ".markdown"}:
        from app.ingestion.parsers.text import parse_text

        return parse_text(path)
    if ext in {".hwp", ".hwpx"}:
        from app.ingestion.parsers.hwp import parse_hwp

        return parse_hwp(path)
    raise UnsupportedFileType(f"Unsupported file type: {ext}")


__all__ = ["SUPPORTED_EXTENSIONS", "ParsedDocument", "ParsedPage", "UnsupportedFileType",
           "parse_file"]
