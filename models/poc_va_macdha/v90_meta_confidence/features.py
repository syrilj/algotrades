"""Causal feature builder for v90_meta_confidence.

Every feature at bar ``t`` is computed only from data available at or before the
close of bar ``t`` (no look-ahead). The same function is used by the offline
trainer (``tools/train_v90_meta_confidence.py``) and by the live
``signal_engine.py`` so training and runtime see identical inputs.

Returns a float feature matrix aligned to ``df.index``. Rows with warm-up NaNs
are left as NaN and dropped by the caller.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

# Ordered, frozen feature list — the runtime engine relies on this exact order.
FEATURES: List[str] = [
    "ret_1",
    "ret_3",
    "ret_6",
    "ret_12",
    "rsi_14",
    "rsi_depth",
    "macd_hist",
    "macd_hist_slope",
    "atr_pct",
    "atr_ratio",
    "vol_z",
    "ema_bull",
    "ema_bear",
    "cloud_dist",
    "above_sma200",
    "sma_slope",
    "rvol_20",
    "dist_hi_20",
    "dist_lo_20",
    "hour",
]


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    roll_up = up.ewm(alpha=1.0 / n, adjust=False).mean()
    roll_down = down.ewm(alpha=1.0 / n, adjust=False).mean()
    rs = roll_up / roll_down.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time feature matrix for one symbol."""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    out = pd.DataFrame(index=df.index)

    out["ret_1"] = close.pct_change(1)
    out["ret_3"] = close.pct_change(3)
    out["ret_6"] = close.pct_change(6)
    out["ret_12"] = close.pct_change(12)

    rsi = _rsi(close, 14)
    out["rsi_14"] = rsi / 100.0
    out["rsi_depth"] = ((50.0 - rsi) / 50.0).clip(-1.0, 1.0)

    macd = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd, 9)
    hist = (macd - signal) / close.replace(0.0, np.nan)
    out["macd_hist"] = hist
    out["macd_hist_slope"] = hist.diff(1)

    atr = _atr(df, 14)
    atr_pct = atr / close.replace(0.0, np.nan)
    out["atr_pct"] = atr_pct
    atr_med = atr_pct.shift(1).rolling(100, min_periods=20).median()
    out["atr_ratio"] = atr_pct / atr_med.replace(0.0, np.nan)

    vsma = volume.rolling(20, min_periods=8).mean()
    vstd = volume.rolling(20, min_periods=8).std().replace(0.0, np.nan)
    out["vol_z"] = ((volume - vsma) / vstd).clip(-4.0, 4.0)

    e_fast, e_mid, e_slow = _ema(close, 9), _ema(close, 21), _ema(close, 55)
    out["ema_bull"] = ((e_fast > e_mid) & (e_mid > e_slow)).astype(float)
    out["ema_bear"] = ((e_fast < e_mid) & (e_mid < e_slow)).astype(float)
    cloud_mid = (pd.concat([e_fast, e_mid, e_slow], axis=1).max(axis=1)
                 + pd.concat([e_fast, e_mid, e_slow], axis=1).min(axis=1)) / 2.0
    out["cloud_dist"] = ((close - cloud_mid) / close.replace(0.0, np.nan)).clip(-0.25, 0.25)

    sma200 = close.rolling(200, min_periods=50).mean()
    out["above_sma200"] = (close > sma200).astype(float)
    out["sma_slope"] = sma200.pct_change(20)

    logret = np.log(close / close.shift(1))
    out["rvol_20"] = logret.rolling(20, min_periods=10).std()

    hi20 = high.rolling(20, min_periods=10).max()
    lo20 = low.rolling(20, min_periods=10).min()
    out["dist_hi_20"] = ((hi20 - close) / close.replace(0.0, np.nan)).clip(0.0, 0.5)
    out["dist_lo_20"] = ((close - lo20) / close.replace(0.0, np.nan)).clip(0.0, 0.5)

    idx = pd.to_datetime(df.index)
    out["hour"] = pd.Series(idx.hour + idx.minute / 60.0, index=df.index).astype(float)

    out = out.replace([np.inf, -np.inf], np.nan)
    return out[FEATURES]
