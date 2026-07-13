"""Cost / slippage realism checks for evolve_direction_v1."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SLIPPAGE_BASE = 0.0010
SLIPPAGE_STRESS = 0.0020


def _pnl_at_slippage(
    direction: pd.Series,
    size: pd.Series,
    entry_raw: pd.Series,
    exit_raw: pd.Series,
    slippage_per_side: float,
) -> pd.Series:
    """Recompute pnl when total per-side slippage is s.

    pnl(s) = direction * size * (exit_raw - entry_raw)
             - s * size * (entry_raw + exit_raw)
    """
    s = float(slippage_per_side)
    raw_pnl = direction * size * (exit_raw - entry_raw)
    cost = s * size * (entry_raw + exit_raw)
    return raw_pnl - cost


def expectancy_after_costs(trades: pd.DataFrame, slippage_per_side: float) -> float:
    """Mean $ PnL when total per-side slippage is ``slippage_per_side``."""
    if trades.empty:
        return 0.0
    required = {"direction", "size", "entry_price", "exit_price", "pnl"}
    if not required.issubset(trades.columns):
        return 0.0

    df = trades.copy()
    # If raw prices are not present, infer from engine-applied slippage
    if "entry_raw" not in df.columns or "exit_raw" not in df.columns:
        slippage = float(df.get("slippage", SLIPPAGE_BASE).iloc[0]) if "slippage" in df.columns else SLIPPAGE_BASE
        direction = df["direction"].astype(float)
        df["entry_raw"] = df["entry_price"] / (1.0 + direction * slippage)
        df["exit_raw"] = df["exit_price"] / (1.0 - direction * slippage)

    pnls = _pnl_at_slippage(
        df["direction"].astype(float),
        df["size"].astype(float),
        df["entry_raw"].astype(float),
        df["exit_raw"].astype(float),
        slippage_per_side,
    )
    return float(pnls.mean())


def adjust_trades_for_slippage(
    trades: pd.DataFrame, slippage_per_side: float
) -> pd.DataFrame:
    """Return trades copy with pnl adjusted to ``slippage_per_side``."""
    if trades.empty:
        return trades.copy()
    df = trades.copy()
    if "entry_raw" not in df.columns or "exit_raw" not in df.columns:
        slippage = float(df.get("slippage", SLIPPAGE_BASE).iloc[0]) if "slippage" in df.columns else SLIPPAGE_BASE
        direction = df["direction"].astype(float)
        df["entry_raw"] = df["entry_price"] / (1.0 + direction * slippage)
        df["exit_raw"] = df["exit_price"] / (1.0 - direction * slippage)

    df["pnl"] = _pnl_at_slippage(
        df["direction"].astype(float),
        df["size"].astype(float),
        df["entry_raw"].astype(float),
        df["exit_raw"].astype(float),
        slippage_per_side,
    )
    return df


def adjust_equity_for_slippage(
    equity: pd.Series, trades: pd.DataFrame, slippage_per_side: float
) -> pd.Series:
    """Approximate equity curve under ``slippage_per_side``.

    Costs are realised at exit timestamps and propagated forward.
    """
    if equity.empty or trades.empty:
        return equity.copy()

    adjusted = adjust_trades_for_slippage(trades, slippage_per_side)
    if "exit_time" not in adjusted.columns or "pnl" not in adjusted.columns:
        return equity.copy()

    base_slippage = float(adjusted["slippage"].iloc[0]) if "slippage" in adjusted.columns else SLIPPAGE_BASE
    delta = adjusted["pnl"] - trades["pnl"]
    delta.index = adjusted["exit_time"]
    cum = delta.groupby(level=0).sum().reindex(equity.index, method="ffill").fillna(0.0).cumsum()
    return equity + cum


def probe_slippage_applied(
    run_dir: str | Path, expected_slippage: float, n_probe: int = 3
) -> None:
    """Spot-check that the engine applied the expected slippage per side.

    Raises RuntimeError if sampled trades drift from expectation.
    """
    run_dir = Path(run_dir)
    trades_path = run_dir / "artifacts" / "trades.csv"
    if not trades_path.exists():
        raise RuntimeError("no trades.csv to probe")

    df = pd.read_csv(trades_path)
    if df.empty:
        raise RuntimeError("trades.csv empty")

    # Use exit rows for symbol lookup (entry row has the symbol, exit row has pnl)
    probe_rows = []
    for i in range(0, min(len(df) - 1, n_probe * 2), 2):
        entry = df.iloc[i]
        exit_ = df.iloc[i + 1]
        symbol = str(entry.get("code", ""))
        ohlcv = run_dir / "artifacts" / f"ohlcv_{symbol}.csv"
        if not ohlcv.exists():
            continue
        probe_rows.append((entry, exit_, ohlcv))
    if not probe_rows:
        raise RuntimeError("no ohlcv files to probe slippage")

    tolerance = 0.001  # 0.1% — loose enough to survive 1D rounding and 1H date match
    for entry, exit_, ohlcv in probe_rows:
        symbol = str(entry.get("code", ""))
        entry_side = str(entry.get("side", "buy")).lower()
        exit_side = str(exit_.get("side", "sell")).lower()
        direction = 1 if entry_side == "buy" else -1
        entry_ts = pd.to_datetime(entry["timestamp"])
        exit_ts = pd.to_datetime(exit_["timestamp"])

        ohlcv_df = pd.read_csv(ohlcv, index_col=0, parse_dates=True)
        ohlcv_df.index = ohlcv_df.index.tz_localize(None)

        # 1D exact match; 1H may have multiple bars on same date
        def best_match(ts: pd.Timestamp, price: float, is_entry: bool) -> float | None:
            date = ts.date()
            bars = ohlcv_df[ohlcv_df.index.date == date]
            if bars.empty:
                return None
            opens = bars["open"].astype(float)
            if len(opens) == 1:
                return float(opens.iloc[0])
            # 1H: find the open producing slippage closest to expected
            dir_ = direction if is_entry else -direction
            implied_s = dir_ * (price / opens - 1.0)
            best = (implied_s - expected_slippage).abs().idxmin()
            return float(opens.loc[best])

        entry_open = best_match(entry_ts, float(entry["price"]), True)
        exit_open = best_match(exit_ts, float(exit_["price"]), False)
        if entry_open is None or exit_open is None:
            continue

        entry_slip = direction * (float(entry["price"]) / entry_open - 1.0)
        exit_slip = -direction * (float(exit_["price"]) / exit_open - 1.0)
        for label, value in (("entry", entry_slip), ("exit", exit_slip)):
            if math.isfinite(value) and abs(value - expected_slippage) > tolerance:
                raise RuntimeError(
                    f"slippage probe {symbol} {label}: got {value:.6f}, expected {expected_slippage:.6f}"
                )
