# * Smoke test: the app can reach Postgres, as the read-only user, with pgvector installed.
from unirag.db import connect


def test_app_connects_as_read_only_user() -> None:
    with connect() as conn:
        user, read_only = conn.execute(
            "SELECT current_user, current_setting('transaction_read_only')"
        ).fetchone()
        has_vector = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()

    assert user == "unirag_ro"
    # ! If this fails, the app user could write to the DB.
    assert read_only == "on"
    assert has_vector is not None
