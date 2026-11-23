# * Checks the loaded data. Needs `python -m unirag.load_data` to have run first.
import psycopg
import pytest

from unirag.db import connect, connect_admin
from unirag.load_data import drive_total_mismatches, orphan_counts, row_counts

# * Row counts from data/README.md.
EXPECTED_ROWS = {
    "students": 240,
    "courses": 120,
    "enrollments": 5760,
    "fee_ledger": 1650,
    "grants": 8,
    "grant_deadlines": 8,
    "academic_calendar": 41,
    "placement_drives": 526,
    "placement_offers_by_branch": 955,
}


# * Data checks run as admin: row-level security hides student rows from the app user.
@pytest.fixture
def admin():
    with connect_admin() as c:
        yield c


@pytest.fixture
def conn():
    with connect() as c:
        yield c


def test_row_counts(admin: psycopg.Connection) -> None:
    assert row_counts(admin) == EXPECTED_ROWS


def test_no_orphan_rows(admin: psycopg.Connection) -> None:
    assert not any(orphan_counts(admin).values())


def test_drive_totals_match_branch_offers(admin: psycopg.Connection) -> None:
    assert drive_total_mismatches(admin) == []


# ! The transaction is switched to READ WRITE on purpose, so only missing privileges can stop it.
@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO grants VALUES (99, 'x', 'x', 1, 'x')",
        "UPDATE students SET cgpa = 10",
        "DELETE FROM fee_ledger",
        "DROP TABLE grants",
        "CREATE TABLE hack (id int)",
    ],
)
def test_read_only_user_cannot_write(conn: psycopg.Connection, statement: str) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("SET TRANSACTION READ WRITE")
        conn.execute(statement)
