"""Post-hoc validation package for a single backtest run."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from backtest.metrics import calc_bars_per_year
from backtest.models import TradeRecord
from backtest.validation import bootstrap_sharpe_ci, monte_carlo_test

from tools.evolve import folds


def _pair_trades_to_records(trades_csv: Path) -> list[TradeRecord]:
    """Read trades.csv and return list of TradeRecord."""
    df = pd.read_csv(trades_csv)
    if df.empty:
        return []
    records = []
    df = df.reset_index(drop=True)
    for i in range(0, len(df) - 1, 2):
        entry = df.iloc[i]
        exit_ = df.iloc[i + 1]
        entry_side = str(entry.get("side", "buy")).lower()
        direction = 1 if entry_side == "buy" else -1
        entry_time = pd.to_datetime(entry["timestamp"])
        exit_time = pd.to_datetime(exit_["timestamp"])
        records.append(
            TradeRecord(
                symbol=str(entry.get("code", "")),
                direction=direction,
                entry_price=float(entry["price"]),
                exit_price=float(exit_["price"]),
                entry_time=entry_time,
                exit_time=exit_time,
                size=float(entry["qty"]),
                leverage=1.0,
                pnl=float(exit_["pnl"]),
                pnl_pct=float(exit_["return_pct"]),
                exit_reason=str(exit_.get("reason", "")),
                holding_bars=int(exit_["holding_days"]) if exit_["holding_days"] else 0,
                commission=0.0,
            )
        )
    return records


def run_package_validation(run_dir: str | Path) -> dict[str, Any]:
    """Run MC and bootstrap validation on a backtest run directory.

    Returns {mc_dd_pvalue, sharpe_ci_low, sharpe_ci_high, notes}.
    """
    run_dir = Path(run_dir)
    cfg = json.loads((run_dir / "config.json").read_text())
    art = run_dir / "artifacts"
    trades_csv = art / "trades.csv"
    equity_csv = art / "equity.csv"

    if not trades_csv.exists() or not equity_csv.exists():
        return {"mc_dd_pvalue": 0.0, "sharpe_ci_low": 0.0, "sharpe_ci_high": 0.0, "notes": "missing artifacts"}

    trades = _pair_trades_to_records(trades_csv)
    equity = pd.read_csv(equity_csv, index_col="timestamp", parse_dates=True)["equity"]
    equity.index = equity.index.tz_localize(None)

    initial_capital = float(cfg.get("initial_cash", equity.iloc[0]))
    interval = str(cfg.get("interval", "1D")).upper()
    bars_per_year = calc_bars_per_year(interval, "yfinance")

    mc = monte_carlo_test(trades, initial_capital, n_simulations=1000, seed=42)
    boot = bootstrap_sharpe_ci(equity, n_bootstrap=1000, confidence=0.95, bars_per_year=bars_per_year, seed=42)

    notes = f"MC n_trades={mc.get('n_trades', 0)}; bootstrap prob_positive={boot.get('prob_positive', 0)}"
    return {
        "mc_dd_pvalue": mc.get("p_value_max_dd", 0.0),
        "sharpe_ci_low": boot.get("ci_lower", 0.0),
        "sharpe_ci_high": boot.get("ci_upper", 0.0),
        "notes": notes,
    }
