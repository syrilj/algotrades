"""Swing-anchored VWAP peg (algo / institutional mean).

Same family as poc_va_macdha specialists (Zeiierman-style dynamic swing VWAP).
Used as SOFT bias for flips — not a global hard AND with VPA.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _alpha_from_apt(apt: float) -> float:
    decay = np.exp(-np.log(2.0) / max(1.0, float(apt)))
    return 1.0 - decay


def swing_anchored_vwap(
    df: pd.DataFrame,
    swing_period: int = 50,
    base_apt: float = 20.0,
) -> pd.DataFrame:
    """Return vwap, uptrend (causal: use .shift(1) at signal time)."""
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    volume = df["volume"].to_numpy(float) if "volume" in df.columns else np.ones(len(df))
    hlc3 = (high + low + close) / 3.0
    n = len(df)
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = pd.Series(tr, index=df.index).ewm(alpha=1 / 50, adjust=False).mean().to_numpy()
    atr_avg = pd.Series(atr, index=df.index).ewm(alpha=1 / 50, adjust=False).mean().to_numpy()

    ph = pl = np.nan
    ph_i = pl_i = 0
    direction = np.ones(n, dtype=int)
    vwap = np.full(n, np.nan)
    p_acc = vol_acc = 0.0

    for i in range(n):
        left = max(0, i - swing_period + 1)
        if high[i] >= np.max(high[left : i + 1]) - 1e-12:
            ph, ph_i = high[i], i
        if low[i] <= np.min(low[left : i + 1]) + 1e-12:
            pl, pl_i = low[i], i
        new_dir = 1 if ph_i > pl_i else -1
        prev_dir = direction[i - 1] if i else new_dir
        alpha = _alpha_from_apt(base_apt)
        if i == 0 or new_dir != prev_dir:
            anchor_i = int(np.clip(pl_i if new_dir > 0 else ph_i, 0, i))
            anchor_y = pl if new_dir > 0 else ph
            if not np.isfinite(anchor_y):
                anchor_y = hlc3[anchor_i]
            p_acc = float(anchor_y) * float(max(volume[anchor_i], 1e-12))
            vol_acc = float(max(volume[anchor_i], 1e-12))
            for j in range(anchor_i, i + 1):
                a = alpha
                p_acc = (1 - a) * p_acc + a * hlc3[j] * volume[j]
                vol_acc = (1 - a) * vol_acc + a * volume[j]
            direction[i] = new_dir
        else:
            p_acc = (1 - alpha) * p_acc + alpha * hlc3[i] * volume[i]
            vol_acc = (1 - alpha) * vol_acc + alpha * volume[i]
            direction[i] = new_dir
        vwap[i] = p_acc / vol_acc if vol_acc > 0 else np.nan

    out = pd.DataFrame(
        {
            "vwap": vwap,
            "uptrend": direction > 0,
            "atr": atr,
        },
        index=df.index,
    )
    # causal
    out["vwap"] = out["vwap"].shift(1)
    out["uptrend"] = out["uptrend"].shift(1)
    out["above_vwap"] = (df["close"] >= out["vwap"]).fillna(False)
    out["below_vwap"] = (df["close"] <= out["vwap"]).fillna(False)
    atr_s = out["atr"].replace(0, np.nan)
    out["dist_vwap_atr"] = (df["close"] - out["vwap"]) / atr_s
    out["chase_long"] = (out["dist_vwap_atr"] > 2.0).fillna(False)  # extended above peg
    out["chase_short"] = (out["dist_vwap_atr"] < -2.0).fillna(False)
    # soft bias: with peg OR reclaim toward peg
    out["call_peg_ok"] = (out["above_vwap"] | out["uptrend"]).fillna(False)
    out["put_peg_ok"] = (out["below_vwap"] | ~out["uptrend"].fillna(False)).fillna(False)
    return out
