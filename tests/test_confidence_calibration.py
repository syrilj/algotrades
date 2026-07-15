import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from confidence_runtime import (  # noqa: E402
    assess_data_freshness,
    assess_execution_readiness,
    bounded_execution_risk,
    evaluate_confidence,
)
from confidence_shadow import ShadowDecisionLedger  # noqa: E402
from evolve.calibration import (  # noqa: E402
    build_calibration_artifact,
    calibration_metrics,
    load_candidate_files,
    purge_training_rows,
    write_artifact,
)


def _candidate_frame(n=90):
    entry = pd.date_range("2024-01-01", periods=n, freq="6h", tz="UTC")
    raw = np.linspace(0.15, 0.85, n)
    labels = (raw > 0.52).astype(float)
    return pd.DataFrame(
        {
            "timestamp": entry,
            "code": ["TEST.US"] * n,
            "adj_proba": raw,
            "exit_timestamp": entry + timedelta(hours=2),
            "return_pct": np.where(labels > 0, 0.02, -0.01),
        }
    )


def test_calibration_metrics_and_artifact_are_finite(tmp_path):
    frame = _candidate_frame()
    source = tmp_path / "candidates.csv"
    frame.to_csv(source, index=False)
    normalized = load_candidate_files([source])
    artifact = build_calibration_artifact(normalized, model="v39d_confluence")
    assert artifact["schema_version"] == "confidence-calibration-v1"
    assert artifact["metrics"]["calibrated_oof"]["n"] > 0
    assert artifact["metrics"]["raw_final_holdout"]["n"] > 0
    assert np.isfinite(artifact["metrics"]["calibrated_oof"]["brier"])
    assert len(artifact["calibrator"]["x"]) == len(artifact["calibrator"]["y"])


def test_purge_removes_overlapping_outcomes():
    frame = pd.DataFrame(
        {
            "entry_ts": pd.to_datetime(["2024-01-01", "2024-01-03"], utc=True),
            "exit_ts": pd.to_datetime(["2024-01-02 00:00", "2024-01-03 12:00"], utc=True),
        }
    )
    kept = purge_training_rows(frame, pd.Timestamp("2024-01-03", tz="UTC"), timedelta(hours=1))
    assert len(kept) == 1
    assert kept.iloc[0]["entry_ts"] == pd.Timestamp("2024-01-01", tz="UTC")


def test_runtime_abstains_without_active_calibrator(tmp_path):
    freshness = assess_data_freshness("2026-07-14T15:00:00Z", now=pd.Timestamp("2026-07-14T15:30:00Z").to_pydatetime())
    result = evaluate_confidence(
        0.85,
        model_ok=True,
        setup_ok=True,
        freshness=freshness,
        model="v39d_confluence",
        calibrator={"available": False, "reason": "calibration_artifact_missing", "path": str(tmp_path / "none.json")},
    )
    assert result["state"] == "ABSTAIN"
    assert result["size_limit"] == 0.0
    assert "active_calibration" in result["failed_checks"]


def test_runtime_enters_only_with_active_gated_calibrator():
    freshness = assess_data_freshness("2026-07-14T15:00:00Z", now=pd.Timestamp("2026-07-14T15:30:00Z").to_pydatetime())
    artifact = {
        "available": True,
        "path": "test",
        "artifact": {
            "status": "active",
            "schema_version": "confidence-calibration-v1",
            "model": "v39d_confluence",
            "promotion": {"all_calibration_gates_pass": True, "all_promotion_gates_pass": True},
            "thresholds": {"watch": 0.50, "enter": 0.60},
            "calibrator": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
        },
    }
    result = evaluate_confidence(
        0.85,
        model_ok=True,
        setup_ok=True,
        freshness=freshness,
        model="v39d_confluence",
        calibrator=artifact,
    )
    assert result["state"] == "ENTER"
    assert result["calibrated_probability"] == 0.85
    assert result["size_limit"] == 1.0
    assert result.get("uncalibrated") is False


def test_identity_fallback_is_flagged_uncalibrated():
    freshness = assess_data_freshness("2026-07-14T15:00:00Z", now=pd.Timestamp("2026-07-14T15:30:00Z").to_pydatetime())
    artifact = {
        "available": True,
        "path": "fallback_identity:auto",
        "artifact": {
            "status": "active",
            "schema_version": "confidence-calibration-v1-fallback-mismatch",
            "model": "auto",
            "promotion": {"all_promotion_gates_pass": True},
            "thresholds": {"watch": 0.50, "enter": 0.60},
            "calibrator": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
        },
    }
    result = evaluate_confidence(
        0.70,
        model_ok=True,
        setup_ok=True,
        freshness=freshness,
        model="auto",
        calibrator=artifact,
    )
    assert result["state"] == "ENTER"
    assert result["uncalibrated"] is True
    assert "using_identity_calibration_fallback" in result["reasons"]


def test_high_cal_without_setup_stays_watch():
    freshness = assess_data_freshness("2026-07-14T15:00:00Z", now=pd.Timestamp("2026-07-14T15:30:00Z").to_pydatetime())
    artifact = {
        "available": True,
        "path": "test",
        "artifact": {
            "status": "active",
            "schema_version": "confidence-calibration-v1",
            "model": "v39d_confluence",
            "promotion": {"all_promotion_gates_pass": True},
            "thresholds": {"watch": 0.50, "enter": 0.60},
            "calibrator": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
        },
    }
    result = evaluate_confidence(
        0.90,
        model_ok=True,
        setup_ok=False,
        freshness=freshness,
        model="v39d_confluence",
        calibrator=artifact,
    )
    assert result["state"] == "WATCH"
    assert result["size_limit"] == 0.0
    assert "setup_not_ready" in result["reasons"]


def test_completed_us_session_bar_remains_current_overnight():
    freshness = assess_data_freshness(
        "2026-07-14T20:00:00Z",
        now=pd.Timestamp("2026-07-15T04:00:00Z").to_pydatetime(),
        market="US_EQUITY",
    )

    assert freshness["stale"] is False
    assert freshness["market_session"] == "closed"
    assert freshness["next_open_utc"] == "2026-07-15T13:30:00+00:00"


def test_old_bar_fails_once_next_us_session_is_open():
    freshness = assess_data_freshness(
        "2026-07-14T20:00:00Z",
        now=pd.Timestamp("2026-07-15T15:00:00Z").to_pydatetime(),
        market="US_EQUITY",
    )

    assert freshness["stale"] is True
    assert freshness["market_session"] == "open"


def test_future_market_timestamp_fails_closed():
    freshness = assess_data_freshness(
        "2026-07-14T16:00:00Z",
        now=pd.Timestamp("2026-07-14T15:30:00Z").to_pydatetime(),
    )

    assert freshness["stale"] is True
    assert freshness["future_timestamp"] is True


def test_execution_overlays_are_recapped_after_adaptation():
    policy = {
        "equity": {"max_risk_pct": 0.02},
        "options": {"max_risk_pct": 0.25},
    }
    risk = bounded_execution_risk(
        account=1000,
        decision_risk_pct=0.22,
        adapt_mult=1.45,
        confidence_size_limit=1.0,
        vehicle="options",
        policy=policy,
    )

    assert risk["uncapped_risk_pct"] > 0.25
    assert risk["effective_risk_pct"] == 0.25
    assert risk["effective_max_loss_dollars"] == 250.0
    assert risk["capped"] is True


def test_live_readiness_requires_verified_portfolio_and_execution_feed():
    risk = {
        "effective_max_loss_dollars": 20.0,
        "effective_risk_pct": 0.02,
        "hard_cap_risk_pct": 0.02,
    }
    result = assess_execution_readiness(
        live={
            "source": "yfinance",
            "price": 100.0,
            "go_long": True,
            "freshness": {"available": True, "stale": False, "asof_utc": "now"},
        },
        macro={"qqq_trend": "up", "xlp_spy_ratio_state": "risk_on"},
        model={"ok": True, "entry": 100.0, "stop": 98.0},
        confidence={
            "state": "ENTER",
            "raw_probability": 0.8,
            "raw_probability_source": "test",
            "calibration_available": True,
            "calibration_version": "v1",
        },
        decision={"action": "enter", "vehicle": "equity"},
        options_plan=None,
        gex=None,
        execution_risk=risk,
        portfolio_state_verified=False,
    )

    assert result["ready"] is False
    assert "portfolio_state_verified" in result["blockers"]
    assert "trusted_execution_feed" in result["blockers"]


def test_shadow_ledger_records_and_settles(tmp_path):
    ledger = ShadowDecisionLedger(tmp_path / "shadow.jsonl")
    event_id = ledger.record({"symbol": "TEST", "state": "ABSTAIN"})
    assert ledger.settle(event_id, outcome=-0.01)
    summary = ledger.summary()
    assert summary["events"] == 1
    assert summary["settled"] == 1
    assert summary["states"]["ABSTAIN"] == 1
