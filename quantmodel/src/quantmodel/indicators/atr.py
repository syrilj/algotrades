"""Average True Range — Wilder smoothing by default."""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    """Wilder's ATR: ATR_t = ((n-1)*ATR_{t-1} + TR_t) / n."""
    if period < 1:
        raise ValueError("period must be >= 1")
    tr = true_range(high, low, close)
    atr = pd.Series(np.nan, index=tr.index, dtype=float)
    if len(tr) < period:
        return atr
    # seed with simple mean of first `period` true ranges
    seed = tr.iloc[:period].mean()
    atr.iloc[period - 1] = seed
    for i in range(period, len(tr)):
        atr.iloc[i] = ((period - 1) * atr.iloc[i - 1] + tr.iloc[i]) / period
    return atr


def atr_asof_prior_session(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20
) -> pd.Series:
    """ATR available before the fill session (prior close's ATR)."""
    return atr_wilder(high, low, close, period).shift(1)
