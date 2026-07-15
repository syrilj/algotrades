from __future__ import annotations
"""v65_desk_specialists — multi-symbol router for the desk bag.

Symbols: TSLA, MU, IONQ (INFQ alias), MSTR, SNDK, ASTS, META, GOOG, COIN.
Each code has specialist DNA from models/poc_va_macdha/specialists/<SYM>/.
CRWV uses its own bounce specialist — not routed here.
"""

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

# ─── indicators ─────────────────────────────────────────────────────────────

def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def _sma(s, n):
    return s.rolling(n, min_periods=max(1, n // 2)).mean()

def _alpha_from_apt(apt: float) -> float:
    decay = np.exp(-np.log(2.0) / max(1.0, float(apt)))
    return 1.0 - decay

def dynamic_swing_anchored_vwap(df, swing_period=50, base_apt=20.0, use_adapt_apt=False, vol_bias=10.0):
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    volume = df["volume"].to_numpy(float)
    hlc3 = (high + low + close) / 3.0
    n = len(df)
    prev_close = np.roll(close, 1); prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = pd.Series(tr, index=df.index).ewm(alpha=1/50, adjust=False).mean().to_numpy()
    atr_avg = pd.Series(atr, index=df.index).ewm(alpha=1/50, adjust=False).mean().to_numpy()
    ph = pl = np.nan
    ph_i = pl_i = 0
    direction = np.ones(n, dtype=int)
    vwap = np.full(n, np.nan)
    p_acc = vol_acc = 0.0
    for i in range(n):
        left = max(0, i - swing_period + 1)
        if high[i] >= np.max(high[left:i+1]) - 1e-12:
            ph, ph_i = high[i], i
        if low[i] <= np.min(low[left:i+1]) + 1e-12:
            pl, pl_i = low[i], i
        new_dir = 1 if ph_i > pl_i else -1
        prev_dir = direction[i-1] if i else new_dir
        ratio = atr[i]/atr_avg[i] if atr_avg[i] > 0 else 1.0
        apt_raw = base_apt / (ratio ** vol_bias) if use_adapt_apt else base_apt
        apt = float(np.clip(round(max(5.0, min(300.0, apt_raw))), 5, 300))
        alpha = _alpha_from_apt(apt)
        if i == 0 or new_dir != prev_dir:
            anchor_i = int(np.clip(pl_i if new_dir > 0 else ph_i, 0, i))
            anchor_y = pl if new_dir > 0 else ph
            if not np.isfinite(anchor_y):
                anchor_y = hlc3[anchor_i]
            p_acc = float(anchor_y) * float(max(volume[anchor_i], 1e-12))
            vol_acc = float(max(volume[anchor_i], 1e-12))
            for j in range(anchor_i, i+1):
                rj = atr[j]/atr_avg[j] if atr_avg[j] > 0 else 1.0
                apt_j = base_apt / (rj ** vol_bias) if use_adapt_apt else base_apt
                apt_j = float(np.clip(round(max(5.0, min(300.0, apt_j))), 5, 300))
                a = _alpha_from_apt(apt_j)
                p_acc = (1-a)*p_acc + a*hlc3[j]*volume[j]
                vol_acc = (1-a)*vol_acc + a*volume[j]
            direction[i] = new_dir
        else:
            p_acc = (1-alpha)*p_acc + alpha*hlc3[i]*volume[i]
            vol_acc = (1-alpha)*vol_acc + alpha*volume[i]
            direction[i] = new_dir
        vwap[i] = p_acc/vol_acc if vol_acc > 0 else np.nan
    return pd.DataFrame({"vwap": vwap, "dir": direction, "uptrend": direction > 0}, index=df.index)

def squeeze_momentum(df, length=20, mult_bb=2.0, length_kc=20, mult_kc=1.5, use_tr=True):
    src = df["close"]
    basis = _sma(src, length)
    std = src.rolling(length, min_periods=max(2, length//2)).std(ddof=0)
    upper_bb = basis + mult_bb * std
    lower_bb = basis - mult_bb * std
    ma = _sma(src, length_kc)
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([(high-low), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    rangema = tr.ewm(span=length_kc, adjust=False).mean() if use_tr else (high-low).rolling(length_kc).mean()
    upper_kc = ma + mult_kc * rangema
    lower_kc = ma - mult_kc * rangema
    sqz_on = ((lower_bb > lower_kc) & (upper_bb < upper_kc)).fillna(False)
    sqz_off = ((lower_bb < lower_kc) & (upper_bb > upper_kc)).fillna(False)
    mom = src - basis
    return {
        "sqz_on": sqz_on.astype(bool),
        "sqz_off": sqz_off.astype(bool),
        "sqz_release": (sqz_on.shift(1).fillna(False) & sqz_off).astype(bool),
        "mom_pos": (mom > 0).fillna(False).astype(bool),
        "mom_neg": (mom < 0).fillna(False).astype(bool),
        "mom_pos_inc": ((mom > mom.shift(1)) & (mom > 0)).fillna(False).astype(bool),
    }

def volume_price_state(df, look=5, vol_sma=20):
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float)
    ret1 = close.pct_change()
    vma = _sma(vol, vol_sma)
    vol_expand = (vol > 1.15 * vma).fillna(False)
    green = (close > close.shift(1)).fillna(False)
    red = (close < close.shift(1)).fillna(False)
    rng = (high - low).replace(0, np.nan)
    upper_wick = (high - close).clip(lower=0) / rng
    lower_wick = (close - low).clip(lower=0) / rng
    dump = (red & vol_expand & (ret1 < -0.02)).fillna(False)
    red_flag_up = (green & vol_expand & (upper_wick > 0.55) & (ret1 > 0.015)).fillna(False)
    confirm_up = (green & vol_expand & (ret1 > 0.005)).fillna(False)
    healthy_pull = (red & ~vol_expand & (lower_wick > 0.4)).fillna(False)
    return {
        "vol_expand": vol_expand.astype(bool),
        "dump": dump.astype(bool),
        "red_flag_up": red_flag_up.astype(bool),
        "confirm_up": confirm_up.astype(bool),
        "healthy_pull": healthy_pull.astype(bool),
    }

def _resample_ohlcv(df, rule):
    if not rule:
        return df
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    l = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    v = df["volume"].resample(rule).sum()
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}).dropna()

def _standardized_macd_ha(df, fast=12, slow=26, signal=9):
    close = df["close"].astype(float)
    macd = _ema(close, fast) - _ema(close, slow)
    sig = _ema(macd, signal)
    hist = macd - sig
    ha_close = (macd + sig + hist + macd.shift(1).fillna(macd)) / 4.0
    ha_open = (macd.shift(1).fillna(macd) + sig.shift(1).fillna(sig)) / 2.0
    ha_green = ha_close >= ha_open
    return pd.DataFrame({"macd": macd, "ha_green": ha_green, "ha_red": ~ha_green}, index=df.index)

def _htf_ha_green(df, htf, fast=12, slow=26, signal=9):
    frame = _resample_ohlcv(df, htf)
    if frame.empty:
        return pd.Series(False, index=df.index)
    ha = _standardized_macd_ha(frame, fast, slow, signal)["ha_green"]
    return ha.reindex(df.index, method="ffill").fillna(False).astype(bool)

def _prior_session_profile(df, lookback=20, rows=25, value_area_pct=0.7):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    n = len(df)
    poc = np.full(n, np.nan)
    val = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    for i in range(n):
        a = max(0, i - lookback)
        if i - a < 5:
            continue
        sl = low.iloc[a:i].to_numpy(); sh = high.iloc[a:i].to_numpy(); sv = volume.iloc[a:i].to_numpy()
        lo, hi = float(np.nanmin(sl)), float(np.nanmax(sh))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            continue
        bins = np.linspace(lo, hi, rows + 1)
        vol = np.zeros(rows)
        for j in range(len(sl)):
            a0, b0, v0 = float(sl[j]), float(sh[j]), float(sv[j])
            if not np.isfinite(v0) or v0 <= 0:
                continue
            if b0 <= a0:
                idx = min(rows - 1, max(0, int((a0 - lo) / (hi - lo + 1e-12) * rows)))
                vol[idx] += v0
                continue
            for k in range(rows):
                bl, bh = bins[k], bins[k + 1]
                overlap = max(0.0, min(b0, bh) - max(a0, bl))
                if overlap > 0:
                    vol[k] += v0 * overlap / (b0 - a0)
        mid = 0.5 * (bins[:-1] + bins[1:])
        poc[i] = float(mid[int(np.argmax(vol))])
        order = np.argsort(vol)[::-1]
        total = float(vol.sum()) or 1.0
        acc = 0.0
        mask = np.zeros(rows, dtype=bool)
        for k in order:
            mask[k] = True
            acc += float(vol[k])
            if acc / total >= value_area_pct:
                break
        idx = np.where(mask)[0]
        val[i] = float(mid[idx.min()]); vah[i] = float(mid[idx.max()])
    return {"poc": pd.Series(poc, index=df.index), "val": pd.Series(val, index=df.index), "vah": pd.Series(vah, index=df.index)}

_ROUTING = {'TSLA.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 30, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': False, 'require_volume_expand': False, 'require_vol_confirm': True, 'block_red_flag': True, 'block_dump': True, 'require_sqz_release': False, 'require_mom_pos': False, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': False, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 3, 'vol_sma': 20, 'min_confidence': 0.6}, 'MU.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': False, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': True, 'block_dump': True, 'require_sqz_release': False, 'require_mom_pos': False, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': False, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}, 'IONQ.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '1D', 'signal_tf': '4h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': True, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': True, 'block_dump': False, 'require_sqz_release': False, 'require_mom_pos': True, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': True, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}, 'MSTR.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': True, 'require_volume_expand': True, 'require_vol_confirm': True, 'block_red_flag': True, 'block_dump': True, 'require_sqz_release': False, 'require_mom_pos': True, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': True, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': True, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}, 'SNDK.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': False, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': True, 'block_dump': True, 'require_sqz_release': False, 'require_mom_pos': False, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': False, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}, 'ASTS.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '1D', 'signal_tf': '4h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': True, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': True, 'block_dump': False, 'require_sqz_release': False, 'require_mom_pos': True, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': True, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}, 'META.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': True, 'require_above_vwap': True, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': False, 'block_dump': False, 'require_sqz_release': False, 'require_mom_pos': False, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': True, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}, 'GOOG.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': True, 'require_above_vwap': True, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': False, 'block_dump': False, 'require_sqz_release': False, 'require_mom_pos': False, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': True, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}, 'COIN.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': True, 'require_volume_expand': True, 'require_vol_confirm': True, 'block_red_flag': True, 'block_dump': True, 'require_sqz_release': False, 'require_mom_pos': True, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': True, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': True, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6}}

_ALIAS = {"INFQ.US": "IONQ.US", "INFQ": "IONQ.US", "GOOGL.US": "GOOG.US", "GOOGL": "GOOG.US"}

class SignalEngine:
    def __init__(self):
        self.routing = dict(_ROUTING)
        # optional on-disk override
        p = Path(__file__).resolve().parent / "ROUTING.json"
        if p.exists():
            try:
                raw = json.loads(p.read_text())
                if isinstance(raw.get("routing"), dict):
                    self.routing.update(raw["routing"])
            except Exception:
                pass

    def _cfg(self, code: str) -> Dict[str, Any]:
        code = _ALIAS.get(code, code)
        if not code.endswith(".US") and f"{code}.US" in self.routing:
            code = f"{code}.US"
        return dict(self.routing.get(code) or self.routing.get("TSLA.US") or {})

    def _signals_on_frame(self, data, cfg: Dict[str, Any]):
        value_area_pct = float(cfg.get("value_area_pct", 0.7))
        profile_rows = int(cfg.get("profile_rows", 25))
        profile_lookback = int(cfg.get("profile_lookback", 20))
        macd_fast = int(cfg.get("macd_fast", 12))
        macd_slow = int(cfg.get("macd_slow", 26))
        macd_signal = int(cfg.get("macd_signal", 9))
        macd_htf = cfg.get("macd_htf", "4h")
        require_htf_green = bool(cfg.get("require_htf_green", True))
        require_vwap_uptrend = bool(cfg.get("require_vwap_uptrend", False))
        require_above_vwap = bool(cfg.get("require_above_vwap", False))
        require_volume_expand = bool(cfg.get("require_volume_expand", False))
        require_vol_confirm = bool(cfg.get("require_vol_confirm", False))
        block_red_flag = bool(cfg.get("block_red_flag", True))
        block_dump = bool(cfg.get("block_dump", True))
        require_sqz_release = bool(cfg.get("require_sqz_release", False))
        require_mom_pos = bool(cfg.get("require_mom_pos", False))
        require_mom_pos_inc = bool(cfg.get("require_mom_pos_inc", False))
        allow_healthy_pull_entry = bool(cfg.get("allow_healthy_pull_entry", False))
        exit_on_poc_break = bool(cfg.get("exit_on_poc_break", False))
        exit_on_val_break = bool(cfg.get("exit_on_val_break", False))
        exit_below_vwap = bool(cfg.get("exit_below_vwap", False))
        exit_on_sqz_neg = bool(cfg.get("exit_on_sqz_neg", False))
        soft_confidence = bool(cfg.get("soft_confidence", False))
        swing_period = int(cfg.get("swing_period", 50))
        vol_look = int(cfg.get("vol_look", 5))
        vol_sma = int(cfg.get("vol_sma", 20))
        min_confidence = float(cfg.get("min_confidence", 0.6))

        levels = _prior_session_profile(data, profile_lookback, profile_rows, value_area_pct)
        poc, vah, val = levels["poc"], levels["vah"], levels["val"]
        close = data["close"]
        poc_ok = (close >= poc) & poc.notna()
        in_va = (close >= val) & (close <= vah) & val.notna()
        htf = _htf_ha_green(data, macd_htf, macd_fast, macd_slow, macd_signal)
        local_ha = _standardized_macd_ha(data, macd_fast, macd_slow, macd_signal)
        swing = dynamic_swing_anchored_vwap(data, swing_period)
        vwap = swing["vwap"].shift(1)
        uptrend = swing["uptrend"].shift(1).fillna(False).astype(bool)
        above_vwap = (close >= vwap).fillna(False)
        vp = volume_price_state(data, vol_look, vol_sma)
        sqz = squeeze_momentum(data)
        gates = [poc_ok, in_va]
        if require_htf_green: gates.append(htf)
        if require_vwap_uptrend: gates.append(uptrend)
        if require_above_vwap: gates.append(above_vwap)
        if require_volume_expand: gates.append(vp["vol_expand"])
        if require_vol_confirm:
            gates.append(vp["confirm_up"] | (allow_healthy_pull_entry & vp["healthy_pull"] & above_vwap))
        if block_red_flag: gates.append(~vp["red_flag_up"])
        if block_dump: gates.append(~vp["dump"])
        if require_sqz_release: gates.append(sqz["sqz_release"] | sqz["sqz_off"])
        if require_mom_pos: gates.append(sqz["mom_pos"])
        if require_mom_pos_inc: gates.append(sqz["mom_pos_inc"])
        long_hard = gates[0]
        for g in gates[1:]:
            long_hard = long_hard & g
        if soft_confidence:
            parts = [poc_ok, in_va, htf, uptrend, above_vwap, vp["confirm_up"] | vp["healthy_pull"], ~vp["red_flag_up"], sqz["mom_pos"], sqz["sqz_off"] | sqz["sqz_release"]]
            total = None
            for p in parts:
                total = p.astype(float) if total is None else total + p.astype(float)
            conf = total / float(len(parts))
            long_entry = poc_ok & in_va & (conf >= min_confidence)
            if block_red_flag: long_entry = long_entry & (~vp["red_flag_up"])
            if block_dump: long_entry = long_entry & (~vp["dump"])
            if require_htf_green: long_entry = long_entry & htf
            size = conf.clip(0, 1)
        else:
            long_entry = long_hard
            size = pd.Series(1.0, index=data.index)
        signal = pd.Series(0.0, index=data.index)
        in_pos = False
        for i in range(len(data)):
            if not in_pos:
                if bool(long_entry.iloc[i]):
                    in_pos = True
                    signal.iloc[i] = float(size.iloc[i]) if soft_confidence else 1.0
            else:
                exit_now = False
                if require_htf_green and not bool(htf.iloc[i]): exit_now = True
                if exit_on_poc_break and not bool(poc_ok.iloc[i]): exit_now = True
                if exit_on_val_break and close.iloc[i] < val.iloc[i]: exit_now = True
                if exit_below_vwap and pd.notna(vwap.iloc[i]) and close.iloc[i] < vwap.iloc[i]: exit_now = True
                if exit_on_sqz_neg and bool(sqz["mom_neg"].iloc[i]): exit_now = True
                if bool(local_ha["ha_red"].iloc[i]) and not bool(htf.iloc[i]): exit_now = True
                if block_red_flag and bool(vp["red_flag_up"].iloc[i]): exit_now = True
                if exit_now:
                    in_pos = False
                    signal.iloc[i] = 0.0
                else:
                    signal.iloc[i] = float(size.iloc[i]) if soft_confidence else 1.0
                    in_pos = True
        return signal.fillna(0.0)

    def _one(self, code: str, df: pd.DataFrame) -> pd.Series:
        cfg = self._cfg(code)
        if not cfg:
            return pd.Series(0.0, index=df.index)
        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()
        data.columns = [str(c).lower() for c in data.columns]
        signal_tf = cfg.get("signal_tf") or None
        if signal_tf:
            frame = _resample_ohlcv(data, signal_tf)
            if frame.empty:
                return pd.Series(0.0, index=data.index)
            return self._signals_on_frame(frame, cfg).reindex(data.index, method="ffill").fillna(0.0)
        return self._signals_on_frame(data, cfg)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out = {}
        for code, df in data_map.items():
            resolved = _ALIAS.get(code, code)
            if resolved not in self.routing and f"{resolved}.US" not in self.routing and code not in self.routing:
                out[code] = pd.Series(0.0, index=df.index)
                continue
            out[code] = self._one(code, df)
        return out
