"""v19_node_cloud — reactive node magnets + MA cloud compass (rules primary).

Do not predict the market. Read nodes (VAL/POC/VAH), use the EMA cloud to
decide which node price is traveling toward, and react along that path.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

MODEL_SPEC = {
    "id": "poc_va_macdha",
    "version": "v19_node_cloud",
    "variant": {
        "idea": "react_to_node_via_ma_cloud",
        "nodes": ["val", "poc", "vah"],
        "cloud": ["ema_fast", "ema_mid", "ema_slow"],
    },
}


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _volume_profile_levels(highs, lows, volumes, rows, value_area_pct):
    lo = float(np.min(lows))
    hi = float(np.max(highs))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.nan, np.nan, np.nan
    step = (hi - lo) / max(rows, 1)
    if step <= 0:
        return np.nan, np.nan, np.nan
    vol_bins = np.zeros(rows, dtype=float)
    for h, l, v in zip(highs, lows, volumes):
        if not np.isfinite(h) or not np.isfinite(l) or not np.isfinite(v):
            continue
        a = int(np.clip(np.floor((l - lo) / step), 0, rows - 1))
        b = int(np.clip(np.floor((h - lo) / step), 0, rows - 1))
        if b < a:
            a, b = b, a
        share = float(v) / max(b - a + 1, 1)
        vol_bins[a : b + 1] += share
    poc_level = int(np.argmax(vol_bins))
    total = float(vol_bins.sum())
    if total <= 0:
        return np.nan, np.nan, np.nan
    target = total * float(value_area_pct)
    value = vol_bins[poc_level]
    above = below = poc_level
    while value < target and (above < rows - 1 or below > 0):
        up = vol_bins[above + 1] if above < rows - 1 else -1.0
        dn = vol_bins[below - 1] if below > 0 else -1.0
        if up >= dn:
            above = min(above + 1, rows - 1)
            value += max(up, 0.0)
        else:
            below = max(below - 1, 0)
            value += max(dn, 0.0)
    poc = lo + (poc_level + 0.5) * step
    vah = lo + (above + 1) * step
    val = lo + below * step
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


def _resample_ohlcv(df, rule):
    ohlc = df[["open", "high", "low", "close", "volume"]].copy()
    return (
        ohlc.resample(rule, label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )


def _ma_cloud(close: pd.Series, fast: int, mid: int, slow: int) -> pd.DataFrame:
    ema_f = _ema(close, fast)
    ema_m = _ema(close, mid)
    ema_s = _ema(close, slow)
    # Causal: use prior bar cloud so we react to confirmed stack, not same-bar peek.
    ema_f_s = ema_f.shift(1)
    ema_m_s = ema_m.shift(1)
    ema_s_s = ema_s.shift(1)
    bull = (ema_f_s > ema_m_s) & (ema_m_s > ema_s_s) & (close >= ema_m_s)
    bear = (ema_f_s < ema_m_s) & (ema_m_s < ema_s_s) & (close <= ema_m_s)
    return pd.DataFrame(
        {
            "ema_fast": ema_f_s,
            "ema_mid": ema_m_s,
            "ema_slow": ema_s_s,
            "cloud_bull": bull.fillna(False),
            "cloud_bear": bear.fillna(False),
        },
        index=close.index,
    )


def _nearest_node_above(spot: float, nodes: dict[str, float]) -> tuple[str | None, float]:
    above = {k: v for k, v in nodes.items() if np.isfinite(v) and v > spot}
    if not above:
        return None, np.nan
    name = min(above, key=above.get)
    return name, float(above[name])


def _support_held(spot: float, nodes: dict[str, float]) -> bool:
    """Price holds above at least one defined node used as support."""
    supports = []
    for key in ("val", "poc"):
        v = nodes.get(key)
        if v is not None and np.isfinite(v):
            supports.append(float(v))
    if not supports:
        return False
    return spot >= min(supports)


class SignalEngine:
    """Reactive longs: MA cloud compass → nearest upside VP node as target."""

    def __init__(
        self,
        value_area_pct=0.70,
        profile_rows=25,
        profile_lookback=20,
        signal_tf="2h",
        ema_fast=8,
        ema_mid=21,
        ema_slow=55,
        min_target_room_pct=0.004,
        require_support_node=True,
        exit_at_target=True,
        exit_on_cloud_flip=True,
        exit_on_support_break=True,
    ):
        self.value_area_pct = value_area_pct
        self.profile_rows = profile_rows
        self.profile_lookback = profile_lookback
        self.signal_tf = signal_tf
        self.ema_fast = ema_fast
        self.ema_mid = ema_mid
        self.ema_slow = ema_slow
        self.min_target_room_pct = min_target_room_pct
        self.require_support_node = require_support_node
        self.exit_at_target = exit_at_target
        self.exit_on_cloud_flip = exit_on_cloud_flip
        self.exit_on_support_break = exit_on_support_break

    def _signals_on_frame(self, data: pd.DataFrame) -> pd.Series:
        levels = _prior_session_profile(
            data, self.profile_lookback, self.profile_rows, self.value_area_pct
        )
        # Shift nodes so bar i only sees profile from bars strictly before i
        # (_prior_session_profile already excludes bar i; keep levels as-is).
        cloud = _ma_cloud(data["close"], self.ema_fast, self.ema_mid, self.ema_slow)
        close = data["close"]

        signal = pd.Series(0.0, index=data.index)
        in_pos = False
        active_target = np.nan

        for i in range(len(data)):
            spot = float(close.iloc[i])
            nodes = {
                "val": float(levels["val"].iloc[i]) if pd.notna(levels["val"].iloc[i]) else np.nan,
                "poc": float(levels["poc"].iloc[i]) if pd.notna(levels["poc"].iloc[i]) else np.nan,
                "vah": float(levels["vah"].iloc[i]) if pd.notna(levels["vah"].iloc[i]) else np.nan,
            }
            bull = bool(cloud["cloud_bull"].iloc[i])
            bear = bool(cloud["cloud_bear"].iloc[i])
            tgt_name, tgt = _nearest_node_above(spot, nodes)
            room_ok = (
                tgt_name is not None
                and np.isfinite(tgt)
                and ((tgt - spot) / max(spot, 1e-12)) >= self.min_target_room_pct
            )
            support_ok = _support_held(spot, nodes) if self.require_support_node else True

            if not in_pos:
                if bull and room_ok and support_ok:
                    in_pos = True
                    active_target = tgt
                    signal.iloc[i] = 1.0
            else:
                exit_now = False
                if self.exit_on_cloud_flip and bear:
                    exit_now = True
                if self.exit_at_target and np.isfinite(active_target) and spot >= active_target:
                    exit_now = True
                if self.exit_on_support_break and not _support_held(spot, nodes):
                    exit_now = True
                # Refresh target upward if cloud still bullish and a higher node appears
                if not exit_now and bull and room_ok and np.isfinite(tgt):
                    if not np.isfinite(active_target) or tgt > active_target:
                        active_target = tgt
                if exit_now:
                    in_pos = False
                    active_target = np.nan
                    signal.iloc[i] = 0.0
                else:
                    signal.iloc[i] = 1.0
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
            return self._signals_on_frame(frame).reindex(data.index, method="ffill").fillna(0.0)
        return self._signals_on_frame(data)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        return {code: self._one(df) for code, df in data_map.items()}
