"""Platt (logistic) calibration — the P1-7 path to a real non-identity calibrator.

Isotonic PAVA overfits small OOF pools into 0/1 blocks that log-loss rejects
(the exact gate failure recorded in runs/calibration/candidates). Platt is a
2-parameter monotone sigmoid with Platt-1999 target smoothing, so it cannot
emit degenerate 0/1 probabilities and stays promotable on desk-size samples.
"""
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from confidence_runtime import (  # noqa: E402
    assess_data_freshness,
    evaluate_confidence,
    load_active_calibrator,
)
from calibrate_main_models import justified_promotion, promote_artifact  # noqa: E402
from evolve.calibration import (  # noqa: E402
    apply_isotonic,
    build_calibration_artifact,
    calibration_metrics,
    fit_platt,
)


def _overconfident_frame(n=220, seed=11):
    """Raw scores are rank-informative but overconfident at both tails."""
    rng = np.random.default_rng(seed)
    entry = pd.date_range("2024-01-02", periods=n, freq="7h", tz="UTC")
    raw = rng.uniform(0.05, 0.95, n)
    true_p = 0.5 + 0.35 * (raw - 0.5)  # compressed: raw overstates the edge
    labels = (rng.uniform(0, 1, n) < true_p).astype(float)
    return pd.DataFrame(
        {
            "entry_ts": entry,
            "exit_ts": entry + timedelta(hours=2),
            "raw_probability": raw,
            "realized_r": np.where(labels > 0, 0.02, -0.01),
            "label": labels,
            "code": "TEST.US",
        }
    )


def test_fit_platt_returns_interp_compatible_monotone_curve():
    frame = _overconfident_frame()
    cal = fit_platt(frame["raw_probability"], frame["label"])
    assert cal["method"] == "platt"
    x = np.asarray(cal["x"], dtype=float)
    y = np.asarray(cal["y"], dtype=float)
    assert len(x) == len(y) >= 21
    assert np.all(np.diff(x) > 0)
    assert np.all(np.diff(y) >= 0)  # monotone map preserves ranking
    # Never emits the degenerate 0/1 blocks that break log-loss.
    assert y.min() > 0.0 and y.max() < 1.0
    # apply_isotonic (the runtime's interp) must accept it directly.
    out = apply_isotonic([0.1, 0.5, 0.9], cal)
    assert np.all((out > 0.0) & (out < 1.0))
    assert out[0] <= out[1] <= out[2]


def test_platt_improves_log_loss_on_overconfident_scores():
    frame = _overconfident_frame()
    half = len(frame) // 2
    train, test = frame.iloc[:half], frame.iloc[half:]
    cal = fit_platt(train["raw_probability"], train["label"])
    calibrated = apply_isotonic(test["raw_probability"], cal)
    raw_m = calibration_metrics(test["label"], test["raw_probability"])
    cal_m = calibration_metrics(test["label"], calibrated)
    assert cal_m["log_loss"] < raw_m["log_loss"]
    assert cal_m["brier"] <= raw_m["brier"] + 1e-9


def test_artifact_family_selection_prefers_gate_passing_calibrator():
    frame = _overconfident_frame(n=260)
    artifact = build_calibration_artifact(
        frame,
        model="v39d_confluence",
        candidate_sharpe=1.5,
        candidate_dd=-0.10,
        baseline_sharpe=1.5,
        baseline_dd=-0.10,
    )
    assert artifact["calibration_type"] in ("isotonic", "platt")
    sel = artifact["method_selection"]
    assert set(sel["evaluated"]) >= {"isotonic", "platt"}
    assert sel["winner"] == artifact["calibration_type"]
    # On smooth overconfident data the promotion authority must justify it.
    ok, reasons = justified_promotion(artifact)
    assert ok, reasons


def test_activated_platt_artifact_clears_runtime_gate(tmp_path):
    frame = _overconfident_frame(n=260)
    artifact = build_calibration_artifact(
        frame,
        model="v39d_confluence",
        methods=("platt",),
        candidate_sharpe=1.5,
        candidate_dd=-0.10,
        baseline_sharpe=1.5,
        baseline_dd=-0.10,
    )
    assert artifact["calibration_type"] == "platt"
    ok, reasons = justified_promotion(artifact)
    assert ok, reasons
    path = tmp_path / "v39d_confluence.json"
    promote_artifact(artifact, path)

    info = load_active_calibrator("v39d_confluence", path=path)
    assert info["available"] is True, info.get("reason")

    freshness = assess_data_freshness(
        "2026-07-14T15:00:00Z", now=pd.Timestamp("2026-07-14T15:30:00Z").to_pydatetime()
    )
    result = evaluate_confidence(
        0.80,
        model_ok=True,
        setup_ok=True,
        freshness=freshness,
        model="v39d_confluence",
        calibrator=info,
    )
    assert result["state"] in ("ENTER", "WATCH")
    assert result["probability_calibrated"] is True
    assert result["calibrated_probability"] is not None
    assert "active_calibration" not in result["failed_checks"]


def test_isotonic_only_selection_unchanged_for_legacy_callers():
    frame = _overconfident_frame(n=260)
    artifact = build_calibration_artifact(frame, model="v39d_confluence", methods=("isotonic",))
    assert artifact["calibration_type"] == "isotonic"
    assert artifact["method_selection"]["evaluated"] == ["isotonic"]
