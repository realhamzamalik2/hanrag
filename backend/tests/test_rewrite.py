from app.generation import llm, rewrite


def test_rewrite_retries_once_when_busy(monkeypatch):
    calls = []

    def fake(system, prompt):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("503 UNAVAILABLE high demand")
        return '{"standalone": "Who named it?", "translation": "누가 지었나요?"}', llm.Usage()

    monkeypatch.setattr(rewrite.llm, "generate_json", fake)
    monkeypatch.setattr(rewrite, "RETRY_WAIT_S", 0)
    rw = rewrite.rewrite_query("Who named it?", None)
    assert len(calls) == 2 and rw.translation == "누가 지었나요?"


def test_rewrite_gives_up_on_other_errors(monkeypatch):
    def fake(system, prompt):
        raise ValueError("bad json")

    monkeypatch.setattr(rewrite.llm, "generate_json", fake)
    rw = rewrite.rewrite_query("Who named it?", None)
    assert rw.translation is None and rw.standalone == "Who named it?"
