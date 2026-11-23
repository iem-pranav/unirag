# * The whole flow: route -> SQL path and/or docs path (independent) -> synthesize one answer.
import time
from dataclasses import dataclass, field
from itertools import chain, zip_longest

import psycopg

from unirag.config.settings import get_settings
from unirag.db import connect
from unirag.router.route import route
from unirag.structured.guard import tables_in
from unirag.structured.text_to_sql import answer_sql
from unirag.synthesis.writer import SERVICE_UNAVAILABLE, Context, synthesize
from unirag.unstructured.search import Hit, search

REFUSAL = (
    "Sorry, I can't help with that. I answer questions about AIT's rules and public data, "
    "and about your own records when you are signed in as a student."
)
NOT_FOUND = "I could not find this in AIT's records or documents."


@dataclass
class Answer:
    text: str
    status: str  # answered | not_found | refused | error
    route: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    chunks: list[Hit] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    # * Per step: router, sql, docs, synthesis.
    latency_s: dict[str, float] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    infra_error: bool = False
    # * Provider errors (HTTP status + message) per failed step. For logs and evals only.
    infra_detail: list[str] = field(default_factory=list)


def answer(question: str, role: str) -> Answer:
    start = time.perf_counter()
    decision = route(question, role)
    result = Answer("", "", decision.route, infra_error=decision.infra_error)
    result.latency_s["router"] = decision.latency_s
    result.tokens["router"] = decision.tokens
    # ! LLM outage: say so plainly. A half-checked answer could look complete and mislead.
    if decision.infra_error:
        result.infra_detail.append(f"router: {decision.reason}")
        return unavailable(result)

    # ! "none" never reaches the database or another LLM call.
    if decision.route == "none":
        result.text, result.status = REFUSAL, "refused"
        return result

    ctx = Context()
    with connect() as conn:
        if decision.route in ("sql", "both"):
            run_sql_path(conn, decision.sql_question or question, role, result, ctx)
        if decision.route in ("docs", "both"):
            run_docs_path(conn, question, decision.docs_question, decision.route, result, ctx)

    result.missing = ctx.missing
    if result.infra_error:
        return unavailable(result)
    if ctx.sql_rows is None and not ctx.chunks:
        result.text, result.status = NOT_FOUND, "not_found"
        return result

    t = time.perf_counter()
    draft = synthesize(question, role, ctx)
    result.latency_s["synthesis"] = draft.latency_s or time.perf_counter() - t
    result.tokens["synthesis"] = draft.tokens
    result.text, result.status, result.citations = draft.text, draft.status, draft.citations
    result.infra_error = result.infra_error or draft.infra_error
    if draft.infra_error:
        result.infra_detail.append(f"synthesis: {draft.error}")
    result.latency_s["total"] = round(time.perf_counter() - start, 2)
    return result


def unavailable(result: Answer) -> Answer:
    # * No synthesis: some path could not reach any LLM, so the answer would be incomplete.
    result.text, result.status, result.infra_error = SERVICE_UNAVAILABLE, "error", True
    return result


def run_sql_path(
    conn: psycopg.Connection, sql_question: str, role: str, result: Answer, ctx: Context
) -> None:
    sql = answer_sql(conn, sql_question, role)
    result.latency_s["sql"] = sum(c.latency_s for c in sql.llm_calls)
    result.tokens["sql"] = sum(c.prompt_tokens + c.completion_tokens for c in sql.llm_calls)
    result.infra_error = result.infra_error or sql.infra_error
    if sql.infra_error:
        result.infra_detail.append(f"sql: {sql.error}")
    if not sql.ok:
        # * One path failing is not the end: the other path can still answer.
        ctx.missing.append("database records")
        return
    result.sql, result.columns, result.rows = sql.sql, sql.columns, sql.rows
    ctx.sql_columns, ctx.sql_rows, ctx.sql_tables = sql.columns, sql.rows, tables_in(sql.sql)
    ctx.sql_question = sql_question


def run_docs_path(
    conn: psycopg.Connection,
    question: str,
    docs_question: str,
    route_name: str,
    result: Answer,
    ctx: Context,
) -> None:
    t = time.perf_counter()
    settings = get_settings()
    try:
        hits = search(conn, docs_question or question)
        # * For joint questions also search the original wording; it keeps words like "my fees".
        if route_name == "both" and docs_question and docs_question != question:
            other = search(conn, question)
            hits = [h for h in chain(*zip_longest(hits, other)) if h is not None]
    except psycopg.Error:
        ctx.missing.append("policy documents")
        return
    finally:
        result.latency_s["docs"] = round(time.perf_counter() - t, 2)
    seen: set[tuple[str, str, str]] = set()
    for hit in hits:
        key = (hit.document, hit.heading, hit.content)
        if key not in seen and len(ctx.chunks) < settings.max_context_chunks:
            seen.add(key)
            ctx.chunks.append(hit)
    result.chunks = ctx.chunks
