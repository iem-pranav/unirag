# * One small LLM client: Groq first, Gemini on any error. Both speak the OpenAI chat API.
import os
import time
from dataclasses import dataclass, replace

import httpx

from unirag.config.settings import get_settings

# * provider -> (chat completions URL, env var holding the API key)
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "GEMINI_API_KEY",
    ),
}


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    latency_s: float
    prompt_tokens: int
    completion_tokens: int
    # * Why the primary failed, when the fallback answered. Kept for logs and eval reports.
    fallback_reason: str | None = None


def complete(messages: list[dict]) -> LLMResult:
    settings = get_settings()
    try:
        return _call(settings.llm_primary, messages)
    # * Errors, timeouts and rate limits (429) all fall back. A bad reply shape too.
    except (httpx.HTTPError, KeyError, IndexError) as e:
        reason = f"{type(e).__name__}: {e}".splitlines()[0][:200]
        return replace(_call(settings.llm_fallback, messages), fallback_reason=reason)


def _call(name: str, messages: list[dict]) -> LLMResult:
    # * name is provider/model, e.g. groq/openai/gpt-oss-120b
    provider, model = name.split("/", 1)
    url, key_env = PROVIDERS[provider]
    start = time.perf_counter()
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {os.environ[key_env]}"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=get_settings().llm_timeout_s,
    )
    response.raise_for_status()
    body = response.json()
    usage = body.get("usage") or {}
    return LLMResult(
        text=body["choices"][0]["message"]["content"] or "",
        model=name,
        latency_s=round(time.perf_counter() - start, 2),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )
