import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.macro_features import (
    MacroCrossAssetEngine,
    align_cross_asset_bars,
    estimate_d,
    fracdiff_series,
    macro_event_features,
    macro_feature_matrix,
    parse_macro_calendar,
    rolling_betas,
    rolling_correlations,
)


def _ohlcv(n=200, freq="h", seed=42):
    idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC")
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.normal(0, 0.001, n))
    return pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.10,
            "low": close - 0.10,
            "close": close,
            "volume": 1000 + np.random.poisson(50, n),
        },
        index=idx,
    )


def _macro_events(n=10, tz="UTC"):
    releases = pd.date_range("2024-01-02", periods=n, freq="7D", tz=tz)
    return pd.DataFrame(
        {
            "release_ts": releases,
            "event_type": np.tile(["CPI", "FOMC", "NFP"], n // 3 + 1)[:n],
            "actual": np.random.randn(n),
            "expected": np.random.randn(n),
        }
    )


def test_fracdiff_series_is_causal_and_finite():
    # Use a relaxed truncation threshold so the test data is long enough to
    # produce non-NaN values without requiring thousands of historical bars.
    frame = _ohlcv(200)
    fd = fracdiff_series(frame["close"], d=0.4, threshold=1e-3)
    assert np.isfinite(fd.dropna()).all()
    # Causality: value at t should not change when future bars are appended
    prefix = frame.iloc[:80]
    before = fracdiff_series(prefix["close"], d=0.4, threshold=1e-3).iloc[-1]
    after = fracdiff_series(frame["close"], d=0.4, threshold=1e-3).iloc[79]
    assert abs(before - after) < 1e-10


def test_estimate_d_hurst_is_between_zero_and_one():
    # Generate long-memory series: fractional noise d=0.4
    n = 500
    x = np.random.randn(n)
    d = estimate_d(pd.Series(x), method="hurst")
    assert 0.0 <= d < 1.0


def test_parse_macro_calendar_standardizes_surprises():
    events = _macro_events(20)
    parsed = parse_macro_calendar(events)
    assert "surprise" in parsed.columns
    assert "surprise_stdized" in parsed.columns
    assert parsed["surprise_stdized"].iloc[:5].isna().all()  # first estimates expanding
    # With 3 event types cycled, the 6th occurrence of each type is the first
    # to have 5 prior observations; the 20-row calendar hits that around row 15.
    assert parsed["surprise_stdized"].iloc[15:].notna().all()


def test_macro_event_features_do_not_leak_future_releases():
    idx = pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC")
    events = _macro_events(5)
    features = macro_event_features(idx, events)
    before_first = features.loc[: events["release_ts"].iloc[0] - pd.Timedelta("1h")]
    assert before_first["macro_cpi_surprise_lag"].isna().all()
    # After first release, the latest known surprise should be available
    after_first = features.loc[events["release_ts"].iloc[0] :]
    assert after_first["macro_cpi_surprise_lag"].notna().any()


def test_rolling_betas_and_correlations_are_finite_and_lagged():
    df = _ohlcv(200)
    df["spy_close"] = df["close"] + np.random.normal(0, 0.01, len(df))
    betas = rolling_betas(df, "close", "spy_close", windows=[20, 50])
    corrs = rolling_correlations(df, "close", "spy_close", windows=[20, 50])
    assert np.isfinite(betas.to_numpy(dtype=float, na_value=0.0)).all()
    assert np.isfinite(corrs.to_numpy(dtype=float, na_value=0.0)).all()
    # First min_periods rows (plus the lag) should be NaN
    assert betas.iloc[:5].isna().all().all()


def test_align_cross_asset_bars_is_backward_only():
    target = _ohlcv(50)
    spy = _ohlcv(50).rename(columns=lambda c: c if c == "close" else "x")
    # Create a spy close that changes on the last bar to see if target sees it early
    spy["close"] = 0.0
    spy.iloc[-1, spy.columns.get_loc("close")] = 999.0
    aligned = align_cross_asset_bars(target, spy_df=spy)
    # The target should never see the spy close from the last bar before that bar
    assert aligned["spy_close"].iloc[-1] == 999.0
    assert aligned["spy_close"].iloc[-2] != 999.0


def test_macro_feature_matrix_is_finite():
    target = _ohlcv(200)
    spy = _ohlcv(200)
    tlt = _ohlcv(200)
    vix = _ohlcv(200)
    events = _macro_events(10)
    features = macro_feature_matrix(
        target,
        spy_df=spy,
        tlt_df=tlt,
        vix_df=vix,
        events_df=events,
        cfg={"beta_windows": (20, 50), "corr_windows": (20, 50), "regime_lookback": 20},
    )
    assert np.isfinite(features.to_numpy(dtype=float, na_value=0.0)).all()
    assert "risk_on_score" in features.columns
    assert "macro_cpi_surprise_lag" in features.columns
    assert any("_fd" in c for c in features.columns)


def test_macro_cross_asset_engine_fit_transform():
    train = _ohlcv(200)
    test = _ohlcv(100)
    engine = MacroCrossAssetEngine(cfg={"fd_cols": ["close"]})
    engine.fit(train)
    out = engine.transform(test)
    assert np.isfinite(out.to_numpy(dtype=float, na_value=0.0)).all()
    assert "close_fd" in "".join(out.columns)


def test_macro_event_features_use_backward_only_surprise():
    idx = pd.date_range("2024-01-01 00:00", periods=10, freq="h", tz="UTC")
    events = pd.DataFrame(
        {
            "release_ts": pd.to_datetime(["2024-01-01 03:00"], utc=True),
            "event_type": ["CPI"],
            "actual": [3.0],
            "expected": [2.5],
        }
    )
    events = parse_macro_calendar(events)
    features = macro_event_features(idx, events)
    assert pd.isna(features.loc["2024-01-01 02:00", "macro_cpi_surprise_lag"])
    assert pd.notna(features.loc["2024-01-01 03:00", "macro_cpi_surprise_lag"])
    assert pd.notna(features.loc["2024-01-01 04:00", "macro_cpi_surprise_lag"])
