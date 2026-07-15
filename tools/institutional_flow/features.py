"""Causal, OHLCV-safe institutional-flow feature engineering.

This module is the first building block of the research pipeline.  Every
feature is computed only from information available at the close of the
*current* bar, with all rolling / cumulative / percentile logic using the
current bar plus the lookback of prior bars.  The caller (e.g. a backtest
runner) is responsible for shifting the output by one bar if it wants to
trade on the next open.

Leakage controls implemented throughout:
- All rolling means / standard deviations / EMAs use the current bar and
  prior bars only.
- Percentiles and quantiles are point-in-time (expanding or rolling with a
  shift so the current bar does not contribute to its own threshold).
- Signed-volume and tick-rule approximations use only the current bar's
  OHLCV and the immediately previous close.
- Volume-bucket VPIN is built and reset as volume accumulates; the bucket
  value is stamped only on the bar that fills the bucket.
- Intraday volume schedule uses a historical profile built from prior days
  only (`shift(1)` inside the groupby time transform).
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)


def _as_float_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return a column as float, with safe downcast."""
    s = df[col]
    if s.dtype.kind in "iu":
        s = s.astype(float)
    return s


def _sma(s: pd.Series, n: int) -> pd.Series:
    """Simple moving average with relaxed min-periods."""
    return s.rolling(n, min_periods=max(1, n // 2)).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    """Exponential moving average."""
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI via EMA."""
    delta = s.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = _ema(gain, n)
    avg_loss = _ema(loss, n)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR as a fraction of the close."""
    close = _as_float_series(df, "close")
    high = _as_float_series(df, "high")
    low = _as_float_series(df, "low")
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return (tr.ewm(span=n, adjust=False).mean() / close).replace(0, np.nan)


def _vwap(df: pd.DataFrame, n: int = 50) -> pd.Series:
    """Volume-weighted average price over a rolling window."""
    hlc3 = (_as_float_series(df, "high") + _as_float_series(df, "low") + _as_float_series(df, "close")) / 3.0
    vol = _as_float_series(df, "volume")
    num = (hlc3 * vol).rolling(n, min_periods=max(1, n // 2)).sum()
    den = vol.rolling(n, min_periods=max(1, n // 2)).sum()
    return num / den.replace(0, np.nan)


def _daily_volume(df: pd.DataFrame, lookback_days: int = 30) -> pd.Series:
    """Point-in-time ADV estimate: rolling median of completed daily volumes.

    The daily volume is known only after the close, so the series is
    forward-filled and then the rolling median is computed on the daily
    frequency and reindexed back to the bar index.
    """
    vol = _as_float_series(df, "volume")
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        _logger.warning("index is not DatetimeIndex; ADV estimate will be approximate")
        return _sma(vol, lookback_days * 24)

    daily = vol.resample("1D").sum()
    # shift(1): only completed days are used for the ADV estimate
    adv = daily.rolling(lookback_days, min_periods=1).median().shift(1)
    # reindex back to the bar index, forward-filling the last known daily ADV
    adv_bar = adv.reindex(idx, method="ffill")
    return adv_bar


def _intraday_profile(df: pd.DataFrame, lookback_days: int = 30) -> pd.Series:
    """Expected cumulative-volume fraction by time of day from prior days.

    The mean cumulative fraction for each bar's time-of-day is computed
    over the previous `lookback_days` days only (`shift(1)` prevents the
    current day from contributing to its own profile).
    """
    vol = _as_float_series(df, "volume")
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        _logger.warning("index is not DatetimeIndex; intraday profile disabled")
        return pd.Series(0.5, index=idx)

    time_key = idx.time
    day = idx.date
    frame = pd.DataFrame({"vol": vol, "time": time_key, "day": day}, index=idx)
    frame["cum_frac"] = frame.groupby("day")["vol"].cumsum() / frame.groupby("day")["vol"].transform("sum")
    # point-in-time: do not include the current day in the mean
    profile = frame.groupby("time")["cum_frac"].transform(
        lambda s: s.shift(1).rolling(lookback_days, min_periods=1).mean()
    )
    profile.index = idx
    return profile.fillna(0.5)


def ofi_proxy(df: pd.DataFrame, short_len: int = 20, long_len: int = 50) -> pd.DataFrame:
    """Order-flow imbalance proxy from OHLCV.

    Buy/sell volume is approximated by blending the candle-delta (close vs
    open) with the tick rule (close vs previous close).  The imbalance is
    then smoothed over short and long windows.

    Leakage audit: all inputs are from the current bar and the immediately
    preceding close.
    """
    open_ = _as_float_series(df, "open")
    high = _as_float_series(df, "high")
    low = _as_float_series(df, "low")
    close = _as_float_series(df, "close")
    vol = _as_float_series(df, "volume")

    rng = (high - low).replace(0, np.nan)
    candle_delta = ((close - open_) / rng).clip(-1.0, 1.0).fillna(0.0)

    price_change = close.diff().fillna(0.0)
    candle_sign = np.sign(candle_delta).where(np.sign(candle_delta) != 0, 1.0)
    tick_dir = np.sign(price_change).where(price_change != 0, candle_sign)

    # Blend candle delta and tick rule to estimate aggressive buy fraction
    buy_frac = ((candle_delta + 1.0) / 2.0 + (tick_dir + 1.0) / 2.0) / 2.0
    buy_frac = buy_frac.clip(0.0, 1.0)
    buy_vol = vol * buy_frac
    sell_vol = vol * (1.0 - buy_frac)

    tot_vol = (buy_vol + sell_vol).replace(0, np.nan)
    ofi = ((buy_vol - sell_vol) / tot_vol).fillna(0.0)
    ofi_short = _ema(ofi, short_len)
    ofi_long = _ema(ofi, long_len)
    ofi_persistence = ofi.rolling(short_len, min_periods=max(1, short_len // 2)).sum()

    return pd.DataFrame(
        {
            "ofi": ofi_short,
            "ofi_persistence": ofi_persistence,
            "ofi_long": ofi_long,
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
        },
        index=df.index,
    )


def absorption_score(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """Absorption / stealth footprint: large signed volume with limited price move.

    The raw score is |cumulative signed volume| over `lookback` bars divided
    by the absolute price change over the same span.  It is normalised by the
    rolling average volume and ATR so that it is comparable across symbols.

    Leakage audit: all values are current or lagged; normalisation uses
    rolling statistics on past data only.
    """
    close = _as_float_series(df, "close")
    high = _as_float_series(df, "high")
    low = _as_float_series(df, "low")
    open_ = _as_float_series(df, "open")
    vol = _as_float_series(df, "volume")
    atr_pct = _atr_pct(df, 14)

    signed_vol = vol * np.sign(close.diff().fillna(0.0))
    signed_vol_sum = signed_vol.rolling(lookback, min_periods=max(1, lookback // 2)).sum().abs()

    price_change = (close - close.shift(lookback)).abs().replace(0, np.nan)
    raw = signed_vol_sum / price_change

    vol_sma = _sma(vol, lookback).replace(0, np.nan)
    # normalise by prior volume average so the current bar does not inflate
    # its own denominator
    normalised = raw * (1.0 / vol_sma.shift(1)) * (atr_pct * 100.0)

    rng = (high - low).replace(0, np.nan)
    upper_wick = (high - np.maximum(close, open_)).fillna(0.0)
    lower_wick = (np.minimum(close, open_) - low).fillna(0.0)
    upper_wick_frac = (upper_wick / rng).fillna(0.0)
    lower_wick_frac = (lower_wick / rng).fillna(0.0)

    return pd.DataFrame(
        {
            "absorption": normalised.fillna(0.0).replace([np.inf, -np.inf], 0.0),
            "absorption_raw": raw.fillna(0.0).replace([np.inf, -np.inf], 0.0),
            "upper_wick_frac": upper_wick_frac,
            "lower_wick_frac": lower_wick_frac,
            "range_pct": (rng / close).fillna(0.0),
        },
        index=df.index,
    )


def schedule_deviation(df: pd.DataFrame, lookback_days: int = 30) -> pd.Series:
    """Deviation of cumulative intraday volume from the historical schedule.

    Positive values mean volume is running ahead of the historical profile at
    this time of day, consistent with an institutional slice being worked.

    Leakage audit: the historical profile and expected ADV are built from
    prior days only; today's cumulative volume is the current bar's cumulative
    sum.
    """
    vol = _as_float_series(df, "volume")
    exp_daily = _daily_volume(df, lookback_days)
    profile = _intraday_profile(df, lookback_days)
    expected_cum = (exp_daily * profile).replace(0, np.nan)

    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        day = idx.date
    else:
        day = idx
    cum_vol = pd.Series(vol, index=idx).groupby(day).cumsum()

    dev = ((cum_vol - expected_cum) / expected_cum).fillna(0.0)
    return dev


def vpin_proxy(df: pd.DataFrame, bucket_vol_frac: float = 0.05, n_buckets: int = 20) -> pd.Series:
    """Volume-bucketed order-flow toxicity proxy (bar-safe VPIN approximation).

    Volume is accumulated into buckets of size ~`bucket_vol_frac` of the recent
    ADV.  For each completed bucket the absolute imbalance / volume is stored,
    and the final series is a rolling mean over the last `n_buckets` bucket
    values.

    Leakage audit: bucket size is estimated from the recent ADV (past data
    only); each bucket is closed once its cumulative volume reaches the bucket
    size, and the value is stamped on the bar that fills the bucket.
    """
    open_ = _as_float_series(df, "open")
    close = _as_float_series(df, "close")
    vol = _as_float_series(df, "volume")

    price_change = close.diff().fillna(0.0)
    candle_sign = np.sign(close - open_).where(np.sign(close - open_) != 0, 1.0)
    tick_dir = np.sign(price_change).where(price_change != 0, candle_sign)
    buy_vol = vol * ((tick_dir + 1.0) / 2.0)
    sell_vol = vol - buy_vol
    imbalance = (buy_vol - sell_vol).abs()

    avg_vol = _sma(vol, 50)
    # bucket size is based on the prior average volume, not the current bar
    bucket_size = (avg_vol.shift(1) * bucket_vol_frac).fillna(0.0)

    n = len(df)
    out = np.zeros(n, dtype=float)
    bucket_abs = 0.0
    bucket_vol = 0.0
    for i in range(n):
        if bucket_size.iloc[i] <= 0:
            continue
        bucket_abs += float(imbalance.iloc[i])
        bucket_vol += float(vol.iloc[i])
        if bucket_vol >= bucket_size.iloc[i] and bucket_vol > 0:
            out[i] = bucket_abs / bucket_vol
            bucket_abs = 0.0
            bucket_vol = 0.0
        else:
            out[i] = out[i - 1] if i > 0 else 0.0

    s = pd.Series(out, index=df.index)
    return _sma(s, n_buckets).fillna(0.0)


def vpa_confirmation(df: pd.DataFrame, vol_look: int = 20) -> pd.DataFrame:
    """Volume-price agreement: volume surge and close location.

    Returns volume z-score, close location within the range, and a confirmation
    score that is positive when volume is high and the close is near the high
    (up move) or near the low (down move).
    """
    open_ = _as_float_series(df, "open")
    high = _as_float_series(df, "high")
    low = _as_float_series(df, "low")
    close = _as_float_series(df, "close")
    vol = _as_float_series(df, "volume")

    vol_ma = _sma(vol, vol_look)
    # compare current volume to the average of the prior bars (shift 1)
    vol_z = ((vol - vol_ma.shift(1)) / vol_ma.shift(1).replace(0, np.nan)).fillna(0.0)

    rng = (high - low).replace(0, np.nan)
    up_move = close > open_
    close_loc = np.where(
        up_move,
        (close - low) / rng,
        (high - close) / rng,
    )
    close_loc = pd.Series(close_loc, index=df.index).fillna(0.5)

    confirmation = vol_z * (close_loc - 0.5) * 2.0

    return pd.DataFrame(
        {
            "vol_z": vol_z,
            "close_loc": close_loc,
            "vpa_confirmation": confirmation,
        },
        index=df.index,
    )


def regime_features(df: pd.DataFrame, trend_len: int = 200, vol_len: int = 50) -> pd.DataFrame:
    """Trend, volatility, and distance-to-VWAP regime flags.

    Leakage audit: all inputs are current or lagged rolling values.
    """
    close = _as_float_series(df, "close")
    sma = _sma(close, trend_len)
    trend = (close > sma).astype(float)
    vwap = _vwap(df, 50)
    above_vwap = (close > vwap).astype(float)
    atr_pct = _atr_pct(df, 14)
    atr_pct_ma = _sma(atr_pct, vol_len)
    vol_regime = (atr_pct > atr_pct_ma).astype(float)
    rsi = _rsi(close, 14)
    return pd.DataFrame(
        {
            "trend": trend,
            "above_vwap": above_vwap,
            "vol_regime": vol_regime,
            "rsi": rsi,
            "dist_vwap_pct": (close - vwap) / close,
            "atr_pct": atr_pct,
        },
        index=df.index,
    )


def fractional_diff(series: pd.Series, d: float = 0.4, threshold: float = 1e-5) -> pd.Series:
    """Fractionally differentiate a price series to preserve memory while
    improving stationarity.

    Uses the binomial weight expansion and a causal convolution (only past
    values are used).  The first `width` observations are NaN because the
    weights need enough history.

    Reference: Marcos Lopez de Prado, "Advances in Financial Machine Learning".
    """
    if not 0.0 < d < 1.0:
        raise ValueError("d must be between 0 and 1")

    # compute weights w_k = (-1)^k * (d choose k)
    weights = [1.0]
    k = 1
    while True:
        w = -weights[-1] * (d - k + 1) / k
        if abs(w) < threshold:
            break
        weights.append(w)
        k += 1
        if k > 10_000:
            raise RuntimeError("fractional-diff weights did not converge")

    arr = series.to_numpy(dtype=float)
    n = len(arr)
    if n < len(weights):
        return pd.Series(np.nan, index=series.index)

    conv = np.convolve(arr, weights, mode="full")
    out = np.full(n, np.nan, dtype=float)
    width = len(weights) - 1
    out[width:] = conv[width:n]
    return pd.Series(out, index=series.index)


def compute_features(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Compute the full feature matrix for one symbol.

    All features are point-in-time and use only current or past bars.  The
    caller is responsible for aligning the signal with execution (e.g. shift
    by one bar to trade on the next open).

    Args:
        df: OHLCV DataFrame with a sorted index.
        params: optional parameter overrides.  Recognised keys:
            - ofi_short, ofi_long
            - absorption_lookback
            - vol_look
            - trend_len, vol_len
            - schedule_lookback
            - vpin_bucket_frac, vpin_n_buckets
            - fracdiff_d (if provided, adds fractional-diff of close)

    Returns:
        DataFrame with one row per input bar and one column per feature.
    """
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    df.index = idx

    p = params or {}
    ofi = ofi_proxy(df, p.get("ofi_short", 20), p.get("ofi_long", 50))
    absorption = absorption_score(df, p.get("absorption_lookback", 20))
    vpa = vpa_confirmation(df, p.get("vol_look", 20))
    regime = regime_features(df, p.get("trend_len", 200), p.get("vol_len", 50))
    schedule_dev = schedule_deviation(df, p.get("schedule_lookback", 30))
    vpin = vpin_proxy(df, p.get("vpin_bucket_frac", 0.05), p.get("vpin_n_buckets", 20))

    close = _as_float_series(df, "close")
    features = pd.DataFrame(
        {
            "ofi": ofi["ofi"],
            "ofi_persistence": ofi["ofi_persistence"],
            "ofi_long": ofi["ofi_long"],
            "absorption": absorption["absorption"],
            "absorption_raw": absorption["absorption_raw"],
            "upper_wick_frac": absorption["upper_wick_frac"],
            "lower_wick_frac": absorption["lower_wick_frac"],
            "range_pct": absorption["range_pct"],
            "schedule_dev": schedule_dev,
            "vpin": vpin,
            "vol_z": vpa["vol_z"],
            "close_loc": vpa["close_loc"],
            "vpa_confirmation": vpa["vpa_confirmation"],
            "trend": regime["trend"],
            "above_vwap": regime["above_vwap"],
            "vol_regime": regime["vol_regime"],
            "rsi": regime["rsi"],
            "dist_vwap_pct": regime["dist_vwap_pct"],
            "atr_pct": regime["atr_pct"],
            "return_lag1": close.pct_change(1).fillna(0.0),
            "return_lag4": close.pct_change(4).fillna(0.0),
            "return_lag24": close.pct_change(24).fillna(0.0),
            "hour": idx.hour.astype(float),
            "day_of_week": idx.dayofweek.astype(float),
        },
        index=df.index,
    )

    if "fracdiff_d" in p:
        features["fracdiff_close"] = fractional_diff(close, d=float(p["fracdiff_d"]))

    return features.fillna(0.0).replace([np.inf, -np.inf], 0.0)
