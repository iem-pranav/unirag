# * Text-to-SQL run flow with the LLM mocked: one repair try, then a clean "could not answer".
import psycopg
import pytest

from unirag.db import connect
from unirag.llm.client import LLMResult
from unirag.structured import text_to_sql
from unirag.structured.text_to_sql import COULD_NOT_ANSWER, answer_sql


@pytest.fixture(scope="module")
def conn():
    with connect() as c:
        yield c


def fake_llm(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> list[list[dict]]:
    # * Returns the replies in order and records the messages each call received.
    seen: list[list[dict]] = []

    def complete(messages: list[dict]) -> LLMResult:
        seen.append(list(messages))
        return LLMResult(replies[len(seen) - 1], "fake/model", 0.0, 10, 5)

    monkeypatch.setattr(text_to_sql, "complete", complete)
    return seen


def test_bad_sql_is_repaired_once(monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection):
    seen = fake_llm(
        monkeypatch,
        [
            "```sql\nSELECT no_such_column FROM grants\n```",
            "```sql\nSELECT grant_name FROM grants\n```",
        ],
    )
    result = answer_sql(conn, "List the grants", "guest")
    assert result.ok and result.attempts == 2 and len(result.rows) == 8
    # * The repair call must see the database error.
    assert "no_such_column" in seen[1][-1]["content"]


def test_second_failure_gives_clean_could_not_answer(
    monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection
) -> None:
    seen = fake_llm(monkeypatch, ["SELECT nope FROM grants", "SELECT still_nope FROM grants"])
    result = answer_sql(conn, "List the grants", "guest")
    assert not result.ok and result.attempts == 2 and len(seen) == 2
    assert result.message == COULD_NOT_ANSWER and result.rows == []


def test_guard_block_is_repaired_and_model_can_give_up(
    monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection
) -> None:
    seen = fake_llm(monkeypatch, ["SELECT cgpa FROM students", "CANNOT_ANSWER"])
    result = answer_sql(conn, "What is the CGPA of 23CE001?", "guest")
    assert not result.ok and result.message == COULD_NOT_ANSWER
    assert "not allowed" in seen[1][-1]["content"]
