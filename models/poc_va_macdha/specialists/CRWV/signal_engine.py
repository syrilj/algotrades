from __future__ import annotations
"""v64_crwv_bounce — CoreWeave (CRWV) demand-bounce specialist.

Global meta models often print low confidence on CRWV because they are
trend/HTF-gated on a multi-week downtrend. This specialist is built for the
opposite regime: high-vol AI infra name testing multi-week support with
put-wall / value-area demand and call-flow into the bounce.

Entry thesis (long only):
  - Price in demand zone (near 20d low, VAL, or option put-wall band)
  - Bounce structure: local HA green OR vol-confirm up OR squeeze mom flip
  - Not dumping (block climax dump / red-flag chase)
  - Soft confluence score sizes the trade (not a hard all-gates stack)

Exit:
  - Local HA red + lost VWAP, or
  - Close below demand floor (invalidate bounce), or
  - Trail after +1.5 ATR extension
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(1, n // 2)).mean()


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if not rule:
        return df
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    l = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    v = df["volume"].resample(rule).sum()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}).dropna()
    return out


def _standardized_macd_ha(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
    close = df["close"].astype(float)
    macd = _ema(close, fast) - _ema(close, slow)
    sig = _ema(macd, signal)
    hist = macd - sig
    # Heikin-Ashi of MACD line as proxy for local HA color
    ha_close = (macd + sig + hist + macd.shift(1).fillna(macd)) / 4.0
    ha_open = (macd.shift(1).fillna(macd) + sig.shift(1).fillna(sig)) / 2.0
    ha_green = ha_close >= ha_open
    ha_red = ~ha_green
    return pd.DataFrame(
        {"macd": macd, "signal": sig, "hist": hist, "ha_green": ha_green, "ha_red": ha_red},
        index=df.index,
    )


def _htf_ha_green(df: pd.DataFrame, htf: str, fast=12, slow=26, signal=9) -> pd.Series:
    frame = _resample_ohlcv(df, htf)
    if frame.empty:
        return pd.Series(False, index=df.index)
    ha = _standardized_macd_ha(frame, fast, slow, signal)["ha_green"]
    return ha.reindex(df.index, method="ffill").fillna(False).astype(bool)


def _prior_session_profile(df: pd.DataFrame, lookback=20, rows=25, value_area_pct=0.7) -> Dict[str, pd.Series]:
    """Expanding prior-bar value area / POC (no look-ahead within bar)."""
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)
    n = len(df)
    poc = np.full(n, np.nan)
    val = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    for i in range(n):
        a = max(0, i - lookback)
        # use bars strictly before i
        if i - a < 5:
            continue
        sl = low.iloc[a:i].to_numpy()
        sh = high.iloc[a:i].to_numpy()
        sv = volume.iloc[a:i].to_numpy()
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
        val[i] = float(mid[idx.min()])
        vah[i] = float(mid[idx.max()])
    return {
        "poc": pd.Series(poc, index=df.index),
        "val": pd.Series(val, index=df.index),
        "vah": pd.Series(vah, index=df.index),
    }


def volume_price_state(df: pd.DataFrame, look=5, vol_sma=20) -> Dict[str, pd.Series]:
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float)
    ret1 = close.pct_change()
    vma = _sma(vol, vol_sma)
    vol_expand = (vol > 1.15 * vma).fillna(False)
    vol_z = ((vol - vma) / vma.replace(0, np.nan)).fillna(0.0)
    green = (close > close.shift(1)).fillna(False)
    red = (close < close.shift(1)).fillna(False)
    rng = (high - low).replace(0, np.nan)
    upper_wick = (high - close).clip(lower=0) / rng
    lower_wick = (close - low).clip(lower=0) / rng
    # absorption / dump proxies
    dump = (red & vol_expand & (ret1 < -0.02)).fillna(False)
    red_flag_up = (green & vol_expand & (upper_wick > 0.55) & (ret1 > 0.015)).fillna(False)
    confirm_up = (green & vol_expand & (ret1 > 0.005)).fillna(False)
    healthy_pull = (red & ~vol_expand & (lower_wick > 0.4)).fillna(False)
    # stopping volume: high vol red with long lower wick (demand)
    stop_vol = (red & vol_expand & (lower_wick > 0.45)).fillna(False)
    return {
        "vol_expand": vol_expand.astype(bool),
        "vol_z": vol_z,
        "dump": dump.astype(bool),
        "red_flag_up": red_flag_up.astype(bool),
        "confirm_up": confirm_up.astype(bool),
        "healthy_pull": healthy_pull.astype(bool),
        "stop_vol": stop_vol.astype(bool),
        "green": green.astype(bool),
        "red": red.astype(bool),
    }


def squeeze_momentum(df: pd.DataFrame, length=20, mult_bb=2.0, length_kc=20, mult_kc=1.5) -> Dict[str, pd.Series]:
    src = df["close"].astype(float)
    basis = _sma(src, length)
    std = src.rolling(length, min_periods=max(2, length // 2)).std(ddof=0)
    upper_bb = basis + mult_bb * std
    lower_bb = basis - mult_bb * std
    ma = _sma(src, length_kc)
    tr = _atr(df, length_kc)
    upper_kc = ma + mult_kc * tr
    lower_kc = ma - mult_kc * tr
    sqz_on = ((lower_bb > lower_kc) & (upper_bb < upper_kc)).fillna(False)
    sqz_off = ((lower_bb < lower_kc) & (upper_bb > upper_kc)).fillna(False)
    # LazyBear-ish momentum: linear reg residual proxy via close - mid
    mom = src - basis
    mom_pos = (mom > 0).fillna(False)
    mom_neg = (mom < 0).fillna(False)
    mom_pos_inc = (mom > mom.shift(1)).fillna(False) & mom_pos
    return {
        "sqz_on": sqz_on.astype(bool),
        "sqz_off": sqz_off.astype(bool),
        "sqz_release": (sqz_on.shift(1).fillna(False) & sqz_off).astype(bool),
        "mom_pos": mom_pos.astype(bool),
        "mom_neg": mom_neg.astype(bool),
        "mom_pos_inc": mom_pos_inc.astype(bool),
        "mom": mom,
    }


def dynamic_swing_anchored_vwap(df: pd.DataFrame, swing_period: int = 50) -> pd.DataFrame:
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    volume = df["volume"].to_numpy(float)
    hlc3 = (high + low + close) / 3.0
    n = len(df)
    vwap = np.full(n, np.nan)
    direction = np.ones(n, dtype=int)
    p_acc = vol_acc = 0.0
    ph = pl = np.nan
    ph_i = pl_i = 0
    for i in range(n):
        left = max(0, i - swing_period + 1)
        if high[i] >= np.max(high[left : i + 1]) - 1e-12:
            ph, ph_i = high[i], i
        if low[i] <= np.min(low[left : i + 1]) + 1e-12:
            pl, pl_i = low[i], i
        new_dir = 1 if ph_i > pl_i else -1
        if i == 0 or new_dir != direction[i - 1]:
            anchor_i = int(np.clip(pl_i if new_dir > 0 else ph_i, 0, i))
            anchor_y = pl if new_dir > 0 else ph
            if not np.isfinite(anchor_y):
                anchor_y = hlc3[anchor_i]
            p_acc = float(anchor_y) * float(max(volume[anchor_i], 1e-12))
            vol_acc = float(max(volume[anchor_i], 1e-12))
            for j in range(anchor_i, i + 1):
                p_acc += hlc3[j] * volume[j]
                vol_acc += volume[j]
            direction[i] = new_dir
        else:
            p_acc += hlc3[i] * volume[i]
            vol_acc += volume[i]
            direction[i] = new_dir
        vwap[i] = p_acc / vol_acc if vol_acc > 0 else np.nan
    return pd.DataFrame({"vwap": vwap, "uptrend": direction > 0}, index=df.index)


class SignalEngine:
    """CRWV bounce specialist — demand-zone mean reversion with soft confluence."""

    # Static option walls (updated in LIVE_READ; used as soft level magnets).
    PUT_WALLS = (75.0, 80.0, 70.0)
    CALL_MAGNETS = (85.0, 90.0, 95.0)

    def __init__(
        self,
        value_area_pct: float = 0.7,
        profile_rows: int = 25,
        profile_lookback: int = 20,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        macd_htf: str = "4h",
        signal_tf: str = "1h",
        demand_atr_band: float = 0.75,
        min_score: float = 0.45,
        stop_atr: float = 1.2,
        trail_atr: float = 2.0,
        arm_trail_atr: float = 1.0,
        max_hold_bars: int = 24,
        **_kwargs,
    ):
        self.value_area_pct = value_area_pct
        self.profile_rows = profile_rows
        self.profile_lookback = profile_lookback
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.macd_htf = macd_htf
        self.signal_tf = signal_tf
        self.demand_atr_band = demand_atr_band
        self.min_score = min_score
        self.stop_atr = stop_atr
        self.trail_atr = trail_atr
        self.arm_trail_atr = arm_trail_atr
        self.max_hold_bars = max_hold_bars
        self._last_read: Optional[dict] = None

    def last_read(self) -> Optional[dict]:
        return self._last_read

    def _demand_score(self, px: float, val: float, swing_low: float, atr: float) -> float:
        """How close price is to demand (1 = sitting on level)."""
        if not np.isfinite(px) or atr <= 0:
            return 0.0
        band = self.demand_atr_band * atr
        scores = []
        for lvl in (val, swing_low, *self.PUT_WALLS):
            if not np.isfinite(lvl):
                continue
            dist = abs(px - float(lvl))
            if dist <= band:
                scores.append(1.0 - dist / band)
            elif px >= float(lvl) and (px - float(lvl)) <= 1.5 * band:
                # slightly above support still counts softer
                scores.append(max(0.0, 0.55 - (px - float(lvl)) / (2.0 * band)))
        return float(max(scores) if scores else 0.0)

    def _signals_on_frame(self, data: pd.DataFrame, code: str) -> pd.Series:
        levels = _prior_session_profile(
            data, self.profile_lookback, self.profile_rows, self.value_area_pct
        )
        poc, vah, val = levels["poc"], levels["vah"], levels["val"]
        close = data["close"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)
        atr = _atr(data).replace(0, np.nan)
        swing_low = low.rolling(20, min_periods=5).min().shift(1)
        swing = dynamic_swing_anchored_vwap(data, 50)
        vwap = swing["vwap"].shift(1)
        above_vwap = (close >= vwap).fillna(False)
        local_ha = _standardized_macd_ha(data, self.macd_fast, self.macd_slow, self.macd_signal)
        htf = _htf_ha_green(data, self.macd_htf, self.macd_fast, self.macd_slow, self.macd_signal)
        vp = volume_price_state(data)
        sqz = squeeze_momentum(data)

        signal = pd.Series(0.0, index=data.index)
        in_pos = False
        entry_px = peak_px = entry_atr = np.nan
        entry_bar = -1
        last_score = 0.0

        for i in range(len(data)):
            px = float(close.iloc[i])
            a = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else px * 0.03
            v = float(val.iloc[i]) if np.isfinite(val.iloc[i]) else np.nan
            sl = float(swing_low.iloc[i]) if np.isfinite(swing_low.iloc[i]) else np.nan
            demand = self._demand_score(px, v, sl, a)

            # bounce structure points
            bounce_pts = 0.0
            if bool(local_ha["ha_green"].iloc[i]):
                bounce_pts += 0.25
            if bool(vp["confirm_up"].iloc[i]) or bool(vp["stop_vol"].iloc[i]):
                bounce_pts += 0.25
            if bool(sqz["mom_pos"].iloc[i]) or bool(sqz["mom_pos_inc"].iloc[i]):
                bounce_pts += 0.15
            if bool(vp["healthy_pull"].iloc[i]) and above_vwap.iloc[i]:
                bounce_pts += 0.10
            if bool(htf.iloc[i]):
                bounce_pts += 0.15  # bonus, not required
            # reclaim VWAP from below
            if i > 0 and pd.notna(vwap.iloc[i]):
                if float(close.iloc[i - 1]) < float(vwap.iloc[i - 1]) and px >= float(vwap.iloc[i]):
                    bounce_pts += 0.20

            # invalidators at entry
            toxic = bool(vp["dump"].iloc[i]) or bool(vp["red_flag_up"].iloc[i])
            score = 0.0 if toxic else min(1.0, 0.55 * demand + bounce_pts)

            if not in_pos:
                if demand >= 0.35 and score >= self.min_score and bounce_pts >= 0.25 and not toxic:
                    in_pos = True
                    entry_px = px
                    peak_px = px
                    entry_atr = a if a > 0 else px * 0.03
                    entry_bar = i
                    last_score = score
                    # size 0.35–1.0 by score
                    signal.iloc[i] = float(np.clip(0.35 + 0.65 * score, 0.35, 1.0))
            else:
                peak_px = max(peak_px, float(high.iloc[i]))
                hard_stop = px <= entry_px - self.stop_atr * entry_atr
                armed = peak_px >= entry_px + self.arm_trail_atr * entry_atr
                trail = armed and (px <= peak_px - self.trail_atr * entry_atr)
                # invalidate if close decisively under demand floor
                floor = np.nanmin([sl, v, min(self.PUT_WALLS)]) if np.isfinite(sl) or np.isfinite(v) else entry_px - 2 * entry_atr
                if not np.isfinite(floor):
                    floor = entry_px - 2 * entry_atr
                lost_floor = px < float(floor) - 0.15 * entry_atr
                soft_exit = bool(local_ha["ha_red"].iloc[i]) and (
                    (pd.notna(vwap.iloc[i]) and px < float(vwap.iloc[i])) or bool(vp["dump"].iloc[i])
                )
                held_too_long = (i - entry_bar) >= self.max_hold_bars
                if hard_stop or trail or lost_floor or soft_exit or held_too_long:
                    in_pos = False
                    signal.iloc[i] = 0.0
                    entry_px = peak_px = entry_atr = np.nan
                    entry_bar = -1
                else:
                    signal.iloc[i] = float(np.clip(0.35 + 0.65 * last_score, 0.35, 1.0))

        # stash last bar read for desk
        i = len(data) - 1
        px = float(close.iloc[i])
        a = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else np.nan
        v = float(val.iloc[i]) if np.isfinite(val.iloc[i]) else np.nan
        p = float(poc.iloc[i]) if np.isfinite(poc.iloc[i]) else np.nan
        sl = float(swing_low.iloc[i]) if np.isfinite(swing_low.iloc[i]) else np.nan
        demand = self._demand_score(px, v, sl, a if np.isfinite(a) else px * 0.03)
        self._last_read = {
            "code": code,
            "price": px,
            "atr": a,
            "val": v,
            "poc": p,
            "vah": float(vah.iloc[i]) if np.isfinite(vah.iloc[i]) else np.nan,
            "swing_low_20": sl,
            "vwap": float(vwap.iloc[i]) if pd.notna(vwap.iloc[i]) else np.nan,
            "demand_score": demand,
            "htf_green": bool(htf.iloc[i]),
            "local_ha_green": bool(local_ha["ha_green"].iloc[i]),
            "vol_confirm": bool(vp["confirm_up"].iloc[i]),
            "stop_vol": bool(vp["stop_vol"].iloc[i]),
            "dump": bool(vp["dump"].iloc[i]),
            "put_walls": list(self.PUT_WALLS),
            "call_magnets": list(self.CALL_MAGNETS),
            "signal": float(signal.iloc[i]),
        }
        return signal.fillna(0.0)

    def _one(self, code: str, df: pd.DataFrame) -> pd.Series:
        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()
        # normalize columns
        data.columns = [str(c).lower() for c in data.columns]
        if self.signal_tf:
            frame = _resample_ohlcv(data, self.signal_tf)
            if frame.empty:
                return pd.Series(0.0, index=data.index)
            return self._signals_on_frame(frame, code).reindex(data.index, method="ffill").fillna(0.0)
        return self._signals_on_frame(data, code)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out = {}
        for code, df in data_map.items():
            # only trade CRWV variants; flat others if bag mixed
            if "CRWV" not in str(code).upper() and code not in ("CRWV", "CRWV.US"):
                out[code] = pd.Series(0.0, index=df.index)
                continue
            out[code] = self._one(code, df)
        return out
