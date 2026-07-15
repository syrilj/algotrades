"""Small, point-in-time feature families for confidence research."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [str(c).lower() for c in out.columns]
    missing = {"open", "high", "low", "close", "volume"} - set(out.columns)
    if missing:
        raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
    return out.sort_index()


def confirmed_pivot_features(frame: pd.DataFrame, length: int = 10) -> pd.DataFrame:
    """Derive confirmed pivots using only bars available at each output row."""
    if length < 1:
        raise ValueError("length must be positive")
    df = _ohlcv(frame)
    low = df["low"].astype(float)
    high = df["high"].astype(float)
    low_center = low.shift(length)
    high_center = high.shift(length)
    low_window = low.rolling(2 * length + 1, min_periods=2 * length + 1).min()
    high_window = high.rolling(2 * length + 1, min_periods=2 * length + 1).max()
    pivot_low = low_center.notna() & np.isclose(low_center, low_window, equal_nan=False)
    pivot_high = high_center.notna() & np.isclose(high_center, high_window, equal_nan=False)
    result = pd.DataFrame(index=df.index)
    result["pivot_low_confirmed"] = pivot_low.astype(float)
    result["pivot_high_confirmed"] = pivot_high.astype(float)
    result["last_pivot_low"] = low_center.where(pivot_low).ffill()
    result["last_pivot_high"] = high_center.where(pivot_high).ffill()
    result["distance_last_pivot_low_atr"] = (df["close"] - result["last_pivot_low"]) / df["close"].rolling(14).std()
    result["distance_last_pivot_high_atr"] = (result["last_pivot_high"] - df["close"]) / df["close"].rolling(14).std()
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def ohlcv_effort_features(frame: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """Use volume effort and candle result without claiming true order flow."""
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    df = _ohlcv(frame)
    price_range = (df["high"] - df["low"]).replace(0.0, np.nan)
    body = (df["close"] - df["open"]).abs()
    close_location = ((df["close"] - df["low"]) / price_range).clip(0.0, 1.0)
    volume_mean = df["volume"].rolling(lookback, min_periods=lookback).mean()
    volume_std = df["volume"].rolling(lookback, min_periods=lookback).std()
    result = pd.DataFrame(index=df.index)
    result["volume_z"] = (df["volume"] - volume_mean) / volume_std.replace(0.0, np.nan)
    result["body_to_range"] = body / price_range
    result["close_location"] = close_location
    result["effort_result"] = result["volume_z"] * np.sign(df["close"] - df["open"])
    result["range_pct"] = price_range / df["close"].replace(0.0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


FEATURE_FAMILIES = {
    "confirmed_pivot": confirmed_pivot_features,
    "ohlcv_effort": ohlcv_effort_features,
}
