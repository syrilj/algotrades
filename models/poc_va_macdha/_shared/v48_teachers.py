"""Causal, self-contained teacher implementations used by the v48 family.

The module deliberately has no model-directory imports.  A v48 run snapshots this
file beside its signal engine, so teacher behaviour is pinned by the run manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd


REQUIRED_OHLCV = ("open", "high", "low", "close", "volume")


def normalise_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [name for name in REQUIRED_OHLCV if name not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV frame is missing {missing}")
    out = frame.loc[:, REQUIRED_OHLCV].copy()
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_convert("America/New_York").tz_localize(None)
    out = out.sort_index().astype(float)
    if not out.index.is_unique or out.isna().any().any():
        raise ValueError("OHLCV index must be unique and values complete")
    if (out["high"] < out[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("invalid OHLC high")
    if (out["low"] > out[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("invalid OHLC low")
    if (out["volume"] < 0).any():
        raise ValueError("negative OHLCV volume")
    return out


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1.0 / float(length), adjust=False).mean()


def _atr(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    prev_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _rma(true_range, length)


def _daily_vwap(frame: pd.DataFrame) -> pd.Series:
    session = frame.index.normalize()
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    numerator = (typical * frame["volume"]).groupby(session).cumsum()
    denominator = frame["volume"].groupby(session).cumsum().replace(0.0, np.nan)
    return numerator / denominator


def _relative_strength(
    close: pd.Series, benchmark: pd.Series | None, lookback: int = 5
) -> pd.Series:
    own = close.pct_change(lookback).shift(1)
    if benchmark is None or benchmark.empty:
        return own.fillna(0.0)
    bench = benchmark.reindex(close.index, method="ffill").pct_change(lookback).shift(1)
    return (own - bench).fillna(0.0)


@dataclass(frozen=True)
class TrendParams:
    profile_bars: int = 20
    atr_period: int = 14
    stop_atr: float = 1.5
    trail_atr: float = 2.5
    min_volume_ratio: float = 0.70


class TrendTeacher:
    """Causal v39d-style trend/value sleeve.

    It uses only rolling, completed-bar statistics.  All state is local to a
    symbol, avoiding the former cross-symbol streak coupling.
    """

    def __init__(self, params: TrendParams | None = None) -> None:
        self.params = params or TrendParams()

    def _one(self, frame: pd.DataFrame, benchmark: pd.Series | None) -> pd.Series:
        data = normalise_ohlcv(frame)
        p = self.params
        close = data["close"]
        volume = data["volume"]
        typical = (data["high"] + data["low"] + close) / 3.0
        prior_poc = (
            (typical * volume).rolling(p.profile_bars, min_periods=8).sum()
            / volume.rolling(p.profile_bars, min_periods=8).sum().replace(0.0, np.nan)
        ).shift(1)
        vwap = _daily_vwap(data).shift(1)
        fast = _ema(close, 12)
        slow = _ema(close, 26)
        macd_hist = (fast - slow - _ema(fast - slow, 9)).shift(1)
        atr = _atr(data, p.atr_period)
        atr_pct = (atr / close.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        prior_median_atr = atr_pct.shift(1).expanding(min_periods=20).median().fillna(0.02)
        volume_ratio = (volume.shift(1) / volume.rolling(20, min_periods=8).mean().shift(1)).fillna(0.0)
        rs = _relative_strength(close, benchmark)

        long_entry = (
            (close >= prior_poc)
            & (close >= vwap)
            & (fast.shift(1) >= slow.shift(1))
            & (macd_hist >= 0.0)
            & (volume_ratio >= p.min_volume_ratio)
            & (rs >= -0.04)
        ).fillna(False)

        signal = pd.Series(0.0, index=data.index)
        in_position = False
        entry_price = peak_price = entry_atr = 0.0
        entry_size = 0.0
        for i, timestamp in enumerate(data.index):
            price = float(close.iloc[i])
            current_atr = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else price * 0.01
            if not in_position:
                if not bool(long_entry.iloc[i]):
                    continue
                current_atr_pct = float(atr_pct.iloc[i]) if np.isfinite(atr_pct.iloc[i]) else 0.02
                vol_scale = float(
                    np.clip(prior_median_atr.iloc[i] / max(current_atr_pct, 1e-6), 0.55, 1.20)
                )
                rs_scale = float(np.clip(1.0 + 2.0 * float(rs.iloc[i]), 0.75, 1.20))
                entry_size = float(np.clip(0.65 * vol_scale * rs_scale, 0.25, 1.0))
                in_position = True
                entry_price = peak_price = price
                entry_atr = max(current_atr, price * 0.002)
                signal.iloc[i] = entry_size
                continue

            peak_price = max(peak_price, float(data["high"].iloc[i]))
            hard_stop = price <= entry_price - p.stop_atr * entry_atr
            trail_stop = peak_price >= entry_price + entry_atr and price <= peak_price - p.trail_atr * entry_atr
            momentum_exit = bool(fast.shift(1).iloc[i] < slow.shift(1).iloc[i] and macd_hist.iloc[i] < 0.0)
            if hard_stop or trail_stop or momentum_exit:
                in_position = False
                entry_size = 0.0
                signal.iloc[i] = 0.0
            else:
                signal.iloc[i] = entry_size
        return signal

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        benchmark = data_map.get("QQQ.US")
        benchmark_close = normalise_ohlcv(benchmark)["close"] if benchmark is not None else None
        return {code: self._one(frame, benchmark_close) for code, frame in data_map.items()}


@dataclass(frozen=True)
class MeanReversionParams:
    length: int = 14
    smooth: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    atr_mult: float = 2.5
    max_hold_bars: int = 8


def _ultimate_rsi(close: pd.Series, length: int, smooth: int) -> tuple[pd.Series, pd.Series]:
    upper = close.rolling(length, min_periods=1).max()
    lower = close.rolling(length, min_periods=1).min()
    spread = upper - lower
    delta = close.diff()
    raw = pd.Series(
        np.where(upper > upper.shift(1), spread, np.where(lower < lower.shift(1), -spread, delta)),
        index=close.index,
    )
    arsi = _rma(raw, length) / _rma(raw.abs(), length).replace(0.0, np.nan) * 50.0 + 50.0
    return arsi, _ema(arsi, smooth)


class MeanReversionTeacher:
    """Frozen causal Ultimate-RSI mean-reversion sleeve."""

    def __init__(self, params: MeanReversionParams | None = None) -> None:
        self.params = params or MeanReversionParams()

    def _one(self, frame: pd.DataFrame) -> pd.Series:
        data = normalise_ohlcv(frame)
        p = self.params
        close = data["close"]
        arsi, _ = _ultimate_rsi(close, p.length, p.smooth)
        prior = arsi.shift(1)
        red_cross = ((arsi < p.oversold) & (prior >= p.oversold)).fillna(False)
        green_cross = ((arsi > p.overbought) & (prior <= p.overbought)).fillna(False)
        atr = _atr(data, p.length)
        signal = pd.Series(0.0, index=data.index)
        in_position = False
        entry_price = peak_price = stop = 0.0
        entry_bar = 0
        for i in range(len(data)):
            price = float(close.iloc[i])
            if not in_position:
                if not bool(red_cross.iloc[i]):
                    continue
                atr_value = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else price * 0.01
                entry_price = peak_price = price
                stop = price - p.atr_mult * max(atr_value, price * 0.002)
                entry_bar = i
                in_position = True
                signal.iloc[i] = 1.0
                continue
            peak_price = max(peak_price, float(data["high"].iloc[i]))
            atr_value = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else 0.0
            if atr_value > 0.0:
                stop = max(stop, peak_price - p.atr_mult * atr_value)
            exit_now = price <= stop or bool(green_cross.iloc[i]) or (i - entry_bar >= p.max_hold_bars)
            if exit_now:
                in_position = False
                signal.iloc[i] = 0.0
            else:
                signal.iloc[i] = 1.0
        return signal

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        return {code: self._one(frame) for code, frame in data_map.items()}
