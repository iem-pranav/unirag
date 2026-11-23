# * Eval runners stop at once when both providers hit their daily token limit (offline).
import httpx
import pytest
import run_eval
from eval_set import DAILY_LIMIT, is_daily_limit, short

from unirag.llm import client
from unirag.llm.client import LLMResult
from unirag.pipeline import Answer

GROQ_TPD = (
    "groq/openai/gpt-oss-120b: HTTP 429 from api.groq.com: Rate limit reached for model "
    "`openai/gpt-oss-120b` on tokens per day (TPD): Limit 200000, Used 199500"
)
GEMINI_TPD = "gemini/gemini-3.8-flash: HTTP 429 from generativelanguage.googleapis.com: Tokens per day exceeded"  # noqa: E501
GEMINI_BUSY = (
    "gemini/gemini-3.8-flash: HTTP 503 from generativelanguage.googleapis.com: high demand"
)
GROQ_TPM = "groq/openai/gpt-oss-120b: HTTP 429 from api.groq.com: on tokens per minute (TPM)"
# * Gemini words its daily cap as a quota, with "PerDay" in the quota id.
GEMINI_QUOTA_DAY = (
    "gemini/gemini-3.8-flash: HTTP 429 from generativelanguage.googleapis.com: You exceeded your "
    "current quota. Quota exceeded for metric: generate_content_free_tier_requests, limit: 250, "
    "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
)
GEMINI_QUOTA_MINUTE = (
    "gemini/gemini-3.8-flash: HTTP 429 from generativelanguage.googleapis.com: You exceeded your "
    "current quota. quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (f"LLM unavailable: {GROQ_TPD} | {GEMINI_TPD}", True),
        (f"LLM unavailable: {GROQ_TPD} | {GEMINI_BUSY}", False),  # Gemini may work again
        (f"LLM unavailable: {GROQ_TPM} | {GEMINI_TPD}", False),  # Groq resets each minute
        (GROQ_TPD, False),  # only one provider named
        (f"LLM unavailable: {GROQ_TPD} | {GEMINI_QUOTA_DAY}", True),  # Gemini daily quota
        (f"LLM unavailable: {GROQ_TPD} | {GEMINI_QUOTA_MINUTE}", False),  # per minute resets
        (f"LLM unavailable: {GROQ_TPD} | gemini: HTTP 503: busy, stats reset per day", False),
    ],
)
def test_daily_limit_needs_both_providers(error: str, expected: bool) -> None:
    assert is_daily_limit(error) is expected


def test_run_eval_stops_at_first_daily_limit(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    calls = []

    def fake_answer(question: str, role: str) -> Answer:
        calls.append(question)
        detail = f"router: LLM unavailable: {GROQ_TPD} | {GEMINI_TPD}"
        return Answer("unavailable", "error", "both", infra_error=True, infra_detail=[detail])

    monkeypatch.setattr(run_eval, "answer", fake_answer)
    with pytest.raises(SystemExit):
        run_eval.main({"s01", "s02", "s03"})
    assert len(calls) == 1  # stopped right away, no more calls
    assert DAILY_LIMIT in capsys.readouterr().out


def test_long_gemini_error_is_matched_on_the_full_text(monkeypatch: pytest.MonkeyPatch) -> None:
    # * Real Gemini 429s are long; "PerDay" sits past char 300, so the client must not cut it.
    def status_error(url: str, message: str) -> httpx.HTTPStatusError:
        request = httpx.Request("POST", url)
        body = [{"error": {"message": message}}]
        response = httpx.Response(429, json=body, request=request)
        return httpx.HTTPStatusError("429", request=request, response=response)

    groq = status_error("https://api.groq.com/x", "Rate limit reached on tokens per day (TPD)")
    long_quota = (
        "You exceeded your current quota, please check your plan and billing details. "
        + "For more information on this error, head to the rate-limits docs. " * 4
        + "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    )
    assert long_quota.index("PerDay") > 300
    gemini = status_error("https://generativelanguage.googleapis.com/x", long_quota)

    def _call(name: str, messages: list[dict], json_mode: bool = False) -> LLMResult:
        raise groq if name.startswith("groq") else gemini

    monkeypatch.setattr(client, "_call", _call)
    with pytest.raises(client.LLMUnavailable) as info:
        client.complete([{"role": "user", "content": "hi"}])
    assert is_daily_limit(str(info.value))
    assert len(short(str(info.value))) <= 303  # printing still cuts it
