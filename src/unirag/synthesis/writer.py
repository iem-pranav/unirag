# * Synthesizer: writes the final answer from SQL rows [S1] and document chunks [D1], [D2]...
import json
import re
from dataclasses import dataclass, field
from datetime import date

import httpx

from unirag.config.settings import get_settings
from unirag.llm.client import complete
from unirag.unstructured.search import Hit

SYSTEM = """You answer questions for the help desk of a fictional university, AIT. Today is {today}. {user}

Rules:
- Use only the context below. If it does not contain the answer, set status "not_found" and say what is missing.
- Copy names, numbers and dates exactly as they appear in the rows and documents. Money is in Rs. as the data gives it, never "$".
- If a deadline in the context is before today, say applications are closed.
- List every item the data matches, even if the documents say little about it.
- For eligibility questions, check every criterion one by one. Say which are met, which fail, and which cannot be checked from the data. Then give the verdict.
- Check attendance course by course against the rule, not only the overall figure.
- Include the exceptions and conditions the sources state for the rule you apply: "unless", "except", lower limits allowed with approval, waivers, and what must be done to qualify.
- Never reveal another student's data.
- Put the source label right after each claim, like [S1] or [D2].{missing}

Reply with JSON only: {{"status": "answered" or "not_found", "answer": "...", "used_sources": ["S1", "D2"]}}"""  # noqa: E501

STUDENT_USER = "The user is student {role}. Their own records are in the SQL result."
GUEST_USER = "The user is a guest: not a student, no personal records."
MISSING = (
    "\n- Some data could not be fetched ({what}). Answer from the rest and say what is missing."
)
SERVICE_UNAVAILABLE = (
    "The answer service is unavailable right now. Please try again in a few minutes."
)
RETRY = "That was not valid JSON with status and answer. Reply with the JSON only."
MARKER = re.compile(r"\[([SD]\d+)\]")
JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Context:
    # * What the two paths fetched. sql_rows is None when the SQL path was not used or failed.
    sql_columns: list[str] = field(default_factory=list)
    sql_rows: list[tuple] | None = None
    sql_tables: list[str] = field(default_factory=list)
    # * The question the SQL answered. Its filters (year, branch) are not in the result columns.
    sql_question: str = ""
    chunks: list[Hit] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class Draft:
    status: str  # answered | not_found | error
    text: str
    citations: list[dict]
    tokens: int = 0
    latency_s: float = 0.0
    infra_error: bool = False
    error: str = ""  # provider detail for logs; never shown to the user


def cell(value: object) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def render_context(ctx: Context) -> str:
    parts = []
    if ctx.sql_rows is not None:
        cap = get_settings().synthesis_max_rows
        shown = ctx.sql_rows[:cap]
        # ! Without the question the model cannot tell "208" is for IT in 2022-23: not_found.
        head = (
            f"[S1] Database result for: {ctx.sql_question}\n"
            f"(tables: {', '.join(ctx.sql_tables)}), {len(ctx.sql_rows)} rows"
        )
        if len(ctx.sql_rows) > cap:
            head += f", first {cap} shown"
        table = [" | ".join(ctx.sql_columns)] + [" | ".join(map(cell, r)) for r in shown]
        parts.append(head + ":\n" + ("\n".join(table) if shown else "(no rows)"))
    for i, hit in enumerate(ctx.chunks, 1):
        parts.append(f"[D{i}] {hit.document} > {hit.heading}\n{hit.content}")
    return "\n\n".join(parts)


def build_messages(question: str, role: str, ctx: Context) -> list[dict]:
    user = GUEST_USER if role == "guest" else STUDENT_USER.format(role=role)
    missing = MISSING.format(what=", ".join(ctx.missing)) if ctx.missing else ""
    system = SYSTEM.format(today=get_settings().today.isoformat(), user=user, missing=missing)
    content = f"Question: {question}\n\nContext:\n{render_context(ctx)}"
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


def citations(text: str, used: list[str], ctx: Context) -> tuple[str, list[dict]]:
    # * Map [S1]/[Dn] markers to real sources. Markers that point nowhere are removed.
    valid = {"S1"} if ctx.sql_rows is not None else set()
    valid |= {f"D{i}" for i in range(1, len(ctx.chunks) + 1)}
    text = MARKER.sub(lambda m: m[0] if m[1] in valid else "", text)
    labels = list(dict.fromkeys(MARKER.findall(text) + [u for u in used if u in valid]))
    out = []
    for label in labels:
        if label == "S1":
            out.append({"label": "S1", "kind": "table", "tables": ctx.sql_tables})
        else:
            hit = ctx.chunks[int(label[1:]) - 1]
            out.append({"label": label, "kind": "document", "document": hit.document,
                        "heading": hit.heading})  # fmt: skip
    return text, out


def parse(text: str) -> dict:
    match = JSON_BLOCK.search(text)
    if not match:
        raise ValueError("no JSON object in reply")
    data = json.loads(match[0])
    if data.get("status") not in ("answered", "not_found") or not str(data.get("answer", "")):
        raise ValueError("missing status or answer")
    return data


def synthesize(question: str, role: str, ctx: Context) -> Draft:
    messages = build_messages(question, role, ctx)
    tokens, latency = 0, 0.0
    for _ in range(2):
        try:
            reply = complete(messages, json_mode=True)
        except httpx.HTTPError as e:
            return Draft("error", SERVICE_UNAVAILABLE, [],
                         tokens, latency, infra_error=True, error=str(e))  # fmt: skip
        tokens += reply.prompt_tokens + reply.completion_tokens
        latency += reply.latency_s
        try:
            data = parse(reply.text)
        except ValueError:  # json.JSONDecodeError is a ValueError too
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": RETRY},
            ]
            continue
        text, cites = citations(str(data["answer"]), list(data.get("used_sources") or []), ctx)
        return Draft(data["status"], text.strip(), cites, tokens, latency)
    return Draft("error", "Sorry, I could not write an answer.", [], tokens, latency)
