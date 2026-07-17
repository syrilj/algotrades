"""Validation/lockbox layout, slicing, and fold metrics for evolve_direction_v1."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from tools.evolve import scoring

ROOT = Path(__file__).resolve().parents[2]

# Track A (1H) — rolling validation folds for 2025-04 through 2026-04.
# These windows are repeatedly used for model selection and are therefore not
# a final out-of-sample claim.  The historical oos_* keys remain as wire-format
# aliases so existing run artifacts and callers continue to work.
FOLDS_1H: list[dict[str, Any]] = [
    {
        "name": "F1",
        "train_start": "2024-08-01",
        "train_end": "2025-03-31",
        "gap_days": 15,
        "oos_start": "2025-04-16",
        "oos_end": "2025-07-15",
        "warmup_start": "2025-03-02",
    },
    {
        "name": "F2",
        "train_start": "2024-08-01",
        "train_end": "2025-06-30",
        "gap_days": 15,
        "oos_start": "2025-07-16",
        "oos_end": "2025-10-15",
        "warmup_start": "2025-06-01",
    },
    {
        "name": "F3",
        "train_start": "2024-08-01",
        "train_end": "2025-09-30",
        "gap_days": 15,
        "oos_start": "2025-10-16",
        "oos_end": "2026-01-15",
        "warmup_start": "2025-09-01",
    },
    {
        "name": "F4",
        "train_start": "2024-08-01",
        "train_end": "2025-12-31",
        "gap_days": 15,
        "oos_start": "2026-01-16",
        "oos_end": "2026-04-15",
        "warmup_start": "2025-12-02",
    },
]
for _fold in FOLDS_1H:
    _fold.setdefault("evaluation_role", "validation")
    _fold.setdefault("validation_start", _fold["oos_start"])
    _fold.setdefault("validation_end", _fold["oos_end"])

VALIDATION_FOLDS_1H = FOLDS_1H

LOCKBOX: dict[str, Any] = {
    "name": "LOCKBOX",
    "train_start": "2024-08-01",
    "train_end": "2026-03-31",
    "gap_days": 15,
    "oos_start": "2026-04-16",
    "oos_end": "2026-07-11",
    "warmup_start": "2026-03-02",
    "evaluation_role": "untouched_lockbox",
    "window_id": "equity_1h_lockbox_2026q2_v1",
}

# Track B (1D) — independent calendar-year multi-lock validation folds
_FOLDS_1D_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
FOLDS_1D_TRACKB: list[dict[str, Any]] = []
for y in _FOLDS_1D_YEARS:
    validation_start = f"{y+1}-01-16"
    if y == 2025:
        validation_end = "2026-07-11"
    else:
        validation_end = f"{y+1}-12-31"
    FOLDS_1D_TRACKB.append(
        {
            "name": f"B{y+1}",
            "train_start": "2020-01-01",
            "train_end": f"{y}-12-31",
            "gap_days": 15,
            "oos_start": validation_start,  # compatibility artifact key
            "oos_end": validation_end,
            "warmup_start": f"{y}-12-02",
        }
    )
for _fold in FOLDS_1D_TRACKB:
    _fold.setdefault("evaluation_role", "multi_lock_validation")
    _fold.setdefault("validation_start", _fold["oos_start"])
    _fold.setdefault("validation_end", _fold["oos_end"])


def _parse_dt(s: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(s)


def derive_gap_days(trades_csv: str | Path) -> int:
    """Recompute gap from p95 holding days, bounded below by 15."""
    path = Path(trades_csv)
    if not path.exists():
        return 15
    df = pd.read_csv(path)
    if "holding_days" not in df.columns or df.empty:
        return 15
    # Exit rows carry holding_days > 0
    holds = df.loc[df["holding_days"] > 0, "holding_days"].dropna().astype(float)
    if holds.empty:
        return 15
    p95 = float(np.percentile(holds.values, 95))
    return max(15, int(math.ceil(p95)) + 2)


def _pair_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Convert two-row-per-trade CSV into one-row-per-trade DataFrame."""
    if df.empty:
        return pd.DataFrame(
            columns=[
                "entry_time",
                "exit_time",
                "symbol",
                "direction",
                "entry_price",
                "exit_price",
                "size",
                "pnl",
                "pnl_pct",
                "holding_days",
                "exit_reason",
                "slippage",
            ]
        )
    # rows are interleaved: entry, exit, entry, exit, ...
    rows = []
    df = df.reset_index(drop=True)
    for i in range(0, len(df) - 1, 2):
        entry = df.iloc[i]
        exit_ = df.iloc[i + 1]
        # Determine direction from entry side
        entry_side = str(entry.get("side", "buy")).lower()
        direction = 1 if entry_side == "buy" else -1
        entry_ts = pd.to_datetime(entry["timestamp"])
        exit_ts = pd.to_datetime(exit_["timestamp"])
        rows.append(
            {
                "entry_time": entry_ts,
                "exit_time": exit_ts,
                "symbol": entry.get("code", ""),
                "direction": direction,
                "entry_price": float(entry["price"]),
                "exit_price": float(exit_["price"]),
                "size": float(entry["qty"]),
                "pnl": float(exit_["pnl"]),
                "pnl_pct": float(exit_["return_pct"]),
                "holding_days": int(exit_["holding_days"]) if exit_["holding_days"] else 0,
                "exit_reason": str(exit_.get("reason", "")),
            }
        )
    return pd.DataFrame(rows)


def _load_slippage(run_dir: Path) -> float:
    cfg_path = run_dir / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
            sl = cfg.get("slippage_us")
            if sl is not None:
                return float(sl)
        except Exception:
            pass
    return 0.0


def _raw_prices(trades: pd.DataFrame, slippage: float) -> pd.DataFrame:
    """Add entry_raw / exit_raw columns by reversing engine slippage."""
    s = float(slippage)
    direction = trades["direction"].astype(float)
    trades = trades.copy()
    trades["entry_raw"] = trades["entry_price"] / (1.0 + direction * s)
    trades["exit_raw"] = trades["exit_price"] / (1.0 - direction * s)
    return trades


def slice_validation(
    run_dir: str | Path, validation_start: str, validation_end: str
) -> tuple[pd.DataFrame, pd.Series]:
    """Return trades/equity restricted to a selection validation window.

    trades is one row per trade with entry/exit raw prices.
    """
    run_dir = Path(run_dir)
    art = run_dir / "artifacts"
    trades_path = art / "trades.csv"
    equity_path = art / "equity.csv"

    if not trades_path.exists() or not equity_path.exists():
        return pd.DataFrame(), pd.Series(dtype=float)

    trades_df = pd.read_csv(trades_path)
    trades = _pair_trades(trades_df)
    if not trades.empty:
        slippage = _load_slippage(run_dir)
        trades = _raw_prices(trades, slippage)

    oos_start_ts = _parse_dt(validation_start)
    oos_end_ts = _parse_dt(validation_end)

    if not trades.empty:
        trades = trades[
            (trades["entry_time"] >= oos_start_ts) & (trades["entry_time"] <= oos_end_ts)
        ]

    eq = pd.read_csv(equity_path, index_col="timestamp", parse_dates=True)
    eq = eq["equity"].sort_index()
    eq.index = eq.index.tz_localize(None)
    eq = eq[(eq.index >= oos_start_ts) & (eq.index <= oos_end_ts)]
    if eq.empty:
        return trades, eq
    eq = eq / eq.iloc[0]
    return trades, eq


def slice_oos(
    run_dir: str | Path, oos_start: str, oos_end: str
) -> tuple[pd.DataFrame, pd.Series]:
    """Backward-compatible alias for :func:`slice_validation`.

    The name describes the historical artifact schema, not a claim that a
    repeatedly selected-on window is an untouched test set.
    """
    return slice_validation(run_dir, oos_start, oos_end)


def slice_lockbox(
    run_dir: str | Path, lockbox_start: str, lockbox_end: str
) -> tuple[pd.DataFrame, pd.Series]:
    """Slice a designated final lockbox window; callers must not tune on it."""
    return slice_validation(run_dir, lockbox_start, lockbox_end)


def fold_metrics(
    trades: pd.DataFrame, equity: pd.Series, bars_per_year: int
) -> dict[str, Any]:
    """Compute metrics for a validation or lockbox trade/equity slice."""
    if equity.empty or equity.iloc[0] <= 0:
        return {
            "ret": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "dd": 0.0,
            "wr": 0.0,
            "pf": 0.0,
            "n": 0,
            "expectancy": 0.0,
            "avg_hold_days": 0.0,
        }

    n_bars = len(equity)
    ratio = equity / equity.iloc[0]
    ratio = ratio.replace(0, 1e-9).where(ratio > 0, 1e-9)
    log_rets = np.log(ratio)
    total_log = float(log_rets.iloc[-1])
    if not np.isfinite(total_log):
        total_log = float(np.log(1e-9))
    ann_ret = float(np.exp(total_log * (bars_per_year / max(n_bars, 1))) - 1.0)
    ret = float(equity.iloc[-1] / equity.iloc[0] - 1.0)

    port_ret = equity.pct_change().fillna(0.0)
    vol = float(port_ret.std())
    sharpe = float(port_ret.mean() / (vol + 1e-10) * np.sqrt(bars_per_year))

    peak = equity.cummax()
    dd = (equity - peak) / peak.replace(0, 1)
    max_dd = float(dd.min())

    calmar = float(ann_ret / max(abs(max_dd), 0.02))

    if trades.empty or "pnl" not in trades.columns:
        wr = 0.0
        pf = 0.0
        expectancy = 0.0
        avg_hold_days = 0.0
        n = 0
    else:
        pnls = trades["pnl"].astype(float)
        n = int(len(trades))
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        wr = float(len(wins) / n) if n else 0.0
        gross_profit = float(wins.sum()) if len(wins) else 0.0
        gross_loss = abs(float(losses.sum())) if len(losses) else 1e-10
        pf = gross_profit / gross_loss if gross_loss > 1e-10 else 0.0
        expectancy = float(pnls.mean())
        avg_hold_days = float(trades["holding_days"].astype(float).mean()) if "holding_days" in trades.columns else 0.0

    return {
        "ret": ret,
        "sharpe": sharpe,
        "calmar": calmar,
        "dd": max_dd,
        "wr": wr,
        "pf": pf,
        "n": n,
        "expectancy": expectancy,
        "avg_hold_days": avg_hold_days,
    }


def purged_label_mask(
    entry_times: pd.Series, horizon_days: float, train_end: str
) -> np.ndarray:
    """True = keep label (label horizon ends on or before train_end)."""
    train_end_ts = _parse_dt(train_end)
    horizon = pd.Timedelta(days=horizon_days)
    return (entry_times + horizon <= train_end_ts).to_numpy()


def fold_utility(m: dict[str, Any]) -> float:
    """Per-fold utility from OBJECTIVE.json."""
    return scoring.fold_utility(m)


def fold_fitness(fold_ms: list[dict[str, Any]]) -> float:
    """Aggregate fitness across folds."""
    return scoring.fold_fitness(fold_ms)
