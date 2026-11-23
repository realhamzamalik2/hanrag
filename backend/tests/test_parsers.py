from pathlib import Path

import docx
import pymupdf

from app.generation.citations import extract_citations, is_refusal, strip_invalid_citations
from app.ingestion.parsers import parse_file
from app.retrieval.types import RetrievedChunk


def test_markdown_sections_and_title(tmp_path: Path):
    p = tmp_path / "doc.md"
    p.write_text("# 한글\n\n한글은 문자이다.\n\n## 역사\n\n1443년에 창제되었다.\n", encoding="utf-8")
    d = parse_file(p)
    assert d.title == "한글"
    assert not d.paginated
    text = d.pages[0].text
    assert "1443년" in text
    assert [s[1] for s in d.pages[0].sections] == ["한글", "역사"]


def test_cp949_text_file(tmp_path: Path):
    p = tmp_path / "old.txt"
    p.write_bytes("옛날 인코딩 문서입니다.".encode("cp949"))
    assert "옛날 인코딩" in parse_file(p).pages[0].text


def test_pdf_pages_and_toc(tmp_path: Path):
    p = tmp_path / "k.pdf"
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), f"제{i + 1}장\n\n본문 {i + 1}쪽 내용입니다.",
                            fontname="korea", fontsize=11)
    doc.set_toc([[1, "제1장", 1], [1, "제2장", 2]])
    doc.save(p)
    d = parse_file(p)
    assert d.paginated and d.num_pages == 2
    assert "본문 2쪽" in d.pages[1].text
    assert d.pages[1].sections[-1][1] == "제2장"


def test_docx_headings(tmp_path: Path):
    p = tmp_path / "d.docx"
    document = docx.Document()
    document.add_heading("개요", level=1)
    document.add_paragraph("이 문서는 테스트입니다.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "항목"
    table.rows[0].cells[1].text = "값"
    document.save(str(p))
    d = parse_file(p)
    assert "테스트" in d.pages[0].text and "항목 | 값" in d.pages[0].text
    assert d.pages[0].sections[0][1] == "개요"


def _chunk(i: int) -> RetrievedChunk:
    return RetrievedChunk(str(i), "d", "doc", "doc.pdf", i, "", f"text {i}", 0, 6, "ko", True, 0.9)


def test_citation_parsing():
    chunks = [_chunk(1), _chunk(2)]
    ans = "한글은 1443년에 창제되었다 [2]. 세종이 만들었다 [1][2][7]."
    cleaned = strip_invalid_citations(ans, len(chunks))
    assert "[7]" not in cleaned
    assert [c.number for c in extract_citations(cleaned, chunks)] == [2, 1]
    assert is_refusal("[[INSUFFICIENT_CONTEXT]]")
    assert not is_refusal("답변 [1]")
