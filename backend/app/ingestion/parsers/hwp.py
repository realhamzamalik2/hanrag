"""Best-effort HWP support.

- HWPX (OOXML-like zip of XML, used by newer Hangul versions): fully parsed.
- HWP 5.x (binary OLE): text extracted from BodyText sections (zlib-compressed records).
  Layout, tables and page numbers are not recovered, so citations use logical parts.
"""

from __future__ import annotations

import re
import struct
import zipfile
import zlib
from pathlib import Path

from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.parsers.text import blocks_to_pages

HWPTAG_PARA_TEXT = 67


def _parse_hwpx(path: Path) -> list[str]:
    paras: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
        for name in names:
            xml = z.read(name).decode("utf-8", errors="replace")
            for p in re.findall(r"<hp:p\b.*?</hp:p>", xml, flags=re.S):
                text = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", p, flags=re.S))
                text = re.sub(r"<[^>]+>", "", text)
                text = (text.replace("&lt;", "<").replace("&gt;", ">")
                        .replace("&amp;", "&").replace("&quot;", '"'))
                if text.strip():
                    paras.append(text.strip())
    return paras


def _hwp5_section_text(data: bytes) -> list[str]:
    paras: list[str] = []
    i = 0
    while i + 4 <= len(data):
        header = struct.unpack_from("<I", data, i)[0]
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            size = struct.unpack_from("<I", data, i)[0]
            i += 4
        if tag_id == HWPTAG_PARA_TEXT:
            raw = data[i:i + size]
            chars: list[str] = []
            j = 0
            while j + 1 < len(raw):
                code = struct.unpack_from("<H", raw, j)[0]
                # Control chars occupy 8 UTF-16 units (except a few single-unit ones).
                if code < 32:
                    if code in (0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31):
                        if code in (10, 13):
                            chars.append("\n")
                        j += 2
                    else:
                        j += 16
                    continue
                chars.append(chr(code))
                j += 2
            text = "".join(chars).strip()
            if text:
                paras.append(text)
        i += size
    return paras


def _parse_hwp5(path: Path) -> list[str]:
    import olefile

    paras: list[str] = []
    with olefile.OleFileIO(str(path)) as ole:
        header = ole.openstream("FileHeader").read()
        flags = struct.unpack_from("<I", header, 36)[0]
        compressed = bool(flags & 0x01)
        if flags & 0x02:
            raise ValueError("Password-protected HWP files are not supported.")
        sections = sorted(
            (e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
            key=lambda e: int(re.sub(r"\D", "", e[1]) or 0),
        )
        for entry in sections:
            data = ole.openstream(entry).read()
            if compressed:
                data = zlib.decompress(data, -15)
            paras.extend(_hwp5_section_text(data))
    return paras


def parse_hwp(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    paras = _parse_hwpx(path) if suffix == ".hwpx" else _parse_hwp5(path)
    blocks: list[tuple[str | None, str]] = [(None, p) for p in paras]
    return blocks_to_pages(blocks, path.stem, suffix.lstrip("."))
