from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "models" / "poc_va_macdha" / "v90_meta_confidence"
ENGINE_PATH = BUNDLE / "signal_engine.py"
FEATURES_PATH = BUNDLE / "features.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _rth_index(days: int = 120) -> pd.DatetimeIndex:
    rows: list[pd.Timestamp] = []
    for day in pd.bdate_range("2025-01-02", periods=days):
        rows.extend(day + pd.to_timedelta([9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5], unit="h"))
    return pd.DatetimeIndex(rows)


def _ohlcv(seed: int, days: int = 120) -> pd.DataFrame:
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


def test_features_are_prefix_invariant():
    """A feature at bar t must not change when future bars are appended."""
    feat = _load(FEATURES_PATH, "v90_features_test")
    df = _ohlcv(1)
    prefix_n = 400
    full = feat.build_features(df)
    prefix = feat.build_features(df.iloc[:prefix_n])
    pd.testing.assert_frame_equal(prefix, full.iloc[:prefix_n])


def test_engine_prefix_invariant_and_two_sided():
    module = _load(ENGINE_PATH, "v90_engine_test")
    engine = module.SignalEngine()
    frames = {"TSLA.US": _ohlcv(1), "SPY.US": _ohlcv(2)}
    prefix_n = 500
    prefix = {k: v.iloc[:prefix_n] for k, v in frames.items()}

    short = module.SignalEngine().generate(prefix)
    full = engine.generate(frames)
    # Signals emitted for the same historical bars must be identical.
    pd.testing.assert_series_equal(short["TSLA.US"], full["TSLA.US"].iloc[:prefix_n])

    # Confidence must be a valid probability in [0, 1].
    conf = engine.last_confidence["TSLA.US"]
    assert conf.min() >= 0.0 and conf.max() <= 1.0
    # Side series only ever takes the documented labels.
    sides = set(engine.last_side["TSLA.US"].unique())
    assert sides.issubset({"BUY", "SELL", "SELL_FLATTEN", "FLAT"})


def test_short_head_flattens_when_shorting_disabled():
    module = _load(ENGINE_PATH, "v90_engine_noshort")
    engine = module.SignalEngine()
    engine._allow_short = False
    out = engine.generate({"TSLA.US": _ohlcv(3)})
    # No negative (short) target weight may be emitted when shorting is off.
    assert (out["TSLA.US"] >= 0.0).all()


def test_fail_closed_without_artifacts(tmp_path):
    """If the boosters cannot load, the engine must return FLAT, never a guess."""
    module = _load(ENGINE_PATH, "v90_engine_failclosed")
    engine = module.SignalEngine()
    engine._ready = False  # simulate missing artifacts
    out = engine.generate({"TSLA.US": _ohlcv(4)})
    assert (out["TSLA.US"] == 0.0).all()
    assert (engine.last_side["TSLA.US"] == "FLAT").all()
