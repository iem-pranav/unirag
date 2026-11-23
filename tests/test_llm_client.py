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


def status_error(code: int, url: str, body: object) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", url)
    response = httpx.Response(code, json=body, request=request)
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


def test_both_down_reports_each_status_code_and_provider_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # * Groq wraps the error in an object, Gemini in a list. Both texts must come through.
    groq = status_error(429, "https://api.groq.com/x", {"error": {"message": "Rate limit reached"}})
    gemini = status_error(
        503, "https://generativelanguage.googleapis.com/x", [{"error": {"message": "high demand"}}]
    )

    def _call(name: str, messages: list[dict], json_mode: bool = False) -> LLMResult:
        raise groq if name.startswith("groq") else gemini

    monkeypatch.setattr(client, "_call", _call)
    with pytest.raises(client.LLMUnavailable) as info:
        complete([{"role": "user", "content": "hi"}])
    text = str(info.value)
    assert "HTTP 429 from api.groq.com: Rate limit reached" in text
    assert "HTTP 503 from generativelanguage.googleapis.com: high demand" in text


def test_network_error_without_response_names_the_error_type() -> None:
    assert client.describe_error(httpx.ConnectError("refused")) == "ConnectError: refused"
