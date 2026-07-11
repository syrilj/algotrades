from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

# Per-symbol routing with volume-z optimized parameters
_ROUTING = {
    "TSLA.US": {"value_area_pct": 0.7, "profile_rows": 25, "profile_lookback": 15, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "macd_htf": '4h', "signal_tf": '1h', "require_htf_green": True, "require_vwap_uptrend": False, "require_above_vwap": False, "require_volume_expand": True, "require_vol_confirm": True, "block_red_flag": True, "block_dump": True, "require_sqz_release": False, "require_mom_pos": False, "require_mom_pos_inc": False, "allow_healthy_pull_entry": False, "exit_on_poc_break": False, "exit_on_val_break": False, "exit_below_vwap": False, "exit_on_sqz_neg": False, "soft_confidence": True, "swing_period": 50, "vol_look": 5, "vol_sma": 20, "min_confidence": 0.55, "stop_atr": 1.5, "trail_atr": 3.0, "arm_trail_atr": 1.2, "kelly_fraction": 0.5},
    "ARM.US": {"value_area_pct": 0.7, "profile_rows": 25, "profile_lookback": 10, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "macd_htf": '1D', "signal_tf": '2h', "require_htf_green": True, "require_vwap_uptrend": False, "require_above_vwap": True, "require_volume_expand": True, "require_vol_confirm": False, "block_red_flag": True, "block_dump": False, "require_sqz_release": False, "require_mom_pos": True, "require_mom_pos_inc": False, "allow_healthy_pull_entry": False, "exit_on_poc_break": False, "exit_on_val_break": False, "exit_below_vwap": True, "exit_on_sqz_neg": False, "soft_confidence": True, "swing_period": 50, "vol_look": 5, "vol_sma": 20, "min_confidence": 0.55, "stop_atr": 1.5, "trail_atr": 2.5, "arm_trail_atr": 1.0, "kelly_fraction": 0.5},
    "MU.US": {"value_area_pct": 0.7, "profile_rows": 25, "profile_lookback": 10, "macd_fast": 8, "macd_slow": 21, "macd_signal": 9, "macd_htf": '4h', "signal_tf": '1h', "require_htf_green": True, "require_vwap_uptrend": False, "require_above_vwap": False, "require_volume_expand": True, "require_vol_confirm": True, "block_red_flag": True, "block_dump": True, "require_sqz_release": False, "require_mom_pos": False, "require_mom_pos_inc": False, "allow_healthy_pull_entry": False, "exit_on_poc_break": False, "exit_on_val_break": False, "exit_below_vwap": False, "exit_on_sqz_neg": False, "soft_confidence": True, "swing_period": 50, "vol_look": 5, "vol_sma": 20, "min_confidence": 0.6, "stop_atr": 1.5, "trail_atr": 2.5, "arm_trail_atr": 1.0, "kelly_fraction": 0.5},
    "SPY.US": {"value_area_pct": 0.7, "profile_rows": 25, "profile_lookback": 20, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "macd_htf": '1D', "signal_tf": '4h', "require_htf_green": True, "require_vwap_uptrend": True, "require_above_vwap": True, "require_volume_expand": False, "require_vol_confirm": False, "block_red_flag": False, "block_dump": False, "require_sqz_release": False, "require_mom_pos": False, "require_mom_pos_inc": False, "allow_healthy_pull_entry": False, "exit_on_poc_break": False, "exit_on_val_break": False, "exit_below_vwap": True, "exit_on_sqz_neg": False, "soft_confidence": True, "swing_period": 50, "vol_look": 5, "vol_sma": 20, "min_confidence": 0.6, "stop_atr": 1.5, "trail_atr": 2.5, "arm_trail_atr": 1.0, "kelly_fraction": 0.5},
    "IONQ.US": {"value_area_pct": 0.7, "profile_rows": 25, "profile_lookback": 10, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "macd_htf": '1D', "signal_tf": '2h', "require_htf_green": True, "require_vwap_uptrend": True, "require_above_vwap": True, "require_volume_expand": True, "require_vol_confirm": True, "block_red_flag": True, "block_dump": False, "require_sqz_release": False, "require_mom_pos": True, "require_mom_pos_inc": False, "allow_healthy_pull_entry": False, "exit_on_poc_break": False, "exit_on_val_break": False, "exit_below_vwap": True, "exit_on_sqz_neg": False, "soft_confidence": True, "swing_period": 50, "vol_look": 5, "vol_sma": 20, "min_confidence": 0.6, "stop_atr": 2.0, "trail_atr": 3.5, "arm_trail_atr": 1.5, "kelly_fraction": 0.4},
    "APLD.US": {"value_area_pct": 0.7, "profile_rows": 25, "profile_lookback": 10, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "macd_htf": '4h', "signal_tf": '1h', "require_htf_green": True, "require_vwap_uptrend": True, "require_above_vwap": True, "require_volume_expand": True, "require_vol_confirm": True, "block_red_flag": True, "block_dump": True, "require_sqz_release": False, "require_mom_pos": True, "require_mom_pos_inc": False, "allow_healthy_pull_entry": False, "exit_on_poc_break": False, "exit_on_val_break": False, "exit_below_vwap": True, "exit_on_sqz_neg": False, "soft_confidence": True, "swing_period": 50, "vol_look": 5, "vol_sma": 20, "min_confidence": 0.55, "stop_atr": 2.0, "trail_atr": 3.5, "arm_trail_atr": 1.5, "kelly_fraction": 0.4},
}

_SYM_ONEHOT = ["TSLA", "ARM", "MU", "SPY", "IONQ", "APLD"]


def _daily_close(df: pd.DataFrame) -> pd.Series:
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    if getattr(d.index, "tz", None) is not None:
        d.index = d.index.tz_localize(None)
    return d["close"].resample("1D").last().dropna().astype(float)


def _xlp_spy_allow(xlp_df: pd.DataFrame, spy_df: pd.DataFrame) -> pd.Series:
    xlp = _daily_close(xlp_df)
    spy = _daily_close(spy_df)
    idx = xlp.index.intersection(spy.index)
    ratio = xlp.reindex(idx) / spy.reindex(idx)
    ma20 = ratio.rolling(20, min_periods=20).mean()
    ma50 = ratio.rolling(50, min_periods=50).mean()
    defensive = (ratio > ma20) & (ma20 > ma50)
    return (~defensive).astype(bool).shift(1).fillna(False)


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


def squeeze_momentum(df, length=20, mult_bb=2.0, length_kc=20, mult_kc=1.5):
    src = df["close"]
    basis = _sma(src, length)
    std = src.rolling(length, min_periods=max(2, length//2)).std(ddof=0)
    upper_bb = basis + mult_bb * std
    lower_bb = basis - mult_bb * std
    ma = _sma(src, length_kc)
    tr = pd.concat([
        df["high"]-df["low"],
        (df["high"]-df["close"].shift(1)).abs(),
        (df["low"]-df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    rangema = _sma(tr, length_kc)
    upper_kc = ma + rangema * mult_kc
    lower_kc = ma - rangema * mult_kc
    sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
    sqz_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
    highest = df["high"].rolling(length_kc, min_periods=1).max()
    lowest = df["low"].rolling(length_kc, min_periods=1).min()
    mid = ((highest + lowest) / 2.0 + _sma(src, length_kc)) / 2.0
    delta = src - mid
    def _linreg0(x):
        if np.any(~np.isfinite(x)): return np.nan
        n = len(x); t = np.arange(n, dtype=float); t_mean = t.mean(); x_mean = x.mean()
        denom = ((t - t_mean) ** 2).sum()
        if denom == 0: return x_mean
        slope = ((t - t_mean) * (x - x_mean)).sum() / denom
        intercept = x_mean - slope * t_mean
        return intercept + slope * (n - 1)
    val = delta.rolling(length_kc, min_periods=length_kc).apply(_linreg0, raw=True)
    val_prev = val.shift(1)
    mom_up = val > 0
    mom_up_inc = mom_up & (val > val_prev)
    squeeze_release = sqz_on.shift(1).fillna(False) & sqz_off
    return pd.DataFrame({
        "sqz_val": val,
        "sqz_on": sqz_on.fillna(False),
        "sqz_off": sqz_off.fillna(False),
        "sqz_release": squeeze_release.fillna(False),
        "mom_pos": mom_up.fillna(False),
        "mom_pos_inc": mom_up_inc.fillna(False),
        "mom_neg": (val < 0).fillna(False),
    }, index=df.index)


def volume_price_state(df, look=5, vol_sma=20):
    close = df["close"]
    vol = df["volume"]
    price_up = close > close.shift(look)
    price_dn = close < close.shift(look)
    vsma = _sma(vol, vol_sma)
    vol_up = vol > vsma
    vol_dn = vol < vsma
    vol_rising = vol > vol.shift(look)
    vol_falling = vol < vol.shift(look)
    confirm_up = price_up & (vol_up | vol_rising)
    red_flag_up = price_up & vol_falling & ~vol_up
    healthy_pull = price_dn & vol_falling
    dump = price_dn & vol_rising & vol_up
    return pd.DataFrame({
        "confirm_up": confirm_up.fillna(False),
        "red_flag_up": red_flag_up.fillna(False),
        "healthy_pull": healthy_pull.fillna(False),
        "dump": dump.fillna(False),
        "vol_expand": vol_up.fillna(False),
        "vol_z_20": ((vol - vsma) / vol.rolling(20, min_periods=10).std().replace(0, np.nan)).shift(1).fillna(0.0),
    }, index=df.index)


def _volume_profile_levels(highs, lows, volumes, rows, value_area_pct):
    price_high = float(np.max(highs)); price_low = float(np.min(lows))
    if not np.isfinite(price_high) or not np.isfinite(price_low) or price_high <= price_low:
        mid = float(np.nanmean((highs+lows)/2)); return mid, mid, mid
    step = (price_high - price_low) / rows
    if step <= 0:
        mid = (price_high+price_low)/2; return mid, price_high, price_low
    vol_bins = np.zeros(rows)
    for h,l,v in zip(highs, lows, volumes):
        if not np.isfinite(v) or v <= 0: continue
        br = h - l
        for level in range(rows):
            bin_lo = price_low + level*step
            if h >= bin_lo and l < bin_lo+step:
                vol_bins[level] += v * (1.0 if br==0 else step/br)
    if vol_bins.sum() <= 0:
        mid = (price_high+price_low)/2; return mid, price_high, price_low
    poc_level = int(np.argmax(vol_bins))
    target = vol_bins.sum() * value_area_pct
    value = vol_bins[poc_level]; above = below = poc_level
    while value < target:
        if below==0 and above==rows-1: break
        va = vol_bins[above+1] if above < rows-1 else 0.0
        vb = vol_bins[below-1] if below > 0 else 0.0
        if va==0 and vb==0: break
        if va >= vb: above += 1; value += va
        else: below -= 1; value += vb
    return float(price_low+(poc_level+0.5)*step), float(price_low+(above+1)*step), float(price_low+below*step)


def _prior_session_profile(df, lookback, rows, value_area_pct):
    n=len(df); poc=np.full(n,np.nan); vah=np.full(n,np.nan); val=np.full(n,np.nan)
    highs=df["high"].to_numpy(float); lows=df["low"].to_numpy(float); vols=df["volume"].to_numpy(float)
    for i in range(lookback, n):
        poc[i], vah[i], val[i] = _volume_profile_levels(highs[i-lookback:i], lows[i-lookback:i], vols[i-lookback:i], rows, value_area_pct)
    return pd.DataFrame({"poc":poc,"vah":vah,"val":val}, index=df.index)


def _resample_ohlcv(df, rule):
    return (df[["open","high","low","close","volume"]].resample(rule, label="right", closed="right")
            .agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["close"]))


def _htf_ha_green(df, htf, fast, slow, sig):
    htf_df = _resample_ohlcv(df, htf) if htf else df
    if htf_df.empty: return pd.Series(False, index=df.index)
    hl = (htf_df["high"] - htf_df["low"]).replace(0, np.nan)
    macd = (_ema(htf_df["close"], fast) - _ema(htf_df["close"], slow)) / _ema(hl, slow) * 100.0
    macd = macd.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    macd_prev = macd.shift(1).fillna(macd)
    o, h, l, c = macd_prev, np.maximum(macd, macd_prev), np.minimum(macd, macd_prev), macd
    ha_close = (o + h + l + c) / 4.0
    ha_open = pd.Series(index=htf_df.index, dtype=float)
    ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2.0
    for i in range(1, len(htf_df)):
        ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2.0
    ha = pd.DataFrame({"ha_close": ha_close, "ha_open": ha_open}, index=htf_df.index)
    ha["ha_green"] = ha["ha_close"] > ha["ha_open"]
    return ha["ha_green"].astype(float).shift(1).reindex(df.index, method="ffill").fillna(0)>0.5


def _standardized_macd_ha(df, fast=12, slow=26, signal_len=9):
    """Standardized MACD HA - standalone version for module-level calls."""
    src_px = df["close"]
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    macd = (_ema(src_px, fast) - _ema(src_px, slow)) / _ema(hl, slow) * 100.0
    macd = macd.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    macd_prev = macd.shift(1).fillna(macd)
    o, h, l, c = macd_prev, np.maximum(macd, macd_prev), np.minimum(macd, macd_prev), macd
    ha_close = (o + h + l + c) / 4.0
    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2.0
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2.0
    out = pd.DataFrame({"ha_close": ha_close, "ha_open": ha_open, "macd": macd}, index=df.index)
    out["ha_green"] = out["ha_close"] > out["ha_open"]
    out["ha_red"] = out["ha_close"] < out["ha_open"]
    return out


def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def _prob_to_size(p: float, thr: float) -> float:
    if p < thr: return 0.0
    if p < thr + 0.05: return 0.25
    if p < thr + 0.15: return 0.5
    return 1.0


def _risk_scale_size(meta_sz: float, atr_pct: float, med_atr_pct: float, kelly_fraction: float = 0.5) -> float:
    if meta_sz <= 0 or not np.isfinite(meta_sz): return 0.0
    base = float(meta_sz) * float(np.clip(kelly_fraction / 0.5, 0.5, 1.0))
    vol_scale = float(np.clip(med_atr_pct / max(atr_pct, 1e-9), 0.4, 1.25))
    return float(np.clip(base * vol_scale, 0.25, 1.0))


def _sector_rank_score(code: str, data_map: Dict, lookback_days: int = 20) -> float:
    """Compute sector rotation rank score for a symbol (0-1 normalized)."""
    from collections import defaultdict
    sectors = {
        "mag7": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "AVGO"],
        "memory": ["MU", "SNDK", "WDC", "STX", "AMD", "TSM", "ARM", "SMH", "INTC", "QCOM", "MRVL"],
        "quantum": ["IONQ", "RGTI", "QBTS", "QUBT"],
    }
    sym = code.replace(".US", "")
    sector_etf = {"mag7": "QQQ", "memory": "SMH", "quantum": None}
    
    best_score = 0.0
    for sec, members in sectors.items():
        if sym in members:
            etf = sector_etf.get(sec)
            if etf and etf in data_map:
                px = data_map[etf]["close"]
                spy_px = data_map.get("SPY.US", data_map.get("QQQ", pd.DataFrame())["close"])
                if len(px) > lookback_days and len(spy_px) > lookback_days:
                    ret_5 = float(px.iloc[-1] / px.iloc[-6] - 1) if len(px) > 6 else 0.0
                    spy_5 = float(spy_px.iloc[-1] / spy_px.iloc[-6] - 1) if len(spy_px) > 6 else 0.0
                    rs_5 = ret_5 - spy_5
                    score = float(np.clip((rs_5 + 0.15) / 0.30, 0.0, 1.0))  # normalize
                    best_score = max(best_score, score)
    return best_score


def _volume_z_filter(val: float) -> float:
    """Map volume z-score to confidence boost (0-1)."""
    if not np.isfinite(val): return 0.0
    if val >= 2.0: return 1.0
    if val >= 1.0: return 0.7
    if val >= 0.0: return 0.5
    if val >= -1.0: return 0.3
    return 0.0


class SignalEngine:
    """v22: v20b + volume-z boosted confidence + sector rank integration."""

    def __init__(self):
        self.routing = _ROUTING
        self._spy_htf: Optional[pd.Series] = None
        self._sector_scores: Dict[str, float] = {}

    def _cfg(self, code):
        return self.routing.get(code, self.routing.get("SPY.US", {}))

    def _enhanced_confidence(self, conf_base: float, vol_z: float, sector_score: float) -> float:
        """Boost base confidence with volume z and sector rank."""
        vol_boost = _volume_z_filter(vol_z)
        sector_boost = sector_score
        return float(np.clip(0.6 * conf_base + 0.25 * vol_boost + 0.15 * sector_boost, 0.0, 1.0))

    def _signals_on_frame(self, data, cfg, code: str, sector_score: float = 0.0):
        value_area_pct=cfg.get("value_area_pct",0.7); profile_rows=int(cfg.get("profile_rows",25))
        profile_lookback=int(cfg.get("profile_lookback",20))
        macd_fast=int(cfg.get("macd_fast",12)); macd_slow=int(cfg.get("macd_slow",26)); macd_signal=int(cfg.get("macd_signal",9))
        macd_htf=cfg.get("macd_htf","4h"); require_htf_green=bool(cfg.get("require_htf_green",True))
        require_vwap_uptrend=bool(cfg.get("require_vwap_uptrend",False)); require_above_vwap=bool(cfg.get("require_above_vwap",False))
        require_volume_expand=bool(cfg.get("require_volume_expand",False)); require_vol_confirm=bool(cfg.get("require_vol_confirm",False))
        block_red_flag=bool(cfg.get("block_red_flag",False)); block_dump=bool(cfg.get("block_dump",False))
        require_sqz_release=bool(cfg.get("require_sqz_release",False)); require_mom_pos=bool(cfg.get("require_mom_pos",False))
        require_mom_pos_inc=bool(cfg.get("require_mom_pos_inc",False)); allow_healthy_pull_entry=bool(cfg.get("allow_healthy_pull_entry",False))
        exit_on_poc_break=bool(cfg.get("exit_on_poc_break",False)); exit_on_val_break=bool(cfg.get("exit_on_val_break",False))
        exit_below_vwap=bool(cfg.get("exit_below_vwap",False)); exit_on_sqz_neg=bool(cfg.get("exit_on_sqz_neg",False))
        soft_confidence=bool(cfg.get("soft_confidence",False)); swing_period=int(cfg.get("swing_period",50))
        vol_look=int(cfg.get("vol_look",5)); vol_sma=int(cfg.get("vol_sma",20)); min_confidence=float(cfg.get("min_confidence",0.6))
        stop_atr=float(cfg.get("stop_atr",1.5)); trail_atr=float(cfg.get("trail_atr",2.5))
        arm_trail_atr=float(cfg.get("arm_trail_atr",1.0)); kelly_fraction=float(cfg.get("kelly_fraction",0.5))
        
        levels=_prior_session_profile(data,profile_lookback,profile_rows,value_area_pct)
        poc,vah,val=levels["poc"],levels["vah"],levels["val"]; close=data["close"]
        poc_ok=(close>=poc)&poc.notna(); in_va=(close>=val)&(close<=vah)&val.notna()
        htf=_htf_ha_green(data,macd_htf,macd_fast,macd_slow,macd_signal)
        local_ha=_standardized_macd_ha(data,macd_fast,macd_slow,macd_signal)
        macd_hist=local_ha["macd"]-_ema(local_ha["macd"], macd_signal)
        swing=dynamic_swing_anchored_vwap(data,swing_period); vwap=swing["vwap"].shift(1)
        uptrend=swing["uptrend"].shift(1).fillna(False).astype(bool); above_vwap=(close>=vwap).fillna(False)
        vp=volume_price_state(data,vol_look,vol_sma); sqz=squeeze_momentum(data)
        atr=_atr(data).replace(0,np.nan)
        atr_pct=(atr/close.replace(0,np.nan)).fillna(0.0)
        med_atr_pct=float(atr_pct.replace(0,np.nan).median())
        if not np.isfinite(med_atr_pct) or med_atr_pct<=0:
            med_atr_pct=float(atr_pct.mean()) if atr_pct.mean()>0 else 0.02
        
        # Enhanced confidence with volume-z + sector
        vol_z_val = float(vp["vol_z_20"].iloc[-1]) if len(vp) > 0 else 0.0
        enhanced_conf = self._enhanced_confidence(0.5, vol_z_val, sector_score)
        
        gates=[poc_ok,in_va]
        if require_htf_green: gates.append(htf)
        if require_vwap_uptrend: gates.append(uptrend)
        if require_above_vwap: gates.append(above_vwap)
        if require_volume_expand: gates.append(vp["vol_expand"])
        if require_vol_confirm: gates.append(vp["confirm_up"]|(allow_healthy_pull_entry&vp["healthy_pull"]&above_vwap))
        if block_red_flag: gates.append(~vp["red_flag_up"])
        if block_dump: gates.append(~vp["dump"])
        if require_sqz_release: gates.append(sqz["sqz_release"]|sqz["sqz_off"])
        if require_mom_pos: gates.append(sqz["mom_pos"])
        if require_mom_pos_inc: gates.append(sqz["mom_pos_inc"])
        
        long_hard=gates[0]
        for g in gates[1:]: long_hard=long_hard&g
        
        # Use enhanced confidence for entry decision
        vol_z_ge2 = vp["vol_z_20"] >= 2.0
        long_entry = long_hard & (enhanced_conf >= min_confidence) & vol_z_ge2.shift(1).fillna(False)
        
        signal=pd.Series(0.0,index=data.index); in_pos=False; entry_size=0.0
        entry_px=np.nan; peak_px=np.nan; entry_atr=np.nan
        for i in range(len(data)):
            px=float(close.iloc[i])
            a=float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else 0.0
            if not in_pos:
                if bool(long_entry.iloc[i]):
                    # Simplified meta: use enhanced confidence for sizing
                    conf_val = enhanced_conf
                    meta_sz = _prob_to_size(conf_val, 0.5)
                    sz=_risk_scale_size(meta_sz, float(atr_pct.iloc[i]), med_atr_pct, kelly_fraction)
                    if sz>0:
                        in_pos=True; entry_size=sz; signal.iloc[i]=sz
                        entry_px=px; peak_px=px; entry_atr=a if a>0 else px*0.01
            else:
                peak_px=max(peak_px, float(data["high"].iloc[i]))
                hard_stop=px<=entry_px-stop_atr*entry_atr
                armed=peak_px>=entry_px+arm_trail_atr*entry_atr
                trail_stop=armed and (px<=peak_px-trail_atr*entry_atr)
                soft_exit=False
                if not armed:
                    if require_htf_green and not bool(htf.iloc[i]): soft_exit=True
                    if exit_on_poc_break and not bool(poc_ok.iloc[i]): soft_exit=True
                    if exit_on_val_break and close.iloc[i]<val.iloc[i]: soft_exit=True
                    if exit_below_vwap and pd.notna(vwap.iloc[i]) and px<float(vwap.iloc[i]): soft_exit=True
                if hard_stop or trail_stop or soft_exit:
                    in_pos=False; signal.iloc[i]=0.0; entry_size=0.0
                    entry_px=peak_px=entry_atr=np.nan
                else:
                    signal.iloc[i]=entry_size; in_pos=True
        return signal.fillna(0.0)

    def _one(self, code, df, sector_score=0.0):
        cfg=self._cfg(code); data=df.copy(); data.index=pd.to_datetime(data.index)
        if getattr(data.index,"tz",None) is not None: data.index=data.index.tz_localize(None)
        data=data.sort_index(); signal_tf=cfg.get("signal_tf","2h")
        if signal_tf:
            frame=_resample_ohlcv(data,signal_tf)
            if frame.empty: return pd.Series(0.0,index=data.index)
            return self._signals_on_frame(frame,cfg,code,sector_score).reindex(data.index,method="ffill").fillna(0.0)
        return self._signals_on_frame(data,cfg,code,sector_score)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        # Pre-compute sector scores
        self._sector_scores = {_code: _sector_rank_score(_code, data_map) for _code in data_map.keys()}
        
        spy_df = data_map.get("SPY.US")
        if spy_df is not None and not spy_df.empty:
            sdf = spy_df.copy()
            sdf.index = pd.to_datetime(sdf.index)
            if getattr(sdf.index, "tz", None) is not None:
                sdf.index = sdf.index.tz_localize(None)
            self._spy_htf = _htf_ha_green(sdf, "4h", 12, 26, 9).astype(float)
        else:
            self._spy_htf = None

        xlp_df = data_map.get("XLP.US")
        macro_allow = None
        if spy_df is not None and xlp_df is not None and not xlp_df.empty:
            macro_allow = _xlp_spy_allow(xlp_df, spy_df)

        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            sector_score = self._sector_scores.get(code, 0.0)
            sig = self._one(code, df, sector_score)
            if macro_allow is None:
                out[code] = sig
                continue
            idx = pd.to_datetime(sig.index)
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_localize(None)
            days = idx.normalize()
            g = macro_allow.reindex(days).ffill().fillna(False)
            g.index = sig.index
            out[code] = sig.where(g.astype(bool), 0.0).astype(float)
        return out