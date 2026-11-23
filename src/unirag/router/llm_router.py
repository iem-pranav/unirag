# * Main router: one small LLM call with JSON output. Returns the route and the sub-questions.
import json
import re

import httpx

from unirag.config.settings import get_settings
from unirag.llm.client import complete
from unirag.router.base import ROUTES, RouteDecision, other_student_check

# ! Runs on every question, so keep this prompt small (under ~800 tokens).
SYSTEM = """You route questions for the help desk of a fictional university, AIT. Today is {today}. {user}

Sources:
- sql: database tables. Personal records of the asking student only (CGPA, backlogs, marks, attendance, fees). Public: course catalogue, grants with amounts and deadlines, academic calendar dates, placement numbers by year, branch and company.
- docs: policy documents. Rules, eligibility criteria and procedures for academics, exams, admissions, fees and refunds, hostel, library, activities, research grants, scholarships, placements, campus IT.

Routes:
- sql: needs only table data.
- docs: needs only a rule or procedure.
- both: needs table data and a rule, e.g. eligibility ("can I", "am I eligible") or a record or date checked against a rule.
- none: off-topic, or asks for records the user may not see: a guest asking for any student's records, or anyone asking about other students.

Reply with JSON only: {{"route": "...", "sql_question": "...", "docs_question": "...", "reason": "..."}}
sql_question and docs_question are short standalone questions for each source, "" when not used. Put the student id in a personal sql_question. reason: a few words.

Examples:
{examples}"""  # noqa: E501

STUDENT_USER = "The user is student {role}."
GUEST_USER = "The user is a guest: not a student, no personal records."

# * (role, question, answer). ! Must not repeat any eval question (tests/test_router.py).
FEW_SHOTS: list[tuple[str, str, dict]] = [
    (
        "24CE010",
        "Can I get the Conference Travel Grant for my paper?",
        {
            "route": "both",
            "sql_question": "What are the year of study and CGPA of student 24CE010, "
            "and when does the Conference Travel Grant close?",
            "docs_question": "Who is eligible for the Conference Travel Grant?",
            "reason": "eligibility: record + rule",
        },
    ),
    (
        "guest",
        "What is the late fine for library books?",
        {
            "route": "docs",
            "sql_question": "",
            "docs_question": "What is the late fine for library books?",
            "reason": "library rule",
        },
    ),
    (
        "guest",
        "Show me the grades of the IT toppers.",
        {"route": "none", "sql_question": "", "docs_question": "", "reason": "other students"},
    ),
    (
        "23IT010",
        "Which drives in 2021-22 paid over 10 LPA?",
        {
            "route": "sql",
            "sql_question": "Which placement drives in 2021-22 had a package over 10 LPA?",
            "docs_question": "",
            "reason": "placement table",
        },
    ),
]

RETRY = "That was not valid JSON with a route of sql, docs, both or none. Reply with the JSON only."
JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def build_messages(question: str, role: str) -> list[dict]:
    examples = "\n".join(
        f"[{'guest' if r == 'guest' else 'student ' + r}] {q} -> {json.dumps(a)}"
        for r, q, a in FEW_SHOTS
    )
    user = GUEST_USER if role == "guest" else STUDENT_USER.format(role=role)
    system = SYSTEM.format(today=get_settings().today.isoformat(), user=user, examples=examples)
    return [{"role": "system", "content": system}, {"role": "user", "content": question}]


def parse(text: str, question: str, tokens: int) -> RouteDecision:
    # * Raises ValueError on anything that is not a usable decision.
    match = JSON_BLOCK.search(text)
    if not match:
        raise ValueError("no JSON object in reply")
    data = json.loads(match[0])
    route = data.get("route")
    if route not in ROUTES:
        raise ValueError(f"bad route: {route!r}")
    uses_sql, uses_docs = route in ("sql", "both"), route in ("docs", "both")
    # * Blank unused sub-questions; fill a missing one with the original question.
    return RouteDecision(
        route=route,
        sql_question=(str(data.get("sql_question") or "") or question) if uses_sql else "",
        docs_question=(str(data.get("docs_question") or "") or question) if uses_docs else "",
        reason=str(data.get("reason") or ""),
        tokens=tokens,
    )


def route_llm(question: str, role: str) -> RouteDecision:
    if blocked := other_student_check(question, role):
        return blocked
    messages = build_messages(question, role)
    tokens = 0
    for _ in range(2):
        try:
            reply = complete(messages, json_mode=True)
        except httpx.HTTPError as e:
            reason = f"LLM unavailable: {type(e).__name__}"
            break
        tokens += reply.prompt_tokens + reply.completion_tokens
        try:
            return parse(reply.text, question, tokens)
        except ValueError as e:  # json.JSONDecodeError is a ValueError too
            reason = f"bad router reply twice: {e}"
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": RETRY},
            ]
    # ? Fallback: try both sources with the original question. Guard and RLS still apply.
    return RouteDecision("both", question, question, reason=reason, tokens=tokens)
