"""Unit tests for causal drawdown/risk sensors and hard/soft sizing.

Drives the shipped helpers in models/poc_va_macdha/_shared/drawdown_risk.py
(and the v72 SignalEngine sizing path) without a multi-year backtest.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "models" / "poc_va_macdha" / "_shared" / "drawdown_risk.py"


def _load_drawdown_risk():
    name = f"drawdown_risk_under_test_{id(SHARED)}"
    spec = importlib.util.spec_from_file_location(name, SHARED)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


dr = _load_drawdown_risk()


def _ohlcv_from_close(close: np.ndarray, start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(close), freq="h")
    close = np.asarray(close, dtype=float)
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * 1.001
    low = np.minimum(open_, close) * 0.999
    volume = np.full(len(close), 1e6)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _calm_series(n: int = 400) -> pd.DataFrame:
    """Gentle uptrend with low vol — should not elevate risk."""
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0003, 0.0015, size=n)
    close = 100 * np.cumprod(1.0 + rets)
    return _ohlcv_from_close(close)


def _crash_series(n: int = 400) -> pd.DataFrame:
    """Calm then sharp multi-day crash — risk should elevate into the dump."""
    rng = np.random.default_rng(1)
    rets = rng.normal(0.0002, 0.0012, size=n)
    # Inject a ~12% crash over ~30 bars near the end
    crash_start = n - 80
    rets[crash_start : crash_start + 30] = -0.0045
    close = 100 * np.cumprod(1.0 + rets)
    return _ohlcv_from_close(close)


def test_drawdown_from_peak_non_positive_and_causal():
    px = pd.Series([100.0, 110.0, 105.0, 99.0, 101.0])
    dd = dr.drawdown_from_peak(px)
    assert (dd <= 1e-12).all()
    assert dd.iloc[1] == pytest.approx(0.0)
    assert dd.iloc[3] == pytest.approx(99 / 110 - 1.0)


def test_vol_ratio_uses_lagged_returns_no_future_leak():
    df = _calm_series(300)
    base = dr.vol_ratio(df).copy()
    df2 = df.copy()
    # Mutate only the last 40 bars
    df2.iloc[-40:, df2.columns.get_loc("close")] = df2.iloc[-40:]["close"].values * 1.5
    mutated = dr.vol_ratio(df2)
    # Early region must be identical (causality)
    cutoff = -40 - 25
    pd.testing.assert_series_equal(
        base.iloc[:cutoff],
        mutated.iloc[:cutoff],
        check_names=False,
    )


def test_elevated_crash_risk_higher_than_calm():
    calm = _calm_series()
    crash = _crash_series()
    calm_score = dr.composite_risk_score(calm)
    crash_score = dr.composite_risk_score(crash)
    # Tail of crash series should be clearly elevated
    assert float(crash_score.iloc[-20:].mean()) > float(calm_score.iloc[-20:].mean()) + 0.15
    assert float(crash_score.iloc[-10:].max()) >= 0.45


def test_hard_size_mult_stands_aside_when_elevated():
    score = pd.Series([0.1, 0.2, 0.6, 0.9, 0.3])
    mult = dr.size_multiplier(score, mode="hard", elevated_threshold=0.55, size_floor=0.0)
    assert list(mult.values) == [1.0, 1.0, 0.0, 0.0, 1.0]


def test_soft_size_mult_shrinks_but_can_remain_nonzero():
    score = pd.Series([0.0, 0.5, 1.0])
    mult = dr.size_multiplier(
        score, mode="soft", size_floor=0.15, soft_power=1.0
    )
    assert mult.iloc[0] == pytest.approx(1.0)
    assert mult.iloc[1] == pytest.approx(0.15 + 0.85 * 0.5)
    assert mult.iloc[2] == pytest.approx(0.15)
    assert (mult > 0).all()


def test_apply_size_mult_zeros_targets_when_hard_risk_off():
    idx = pd.date_range("2024-01-01", periods=5, freq="h")
    sigs = {"AAA.US": pd.Series([0.0, 1.0, 1.0, 0.8, 0.0], index=idx)}
    mult = pd.Series([1.0, 1.0, 0.0, 0.0, 1.0], index=idx)
    out = dr.apply_size_mult(sigs, mult)
    assert list(out["AAA.US"].values) == [0.0, 1.0, 0.0, 0.0, 0.0]


def test_v72_hard_engine_stands_aside_on_synthetic_crash():
    """End-to-end: shipped v72 SignalEngine zeros teacher size under crash risk."""
    eng_path = ROOT / "models" / "poc_va_macdha" / "v72_trump_risk_hard" / "signal_engine.py"
    mod = _load_module_path(eng_path, "v72_hard_engine_test")

    class _StubTeacher:
        def generate(self, data_map):
            out = {}
            for code, df in data_map.items():
                out[code] = pd.Series(1.0, index=df.index)  # always full long
            return out

    engine = mod.SignalEngine.__new__(mod.SignalEngine)
    engine._risk = dr
    engine._params = dr.default_params("hard")
    engine._teacher = _StubTeacher()
    engine.last_risk_score = None
    engine.last_size_mult = None

    crash = _crash_series(350)
    calm = _calm_series(350)
    # Market map: SPY = crash path drives risk; signal code rides teacher=1
    data_crash = {"SPY.US": crash, "QQQ.US": crash, "TSLA.US": crash}
    data_calm = {"SPY.US": calm, "QQQ.US": calm, "TSLA.US": calm}

    out_crash = engine.generate(data_crash)
    out_calm = engine.generate(data_calm)

    # Elevated tail → near-zero target; calm tail → full teacher size
    assert float(out_crash["TSLA.US"].iloc[-15:].mean()) < 0.35
    assert float(out_calm["TSLA.US"].iloc[-15:].mean()) > 0.7


def _load_module_path(path: Path, key: str):
    name = f"{key}_{id(path)}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_rolling_corr_is_bounded():
    a = _calm_series(200)
    b = a.copy()
    b["close"] = a["close"].values * 1.01 + np.linspace(0, 1, len(a))
    c = dr.rolling_corr(a, b, window=20)
    valid = c.dropna()
    assert len(valid) > 0
    assert valid.min() >= -1.0 - 1e-9
    assert valid.max() <= 1.0 + 1e-9
