"""v19b_node_macro — node+cloud primary + XLP/SPY defensive macro gate.

Fixes from v19 FAIL diagnosis + prior WORKING findings:
- Block longs when XLP/SPY RS is in an uptrend (defensive tape) — v19 lost most $ there
- Prefer risk-on (XLP/SPY stacked down) OR post double-top-bottom confirm windows
- Require volume expand (v18 sniper / v2 DNA)
- Do not emit signals for regime refs (XLP/QQQ)

Still react (nodes + MA cloud), do not predict.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

MODEL_SPEC = {
    "id": "poc_va_macdha",
    "version": "v19b_node_macro",
    "variant": {
        "idea": "react_nodes_cloud_plus_xlp_spy_macro",
        "nodes": ["val", "poc", "vah"],
        "cloud": ["ema_fast", "ema_mid", "ema_slow"],
        "macro": ["xlp_spy_risk_on", "xlp_spy_double_top_bottom", "block_defensive"],
    },
}

REGIME_REFS = {"XLP.US", "QQQ.US"}


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _to_daily_close(df: pd.DataFrame) -> pd.Series:
    data = df.copy()
    data.index = pd.to_datetime(data.index)
    if getattr(data.index, "tz", None) is not None:
        data.index = data.index.tz_localize(None)
    daily = data["close"].resample("1D").last().dropna()
    return daily.astype(float)


def _xlp_spy_macro(xlp_df: pd.DataFrame, spy_df: pd.DataFrame) -> pd.DataFrame:
    """Causal daily macro features from XLP/SPY relative strength."""
    xlp = _to_daily_close(xlp_df)
    spy = _to_daily_close(spy_df)
    idx = xlp.index.intersection(spy.index)
    xlp, spy = xlp.reindex(idx), spy.reindex(idx)
    ratio = xlp / spy
    ma20 = ratio.rolling(20, min_periods=20).mean()
    ma50 = ratio.rolling(50, min_periods=50).mean()
    risk_on = (ratio < ma20) & (ma20 < ma50)
    defensive = (ratio > ma20) & (ma20 > ma50)

    vals = ratio.to_numpy(float)
    n = len(ratio)
    peaks: list[int] = []
    for i in range(5, n - 5):
        if np.isfinite(vals[i]) and vals[i] == np.nanmax(vals[i - 5 : i + 6]):
            peaks.append(i)
    dt = np.zeros(n, dtype=bool)
    for k in range(1, len(peaks)):
        i1, i2 = peaks[k - 1], peaks[k]
        if not (10 <= i2 - i1 <= 50):
            continue
        p1, p2 = vals[i1], vals[i2]
        if abs(p1 - p2) / max(abs(p1), 1e-12) > 0.02:
            continue
        if i2 < 20 or not np.isfinite(ma50.iloc[i2]) or not np.isfinite(ma50.iloc[i2 - 20]):
            continue
        if float(ma50.iloc[i2] - ma50.iloc[i2 - 20]) >= 0:
            continue
        trough = float(np.nanmin(vals[i1 : i2 + 1]))
        for j in range(i2 + 1, min(n, i2 + 20)):
            if vals[j] < trough:
                dt[j : min(n, j + 15)] = True
                break

    out = pd.DataFrame(
        {
            "risk_on": risk_on.astype(bool),
            "defensive": defensive.astype(bool),
            "dt_bottom": pd.Series(dt, index=ratio.index),
        },
        index=ratio.index,
    )
    return out.shift(1)


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
    ema_f = _ema(close, fast).shift(1)
    ema_m = _ema(close, mid).shift(1)
    ema_s = _ema(close, slow).shift(1)
    bull = (ema_f > ema_m) & (ema_m > ema_s) & (close >= ema_m)
    bear = (ema_f < ema_m) & (ema_m < ema_s) & (close <= ema_m)
    return pd.DataFrame(
        {"cloud_bull": bull.fillna(False), "cloud_bear": bear.fillna(False)},
        index=close.index,
    )


def _nearest_node_above(spot: float, nodes: dict[str, float]) -> tuple[str | None, float]:
    above = {k: v for k, v in nodes.items() if np.isfinite(v) and v > spot}
    if not above:
        return None, np.nan
    name = min(above, key=above.get)
    return name, float(above[name])


def _support_held(spot: float, nodes: dict[str, float]) -> bool:
    supports = []
    for key in ("val", "poc"):
        v = nodes.get(key)
        if v is not None and np.isfinite(v):
            supports.append(float(v))
    if not supports:
        return False
    return spot >= min(supports)


class SignalEngine:
    """Node+cloud longs gated by XLP/SPY risk-on / double-top-bottom macro."""

    def __init__(
        self,
        value_area_pct=0.70,
        profile_rows=25,
        profile_lookback=20,
        signal_tf="2h",
        ema_fast=8,
        ema_mid=21,
        ema_slow=55,
        min_target_room_pct=0.006,
        require_support_node=True,
        exit_at_target=True,
        exit_on_cloud_flip=True,
        exit_on_support_break=True,
        require_volume_expand=True,
        volume_sma_len=20,
        volume_expand_mult=1.0,
        require_macro_ok=True,
        block_defensive=True,
        allow_dt_bottom=True,
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
        self.require_volume_expand = require_volume_expand
        self.volume_sma_len = volume_sma_len
        self.volume_expand_mult = volume_expand_mult
        self.require_macro_ok = require_macro_ok
        self.block_defensive = block_defensive
        self.allow_dt_bottom = allow_dt_bottom

    def _signals_on_frame(self, data: pd.DataFrame, macro_ok: pd.Series | None) -> pd.Series:
        levels = _prior_session_profile(
            data, self.profile_lookback, self.profile_rows, self.value_area_pct
        )
        cloud = _ma_cloud(data["close"], self.ema_fast, self.ema_mid, self.ema_slow)
        close = data["close"]
        vol_sma = data["volume"].rolling(self.volume_sma_len, min_periods=1).mean()
        vol_expand = data["volume"] >= (vol_sma * self.volume_expand_mult)

        if macro_ok is None:
            macro = pd.Series(True, index=data.index)
        else:
            macro = macro_ok.reindex(data.index).ffill().fillna(False).astype(bool)

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
            vol_ok = bool(vol_expand.iloc[i]) if self.require_volume_expand else True
            regime_ok = bool(macro.iloc[i]) if self.require_macro_ok else True

            if not in_pos:
                if bull and room_ok and support_ok and vol_ok and regime_ok:
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
                if self.block_defensive and not regime_ok:
                    exit_now = True
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

    def _one(self, df: pd.DataFrame, macro_daily: pd.Series | None) -> pd.Series:
        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()
        macro_ok = None
        if macro_daily is not None:
            days = data.index.normalize()
            macro_ok = macro_daily.reindex(days).ffill().fillna(False)
            macro_ok.index = data.index
        if self.signal_tf:
            frame = _resample_ohlcv(data, self.signal_tf)
            if frame.empty:
                return pd.Series(0.0, index=data.index)
            m = macro_ok.reindex(frame.index, method="ffill").fillna(False) if macro_ok is not None else None
            return self._signals_on_frame(frame, m).reindex(data.index, method="ffill").fillna(0.0)
        return self._signals_on_frame(data, macro_ok)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        macro_allow: pd.Series | None = None
        spy_key = next((k for k in data_map if k.startswith("SPY")), None)
        xlp_key = next((k for k in data_map if k.startswith("XLP")), None)
        if spy_key and xlp_key:
            feat = _xlp_spy_macro(data_map[xlp_key], data_map[spy_key])
            allow = feat["risk_on"].astype(bool)
            if self.allow_dt_bottom:
                allow = allow | feat["dt_bottom"].astype(bool)
            if self.block_defensive:
                allow = allow & (~feat["defensive"].astype(bool))
            macro_allow = allow.astype(bool)

        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            if code in REGIME_REFS or str(code).startswith("XLP") or str(code).startswith("QQQ"):
                out[code] = pd.Series(0.0, index=df.index)
                continue
            if macro_allow is None and self.require_macro_ok:
                out[code] = pd.Series(0.0, index=df.index)
                continue
            out[code] = self._one(df, macro_allow)
        return out
