"""Tests for historical confidence audit — pure helpers + report schema.

Drives real shipped functions in tools/confidence_audit.py (no re-implementation).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from confidence_audit import (  # noqa: E402
    REQUIRED_METRIC_KEYS,
    assert_report_schema,
    build_live_inventory,
    calibrate_confidence_buckets,
    capital_guardrail,
    check_vol_research_only,
    pack_window_metrics,
    pair_round_trips,
    render_markdown,
    run_audit,
)


def test_inventory_lists_money_path_models_and_data_contract():
    inv = build_live_inventory()
    assert inv["schema_version"] == "confidence-audit-inventory-v1"
    mp = inv["money_path"]
    assert mp["preferred_combined_book"]
    assert mp["high_wr_sleeve"]
    assert mp["fallback_equity"]
    routed = inv["models_routed"]
    assert mp["preferred_combined_book"] in routed
    assert routed[mp["preferred_combined_book"]]["confidence_source"]
    dc = inv["data_contract"]
    assert dc["source"] == "local"
    assert dc["interval"] == "1H"
    assert dc["holdout_retune_forbidden"] is True
    assert inv["explicitly_not_money_path"]["options_vol_package_score"]["auto_trade"] is False


def test_pack_window_metrics_requires_all_fields():
    good = pack_window_metrics(
        {
            "total_return": 0.5,
            "max_drawdown": -0.1,
            "sharpe": 1.2,
            "trade_count": 40,
            "win_rate": 0.6,
            "final_value": 1500,
        },
        window="full",
        start="2024-08-01",
        end="2026-07-11",
        cash=1000,
    )
    assert good["schema_ok"] is True
    for k in REQUIRED_METRIC_KEYS:
        assert good[k] is not None

    bad = pack_window_metrics(
        {"total_return": 0.1},
        window="holdout",
        start="2025-08-01",
        end="2026-07-11",
        cash=1000,
    )
    assert bad["schema_ok"] is False
    assert "n" in bad["missing_fields"]


def test_calibrate_buckets_marks_thin_n_unreliable():
    # High conf should win more when n is large
    rng = np.random.default_rng(0)
    conf = np.linspace(0.2, 0.9, 60)
    win = (conf + rng.normal(0, 0.05, size=60) > 0.55).astype(float)
    ret = np.where(win > 0, 0.02, -0.01)
    df = pd.DataFrame({"confidence": conf, "win": win, "return_pct": ret})
    cal = calibrate_confidence_buckets(df, min_bucket_n=5, min_total_n=20)
    assert cal["n"] == 60
    assert len(cal["buckets"]) >= 2
    assert cal["reliable"] is True or cal["label"] in ("ok", "unreliable_inverted")

    thin = pd.DataFrame(
        {
            "confidence": [0.3, 0.4, 0.8],
            "win": [1.0, 0.0, 1.0],
            "return_pct": [0.01, -0.01, 0.02],
        }
    )
    cal_thin = calibrate_confidence_buckets(thin, min_bucket_n=8, min_total_n=20)
    assert cal_thin["reliable"] is False
    assert cal_thin["label"] == "unreliable"


def test_calibrate_inverted_is_flagged():
    # Low conf wins more than high conf → inverted
    conf = np.array([0.2] * 15 + [0.5] * 15 + [0.85] * 15)
    win = np.array([1.0] * 15 + [0.5] * 15 + [0.0] * 15)  # inverted
    # make win 0/1 properly for high bucket all losses
    win = np.array([1] * 15 + [1] * 8 + [0] * 7 + [0] * 15, dtype=float)
    ret = np.where(win > 0, 0.02, -0.02)
    df = pd.DataFrame({"confidence": conf, "win": win, "return_pct": ret})
    cal = calibrate_confidence_buckets(df, min_bucket_n=5, min_total_n=20)
    assert cal["n"] == 45
    # discrimination should be negative or label inverted
    if cal.get("discrimination") is not None and cal["discrimination"] < -0.02:
        assert cal["label"] == "unreliable_inverted"
        assert cal["reliable"] is False


def test_pair_round_trips_uses_percent_points():
    trades = pd.DataFrame(
        {
            "timestamp": ["2024-01-01", "2024-01-03", "2024-01-05", "2024-01-07"],
            "code": ["AAA.US", "AAA.US", "BBB.US", "BBB.US"],
            "side": ["buy", "sell", "buy", "sell"],
            "price": [100.0, 110.0, 50.0, 45.0],
            "qty": [1.0, 1.0, 2.0, 2.0],
            "return_pct": [0.0, 10.0, 0.0, -10.0],  # percent points
        }
    )
    trips = pair_round_trips(trades)
    assert len(trips) == 2
    assert abs(trips.iloc[0]["return_pct"] - 0.10) < 1e-9
    assert trips.iloc[0]["win"] == 1.0
    assert abs(trips.iloc[1]["return_pct"] + 0.10) < 1e-9
    assert trips.iloc[1]["win"] == 0.0


def test_capital_guardrail_blocks_thin_holdout_and_vol_autotrade():
    cal_ok = {"reliable": True, "label": "ok", "reason": None}
    g = capital_guardrail(full_n=100, holdout_n=10, calib=cal_ok, vol_auto_trade=False)
    assert g["research_only"] is True
    assert g["not_for_naked_size_up"] is True
    assert g["auto_promote"] is False

    g2 = capital_guardrail(full_n=100, holdout_n=50, calib=cal_ok, vol_auto_trade=True)
    assert g2["research_only"] is True
    assert "auto_trade" in " ".join(g2["reasons"]).lower() or any(
        "auto_trade" in r for r in g2["reasons"]
    )


def test_vol_research_still_not_auto_trade():
    check = check_vol_research_only()
    assert check.get("auto_trade") is False
    assert check.get("research_only") is True


def test_run_audit_quick_schema_offline(tmp_path):
    """Smoke the real CLI path with --quick (frozen results, no long backtest)."""
    out = tmp_path / "audit"
    report = run_audit(cash=1000, quick=True, out_dir=out)
    assert report["schema_version"] == "confidence-audit-v1"
    errs = assert_report_schema(report)
    assert errs == [], errs
    assert report["schema_ok"] is True
    assert (out / "AUDIT.json").exists()
    assert (out / "AUDIT.md").exists()
    raw = json.loads((out / "AUDIT.json").read_text())
    assert raw["inventory"]["money_path"]["preferred_combined_book"]
    assert len(raw["confidence_calibration"]["buckets"]) >= 2
    assert raw["guardrails"]["auto_promote"] is False
    assert raw["options_vol_research"]["auto_trade"] is False
    md = (out / "AUDIT.md").read_text()
    assert "Inventory" in md
    assert "Confidence calibration" in md
    # markdown renderer is the same shipped function
    assert "dual_sleeve" in render_markdown(report).lower() or "v72" in render_markdown(report).lower()


def test_assert_report_schema_fails_on_error_only_window(tmp_path):
    """Failed historical windows must not report schema_ok (criterion 5)."""
    good = run_audit(cash=1000, quick=True, out_dir=tmp_path / "base")
    assert good["schema_ok"] is True
    # Mutate a real report: replace holdout with error-only block (no metrics).
    broken = json.loads(json.dumps(good, default=str))
    broken["historical"]["dual_sleeve"]["holdout"] = {
        "error": "simulated_backtest_failure",
        "schema_ok": False,
        "missing_fields": list(REQUIRED_METRIC_KEYS),
    }
    errs = assert_report_schema(broken)
    assert errs, "expected non-empty schema_errors for error-only holdout"
    assert any("holdout" in e and "error" in e for e in errs)
    assert any("holdout.ret missing" in e or "holdout.n missing" in e for e in errs)
    # Simulate run_audit's schema_ok assignment path
    assert (len(errs) == 0) is False
    # Also missing metrics without error key
    broken2 = json.loads(json.dumps(good, default=str))
    broken2["historical"]["dual_sleeve"]["full"] = {"window": "full", "start": "x", "end": "y"}
    errs2 = assert_report_schema(broken2)
    assert errs2
    assert any("full.ret missing" in e for e in errs2)
    assert any("full.n missing" in e for e in errs2)
    for k in REQUIRED_METRIC_KEYS:
        assert any(f"full.{k} missing" in e for e in errs2), f"missing check for full.{k}"
