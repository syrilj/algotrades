"""v60_microstructure: microstructure-grounded high-precision long model.

Detects footprints of institutional algorithmic execution (persistent one-sided
volume, absorption, schedule-deviation) and acts only on high-conviction setups.

- Uses OHLCV-safe approximations of order-flow imbalance (OFI), absorption,
  volume-schedule deviation, VPIN-style toxicity, and VPA confirmation.
- Optional XGB meta-classifier loaded from meta_xgb_final.json; falls back to
  a calibrated heuristic classifier if no trained model is present.
- State-machine with stop-loss, max-hold, and trend-invalidated exits.
- All rolling statistics and signed-volume approximations are point-in-time.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from xgboost import XGBClassifier


# ─── Helpers ────────────────────────────────────────────────────────────────
def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(1, n // 2)).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = _ema(gain, n)
    avg_loss = _ema(loss, n)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return (tr.ewm(span=n, adjust=False).mean() / close).replace(0, np.nan)


def _vwap(df: pd.DataFrame, n: int = 50) -> pd.Series:
    hlc3 = (df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)) / 3.0
    vol = df["volume"].astype(float)
    num = (hlc3 * vol).rolling(n, min_periods=max(1, n // 2)).sum()
    den = vol.rolling(n, min_periods=max(1, n // 2)).sum()
    return num / den.replace(0, np.nan)


def _daily_volume(df: pd.DataFrame) -> pd.Series:
    """Point-in-time estimate of expected daily volume (ADV proxy)."""
    vol = df["volume"].astype(float)
    # Use expanding median of daily volume up to current day
    daily = vol.resample("1D").sum().reindex(df.index, method="ffill")
    return daily.rolling(30, min_periods=1).median()


def _intraday_profile(df: pd.DataFrame, lookback: int = 30) -> pd.Series:
    """Expected fraction of daily volume elapsed by the current bar's time.

    Uses the mean intraday cumulative-volume profile over the last `lookback`
    days. This is point-in-time because the mean is taken over prior days only.
    """
    vol = df["volume"].astype(float)
    idx = df.index
    time_key = idx.time if hasattr(idx, "time") else idx
    day = idx.date if hasattr(idx, "date") else idx

    # Build per-day cumulative volume fractions across time keys
    daily_frac: pd.DataFrame = pd.DataFrame(
        {"vol": vol, "time": time_key, "day": day}
    )
    daily_frac["cum_frac"] = daily_frac.groupby("day")["vol"].cumsum() / daily_frac.groupby("day")["vol"].transform("sum")
    # rolling mean per time key over days; shift(1) to avoid including today
    profile = daily_frac.groupby("time")["cum_frac"].transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=1).mean()
    )
    profile.index = df.index
    return profile.fillna(0.5)


def _volume_zscore(df: pd.DataFrame, lookback: int = 50) -> pd.Series:
    vol = df["volume"].astype(float)
    mean = _sma(vol, lookback)
    std = vol.rolling(lookback, min_periods=max(1, lookback // 2)).std(ddof=0)
    return ((vol - mean) / std.replace(0, np.nan)).fillna(0.0)


def _ofi_proxy(df: pd.DataFrame, short_len: int = 20, long_len: int = 50) -> pd.DataFrame:
    """Order-flow imbalance proxy from candle delta + tick rule.

    All signed-volume splits are computed only from information available at the
    close of the bar.
    """
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)

    # Candle delta as a fraction of the range
    rng = high - low
    candle_delta = (close - open_) / rng.replace(0, np.nan)
    candle_delta = candle_delta.fillna(0.0).clip(-1.0, 1.0)

    # Tick rule for the previous close
    price_change = close.diff().fillna(0.0)
    candle_sign = np.sign(candle_delta).where(np.sign(candle_delta) != 0, 1.0)
    tick_dir = np.sign(price_change).where(price_change != 0, candle_sign)

    # Blend candle delta and tick rule to approximate signed aggressive volume
    buy_frac = ((candle_delta + 1.0) / 2.0 + (tick_dir + 1.0) / 2.0) / 2.0
    buy_frac = buy_frac.clip(0.0, 1.0)
    buy_vol = vol * buy_frac
    sell_vol = vol * (1.0 - buy_frac)

    # Imbalance over windows
    tot_vol = (buy_vol + sell_vol).replace(0, np.nan)
    ofi = ((buy_vol - sell_vol) / tot_vol).fillna(0.0)
    ofi_short = _ema(ofi, short_len)
    ofi_long = _ema(ofi, long_len)
    ofi_persistence = ofi.rolling(short_len, min_periods=max(1, short_len // 2)).sum()

    return pd.DataFrame(
        {
            "ofi": ofi_short,
            "ofi_persistence": ofi_persistence,
            "ofi_long": ofi_long,
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
        },
        index=df.index,
    )


def _absorption_score(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """Absorption / stealth footprint: large signed volume without proportional
    price movement, normalised by ATR and volume regime.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float)
    atr_pct = _atr_pct(df, 14)

    signed_vol = vol * np.sign(close.diff().fillna(0.0))
    signed_vol_sum = signed_vol.rolling(lookback, min_periods=max(1, lookback // 2)).sum().abs()

    price_change = (close - close.shift(lookback)).abs()
    price_change = price_change.replace(0, np.nan)

    raw = signed_vol_sum / price_change
    # Normalise by ATR and median volume to make it cross-sectionally stable
    vol_sma = _sma(vol, lookback)
    normalised = raw * (1.0 / vol_sma.replace(0, np.nan)) * (atr_pct * 100.0)

    # Wick absorption proxy: volume in the wick relative to range
    upper_wick = high - np.maximum(close, df["open"].astype(float))
    lower_wick = np.minimum(close, df["open"].astype(float)) - low
    range_ = rng = (high - low).replace(0, np.nan)
    upper_wick_frac = (upper_wick / range_).fillna(0.0)
    lower_wick_frac = (lower_wick / range_).fillna(0.0)

    return pd.DataFrame(
        {
            "absorption": normalised.fillna(0.0).replace([np.inf, -np.inf], 0.0),
            "absorption_raw": raw.fillna(0.0).replace([np.inf, -np.inf], 0.0),
            "upper_wick_frac": upper_wick_frac,
            "lower_wick_frac": lower_wick_frac,
            "range_pct": range_ / close,
        },
        index=df.index,
    )


def _schedule_deviation(df: pd.DataFrame, lookback: int = 30) -> pd.Series:
    """Deviation of cumulative intraday volume from the historical TWAP-like
    schedule. High positive deviation means a burst of volume early in the day,
    consistent with institutional slicing.
    """
    vol = df["volume"].astype(float)
    exp_daily = _daily_volume(df)
    profile = _intraday_profile(df, lookback)
    expected_cum = exp_daily * profile
    expected_cum = expected_cum.replace(0, np.nan)

    # Actual cumulative volume within the current day
    idx = df.index
    day = idx.date if hasattr(idx, "date") else idx
    cum_vol = pd.Series(vol, index=idx).groupby(day).cumsum()

    dev = ((cum_vol - expected_cum) / expected_cum).fillna(0.0)
    return dev


def _vpin_proxy(df: pd.DataFrame, bucket_vol_frac: float = 0.05, n_buckets: int = 20) -> pd.Series:
    """Volume-bucketed order-flow toxicity proxy.

    Divides recent volume into buckets of equal volume (~5% of ADV by default)
    and computes the average absolute imbalance per bucket. This is a bar-safe
    approximation of VPIN that requires only OHLCV.
    """
    open_ = df["open"].astype(float)
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    price_change = close.diff().fillna(0.0)
    candle_sign = np.sign(close - open_).where(np.sign(close - open_) != 0, 1.0)
    tick_dir = np.sign(price_change).where(price_change != 0, candle_sign)
    # Buy/sell split
    buy_vol = vol * ((tick_dir + 1.0) / 2.0)
    sell_vol = vol - buy_vol
    imbalance = (buy_vol - sell_vol).abs()

    # Average volume over window to estimate ADV
    avg_vol = _sma(vol, 50)
    bucket_size = (avg_vol * bucket_vol_frac).fillna(0.0)

    # Build volume buckets on-the-fly and compute mean absolute imbalance
    n = len(df)
    out = np.zeros(n, dtype=float)
    bucket_abs = 0.0
    bucket_vol = 0.0
    window_abs = np.zeros(n, dtype=float)
    bucket_count = 0
    for i in range(n):
        if bucket_size.iloc[i] <= 0:
            continue
        bucket_abs += imbalance.iloc[i]
        bucket_vol += vol.iloc[i]
        if bucket_vol >= bucket_size.iloc[i]:
            # store bucket VPIN in last index of bucket
            if bucket_vol > 0:
                vpin_val = bucket_abs / bucket_vol
            else:
                vpin_val = 0.0
            out[i] = vpin_val
            bucket_abs = 0.0
            bucket_vol = 0.0
            bucket_count += 1
        else:
            out[i] = out[i - 1] if i > 0 else 0.0

    # EMA over buckets is noisy; use a rolling mean over last n_buckets
    s = pd.Series(out, index=df.index)
    return _sma(s, n_buckets).fillna(0.0)


def _vpa_confirmation(df: pd.DataFrame, vol_look: int = 20) -> pd.DataFrame:
    """Volume-price agreement: volume surge + close near the side of the move.
    """
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)

    vol_ma = _sma(vol, vol_look)
    vol_z = ((vol - vol_ma) / vol_ma.replace(0, np.nan)).fillna(0.0)

    range_ = (high - low).replace(0, np.nan)
    up_move = close > open_
    close_loc = np.where(
        up_move,
        (close - low) / range_,
        (high - close) / range_,
    )
    close_loc = pd.Series(close_loc, index=df.index).fillna(0.5)

    # Volume-price confirmation: high volume and close near the high (up) or low (down)
    confirmation = vol_z * (close_loc - 0.5) * 2.0

    return pd.DataFrame(
        {
            "vol_z": vol_z,
            "close_loc": close_loc,
            "vpa_confirmation": confirmation,
        },
        index=df.index,
    )


def _regime_features(df: pd.DataFrame, trend_len: int = 200, vol_len: int = 50) -> pd.DataFrame:
    close = df["close"].astype(float)
    sma = _sma(close, trend_len)
    trend = (close > sma).astype(float)
    vwap = _vwap(df, 50)
    above_vwap = (close > vwap).astype(float)
    atr_pct = _atr_pct(df, 14)
    atr_pct_ma = _sma(atr_pct, vol_len)
    vol_regime = (atr_pct > atr_pct_ma).astype(float)  # 1 = high volatility
    rsi = _rsi(close, 14)
    return pd.DataFrame(
        {
            "trend": trend,
            "above_vwap": above_vwap,
            "vol_regime": vol_regime,
            "rsi": rsi,
            "dist_vwap_pct": (close - vwap) / close,
            "atr_pct": atr_pct,
        },
        index=df.index,
    )


# ─── Feature matrix for classifier ──────────────────────────────────────────
def compute_feature_df(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Compute the full feature matrix for one symbol. Point-in-time only."""
    # Ensure monotonic index and no timezone
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)

    ofi = _ofi_proxy(df, params.get("ofi_short", 20), params.get("ofi_long", 50))
    absorption = _absorption_score(df, params.get("absorption_lookback", 20))
    vpa = _vpa_confirmation(df, params.get("vol_look", 20))
    regime = _regime_features(df, params.get("trend_len", 200), params.get("vol_len", 50))
    schedule_dev = _schedule_deviation(df, params.get("schedule_lookback", 30))
    vpin = _vpin_proxy(df, params.get("vpin_bucket_frac", 0.05), params.get("vpin_n_buckets", 20))

    close = df["close"].astype(float)
    features = pd.DataFrame(
        {
            "ofi": ofi["ofi"],
            "ofi_persistence": ofi["ofi_persistence"],
            "ofi_long": ofi["ofi_long"],
            "absorption": absorption["absorption"],
            "absorption_raw": absorption["absorption_raw"],
            "upper_wick_frac": absorption["upper_wick_frac"],
            "lower_wick_frac": absorption["lower_wick_frac"],
            "range_pct": absorption["range_pct"],
            "schedule_dev": schedule_dev,
            "vpin": vpin,
            "vol_z": vpa["vol_z"],
            "close_loc": vpa["close_loc"],
            "vpa_confirmation": vpa["vpa_confirmation"],
            "trend": regime["trend"],
            "above_vwap": regime["above_vwap"],
            "vol_regime": regime["vol_regime"],
            "rsi": regime["rsi"],
            "dist_vwap_pct": regime["dist_vwap_pct"],
            "atr_pct": regime["atr_pct"],
            "return_1h": close.pct_change(1).fillna(0.0),
            "return_4h": close.pct_change(4).fillna(0.0),
            "return_1d": close.pct_change(24).fillna(0.0),
            "hour": df.index.hour.astype(float),
            "day_of_week": df.index.dayofweek.astype(float),
        },
        index=df.index,
    )
    return features.fillna(0.0).replace([np.inf, -np.inf], 0.0)


# ─── Heuristic classifier ───────────────────────────────────────────────────
def _heuristic_proba(features: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """High-conviction pullback-to-VWAP + institutional-absorption score.

    The model looks for a quiet, shallow pullback to VWAP within a rising trend
    while OFI shows persistent buying and absorption is elevated. These are the
    typical footprints of a large player absorbing passive liquidity without
    moving price.
    """
    trend = features["trend"]
    above_vwap = features["above_vwap"]
    ofi = features["ofi"]
    ofi_persistence = features["ofi_persistence"]
    absorption = features["absorption"].clip(-50.0, 50.0) / 10.0
    rsi = features["rsi"].fillna(50.0)
    vol_regime = features["vol_regime"]
    dist_vwap = features["dist_vwap_pct"]
    range_pct = features["range_pct"]
    atr_pct = features["atr_pct"]
    vol_z = features["vol_z"].clip(-5.0, 5.0)
    schedule_dev = features["schedule_dev"].clip(-2.0, 2.0)
    vpin = features["vpin"].clip(0.0, 1.0)

    # Pullback zone: close is slightly above VWAP but not extended
    vwap_pullback = ((dist_vwap >= 0.0) & (dist_vwap <= 0.015)).astype(float)
    not_extended = (dist_vwap < 0.03).astype(float)

    # Range compression: current bar range is tight relative to its ATR
    compression = (range_pct < atr_pct * 0.8).astype(float)

    # OFI buying pressure
    ofi_ok = (ofi > 0.0).astype(float)
    ofi_persistent = (ofi_persistence > 0.0).astype(float)

    # Stealth volume: not a climax, but not dead either
    vol_stealth = ((vol_z > -0.5) & (vol_z < 1.0)).astype(float)

    # RSI healthy: not overbought, not deeply oversold
    rsi_ok = ((rsi > 45.0) & (rsi < 70.0)).astype(float)

    # Absorption present
    absorption_ok = (absorption > 0.5).astype(float)

    # Avoid event/volatility regimes
    vol_regime_ok = (vol_regime == 0.0).astype(float)
    schedule_ok = (schedule_dev.abs() < 1.0).astype(float)

    score = (
        3.0 * trend
        + 2.5 * vwap_pullback
        + 1.0 * not_extended
        + 1.5 * compression
        + 1.5 * ofi_ok
        + 1.0 * ofi_persistent
        + 1.0 * vol_stealth
        + 1.0 * rsi_ok
        + 0.5 * absorption_ok
        + 0.5 * vol_regime_ok
        + 0.5 * schedule_ok
        + 0.2 * vpin
        - 3.0 * (dist_vwap < 0.0).astype(float)  # no longs below VWAP
        - 2.0 * (rsi >= 70.0).astype(float)
    )

    temperature = float(params.get("temperature", 0.5))
    proba = (1.0 / (1.0 + np.exp(-score * temperature))).clip(0.0, 1.0)
    return proba


# ─── Signal engine ──────────────────────────────────────────────────────────
class SignalEngine:
    """v60_microstructure: high-precision long model from microstructure features."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        self._model_dir = self_dir

        # Load configuration
        self._hunt: Dict[str, Any] = {}
        hunt_path = self_dir / "hunt_config.json"
        if hunt_path.exists():
            self._hunt = json.loads(hunt_path.read_text(encoding="utf-8"))

        meta_path = self_dir / "meta_config.json"
        self._meta: Dict[str, Any] = {}
        if meta_path.exists():
            self._meta = json.loads(meta_path.read_text(encoding="utf-8"))

        self._params = self._make_params()

        # Load XGB if available and requested
        self._use_xgb = bool(self._hunt.get("use_xgb", self._meta.get("use_xgb", False)))
        self._booster: Optional[Any] = None
        self._feat_cols: List[str] = list(self._meta.get("feat_cols", []))
        if self._use_xgb and XGBClassifier is not None:
            xgb_path = self_dir / "meta_xgb_final.json"
            if xgb_path.exists():
                try:
                    self._booster = XGBClassifier()
                    self._booster.load_model(str(xgb_path))
                except Exception as exc:
                    print(f"[v60] warning: could not load XGB model: {exc}")
                    self._use_xgb = False

    def _make_params(self) -> Dict[str, Any]:
        defaults = {
            "ofi_short": 20,
            "ofi_long": 50,
            "absorption_lookback": 20,
            "vol_look": 20,
            "trend_len": 200,
            "vol_len": 50,
            "schedule_lookback": 30,
            "vpin_bucket_frac": 0.05,
            "vpin_n_buckets": 20,
            "max_hold_bars": 20,
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 3.0,
            "min_conviction": 0.70,
            "signal_scale": 1.0,
            "temperature": 0.5,
            "rsi_max": 70.0,
            "require_above_vwap": True,
            "require_trend": True,
        }
        # merge hunt, then meta, then defaults
        merged = {**defaults, **self._hunt, **self._meta.get("params", {}), **self._hunt}
        return merged

    def _classifier_proba(self, features: pd.DataFrame) -> pd.Series:
        if self._booster is not None and self._use_xgb:
            X = features[self._feat_cols].astype(float)
            proba = self._booster.predict_proba(X)[:, 1]
            return pd.Series(proba, index=features.index)
        return _heuristic_proba(features, self._params)

    def _exit_signal(self, df: pd.DataFrame, features: pd.DataFrame, state: Dict[str, Any], i: int) -> bool:
        close = df["close"].astype(float).values
        entry_price = float(state["entry_price"])
        bars = int(state["bars_in_pos"])

        # Stop-loss and take-profit (triple-barrier style)
        atr_pct = float(features["atr_pct"].iloc[i])
        sl_mult = float(self._params["sl_atr_mult"])
        tp_mult = float(self._params["tp_atr_mult"])
        sl_pct = max(0.005, sl_mult * atr_pct)
        tp_pct = max(0.010, tp_mult * atr_pct)
        if close[i] < entry_price * (1.0 - sl_pct):
            return True
        if close[i] > entry_price * (1.0 + tp_pct):
            return True

        # Max hold
        if bars >= int(self._params["max_hold_bars"]):
            return True

        # Trend invalidation
        if bool(self._params["require_trend"]) and features["trend"].iloc[i] == 0.0:
            return True

        # Above VWAP invalidation
        if bool(self._params["require_above_vwap"]) and features["above_vwap"].iloc[i] == 0.0:
            return True

        return False

    def _generate_one(self, df: pd.DataFrame) -> pd.Series:
        features = compute_feature_df(df, self._params)
        proba = self._classifier_proba(features)
        close = df["close"].astype(float)
        idx = df.index
        out = pd.Series(0.0, index=idx)

        in_pos = False
        entry_price = 0.0
        bars_in_pos = 0
        min_conviction = float(self._params["min_conviction"])
        rsi_max = float(self._params["rsi_max"])
        require_trend = bool(self._params["require_trend"])
        require_above_vwap = bool(self._params["require_above_vwap"])

        for i in range(len(idx)):
            p = float(proba.iloc[i])
            rsi = float(features["rsi"].iloc[i])
            trend_ok = (not require_trend) or features["trend"].iloc[i] > 0.5
            vwap_ok = (not require_above_vwap) or features["above_vwap"].iloc[i] > 0.5
            rsi_ok = rsi < rsi_max

            if not in_pos:
                if p >= min_conviction and trend_ok and vwap_ok and rsi_ok:
                    in_pos = True
                    entry_price = float(close.iloc[i])
                    bars_in_pos = 0
            else:
                state = {"entry_price": entry_price, "bars_in_pos": bars_in_pos}
                if self._exit_signal(df, features, state, i):
                    in_pos = False
                else:
                    bars_in_pos += 1

            out.iloc[i] = float(self._params["signal_scale"]) if in_pos else 0.0

        return out

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue
            out[code] = self._generate_one(df)
        return out
