"""Ultimate RSI mean-reversion with ATR stop and regime filter.

Ports the LuxAlgo "Ultimate RSI" oscillator and trades the color rule, but
adds a protective ATR stop/trail and a trend-regime filter to cut the large
drawdowns of the raw mean-reversion signal.

  - Buy long when the oscillator line becomes red (crosses under oversold).
  - Exit when the line becomes green (crosses over overbought) OR an ATR stop
    is hit.
  - Optional regime filter: only enter when price is above a long-period SMA
    (i.e., avoid catching falling knives in strong downtrends).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


DEFAULT_PARAMS: Dict[str, Any] = {
    "length": 21,
    "smooth": 14,
    "ob_value": 70.0,
    "os_value": 30.0,
    "smo_type1": "RMA",
    "smo_type2": "EMA",
    "signal_tf": "4h",
    "src": "close",
    "use_atr_stop": True,
    "atr_mult": 2.5,
    "use_trail": True,
    "atr_period": 14,
    "atr_smo": "RMA",
    "regime_period": 0,
    "use_regime": False,
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
    ohlc = df[["open", "high", "low", "close", "volume"]].copy()
    out = ohlc.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    return out


def ultimate_rsi(
    df: pd.DataFrame,
    length: int = 14,
    smooth: int = 14,
    smo_type1: str = "RMA",
    smo_type2: str = "EMA",
    src: str = "close",
) -> pd.DataFrame:
    """Compute the LuxAlgo Ultimate RSI and its signal line."""
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

    return pd.DataFrame(
        {"arsi": arsi, "signal": signal, "upper": upper, "lower": lower},
        index=df.index,
    )


class SignalEngine:
    """Ultimate RSI color-rule mean reversion with ATR stop and regime filter."""

    def __init__(self) -> None:
        self._params = self._load_params()

    def _load_params(self) -> Dict[str, Any]:
        # Search for config.json in the run directory (preferred) or the model dir.
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

        # Accept parameters at top-level or inside strategy. Top-level wins.
        strategy = cfg.get("strategy", {}) if isinstance(cfg.get("strategy"), dict) else {}
        overrides = {**strategy, **{k: cfg[k] for k in DEFAULT_PARAMS if k in cfg}}
        return {**DEFAULT_PARAMS, **overrides}

    def _signals_on_frame(self, data: pd.DataFrame) -> pd.Series:
        p = self._params
        out = ultimate_rsi(
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

        use_atr = bool(p.get("use_atr_stop", False))
        use_trail = bool(p.get("use_trail", False))
        atr_mult = float(p.get("atr_mult", 2.5))
        atr_period = int(p.get("atr_period", int(p["length"])))
        atr_smo = str(p.get("atr_smo", "RMA"))

        atr = _atr(data, atr_period, atr_smo) if use_atr else None

        use_regime = bool(p.get("use_regime", False))
        regime_period = int(p.get("regime_period", 50))
        regime_ok = pd.Series(True, index=data.index)
        if use_regime and regime_period > 0:
            regime_sma = data["close"].rolling(regime_period, min_periods=max(1, regime_period // 2)).mean()
            regime_ok = data["close"] > regime_sma

        signal = pd.Series(0.0, index=data.index)
        in_pos = False
        stop = 0.0
        for i in range(len(data)):
            if not in_pos:
                if bool(red_cross.iloc[i]) and bool(regime_ok.iloc[i]):
                    in_pos = True
                    entry_px = float(data["close"].iloc[i])
                    if use_atr and atr is not None and not np.isnan(atr.iloc[i]):
                        stop = entry_px - atr_mult * float(atr.iloc[i])
                    else:
                        stop = 0.0
                    signal.iloc[i] = 1.0
            else:
                close_i = float(data["close"].iloc[i])
                high_i = float(data["high"].iloc[i])

                if use_trail and atr is not None and not np.isnan(atr.iloc[i]):
                    trail = high_i - atr_mult * float(atr.iloc[i])
                    if trail > stop:
                        stop = trail

                exit = bool(green_cross.iloc[i]) or (use_atr and stop > 0.0 and close_i < stop)
                if exit:
                    signal.iloc[i] = 0.0
                    in_pos = False
                    stop = 0.0
                else:
                    signal.iloc[i] = 1.0
        return signal.fillna(0.0)

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
