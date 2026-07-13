"""Tests for direction_report and audit_gen helpers."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools import direction_report
from tools.evolve import audit_gen


def test_build_direction_report(tmp_path: Path):
    trades_csv = tmp_path / "trades.csv"
    # two trades, two rows each
    rows = [
        {"timestamp": "2025-01-02", "code": "TSLA.US", "side": "buy", "price": 100, "qty": 1, "reason": "signal", "pnl": 0, "holding_days": 0, "return_pct": 0},
        {"timestamp": "2025-01-05", "code": "TSLA.US", "side": "sell", "price": 105, "qty": 1, "reason": "stop", "pnl": 5, "holding_days": 3, "return_pct": 0.05},
        {"timestamp": "2025-01-10", "code": "TSLA.US", "side": "buy", "price": 102, "qty": 1, "reason": "signal", "pnl": 0, "holding_days": 0, "return_pct": 0},
        {"timestamp": "2025-01-13", "code": "TSLA.US", "side": "sell", "price": 100, "qty": 1, "reason": "stop", "pnl": -2, "holding_days": 3, "return_pct": -0.02},
    ]
    pd.DataFrame(rows).to_csv(trades_csv, index=False)

    idx = pd.date_range("2025-01-01", "2025-01-15")
    np.random.seed(0)
    close = pd.Series(100 + np.cumsum(np.random.randn(len(idx))), index=idx)
    bars = {"TSLA.US": pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000}, index=idx)}

    report = direction_report.build_direction_report(trades_csv, bars)
    assert report["n_trades"] == 2
    assert report["expectancy"] == pytest.approx(1.5, abs=0.01)
    assert "hit_3d" in report["hit"]
    assert "mfe_mae" in report
    assert "regime_slices" in report


def test_audit_gen_evaluate(tmp_path: Path):
    idx = pd.date_range("2025-01-01", periods=100)
    equity = pd.Series(1 + np.cumsum(np.random.normal(0.001, 0.01, 100)), index=idx)
    trades = pd.DataFrame({
        "entry_time": pd.to_datetime(["2025-01-02", "2025-01-20", "2025-02-10"]),
        "exit_time": pd.to_datetime(["2025-01-10", "2025-01-30", "2025-02-20"]),
        "symbol": ["TSLA.US"] * 3,
        "direction": [1, 1, -1],
        "entry_price": [100.0, 101.0, 105.0],
        "exit_price": [105.0, 100.0, 100.0],
        "size": [1.0, 1.0, 1.0],
        "pnl": [5.0, -1.0, 5.0],
        "pnl_pct": [0.05, -0.01, 0.05],
        "holding_days": [8, 10, 10],
        "exit_reason": ["stop", "stop", "stop"],
    })
    candidate = {
        "id": "test",
        "gen": 0,
        "campaign_id": "test",
        "parent": "",
        "fitness": 0.5,
        "fold_metrics": {
            "F1": {"ret": 0.1, "sharpe": 0.6, "calmar": 1.0, "dd": -0.15, "wr": 0.55, "pf": 1.5, "n": 50, "expectancy": 0.5, "avg_hold_days": 3},
            "F2": {"ret": 0.08, "sharpe": 0.55, "calmar": 0.9, "dd": -0.18, "wr": 0.52, "pf": 1.4, "n": 45, "expectancy": 0.4, "avg_hold_days": 3},
            "F3": {"ret": 0.12, "sharpe": 0.7, "calmar": 1.2, "dd": -0.12, "wr": 0.58, "pf": 1.6, "n": 55, "expectancy": 0.6, "avg_hold_days": 3},
            "F4": {"ret": 0.09, "sharpe": 0.58, "calmar": 1.0, "dd": -0.14, "wr": 0.54, "pf": 1.5, "n": 48, "expectancy": 0.45, "avg_hold_days": 3},
        },
        "trades": trades,
        "equity": equity,
        "bars_per_year": 252,
        "validation": {"mc_dd_pvalue": 0.12, "sharpe_ci_low": 0.2, "sharpe_ci_high": 0.8, "notes": ""},
        "direction_report": {
            "n_trades": 3,
            "expectancy": 3.0,
            "win_rate": 0.66,
            "hit": {"hit_5d": {"rate": 0.6, "n": 3, "p_value": 0.1, "ci_low": 0.2, "ci_high": 0.9}},
            "mfe_mae": {"mfe_median": 2.0, "mae_median": 1.0, "mfe_mae_ratio": 2.0},
            "regime_slices": {
                "risk_on": {"n": 2, "expectancy": 2.0, "win_rate": 0.5, "ret": 0.02, "max_drawdown": -0.1},
                "neutral": {"n": 1, "expectancy": 1.0, "win_rate": 1.0, "ret": 0.01, "max_drawdown": -0.05},
            },
        },
        "perturb_fitness": [0.4, 0.5, 0.45],
        "lockbox": {"fitness": 0.3},
        "run_dir": str(tmp_path),
        "model_dir": str(tmp_path),
    }
    gate_results = audit_gen.evaluate_gates(candidate)
    assert len(gate_results) == 13
    out_path = tmp_path / "AUDIT.json"
    audit_gen.write_audit(candidate, gate_results, out_path)
    assert out_path.exists()
    assert out_path.with_suffix(".md").exists()
