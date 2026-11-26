from app.retrieval.bm25 import BM25Index, Row
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.types import RetrievedChunk

DOCS = [
    "세종대왕은 1443년에 훈민정음을 창제하였다.",
    "김치는 배추와 고춧가루로 만든 발효 음식이다.",
    "경복궁은 조선의 법궁으로 1395년에 지어졌다.",
    "Hangul was created by King Sejong in 1443.",
]


def _index(tokenizer: str) -> BM25Index:
    rows = [Row(str(i), "d", "doc", "doc.pdf", 1, "", t, 0, len(t), "ko", True)
            for i, t in enumerate(DOCS)]
    idx = BM25Index(tokenizer)  # type: ignore[arg-type]
    idx.build_from_rows(rows, (len(rows), "x"))
    return idx


def _rc(cid: str, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(cid, "d", "t", "f", 1, "", cid, 0, 1, "ko", True, score)


def test_kiwi_bm25_matches_inflected_korean():
    hits = _index("kiwi").search("훈민정음은 누가 창제했나요", k=3)
    assert hits and hits[0].chunk_id == "0"


def test_whitespace_bm25_misses_inflected_korean():
    # "훈민정음은" / "창제했나요" never equal the whitespace tokens "훈민정음을" / "창제하였다."
    hits = _index("whitespace").search("훈민정음은 누가 창제했나요", k=3)
    assert not hits or hits[0].chunk_id != "0"


def test_bm25_english_and_unknown_terms():
    idx = _index("kiwi")
    assert idx.search("King Sejong", k=2)[0].chunk_id == "3"
    assert idx.search("양자역학", k=2) == []


def test_rrf_rewards_agreement_and_records_ranks():
    a = [_rc("x"), _rc("y"), _rc("z")]
    b = [_rc("y"), _rc("w")]
    fused = reciprocal_rank_fusion({"bm25": a, "vector": b}, k=60)
    assert fused[0].chunk_id == "y"  # ranked by both lists
    assert fused[0].scores["bm25_rank"] == 2 and fused[0].scores["vector_rank"] == 1
    assert abs(fused[0].score - (1 / 62 + 1 / 61)) < 1e-12
    assert [c.rank for c in fused] == [1, 2, 3, 4]
    assert a[1].scores == {}  # inputs are not mutated


def test_rrf_limit():
    fused = reciprocal_rank_fusion({"a": [_rc(str(i)) for i in range(10)]}, limit=3)
    assert len(fused) == 3


def _chunk(cid: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(cid, "d", "t", "f", 1, "", text, 0, 1, "ko", True, 0.0)


def test_rerank_query_matches_passage_language():
    from app.retrieval.hybrid import match_query_language

    chunks = [_chunk("a", "경복궁은 1395년에 창건되었다."), _chunk("b", "RAG was proposed in 2020.")]
    q, tr = "When was Gyeongbokgung built?", "경복궁은 언제 지어졌나요?"
    assert match_query_language(q, [tr], chunks) == [tr, q]
    # No translation in the other language: keep the plain single-query path.
    assert match_query_language(q, [], chunks) is None
    assert match_query_language(q, ["When was it built?"], chunks) is None
