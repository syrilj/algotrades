"""
================================================================================
MODEL SECTION — poc_va_macdha
================================================================================
MODEL_ID:      poc_va_macdha
VERSION:       v2_vwap
PARENT:        v1_2h4h
STATUS:        active (runs/poc_va_macdha/code/signal_engine.py)
SNAPSHOTS:     models/poc_va_macdha/v1_2h4h/  |  models/poc_va_macdha/v2_vwap/
PINE:          pine/poc_va_macdha_v1.pine  |  pine/poc_va_macdha_v2_vwap.pine

STACK
-----
1) Prior-window Volume Profile → POC / VAL / VAH (value_area_pct ≈ 70%)
2) POC support while held; lost POC = resistance (no long base)
3) Long only inside [VAL, VAH] while POC holds
4) HTF Standardized MACD Heikin-Ashi green (default 4H) for timing
5) Signal TF resample (default 2H from 1H bars)
6) [v2] Dynamic Swing-Anchored VWAP (Zeiierman-style) trend + volume confidence:
     - Swing dir > 0 → uptrend (anchored from swing low)
     - Require close >= swing VWAP for long confidence
     - Require volume expansion vs SMA before entry

TOGGLE FLAGS (iterate here)
---------------------------
require_htf_green, require_vwap_uptrend, require_above_vwap,
require_volume_expand, exit_on_poc_break, exit_on_val_break,
exit_below_vwap, use_os_reclaim, signal_tf, macd_htf

IMPROVEMENT ROADMAP
-------------------
A. Confidence score (0-1) from VP + HA + VWAP + vol → size position
B. Per-symbol parameter sets (MU likes 2H/4H; SPY prefers daily)
C. Soft POC exits (trail) instead of binary leave
D. Short side when dir < 0, below VWAP, HA red, in VA near VAH
E. Session VP from true RTH minute bars when data allows
F. Walk-forward + purged CV before live

CHANGELOG
---------
v1_2h4h  : POC/VA + 2H signals + 4H St.MACD-HA
v2_vwap  : + swing-anchored adaptive VWAP trend/volume gates
================================================================================
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

MODEL_SPEC = {
    "id": "poc_va_macdha",
    "version": "v2_vwap",
    "parent": "v1_2h4h",
    "defaults": {
        "value_area_pct": 0.70,
        "profile_rows": 25,
        "profile_lookback": 20,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "macd_htf": "4h",
        "signal_tf": "2h",
        "require_htf_green": True,
        "exit_on_poc_break": False,
        "exit_on_val_break": False,
        "use_os_reclaim": False,
        "swing_period": 50,
        "base_apt": 20.0,
        "use_adapt_apt": False,
        "vol_bias": 10.0,
        "volume_sma_len": 20,
        "volume_expand_mult": 1.0,
        "require_vwap_uptrend": True,
        "require_above_vwap": True,
        "require_volume_expand": True,
        "exit_below_vwap": True,
    },
}


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _alpha_from_apt(apt: float) -> float:
    decay = np.exp(-np.log(2.0) / max(1.0, float(apt)))
    return 1.0 - decay


def dynamic_swing_anchored_vwap(
    df: pd.DataFrame,
    swing_period: int = 50,
    base_apt: float = 20.0,
    use_adapt_apt: bool = False,
    vol_bias: float = 10.0,
) -> pd.DataFrame:
    """Zeiierman-style Dynamic Swing Anchored VWAP (causal, bar-by-bar)."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    hlc3 = (high + low + close) / 3.0
    n = len(df)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = pd.Series(tr, index=df.index).ewm(alpha=1 / 50, adjust=False).mean().to_numpy()
    atr_avg = pd.Series(atr, index=df.index).ewm(alpha=1 / 50, adjust=False).mean().to_numpy()

    ph = np.nan
    pl = np.nan
    ph_i = 0
    pl_i = 0
    direction = np.ones(n, dtype=int)
    vwap = np.full(n, np.nan)
    apt_out = np.full(n, np.nan)
    p_acc = 0.0
    vol_acc = 0.0

    for i in range(n):
        left = max(0, i - swing_period + 1)
        window_h = high[left : i + 1]
        window_l = low[left : i + 1]
        if high[i] >= np.max(window_h) - 1e-12:
            ph = high[i]
            ph_i = i
        if low[i] <= np.min(window_l) + 1e-12:
            pl = low[i]
            pl_i = i

        new_dir = 1 if ph_i > pl_i else -1
        prev_dir = direction[i - 1] if i > 0 else new_dir

        ratio = atr[i] / atr_avg[i] if atr_avg[i] > 0 else 1.0
        apt_raw = base_apt / (ratio ** vol_bias) if use_adapt_apt else base_apt
        apt = float(np.clip(round(max(5.0, min(300.0, apt_raw))), 5, 300))
        apt_out[i] = apt
        alpha = _alpha_from_apt(apt)

        if i == 0 or new_dir != prev_dir:
            anchor_i = pl_i if new_dir > 0 else ph_i
            anchor_i = int(np.clip(anchor_i, 0, i))
            anchor_y = pl if new_dir > 0 else ph
            if not np.isfinite(anchor_y):
                anchor_y = hlc3[anchor_i]
            p_acc = float(anchor_y) * float(max(volume[anchor_i], 1e-12))
            vol_acc = float(max(volume[anchor_i], 1e-12))
            for j in range(anchor_i, i + 1):
                ratio_j = atr[j] / atr_avg[j] if atr_avg[j] > 0 else 1.0
                apt_j = base_apt / (ratio_j ** vol_bias) if use_adapt_apt else base_apt
                apt_j = float(np.clip(round(max(5.0, min(300.0, apt_j))), 5, 300))
                a = _alpha_from_apt(apt_j)
                pxv = hlc3[j] * volume[j]
                p_acc = (1.0 - a) * p_acc + a * pxv
                vol_acc = (1.0 - a) * vol_acc + a * volume[j]
            direction[i] = new_dir
        else:
            pxv = hlc3[i] * volume[i]
            p_acc = (1.0 - alpha) * p_acc + alpha * pxv
            vol_acc = (1.0 - alpha) * vol_acc + alpha * volume[i]
            direction[i] = new_dir

        vwap[i] = p_acc / vol_acc if vol_acc > 0 else np.nan

    return pd.DataFrame(
        {
            "vwap": vwap,
            "dir": direction,
            "apt": apt_out,
            "uptrend": direction > 0,
            "downtrend": direction < 0,
        },
        index=df.index,
    )


def _standardized_macd_ha(df, fast=12, slow=26, signal_len=9, src="close"):
    src_px = df[src]
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    macd = (_ema(src_px, fast) - _ema(src_px, slow)) / _ema(hl, slow) * 100.0
    macd = macd.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    macd_prev = macd.shift(1).fillna(macd)
    o, h, l, c = macd_prev, np.maximum(macd, macd_prev), np.minimum(macd, macd_prev), macd
    ha_close = (o + h + l + c) / 4.0
    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2.0
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0
    ha_high = pd.concat([pd.Series(h, index=df.index), ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([pd.Series(l, index=df.index), ha_open, ha_close], axis=1).min(axis=1)
    out = pd.DataFrame(
        {"ha_open": ha_open, "ha_high": ha_high, "ha_low": ha_low, "ha_close": ha_close, "macd": macd},
        index=df.index,
    )
    out["ha_green"] = out["ha_close"] > out["ha_open"]
    out["ha_red"] = out["ha_close"] < out["ha_open"]
    prev_green = out["ha_green"].shift(1).fillna(0).astype(bool)
    out["os_reclaim"] = out["ha_green"] & (~prev_green) & (out["ha_low"] < -100)
    return out


def _volume_profile_levels(highs, lows, volumes, rows, value_area_pct):
    price_high = float(np.max(highs))
    price_low = float(np.min(lows))
    if not np.isfinite(price_high) or not np.isfinite(price_low) or price_high <= price_low:
        mid = float(np.nanmean((highs + lows) / 2.0))
        return mid, mid, mid
    step = (price_high - price_low) / rows
    if step <= 0:
        mid = (price_high + price_low) / 2.0
        return mid, price_high, price_low
    vol_bins = np.zeros(rows, dtype=float)
    for h, l, v in zip(highs, lows, volumes):
        if not np.isfinite(v) or v <= 0:
            continue
        bar_range = h - l
        for level in range(rows):
            bin_lo = price_low + level * step
            bin_hi = bin_lo + step
            if h >= bin_lo and l < bin_hi:
                weight = 1.0 if bar_range == 0 else step / bar_range
                vol_bins[level] += v * weight
    if vol_bins.sum() <= 0:
        mid = (price_high + price_low) / 2.0
        return mid, price_high, price_low
    poc_level = int(np.argmax(vol_bins))
    target = vol_bins.sum() * value_area_pct
    value = vol_bins[poc_level]
    above = below = poc_level
    while value < target:
        if below == 0 and above == rows - 1:
            break
        vol_above = vol_bins[above + 1] if above < rows - 1 else 0.0
        vol_below = vol_bins[below - 1] if below > 0 else 0.0
        if vol_above == 0 and vol_below == 0:
            break
        if vol_above >= vol_below:
            above += 1
            value += vol_above
        else:
            below -= 1
            value += vol_below
    poc = price_low + (poc_level + 0.5) * step
    vah = price_low + (above + 1.0) * step
    val = price_low + below * step
    return float(poc), float(vah), float(val)


def _prior_session_profile(df, lookback, rows, value_area_pct):
    n = len(df)
    poc = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    val = np.full(n, np.nan)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    vols = df["volume"].to_numpy(dtype=float)
    for i in range(lookback, n):
        sl = slice(i - lookback, i)
        poc[i], vah[i], val[i] = _volume_profile_levels(highs[sl], lows[sl], vols[sl], rows, value_area_pct)
    return pd.DataFrame({"poc": poc, "vah": vah, "val": val}, index=df.index)


def _resample_ohlcv(df, rule):
    ohlc = df[["open", "high", "low", "close", "volume"]].copy()
    return (
        ohlc.resample(rule, label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )


def _htf_ha_green(df, htf, macd_params):
    htf_df = _resample_ohlcv(df, htf) if htf else df
    if htf_df.empty:
        return pd.Series(False, index=df.index)
    ha = _standardized_macd_ha(htf_df, macd_params["macd_fast"], macd_params["macd_slow"], macd_params["macd_signal"])
    green = ha["ha_green"].astype(float).shift(1)
    return green.reindex(df.index, method="ffill").fillna(0.0) > 0.5


class SignalEngine:
    """v2: POC/VA + HTF St.MACD-HA + swing-anchored VWAP / volume confidence."""

    def __init__(
        self,
        value_area_pct=0.70,
        profile_rows=25,
        profile_lookback=20,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        macd_htf="4h",
        signal_tf="2h",
        require_htf_green=True,
        exit_on_poc_break=False,
        exit_on_val_break=False,
        use_os_reclaim=False,
        swing_period=50,
        base_apt=20.0,
        use_adapt_apt=False,
        vol_bias=10.0,
        volume_sma_len=20,
        volume_expand_mult=1.0,
        require_vwap_uptrend=True,
        require_above_vwap=True,
        require_volume_expand=True,
        exit_below_vwap=True,
    ):
        self.value_area_pct = value_area_pct
        self.profile_rows = profile_rows
        self.profile_lookback = profile_lookback
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.macd_htf = macd_htf
        self.signal_tf = signal_tf
        self.require_htf_green = require_htf_green
        self.exit_on_poc_break = exit_on_poc_break
        self.exit_on_val_break = exit_on_val_break
        self.use_os_reclaim = use_os_reclaim
        self.swing_period = swing_period
        self.base_apt = base_apt
        self.use_adapt_apt = use_adapt_apt
        self.vol_bias = vol_bias
        self.volume_sma_len = volume_sma_len
        self.volume_expand_mult = volume_expand_mult
        self.require_vwap_uptrend = require_vwap_uptrend
        self.require_above_vwap = require_above_vwap
        self.require_volume_expand = require_volume_expand
        self.exit_below_vwap = exit_below_vwap

    def _signals_on_frame(self, data):
        levels = _prior_session_profile(data, self.profile_lookback, self.profile_rows, self.value_area_pct)
        poc, vah, val = levels["poc"], levels["vah"], levels["val"]
        close = data["close"]
        poc_support_ok = (close >= poc) & poc.notna()
        in_value_area = (close >= val) & (close <= vah) & val.notna() & vah.notna()
        macd_params = {"macd_fast": self.macd_fast, "macd_slow": self.macd_slow, "macd_signal": self.macd_signal}
        htf_green = _htf_ha_green(data, self.macd_htf, macd_params)
        local_ha = _standardized_macd_ha(data, self.macd_fast, self.macd_slow, self.macd_signal)

        swing = dynamic_swing_anchored_vwap(
            data, self.swing_period, self.base_apt, self.use_adapt_apt, self.vol_bias
        )
        vwap = swing["vwap"].shift(1)
        uptrend = swing["uptrend"].shift(1).fillna(False).astype(bool)
        vol_sma = data["volume"].rolling(self.volume_sma_len, min_periods=1).mean()
        vol_expand = data["volume"] >= (vol_sma * self.volume_expand_mult)
        above_vwap = close >= vwap

        buy_trigger = htf_green if self.require_htf_green else pd.Series(True, index=data.index)
        if self.use_os_reclaim:
            buy_trigger = buy_trigger & (local_ha["os_reclaim"] | local_ha["ha_green"])
        if self.require_vwap_uptrend:
            buy_trigger = buy_trigger & uptrend
        if self.require_above_vwap:
            buy_trigger = buy_trigger & above_vwap.fillna(False)
        if self.require_volume_expand:
            buy_trigger = buy_trigger & vol_expand.fillna(False)

        long_entry = poc_support_ok & in_value_area & buy_trigger
        signal = pd.Series(0.0, index=data.index)
        in_pos = False
        for i in range(len(data)):
            if not in_pos:
                if bool(long_entry.iloc[i]):
                    in_pos = True
                    signal.iloc[i] = 1.0
            else:
                exit_now = False
                if self.require_htf_green and not bool(htf_green.iloc[i]):
                    exit_now = True
                if self.exit_on_poc_break and not bool(poc_support_ok.iloc[i]):
                    exit_now = True
                if self.exit_on_val_break and close.iloc[i] < val.iloc[i]:
                    exit_now = True
                if self.exit_below_vwap and pd.notna(vwap.iloc[i]) and close.iloc[i] < vwap.iloc[i]:
                    exit_now = True
                if bool(local_ha["ha_red"].iloc[i]) and not bool(htf_green.iloc[i]):
                    exit_now = True
                signal.iloc[i] = 0.0 if exit_now else 1.0
                in_pos = not exit_now
        return signal.fillna(0.0)

    def _one(self, df):
        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()
        if self.signal_tf:
            frame = _resample_ohlcv(data, self.signal_tf)
            if frame.empty:
                return pd.Series(0.0, index=data.index)
            return self._signals_on_frame(frame).reindex(data.index, method="ffill").fillna(0.0)
        return self._signals_on_frame(data)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        return {code: self._one(df) for code, df in data_map.items()}
