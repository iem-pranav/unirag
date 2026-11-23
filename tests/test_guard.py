# * SQL guard tests (offline): unsafe SQL is blocked, safe SQL passes with a forced LIMIT.
import pytest

from unirag.structured.guard import GuardError, guard

BLOCKED = [
    ("guest", "DROP TABLE grants"),
    ("guest", "UPDATE grants SET max_amount_inr = 0"),
    ("guest", "SELECT 1; DROP TABLE grants"),
    ("guest", "SELECT * FROM grants; SELECT * FROM courses"),
    ("23CE001", "SELECT pg_sleep(10)"),
    ("23CE001", "SELECT * FROM grants WHERE pg_sleep(10) IS NOT NULL"),
    ("guest", "SELECT * FROM students"),
    ("guest", "SELECT f.* FROM grants g JOIN fee_ledger f ON true"),
    ("guest", "SELECT * FROM student_branch_rank"),
    ("23CE001", "SELECT set_config('app.student_id', '23CE002', true)"),
    ("guest", "SELECT * INTO copy_of_grants FROM grants"),
    ("guest", "WITH d AS (DELETE FROM grants RETURNING *) SELECT * FROM d"),
    ("guest", "WITH students AS (SELECT * FROM students) SELECT * FROM students"),
    ("guest", "SELECT * FROM pg_catalog.pg_user"),
    ("guest", "SELECT * FROM information_schema.tables"),
    ("guest", "SELECT * FROM grants FOR UPDATE"),
    ("guest", "SELECT * FROM doc_chunks"),
    ("guest", "not sql at all ((("),
]


@pytest.mark.parametrize(("role", "query"), BLOCKED)
def test_guard_blocks(role: str, query: str) -> None:
    with pytest.raises(GuardError):
        guard(query, role)


def test_guard_forces_limit() -> None:
    assert guard("SELECT * FROM grants", "guest").endswith("LIMIT 100")
    assert guard("SELECT * FROM grants LIMIT 5000", "guest").endswith("LIMIT 100")
    assert guard("SELECT * FROM grants LIMIT 3", "guest").endswith("LIMIT 3")


def test_guard_allows_student_tables_for_students_and_ctes() -> None:
    sql = "WITH me AS (SELECT cgpa FROM students WHERE student_id = '23CE001') SELECT * FROM me"
    assert guard(sql, "23CE001").startswith("WITH me AS")
