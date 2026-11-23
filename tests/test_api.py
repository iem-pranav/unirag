# * API tests with a fake pipeline.answer: no LLM calls. The role check uses the real DB.
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from unirag import pipeline
from unirag.api.app import app, role_exists
from unirag.config.settings import get_settings
from unirag.pipeline import Answer

client = TestClient(app)


@pytest.fixture
def fake_answer(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def answer(question: str, role: str) -> Answer:
        calls.append((question, role))
        if "poem" in question:
            return Answer(pipeline.REFUSAL, "refused", "none")
        return Answer(
            "Your CGPA is 8.65 [S1].",
            "answered",
            "sql",
            sql="SELECT cgpa, updated FROM students LIMIT 100",
            columns=["cgpa", "updated"],
            rows=[(Decimal("8.65"), date(2026, 11, 23))],
            citations=[{"label": "S1", "kind": "table", "tables": ["students"]}],
            latency_s={"router": 0.5},
            tokens={"router": 700},
        )

    monkeypatch.setattr(pipeline, "answer", answer)
    return calls


def test_chat_returns_the_answer_with_sources_and_details(fake_answer) -> None:
    r = client.post("/chat", json={"question": "What is my CGPA?", "role": "23ENTC008"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "answered" and body["route"] == "sql"
    assert body["citations"][0]["tables"] == ["students"]
    # * Decimals come out as exact strings (no float rounding), dates as ISO text.
    assert body["rows"] == [["8.65", "2026-11-23"]]
    assert fake_answer == [("What is my CGPA?", "23ENTC008")]


def test_refusal_is_a_normal_reply(fake_answer) -> None:
    r = client.post("/chat", json={"question": "write a poem", "role": "guest"})
    assert r.status_code == 200 and r.json()["status"] == "refused"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "What is my CGPA?", "role": "99XX999"},  # no such student
        {"question": "", "role": "guest"},  # empty question
    ],
)
def test_bad_requests_are_rejected_before_the_pipeline(fake_answer, payload: dict) -> None:
    r = client.post("/chat", json=payload)
    assert r.status_code == 422
    assert fake_answer == []


def test_any_real_student_is_accepted_not_only_demo_ones(fake_answer) -> None:
    assert client.post("/chat", json={"question": "hi", "role": "23CE010"}).status_code == 200


def test_roles_list_guest_first_and_every_demo_student_exists() -> None:
    roles = client.get("/roles").json()
    assert roles[0]["id"] == "guest"
    assert [r["id"] for r in roles[1:]] == [d["id"] for d in get_settings().demo_students]
    assert all(role_exists(r["id"]) for r in roles)


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}
