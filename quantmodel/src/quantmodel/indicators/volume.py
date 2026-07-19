"""Volume confirmation indicators — prior window only."""

from __future__ import annotations

import pandas as pd


def prior_median_volume(volume: pd.Series, lookback: int) -> pd.Series:
    """Median of prior `lookback` sessions (excludes current bar)."""
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    return volume.shift(1).rolling(lookback, min_periods=lookback).median()


def volume_confirm(volume: pd.Series, lookback: int, multiple: float) -> pd.Series:
    med = prior_median_volume(volume, lookback)
    return volume >= (multiple * med)


def volume_multiple_ratio(volume: pd.Series, lookback: int) -> pd.Series:
    med = prior_median_volume(volume, lookback)
    return volume / med
