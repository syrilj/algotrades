import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from institutional_flow.features import (
    absorption_score,
    compute_features,
    fractional_diff,
    ofi_proxy,
    schedule_deviation,
    vpa_confirmation,
    vpin_proxy,
)
from institutional_flow.impact import (
    cost_for_trade,
    impact_per_share,
    optimal_trajectory,
)


def _ohlcv(n=200, freq="h", seed=42, multi_day: bool = False, tz=None):
    if multi_day:
        # 7 trading hours per day, 5 days per week, 24h calendar
        idx = pd.date_range("2024-01-01 09:30", periods=n, freq="h")
    else:
        idx = pd.date_range("2024-01-01", periods=n, freq=freq, tz=tz)
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.normal(0, 0.002, n))
    high = close + np.abs(np.random.normal(0.05, 0.02, n))
    low = close - np.abs(np.random.normal(0.05, 0.02, n))
    open_ = close + np.random.normal(0, 0.01, n)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.random.poisson(1000, n) + 100,
        },
        index=idx,
    )


def test_compute_features_is_finite():
    df = _ohlcv(250)
    features = compute_features(df)
    assert np.isfinite(features.to_numpy(dtype=float, na_value=0.0)).all()
    assert features.shape[0] == len(df)
    assert "ofi" in features.columns
    assert "absorption" in features.columns
    assert "vpin" in features.columns
    assert "schedule_dev" in features.columns


def test_compute_features_with_tz_aware_and_integer_index():
    df = _ohlcv(100, tz=None)
    aware = df.copy()
    aware.index = aware.index.tz_localize("UTC")
    f1 = compute_features(aware)
    f2 = compute_features(df)
    # Timezone should be stripped, but values should be identical for identical bars
    pd.testing.assert_frame_equal(f1, f2, check_freq=False)

    # integer index (no datetime) should not raise
    df_int = df.reset_index(drop=True)
    f_int = compute_features(df_int)
    assert f_int.shape[0] == len(df_int)


def test_compute_features_is_causal():
    full = _ohlcv(200)
    prefix = full.iloc[:120]
    f_full = compute_features(full)
    f_prefix = compute_features(prefix)
    # Causal columns should be unchanged by future bars
    for col in ["ofi", "absorption", "vpin", "vol_z", "vpa_confirmation", "rsi", "return_lag1"]:
        # EMA/rolling may have tiny floating differences; use a tighter tolerance
        diff = (f_prefix[col] - f_full.loc[prefix.index, col]).abs().max()
        assert diff < 1e-10, f"{col} leaked future data: {diff}"


def test_absorption_score_handles_flat_price():
    df = _ohlcv(50)
    # Force a flat price for the lookback to exercise zero-price-change path
    df.loc[df.index[10:30], "close"] = df["close"].iloc[9]
    out = absorption_score(df, lookback=20)
    assert np.isfinite(out["absorption"]).all()
    assert not out["absorption"].isna().any()


def test_schedule_deviation_uses_prior_days_only():
    df = _ohlcv(500, multi_day=True)
    dev = schedule_deviation(df, lookback_days=30)
    # First day should have no expected schedule => filled to 0
    first_day = df.index[0].date()
    assert dev.loc[df.index.date == first_day].abs().max() == 0.0


def test_vpin_proxy_buckets_are_causal():
    df = _ohlcv(200)
    vpin = vpin_proxy(df, bucket_vol_frac=0.05, n_buckets=20)
    # Adding future bars should not change past vpin values
    vpin_full = vpin_proxy(df, bucket_vol_frac=0.05, n_buckets=20)
    vpin_prefix = vpin_proxy(df.iloc[:120], bucket_vol_frac=0.05, n_buckets=20)
    diff = (vpin_prefix - vpin_full.iloc[:120]).abs().max()
    assert diff < 1e-10


def test_ofi_proxy_obeys_candle_and_tick_rule():
    df = _ohlcv(50)
    # Strong up candle: close == high, open == low
    df.iloc[-1, df.columns.get_loc("open")] = df["low"].iloc[-1]
    df.iloc[-1, df.columns.get_loc("close")] = df["high"].iloc[-1]
    out = ofi_proxy(df)
    # buy fraction should be close to 1 for the last bar
    last_buy_frac = out["buy_vol"].iloc[-1] / df["volume"].iloc[-1]
    assert last_buy_frac > 0.75


def test_vpa_confirmation_positive_for_up_move_with_volume():
    df = _ohlcv(50)
    # Force a strong up move with above-average volume on the last bar
    avg_vol = df["volume"].iloc[-10:-1].mean()
    df.iloc[-1, df.columns.get_loc("volume")] = int(avg_vol * 3)
    df.iloc[-1, df.columns.get_loc("close")] = df["high"].iloc[-1]
    df.iloc[-1, df.columns.get_loc("open")] = df["low"].iloc[-1]
    out = vpa_confirmation(df)
    assert out["vpa_confirmation"].iloc[-1] > 0


def test_fractional_diff_is_causal():
    s = pd.Series(np.cumsum(np.random.randn(200)), index=pd.date_range("2024-01-01", periods=200, freq="h"))
    fd = fractional_diff(s, d=0.4, threshold=1e-3)
    prefix = s.iloc[:100]
    fd_prefix = fractional_diff(prefix, d=0.4, threshold=1e-3)
    # Past values should not change when future is appended
    assert (fd.iloc[:99].dropna() - fd_prefix.iloc[:99].dropna()).abs().max() < 1e-10


def test_impact_per_share_zero_inputs():
    assert impact_per_share(0, 100, 1e6, 0.02) == 0.0
    assert impact_per_share(1000, 0, 1e6, 0.02) == 0.0
    assert impact_per_share(1000, 100, 0, 0.02) == 0.0


def test_optimal_trajectory_liquidates_full_position():
    traj = optimal_trajectory(1000, 10, eta=0.1, sigma=0.02, lambda_=1.0)
    assert abs(traj[0] - 1000.0) < 1e-9
    assert abs(traj[-1]) < 1e-9
    assert all(traj[i] >= traj[i + 1] >= 0 for i in range(len(traj) - 1))


def test_cost_for_trade_returns_sensible_dict():
    df = _ohlcv(100)
    result = cost_for_trade(df, price=100, notional=10000, interval="1h")
    assert result["shares"] == 100.0
    assert result["total_cost"] >= 0.0
    assert result["adv"] > 0.0
    assert result["volatility"] > 0.0
