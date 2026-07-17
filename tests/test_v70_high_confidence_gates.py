"""Unit tests for v70 causal quality gates (no look-ahead)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models" / "poc_va_macdha" / "v70_high_confidence_wr"))

from gates import (  # noqa: E402
    apply_entry_only_gates,
    quality_components,
    quality_gate,
    quality_score,
    trend_mask,
)


def _synthetic_ohlcv(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    close = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    open_ = close + rng.normal(0, 0.2, size=n)
    high = np.maximum(open_, close) + rng.uniform(0, 0.5, size=n)
    low = np.minimum(open_, close) - rng.uniform(0, 0.5, size=n)
    volume = rng.uniform(1e5, 5e5, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_trend_mask_above_sma_is_boolean_and_aligned():
    df = _synthetic_ohlcv()
    mask = trend_mask(df["close"], lookback=50, direction="above")
    assert len(mask) == len(df)
    assert mask.dtype == bool or mask.dtype == np.bool_
    # After warmup, when price is above SMA it should be True somewhere
    sma = df["close"].rolling(50, min_periods=25).mean()
    expected = (df["close"] > sma).fillna(False)
    pd.testing.assert_series_equal(mask, expected, check_names=False)


def test_quality_score_range_and_components():
    df = _synthetic_ohlcv()
    comps = quality_components(df)
    assert set(comps) == {"constructive", "volume_ok", "atr_ok"}
    score = quality_score(df)
    assert score.min() >= 0
    assert score.max() <= 3
    gate = quality_gate(df, min_score=2)
    assert gate.dtype == bool or gate.dtype == np.bool_
    assert gate.equals(score >= 2)


def test_atr_ok_does_not_use_future_bars():
    """Expanding median for atr threshold is shift(1); flipping future rows
    must not change past quality decisions."""
    df = _synthetic_ohlcv(400)
    base = quality_components(df)["atr_ok"].copy()

    # Mutate the last 50 bars' ranges dramatically
    df2 = df.copy()
    df2.loc[df2.index[-50]:, "high"] = df2.loc[df2.index[-50]:, "high"] * 3.0
    df2.loc[df2.index[-50]:, "low"] = df2.loc[df2.index[-50]:, "low"] * 0.3
    mutated = quality_components(df2)["atr_ok"]

    # Past region (exclude last 50 and a small ATR warmup buffer) must match
    cutoff = -50 - 20
    pd.testing.assert_series_equal(
        base.iloc[:cutoff],
        mutated.iloc[:cutoff],
        check_names=False,
    )


def test_entry_only_gate_holds_through_quality_flicker():
    idx = pd.date_range("2024-01-01", periods=10, freq="h")
    # primary: enter bar 2, stay through bar 6
    primary = pd.Series([0, 0, 1, 1, 1, 1, 1, 0, 0, 0], index=idx, dtype=float)
    trend = pd.Series([True] * 10, index=idx)
    # quality fails on bar 4 (mid-trade) — should NOT force exit under entry-only
    quality = pd.Series([True, True, True, True, False, True, True, True, True, True], index=idx)
    close = pd.Series(np.linspace(100, 110, 10), index=idx)

    out = apply_entry_only_gates(primary, trend=trend, quality=quality, close=close)
    # In position from bar 2 through bar 6
    assert list(out.astype(int).values) == [0, 0, 1, 1, 1, 1, 1, 0, 0, 0]


def test_entry_blocked_when_quality_false_at_entry():
    idx = pd.date_range("2024-01-01", periods=6, freq="h")
    primary = pd.Series([0, 1, 1, 1, 0, 0], index=idx, dtype=float)
    trend = pd.Series(True, index=idx)
    quality = pd.Series([True, False, True, True, True, True], index=idx)
    close = pd.Series([100.0] * 6, index=idx)
    out = apply_entry_only_gates(primary, trend=trend, quality=quality, close=close)
    assert out.sum() == 0.0


def test_frozen_defaults_min_score_is_two():
    from gates import frozen_defaults

    d = frozen_defaults()
    assert d["quality"]["min_score"] == 2
    assert d["trend_filter"]["apply"] == "entry"
    assert d["train_window_end"] == "2025-08-01"
