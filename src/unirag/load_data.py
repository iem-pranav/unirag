# * Loads data/seed into Postgres as admin, then checks it. Run: python -m unirag.load_data
import psycopg
from psycopg import sql

from unirag.config.settings import ROOT, get_settings
from unirag.db import connect

SEED = ROOT / "data" / "seed"
DOCS = ROOT / "data" / "documents"
EXPECTED_DOCS = 15

# ! Parents before children: COPY and the foreign keys need this order.
TABLES = [
    "students",
    "courses",
    "enrollments",
    "fee_ledger",
    "grants",
    "grant_deadlines",
    "academic_calendar",
    "placement_drives",
    "placement_offers_by_branch",
]

# * Each query counts child rows whose parent row is missing.
ORPHAN_QUERIES = {
    "enrollments.student_id": "SELECT count(*) FROM enrollments e WHERE NOT EXISTS "
    "(SELECT 1 FROM students s WHERE s.student_id = e.student_id)",
    "enrollments.course_code": "SELECT count(*) FROM enrollments e WHERE NOT EXISTS "
    "(SELECT 1 FROM courses c WHERE c.course_code = e.course_code)",
    "fee_ledger.student_id": "SELECT count(*) FROM fee_ledger f WHERE NOT EXISTS "
    "(SELECT 1 FROM students s WHERE s.student_id = f.student_id)",
    "grant_deadlines.grant_id": "SELECT count(*) FROM grant_deadlines d WHERE NOT EXISTS "
    "(SELECT 1 FROM grants g WHERE g.grant_id = d.grant_id)",
    "placement_offers_by_branch.drive_id": "SELECT count(*) FROM placement_offers_by_branch o "
    "WHERE NOT EXISTS (SELECT 1 FROM placement_drives d WHERE d.drive_id = o.drive_id)",
}

DRIVE_TOTAL_QUERY = """
SELECT d.drive_id, d.total_offers, COALESCE(SUM(o.offers), 0) AS branch_sum
FROM placement_drives d LEFT JOIN placement_offers_by_branch o USING (drive_id)
GROUP BY d.drive_id, d.total_offers
HAVING d.total_offers <> COALESCE(SUM(o.offers), 0)
"""

# * CGPA = credit-weighted grade points over finished courses. Backlogs (F = 0) count too.
# ! Compare to the unrounded value: the generator's float round() sends ties like 7.225 down,
# ! Postgres ROUND sends them up. Both are valid, so allow a difference of up to 0.005.
CGPA_QUERY = """
WITH calc AS (
    SELECT e.student_id, SUM(c.credits * e.grade_point)::numeric / SUM(c.credits) AS cgpa
    FROM enrollments e JOIN courses c USING (course_code)
    WHERE e.status <> 'ongoing'
    GROUP BY e.student_id
)
SELECT s.student_id, s.cgpa, ROUND(calc.cgpa, 4)
FROM students s JOIN calc USING (student_id)
WHERE s.cgpa IS NULL OR ABS(s.cgpa - calc.cgpa) > 0.005
"""


def load(conn: psycopg.Connection) -> None:
    # ! No CASCADE: if a view depends on a table, fail loudly instead of dropping it silently.
    for table in reversed(TABLES):
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table)))
    conn.execute((SEED / "schema.sql").read_text(encoding="utf-8"))
    for table in TABLES:
        copy_csv(conn, table)
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO unirag_ro")


def copy_csv(conn: psycopg.Connection, table: str) -> None:
    query = sql.SQL("COPY {} FROM STDIN WITH (FORMAT csv, HEADER true)").format(
        sql.Identifier(table)
    )
    with conn.cursor().copy(query) as copy:
        copy.write((SEED / f"{table}.csv").read_bytes())


def row_counts(conn: psycopg.Connection) -> dict[str, int]:
    counts = {}
    for table in TABLES:
        query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
        counts[table] = conn.execute(query).fetchone()[0]
    return counts


def orphan_counts(conn: psycopg.Connection) -> dict[str, int]:
    return {name: conn.execute(q).fetchone()[0] for name, q in ORPHAN_QUERIES.items()}


def drive_total_mismatches(conn: psycopg.Connection) -> list[tuple]:
    return conn.execute(DRIVE_TOTAL_QUERY).fetchall()


def cgpa_mismatches(conn: psycopg.Connection) -> list[tuple]:
    return conn.execute(CGPA_QUERY).fetchall()


def document_problems() -> list[str]:
    files = sorted(DOCS.glob("*.md"))
    problems = [f"{f.name} is empty" for f in files if not f.read_text(encoding="utf-8").strip()]
    if len(files) != EXPECTED_DOCS:
        problems.append(f"expected {EXPECTED_DOCS} documents, found {len(files)}")
    return problems


def report(conn: psycopg.Connection) -> bool:
    print("Row counts:")
    for table, n in row_counts(conn).items():
        print(f"  {table:<28} {n:>6}")

    orphans = {k: v for k, v in orphan_counts(conn).items() if v}
    drives = drive_total_mismatches(conn)
    cgpas = cgpa_mismatches(conn)
    docs = document_problems()

    print(f"Orphan rows: {orphans or 'none'}")
    print(f"Drive total_offers != sum of branch offers: {drives or 'none'}")
    print(f"students.cgpa != enrollments CGPA: {cgpas or 'none'}")
    print(f"Documents ({DOCS.name}/): {docs or f'{EXPECTED_DOCS} files, none empty'}")
    return not (orphans or drives or cgpas or docs)


def main() -> None:
    with psycopg.connect(get_settings().admin_database_url) as conn:
        load(conn)
    print(f"Loaded {len(TABLES)} tables from {SEED.relative_to(ROOT)}")

    # * Checks run as the read-only app user, which also proves it can SELECT every table.
    with connect() as conn:
        ok = report(conn)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
