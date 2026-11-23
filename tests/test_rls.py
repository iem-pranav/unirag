# * Database boundary tests (row-level security, timeout): run without the guard on purpose.
import psycopg
import pytest

from unirag.db import connect, run_query

A, B = "23CE001", "23CE002"


@pytest.fixture(scope="module")
def conn():
    with connect() as c:
        yield c


@pytest.mark.parametrize("table", ["students", "enrollments", "fee_ledger"])
def test_student_sees_only_own_rows(conn: psycopg.Connection, table: str) -> None:
    _, rows = run_query(conn, f"SELECT DISTINCT student_id FROM {table}", A)
    assert rows == [(A,)]


@pytest.mark.parametrize("table", ["students", "enrollments", "fee_ledger"])
def test_student_cannot_read_other_student_even_when_asked(
    conn: psycopg.Connection, table: str
) -> None:
    _, rows = run_query(conn, f"SELECT * FROM {table} WHERE student_id = '{B}'", A)
    assert rows == []


def test_guest_sees_no_student_rows(conn: psycopg.Connection) -> None:
    _, rows = run_query(conn, "SELECT count(*) FROM students", "guest")
    assert rows == [(0,)]


def test_rank_view_shows_only_own_row(conn: psycopg.Connection) -> None:
    _, own = run_query(conn, "SELECT student_id, cgpa FROM students", A)
    columns, rows = run_query(conn, "SELECT * FROM student_branch_rank", A)
    assert columns == ["student_id", "branch", "cgpa", "branch_rank"]
    assert len(rows) == 1
    assert rows[0][0] == A and rows[0][2] == own[0][1]


@pytest.mark.parametrize(
    "query",
    [
        f"SELECT * FROM student_branch_rank WHERE student_id = '{B}'",
        f"SELECT * FROM student_branch_rank WHERE student_id <> '{A}'",
        "SELECT * FROM student_branch_rank WHERE branch_rank = 1 AND student_id <> '23CE001'",
    ],
)
def test_rank_view_never_shows_another_student(conn: psycopg.Connection, query: str) -> None:
    _, rows = run_query(conn, query, A)
    assert rows == []


def test_app_user_cannot_switch_student_with_set_config(conn: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_query(conn, f"SELECT set_config('app.student_id', '{B}', true)", A)


def test_statement_timeout_stops_slow_queries(conn: psycopg.Connection) -> None:
    # * Bypasses the guard on purpose: the database itself must stop runaway queries (5 s).
    with pytest.raises(psycopg.errors.QueryCanceled):
        run_query(conn, "SELECT pg_sleep(30)", A)
