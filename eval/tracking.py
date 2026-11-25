# * Optional MLflow tracking for eval runs. Off by default; turn on with --mlflow.
import hashlib
import os

from unirag.config.settings import get_settings
from unirag.router import llm_router
from unirag.structured import text_to_sql
from unirag.synthesis import writer

FLAG = "--mlflow"


def take_flag(args: list[str]) -> tuple[bool, list[str]]:
    # * Strip the flag first, so the runners never read it as a question id.
    return FLAG in args, [a for a in args if a != FLAG]


def prompt_hash(*parts: object) -> str:
    # * Short fingerprint of a prompt and its examples: shows which runs used the same prompt.
    return hashlib.sha256(repr(parts).encode("utf-8")).hexdigest()[:12]


def run_params() -> dict[str, object]:
    s = get_settings()
    return {
        "llm_primary": s.llm_primary,
        "llm_fallback": s.llm_fallback,
        "router_type": s.router_type,
        "embedding_model": s.embedding_model,
        "chunk_size": s.chunk_size,
        "top_k": s.top_k,
        "candidate_pool": s.candidate_pool,
        "rrf_k": s.rrf_k,
        "max_context_chunks": s.max_context_chunks,
        "synthesis_max_rows": s.synthesis_max_rows,
        "llm_cache": s.llm_cache,
        "router_prompt": prompt_hash(llm_router.SYSTEM, llm_router.FEW_SHOTS),
        "sql_prompt": prompt_hash(text_to_sql.SYSTEM, text_to_sql.EXAMPLES),
        "synthesis_prompt": prompt_hash(writer.SYSTEM),
    }


def log_run(experiment: str, metrics: dict[str, float], params: dict[str, object]) -> None:
    import mlflow  # * Imported here: plain eval runs should not pay for it.

    uri = get_settings().mlflow_tracking_uri
    # ! MLflow 3 refuses a local folder store unless asked; mlflow-skinny has no SQLite store.
    # * The Compose MLflow server (full image, SQLite) is used through MLFLOW_TRACKING_URI.
    if uri.startswith("file:"):
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run() as run:
        mlflow.log_params({**run_params(), **params})
        mlflow.log_metrics(metrics)
    print(f"MLflow: logged run {run.info.run_id} to experiment {experiment!r}")
