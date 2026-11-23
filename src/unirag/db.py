# * Database access: the read-only app connection, the admin connection, and scoped queries.
import psycopg
from psycopg import sql

from unirag.config.settings import get_settings


def connect() -> psycopg.Connection:
    # * Autocommit, so each run_query() is its own real transaction and SET LOCAL ends with it.
    return psycopg.connect(get_settings().database_url, autocommit=True)


def connect_admin() -> psycopg.Connection:
    # ! Admin bypasses row-level security. Only for loading data and data checks, never the app.
    return psycopg.connect(get_settings().admin_database_url)


def run_query(conn: psycopg.Connection, query: str, role: str) -> tuple[list[str], list[tuple]]:
    # * role is a student_id or "guest". Row-level security reads app.student_id from here.
    # ! Needs autocommit: inside an outer transaction, SET LOCAL would outlive this query.
    if not conn.autocommit:
        raise ValueError("run_query needs an autocommit connection")
    settings = get_settings()
    student_id = "" if role == "guest" else role
    with conn.transaction():
        conn.execute(
            sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(settings.sql_timeout_ms))
        )
        conn.execute(sql.SQL("SET LOCAL app.student_id = {}").format(sql.Literal(student_id)))
        cur = conn.execute(query)
        return [col.name for col in cur.description], cur.fetchall()
