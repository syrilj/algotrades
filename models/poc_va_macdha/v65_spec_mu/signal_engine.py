from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

# Literal-only top-level assigns (backtest runner AST sandbox).
_SYM_ONEHOT = ["TSLA", "ARM", "MU", "SPY", "IONQ", "APLD"]

_ROUTING = {'MU.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': False, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': True, 'block_dump': True, 'require_sqz_release': False, 'require_mom_pos': False, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': False, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6, 'max_hold_bars': 15, 'max_loss_pct': 0.025}, 'SPY.US': {'value_area_pct': 0.7, 'profile_rows': 25, 'profile_lookback': 20, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9, 'macd_htf': '4h', 'signal_tf': '2h', 'require_htf_green': True, 'require_vwap_uptrend': False, 'require_above_vwap': False, 'require_volume_expand': False, 'require_vol_confirm': False, 'block_red_flag': True, 'block_dump': True, 'require_sqz_release': False, 'require_mom_pos': False, 'require_mom_pos_inc': False, 'allow_healthy_pull_entry': False, 'exit_on_poc_break': False, 'exit_on_val_break': False, 'exit_below_vwap': False, 'exit_on_sqz_neg': False, 'soft_confidence': False, 'swing_period': 50, 'vol_look': 5, 'vol_sma': 20, 'min_confidence': 0.6, 'max_hold_bars': 15, 'max_loss_pct': 0.025}}


TRADE_DROP = {"__none__"}
REGIME_FLAT = {"__none__"}


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


def squeeze_momentum(df, length=20, mult_bb=2.0, length_kc=20, mult_kc=1.5, use_tr=True):
    """LazyBear SQZMOM_LB."""
    src = df["close"]
    basis = _sma(src, length)
    # LazyBear BB uses multKC * stdev in original script (known quirk) — match LazyBear exactly
    dev = mult_kc * src.rolling(length, min_periods=length).std(ddof=0)
    upper_bb = basis + mult_bb * src.rolling(length, min_periods=length).std(ddof=0)
    lower_bb = basis - mult_bb * src.rolling(length, min_periods=length).std(ddof=0)
    # Recreate as published: basis=sma, upperBB=basis+mult*stdev — use BB mult for BB
    std = src.rolling(length, min_periods=max(2, length//2)).std(ddof=0)
    upper_bb = basis + mult_bb * std
    lower_bb = basis - mult_bb * std
    ma = _sma(src, length_kc)
    tr = pd.concat([
        df["high"]-df["low"],
        (df["high"]-df["close"].shift(1)).abs(),
        (df["low"]-df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    rng = tr if use_tr else (df["high"] - df["low"])
    rangema = _sma(rng, length_kc)
    upper_kc = ma + rangema * mult_kc
    lower_kc = ma - rangema * mult_kc
    sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
    sqz_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
    # linreg of (src - avg(avg(highest,lowest), sma))
    highest = df["high"].rolling(length_kc, min_periods=1).max()
    lowest = df["low"].rolling(length_kc, min_periods=1).min()
    mid = ((highest + lowest) / 2.0 + _sma(src, length_kc)) / 2.0
    delta = src - mid
    # rolling linear regression value at end of window (slope*0 + intercept relative) == linreg(...,0)
    def _linreg0(x):
        if np.any(~np.isfinite(x)):
            return np.nan
        n = len(x)
        t = np.arange(n, dtype=float)
        t_mean = t.mean()
        x_mean = x.mean()
        denom = ((t - t_mean) ** 2).sum()
        if denom == 0:
            return x_mean
        slope = ((t - t_mean) * (x - x_mean)).sum() / denom
        intercept = x_mean - slope * t_mean
        return intercept + slope * (n - 1)  # value at last bar of window

    val = delta.rolling(length_kc, min_periods=length_kc).apply(_linreg0, raw=True)
    val_prev = val.shift(1)
    mom_up = val > 0
    mom_up_inc = mom_up & (val > val_prev)
    mom_dn = val < 0
    squeeze_release = sqz_on.shift(1).fillna(False) & sqz_off  # just released
    return pd.DataFrame({
        "sqz_val": val,
        "sqz_on": sqz_on.fillna(False),
        "sqz_off": sqz_off.fillna(False),
        "sqz_release": squeeze_release.fillna(False),
        "mom_pos": mom_up.fillna(False),
        "mom_pos_inc": mom_up_inc.fillna(False),
        "mom_neg": mom_dn.fillna(False),
    }, index=df.index)


def volume_price_state(df, look=3, vol_sma=14, stop_look=5):
    """Coulling VPA + continuous score (v39b live-adapt).

    Faster defaults than v39 (look=3, vol_sma=14, stop_look=5) so tape
    changes show up in ~1–3 bars instead of lagging a full day of 1H bars.

    Negatives halved vs v39 (capacity kill on WINNER bag). Philosophy:
      react to volume effort at nodes — do not predict price.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    open_ = df["open"].astype(float) if "open" in df.columns else close
    vol = df["volume"].astype(float)

    price_up = close > close.shift(look)
    price_dn = close < close.shift(look)
    vsma = _sma(vol, vol_sma)
    vol_up = vol > vsma
    vol_rising = vol > vol.shift(look)
    vol_falling = vol < vol.shift(look)

    confirm_up = price_up & (vol_up | vol_rising)
    red_flag_up = price_up & vol_falling & ~vol_up
    healthy_pull = price_dn & vol_falling
    dump = price_dn & vol_rising & vol_up

    spread = (high - low).replace(0, np.nan)
    spread_ma = spread.rolling(14, min_periods=4).mean()
    narrow = spread < (0.75 * spread_ma)
    wide = spread > (1.25 * spread_ma)
    vol_low = vol < (0.70 * vsma)
    vol_high = vol > (1.5 * vsma)
    vol_climax = vol > (2.0 * vsma)

    green = close > open_
    red = close < open_
    ret1 = close.pct_change(1)

    prior_dn = close.shift(1) < close.shift(look + 1)
    prior_up = close.shift(1) > close.shift(look + 1)
    stopping_volume = (prior_dn & vol_high & narrow).fillna(False)
    topping_volume = (prior_up & vol_high & narrow).fillna(False)
    no_demand = ((price_up | green) & vol_low).fillna(False)
    no_supply = ((price_dn | red) & vol_low).fillna(False)
    effort_anomaly = ((wide & vol_low) | (wide & price_up & ~vol_up & vol_falling)).fillna(False)
    buying_climax = (price_up & vol_climax & wide).fillna(False)
    selling_climax = (price_dn & vol_climax & wide).fillna(False)

    stop_recent = stopping_volume.rolling(stop_look, min_periods=1).max().astype(bool)
    top_recent = topping_volume.rolling(stop_look, min_periods=1).max().astype(bool)
    climax_recent = buying_climax.rolling(stop_look, min_periods=1).max().astype(bool)

    stopping_reclaim = (stop_recent & green & (ret1 > 0.004) & ~dump).fillna(False)
    no_supply_test = (stop_recent & no_supply & green).fillna(False)
    commitment = (confirm_up | stopping_reclaim | no_supply_test).fillna(False)

    prior_high = high.shift(1).rolling(look, min_periods=2).max()
    prior_low = low.shift(1).rolling(look, min_periods=2).min()
    upthrust = ((high > prior_high) & (close < open_) & (close < prior_high)).fillna(False)
    spring = ((low < prior_low) & (close > open_) & (close > prior_low)).fillna(False)

    # Lighter negatives (ablation C) — keep positives strong for live reaction
    score = (
        stopping_reclaim.astype(float) * 1.00
        + no_supply_test.astype(float) * 0.75
        + spring.astype(float) * 0.55
        + confirm_up.astype(float) * 0.50
        + healthy_pull.astype(float) * 0.20
        + stopping_volume.astype(float) * 0.25
        - no_demand.astype(float) * 0.40
        - climax_recent.astype(float) * 0.45
        - effort_anomaly.astype(float) * 0.30
        - top_recent.astype(float) * 0.28
        - upthrust.astype(float) * 0.35
        - dump.astype(float) * 0.40
        - red_flag_up.astype(float) * 0.22
    )
    vpa_score = score.clip(-2.0, 2.5)

    # Fast live adapt: score momentum vs recent mean (improving / decaying effort)
    vpa_ma = vpa_score.rolling(8, min_periods=3).mean()
    vpa_mom = (vpa_score - vpa_ma).fillna(0.0).clip(-1.5, 1.5)

    vol_std = vol.rolling(14, min_periods=6).std().replace(0, np.nan)
    vol_z = ((vol - vsma) / vol_std).shift(1).fillna(0.0)
    # Regime: high recent |vol_z| → trust volume signals more
    vol_regime = vol_z.abs().rolling(10, min_periods=3).mean().fillna(0.5).clip(0.0, 3.0)

    return pd.DataFrame({
        "confirm_up": confirm_up.fillna(False),
        "red_flag_up": red_flag_up.fillna(False),
        "healthy_pull": healthy_pull.fillna(False),
        "dump": dump.fillna(False),
        "vol_expand": vol_up.fillna(False),
        "vol_z": vol_z,
        "vol_regime": vol_regime,
        "no_demand": no_demand,
        "no_supply": no_supply,
        "no_supply_test": no_supply_test,
        "stopping_volume": stopping_volume,
        "stopping_reclaim": stopping_reclaim,
        "topping_volume": topping_volume,
        "effort_anomaly": effort_anomaly,
        "buying_climax": buying_climax,
        "climax_recent": climax_recent,
        "upthrust": upthrust,
        "spring": spring,
        "commitment": commitment,
        "vpa_score": vpa_score.fillna(0.0),
        "vpa_mom": vpa_mom,
    }, index=df.index)


def ema_cloud_state(df, fast=9, mid=21, slow=55):
    """EMA cloud path context — where tape is trying to head (soft only).

    Bull stack: fast > mid > slow. Bear stack inverted.
    Does not choose SIDE; only soft-sizes reactions near nodes.
    """
    close = df["close"].astype(float)
    e_fast = _ema(close, fast)
    e_mid = _ema(close, mid)
    e_slow = _ema(close, slow)
    bull = (e_fast > e_mid) & (e_mid > e_slow)
    bear = (e_fast < e_mid) & (e_mid < e_slow)
    above = close >= e_fast
    # Distance into cloud as soft pressure (0 = at cloud, >0 above)
    cloud_top = pd.concat([e_fast, e_mid, e_slow], axis=1).max(axis=1)
    cloud_bot = pd.concat([e_fast, e_mid, e_slow], axis=1).min(axis=1)
    mid_c = (cloud_top + cloud_bot) / 2.0
    dist = (close - mid_c) / close.replace(0, np.nan)
    return pd.DataFrame({
        "ema_bull": bull.fillna(False),
        "ema_bear": bear.fillna(False),
        "above_cloud": above.fillna(False),
        "cloud_dist": dist.fillna(0.0),
        "ema_fast": e_fast,
        "ema_mid": e_mid,
        "ema_slow": e_slow,
    }, index=df.index)


def vpa_score_to_mult(score: float, mom: float = 0.0, vol_regime: float = 0.5) -> float:
    """Map continuous VPA score → size mult (never zero).

    Live adapt:
      - mom > 0: volume story improving → lean in
      - mom < 0: story fading → lean out
      - high vol_regime: trust VPA more (scale extremes)
    """
    if not np.isfinite(score):
        return 1.0
    s = float(score)
    if np.isfinite(mom):
        s = s + 0.35 * float(mom)
    # amplify score when volume environment is informative
    if np.isfinite(vol_regime) and vol_regime > 0.8:
        s = s * (1.0 + 0.15 * min(vol_regime, 2.0))
    if s >= 1.25:
        return 1.20
    if s >= 0.60:
        return 1.12
    if s >= 0.20:
        return 1.06
    if s >= -0.20:
        return 1.00
    if s >= -0.70:
        return 0.82
    if s >= -1.25:
        return 0.68
    return 0.55


def _live_streak_update(streak_mult: float, won: bool, consec: int, after_win: float, after_loss: float) -> tuple:
    """Faster adaptive streak for live: stacks wins/losses, mean-reverts toward 1."""
    if won:
        consec = consec + 1 if consec > 0 else 1
        boost = after_win * (1.0 + 0.04 * min(consec, 4))
        streak_mult = min(1.45, streak_mult * 0.35 + boost * 0.65)
    else:
        consec = consec - 1 if consec < 0 else -1
        cut = after_loss * (1.0 - 0.05 * min(abs(consec), 4))
        streak_mult = max(0.45, streak_mult * 0.40 + cut * 0.60)
    # pull toward neutral so one bad day does not freeze the desk forever
    streak_mult = 0.85 * streak_mult + 0.15 * 1.0
    return float(np.clip(streak_mult, 0.45, 1.45)), int(consec)


def _standardized_macd_ha(df, fast=12, slow=26, signal_len=9):
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
    ha = _standardized_macd_ha(htf_df, fast, slow, sig)
    return ha["ha_green"].astype(float).shift(1).reindex(df.index, method="ffill").fillna(0)>0.5




def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


# Research genome (v36 evolve train) — secondary knobs only
_GENOME = {
    "risk_pct": 0.1299,
    "after_loss_mult": 0.730,
    "after_win_mult": 1.090,
    "soft_dd": 0.099,
    "struct_good_mult": 1.15,
    "struct_weak_mult": 0.55,
    "meta_p_skip": 0.50,
    "meta_p_full": 0.68,
}


def _prob_to_size(p: float, thr: float) -> float:
    """Continuous soft size from meta P(win).

    Merges v37 continuous map + v36 genome meta breakpoints.
    Soft skip ~0.50 (not 0.60 hard); full ~0.68; half-Kelly blend.
    """
    if not np.isfinite(p):
        return 0.0
    skip = min(float(thr), float(_GENOME["meta_p_skip"]))
    if p < skip:
        return 0.0
    full_at = max(skip + 0.15, float(_GENOME["meta_p_full"]))
    if p >= full_at:
        base = 1.0
    else:
        t = (p - skip) / max(full_at - skip, 1e-9)
        base = 0.25 + 0.75 * float(np.clip(t, 0.0, 1.0))
    b = 1.90
    edge = p * b - (1.0 - p)
    if edge <= 0:
        return 0.0
    kelly = 0.5 * edge / b
    blended = 0.55 * base + 0.45 * float(np.clip(kelly / 0.28, 0.25, 1.0))
    return float(np.clip(blended, 0.25, 1.0))


def _risk_scale_size(meta_sz: float, atr_pct: float, med_atr_pct: float, kelly_fraction: float = 0.5) -> float:
    """Vol/Kelly scale on top of meta size; never revive a meta zero-out."""
    if meta_sz <= 0 or not np.isfinite(meta_sz):
        return 0.0
    base = float(meta_sz) * float(np.clip(kelly_fraction / 0.5, 0.5, 1.0))
    vol_scale = float(np.clip(med_atr_pct / max(atr_pct, 1e-9), 0.4, 1.25))
    return float(np.clip(base * vol_scale, 0.20, 1.0))


def _volume_z_boost(vol_z: float) -> float:
    """Map volume z-score to a small confidence boost for sizing.

    vol_z >= 1.0 has shown OOS lift; penalize very low vol_z to avoid
    weak entries while keeping a small positive boost.
    """
    if not np.isfinite(vol_z):
        return 0.0
    if vol_z >= 2.0:
        return 0.04
    if vol_z >= 1.0:
        return 0.02
    if vol_z >= 0.0:
        return 0.0
    if vol_z >= -1.0:
        return -0.02
    return -0.04


def _soft_feature_mult(
    atr_pct: float,
    med_atr_pct: float,
    room_pct: float,
    macd_hist: float,
    ret_5d: float,
    structure_good: bool,
    chase: bool,
    vpa_score: float = 0.0,
    vpa_mom: float = 0.0,
    vol_regime: float = 0.5,
    demand_node: bool = False,
    ema_bull: bool = False,
    ema_bear: bool = False,
    high_beta_qqq_weak: bool = False,
) -> float:
    """Soft size mult — live-adapt stack. Never hard-blocks.

    Ablations from v39 fail:
      - no stand-aside floor
      - EMA bear only mild (0.90 not 0.78)
      - lighter VPA negatives via score map
      - + vpa_mom + vol_regime for rapid tape adapt
    """
    m = 1.0
    good_m = float(_GENOME["struct_good_mult"])
    weak_m = float(_GENOME["struct_weak_mult"])
    if np.isfinite(atr_pct) and np.isfinite(med_atr_pct) and med_atr_pct > 0:
        if atr_pct > 1.45 * med_atr_pct:
            m *= 0.72
        elif atr_pct > 1.15 * med_atr_pct:
            m *= 0.88
        elif atr_pct < 0.70 * med_atr_pct:
            m *= 1.06
    if np.isfinite(room_pct):
        if room_pct >= 0.04:
            m *= 1.12
        elif room_pct >= 0.02:
            m *= 1.05
        elif room_pct < 0.008:
            m *= 0.68
    if np.isfinite(macd_hist) and abs(macd_hist) > 0.0:
        mh = abs(float(macd_hist))
        if mh > 1.5:
            m *= 0.82
        elif mh > 0.8:
            m *= 0.92
    if np.isfinite(ret_5d):
        if ret_5d > 0.15:
            m *= 0.55
        elif ret_5d > 0.08:
            m *= 0.80
        elif ret_5d < -0.08:
            m *= 1.05
    if structure_good:
        m *= good_m
    if chase:
        m *= weak_m
    m *= vpa_score_to_mult(vpa_score, vpa_mom, vol_regime)
    # Demand node reaction (inventory zones)
    if demand_node and float(vpa_score) + 0.25 * float(vpa_mom) >= 0.0:
        m *= 1.12
    # A+ confluence: structure + demand + supportive VPA (book commitment)
    if (
        structure_good
        and demand_node
        and float(vpa_score) >= 0.20
        and float(vpa_mom) >= -0.10
    ):
        m *= 1.12
    # EMA: bull soft boost; bear only mild (ablation B)
    if ema_bull:
        m *= 1.06
    if ema_bear:
        m *= 0.90
    if high_beta_qqq_weak:
        m *= 0.70
    return float(np.clip(m, 0.35, 1.50))


def _sector_rs_score(code: str, data_map: Dict, lookback_days: int = 5) -> float:
    """Sector relative strength vs SPY (0-1, 0.5 = neutral)."""
    sym = code.replace(".US", "")
    sectors = {
        "mag7": (["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "AVGO"], "QQQ"),
        "memory": (["MU", "SNDK", "WDC", "STX", "AMD", "TSM", "ARM", "SMH", "INTC", "QCOM", "MRVL"], "SMH"),
        "quantum": (["IONQ", "RGTI", "QBTS", "QUBT"], None),
    }
    etf = None
    for _, (members, etf_name) in sectors.items():
        if sym in members:
            etf = etf_name
            break
    if etf is None or etf not in data_map:
        return 0.5
    etf_px = data_map[etf]["close"]
    spy_px = data_map.get("SPY.US", pd.DataFrame())["close"]
    if len(etf_px) <= lookback_days or len(spy_px) <= lookback_days:
        return 0.5
    try:
        etf_ret = float(etf_px.iloc[-1] / etf_px.iloc[-lookback_days-1] - 1)
        spy_ret = float(spy_px.iloc[-1] / spy_px.iloc[-lookback_days-1] - 1)
        rs = etf_ret - spy_ret
        return float(np.clip((rs + 0.05) / 0.10, 0.0, 1.0))
    except Exception:
        return 0.5


def _qqq_rs_score(data_map: Dict, lookback_days: int = 5) -> float:
    """QQQ vs SPY relative strength (0-1, 0.5 = neutral)."""
    qqq = data_map.get("QQQ.US")
    spy = data_map.get("SPY.US")
    if qqq is None or spy is None or qqq.empty or spy.empty:
        return 0.5
    qqq_px = qqq["close"]
    spy_px = spy["close"]
    if len(qqq_px) <= lookback_days or len(spy_px) <= lookback_days:
        return 0.5
    try:
        qqq_ret = float(qqq_px.iloc[-1] / qqq_px.iloc[-lookback_days-1] - 1)
        spy_ret = float(spy_px.iloc[-1] / spy_px.iloc[-lookback_days-1] - 1)
        rs = qqq_ret - spy_ret
        return float(np.clip((rs + 0.05) / 0.10, 0.0, 1.0))
    except Exception:
        return 0.5


_HIGH_BETA = {"TSLA.US", "IONQ.US", "APLD.US", "ARM.US"}


class SignalEngine:
    """v39d_confluence: v39b + A+ confluence size + calmer exits.

    Keeps v39b live VPA stack. Adds:
      - size boost when demand_node + structure_good + VPA supportive (book commitment)
      - VPA soft exits only with dump/red_flag confirmation (less early over-exit)
      - mid-trade shrink only when underwater
      - seed streak from runs/live_adapt STATE.json when present

    Forbidden: climax hard-stacks, price ML primary, dual-speed score blends (v39c fail).
    """

    def __init__(self):
        self.routing = _ROUTING
        model_dir = Path(__file__).resolve().parent
        meta_cfg_path = model_dir / "meta_config.json"
        meta_booster_path = model_dir / "meta_xgb_final.json"
        self._meta_cfg = json.loads(meta_cfg_path.read_text(encoding="utf-8"))
        self._thr = float(self._meta_cfg.get("threshold", _GENOME["meta_p_skip"]))
        self._feat_cols = list(self._meta_cfg["feat_cols"])
        if str(model_dir) not in sys.path:
            sys.path.insert(0, str(model_dir))
        import candidate_ledger

        self._ledger = candidate_ledger.CandidateLedger(model_dir.parent, self._feat_cols)
        self._booster = XGBClassifier()
        self._booster.load_model(str(meta_booster_path))
        self._spy_htf: Optional[pd.Series] = None
        self._active_code = "SPY.US"
        self._risk_scale = max(0.20, min(2.0, float(_GENOME["risk_pct"]) / 0.10))
        self._after_loss = float(_GENOME["after_loss_mult"])
        self._after_win = float(_GENOME["after_win_mult"])
        # Live adaptive state (persists across generate() when desk reuses engine)
        self._live_streak = 1.0
        self._live_consec = 0
        self._live_trades: list = []
        self._last_adapt: dict = {}
        # Seed from desk paper-adapt file if present
        try:
            import live_adapt as _la

            self._live_streak = float(_la.size_mult_for("v39d_confluence") or 1.0)
            # prefer model-specific if any history under v39b lineage
            m39 = float(_la.size_mult_for("v39b_live_adapt") or 1.0)
            self._live_streak = float(np.clip(0.5 * self._live_streak + 0.5 * m39, 0.45, 1.45))
        except Exception:
            pass

    def record_trade(self, pnl: float, symbol: str = "", tags: Optional[dict] = None) -> dict:
        """Call after each live/paper fill outcome so size adapts next plan."""
        won = float(pnl) >= 0.0
        self._live_streak, self._live_consec = _live_streak_update(
            self._live_streak, won, self._live_consec, self._after_win, self._after_loss
        )
        rec = {
            "symbol": symbol,
            "pnl": float(pnl),
            "won": won,
            "streak_mult": self._live_streak,
            "consec": self._live_consec,
            "tags": tags or {},
        }
        self._live_trades.append(rec)
        if len(self._live_trades) > 50:
            self._live_trades = self._live_trades[-50:]
        return rec

    def live_adapt_snapshot(self) -> dict:
        """Desk helper: current adaptive knobs + last VPA read."""
        recent = self._live_trades[-8:]
        wr = (sum(1 for t in recent if t["won"]) / len(recent)) if recent else None
        return {
            "streak_mult": self._live_streak,
            "consec": self._live_consec,
            "recent_n": len(recent),
            "recent_wr": wr,
            "last_adapt": dict(self._last_adapt),
            "philosophy": "react_nodes_vpa_fast",
        }

    def _cfg(self, code):
        return self.routing.get(code, self.routing.get("SPY.US", {}))

    def _meta_row(self, code, i, close, poc, val, vwap, atr, local_ha, macd_hist, above_vwap, vp, htf, conf, spy_reg):
        a0 = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else np.nan
        px = float(close.iloc[i])
        dist_poc = (px - float(poc.iloc[i])) / a0 if pd.notna(poc.iloc[i]) and a0 == a0 and a0 else 0.0
        dist_val = (px - float(val.iloc[i])) / a0 if pd.notna(val.iloc[i]) and a0 == a0 and a0 else 0.0
        dist_vwap = (px - float(vwap.iloc[i])) / a0 if pd.notna(vwap.iloc[i]) and a0 == a0 and a0 else 0.0
        row = {
            "dist_poc": dist_poc,
            "dist_val": dist_val,
            "dist_vwap": dist_vwap,
            "ha_green": float(bool(local_ha["ha_green"].iloc[i])),
            "above_vwap": float(bool(above_vwap.iloc[i])),
            "vol_expand": float(bool(vp["vol_expand"].iloc[i])),
            "macd_hist": float(macd_hist.iloc[i]) if pd.notna(macd_hist.iloc[i]) else 0.0,
            "block_red_flag_on": float(bool(vp["red_flag_up"].iloc[i])),
            "htf_green": float(bool(htf.iloc[i])),
            "atr_pct": float(a0 / px) if px and a0 == a0 else 0.0,
            "conf": float(conf.iloc[i]),
            "spy_htf_green": float(spy_reg.iloc[i]) if pd.notna(spy_reg.iloc[i]) else 0.0,
        }
        for s in _SYM_ONEHOT:
            row[f"sym_{s}"] = 1.0 if code.startswith(s) else 0.0
        return [row.get(c, 0.0) for c in self._feat_cols]

    def _signals_on_frame(self, data, cfg, code: str, data_map: Dict[str, pd.DataFrame]):
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
        cloud=ema_cloud_state(data)
        atr=_atr(data).replace(0,np.nan)
        high=data["high"]
        atr_pct=(atr/close.replace(0,np.nan)).fillna(0.0)
        med_atr_pct=float(atr_pct.replace(0,np.nan).median())
        if not np.isfinite(med_atr_pct) or med_atr_pct<=0:
            med_atr_pct=float(atr_pct.mean()) if atr_pct.mean()>0 else 0.02

        # Conviction overlays + live-adapt VPA
        vol_z = vp["vol_z"].shift(1).fillna(0.0)
        vpa_sc = vp["vpa_score"].shift(1).fillna(0.0)
        vpa_mom = vp["vpa_mom"].shift(1).fillna(0.0)
        vol_reg = vp["vol_regime"].shift(1).fillna(0.5)
        climax_soft = vp["climax_recent"].shift(1).fillna(False).astype(bool)
        # room to recent high (prior 20 bars) — feature-evolve IC positive
        roll_hi = high.rolling(20, min_periods=5).max().shift(1)
        room_pct = ((roll_hi - close) / close.replace(0, np.nan)).fillna(0.0)
        ret_5d = close.pct_change(5).shift(1).fillna(0.0)
        va_mid = (val + vah) / 2.0
        structure_good = (close <= va_mid) & local_ha["ha_green"] & above_vwap
        chase_ob = (close >= vah) & (macd_hist > 0) & (ret_5d > 0.05)
        # Demand nodes — slightly wider (0.75 ATR) for faster live hits
        a_safe = atr.replace(0, np.nan)
        near_val = ((close - val).abs() / a_safe) <= 0.75
        near_poc = ((close - poc).abs() / a_safe) <= 0.75
        demand_node = (near_val | near_poc).fillna(False)
        ema_bull = cloud["ema_bull"].shift(1).fillna(False).astype(bool)
        ema_bear = cloud["ema_bear"].shift(1).fillna(False).astype(bool)
        sector_score = _sector_rs_score(code, data_map)
        qqq_score = _qqq_rs_score(data_map)
        rs_boost = 0.02 * (float(sector_score) - 0.5) + 0.02 * (float(qqq_score) - 0.5)
        qqq_weak = float(qqq_score) < 0.40
        hb_soft = (code in _HIGH_BETA) and qqq_weak

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
        if soft_confidence:
            parts=[poc_ok,in_va,htf,uptrend,above_vwap,vp["confirm_up"]|vp["healthy_pull"],~vp["red_flag_up"],sqz["mom_pos"],sqz["sqz_off"]|sqz["sqz_release"]]
            total=None
            for p in parts: total=p.astype(float) if total is None else total+p.astype(float)
            conf=total/float(len(parts)); long_entry=poc_ok&in_va&(conf>=min_confidence)
            if block_red_flag: long_entry=long_entry&(~vp["red_flag_up"])
            if block_dump: long_entry=long_entry&(~vp["dump"])
            if require_htf_green: long_entry=long_entry&htf
        else:
            long_entry=long_hard; conf=pd.Series(1.0,index=data.index)
        spy_reg=pd.Series(0.0,index=data.index)
        if self._spy_htf is not None and not self._spy_htf.empty:
            spy_reg=self._spy_htf.reindex(data.index,method="ffill").fillna(0.0)
        signal=pd.Series(0.0,index=data.index); in_pos=False; entry_size=0.0
        entry_px=np.nan; peak_px=np.nan; entry_atr=np.nan; entry_bar=-1
        # Seed from live desk streak if available (rapid adapt across sessions)
        streak_mult = float(self._live_streak)
        consec = int(self._live_consec)
        for i in range(len(data)):
            px=float(close.iloc[i])
            a=float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else 0.0
            if not in_pos:
                if bool(long_entry.iloc[i]):
                    feats=self._meta_row(code,i,close,poc,val,vwap,atr,local_ha,macd_hist,above_vwap,vp,htf,conf,spy_reg)
                    proba=float(self._booster.predict_proba(np.asarray([feats],dtype=float))[0,1])
                    boost = _volume_z_boost(float(vol_z.iloc[i])) + float(rs_boost)
                    # Live: VPA mom lifts meta confidence
                    boost += 0.015 * float(np.clip(vpa_mom.iloc[i], -1.0, 1.0))
                    # A+ confluence slight meta nudge (secondary only)
                    if (
                        bool(structure_good.iloc[i])
                        and bool(demand_node.iloc[i])
                        and float(vpa_sc.iloc[i]) >= 0.20
                    ):
                        boost += 0.02
                    adj_proba = float(np.clip(proba + boost, 0.0, 1.0))
                    meta_sz=_prob_to_size(adj_proba, self._thr)
                    feat_m = _soft_feature_mult(
                        float(atr_pct.iloc[i]),
                        med_atr_pct,
                        float(room_pct.iloc[i]),
                        float(macd_hist.iloc[i]) if pd.notna(macd_hist.iloc[i]) else 0.0,
                        float(ret_5d.iloc[i]),
                        bool(structure_good.iloc[i]),
                        bool(chase_ob.iloc[i]),
                        float(vpa_sc.iloc[i]),
                        float(vpa_mom.iloc[i]),
                        float(vol_reg.iloc[i]),
                        bool(demand_node.iloc[i]),
                        bool(ema_bull.iloc[i]),
                        bool(ema_bear.iloc[i]),
                        bool(hb_soft),
                    )
                    raw = meta_sz * feat_m * streak_mult if meta_sz > 0 else 0.0
                    sz=_risk_scale_size(raw, float(atr_pct.iloc[i]), med_atr_pct, kelly_fraction)
                    sz = float(np.clip(sz * self._risk_scale, 0.0, 1.0))
                    self._ledger.record_entry(
                        timestamp=data.index[i],
                        code=code,
                        entry_px=px,
                        features=feats,
                        meta_proba=proba,
                        adj_proba=adj_proba,
                        meta_sz=meta_sz,
                        feat_m=feat_m,
                        raw_size=raw,
                        final_size=sz,
                        passed=sz > 0,
                    )
                    # No hard stand-aside floor — only soft size
                    if sz>0:
                        in_pos=True; entry_size=sz; signal.iloc[i]=sz
                        entry_px=px; peak_px=px; entry_atr=a if a>0 else px*0.01
                        entry_bar=i
                        self._last_adapt = {
                            "code": code,
                            "vpa_score": float(vpa_sc.iloc[i]),
                            "vpa_mom": float(vpa_mom.iloc[i]),
                            "vol_regime": float(vol_reg.iloc[i]),
                            "demand_node": bool(demand_node.iloc[i]),
                            "feat_m": float(feat_m),
                            "streak_mult": float(streak_mult),
                            "size": float(sz),
                        }
            else:
                peak_px=max(peak_px, float(high.iloc[i]))
                hard_stop=px<=entry_px-stop_atr*entry_atr
                armed=peak_px>=entry_px+arm_trail_atr*entry_atr
                trail_stop=armed and (px<=peak_px-trail_atr*entry_atr)
                soft_exit=False
                # Softer VPA exits (v39d): need volume confirmation, not mom alone
                vpa_now = float(vpa_sc.iloc[i])
                mom_now = float(vpa_mom.iloc[i])
                vol_bad = bool(vp["dump"].iloc[i]) or bool(vp["red_flag_up"].iloc[i])
                if not armed:
                    if require_htf_green and not bool(htf.iloc[i]): soft_exit=True
                    if exit_on_poc_break and not bool(poc_ok.iloc[i]): soft_exit=True
                    if exit_on_val_break and close.iloc[i]<val.iloc[i]: soft_exit=True
                    if exit_below_vwap and pd.notna(vwap.iloc[i]) and px<float(vwap.iloc[i]): soft_exit=True
                    if exit_on_sqz_neg and bool(sqz["mom_neg"].iloc[i]): soft_exit=True
                    if bool(local_ha["ha_red"].iloc[i]) and not bool(htf.iloc[i]): soft_exit=True
                    if block_red_flag and bool(vp["red_flag_up"].iloc[i]): soft_exit=True
                    if bool(climax_soft.iloc[i]) and vpa_now < 0.0 and vol_bad:
                        soft_exit=True
                    # VPA collapse only with dump/red_flag (was pure mom — over-exited early)
                    if mom_now <= -0.95 and vpa_now <= -0.45 and vol_bad:
                        soft_exit=True
                elif block_red_flag and bool(vp["red_flag_up"].iloc[i]):
                    soft_exit=True
                elif exit_on_sqz_neg and bool(sqz["mom_neg"].iloc[i]) and px<entry_px:
                    soft_exit=True
                elif mom_now <= -1.15 and vpa_now <= -0.70 and px < entry_px and vol_bad:
                    soft_exit=True
                if hard_stop or trail_stop or soft_exit:
                    if np.isfinite(entry_px) and entry_px > 0:
                        won = px >= entry_px
                        streak_mult, consec = _live_streak_update(
                            streak_mult, won, consec, self._after_win, self._after_loss
                        )
                        self._live_streak = streak_mult
                        self._live_consec = consec
                    reason = "soft_exit" if soft_exit else ("trail_stop" if trail_stop else "hard_stop")
                    self._ledger.record_exit(
                        timestamp=data.index[i], code=code, exit_px=px, reason=reason
                    )
                    in_pos=False; signal.iloc[i]=0.0; entry_size=0.0
                    entry_px=peak_px=entry_atr=np.nan; entry_bar=-1
                else:
                    # Mid-trade shrink only when underwater + VPA bad (v39d)
                    if (
                        px < entry_px
                        and mom_now <= -0.85
                        and vpa_now < 0
                        and entry_size > 0.25
                    ):
                        entry_size = max(0.25, entry_size * 0.90)
                    signal.iloc[i]=entry_size; in_pos=True
        if in_pos and np.isfinite(entry_px) and entry_px > 0:
            self._ledger.record_exit(
                timestamp=data.index[-1],
                code=code,
                exit_px=float(close.iloc[-1]),
                reason="end_of_backtest",
            )
        return signal.fillna(0.0)

    def _one(self, code, df, data_map: Dict[str, pd.DataFrame]):
        cfg=self._cfg(code); data=df.copy(); data.index=pd.to_datetime(data.index)
        if getattr(data.index,"tz",None) is not None: data.index=data.index.tz_localize(None)
        data=data.sort_index(); signal_tf=cfg.get("signal_tf","2h")
        if signal_tf:
            frame=_resample_ohlcv(data,signal_tf)
            if frame.empty: return pd.Series(0.0,index=data.index)
            return self._signals_on_frame(frame,cfg,code,data_map).reindex(data.index,method="ffill").fillna(0.0)
        return self._signals_on_frame(data,cfg,code,data_map)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
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
            if code in REGIME_FLAT or code in TRADE_DROP:
                out[code] = pd.Series(0.0, index=df.index)
                continue
            sig = self._one(code, df, data_map)
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
        self._ledger.flush()
        return out
