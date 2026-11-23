# * HTTP API: POST /chat runs one question through the pipeline. Run: uvicorn unirag.api.app:app
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from unirag import pipeline
from unirag.config.settings import get_settings
from unirag.db import connect, run_query

app = FastAPI(
    title="UniRAG", description="Ask about AIT: tables and policy documents in one answer."
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # * "guest" or a student_id. No login: the role only scopes data (row-level security).
    role: str = "guest"


class ChatResponse(BaseModel):
    text: str
    status: str  # answered | not_found | refused | error
    route: str
    citations: list[dict[str, Any]]
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    missing: list[str]
    latency_s: dict[str, float]
    tokens: dict[str, int]


def role_exists(role: str) -> bool:
    if role == "guest":
        return True
    # * Row-level security returns the row only for the student itself, so this checks existence.
    with connect() as conn:
        _, rows = run_query(conn, "SELECT 1 FROM students", role)
    return bool(rows)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/roles")
def roles() -> list[dict[str, str]]:
    return [{"id": "guest", "label": "Guest / Applicant"}, *get_settings().demo_students]


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    # * A plain def: FastAPI runs it in a thread, since the pipeline blocks on DB and LLM calls.
    if not role_exists(request.role):
        raise HTTPException(status_code=422, detail=f"Unknown role: {request.role}")
    # * Called through the module, so tests can swap in a fake pipeline.answer.
    a = pipeline.answer(request.question, request.role)
    return ChatResponse(
        text=a.text,
        status=a.status,
        route=a.route,
        citations=a.citations,
        sql=a.sql,
        columns=a.columns,
        rows=[list(row) for row in a.rows],
        missing=a.missing,
        latency_s=a.latency_s,
        tokens=a.tokens,
    )
