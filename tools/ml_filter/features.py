"""Causal per-bar features for the XGB trade filter.

Every column at bar ``t`` is computed from data up to and including ``t``.
Entries generated at bar ``t`` fill at the open of ``t+1`` (the engine's own
fill convention), so bar-``t`` features carry no lookahead relative to the
fill. Truncation invariance (features at ``t`` unchanged when future bars are
removed) is covered by tests/test_ml_filter.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

UNIVERSE = ["TSLA", "MU", "SPY", "IONQ", "APLD", "XLP", "QQQ"]

BASE_FEATURES = [
    "ret_5",
    "ret_20",
    "atr_pct",
    "rvol_20",
    "macd_hist_atr",
    "macd_hist_slope_atr",
    "dist_ema22_atr",
    "dist_ema50_atr",     # New
    "dist_ema100_atr",    # New
    "dist_ema200_atr",
    "dist_hh20_atr",
    "dist_vwap_atr",
    "rsi_14",             # New
    "bb_width",           # New
    "body_atr",           # New
    "upper_wick_atr",     # New
    "lower_wick_atr",     # New
    "engine_conf",
    "sleeve",
    "spy_regime",
]

FEATURE_COLUMNS = BASE_FEATURES + [f"sym_{s}" for s in UNIVERSE]


def _atr(frame: pd.DataFrame, span: int = 14) -> pd.Series:
    high, low, close = frame["high"], frame["low"], frame["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_feature_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    engine_conf: pd.Series | None = None,
    sleeve: pd.Series | None = None,
    spy_close: pd.Series | None = None,
) -> pd.DataFrame:
    """Feature matrix aligned to ``frame.index`` (lower-case ohlcv columns).

    ``engine_conf``/``sleeve`` are the v72 engine's published per-bar series
    (reindexed; missing values become 0). ``spy_close`` supplies the market
    regime flag; when absent the flag is a neutral 0.5 so the model can learn
    to ignore it rather than being fed a fake bull/bear call.
    """
    close = frame["close"].astype(float)
    volume = frame["volume"].astype(float) if "volume" in frame.columns else pd.Series(0.0, index=frame.index)
    atr = _atr(frame)
    atr_safe = atr.replace(0.0, np.nan)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    ema22 = close.ewm(span=22, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema100 = close.ewm(span=100, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    hh20 = frame["high"].rolling(20, min_periods=5).max()

    typical = (frame["high"] + frame["low"] + close) / 3.0
    vol_for_vwap = volume.replace(0.0, np.nan)
    rolling_pv = (typical * vol_for_vwap).rolling(35, min_periods=10).sum()
    rolling_v = vol_for_vwap.rolling(35, min_periods=10).sum()
    vwap = rolling_pv / rolling_v

    # Bollinger Bands
    sma20 = close.rolling(20, min_periods=5).mean()
    std20 = close.rolling(20, min_periods=5).std()

    out = pd.DataFrame(index=frame.index)
    out["ret_5"] = close.pct_change(5)
    out["ret_20"] = close.pct_change(20)
    out["atr_pct"] = atr / close
    vol_sma = volume.rolling(20, min_periods=5).mean().replace(0.0, np.nan)
    out["rvol_20"] = volume / vol_sma
    out["macd_hist_atr"] = macd_hist / atr_safe
    out["macd_hist_slope_atr"] = macd_hist.diff(3) / atr_safe
    out["dist_ema22_atr"] = (close - ema22) / atr_safe
    out["dist_ema50_atr"] = (close - ema50) / atr_safe
    out["dist_ema100_atr"] = (close - ema100) / atr_safe
    out["dist_ema200_atr"] = (close - ema200) / atr_safe
    out["dist_hh20_atr"] = (hh20 - close) / atr_safe
    out["dist_vwap_atr"] = (close - vwap) / atr_safe
    
    out["rsi_14"] = _rsi(close, 14)
    out["bb_width"] = (4 * std20) / sma20.replace(0.0, np.nan)
    
    out["body_atr"] = (close - frame["open"]) / atr_safe
    out["upper_wick_atr"] = (frame["high"] - close.combine(frame["open"], max)) / atr_safe
    out["lower_wick_atr"] = (close.combine(frame["open"], min) - frame["low"]) / atr_safe

    out["engine_conf"] = (
        engine_conf.reindex(frame.index).astype(float).fillna(0.0)
        if engine_conf is not None
        else 0.0
    )
    out["sleeve"] = (
        sleeve.reindex(frame.index).astype(float).fillna(0.0) if sleeve is not None else 0.0
    )

    if spy_close is not None and len(spy_close) > 0:
        spy = spy_close.astype(float).sort_index()
        spy_ema50 = spy.ewm(span=50, adjust=False).mean()
        regime = (spy > spy_ema50).astype(float)
        # Align to this symbol's bars without leaking future SPY bars.
        out["spy_regime"] = regime.reindex(frame.index, method="ffill").fillna(0.5)
    else:
        out["spy_regime"] = 0.5

    bare = str(symbol).upper().replace(".US", "")
    for name in UNIVERSE:
        out[f"sym_{name}"] = 1.0 if name == bare else 0.0

    return out[FEATURE_COLUMNS]
