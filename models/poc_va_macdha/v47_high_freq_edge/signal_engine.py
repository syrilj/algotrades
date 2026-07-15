"""v47_high_freq_edge: high-frequency mean-reversion with triple-barrier exits.

Primary signal: Ultimate RSI color cross (looser os/ob thresholds on 1H).
Meta-filter:    4H trend + 1H volume confirmation.
Bet sizing:     confidence score from filter alignment.
Exit:           ATR stop, ATR take-profit, max-hold vertical barrier,
                oscillator green-cross, optional trailing stop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


DEFAULT_PARAMS: Dict[str, Any] = {
    "length": 14,
    "smooth": 14,
    "ob_value": 70.0,
    "os_value": 30.0,
    "smo_type1": "RMA",
    "smo_type2": "EMA",
    "signal_tf": "1h",
    "src": "close",
    "use_atr_stop": True,
    "atr_mult": 2.5,
    "tp_atr_mult": 2.5,
    "use_tp": False,
    "use_trail": True,
    "atr_period": 14,
    "atr_smo": "RMA",
    "trend_period": 50,
    "trend_tf": "4h",
    "use_trend": False,
    "use_volume": False,
    "vol_sma_period": 20,
    "max_hold_bars": 8,
    "min_confidence": 0.5,
}


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(1, n // 2)).mean()


def _rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def _ma(s: pd.Series, n: int, kind: str) -> pd.Series:
    k = kind.upper()
    if k == "EMA":
        return _ema(s, n)
    if k == "SMA":
        return _sma(s, n)
    if k == "RMA":
        return _rma(s, n)
    raise ValueError(f"Unknown MA kind: {kind}")


def _select_src(df: pd.DataFrame, src: str) -> pd.Series:
    src = src.lower()
    if src == "close":
        return df["close"]
    if src == "hlc3":
        return (df["high"] + df["low"] + df["close"]) / 3.0
    if src == "hl2":
        return (df["high"] + df["low"]) / 2.0
    if src in df.columns:
        return df[src]
    raise ValueError(f"Unknown src: {src}")


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
    cols = ["open", "high", "low", "close", "volume"]
    ohlc = df[[c for c in cols if c in df.columns]].copy()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = ohlc.resample(rule, label="right", closed="right").agg(
        {c: agg[c] for c in ohlc.columns}
    )
    return out.dropna(subset=["close"])


def _ultimate_rsi(
    df: pd.DataFrame,
    length: int = 14,
    smooth: int = 14,
    smo_type1: str = "RMA",
    smo_type2: str = "EMA",
    src: str = "close",
) -> pd.DataFrame:
    """Compute LuxAlgo Ultimate RSI and its signal line."""
    source = _select_src(df, src)
    upper = source.rolling(length, min_periods=1).max()
    lower = source.rolling(length, min_periods=1).min()
    r = upper - lower
    d = source.diff()

    upper_prev = upper.shift(1)
    lower_prev = lower.shift(1)

    diff = np.where(upper > upper_prev, r, np.where(lower < lower_prev, -r, d))
    diff = pd.Series(diff, index=df.index)

    num = _ma(diff, length, smo_type1)
    den = _ma(diff.abs(), length, smo_type1)
    arsi = num / den * 50.0 + 50.0
    signal = _ma(arsi, smooth, smo_type2)
    return pd.DataFrame({"arsi": arsi, "signal": signal, "upper": upper, "lower": lower}, index=df.index)


class SignalEngine:
    """High-frequency mean-reversion with triple-barrier and rule-based meta-sizing."""

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
        return {**DEFAULT_PARAMS, **overrides}

    def _trend_ok(self, raw: pd.DataFrame, target_index: pd.DatetimeIndex) -> pd.Series:
        p = self._params
        if not bool(p.get("use_trend", True)):
            return pd.Series(True, index=target_index)

        trend_tf = str(p.get("trend_tf", "4h"))
        trend_period = int(p.get("trend_period", 50))
        if not trend_tf or trend_tf.lower() in ("", "none"):
            return pd.Series(True, index=target_index)

        tf = _resample_ohlcv(raw, trend_tf)
        if tf.empty or len(tf) < max(2, trend_period // 2):
            return pd.Series(True, index=target_index)

        close = tf["close"].astype(float)
        ema = _ema(close, trend_period)
        trend = close > ema
        out = trend.reindex(target_index, method="ffill").fillna(False)
        return out

    def _volume_ok(self, data: pd.DataFrame) -> pd.Series:
        p = self._params
        if not bool(p.get("use_volume", True)):
            return pd.Series(True, index=data.index)

        vol = data["volume"].astype(float)
        period = int(p.get("vol_sma_period", 20))
        vsma = _sma(vol, period)
        return vol > (vsma * 0.7)

    def _signals_on_frame(self, data: pd.DataFrame, raw: pd.DataFrame) -> pd.Series:
        p = self._params
        out = _ultimate_rsi(
            data,
            length=int(p["length"]),
            smooth=int(p["smooth"]),
            smo_type1=str(p["smo_type1"]),
            smo_type2=str(p["smo_type2"]),
            src=str(p["src"]),
        )
        arsi = out["arsi"]
        ob = float(p["ob_value"])
        os = float(p["os_value"])

        arsi_prev = arsi.shift(1)
        red_cross = (arsi < os) & (arsi_prev >= os)
        green_cross = (arsi > ob) & (arsi_prev <= ob)

        use_atr = bool(p.get("use_atr_stop", True))
        atr_mult = float(p.get("atr_mult", 1.2))
        tp_atr_mult = float(p.get("tp_atr_mult", 2.5))
        use_trail = bool(p.get("use_trail", True))
        atr_period = int(p.get("atr_period", 14))
        atr_smo = str(p.get("atr_smo", "RMA"))
        max_hold = int(p.get("max_hold_bars", 12))
        min_conf = float(p.get("min_confidence", 0.5))

        atr = _atr(data, atr_period, atr_smo) if use_atr else None
        trend_ok = self._trend_ok(raw, data.index)
        vol_ok = self._volume_ok(data)

        signal = pd.Series(0.0, index=data.index)
        in_pos = False
        entry_bar = 0
        entry_size = 0.0
        stop = 0.0
        target = 0.0

        for i in range(len(data)):
            if not in_pos:
                ok = bool(trend_ok.iloc[i])
                if not ok:
                    continue
                if not bool(red_cross.iloc[i]):
                    continue

                confidence = 1.0 if bool(vol_ok.iloc[i]) else 0.5
                if confidence < min_conf:
                    continue

                in_pos = True
                entry_bar = i
                entry_size = confidence
                entry_px = float(data["close"].iloc[i])
                if use_atr and atr is not None and not np.isnan(atr.iloc[i]) and atr.iloc[i] > 0:
                    atr_val = float(atr.iloc[i])
                    stop = entry_px - atr_mult * atr_val
                    target = entry_px + tp_atr_mult * atr_val if bool(p.get("use_tp", False)) else np.inf
                else:
                    stop = 0.0
                    target = np.inf
                signal.iloc[i] = entry_size
            else:
                close_i = float(data["close"].iloc[i])
                high_i = float(data["high"].iloc[i])

                if use_trail and atr is not None and not np.isnan(atr.iloc[i]) and atr.iloc[i] > 0:
                    trail = high_i - atr_mult * float(atr.iloc[i])
                    if trail > stop:
                        stop = trail

                hit_tp = target > 0.0 and close_i >= target
                hit_sl = stop > 0.0 and close_i <= stop
                hit_green = bool(green_cross.iloc[i])
                hit_time = (i - entry_bar) >= max_hold

                if hit_tp or hit_sl or hit_green or hit_time:
                    signal.iloc[i] = 0.0
                    in_pos = False
                    entry_size = 0.0
                    stop = 0.0
                    target = 0.0
                else:
                    signal.iloc[i] = entry_size

        return signal.fillna(0.0)

    def _one(self, df: pd.DataFrame) -> pd.Series:
        data = df.copy()
        data.index = pd.to_datetime(data.index)
        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)
        data = data.sort_index()

        signal_tf = self._params.get("signal_tf")
        if signal_tf and str(signal_tf).strip().lower() not in ("", "none"):
            frame = _resample_ohlcv(data, signal_tf)
            if frame.empty:
                return pd.Series(0.0, index=data.index)
            sig = self._signals_on_frame(frame, raw=data)
            return sig.reindex(data.index, method="ffill").fillna(0.0)

        return self._signals_on_frame(data, raw=data)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        return {code: self._one(df) for code, df in data_map.items()}
