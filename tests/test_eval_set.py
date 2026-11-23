# * Checks the eval set: every question is well formed, every gold_sql runs, facts match fairly.
import psycopg
import pytest
from eval_set import GOLD, QUESTIONS, fact_in_answer, load_jsonl, rows_to_facts

from unirag.db import connect
from unirag.load_data import DOCS, TABLES

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
ROUTES = {"sql", "docs", "both"}
TYPES = {"sql", "docs", "joint", "not_answerable", "guest_refusal"}
NO_ANSWER_TYPES = {"not_answerable", "guest_refusal"}
# ! Guests must never reach these, not even in gold answers.
STUDENT_TABLES = {"students", "enrollments", "fee_ledger"}

QUESTION_LIST = load_jsonl(QUESTIONS)
WITH_SQL = [q for q in QUESTION_LIST if q["gold_sql"]]


@pytest.fixture(scope="module")
def conn():
    with connect() as c:
        yield c


def test_ids_are_unique() -> None:
    ids = [q["id"] for q in QUESTION_LIST]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("q", QUESTION_LIST, ids=lambda q: q["id"])
def test_question_is_valid(q: dict, conn: psycopg.Connection) -> None:
    assert set(q) - {"retrieval_facts"} == KEYS
    assert q["question"].strip()
    if "retrieval_facts" in q:
        assert q["expected_route"] in {"docs", "both"}
        assert q["retrieval_facts"] and all(isinstance(f, str) and f for f in q["retrieval_facts"])
    assert q["expected_route"] in ROUTES
    assert q["question_type"] in TYPES
    assert all(isinstance(f, str) and f for f in q["expected_facts"])

    if q["role"] != "guest":
        found = conn.execute("SELECT 1 FROM students WHERE student_id = %s", [q["role"]]).fetchone()
        assert found, f"unknown student {q['role']}"

    needs_sql = q["expected_route"] in {"sql", "both"} and q["question_type"] not in NO_ANSWER_TYPES
    assert bool(q["gold_sql"]) == needs_sql

    if q["question_type"] not in NO_ANSWER_TYPES:
        assert q["expected_sources"]
    for source in q["expected_sources"]:
        assert source in TABLES or (DOCS / source).is_file(), f"unknown source {source}"

    if q["role"] == "guest":
        assert not STUDENT_TABLES & set(q["expected_sources"])


@pytest.mark.parametrize("q", WITH_SQL, ids=lambda q: q["id"])
def test_gold_sql_runs_and_matches_gold_file(q: dict, conn: psycopg.Connection) -> None:
    rows = conn.execute(q["gold_sql"]).fetchall()
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
