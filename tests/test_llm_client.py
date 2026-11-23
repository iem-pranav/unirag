# * LLM client tests (offline): Groq first, Gemini when Groq fails.
import httpx
import pytest

from unirag.llm import client
from unirag.llm.client import LLMResult, complete

RATE_LIMITED = httpx.HTTPStatusError(
    "429 Too Many Requests",
    request=httpx.Request("POST", "https://api.groq.com"),
    response=httpx.Response(429),
)


def fake_call(fail_primary: Exception | None):
    def _call(name: str, messages: list[dict], json_mode: bool = False) -> LLMResult:
        if name.startswith("groq") and fail_primary:
            raise fail_primary
        return LLMResult("SELECT 1", name, 0.1, 10, 2)

    return _call


@pytest.mark.parametrize("error", [RATE_LIMITED, httpx.ConnectTimeout("timed out")])
def test_falls_back_to_gemini_on_error(monkeypatch: pytest.MonkeyPatch, error: Exception):
    monkeypatch.setattr(client, "_call", fake_call(error))
    result = complete([{"role": "user", "content": "hi"}])
    assert result.model.startswith("gemini/")
    assert result.fallback_reason


def test_uses_groq_when_it_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "_call", fake_call(None))
    result = complete([{"role": "user", "content": "hi"}])
    assert result.model.startswith("groq/") and result.fallback_reason is None
