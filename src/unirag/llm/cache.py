# * Record/replay cache for LLM calls: one JSON file per call, keyed by model + messages.
# * Only eval commands turn it on (see client.configure_eval). The app never uses it.
import hashlib
import json
from pathlib import Path


class CacheMiss(Exception):
    pass


def cache_key(model: str, messages: list[dict], json_mode: bool) -> str:
    raw = json.dumps([model, messages, json_mode], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load(cache_dir: Path, key: str) -> dict:
    path = cache_dir / f"{key}.json"
    if not path.is_file():
        raise CacheMiss(f"no cached LLM reply {key[:12]}. Run once with cache=record first.")
    return json.loads(path.read_text(encoding="utf-8"))


def save(cache_dir: Path, key: str, record: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
