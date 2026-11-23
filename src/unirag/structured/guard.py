# * SQL guard: parse LLM SQL with sqlglot and allow only one safe SELECT on allowed tables.
# ! A first line of defense. The read-only user and row-level security are the real boundary.
import sqlglot
from sqlglot import exp

from unirag.config.settings import get_settings

PUBLIC_TABLES = {
    "courses",
    "grants",
    "grant_deadlines",
    "academic_calendar",
    "placement_drives",
    "placement_offers_by_branch",
}
STUDENT_TABLES = {"students", "enrollments", "fee_ledger", "student_branch_rank"}

# * Anything that writes, changes the schema, creates a table, or takes a lock.
FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Into,
    exp.Lock,
)
# ! sqlglot parses unknown functions as Anonymous. Block the ones that sleep, read files,
# ! reach other servers or change settings.
FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "set_config", "current_setting", "query_to")


class GuardError(ValueError):
    pass


def allowed_tables(role: str) -> set[str]:
    # ! Guests never reach student tables, not even an empty scoped result.
    return PUBLIC_TABLES if role == "guest" else PUBLIC_TABLES | STUDENT_TABLES


def guard(query: str, role: str) -> str:
    try:
        statements = [s for s in sqlglot.parse(query, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"SQL does not parse: {e}") from e
    if len(statements) != 1:
        raise GuardError(f"Expected exactly one statement, got {len(statements)}")
    tree = statements[0]

    if not isinstance(tree, exp.Query):
        raise GuardError(f"Only SELECT is allowed, got {tree.key.upper()}")
    if bad := tree.find(*FORBIDDEN_NODES):
        raise GuardError(f"Not allowed in a query: {bad.key.upper()}")
    check_functions(tree)
    check_tables(tree, role)
    return add_limit(tree, get_settings().sql_max_rows).sql(dialect="postgres")


def check_functions(tree: exp.Expression) -> None:
    for func in tree.find_all(exp.Anonymous):
        if func.name.lower().startswith(FORBIDDEN_FUNCTION_PREFIXES):
            raise GuardError(f"Function not allowed: {func.name}")


def check_tables(tree: exp.Expression, role: str) -> None:
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    # ! WITH students AS (SELECT * FROM students) would hide the real table behind a CTE name.
    if shadowing := ctes & (PUBLIC_TABLES | STUDENT_TABLES):
        raise GuardError(f"CTE name shadows a table: {', '.join(sorted(shadowing))}")
    allowed = allowed_tables(role)
    for table in tree.find_all(exp.Table):
        if table.db not in ("", "public") or table.catalog:
            raise GuardError(f"Schema not allowed: {table.sql(dialect='postgres')}")
        if table.name in ctes and not table.db:
            continue
        if table.name not in allowed:
            raise GuardError(f"Table not allowed for role {role}: {table.name}")


def tables_in(query: str) -> list[str]:
    # * Real tables a (guarded) query reads, for citations. CTE names are left out.
    tree = sqlglot.parse_one(query, read="postgres")
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    return sorted({t.name for t in tree.find_all(exp.Table)} - ctes)


def add_limit(tree: exp.Query, max_rows: int) -> exp.Query:
    # * Keep a smaller LIMIT the query already has; otherwise force max_rows.
    limit = tree.args.get("limit")
    value = limit.expression if limit else None
    if isinstance(value, exp.Literal) and value.is_int and int(value.name) <= max_rows:
        return tree
    return tree.limit(max_rows)
