# * LLM record/replay cache and the eval-only network retry (offline).
import httpx
import pytest

from unirag.llm import client
from unirag.llm.cache import CacheMiss
from unirag.llm.client import EvalOptions, LLMResult, complete

MESSAGES = [{"role": "user", "content": "hi"}]


def use(monkeypatch: pytest.MonkeyPatch, tmp_path, **options) -> list[str]:
    calls: list[str] = []

    def _call(name: str, messages: list[dict], json_mode: bool = False) -> LLMResult:
        calls.append(name)
        return LLMResult(f"reply from {name}", name, 0.5, 10, 2)

    monkeypatch.setattr(client, "_call", _call)
    monkeypatch.setattr(client, "EVAL", EvalOptions(cache_dir=tmp_path, **options))
    return calls


def test_record_then_replay_gives_same_reply_without_calling(monkeypatch, tmp_path) -> None:
    calls = use(monkeypatch, tmp_path, cache="record")
    recorded = complete(MESSAGES)
    assert len(calls) == 1 and len(list(tmp_path.glob("*.json"))) == 1

    calls = use(monkeypatch, tmp_path, cache="replay")
    assert complete(MESSAGES) == recorded and calls == []


def test_record_reuses_hits_and_only_calls_on_a_miss(monkeypatch, tmp_path) -> None:
    # * Like a restarted run: the first question is cached, the second is new.
    calls = use(monkeypatch, tmp_path, cache="record")
    first = complete(MESSAGES)
    calls.clear()

    again = complete(MESSAGES)
    new = complete([{"role": "user", "content": "a new question"}])
    assert again == first and new.text.startswith("reply from")
    assert len(calls) == 1  # only the miss went live
    assert len(list(tmp_path.glob("*.json"))) == 2  # and its reply was stored


def test_replay_miss_fails_loudly(monkeypatch, tmp_path) -> None:
    use(monkeypatch, tmp_path, cache="replay")
    with pytest.raises(CacheMiss):
        complete([{"role": "user", "content": "never recorded"}])


def test_key_depends_on_messages(monkeypatch, tmp_path) -> None:
    use(monkeypatch, tmp_path, cache="record")
    complete(MESSAGES)
    complete([{"role": "user", "content": "something else"}])
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_off_mode_writes_nothing(monkeypatch, tmp_path) -> None:
    use(monkeypatch, tmp_path)
    complete(MESSAGES)
    assert list(tmp_path.glob("*.json")) == []


def test_eval_retry_after_network_error(monkeypatch, tmp_path) -> None:
    failures = iter([True, True, False])  # groq fails, gemini fails, then groq works

    def _call(name: str, messages: list[dict], json_mode: bool = False) -> LLMResult:
        if next(failures):
            raise httpx.ConnectError("down")
        return LLMResult("ok", name, 0.1, 1, 1)

    monkeypatch.setattr(client, "_call", _call)
    monkeypatch.setattr(client, "EVAL", EvalOptions(cache_dir=tmp_path, retry_wait_s=0.01))
    assert complete(MESSAGES).text == "ok"


def test_no_retry_in_app_mode(monkeypatch, tmp_path) -> None:
    def _call(name: str, messages: list[dict], json_mode: bool = False) -> LLMResult:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(client, "_call", _call)
    monkeypatch.setattr(client, "EVAL", EvalOptions(cache_dir=tmp_path))
    # * Both providers down, no retry: one LLMUnavailable naming both failures.
    with pytest.raises(client.LLMUnavailable, match="ConnectError: down"):
        complete(MESSAGES)
