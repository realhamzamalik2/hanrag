from app.ingestion.korean import (
    detect_lang,
    fix_spacing,
    needs_spacing_fix,
    normalize_text,
    split_sentences,
    tokenize_ko,
    tokenize_whitespace,
)


def test_normalize_nfd_to_nfc_and_line_joins():
    nfd = "한글"  # "한글" in decomposed jamo
    out = normalize_text(f"{nfd} 문서\n줄바꿈\n\n새 문단  공백")
    assert out == "한글 문서 줄바꿈\n\n새 문단 공백"


def test_tokenize_strips_particles_and_keeps_english():
    toks = tokenize_ko("서울과학기술대학교는 노원구에 있으며 AI 연구를 한다.")
    assert "서울과학기술대학교" in toks
    assert "노원구" in toks
    assert "ai" in toks
    assert "는" not in toks and "를" not in toks


def test_morph_tokens_match_where_whitespace_fails():
    doc, query = "세종대왕은 한글을 창제하였다.", "한글 창제"
    q_ws, d_ws = set(tokenize_whitespace(query)), set(tokenize_whitespace(doc))
    q_ko, d_ko = set(tokenize_ko(query)), set(tokenize_ko(doc))
    assert not (q_ws & d_ws)  # "한글을" != "한글"
    assert {"한글", "창제"} <= (q_ko & d_ko)


def test_sentence_split_offsets_are_exact():
    text = "첫 문장입니다. 두 번째 문장이에요! This is English.\n\n다음 문단."
    sents = split_sentences(text)
    assert len(sents) == 4
    for s in sents:
        assert text[s.start:s.end].strip() == s.text


def test_lang_detection():
    assert detect_lang("한국어 문장입니다") == "ko"
    assert detect_lang("This is English") == "en"
    assert detect_lang("RAG 파이프라인 hybrid search 구현") == "mixed"


def test_spacing_fix_only_when_broken():
    normal = "이 문장은 띄어쓰기가 정상적으로 되어 있는 한국어 문장입니다. " * 2
    broken = "아버지가방에들어가신다그리고오늘은날씨가매우좋아서공원에산책을하러갔습니다"
    assert not needs_spacing_fix(normal)
    assert needs_spacing_fix(broken)
    assert fix_spacing(normal) == normal
    assert fix_spacing(broken).count(" ") >= 5
