"""Moving averages."""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    if window < 1:
        raise ValueError("window must be >= 1")
    return series.rolling(window, min_periods=window).mean()


def above_sma(series: pd.Series, window: int) -> pd.Series:
    return series > sma(series, window)
