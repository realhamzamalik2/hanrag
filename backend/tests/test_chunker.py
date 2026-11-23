from app.ingestion.chunker import chunk_document, chunk_page
from app.ingestion.parsers.base import ParsedDocument, ParsedPage

KO = ("한글은 조선의 세종이 1443년에 창제한 문자이다. 처음에는 훈민정음이라고 불렸다. "
      "한글은 자음과 모음을 조합하여 음절을 표기한다. 현재 대한민국과 북한에서 공식 문자로 쓰인다. ")


def test_chunks_respect_max_chars_and_sentences():
    page = ParsedPage(page=3, text=KO * 10)
    chunks = chunk_page(page, max_chars=200, overlap_sentences=1, min_chars=20)
    assert len(chunks) > 3
    for c in chunks:
        assert len(c.text) <= 200
        assert c.page == 3
        assert c.text.endswith(("다.", "다"))  # never cut mid-sentence
        assert page.text[c.char_start:c.char_end].strip() == c.text


def test_overlap_repeats_last_sentence():
    page = ParsedPage(page=1, text=KO * 4)
    chunks = chunk_page(page, max_chars=150, overlap_sentences=1, min_chars=10)
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.char_start < a.char_end  # overlapping spans


def test_chunks_never_cross_pages_and_indices_are_global():
    doc = ParsedDocument("t", "pdf", [ParsedPage(1, KO * 3), ParsedPage(2, KO * 3)], True)
    chunks = chunk_document(doc, max_chars=180)
    assert {c.page for c in chunks} == {1, 2}
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_section_metadata():
    text = "서론 내용입니다. " * 5 + "본론 내용입니다. " * 5
    page = ParsedPage(1, text, sections=[(0, "서론"), (text.index("본론"), "본론")])
    chunks = chunk_page(page, max_chars=60, overlap_sentences=0, min_chars=5)
    assert chunks[0].section == "서론"
    assert chunks[-1].section == "본론"


def test_long_unpunctuated_text_is_hard_split():
    page = ParsedPage(1, "표 데이터 " * 300)
    chunks = chunk_page(page, max_chars=300, overlap_sentences=0, min_chars=10)
    assert all(len(c.text) <= 300 for c in chunks)


def test_empty_page():
    assert chunk_page(ParsedPage(1, "   "), 500, 1, 10) == []
