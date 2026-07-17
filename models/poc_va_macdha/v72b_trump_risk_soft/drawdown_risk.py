"""Causal large-drawdown / swing-risk sensors for live-oriented overlays.

Point-in-time contracts (no look-ahead)
--------------------------------------
- Returns are shifted by 1 before rolling vol/corr windows.
- Drawdown is computed from a causal running peak of *finished* closes.
- Expanding baselines (vol median) use prior history only via shift(1).

These helpers are pure: they take OHLCV series/frames and return Series.
Signal engines multiply teacher targets by size mult; unit tests drive
elevated vs calm synthetic series without a full backtest.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import numpy as np
import pandas as pd


def _close(series_or_df: pd.Series | pd.DataFrame, col: str = "close") -> pd.Series:
    if isinstance(series_or_df, pd.DataFrame):
        if col not in series_or_df.columns:
            raise KeyError(f"missing column {col}")
        return series_or_df[col].astype(float)
    return series_or_df.astype(float)


def drawdown_from_peak(close: pd.Series | pd.DataFrame, *, col: str = "close") -> pd.Series:
    """Causal drawdown from running peak: price / cummax - 1 (≤ 0)."""
    px = _close(close, col)
    peak = px.cummax()
    dd = (px / peak.replace(0.0, np.nan)) - 1.0
    return dd.fillna(0.0).rename("drawdown")


def lagged_returns(close: pd.Series | pd.DataFrame, *, col: str = "close") -> pd.Series:
    """One-bar lagged simple returns (causal input to rolling stats)."""
    px = _close(close, col)
    return px.pct_change().shift(1).rename("lagged_ret")


def realized_vol(
    close: pd.Series | pd.DataFrame,
    *,
    window: int = 20,
    min_periods: int | None = None,
    col: str = "close",
) -> pd.Series:
    """Rolling std of lagged returns."""
    min_periods = min_periods if min_periods is not None else max(5, window // 2)
    r = lagged_returns(close, col=col)
    return r.rolling(window, min_periods=min_periods).std().rename("realized_vol")


def vol_ratio(
    close: pd.Series | pd.DataFrame,
    *,
    window: int = 20,
    col: str = "close",
) -> pd.Series:
    """Realized vol / expanding median of prior vol (causal)."""
    vol = realized_vol(close, window=window, col=col)
    med = vol.shift(1).expanding(min_periods=max(10, window)).median()
    ratio = (vol / med.replace(0.0, np.nan)).clip(0.25, 4.0)
    return ratio.fillna(1.0).rename("vol_ratio")


def below_ma(
    close: pd.Series | pd.DataFrame,
    *,
    lookback: int = 50,
    col: str = "close",
) -> pd.Series:
    """True when lagged close is below SMA (entry/exit regime, causal)."""
    px = _close(close, col)
    # Use lagged price vs MA of lagged prices so the open of the next bar
    # does not leak the unfinished bar into the decision for bar t.
    lag = px.shift(1)
    ma = lag.rolling(lookback, min_periods=max(5, lookback // 2)).mean()
    return (lag < ma).fillna(False).rename("below_ma")


def rolling_corr(
    a: pd.Series | pd.DataFrame,
    b: pd.Series | pd.DataFrame,
    *,
    window: int = 20,
    col: str = "close",
) -> pd.Series:
    """Rolling correlation of lagged returns between two series."""
    ra = lagged_returns(a, col=col)
    rb = lagged_returns(b, col=col)
    # Align on intersection of indices
    joined = pd.concat([ra.rename("a"), rb.rename("b")], axis=1, join="inner")
    if joined.empty:
        idx = _close(a, col).index
        return pd.Series(np.nan, index=idx, name="rolling_corr")
    c = joined["a"].rolling(window, min_periods=max(5, window // 2)).corr(joined["b"])
    return c.rename("rolling_corr")


def dd_stress(dd: pd.Series, *, soft: float = -0.03, hard: float = -0.08) -> pd.Series:
    """Map drawdown depth to [0, 1] stress. soft→0, hard→1, linear in between."""
    soft = float(soft)
    hard = float(hard)
    if hard >= soft:
        hard = soft - 0.05
    # dd is ≤ 0; more negative → higher stress
    x = (dd - soft) / (hard - soft)
    return x.clip(0.0, 1.0).fillna(0.0).rename("dd_stress")


def vol_stress(ratio: pd.Series, *, soft: float = 1.15, hard: float = 2.0) -> pd.Series:
    """Map vol_ratio to [0, 1] stress."""
    x = (ratio.astype(float) - soft) / (hard - soft)
    return x.clip(0.0, 1.0).fillna(0.0).rename("vol_stress")


def composite_risk_score(
    market: pd.Series | pd.DataFrame,
    *,
    tech: pd.Series | pd.DataFrame | None = None,
    crypto: pd.Series | pd.DataFrame | None = None,
    dd_soft: float = -0.03,
    dd_hard: float = -0.10,
    vol_window: int = 20,
    ma_lookback: int = 50,
    w_dd: float = 0.45,
    w_vol: float = 0.30,
    w_trend: float = 0.15,
    w_tech: float = 0.10,
    w_crypto: float = 0.0,
) -> pd.Series:
    """Composite elevated-swing risk score in [0, 1].

    Components (all causal):
    - market drawdown stress (SPY)
    - market vol spike stress
    - below MA50 trend break
    - optional tech (QQQ) drawdown stress
    - optional crypto-proxy (COIN/MSTR) drawdown stress weighted by corr to market

    Weights are re-normalized over available components.
    """
    idx = _close(market).index
    dd = drawdown_from_peak(market)
    v_ratio = vol_ratio(market, window=vol_window)
    trend_break = below_ma(market, lookback=ma_lookback).astype(float)

    parts: list[tuple[float, pd.Series]] = [
        (w_dd, dd_stress(dd, soft=dd_soft, hard=dd_hard)),
        (w_vol, vol_stress(v_ratio)),
        (w_trend, trend_break),
    ]

    if tech is not None:
        try:
            tech_dd = drawdown_from_peak(tech).reindex(idx).ffill()
            parts.append((w_tech, dd_stress(tech_dd, soft=dd_soft, hard=dd_hard * 0.9)))
        except Exception:
            pass

    if crypto is not None and w_crypto > 0:
        try:
            c_dd = drawdown_from_peak(crypto).reindex(idx).ffill()
            c_stress = dd_stress(c_dd, soft=-0.08, hard=-0.25)
            corr = rolling_corr(market, crypto).reindex(idx)
            # Only count crypto stress when corridor correlation is elevated
            corr_gate = corr.fillna(0.0).clip(0.0, 1.0)
            parts.append((w_crypto, (c_stress * corr_gate).fillna(0.0)))
        except Exception:
            pass

    w_sum = sum(w for w, _ in parts) or 1.0
    score = pd.Series(0.0, index=idx, dtype=float)
    for w, s in parts:
        score = score + (w / w_sum) * s.reindex(idx).fillna(0.0).astype(float)
    return score.clip(0.0, 1.0).rename("risk_score")


def size_multiplier(
    risk_score: pd.Series,
    *,
    mode: str = "soft",
    elevated_threshold: float = 0.55,
    size_floor: float = 0.0,
    soft_power: float = 1.0,
) -> pd.Series:
    """Map risk score → target size multiplier.

    mode="hard": score >= threshold → size_floor (default 0 = stand aside);
                 otherwise 1.0.
    mode="soft": continuous (1 - score)^power, clipped to [size_floor, 1].
    """
    s = risk_score.astype(float).clip(0.0, 1.0)
    mode = str(mode).lower()
    if mode == "hard":
        mult = pd.Series(
            np.where(s >= float(elevated_threshold), float(size_floor), 1.0),
            index=s.index,
            dtype=float,
        )
    else:
        # soft: elevated risk shrinks size; score=0 → 1.0, score=1 → size_floor
        raw = (1.0 - s) ** float(soft_power)
        mult = (float(size_floor) + (1.0 - float(size_floor)) * raw).clip(
            float(size_floor), 1.0
        )
    return mult.astype(float).rename("size_mult")


def apply_size_mult(
    signals: Mapping[str, pd.Series],
    mult: pd.Series,
) -> Dict[str, pd.Series]:
    """Multiply each code's target series by mult (aligned / ffilled)."""
    out: Dict[str, pd.Series] = {}
    for code, sig in signals.items():
        if sig is None or (hasattr(sig, "empty") and sig.empty):
            out[code] = sig
            continue
        m = mult.reindex(sig.index).ffill().fillna(1.0).astype(float)
        out[code] = (sig.astype(float) * m).astype(float)
    return out


def risk_state_label(score: float, *, elevated_threshold: float = 0.55) -> str:
    if score >= elevated_threshold:
        return "elevated"
    if score >= elevated_threshold * 0.6:
        return "elevated_watch"
    return "calm"


def default_params(mode: str = "hard") -> Dict[str, Any]:
    """Frozen defaults for Trump-era live risk overlays (pre-registered)."""
    mode = str(mode).lower()
    if mode == "hard":
        return {
            "mode": "hard",
            "elevated_threshold": 0.55,
            "size_floor": 0.0,
            "dd_soft": -0.03,
            "dd_hard": -0.10,
            "vol_window": 20,
            "ma_lookback": 50,
            "w_dd": 0.45,
            "w_vol": 0.30,
            "w_trend": 0.15,
            "w_tech": 0.10,
            "w_crypto": 0.0,
            "market_code": "SPY.US",
            "tech_code": "QQQ.US",
            "crypto_codes": ["COIN.US", "MSTR.US"],
            "teacher": "v39d_confluence",
        }
    return {
        "mode": "soft",
        "elevated_threshold": 0.50,
        "size_floor": 0.15,
        "soft_power": 1.25,
        "dd_soft": -0.025,
        "dd_hard": -0.12,
        "vol_window": 16,
        "ma_lookback": 40,
        "w_dd": 0.35,
        "w_vol": 0.30,
        "w_trend": 0.15,
        "w_tech": 0.10,
        "w_crypto": 0.10,
        "market_code": "SPY.US",
        "tech_code": "QQQ.US",
        "crypto_codes": ["COIN.US", "MSTR.US"],
        "teacher": "v39b_live_adapt",
    }


def score_from_data_map(
    data_map: Mapping[str, pd.DataFrame],
    params: Optional[Dict[str, Any]] = None,
) -> pd.Series:
    """Build risk score from a multi-asset data_map using param codes."""
    p = dict(default_params("soft"))
    if params:
        p.update(params)
    market_code = str(p.get("market_code", "SPY.US"))
    tech_code = str(p.get("tech_code", "QQQ.US"))
    crypto_codes = list(p.get("crypto_codes") or [])

    market = data_map.get(market_code)
    if market is None or market.empty:
        # No market reference → calm (do not block teacher blindly)
        any_df = next((df for df in data_map.values() if df is not None and not df.empty), None)
        if any_df is None:
            return pd.Series(dtype=float, name="risk_score")
        return pd.Series(0.0, index=any_df.index, name="risk_score")

    tech = data_map.get(tech_code)
    crypto = None
    for c in crypto_codes:
        df = data_map.get(c)
        if df is not None and not df.empty:
            crypto = df
            break

    return composite_risk_score(
        market,
        tech=tech,
        crypto=crypto,
        dd_soft=float(p.get("dd_soft", -0.03)),
        dd_hard=float(p.get("dd_hard", -0.10)),
        vol_window=int(p.get("vol_window", 20)),
        ma_lookback=int(p.get("ma_lookback", 50)),
        w_dd=float(p.get("w_dd", 0.45)),
        w_vol=float(p.get("w_vol", 0.30)),
        w_trend=float(p.get("w_trend", 0.15)),
        w_tech=float(p.get("w_tech", 0.10)),
        w_crypto=float(p.get("w_crypto", 0.0)),
    )
