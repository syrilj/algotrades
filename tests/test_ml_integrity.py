"""Focused contracts for validation, lockbox, gates, and calibration honesty."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tools import calibrate_main_models
from tools.evolve import auditor, folds, gates, train_loop
import tools.evolve_scheduler as scheduler


def _strong_row() -> dict:
    return {
        "id": "candidate",
        "mode": "daily",
        "ret": 0.30,
        "dd": -0.10,
        "sharpe": 1.5,
        "n": 80,
        "wr": 0.60,
        "pf": 1.6,
        "expectancy": 2.0,
    }


def _promotion_evidence() -> dict:
    return {
        "lockbox": {
            "evaluation_role": "untouched_lockbox",
            "window_id": "lockbox-v1",
            "window_start": "2026-04-16",
            "window_end": "2026-07-11",
            "candidate_id": "candidate",
            "selection_use_forbidden": True,
            "ok": True,
        },
        "multi_lock": {"status": "PASS", "ok": True, "n_holdouts": 2},
    }


def test_pass_bar_fails_closed_on_missing_pf_and_expectancy():
    row = _strong_row()
    row.pop("pf")
    row.pop("expectancy")
    result = gates.check_pass_bar(row)
    assert result["passed"] is False
    assert "missing required metric: profit_factor" in result["reasons"]
    assert "missing required metric: expectancy_after_costs" in result["reasons"]


def test_auto_promotion_requires_lockbox_and_multi_lock():
    without_evidence = gates.apply_gates(_strong_row())
    assert without_evidence["pass_bar"]["passed"] is True
    assert without_evidence["claim_level"] == "CLAIM"
    assert without_evidence["may_auto_promote"] is False

    row = _strong_row()
    row["promotion_evidence"] = _promotion_evidence()
    with_evidence = gates.apply_gates(row)
    assert with_evidence["promotion_evidence_ok"] is True
    assert with_evidence["may_auto_promote"] is True


def test_validation_and_lockbox_roles_are_explicit():
    assert folds.VALIDATION_FOLDS_1H is folds.FOLDS_1H
    assert all(f["evaluation_role"] == "validation" for f in folds.FOLDS_1H)
    assert folds.LOCKBOX["evaluation_role"] == "untouched_lockbox"
    assert folds.LOCKBOX["window_id"]


def test_train_loop_calls_selection_window_validation_and_keeps_aliases(monkeypatch):
    tags: list[str] = []

    def fake_run(*args, **kwargs):
        tags.append(kwargs["tag"])
        return {
            "utility": 1.0 if kwargs["tag"] == "train" else 0.8,
            "ret": 0.1,
            "n": 10,
        }

    monkeypatch.setattr(train_loop, "run_one_cached", fake_run)
    result = train_loop.evaluate_model(
        {"id": "m"},
        track="equity_ohlcv",
        cash=1_000,
        train_window=("2024-01-01", "2024-12-31"),
        validation_window=("2025-01-01", "2025-03-31"),
        bag=["SPY.US"],
        reuse=False,
    )
    assert tags == ["train", "validation"]
    assert result["evaluation_role"] == "selection_validation"
    assert result["validation"] is result["oos"]
    assert result["u_validation"] == result["u_oos"]


def _portfolio() -> dict:
    return {
        "total_return": 0.2,
        "max_drawdown": -0.1,
        "sharpe": 1.2,
        "trade_count": 50,
        "win_rate": 0.6,
    }


def test_auditor_uses_results_holdout_as_oos(tmp_path: Path):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"portfolio": _portfolio(), "holdout": _portfolio()}))
    report = auditor.audit_model(model_id="m", results_json=path)
    codes = {finding.code for finding in report.findings}
    assert "missing_holdout" not in codes
    assert "incomplete_holdout" not in codes
    assert report.metrics_snapshot["n"] == 50
    assert report.metrics_snapshot["ret"] == 0.2


def test_auditor_flags_missing_and_malformed_holdout(tmp_path: Path):
    missing = tmp_path / "missing_holdout.json"
    missing.write_text(json.dumps({"portfolio": _portfolio()}))
    report = auditor.audit_model(model_id="m", results_json=missing)
    assert "missing_holdout" in {finding.code for finding in report.findings}
    assert report.verdict == "FAIL"

    malformed = tmp_path / "malformed_holdout.json"
    malformed.write_text(json.dumps({"portfolio": _portfolio(), "holdout": []}))
    report = auditor.audit_model(model_id="m", results_json=malformed)
    assert "malformed_holdout" in {finding.code for finding in report.findings}

    bad_value = tmp_path / "bad_value.json"
    holdout = _portfolio()
    holdout["sharpe"] = "not-a-number"
    bad_value.write_text(json.dumps({"portfolio": _portfolio(), "holdout": holdout}))
    report = auditor.audit_model(model_id="m", results_json=bad_value)
    assert "malformed_holdout_metrics" in {finding.code for finding in report.findings}


def test_identity_artifact_is_ordinal_and_never_runtime_eligible():
    frame = pd.DataFrame(
        {
            "entry_ts": pd.date_range("2025-01-01", periods=4, tz="UTC"),
            "raw_probability": [0.4, 0.6, 0.7, 0.9],
            "label": [0.0, 1.0, 0.0, 1.0],
            "realized_r": [-0.1, 0.2, -0.05, 0.3],
        }
    )
    artifact = calibrate_main_models.build_identity_artifact(
        frame,
        model="m",
        sharpe=1.0,
        dd=-0.1,
        thresholds={"watch": 0.5, "enter": 0.7},
        isotonic_artifact={"dataset": {"n_oof": 4, "folds": 2}, "metrics": {}},
        threshold_meta={"ok": True},
    )
    assert artifact["probability_semantics"] == "uncalibrated_ordinal_score_not_probability"
    assert artifact["calibrated_probability_available"] is False
    assert artifact["runtime_eligible"] is False
    assert artifact["promotion"]["all_calibration_gates_pass"] is False
    assert artifact["promotion"]["all_promotion_gates_pass"] is False


def test_scheduler_is_repo_rooted_and_never_disables_multi_lock(monkeypatch):
    assert scheduler.ROOT.name == "TradingAlgoWork"
    seen: list[str] = []
    monkeypatch.setattr(scheduler, "log", lambda message: None)

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen.extend(str(item) for item in cmd)
        return Result()

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    assert scheduler.run_bounded_evolve() is True
    assert "--no-multi-lock" not in seen
    assert "--quick" not in seen


def test_scheduler_settles_due_before_health_with_expected_output(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(scheduler, "ROOT", tmp_path)
    monkeypatch.setattr(scheduler, "log", lambda message: None)

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen.extend(str(item) for item in cmd)
        output = Path(cmd[cmd.index("--output") + 1])
        output.write_text("{}")
        return Result()

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    assert scheduler.settle_and_monitor_models() is True
    assert "--settle-due" in seen
    assert str(tmp_path / "runs" / "monitoring" / "MODEL_HEALTH.json") in seen
