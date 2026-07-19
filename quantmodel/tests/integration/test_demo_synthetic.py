"""Integration: synthetic end-to-end backtest runs and writes artifacts."""

from __future__ import annotations

from pathlib import Path

from quantmodel.backtest.engine import run_backtest
from quantmodel.config import load_config

PACKAGE = Path(__file__).resolve().parents[2]


def test_synthetic_backtest_smoke(tmp_path: Path) -> None:
    cfg = load_config(PACKAGE / "configs" / "demo_synthetic.yaml")
    # shorten for test speed
    cfg["data"]["start_date"] = "2019-01-01"
    cfg["data"]["end_date"] = "2022-12-31"
    cfg["data"]["min_history_days"] = 220
    res = run_backtest(cfg, artifacts_root=tmp_path, experiment_number=1, notes="pytest")
    art = Path(res["artifact_dir"])
    assert art.exists()
    assert (art / "manifest.json").exists()
    assert (art / "metrics.json").exists()
    assert (art / "equity_curve.csv").exists()
    assert res["metrics"]["n_days"] > 50
    # synthetic has no survivorship bias flag false -> may still block stress era etc.
    assert res["manifest"].deployment_status in {
        "RESEARCH_ONLY",
        "VALIDATION_PASS",
        "DEPLOYMENT_BLOCKED",
        "PAPER_READY",
    }
