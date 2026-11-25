# * Phase 8 plumbing, offline: CI gate, latency percentile, MLflow logging to a temp folder.
import pytest
import routing_eval
import tracking
from run_eval import percentile

from unirag.config import settings as settings_module


def test_gate_fails_below_the_floor_and_passes_at_it(capsys) -> None:
    with pytest.raises(SystemExit):
        routing_eval.gate(0.54, 0.55)
    assert "GATE FAILED" in capsys.readouterr().out
    routing_eval.gate(0.55, 0.55)  # equal is enough
    assert "GATE OK" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("values", "p", "expected"),
    [([], 95, 0.0), ([3.0], 95, 3.0), ([1.0, 2.0, 3.0, 4.0], 50, 2.0), ([*range(1, 21)], 95, 19)],
)
def test_percentile_is_nearest_rank(values: list[float], p: int, expected: float) -> None:
    assert percentile(values, p) == expected


def test_take_flag_strips_it_so_it_is_not_read_as_an_id() -> None:
    assert tracking.take_flag(["s01", "--mlflow"]) == (True, ["s01"])
    assert tracking.take_flag(["s01"]) == (False, ["s01"])


def test_log_run_writes_params_and_metrics(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    mlflow = pytest.importorskip("mlflow")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tmp_path.as_uri())
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")  # restored after the test
    settings_module.get_settings.cache_clear()
    try:
        tracking.log_run("test_runs", {"accuracy": 0.75}, {"questions": 4})
        run = mlflow.search_runs(experiment_names=["test_runs"], output_format="list")[0]
    finally:
        settings_module.get_settings.cache_clear()
    assert run.data.metrics["accuracy"] == 0.75
    assert run.data.params["questions"] == "4"
    # * Prompt fingerprints let two runs be compared: same hash = same prompt.
    assert len(run.data.params["router_prompt"]) == 12
