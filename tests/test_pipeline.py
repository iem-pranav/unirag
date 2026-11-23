# * End-to-end pipeline tests with the LLM mocked: refusals, failing paths, citations, scoping.
import json

import pytest

from unirag import pipeline
from unirag.llm.client import LLMResult, LLMUnavailable
from unirag.router import llm_router
from unirag.structured import text_to_sql
from unirag.synthesis import writer
from unirag.synthesis.writer import SERVICE_UNAVAILABLE, Context, citations
from unirag.unstructured.search import Hit

A, B = "23CE001", "23CE002"


def fake_llm(monkeypatch: pytest.MonkeyPatch, replies: dict[str, list]) -> dict[str, list]:
    # * One fake for all steps; the step is known from its system prompt.
    # * replies[step] is used in order; the last reply repeats if a step is called again.
    seen: dict[str, list] = {"router": [], "sql": [], "synthesis": []}

    def complete(messages: list[dict], json_mode: bool = False) -> LLMResult:
        system = messages[0]["content"]
        step = (
            "router"
            if system.startswith("You route")
            else "sql"
            if system.startswith("You write one PostgreSQL")
            else "synthesis"
        )
        seen[step].append(messages)
        options = replies[step]
        reply = options[min(len(seen[step]), len(options)) - 1]
        if isinstance(reply, Exception):
            raise reply  # * simulates an LLM outage at this step
        return LLMResult(reply, "fake/m", 0.0, 10, 5)

    for module in (llm_router, text_to_sql, writer):
        monkeypatch.setattr(module, "complete", complete)
    return seen


def route_json(route: str, sql_q: str = "", docs_q: str = "") -> str:
    return json.dumps({"route": route, "sql_question": sql_q, "docs_question": docs_q})


ANSWER = json.dumps({"status": "answered", "answer": "Done [S1] [D1].", "used_sources": ["S1"]})


def test_citations_map_markers_and_drop_unknown_ones() -> None:
    ctx = Context(
        sql_columns=["cgpa"],
        sql_rows=[(8.5,)],
        sql_tables=["students"],
        chunks=[Hit("a.md", "A > x", "...", 1.0), Hit("b.md", "B > y", "...", 0.9)],
    )
    text, cites = citations("CGPA is 8.5 [S1]. Rule [D2]. Ghost [D7].", ["D1"], ctx)
    assert "[D7]" not in text
    assert [c["label"] for c in cites] == ["S1", "D2", "D1"]
    assert cites[0] == {"label": "S1", "kind": "table", "tables": ["students"]}
    assert cites[1]["document"] == "b.md" and cites[1]["heading"] == "B > y"


def test_none_route_refuses_without_more_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = fake_llm(monkeypatch, {"router": [route_json("none")], "sql": [], "synthesis": []})
    result = pipeline.answer("Write me a song", "guest")
    assert result.status == "refused" and result.text == pipeline.REFUSAL
    assert len(seen["router"]) == 1 and seen["sql"] == [] and seen["synthesis"] == []


def test_other_student_id_refuses_with_no_llm_call_at_all(monkeypatch: pytest.MonkeyPatch):
    seen = fake_llm(monkeypatch, {"router": [], "sql": [], "synthesis": []})
    result = pipeline.answer(f"What is {B}'s CGPA?", A)
    assert result.status == "refused" and all(v == [] for v in seen.values())


def test_failed_sql_path_still_answers_from_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = fake_llm(
        monkeypatch,
        {
            "router": [route_json("both", "my fees", "fee rules")],
            "sql": ["SELECT nope FROM fee_ledger"],
            "synthesis": [ANSWER],
        },
    )
    result = pipeline.answer("Can I pay my fees late?", A)
    assert result.status == "answered" and result.chunks
    assert "database records" in result.missing
    synth_prompt = seen["synthesis"][0][0]["content"] + seen["synthesis"][0][1]["content"]
    assert "could not be fetched (database records)" in synth_prompt
    assert "[S1]" not in seen["synthesis"][0][1]["content"]


def test_guest_never_gets_student_data(monkeypatch: pytest.MonkeyPatch) -> None:
    # ! The mocked LLM tries to read students for a guest. Guard blocks it on both tries.
    seen = fake_llm(
        monkeypatch,
        {
            "router": [route_json("both", "CGPA of all students", "CGPA rules")],
            "sql": ["SELECT student_id, full_name, cgpa FROM students"],
            "synthesis": [ANSWER],
        },
    )
    result = pipeline.answer("Who are the toppers?", "guest")
    assert result.rows == [] and result.sql is None
    context = seen["synthesis"][0][1]["content"]
    assert "[S1]" not in context and A not in context


def test_student_cannot_get_another_students_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    # ! Even a query that asks for B by id, or for everyone, returns only A's own row.
    for bad_sql in [f"SELECT student_id, cgpa FROM students WHERE student_id = '{B}'",
                    "SELECT student_id, cgpa FROM students"]:  # fmt: skip
        seen = fake_llm(
            monkeypatch,
            {
                "router": [route_json("sql", "CGPA of students")],
                "sql": [bad_sql],
                "synthesis": [ANSWER],
            },  # fmt: skip
        )
        result = pipeline.answer("Show CGPAs", A)
        assert all(row[0] == A for row in result.rows)
        assert B not in seen["synthesis"][0][1]["content"]


def test_sql_result_is_labelled_with_the_question_it_answers(monkeypatch: pytest.MonkeyPatch):
    # * The filters (year, branch) live in the WHERE clause, so the label must carry them.
    sub_q = "How many placement offers did IT students get in 2022-23?"
    seen = fake_llm(
        monkeypatch,
        {
            "router": [route_json("sql", sub_q)],
            "sql": ["SELECT SUM(offers) AS total_offers FROM placement_offers_by_branch"],
            "synthesis": [ANSWER],
        },
    )
    pipeline.answer("IT offers in 2022-23?", "guest")
    assert f"[S1] Database result for: {sub_q}" in seen["synthesis"][0][1]["content"]


OUTAGE = LLMUnavailable("groq: HTTP 429 from api.groq.com: Rate limit reached | gemini: HTTP 503")


def test_sql_path_outage_returns_service_unavailable_without_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # * Docs still work, but a half-checked answer could mislead: no synthesis at all.
    seen = fake_llm(
        monkeypatch,
        {
            "router": [route_json("both", "my fee status", "fee rules")],
            "sql": [OUTAGE],
            "synthesis": [ANSWER],
        },
    )
    result = pipeline.answer("Can I pay my fees late?", A)
    assert result.status == "error" and result.text == SERVICE_UNAVAILABLE
    assert result.infra_error and seen["synthesis"] == []
    assert any("HTTP 429" in d and "Rate limit reached" in d for d in result.infra_detail)


def test_router_outage_returns_service_unavailable_and_runs_no_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = fake_llm(monkeypatch, {"router": [OUTAGE], "sql": [], "synthesis": []})
    result = pipeline.answer("When is the hostel gate closed?", "guest")
    assert result.status == "error" and result.text == SERVICE_UNAVAILABLE
    assert seen["sql"] == [] and seen["synthesis"] == [] and result.chunks == []
