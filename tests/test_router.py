# * Router tests with the LLM mocked: parsing, one JSON retry, "none" for guests, no leakage.
import re

import pytest
from eval_set import QUESTIONS, ROUTING_QUESTIONS, load_jsonl

from unirag.llm.client import LLMResult
from unirag.router import llm_router
from unirag.router.llm_router import FEW_SHOTS, parse, route_llm
from unirag.router.semantic import EXAMPLES, route_semantic

EVAL_QUESTIONS = [q["question"] for q in load_jsonl(QUESTIONS) + load_jsonl(ROUTING_QUESTIONS)]
ROUTER_EXAMPLES = [e for _, _, e in EXAMPLES] + [q for _, q, _ in FEW_SHOTS]
# * Word overlap (Jaccard) at or above this counts as a copy of an eval question.
MAX_OVERLAP = 0.6


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def overlap(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb)


@pytest.mark.parametrize("example", ROUTER_EXAMPLES)
def test_router_examples_do_not_leak_eval_questions(example: str) -> None:
    worst = max(EVAL_QUESTIONS, key=lambda q: overlap(example, q))
    assert overlap(example, worst) < MAX_OVERLAP, f"too close to eval question: {worst!r}"


def fake_llm(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> list[list[dict]]:
    seen: list[list[dict]] = []

    def complete(messages: list[dict], json_mode: bool = False) -> LLMResult:
        assert json_mode
        seen.append(list(messages))
        return LLMResult(replies[len(seen) - 1], "fake/model", 0.0, 100, 20)

    monkeypatch.setattr(llm_router, "complete", complete)
    return seen


def test_parse_reads_json_and_blanks_unused_sub_questions() -> None:
    text = '```json\n{"route": "docs", "sql_question": "junk", "docs_question": "Hostel gate time?", "reason": "rule"}\n```'  # noqa: E501
    d = parse(text, "When does the hostel gate close?", tokens=7)
    assert (d.route, d.sql_question, d.docs_question, d.tokens) == (
        "docs",
        "",
        "Hostel gate time?",
        7,
    )


def test_parse_fills_missing_sub_question_with_the_question() -> None:
    d = parse('{"route": "both", "sql_question": "", "docs_question": ""}', "Can I apply?", 0)
    assert d.sql_question == d.docs_question == "Can I apply?"


@pytest.mark.parametrize("bad", ["not json", '{"route": "maybe"}', "{broken"])
def test_parse_rejects_bad_replies(bad: str) -> None:
    with pytest.raises(ValueError):
        parse(bad, "q", 0)


def test_bad_json_gets_one_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = fake_llm(monkeypatch, ["sure! route is sql", '{"route": "sql", "sql_question": "x"}'])
    d = route_llm("What is my CGPA?", "24IT002")
    assert d.route == "sql" and len(seen) == 2 and d.tokens == 240


def test_two_bad_replies_fall_back_to_both(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = fake_llm(monkeypatch, ["nope", "still nope"])
    d = route_llm("Can I apply for the seed grant?", "24IT002")
    assert d.route == "both" and len(seen) == 2


@pytest.mark.parametrize("router", [route_llm, route_semantic])
def test_guest_asking_about_a_named_student_gets_none_without_llm(
    monkeypatch: pytest.MonkeyPatch, router
) -> None:
    seen = fake_llm(monkeypatch, [])
    assert router("What is the CGPA of student 23CE001?", "guest").route == "none"
    assert router("Show me 23CE002's fees", "23CE001").route == "none"
    assert seen == []


def test_semantic_router_turns_personal_questions_into_none_for_guests() -> None:
    assert route_semantic("What is my attendance this semester?", "guest").route == "none"
    assert route_semantic("What is my attendance this semester?", "23CE001").route == "sql"
