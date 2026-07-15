"""Leakage-free VPA + reflexivity feature engineering for v51.

All features are computable from information available at the bar close (or at
the next open). Rolling statistics use only past bars; no forward-looking
information is used. Cross-asset inputs (e.g. SPY) are aligned by timestamp.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


MIN_LOOKBACK = 20


def _rolling_linreg(x: np.ndarray, y: np.ndarray, window: int) -> tuple:
    """Vectorized slope and R^2 of y on x over a rolling window.

    x is assumed deterministic (e.g. 0..window-1).  Returns (slope, r2) arrays.
    """
    x = np.asarray(x, dtype=float)
    n = len(y)
    slope = np.full(n, np.nan)
    r2 = np.full(n, np.nan)
    x_mean = x.mean()
    x -= x_mean
    ssx = np.sum(x * x)
    for i in range(window, n + 1):
        yy = y[i - window : i]
        y_mean = yy.mean()
        sxy = np.sum(x * (yy - y_mean))
        if ssx != 0:
            b = sxy / ssx
            slope[i - 1] = b
            ss_res = np.sum((yy - y_mean - b * x) ** 2)
            ss_tot = np.sum((yy - y_mean) ** 2)
            if ss_tot > 1e-12:
                r2[i - 1] = 1.0 - ss_res / ss_tot
    return slope, r2


def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range, causal."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window, min_periods=window).mean()


def _adx(df: pd.DataFrame, window: int = 14, adx_smooth: int = 14) -> pd.Series:
    """Wilder's ADX, causal."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    up = high - high.shift(1)
    down = low.shift(1) - low
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = _atr(df, window=window)
    plus_di = 100 * plus_dm.rolling(window, min_periods=window).mean() / atr
    minus_di = 100 * minus_dm.rolling(window, min_periods=window).mean() / atr
    dx = (plus_di - minus_di).abs() / (plus_di + minus_dm).abs() * 100
    adx = dx.rolling(adx_smooth, min_periods=adx_smooth).mean()
    return adx


def compute_features(df: pd.DataFrame, spy_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Compute a leakage-free feature matrix for one symbol.

    Args:
        df: OHLCV DataFrame with DatetimeIndex for the symbol.
        spy_df: optional OHLCV DataFrame for SPY, used for market regime / breadth.

    Returns:
        DataFrame indexed like df with engineered columns.
    """
    df = df.copy()
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    hlc3 = (high + low + close) / 3.0

    out = pd.DataFrame(index=df.index)

    # ── Price / return features (stationary, comparable across symbols) ──
    log_ret = np.log(close / close.shift(1))
    for h in [1, 2, 3, 5, 10, 20]:
        out[f"ret_{h}"] = close / close.shift(h) - 1.0
    out["log_ret"] = log_ret

    # ── Volume Price Analysis (VPA) core ──
    vol_med = volume.rolling(20, min_periods=20).median()
    out["rel_volume"] = volume / vol_med
    vol_ma = volume.rolling(20, min_periods=20).mean()
    vol_std = volume.rolling(20, min_periods=20).std()
    out["vol_z"] = (volume - vol_ma) / vol_std.replace(0, np.nan)
    # Signed volume confirmation: volume surge aligned with price direction.
    out["volume_price_confirm"] = out["vol_z"] * np.sign(close - open_)
    # Divergence proxy: OBV slope vs price slope.
    obv = (np.sign(close.diff()) * volume).cumsum()
    out["obv_slope_5"] = (obv - obv.shift(5)) / close.replace(0, np.nan)
    out["obv_slope_20"] = (obv - obv.shift(20)) / close.replace(0, np.nan)

    # ── Candle / climax proxies ──
    candle_range = high - low
    body = (close - open_).abs()
    upper_wick = high - pd.concat([open_, close], axis=1).max(axis=1)
    lower_wick = pd.concat([open_, close], axis=1).min(axis=1) - low
    out["body_ratio"] = body / candle_range.replace(0, np.nan)
    out["upper_wick_ratio"] = upper_wick / candle_range.replace(0, np.nan)
    out["lower_wick_ratio"] = lower_wick / candle_range.replace(0, np.nan)
    # Formulaic exhaustion: high volume + small body + long wick
    out["climax_bull"] = (
        (out["vol_z"] > 2.0)
        & (out["lower_wick_ratio"] > 0.5)
        & (out["body_ratio"] < 0.5)
    ).astype(float)
    out["climax_bear"] = (
        (out["vol_z"] > 2.0)
        & (out["upper_wick_ratio"] > 0.5)
        & (out["body_ratio"] < 0.5)
    ).astype(float)

    # ── Anchored / rolling VWAP ──
    vwap_20 = (hlc3 * volume).rolling(20, min_periods=20).sum() / volume.rolling(
        20, min_periods=20
    ).sum()
    out["dist_vwap"] = (close - vwap_20) / _atr(df, 14)
    out["above_vwap"] = (close > vwap_20).astype(float)

    # ── Reflexivity / regime features (stationary) ──
    sma_20 = close.rolling(20, min_periods=20).mean()
    sma_50 = close.rolling(50, min_periods=50).mean()
    out["above_sma20"] = (close > sma_20).astype(float)
    out["above_sma50"] = (close > sma_50).astype(float)
    out["price_trend"] = close / sma_50 - 1.0

    slope_20, r2_20 = _rolling_linreg(
        np.arange(20, dtype=float), close.to_numpy(dtype=float), 20
    )
    out["trend_slope_pct"] = pd.Series(slope_20, index=df.index) / close
    out["trend_r2_20"] = pd.Series(r2_20, index=df.index)
    out["adx_14"] = _adx(df, 14, 14)
    # Trend strength × volume confirmation (positive feedback proxy)
    out["trend_vol_confirm"] = out["trend_r2_20"] * out["volume_price_confirm"]

    # Volatility regime
    vol_20 = log_ret.rolling(20, min_periods=20).std()
    vol_60 = log_ret.rolling(60, min_periods=60).std()
    out["volatility_20"] = vol_20
    out["volatility_ratio"] = vol_20 / vol_60
    out["volatility_pct"] = vol_20 / vol_20.rolling(60, min_periods=60).max()

    # Cross-asset / market breadth (SPY)
    if spy_df is not None and not spy_df.empty:
        spy_close = spy_df["close"].astype(float)
        spy_close = spy_close.reindex(df.index, method="ffill")
        out["spy_ret_5"] = spy_close / spy_close.shift(5) - 1.0
        out["spy_ret_10"] = spy_close / spy_close.shift(10) - 1.0
        out["spy_trend"] = (spy_close > spy_close.rolling(50, min_periods=50).mean()).astype(float)
        out["spy_above_sma20"] = (
            spy_close > spy_close.rolling(20, min_periods=20).mean()
        ).astype(float)
        out["relative_strength_20"] = out["ret_20"] - (spy_close / spy_close.shift(20) - 1.0)
    else:
        for c in ["spy_ret_5", "spy_ret_10", "spy_trend", "spy_above_sma20", "relative_strength_20"]:
            out[c] = 0.0

    # Calendar features
    out["hour"] = df.index.hour
    out["dayofweek"] = df.index.dayofweek
    out["month"] = df.index.month

    return out


def primary_events(features: pd.DataFrame) -> pd.Series:
    """Define candidate long-entry events from VPA + reflexivity rules.

    This is the "primary model" in the meta-labeling terminology.  It produces a
    boolean series that selects bars where volume confirms directional movement in
    a positive-feedback regime.  The secondary meta-labeler will filter these.
    """
    cond = pd.Series(True, index=features.index)
    # Strong volume confirmation: above-median volume and surge aligned with direction.
    cond &= features["rel_volume"].fillna(0) > 1.5
    cond &= features["volume_price_confirm"].fillna(0) > 1.0
    # Reflexivity / regime filters: in a positive-feedback trend with market support.
    cond &= features["above_vwap"].fillna(0) > 0
    cond &= features["above_sma50"].fillna(0) > 0
    cond &= features["spy_trend"].fillna(0) > 0
    cond &= features["climax_bear"].fillna(0) < 0.5
    cond &= features["volatility_pct"].fillna(0) < 0.9
    cond &= features["relative_strength_20"].fillna(0) > -0.05
    # Strong bullish candle: close well above open (body > half the range).
    cond &= features["body_ratio"].fillna(0) > 0.5
    return cond


def triple_barrier_labels(
    df: pd.DataFrame, events: pd.Series, profit_mult: float = 1.5, loss_mult: float = 1.0, max_hold: int = 20
) -> tuple:
    """Compute triple-barrier labels for candidate events.

    Returns:
        labels: pd.Series of {0,1, np.nan} aligned with df; NaN for non-events.
        touches: pd.Series of the first-touch bar (relative index) for diagnostics.
        returns: pd.Series of realized return at exit (for expectancy).
    """
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    atr = _atr(df, 14).to_numpy()
    n = len(df)
    labels = np.full(n, np.nan)
    touch_bars = np.full(n, np.nan)
    realized = np.full(n, np.nan)
    event_idx = np.where(events.to_numpy() & np.isfinite(close) & np.isfinite(atr))[0]
    for i in event_idx:
        if i >= n - 1:
            continue
        upper = close[i] + profit_mult * atr[i]
        lower = close[i] - loss_mult * atr[i]
        max_k = min(max_hold, n - i - 1)
        for k in range(1, max_k + 1):
            j = i + k
            if low[j] <= lower:
                labels[i] = 0.0
                touch_bars[i] = k
                realized[i] = (lower / close[i]) - 1.0
                break
            if high[j] >= upper:
                labels[i] = 1.0
                touch_bars[i] = k
                realized[i] = (upper / close[i]) - 1.0
                break
        else:
            # Time exit
            j = min(i + max_hold, n - 1)
            labels[i] = 1.0 if close[j] > close[i] else 0.0
            touch_bars[i] = max_hold if i + max_hold < n else n - i
            realized[i] = (close[j] / close[i]) - 1.0
    return (
        pd.Series(labels, index=df.index),
        pd.Series(touch_bars, index=df.index),
        pd.Series(realized, index=df.index),
    )
