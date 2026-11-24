"""API tests with FastAPI's TestClient, real PostgreSQL, fake models and a fake LLM."""

from __future__ import annotations

import json
import time

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def client(clean_db, fake_models, monkeypatch):
    from fastapi.testclient import TestClient

    from app.generation import llm
    from app.generation.llm import Usage

    monkeypatch.setattr("app.main._warm_models", lambda: None)
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "generate", lambda s, p: ("세종이 창제했다 [1].", Usage(5, 3)))

    def fake_stream(system, prompt, result):
        for part in ["세종이 ", "창제했다 ", "[1]."]:
            result.text_parts.append(part)
            yield part

    monkeypatch.setattr(llm, "generate_stream", fake_stream)
    from app.main import app

    with TestClient(app) as c:
        yield c


def _upload(client, name: str, content: str) -> dict:
    r = client.post("/api/documents", files={"file": (name, content.encode("utf-8"))})
    assert r.status_code == 202, r.text
    job = r.json()
    for _ in range(100):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    return job


def test_full_api_flow(client):
    assert client.get("/api/health").json()["database"] is True
    assert client.get("/api/config").json()["retrieval_mode"] == "hybrid_rerank"

    job = _upload(client, "hangul.md", "# 한글\n\n한글은 세종이 1443년에 창제한 문자이다.\n\n"
                                         "## 김치\n\n김치는 발효 음식이다.\n")
    doc_id = job["document_id"]
    assert client.post("/api/documents", files={"file": ("x.exe", b"MZ")}).status_code == 415

    docs = client.get("/api/documents").json()
    assert [d["id"] for d in docs] == [doc_id] and docs[0]["status"] == "ready"
    assert client.get(f"/api/documents/{doc_id}/chunks").json()
    f = client.get(f"/api/documents/{doc_id}/file")
    assert f.status_code == 200 and "한글" in f.content.decode("utf-8")

    s = client.post("/api/search", json={"query": "한글 창제", "mode": "hybrid_rerank"}).json()
    assert set(s["lists"]) == {"bm25", "vector"} and s["reranked"] and s["final"]

    c = client.post("/api/chat", json={"question": "한글은 누가 창제했나요?"}).json()
    assert c["answer"] == "세종이 창제했다 [1]." and c["citations"][0]["number"] == 1
    assert c["trace_id"]

    with client.stream("POST", "/api/chat/stream",
                       json={"question": "한글은 누가 창제했나요?"}) as r:
        body = "".join(r.iter_text())
    events = [line[7:] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "rewrite" and events[1] == "retrieval" and events[-1] == "done"
    assert events.count("token") == 3
    done = json.loads([ln for ln in body.splitlines() if ln.startswith("data: ")][-1][6:])
    assert done["citations"][0]["number"] == 1 and not done["refused"]

    traces = client.get("/api/traces").json()
    assert len(traces) >= 2
    t = client.get(f"/api/traces/{traces[0]['id']}").json()
    assert t["retrieval"]["lists"]

    st = client.get("/api/stats").json()
    assert st["documents"] == 1 and st["questions"] >= 2

    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get("/api/documents").json() == []
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_validation_errors(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "q", "mode": "nope"}).status_code == 422
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.get("/api/traces/not-a-uuid").status_code == 404
