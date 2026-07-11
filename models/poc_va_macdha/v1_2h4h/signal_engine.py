
"""POC/VA + HTF St. MACD HA — supports daily or intraday bars via resample HTF."""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _standardized_macd_ha(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal_len: int = 9,
    src: str = "close",
) -> pd.DataFrame:
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
        poc[i], vah[i], val[i] = _volume_profile_levels(
            highs[sl], lows[sl], vols[sl], rows, value_area_pct
        )
    return pd.DataFrame({"poc": poc, "vah": vah, "val": val}, index=df.index)


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    ohlc = df[["open", "high", "low", "close", "volume"]].copy()
    out = ohlc.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    return out


def _htf_ha_green(df: pd.DataFrame, htf: str, macd_params: dict) -> pd.Series:
    htf_df = _resample_ohlcv(df, htf) if htf else df
    if htf_df.empty:
        return pd.Series(False, index=df.index)
    ha = _standardized_macd_ha(
        htf_df,
        fast=macd_params["macd_fast"],
        slow=macd_params["macd_slow"],
        signal_len=macd_params["macd_signal"],
    )
    green = ha["ha_green"].astype(float).shift(1)  # no lookahead
    return green.reindex(df.index, method="ffill").fillna(0.0) > 0.5


class SignalEngine:
    """2H (or native) POC/VA longs filtered by 4H St. MACD HA green."""

    def __init__(
        self,
        value_area_pct: float = 0.70,
        profile_rows: int = 25,
        profile_lookback: int = 20,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        macd_htf: str = "4h",
        signal_tf: str = "2h",  # e.g. "2h" to resample 1H bars up to 2H
        require_htf_green: bool = True,
        exit_on_poc_break: bool = False,
        exit_on_val_break: bool = False,
        use_os_reclaim: bool = False,
    ) -> None:
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

    def _signals_on_frame(self, data: pd.DataFrame) -> pd.Series:
        levels = _prior_session_profile(
            data, self.profile_lookback, self.profile_rows, self.value_area_pct
        )
        poc, vah, val = levels["poc"], levels["vah"], levels["val"]
        close = data["close"]
        poc_support_ok = (close >= poc) & poc.notna()
        in_value_area = (close >= val) & (close <= vah) & val.notna() & vah.notna()
        macd_params = {
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
        }
        htf_green = _htf_ha_green(data, self.macd_htf, macd_params)
        daily_ha = _standardized_macd_ha(
            data, self.macd_fast, self.macd_slow, self.macd_signal
        )
        buy_trigger = htf_green if self.require_htf_green else pd.Series(True, index=data.index)
        if self.use_os_reclaim:
            buy_trigger = buy_trigger & (daily_ha["os_reclaim"] | daily_ha["ha_green"])
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
                if bool(daily_ha["ha_red"].iloc[i]) and not bool(htf_green.iloc[i]):
                    exit_now = True
                signal.iloc[i] = 0.0 if exit_now else 1.0
                in_pos = not exit_now
        return signal.fillna(0.0)

    def _one(self, df: pd.DataFrame) -> pd.Series:
        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()

        if self.signal_tf:
            frame = _resample_ohlcv(data, self.signal_tf)
            if frame.empty:
                return pd.Series(0.0, index=data.index)
            sig_tf = self._signals_on_frame(frame)
            # map 2H signal onto native bars (1H) without lookahead: ffill within bar
            return sig_tf.reindex(data.index, method="ffill").fillna(0.0)

        return self._signals_on_frame(data)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        return {code: self._one(df) for code, df in data_map.items()}
