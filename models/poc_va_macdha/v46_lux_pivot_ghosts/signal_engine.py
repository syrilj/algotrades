"""LuxAlgo Pivot Points High Low & Missed Reversal Levels.

Modes:
- "zigzag": long when the latest confirmed pivot is a low, flat when it is a high.
- "missed_sr": long on a higher-low pivot (close above the new swing low) with the
  previous swing low as the stop, flat on a lower-high pivot or close below the
  previous swing low.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


DEFAULT_PARAMS: Dict[str, Any] = {
    "pivot_length": 10,
    "signal_tf": None,
    "strategy_mode": "zigzag",
    "use_atr_stop": False,
    "atr_mult": 2.5,
    "use_trail": False,
    "atr_period": 14,
    "atr_smo": "RMA",
}


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(1, n // 2)).mean()


def _rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def _tma(s: pd.Series, n: int) -> pd.Series:
    return _sma(_sma(s, n), n)


def _ma(s: pd.Series, n: int, kind: str) -> pd.Series:
    k = kind.upper()
    if k == "EMA":
        return _ema(s, n)
    if k == "SMA":
        return _sma(s, n)
    if k == "RMA":
        return _rma(s, n)
    if k == "TMA":
        return _tma(s, n)
    raise ValueError(f"Unknown MA kind: {kind}")


def _atr(df: pd.DataFrame, n: int, kind: str) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    close_prev = close.shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return _ma(tr, n, kind)


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    ohlc = df[["open", "high", "low", "close", "volume"]].copy()
    out = ohlc.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    return out


def _pivot_high(s: pd.Series, length: int) -> pd.Series:
    """Right-most maximum in a window of size 2*length+1."""
    left_max = s.rolling(window=length, min_periods=length).max().shift(1)
    right_max = s.rolling(window=length, min_periods=length).max().shift(-length)
    return (s >= left_max) & (s > right_max)


def _pivot_low(s: pd.Series, length: int) -> pd.Series:
    """Right-most minimum in a window of size 2*length+1."""
    left_min = s.rolling(window=length, min_periods=length).min().shift(1)
    right_min = s.rolling(window=length, min_periods=length).min().shift(-length)
    return (s <= left_min) & (s < right_min)


def _pivot_events(df: pd.DataFrame, length: int) -> pd.DataFrame:
    """Return confirmed pivot events aligned at the confirmation bar."""
    ph_raw = _pivot_high(df["high"], length).shift(length)
    pl_raw = _pivot_low(df["low"], length).shift(length)
    ph = pd.Series(np.where(ph_raw.isna(), False, ph_raw), index=df.index, dtype=bool)
    pl = pd.Series(np.where(pl_raw.isna(), False, pl_raw), index=df.index, dtype=bool)
    return pd.DataFrame({"ph": ph, "pl": pl}, index=df.index)


class SignalEngine:
    """Pivot high/low trend-follow with optional missed-level S/R confirmation."""

    def __init__(self) -> None:
        self._params = self._load_params()

    def _load_params(self) -> Dict[str, Any]:
        candidates = [
            Path(__file__).resolve().parent / "config.json",
            Path(__file__).resolve().parents[1] / "config.json",
        ]
        cfg: Dict[str, Any] = {}
        for cand in candidates:
            if cand.exists():
                try:
                    cfg = json.loads(cand.read_text(encoding="utf-8"))
                except Exception:
                    cfg = {}
                break

        strategy = cfg.get("strategy", {}) if isinstance(cfg.get("strategy"), dict) else {}
        overrides = {**strategy, **{k: cfg[k] for k in DEFAULT_PARAMS if k in cfg}}
        params = {**DEFAULT_PARAMS, **overrides}

        tf = params.get("signal_tf")
        if tf is not None and isinstance(tf, str) and not tf.strip():
            tf = None
        params["signal_tf"] = tf

        mode = params.get("strategy_mode", "zigzag")
        if mode not in ("zigzag", "missed_sr"):
            mode = "zigzag"
        params["strategy_mode"] = mode
        return params

    def _signals_zigzag(self, data: pd.DataFrame) -> pd.Series:
        p = self._params
        length = int(p["pivot_length"])
        events = _pivot_events(data, length)

        use_atr = bool(p.get("use_atr_stop", False))
        use_trail = bool(p.get("use_trail", False))
        atr_mult = float(p.get("atr_mult", 2.5))
        atr_period = int(p.get("atr_period", 14))
        atr_smo = str(p.get("atr_smo", "RMA"))

        atr = _atr(data, atr_period, atr_smo) if use_atr else None

        close = data["close"].to_numpy(float)
        high = data["high"].to_numpy(float)
        ph = events["ph"].to_numpy()
        pl = events["pl"].to_numpy()

        signal = np.zeros(len(data))
        in_long = False
        stop = 0.0

        for i in range(len(data)):
            if not in_long:
                if pl[i]:
                    in_long = True
                    if use_atr and atr is not None and not np.isnan(atr.iloc[i]) and atr.iloc[i] > 0:
                        stop = close[i] - atr_mult * float(atr.iloc[i])
                    else:
                        stop = 0.0
                    signal[i] = 1.0
            else:
                exit = ph[i] or (use_atr and stop > 0.0 and close[i] < stop)
                if exit:
                    signal[i] = 0.0
                    in_long = False
                    stop = 0.0
                else:
                    signal[i] = 1.0
                    if use_trail and atr is not None and not np.isnan(atr.iloc[i]) and atr.iloc[i] > 0:
                        trail = high[i] - atr_mult * float(atr.iloc[i])
                        if trail > stop:
                            stop = trail

        return pd.Series(signal, index=data.index)

    def _signals_missed_sr(self, data: pd.DataFrame) -> pd.Series:
        p = self._params
        length = int(p["pivot_length"])

        # The Lux script operates on the candidate bar (n-length). Shift price so the
        # candidate bar aligns with the confirmation bar at index i.
        high_c = data["high"].shift(length)
        low_c = data["low"].shift(length)
        close = data["close"].to_numpy(float)

        ph_raw = _pivot_high(high_c, length)
        pl_raw = _pivot_low(low_c, length)
        ph = pd.Series(np.where(ph_raw.isna(), False, ph_raw), index=data.index, dtype=bool).to_numpy()
        pl = pd.Series(np.where(pl_raw.isna(), False, pl_raw), index=data.index, dtype=bool).to_numpy()

        high_c_arr = high_c.to_numpy(float)
        low_c_arr = low_c.to_numpy(float)

        signal = np.zeros(len(data))
        in_long = False
        max_swing = 0.0
        min_swing = 0.0
        stop = 0.0

        for i in range(len(data)):
            hc = high_c_arr[i]
            lc = low_c_arr[i]

            if not np.isnan(hc):
                if hc > max_swing:
                    max_swing = hc
            if not np.isnan(lc):
                if lc < min_swing or min_swing == 0.0:
                    min_swing = lc

            if ph[i]:
                ph_val = hc
                if not np.isnan(ph_val):
                    # Lower-high pivot: resistance held, exit long.
                    if in_long and ph_val < max_swing:
                        in_long = False
                    # Reset both swing trackers to the new high.
                    max_swing = ph_val
                    min_swing = ph_val

            if pl[i]:
                pl_val = lc
                if not np.isnan(pl_val):
                    prev_min = min_swing
                    # Higher-low pivot: support held and close above it -> enter/hold.
                    if pl_val > min_swing and close[i] > pl_val:
                        in_long = True
                        # Stop is the previous swing low (or the new low if no prior low).
                        stop = prev_min if prev_min > 0.0 else pl_val
                    elif in_long:
                        # Lower/equal low: support broken, exit.
                        in_long = False
                    # Reset both swing trackers to the new low.
                    max_swing = pl_val
                    min_swing = pl_val

            if in_long and stop > 0.0 and close[i] < stop:
                # Close below the previous swing low support.
                in_long = False

            signal[i] = 1.0 if in_long else 0.0

        return pd.Series(signal, index=data.index)

    def _signals_on_frame(self, data: pd.DataFrame) -> pd.Series:
        mode = self._params.get("strategy_mode", "zigzag")
        if mode == "missed_sr":
            return self._signals_missed_sr(data)
        return self._signals_zigzag(data)

    def _one(self, df: pd.DataFrame) -> pd.Series:
        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()

        signal_tf = self._params.get("signal_tf")
        if signal_tf:
            frame = _resample_ohlcv(data, signal_tf)
            if frame.empty:
                return pd.Series(0.0, index=data.index)
            sig_tf = self._signals_on_frame(frame)
            return sig_tf.reindex(data.index, method="ffill").fillna(0.0)

        return self._signals_on_frame(data)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        return {code: self._one(df) for code, df in data_map.items()}
