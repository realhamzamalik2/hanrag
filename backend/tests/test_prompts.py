from app.generation.prompts import answer_language, build_user_prompt


def test_answer_language_is_stated_in_the_prompt():
    assert answer_language("Who named Gyeongbokgung Palace?") == "en"
    assert answer_language("경복궁의 이름은 누가 지었나요?") == "ko"
    en = build_user_prompt("Who named Gyeongbokgung Palace?", [])
    ko = build_user_prompt("경복궁의 이름은 누가 지었나요?", [])
    assert "Write the answer in English" in en
    assert "한국어로" in ko and "Write the answer in English" not in ko


def test_mixed_question_gets_no_language_line():
    p = build_user_prompt("RAG 기법이란 retrieval-augmented generation?", [])
    assert "Write the answer in English" not in p and "한국어로 작성" not in p
