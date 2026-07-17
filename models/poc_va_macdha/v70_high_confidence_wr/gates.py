"""Pure causal quality gates for high-confidence entry selection.

All features use only past / current finished information:
- rolling windows end at the bar being evaluated
- prior-bar constructive uses open/close of the *current* finished bar when
  the signal is generated on that bar (OHLCV of the bar is known at close)
- expanding ATR median is shifted by 1 so the threshold never includes the
  current bar's own ATR when classifying extremes

These helpers are free of I/O so unit tests can assert causality without a
full multi-year backtest.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1.0 / length, adjust=False).mean()


def trend_mask(
    close: pd.Series,
    *,
    lookback: int = 250,
    direction: str = "above",
) -> pd.Series:
    """Price vs SMA(lookback). Causal rolling mean only."""
    price = close.astype(float)
    sma = price.rolling(lookback, min_periods=max(1, lookback // 2)).mean()
    direction = direction.lower()
    if direction == "above":
        return (price > sma).fillna(False)
    if direction == "below":
        return (price < sma).fillna(False)
    return pd.Series(True, index=close.index)


def quality_components(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Return named boolean components used by the quality score.

    Components (all point-in-time at bar close):
    - constructive: close >= open (finished bar not a pure sell)
    - volume_ok: volume >= 0.85 * 20-bar average volume
    - atr_ok: atr% <= 1.35 * expanding median of prior atr% (no current-bar leak)
    """
    close = df["close"].astype(float)
    opening = df["open"].astype(float)
    volume = df["volume"].astype(float)

    constructive = (close >= opening).fillna(False)

    vol_ma = volume.rolling(20, min_periods=8).mean()
    volume_ok = (volume >= 0.85 * vol_ma).fillna(False)

    atr14 = atr(df, 14)
    atr_pct = atr14 / close.replace(0.0, np.nan)
    # Expanding median of *prior* atr% only
    atr_med = atr_pct.shift(1).expanding(min_periods=20).median()
    atr_ok = (atr_pct <= 1.35 * atr_med).fillna(False)

    return {
        "constructive": constructive,
        "volume_ok": volume_ok,
        "atr_ok": atr_ok,
    }


def quality_score(df: pd.DataFrame) -> pd.Series:
    comps = quality_components(df)
    score = sum(c.astype(int) for c in comps.values())
    return score.astype(int).rename("quality_score")


def quality_gate(df: pd.DataFrame, *, min_score: int = 2) -> pd.Series:
    """True when quality_score >= min_score (entry filter only)."""
    return (quality_score(df) >= int(min_score)).rename("quality_gate")


def apply_entry_only_gates(
    primary: pd.Series,
    *,
    trend: Optional[pd.Series] = None,
    quality: Optional[pd.Series] = None,
    close: Optional[pd.Series] = None,
    stop_loss_pct: float = 0.0,
    continuous_trend: bool = False,
) -> pd.Series:
    """State machine: gates apply at entry; exit when primary drops (or stop).

    - New long only if primary crosses into long AND trend AND quality hold.
    - Once in, stay until primary exits (or optional hard stop).
    - continuous_trend=True also exits when trend flips (not used by default).
    """
    idx = primary.index
    primary = primary.reindex(idx).fillna(0.0).astype(float)
    if trend is None:
        trend = pd.Series(True, index=idx)
    else:
        trend = trend.reindex(idx).fillna(False)
    if quality is None:
        quality = pd.Series(True, index=idx)
    else:
        quality = quality.reindex(idx).fillna(False)
    if close is None:
        close = pd.Series(1.0, index=idx)
    else:
        close = close.reindex(idx).astype(float)

    trigger = 1.0 - stop_loss_pct if stop_loss_pct > 0 else 0.0
    in_pos = False
    entry_price = 0.0
    prev_primary = 0.0
    out = pd.Series(0.0, index=idx)

    for i in range(len(idx)):
        p = float(primary.iloc[i])
        t = bool(trend.iloc[i])
        q = bool(quality.iloc[i])
        c = float(close.iloc[i])
        new_entry = (p > 0.5) and (prev_primary <= 0.5) and t and q

        if not in_pos:
            if new_entry:
                in_pos = True
                entry_price = c
        else:
            exit_now = False
            if p <= 0.5:
                exit_now = True
            elif stop_loss_pct > 0 and c < entry_price * trigger:
                exit_now = True
            elif continuous_trend and not t:
                exit_now = True
            if exit_now:
                in_pos = False

        out.iloc[i] = 1.0 if in_pos else 0.0
        prev_primary = p

    return out


def frozen_defaults() -> Dict[str, Any]:
    """Pre-registered hunt defaults (frozen before OOS evaluation)."""
    return {
        "base_models": ["v45_ultimate_rsi"],
        "primary": "v45_ultimate_rsi",
        "trend_filter": {
            "lookback": 250,
            "price_col": "close",
            "direction": "above",
            "apply": "entry",
        },
        "quality": {
            "min_score": 2,
            "enabled": True,
        },
        "signal_scale": 0.225,
        "stop_loss_pct": 0.0,
        "selection_rule": "frozen_before_oos_eval",
        "train_window_end": "2025-08-01",
    }
