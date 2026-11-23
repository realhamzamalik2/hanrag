"""Download openly licensed demo documents (Wikipedia, CC BY-SA 4.0) into data/samples/.

Each article is saved as Markdown, and Korean articles are also rendered to a multi-page PDF
(with PyMuPDF's built-in Korean font) so the demo shows real page-number citations.
Attribution is written to data/samples/SOURCES.md and sources.json.

Usage (from backend/):  uv run python -m scripts.fetch_samples
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx
import pymupdf

from app.config import ROOT_DIR

OUT = ROOT_DIR / "data" / "samples"
LICENSE = "CC BY-SA 4.0"
UA = {"User-Agent": "HanRAG-demo/0.1 (portfolio project; github.com/realhamzamalik2/hanrag)"}

# (lang, title, output stem). Pairs across languages support cross-lingual eval questions.
ARTICLES = [
    ("ko", "한글", "ko_hangul"),
    ("ko", "세종", "ko_sejong"),
    ("ko", "훈민정음", "ko_hunminjeongeum"),
    ("ko", "경복궁", "ko_gyeongbokgung"),
    ("ko", "김치", "ko_kimchi"),
    ("ko", "서울특별시", "ko_seoul"),
    ("en", "Hangul", "en_hangul"),
    ("en", "Retrieval-augmented generation", "en_rag"),
    ("en", "Kimchi", "en_kimchi"),
]

SKIP_SECTIONS = {"같이 보기", "각주", "참고 문헌", "외부 링크", "내용주", "출처",
                 "See also", "References", "External links", "Notes", "Further reading",
                 "Bibliography", "Sources"}


def fetch_extract(client: httpx.Client, lang: str, title: str) -> tuple[str, str]:
    r = client.get(f"https://{lang}.wikipedia.org/w/api.php", params={
        "action": "query", "prop": "extracts|info", "explaintext": 1, "exsectionformat": "wiki",
        "inprop": "url", "titles": title, "format": "json", "formatversion": 2, "redirects": 1,
    })
    r.raise_for_status()
    page = r.json()["query"]["pages"][0]
    return page["extract"], page["fullurl"]


def to_markdown(title: str, extract: str) -> str:
    out = [f"# {title}", ""]
    skipping = False
    for line in extract.split("\n"):
        m = re.match(r"^(={2,6})\s*(.+?)\s*\1\s*$", line)
        if m:
            heading = m.group(2)
            skipping = heading in SKIP_SECTIONS
            if not skipping:
                out += ["", "#" * len(m.group(1)) + " " + heading, ""]
            continue
        if not skipping:
            out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def markdown_to_pdf(md: str, title: str, source_url: str, path: Path) -> None:
    """Render Markdown to A4 pages with an outline (TOC) so sections map to real pages."""
    doc = pymupdf.open()
    doc.set_metadata({"title": title, "subject": f"Source: {source_url} ({LICENSE})"})
    rect = pymupdf.Rect(56, 56, 539, 786)
    toc: list[list] = []
    state = {"page": doc.new_page(width=595, height=842), "y": rect.y0, "empty": True}

    def place(text: str, size: float) -> bool:
        if rect.y1 - state["y"] < size * 2:  # no room left on this page
            return False
        box = pymupdf.Rect(rect.x0, state["y"], rect.x1, rect.y1)
        spare = state["page"].insert_textbox(box, text, fontsize=size, fontname="korea",
                                             lineheight=1.5)
        if spare < 0:  # overflow: PyMuPDF writes nothing
            return False
        state["y"] = rect.y1 - spare + size * 0.6
        state["empty"] = False
        return True

    def new_page() -> None:
        state.update(page=doc.new_page(width=595, height=842), y=rect.y0, empty=True)

    def write(text: str, size: float) -> None:
        if place(text, size):
            return
        if not state["empty"]:
            new_page()
            if place(text, size):
                return
        # Longer than a whole page: pack as many sentences as fit, then continue.
        parts = re.split(r"(?<=[.!?])\s+", text)
        if len(parts) == 1:
            parts = [text[i:i + 400] for i in range(0, len(text), 400)]
        while parts:
            lo, hi = 0, len(parts)  # largest prefix that fits on the current page
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if fits(" ".join(parts[:mid]), size):
                    lo = mid
                else:
                    hi = mid - 1
            if lo == 0:
                if state["empty"]:  # a single part bigger than a page: hard split
                    half = len(parts[0]) // 2
                    parts = [parts[0][:half], parts[0][half:], *parts[1:]]
                else:
                    new_page()
                continue
            place(" ".join(parts[:lo]), size)
            parts = parts[lo:]
            if parts:
                new_page()

    def fits(text: str, size: float) -> bool:
        if rect.y1 - state["y"] < size * 2:
            return False
        scratch = pymupdf.open()
        pg = scratch.new_page(width=595, height=842)
        box = pymupdf.Rect(rect.x0, state["y"], rect.x1, rect.y1)
        ok = pg.insert_textbox(box, text, fontsize=size, fontname="korea", lineheight=1.5) >= 0
        scratch.close()
        return ok

    blocks = [b.strip() for b in md.split("\n\n") if b.strip()]
    for n, block in enumerate(blocks):
        m = re.match(r"^(#{1,6})\s+(.+)$", block)
        if m:
            level, heading = len(m.group(1)), m.group(2)
            if state["y"] > rect.y1 - 80:  # avoid a heading stranded at the page bottom
                new_page()
            write(heading, 16 if level == 1 else 12.5)
            toc.append([min(level, 2) if level > 1 else 1, heading, state["page"].number + 1])
            if n == 0:
                write(f"Source: {source_url} (Wikipedia, {LICENSE})", 8)
        else:
            write(block, 10.5)
    # TOC levels must start at 1 and not jump by more than 1.
    fixed, prev = [], 0
    for level, heading, page_no in toc:
        level = min(level, prev + 1) if prev else 1
        fixed.append([level, heading, page_no])
        prev = level
    doc.set_toc(fixed)
    doc.save(path, garbage=3, deflate=True)
    doc.close()


def save_article(lang: str, title: str, stem: str, md: str, url: str) -> Path:
    if lang == "ko":
        pdf_path = OUT / f"{stem}.pdf"
        markdown_to_pdf(md, title, url, pdf_path)
        with pymupdf.open(pdf_path) as d:
            print(f"[done] {pdf_path.name} ({d.page_count} pages)")
        return pdf_path
    md_path = OUT / f"{stem}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"[done] {md_path.name}")
    return md_path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sources: dict[str, dict[str, str]] = {}
    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as client:
        for lang, title, stem in ARTICLES:
            try:
                extract, url = fetch_extract(client, lang, title)
            except Exception as e:
                print(f"[fail] {title}: {e}")
                continue
            md = to_markdown(title, extract)
            try:
                saved = save_article(lang, title, stem, md, url)
            except Exception as e:
                print(f"[fail] {title}: {e}")
                continue
            sources[saved.name] = {"url": url, "license": LICENSE, "title": title}
            time.sleep(0.5)

    (OUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    lines = ["# Sample documents and licenses", "",
             "All sample documents are adapted from Wikipedia and licensed under "
             "[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). "
             "Changes: reference sections removed, Korean articles re-typeset as PDF.", ""]
    for name, meta in sources.items():
        lines.append(f"- `{name}`: [{meta['title']}]({meta['url']}), Wikipedia contributors, "
                     f"{meta['license']}")
    (OUT / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {len(sources)} files to {OUT}")
    return 0 if sources else 1


if __name__ == "__main__":
    sys.exit(main())
