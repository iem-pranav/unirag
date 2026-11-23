# * Text-to-SQL: question -> SQL (LLM) -> guard -> run as the read-only user, with one repair try.
import re
from dataclasses import dataclass, field

import httpx
import psycopg

from unirag.config.settings import ROOT, get_settings
from unirag.db import run_query
from unirag.llm.client import LLMResult, complete
from unirag.structured.guard import GuardError, allowed_tables, guard

SCHEMA_SQL = ROOT / "data" / "seed" / "schema.sql"
CREATE_TABLE = re.compile(r"CREATE TABLE (\w+)")
SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
CANNOT_ANSWER = "CANNOT_ANSWER"
COULD_NOT_ANSWER = "I could not answer this from the database."
# * One first try plus one repair try.
MAX_ATTEMPTS = 2

# * The view lives in security.sql, not schema.sql, so describe it here for students.
VIEW_SCHEMA = """CREATE VIEW student_branch_rank (student_id TEXT, branch TEXT, cgpa NUMERIC, branch_rank BIGINT);
COMMENT ON VIEW student_branch_rank IS 'The current student''s CGPA rank within their branch, among students in years 2-4 with a CGPA. Rank 1 = highest CGPA. Only the asking student''s own row is visible.';"""  # noqa: E501

SYSTEM = """You write one PostgreSQL SELECT query that answers the user's question.

Rules:
- Use only the tables below. Only SELECT. No INSERT, UPDATE, DELETE or DDL.
- Today is {today}. For "today", "now", "next" or "upcoming" use DATE '{today}', never CURRENT_DATE.
- {role_rule}
- Year groups: FE = first year, SE = second, TE = third, BE = final year.
- Select only the columns needed for the answer. Prefer names and titles over internal IDs.
- If the tables cannot answer the question, reply with exactly {cannot}.
- Reply with only the SQL inside a ```sql block.

Tables:
{schema}

Examples:
{examples}"""

STUDENT_RULE = (
    "The user is student {student_id}. 'I', 'my' and 'me' mean this student, "
    "so filter student tables with student_id = '{student_id}'."
)
GUEST_RULE = "The user is a guest, not a student. Guests have no personal records."

# * (students_only, question, sql). These are not eval questions, to keep the eval honest.
EXAMPLES = [
    (
        False,
        "Which grants open for applications after today?",
        "SELECT g.grant_name, d.opens_on, d.closes_on FROM grants g JOIN grant_deadlines d "
        "USING (grant_id) WHERE d.opens_on > DATE '{today}' ORDER BY d.opens_on",
    ),
    (
        False,
        "What was the average package in 2021-22?",
        "SELECT ROUND(AVG(package_lpa), 2) AS average_package_lpa FROM placement_drives "
        "WHERE academic_year = '2021-22'",
    ),
    (
        False,
        "What events are there for final-year students in December 2026?",
        "SELECT event, start_date, end_date FROM academic_calendar "
        "WHERE 'BE' = ANY(string_to_array(applies_to, ',')) "
        "AND start_date BETWEEN DATE '2026-12-01' AND DATE '2026-12-31' ORDER BY start_date",
    ),
    (
        True,
        "What is my attendance in each course this semester?",
        "SELECT c.title, e.attendance_pct FROM enrollments e JOIN courses c USING (course_code) "
        "WHERE e.student_id = '{student_id}' AND e.status = 'ongoing' ORDER BY c.title",
    ),
    (
        True,
        "Which of my fee items are overdue?",
        "SELECT fee_type, amount_due - amount_paid AS amount_unpaid, due_date FROM fee_ledger "
        "WHERE student_id = '{student_id}' AND status = 'overdue'",
    ),
    (
        True,
        "Where do I rank in my branch by CGPA?",
        "SELECT cgpa, branch_rank FROM student_branch_rank WHERE student_id = '{student_id}'",
    ),
]

REPAIR = (
    "That SQL failed with this error:\n{error}\nFix it. Reply with only the SQL in a ```sql block."
)


@dataclass
class SqlResult:
    ok: bool
    sql: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    # * message is safe to show the user. error is the internal reason, for logs and eval.
    message: str = ""
    error: str | None = None
    attempts: int = 0
    llm_calls: list[LLMResult] = field(default_factory=list)


def schema_for(role: str) -> str:
    allowed = allowed_tables(role)
    blocks = SCHEMA_SQL.read_text(encoding="utf-8").split("\n\n")
    keep = [b for b in blocks if (m := CREATE_TABLE.search(b)) and m[1] in allowed]
    if "student_branch_rank" in allowed:
        keep.append(VIEW_SCHEMA)
    return "\n\n".join(keep)


def build_messages(question: str, role: str) -> list[dict]:
    today = get_settings().today.isoformat()
    is_student = role != "guest"
    examples = "\n\n".join(
        f"Q: {q}\n```sql\n{sql.format(today=today, student_id=role)}\n```"
        for students_only, q, sql in EXAMPLES
        if is_student or not students_only
    )
    role_rule = STUDENT_RULE.format(student_id=role) if is_student else GUEST_RULE
    system = SYSTEM.format(
        today=today,
        role_rule=role_rule,
        cannot=CANNOT_ANSWER,
        schema=schema_for(role),
        examples=examples,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]


def extract_sql(text: str) -> str | None:
    # * None means the model said the tables cannot answer.
    match = SQL_BLOCK.search(text)
    sql = (match[1] if match else text).strip().rstrip(";").strip()
    return None if not sql or sql == CANNOT_ANSWER else sql


def answer_sql(conn: psycopg.Connection, question: str, role: str) -> SqlResult:
    messages = build_messages(question, role)
    result = SqlResult(ok=False, sql=None, message=COULD_NOT_ANSWER)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result.attempts = attempt
        try:
            reply = complete(messages)
        except httpx.HTTPError as e:
            result.error = f"LLM unavailable: {e}"
            return result
        result.llm_calls.append(reply)

        result.sql = extract_sql(reply.text)
        if result.sql is None:
            result.error = "model said the tables cannot answer"
            return result
        try:
            safe_sql = guard(result.sql, role)
            result.columns, result.rows = run_query(conn, safe_sql, role)
        except (GuardError, psycopg.Error) as e:
            result.error = f"{type(e).__name__}: {e}".strip()
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": REPAIR.format(error=result.error)},
            ]
            continue
        result.ok, result.sql, result.message, result.error = True, safe_sql, "", None
        return result
    return result
