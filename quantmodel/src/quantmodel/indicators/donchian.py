"""Donchian channel indicators — current bar excluded from windows."""

from __future__ import annotations

import pandas as pd


def prior_high(high: pd.Series, lookback: int) -> pd.Series:
    """Rolling max of prior `lookback` highs (excludes current bar)."""
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    return high.shift(1).rolling(lookback, min_periods=lookback).max()


def prior_low(low: pd.Series, lookback: int) -> pd.Series:
    """Rolling min of prior `lookback` lows (excludes current bar)."""
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    return low.shift(1).rolling(lookback, min_periods=lookback).min()


def breakout_entry(close: pd.Series, high: pd.Series, lookback: int) -> pd.Series:
    """Close breaks above prior lookback high."""
    return close > prior_high(high, lookback)


def donchian_exit(low: pd.Series, lookback: int) -> pd.Series:
    """Low breaks below prior lookback low."""
    return low < prior_low(low, lookback)
