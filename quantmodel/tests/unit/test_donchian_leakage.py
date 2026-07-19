"""Leakage tests for Donchian windows."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantmodel.indicators.donchian import breakout_entry, prior_high, prior_low


def test_current_bar_excluded_from_prior_high() -> None:
    high = pd.Series([1, 2, 3, 10, 4, 5], dtype=float)
    ph = prior_high(high, 3)
    # at index 3 (value 10), prior window is high[0:3] = 1,2,3 max=3, not including 10
    assert ph.iloc[3] == 3.0
    # incorrect rolling without shift would be 10
    wrong = high.rolling(3).max()
    assert wrong.iloc[3] == 10.0
    assert ph.iloc[3] != wrong.iloc[3]


def test_breakout_uses_prior_only() -> None:
    high = pd.Series(np.arange(1, 60, dtype=float))
    close = high.copy()
    close.iloc[-1] = 1000.0  # huge close that is also high
    high.iloc[-1] = 1000.0
    entry = breakout_entry(close, high, 55)
    # last bar: prior max is max of previous 55 highs ending at n-2 = 58? 
    # indices 0..58, last idx 58; prior is shift1 rolling 55 of high -> max of high[3:58] if n=59
    # The current high of 1000 must not be in the threshold
    ph = prior_high(high, 55)
    assert ph.iloc[-1] < 1000.0
    assert bool(entry.iloc[-1]) is True


def test_prior_low_excludes_current() -> None:
    low = pd.Series([5, 4, 3, 1, 2, 2], dtype=float)
    pl = prior_low(low, 3)
    assert pl.iloc[3] == 3.0  # min of 5,4,3 — not 1
