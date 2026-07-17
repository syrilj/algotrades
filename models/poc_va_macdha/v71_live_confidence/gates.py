"""Causal confidence gates for v71_live_confidence.

Design goals
------------
- High *live* confidence: every entry has an explicit [0,1] confidence score.
- High win rate without v70-style trade starvation.
- No look-ahead: rolling windows end at the finished bar; expanding ATR median
  is shifted by 1 so the current bar never enters its own threshold.

Soft-size philosophy (vs hard quality gates)
--------------------------------------------
Hard min_score=2 (v70) raised full-window WR to ~91% but cut trades below
auditor floors on holdout. v71 keeps entries when min_score is met (default 1)
and *scales size* by confidence so weak setups shrink instead of vanishing.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1.0 / length, adjust=False).mean()


def trend_mask(
    close: pd.Series,
    *,
    lookback: int = 250,
    direction: str = "above",
) -> pd.Series:
    price = close.astype(float)
    sma = price.rolling(lookback, min_periods=max(1, lookback // 2)).mean()
    direction = direction.lower()
    if direction == "above":
        return (price > sma).fillna(False)
    if direction == "below":
        return (price < sma).fillna(False)
    return pd.Series(True, index=close.index)


def quality_components(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """Point-in-time quality bits used by the confidence score.

    - constructive: finished bar not pure sell (close >= open)
    - volume_ok: volume >= 0.85 * 20-bar average
    - atr_ok: atr% <= 1.35 * expanding median of *prior* atr%
    """
    close = df["close"].astype(float)
    opening = df["open"].astype(float)
    volume = df["volume"].astype(float)

    constructive = (close >= opening).fillna(False)

    vol_ma = volume.rolling(20, min_periods=8).mean()
    volume_ok = (volume >= 0.85 * vol_ma).fillna(False)

    atr14 = atr(df, 14)
    atr_pct = atr14 / close.replace(0.0, np.nan)
    atr_med = atr_pct.shift(1).expanding(min_periods=20).median()
    atr_ok = (atr_pct <= 1.35 * atr_med).fillna(False)

    return {
        "constructive": constructive,
        "volume_ok": volume_ok,
        "atr_ok": atr_ok,
    }


def quality_score(df: pd.DataFrame) -> pd.Series:
    comps = quality_components(df)
    score = sum(c.astype(int) for c in comps.values())
    return score.astype(int).rename("quality_score")


def quality_confidence(df: pd.DataFrame) -> pd.Series:
    """Map quality score {0,1,2,3} → continuous confidence in [0, 1]."""
    return (quality_score(df).astype(float) / 3.0).clip(0.0, 1.0).rename("quality_conf")


def rsi_depth_confidence(
    df: pd.DataFrame,
    *,
    length: int = 14,
    os_value: float = 20.0,
) -> pd.Series:
    """Higher confidence when Ultimate-RSI-like oscillator is deeper oversold.

    Uses a lightweight RMA RSI on close (not full Ultimate RSI) as a causal
    proxy for setup extremity. Output in [0.4, 1.0] so weak oversold still
    trades but deep oversold gets full size.
    """
    close = df["close"].astype(float)
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    roll_up = up.ewm(alpha=1.0 / length, adjust=False).mean()
    roll_down = down.ewm(alpha=1.0 / length, adjust=False).mean()
    rs = roll_up / roll_down.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # depth: how far below oversold threshold (0 at os_value, 1 at 0)
    depth = ((float(os_value) - rsi) / max(float(os_value), 1.0)).clip(0.0, 1.0)
    conf = (0.4 + 0.6 * depth).clip(0.4, 1.0)
    return conf.fillna(0.5).rename("rsi_depth_conf")


def blend_confidence(
    quality_conf: pd.Series,
    rsi_conf: Optional[pd.Series] = None,
    *,
    quality_weight: float = 0.65,
    rsi_weight: float = 0.35,
) -> pd.Series:
    q = quality_conf.astype(float).clip(0.0, 1.0)
    if rsi_conf is None:
        return q.rename("confidence")
    r = rsi_conf.reindex(q.index).astype(float).clip(0.0, 1.0).fillna(0.5)
    wq = max(0.0, float(quality_weight))
    wr = max(0.0, float(rsi_weight))
    total = wq + wr
    if total <= 0:
        return q.rename("confidence")
    return ((wq * q + wr * r) / total).clip(0.0, 1.0).rename("confidence")


def size_from_confidence(
    confidence: pd.Series,
    *,
    base_scale: float = 0.225,
    min_scale_frac: float = 0.45,
    max_scale_frac: float = 1.0,
) -> pd.Series:
    """Map confidence → position scale.

    size = base_scale * (min_frac + (max_frac - min_frac) * confidence)
    At conf=0 → base * min_frac; at conf=1 → base * max_frac.
    """
    c = confidence.astype(float).clip(0.0, 1.0)
    lo = float(min_scale_frac)
    hi = float(max_scale_frac)
    mult = lo + (hi - lo) * c
    return (float(base_scale) * mult).rename("size")


def apply_entry_only_soft(
    primary: pd.Series,
    *,
    trend: Optional[pd.Series] = None,
    quality_ok: Optional[pd.Series] = None,
    confidence: Optional[pd.Series] = None,
    agree_boost: Optional[pd.Series] = None,
    close: Optional[pd.Series] = None,
    stop_loss_pct: float = 0.0,
    continuous_trend: bool = False,
    base_scale: float = 0.225,
    min_scale_frac: float = 0.45,
    max_scale_frac: float = 1.0,
    agree_boost_mult: float = 1.15,
    max_scale_cap: float = 0.35,
) -> Tuple[pd.Series, pd.Series]:
    """Entry-only state machine with soft confidence sizing.

    Returns (signal_size, entry_confidence).
    - New long only if primary crosses into long AND trend AND quality_ok.
    - Once in, hold until primary exits (or optional hard stop / continuous trend).
    - Size is set at entry from confidence (and optional teacher-agreement boost)
      and held constant for the trade (no mid-trade confidence thrash).
    """
    idx = primary.index
    primary = primary.reindex(idx).fillna(0.0).astype(float)
    if trend is None:
        trend = pd.Series(True, index=idx)
    else:
        trend = trend.reindex(idx).fillna(False)
    if quality_ok is None:
        quality_ok = pd.Series(True, index=idx)
    else:
        quality_ok = quality_ok.reindex(idx).fillna(False)
    if confidence is None:
        confidence = pd.Series(0.7, index=idx)
    else:
        confidence = confidence.reindex(idx).fillna(0.5).astype(float)
    if agree_boost is None:
        agree_boost = pd.Series(False, index=idx)
    else:
        agree_boost = agree_boost.reindex(idx).fillna(False)
    if close is None:
        close = pd.Series(1.0, index=idx)
    else:
        close = close.reindex(idx).astype(float)

    trigger = 1.0 - stop_loss_pct if stop_loss_pct > 0 else 0.0
    in_pos = False
    entry_price = 0.0
    entry_size = 0.0
    entry_conf = 0.0
    prev_primary = 0.0
    out = pd.Series(0.0, index=idx)
    conf_out = pd.Series(0.0, index=idx)

    lo = float(min_scale_frac)
    hi = float(max_scale_frac)
    base = float(base_scale)
    boost = float(agree_boost_mult)
    cap = float(max_scale_cap)

    for i in range(len(idx)):
        p = float(primary.iloc[i])
        t = bool(trend.iloc[i])
        q = bool(quality_ok.iloc[i])
        c = float(close.iloc[i])
        conf = float(np.clip(confidence.iloc[i], 0.0, 1.0))
        agree = bool(agree_boost.iloc[i])
        new_entry = (p > 0.5) and (prev_primary <= 0.5) and t and q

        if not in_pos:
            if new_entry:
                in_pos = True
                entry_price = c
                mult = lo + (hi - lo) * conf
                sz = base * mult
                if agree:
                    sz *= boost
                entry_size = float(min(sz, cap))
                entry_conf = conf
        else:
            exit_now = False
            if p <= 0.5:
                exit_now = True
            elif stop_loss_pct > 0 and c < entry_price * trigger:
                exit_now = True
            elif continuous_trend and not t:
                exit_now = True
            if exit_now:
                in_pos = False
                entry_size = 0.0
                entry_conf = 0.0

        out.iloc[i] = entry_size if in_pos else 0.0
        conf_out.iloc[i] = entry_conf if in_pos else 0.0
        prev_primary = p

    return out.rename("signal"), conf_out.rename("entry_confidence")


def frozen_defaults() -> Dict[str, Any]:
    """Pre-registered defaults (frozen before OOS evaluation)."""
    return {
        "base_models": ["v45_ultimate_rsi"],
        "primary": "v45_ultimate_rsi",
        "secondary": None,
        "secondary_agree_boost": True,
        "agree_boost_mult": 1.15,
        "trend_filter": {
            "lookback": 250,
            "price_col": "close",
            "direction": "above",
            "apply": "entry",
        },
        "quality": {
            "enabled": True,
            "min_score": 1,
        },
        "confidence": {
            "use_rsi_depth": True,
            "quality_weight": 0.65,
            "rsi_weight": 0.35,
            "min_scale_frac": 0.50,
            "max_scale_frac": 1.0,
        },
        "signal_scale": 0.225,
        "max_scale_cap": 0.35,
        "stop_loss_pct": 0.0,
        "selection_rule": "frozen_before_oos_eval",
        "train_window_end": "2025-08-01",
    }
