# * One small LLM client: Groq first, Gemini on any error. Both speak the OpenAI chat API.
import os
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import httpx

from unirag.config.settings import get_settings
from unirag.llm import cache
from unirag.llm.cache import CacheMiss

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


class LLMUnavailable(httpx.HTTPError):
    # * Both providers failed. The message names each one's HTTP status and error text.
    # * A subclass of httpx.HTTPError, so existing "except httpx.HTTPError" still catches it.
    pass


def describe_error(e: Exception) -> str:
    # ! Full text, no cut: the eval's daily-limit check needs words that can come late.
    # * "HTTP 429 from api.groq.com: Rate limit reached ..." or "ConnectError: ..." (no response).
    if isinstance(e, httpx.HTTPStatusError):
        return (
            f"HTTP {e.response.status_code} from {e.request.url.host}: {provider_text(e.response)}"
        )
    return f"{type(e).__name__}: {e}".splitlines()[0]


def provider_text(response: httpx.Response) -> str:
    # * Groq sends {"error": {"message": ...}}; Gemini sends the same inside a list.
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, list) and body:
        body = body[0]
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    return str(message or response.text)


@dataclass
class EvalOptions:
    # * Defaults = app behaviour: no cache, no spacing, no extra retry.
    cache: str = "off"  # off | record | replay
    cache_dir: Path = Path(".cache/llm")
    min_interval_s: float = 0.0  # space live calls out (Groq free-tier tokens per minute)
    retry_wait_s: float = 0.0  # wait, then try once more when both providers fail


EVAL = EvalOptions()
_last_live_call = 0.0


def configure_eval(options: EvalOptions) -> None:
    # ! Only eval commands call this.
    global EVAL
    EVAL = options


def complete(messages: list[dict], json_mode: bool = False) -> LLMResult:
    # * json_mode asks the provider for a JSON object reply (both support it).
    try:
        return _with_fallback(messages, json_mode)
    except httpx.HTTPError:
        if not EVAL.retry_wait_s:
            raise
        # * Eval only: a network blip gets one more try after a pause.
        time.sleep(EVAL.retry_wait_s)
        return _with_fallback(messages, json_mode)


def _with_fallback(messages: list[dict], json_mode: bool) -> LLMResult:
    settings = get_settings()
    try:
        return _cached_call(settings.llm_primary, messages, json_mode)
    # * Errors, timeouts, rate limits (429), a bad reply shape or a replay miss: all fall back.
    except (httpx.HTTPError, KeyError, IndexError, CacheMiss) as e:
        reason = f"{settings.llm_primary}: {describe_error(e)}"
    try:
        result = _cached_call(settings.llm_fallback, messages, json_mode)
    except httpx.HTTPError as e:
        raise LLMUnavailable(f"{reason} | {settings.llm_fallback}: {describe_error(e)}") from e
    return replace(result, fallback_reason=reason)


def _cached_call(name: str, messages: list[dict], json_mode: bool) -> LLMResult:
    global _last_live_call
    key = cache.cache_key(name, messages, json_mode)
    # ! replay: a miss raises CacheMiss. record: a hit is reused, so an interrupted run resumes.
    if EVAL.cache in ("replay", "record"):
        try:
            return LLMResult(**cache.load(EVAL.cache_dir, key))
        except CacheMiss:
            if EVAL.cache == "replay":
                raise
    wait = EVAL.min_interval_s - (time.monotonic() - _last_live_call)
    if wait > 0:
        time.sleep(wait)
    try:
        result = _call(name, messages, json_mode)
    finally:
        _last_live_call = time.monotonic()
    if EVAL.cache == "record":
        cache.save(EVAL.cache_dir, key, asdict(result))
    return result


def _call(name: str, messages: list[dict], json_mode: bool = False) -> LLMResult:
    # * name is provider/model, e.g. groq/openai/gpt-oss-120b
    provider, model = name.split("/", 1)
    url, key_env = PROVIDERS[provider]
    payload: dict = {"model": model, "messages": messages, "temperature": 0}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    start = time.perf_counter()
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {os.environ[key_env]}"},
        json=payload,
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
