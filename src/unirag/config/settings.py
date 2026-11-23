# * One place to read settings: config/settings.yaml for tuning, .env for secrets.
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    llm_primary: str
    llm_fallback: str
    embedding_model: str
    top_k: int
    chunk_size: int
    database_url: str
    # ! Admin URL is only for the data loader. The app itself must never use it.
    admin_database_url: str | None


@lru_cache
def get_settings() -> Settings:
    # * Real env vars win over .env, so CI can set them directly.
    load_dotenv(ROOT / ".env")
    raw = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    return Settings(
        llm_primary=raw["llm"]["primary"],
        llm_fallback=raw["llm"]["fallback"],
        embedding_model=raw["embedding"]["model"],
        top_k=raw["retrieval"]["top_k"],
        chunk_size=raw["chunking"]["chunk_size"],
        database_url=os.environ["DATABASE_URL"],
        admin_database_url=os.environ.get("ADMIN_DATABASE_URL"),
    )
