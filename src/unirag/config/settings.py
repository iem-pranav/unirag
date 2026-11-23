# * One place to read settings: config/settings.yaml for tuning, .env for secrets.
import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    today: date
    llm_primary: str
    llm_fallback: str
    llm_timeout_s: float
    sql_max_rows: int
    sql_timeout_ms: int
    embedding_model: str
    top_k: int
    candidate_pool: int
    rrf_k: int
    chunk_size: int
    number_tolerance: float
    eval_pause_s: float
    database_url: str
    # ! Admin URL is only for the data loader. The app itself must never use it.
    admin_database_url: str | None


@lru_cache
def get_settings() -> Settings:
    # * Real env vars win over .env, so CI can set them directly.
    load_dotenv(ROOT / ".env")
    raw = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    return Settings(
        today=raw["today"],
        llm_primary=raw["llm"]["primary"],
        llm_fallback=raw["llm"]["fallback"],
        llm_timeout_s=raw["llm"]["timeout_s"],
        sql_max_rows=raw["sql"]["max_rows"],
        sql_timeout_ms=raw["sql"]["timeout_ms"],
        embedding_model=raw["embedding"]["model"],
        top_k=raw["retrieval"]["top_k"],
        candidate_pool=raw["retrieval"]["candidate_pool"],
        rrf_k=raw["retrieval"]["rrf_k"],
        chunk_size=raw["chunking"]["chunk_size"],
        number_tolerance=raw["eval"]["number_tolerance"],
        eval_pause_s=raw["eval"]["pause_s"],
        database_url=os.environ["DATABASE_URL"],
        admin_database_url=os.environ.get("ADMIN_DATABASE_URL"),
    )
