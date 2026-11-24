# * Checks the eval set: every question is well formed, every gold_sql runs, facts match fairly.
import psycopg
import pytest
from eval_set import (
    GOLD,
    QUESTIONS,
    ROUTING_QUESTIONS,
    fact_in_answer,
    load_jsonl,
    rows_match,
    rows_to_facts,
    run_gold,
)

from unirag.db import connect, run_query
from unirag.load_data import DOCS
from unirag.structured.guard import PUBLIC_TABLES
from unirag.structured.guard import STUDENT_TABLES as ALL_STUDENT_TABLES

KEYS = {
    "id",
    "question",
    "role",
    "expected_route",
    "question_type",
    "gold_sql",
    "expected_facts",
    "expected_sources",
}
ROUTES = {"sql", "docs", "both", "none"}
TYPES = {"sql", "docs", "joint", "not_answerable", "guest_refusal"}
NO_ANSWER_TYPES = {"not_answerable", "guest_refusal"}
# ! Guests must never reach these, not even in gold answers.
STUDENT_TABLES = ALL_STUDENT_TABLES

QUESTION_LIST = load_jsonl(QUESTIONS)
ROUTING_LIST = load_jsonl(ROUTING_QUESTIONS)
WITH_SQL = [q for q in QUESTION_LIST if q["gold_sql"]]


@pytest.fixture(scope="module")
def conn():
    with connect() as c:
        yield c


def test_ids_are_unique() -> None:
    ids = [q["id"] for q in QUESTION_LIST + ROUTING_LIST]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("q", QUESTION_LIST, ids=lambda q: q["id"])
def test_question_is_valid(q: dict, conn: psycopg.Connection) -> None:
    assert set(q) - {"retrieval_facts", "expected_status", "note"} == KEYS
    assert q.get("expected_status", "answered") in {"answered", "not_found", "refused"}
    assert q["question"].strip()
    if "retrieval_facts" in q:
        assert q["expected_route"] in {"docs", "both"}
        assert q["retrieval_facts"] and all(isinstance(f, str) and f for f in q["retrieval_facts"])
    assert q["expected_route"] in ROUTES
    assert q["question_type"] in TYPES
    assert all(isinstance(f, str) and f for f in q["expected_facts"])

    if q["role"] != "guest":
        # * Row-level security returns the row only if this student exists.
        _, found = run_query(conn, "SELECT 1 FROM students", q["role"])
        assert found, f"unknown student {q['role']}"

    # * Guests asking for personal data must be routed to "none".
    if q["question_type"] == "guest_refusal":
        assert q["expected_route"] == "none"
    needs_sql = q["expected_route"] in {"sql", "both"} and q["question_type"] not in NO_ANSWER_TYPES
    assert bool(q["gold_sql"]) == needs_sql

    if q["question_type"] not in NO_ANSWER_TYPES:
        assert q["expected_sources"]
    for source in q["expected_sources"]:
        known = PUBLIC_TABLES | STUDENT_TABLES
        assert source in known or (DOCS / source).is_file(), f"unknown source {source}"

    if q["role"] == "guest":
        assert not STUDENT_TABLES & set(q["expected_sources"])


@pytest.mark.parametrize("q", ROUTING_LIST, ids=lambda q: q["id"])
def test_routing_question_is_valid(q: dict, conn: psycopg.Connection) -> None:
    assert set(q) == {"id", "question", "role", "expected_route"}
    assert q["question"].strip() and q["expected_route"] in ROUTES
    if q["role"] != "guest":
        _, found = run_query(conn, "SELECT 1 FROM students", q["role"])
        assert found, f"unknown student {q['role']}"


@pytest.mark.parametrize("q", WITH_SQL, ids=lambda q: q["id"])
def test_gold_sql_runs_and_matches_gold_file(q: dict, conn: psycopg.Connection) -> None:
    rows = run_gold(conn, q)
    assert rows, "gold_sql returned no rows"
    gold = {g["id"]: g for g in load_jsonl(GOLD)}
    assert gold[q["id"]]["facts"] == rows_to_facts(rows), "gold.jsonl is stale, run build_gold.py"


@pytest.mark.parametrize(
    ("fact", "answer", "expected"),
    [
        ("102000", "You owe Rs. 1,02,000 in tuition.", True),
        ("102000", "You owe Rs. 102,000.", True),
        ("8.80", "Your CGPA is 8.8.", True),
        ("15", "The fee is Rs. 150.", False),
        ("12", "Your ISE score is 12/15.", True),
        ("2026-11-20", "Applications closed on 20 November 2026.", True),
        ("2026-11-20", "It closed on November 20, 2026.", True),
        ("2026-11-20", "It closes on 2026-12-20.", False),
        ("tuition_fee", "Your tuition fee is overdue.", True),
        ("B+", "You got a b+ in Machine Learning.", True),
        ("Group II", "You can only sit for Group I drives.", False),
    ],
)
def test_fact_in_answer(fact: str, answer: str, expected: bool) -> None:
    assert fact_in_answer(fact, answer) is expected


TOL = 0.01


@pytest.mark.parametrize(
    ("gold", "got", "expected"),
    [
        ([["Adobe", "61.10"]], [["Adobe", "61.1"]], True),
        ([["Adobe", "61.10"]], [["61.1", "Adobe", "drive 12"]], True),
        ([["a", "1"], ["b", "2"]], [["b", "2"], ["a", "1"]], True),
        ([["208"]], [["208.004"]], True),
        ([["208"]], [["209"]], False),
        (
            [["Guru Nanak Jayanti", "2026-11-24"]],
            [["Guru Nanak Jayanti (holiday)", "2026-11-24"]],
            True,
        ),
        ([["a", "1"]], [["a", "1"], ["b", "2"]], False),
        ([["x", "1"], ["x", "1"]], [["x", "1"], ["y", "1"]], False),
    ],
)
def test_rows_match(gold: list, got: list, expected: bool) -> None:
    assert rows_match(gold, got, TOL) is expected
