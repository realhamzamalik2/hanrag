import json
from pathlib import Path

from app.config import ROOT_DIR
from app.evaluation import (
    answer_matches,
    first_relevant_rank,
    is_relevant,
    latency_stats,
    load_questions,
    retrieval_metrics,
    threshold_sweep,
)


def test_relevance_ignores_whitespace():
    assert is_relevant("훈민정음 해례본은 1962년에 국보 70호로\n지정되었다", ["국보 70호로 지정"])
    assert not is_relevant("국보 제71호", ["국보 70호"])


def test_first_relevant_rank_and_metrics():
    texts = ["김치", "경복궁", "1446년 음력 9월에 훈민정음을 반포하였다"]
    assert first_relevant_rank(texts, ["1446년 음력 9월에 훈민정음을 반포"]) == 3
    assert first_relevant_rank(texts, ["없는 문장"]) is None
    m = retrieval_metrics([1, 3, None, 12])
    assert m["recall@1"] == 0.25 and m["recall@3"] == 0.5 and m["recall@10"] == 0.5
    assert abs(m["mrr@10"] - (1 + 1 / 3) / 4) < 1e-9


def test_answer_matching_groups():
    must = [["세종"], ["1443"]]
    assert answer_matches("한글은 세종대왕이 1443년에 창제했습니다 [1].", must)
    assert not answer_matches("한글은 세종대왕이 만들었습니다.", must)
    assert answer_matches("It was named by Jeong Do-jeon.", [["Jeong", "정도전"]])


def test_latency_and_sweep():
    s = latency_stats([100, 200, 300, 400])
    assert s["p50"] == 250 and s["mean"] == 250
    rows = threshold_sweep([0.9, 0.5, 0.03], [0.001, 0.2], [0.05])
    assert rows[0]["unanswerable_refused"] == 0.5
    assert abs(rows[0]["answerable_refused"] - 1 / 3) < 1e-9


def test_dataset_is_valid():
    qs = load_questions(ROOT_DIR / "eval" / "dataset" / "qa.jsonl")
    assert len(qs) == 50 and len({q.id for q in qs}) == 50
    for q in qs:
        if q.answerable:
            assert q.evidence and q.must and q.docs, q.id
        else:
            assert not q.evidence and not q.must, q.id
    assert sum(not q.answerable for q in qs) == 10


def test_dataset_json_lines(tmp_path: Path):
    p = tmp_path / "q.jsonl"
    p.write_text(json.dumps({"id": "a", "question": "q", "lang": "ko", "type": "unanswerable",
                             "answer": ""}) + "\n", encoding="utf-8")
    assert load_questions(p)[0].answerable is False


def test_cited_numbers_keep_answer_numbering():
    from scripts.run_eval import cited_numbers

    assert cited_numbers("A [1][3]. B [3][5].", 3) == [1, 3, 5]
    assert cited_numbers("no citations", 0) == []
