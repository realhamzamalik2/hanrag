"""Common types for document parsers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    """One unit of citation. For PDFs this is a real page; for DOCX/TXT/MD it is page 1..n
    of logical parts, and `section` carries the heading for citations."""

    page: int
    text: str
    sections: list[tuple[int, str]] = field(default_factory=list)
    """(char_offset_in_text, heading) pairs, sorted by offset."""


@dataclass
class ParsedDocument:
    title: str
    file_type: str
    pages: list[ParsedPage]
    paginated: bool  # True only when page numbers are real (PDF)

    @property
    def num_pages(self) -> int:
        return len(self.pages)


class UnsupportedFileType(ValueError):
    pass
