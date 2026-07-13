"""Tests for tools/evolve/folds.py and tools/evolve/costs.py."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools.evolve import costs, folds


def _write_trade_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_derive_gap_days(tmp_path: Path):
    rows = []
    for _ in range(19):
        rows.append({"timestamp": "2025-01-01", "side": "buy", "price": 100, "qty": 1, "reason": "signal", "pnl": 0, "holding_days": 0, "return_pct": 0})
        rows.append({"timestamp": "2025-01-11", "side": "sell", "price": 101, "qty": 1, "reason": "stop", "pnl": 1, "holding_days": 10, "return_pct": 0.01})
    path = tmp_path / "trades.csv"
    _write_trade_csv(path, rows)
    assert folds.derive_gap_days(path) == 15


def test_slice_oos(tmp_path: Path):
    run_dir = tmp_path / "run"
    art = run_dir / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    rows = [
        {"timestamp": "2025-04-15", "code": "TSLA.US", "side": "buy", "price": 100, "qty": 1, "reason": "signal", "pnl": 0, "holding_days": 0, "return_pct": 0},
        {"timestamp": "2025-04-16", "code": "TSLA.US", "side": "sell", "price": 101, "qty": 1, "reason": "stop", "pnl": 1, "holding_days": 1, "return_pct": 0.01},
        {"timestamp": "2025-05-01", "code": "TSLA.US", "side": "buy", "price": 102, "qty": 1, "reason": "signal", "pnl": 0, "holding_days": 0, "return_pct": 0},
        {"timestamp": "2025-05-02", "code": "TSLA.US", "side": "sell", "price": 100, "qty": 1, "reason": "stop", "pnl": -2, "holding_days": 1, "return_pct": -0.02},
    ]
    _write_trade_csv(art / "trades.csv", rows)
    idx = pd.date_range("2025-04-15", "2025-05-02")
    eq = pd.Series(1 + np.linspace(0, 0.02, len(idx)) - 0.01, index=idx)
    eq.index.name = "timestamp"
    eq.to_frame(name="equity").to_csv(art / "equity.csv")
    (run_dir / "config.json").write_text(json.dumps({"slippage_us": 0.001}))

    trades, equity = folds.slice_oos(run_dir, "2025-04-16", "2025-05-01")
    assert len(trades) == 1
    assert trades.iloc[0]["entry_time"] == pd.Timestamp("2025-05-01")


def test_fold_metrics():
    idx = pd.date_range("2025-01-01", periods=50)
    equity = pd.Series(1 + np.cumsum(np.random.normal(0.001, 0.01, 50)), index=idx)
    trades = pd.DataFrame({
        "pnl": [1.0, -0.5, 2.0, -1.0, 0.5],
        "holding_days": [1, 2, 1, 3, 1],
    })
    m = folds.fold_metrics(trades, equity, 252)
    assert m["n"] == 5
    assert m["expectancy"] == pytest.approx(0.4, abs=0.001)
    assert "sharpe" in m


def test_expectancy_after_costs():
    trades = pd.DataFrame({
        "direction": [1, -1],
        "size": [1.0, 1.0],
        "entry_price": [100.0, 100.0],
        "exit_price": [101.0, 99.0],
        "pnl": [1.0, 1.0],
        "slippage": [0.001, 0.001],
    })
    e = costs.expectancy_after_costs(trades, 0.001)
    assert e == pytest.approx(1.0, abs=0.01)
    e_stress = costs.expectancy_after_costs(trades, 0.002)
    assert e_stress < e
