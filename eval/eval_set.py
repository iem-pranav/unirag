# * Shared eval helpers: load the question files, turn gold SQL rows into facts, match facts.
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg

from unirag.config.settings import get_settings
from unirag.db import run_query
from unirag.llm.client import EvalOptions, configure_eval
from unirag.structured.guard import guard

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS = EVAL_DIR / "questions.jsonl"
GOLD = EVAL_DIR / "gold.jsonl"
# * Routing-only questions: id, question, role, expected_route.
ROUTING_QUESTIONS = EVAL_DIR / "routing_questions.jsonl"

NUMBER = re.compile(r"\d+(?:\.\d+)?")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# * Drop thousands separators, so Indian style 1,02,000 and 102,000 both read as 102000.
DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d)")


def load_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


DAILY_LIMIT = (
    "Daily limit reached. Run the same command again later; the cache keeps finished answers."
)


def is_daily_limit(error: str) -> bool:
    # * The client joins the two providers' errors with " | ". Stop only when BOTH hit their
    # * daily cap; if one still works, the run can go on.
    parts = error.split(" | ")
    return len(parts) >= 2 and all(says_daily_cap(part) for part in parts)


def says_daily_cap(text: str) -> bool:
    # * Groq: "tokens per day (TPD)". Gemini: "exceeded your current quota ... PerDay...".
    text = text.casefold()
    per_day = "per day" in text or "perday" in text
    return "tokens per day" in text or ("quota" in text and per_day)


def short(text: str, limit: int = 300) -> str:
    # * Errors stay whole for matching; cut them only when printing.
    return text if len(text) <= limit else text[:limit] + "..."


def stop_on_daily_limit(errors: list[str]) -> None:
    # ! More calls today would only fail. Stop now; a record-mode re-run resumes from the cache.
    if any(is_daily_limit(e) for e in errors):
        print(DAILY_LIMIT)
        raise SystemExit(1)


def setup_llm(args: list[str]) -> list[str]:
    # * Eval-only LLM options: cache mode (config, or --cache MODE), call spacing, network retry.
    # * Returns the remaining command-line arguments.
    settings = get_settings()
    mode = settings.llm_cache
    if "--cache" in args:
        i = args.index("--cache")
        mode, args = args[i + 1], args[:i] + args[i + 2 :]
    configure_eval(
        EvalOptions(
            cache=mode,
            cache_dir=settings.llm_cache_dir,
            min_interval_s=settings.eval_pause_s,
            retry_wait_s=settings.eval_network_retry_s,
        )
    )
    print(f"LLM cache: {mode}")
    return args


def run_gold(conn: psycopg.Connection, q: dict) -> list[tuple]:
    # * Gold SQL goes through the same guard and row scoping as the app, as the asking role.
    _, rows = run_query(conn, guard(q["gold_sql"], q["role"]), q["role"])
    return rows


def cell_to_text(value: object) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def rows_to_facts(rows: list[tuple]) -> list[str]:
    # ! Every non-null cell becomes a fact, so gold_sql must SELECT only what the answer needs.
    return [cell_to_text(v) for row in rows for v in row if v is not None]


def normalize(text: str) -> str:
    return DIGIT_COMMA.sub("", text).replace("_", " ").casefold()


def date_forms(d: date) -> list[str]:
    month = d.strftime("%B").casefold()
    return [d.isoformat(), f"{d.day} {month} {d.year}", f"{month} {d.day}, {d.year}"]


def fact_in_answer(fact: str, answer: str) -> bool:
    text = normalize(answer)
    if ISO_DATE.fullmatch(fact):
        return any(form in text for form in date_forms(date.fromisoformat(fact)))
    fact = normalize(fact)
    if NUMBER.fullmatch(fact):
        # * Compare as numbers: 8.8 matches 8.80, but 15 does not match 150.
        return any(Decimal(n) == Decimal(fact) for n in NUMBER.findall(text))
    return fact in text


def cells_equal(gold: str, got: str, tolerance: float) -> bool:
    try:
        return abs(Decimal(gold) - Decimal(got)) <= Decimal(str(tolerance))
    except InvalidOperation:
        # * Text: gold inside the cell is enough, e.g. "Guru Nanak Jayanti (holiday)".
        return gold.strip().casefold() in got.strip().casefold()


def take_match(items: list, predicate) -> bool:
    # * Remove the first item that matches, so each item is used at most once.
    for i, item in enumerate(items):
        if predicate(item):
            items.pop(i)
            return True
    return False


def row_covers(got_row: list[str], gold_row: list[str], tolerance: float) -> bool:
    # * Every gold cell must appear in the row. Extra columns (an id, a label) are allowed.
    cells = list(got_row)
    return all(take_match(cells, lambda c, g=g: cells_equal(g, c, tolerance)) for g in gold_row)


def rows_match(gold_rows: list[list[str]], got_rows: list[list[str]], tolerance: float) -> bool:
    # * Same number of rows, any order, each gold row covered by a different result row.
    if len(gold_rows) != len(got_rows):
        return False
    rows = list(got_rows)
    return all(take_match(rows, lambda r, g=g: row_covers(r, g, tolerance)) for g in gold_rows)


def data_covered(gold_rows: list[list[str]], got_rows: list[list[str]], tolerance: float) -> bool:
    # * Joint questions: every gold value was fetched somewhere. Shape, extra rows and extra
    # * columns do not matter; the synthesizer reasons over whatever was fetched.
    # * Each distinct value once: a cross join repeats profile values on every row. NULLs skipped.
    pool = [cell for row in got_rows for cell in row]
    gold_cells = {cell for row in gold_rows for cell in row if cell != "None"}
    return all(any(cells_equal(g, c, tolerance) for c in pool) for g in gold_cells)


def sql_part_ok(q: dict, gold_rows: list[list[str]], got_rows: list[list[str]]) -> bool:
    tolerance = get_settings().number_tolerance
    if q["question_type"] == "joint":
        return data_covered(gold_rows, got_rows, tolerance)
    return rows_match(gold_rows, got_rows, tolerance)
