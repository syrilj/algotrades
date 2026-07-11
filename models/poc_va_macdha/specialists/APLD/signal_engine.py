from __future__ import annotations
from typing import Dict
import numpy as np
import pandas as pd

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


def volume_price_state(df, look=5, vol_sma=20):
    """Volume-price confirmation / red-flag logic.

    Confirm long: price rising AND volume expanding
    Red flag:     price rising AND volume drying up
    Healthy dip:  price falling AND volume drying up (not a panic)
    Dump:         price falling AND volume expanding
    """
    close = df["close"]
    vol = df["volume"]
    price_up = close > close.shift(look)
    price_dn = close < close.shift(look)
    vsma = _sma(vol, vol_sma)
    vol_up = vol > vsma
    vol_dn = vol < vsma
    # also short-term volume trend
    vol_rising = vol > vol.shift(look)
    vol_falling = vol < vol.shift(look)

    confirm_up = price_up & (vol_up | vol_rising)          # price↑ volume↑
    red_flag_up = price_up & vol_falling & ~vol_up         # price↑ volume drying — weak
    healthy_pull = price_dn & vol_falling                  # price↓ volume↓
    dump = price_dn & vol_rising & vol_up                  # price↓ volume↑ — avoid longs

    return pd.DataFrame({
        "confirm_up": confirm_up.fillna(False),
        "red_flag_up": red_flag_up.fillna(False),
        "healthy_pull": healthy_pull.fillna(False),
        "dump": dump.fillna(False),
        "vol_expand": vol_up.fillna(False),
    }, index=df.index)


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




class SignalEngine:
    def __init__(
        self,
        value_area_pct=0.7,
        profile_rows=25,
        profile_lookback=20,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        macd_htf='4h',
        signal_tf='2h',
        require_htf_green=True,
        require_vwap_uptrend=True,
        require_above_vwap=True,
        require_volume_expand=True,
        require_vol_confirm=True,
        block_red_flag=True,
        block_dump=True,
        require_sqz_release=False,
        require_mom_pos=True,
        require_mom_pos_inc=False,
        allow_healthy_pull_entry=False,
        exit_on_poc_break=False,
        exit_on_val_break=False,
        exit_below_vwap=True,
        exit_on_sqz_neg=False,
        soft_confidence=False,
        swing_period=50,
        vol_look=5,
        vol_sma=20,
        min_confidence=0.6,
    ):
        self.value_area_pct=value_area_pct; self.profile_rows=profile_rows; self.profile_lookback=profile_lookback
        self.macd_fast=macd_fast; self.macd_slow=macd_slow; self.macd_signal=macd_signal
        self.macd_htf=macd_htf; self.signal_tf=signal_tf; self.require_htf_green=require_htf_green
        self.require_vwap_uptrend=require_vwap_uptrend; self.require_above_vwap=require_above_vwap
        self.require_volume_expand=require_volume_expand; self.require_vol_confirm=require_vol_confirm
        self.block_red_flag=block_red_flag; self.block_dump=block_dump
        self.require_sqz_release=require_sqz_release; self.require_mom_pos=require_mom_pos
        self.require_mom_pos_inc=require_mom_pos_inc; self.allow_healthy_pull_entry=allow_healthy_pull_entry
        self.exit_on_poc_break=exit_on_poc_break; self.exit_on_val_break=exit_on_val_break
        self.exit_below_vwap=exit_below_vwap; self.exit_on_sqz_neg=exit_on_sqz_neg
        self.soft_confidence=soft_confidence; self.swing_period=swing_period
        self.vol_look=vol_look; self.vol_sma=vol_sma; self.min_confidence=min_confidence

    def _signals_on_frame(self, data):
        levels = _prior_session_profile(data, self.profile_lookback, self.profile_rows, self.value_area_pct)
        poc,vah,val = levels["poc"],levels["vah"],levels["val"]
        close=data["close"]
        poc_ok=(close>=poc)&poc.notna(); in_va=(close>=val)&(close<=vah)&val.notna()
        htf=_htf_ha_green(data,self.macd_htf,self.macd_fast,self.macd_slow,self.macd_signal)
        local_ha=_standardized_macd_ha(data,self.macd_fast,self.macd_slow,self.macd_signal)
        swing=dynamic_swing_anchored_vwap(data,self.swing_period)
        vwap=swing["vwap"].shift(1); uptrend=swing["uptrend"].shift(1).fillna(False).astype(bool)
        above_vwap=(close>=vwap).fillna(False)
        vp=volume_price_state(data,self.vol_look,self.vol_sma); sqz=squeeze_momentum(data)
        gates=[poc_ok,in_va]
        if self.require_htf_green: gates.append(htf)
        if self.require_vwap_uptrend: gates.append(uptrend)
        if self.require_above_vwap: gates.append(above_vwap)
        if self.require_volume_expand: gates.append(vp["vol_expand"])
        if self.require_vol_confirm: gates.append(vp["confirm_up"]|(self.allow_healthy_pull_entry&vp["healthy_pull"]&above_vwap))
        if self.block_red_flag: gates.append(~vp["red_flag_up"])
        if self.block_dump: gates.append(~vp["dump"])
        if self.require_sqz_release: gates.append(sqz["sqz_release"]|sqz["sqz_off"])
        if self.require_mom_pos: gates.append(sqz["mom_pos"])
        if self.require_mom_pos_inc: gates.append(sqz["mom_pos_inc"])
        long_hard=gates[0]
        for g in gates[1:]: long_hard=long_hard&g
        if self.soft_confidence:
            parts=[poc_ok,in_va,htf,uptrend,above_vwap,vp["confirm_up"]|vp["healthy_pull"],~vp["red_flag_up"],sqz["mom_pos"],sqz["sqz_off"]|sqz["sqz_release"]]
            total=None
            for p in parts: total=p.astype(float) if total is None else total+p.astype(float)
            conf=total/float(len(parts))
            long_entry=poc_ok&in_va&(conf>=self.min_confidence)
            if self.block_red_flag: long_entry=long_entry&(~vp["red_flag_up"])
            if self.block_dump: long_entry=long_entry&(~vp["dump"])
            if self.require_htf_green: long_entry=long_entry&htf
            size=conf.clip(0,1)
        else:
            long_entry=long_hard; size=pd.Series(1.0,index=data.index)
        signal=pd.Series(0.0,index=data.index); in_pos=False
        for i in range(len(data)):
            if not in_pos:
                if bool(long_entry.iloc[i]):
                    in_pos=True; signal.iloc[i]=float(size.iloc[i]) if self.soft_confidence else 1.0
            else:
                exit_now=False
                if self.require_htf_green and not bool(htf.iloc[i]): exit_now=True
                if self.exit_on_poc_break and not bool(poc_ok.iloc[i]): exit_now=True
                if self.exit_on_val_break and close.iloc[i]<val.iloc[i]: exit_now=True
                if self.exit_below_vwap and pd.notna(vwap.iloc[i]) and close.iloc[i]<vwap.iloc[i]: exit_now=True
                if self.exit_on_sqz_neg and bool(sqz["mom_neg"].iloc[i]): exit_now=True
                if bool(local_ha["ha_red"].iloc[i]) and not bool(htf.iloc[i]): exit_now=True
                if self.block_red_flag and bool(vp["red_flag_up"].iloc[i]): exit_now=True
                if exit_now: in_pos=False; signal.iloc[i]=0.0
                else: signal.iloc[i]=float(size.iloc[i]) if self.soft_confidence else 1.0; in_pos=True
        return signal.fillna(0.0)

    def _one(self, df):
        data=df.copy(); data.index=pd.to_datetime(data.index)
        if getattr(data.index,"tz",None) is not None: data.index=data.index.tz_localize(None)
        data=data.sort_index()
        if self.signal_tf:
            frame=_resample_ohlcv(data,self.signal_tf)
            if frame.empty: return pd.Series(0.0,index=data.index)
            return self._signals_on_frame(frame).reindex(data.index,method="ffill").fillna(0.0)
        return self._signals_on_frame(data)

    def generate(self, data_map):
        return {c: self._one(df) for c,df in data_map.items()}
