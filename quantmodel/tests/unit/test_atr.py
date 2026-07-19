"""Wilder ATR tests."""

from __future__ import annotations

import pandas as pd

from quantmodel.indicators.atr import atr_wilder, true_range


def test_true_range_basic() -> None:
    high = pd.Series([10.0, 12.0, 11.0])
    low = pd.Series([9.0, 10.0, 9.5])
    close = pd.Series([9.5, 11.0, 10.0])
    tr = true_range(high, low, close)
    assert tr.iloc[0] == 1.0
    # day1: max(2, |12-9.5|, |10-9.5|) = max(2, 2.5, 0.5) = 2.5
    assert abs(tr.iloc[1] - 2.5) < 1e-9


def test_atr_wilder_seed_and_smooth() -> None:
    n = 30
    high = pd.Series(range(10, 10 + n), dtype=float)
    low = high - 1.0
    close = high - 0.3
    atr = atr_wilder(high, low, close, period=5)
    assert pd.isna(atr.iloc[3])
    assert pd.notna(atr.iloc[4])
    # recursive smooth should be finite and positive
    assert atr.iloc[-1] > 0
