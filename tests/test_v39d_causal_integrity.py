from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "models" / "poc_va_macdha" / "v39d_confluence" / "signal_engine.py"


def _module():
    spec = importlib.util.spec_from_file_location("v39d_causal_integrity", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _rth_index(days: int = 90) -> pd.DatetimeIndex:
    rows: list[pd.Timestamp] = []
    for day in pd.bdate_range("2025-01-02", periods=days):
        rows.extend(day + pd.to_timedelta([9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5], unit="h"))
    return pd.DatetimeIndex(rows)


def _ohlcv(seed: int, days: int = 90) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = _rth_index(days)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.009, len(index))))
    open_ = np.r_[close[0], close[:-1]] * (1.0 + rng.normal(0.0, 0.001, len(index)))
    spread = np.maximum(close, open_) * rng.uniform(0.001, 0.008, len(index))
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.integers(100_000, 2_000_000, len(index)).astype(float),
        },
        index=index,
    )


class _LedgerStub:
    def record_entry(self, **_kwargs):
        return None

    def record_exit(self, **_kwargs):
        return None

    def flush(self):
        return None


def _engine(module):
    engine = module.SignalEngine()
    engine._ledger = _LedgerStub()
    return engine


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "TSLA.US": _ohlcv(1),
        "SPY.US": _ohlcv(2),
        "QQQ.US": _ohlcv(3),
        "XLP.US": _ohlcv(4),
    }


def test_relative_strength_is_prefix_invariant():
    module = _module()
    frames = _frames()
    index = frames["TSLA.US"].index
    prefix_n = 420
    before = module._qqq_rs_score(
        {key: value.iloc[:prefix_n] for key, value in frames.items()}, index[:prefix_n]
    )
    after = module._qqq_rs_score(frames, index)
    pd.testing.assert_series_equal(before, after.iloc[:prefix_n])


def test_generate_is_prefix_invariant_and_symbol_order_independent():
    module = _module()
    frames = _frames()
    prefix_n = 420
    prefix = {key: value.iloc[:prefix_n] for key, value in frames.items()}

    short = _engine(module).generate(prefix)
    full = _engine(module).generate(frames)
    pd.testing.assert_series_equal(short["TSLA.US"], full["TSLA.US"].iloc[:prefix_n])

    reversed_frames = dict(reversed(list(frames.items())))
    reversed_out = _engine(module).generate(reversed_frames)
    for code in frames:
        pd.testing.assert_series_equal(full[code], reversed_out[code])

