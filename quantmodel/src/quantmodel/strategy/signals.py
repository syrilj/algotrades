"""Signal computation for Donchian swing trend model."""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from quantmodel.data.earnings import earnings_blackout_mask
from quantmodel.data.universe import annotate_universe_features, eligible_mask
from quantmodel.indicators.atr import atr_wilder
from quantmodel.indicators.donchian import donchian_exit, prior_high, prior_low
from quantmodel.indicators.moving_average import sma
from quantmodel.indicators.volume import prior_median_volume, volume_multiple_ratio


def compute_features(bars: pd.DataFrame, config: Mapping) -> pd.DataFrame:
    """Add indicator columns per security. Uses adjusted series for signal continuity."""
    s = config["signal"]
    r = config["risk"]
    out = annotate_universe_features(bars)
    parts: list[pd.DataFrame] = []
    for sid, grp in out.groupby("permanent_security_id", sort=False):
        g = grp.sort_values("date").copy()
        high = g["adjusted_high"]
        low = g["adjusted_low"]
        close = g["adjusted_close"]
        vol = g["volume"]  # raw volume for confirmation per spec default
        g["prior_entry_high"] = prior_high(high, int(s["entry_lookback"]))
        g["prior_exit_low"] = prior_low(low, int(s["exit_lookback"]))
        g["sma_trend"] = sma(close, int(s["trend_sma_days"]))
        g["median_vol"] = prior_median_volume(vol, int(s["volume_lookback"]))
        g["volume_mult"] = volume_multiple_ratio(vol, int(s["volume_lookback"]))
        g["atr"] = atr_wilder(high, low, close, int(r["atr_days"]))
        g["breakout"] = close > g["prior_entry_high"]
        vol_mult = float(s.get("volume_multiple", 1.5) or 0.0)
        if s.get("require_volume_confirm", True) and vol_mult > 0:
            g["volume_confirm"] = g["volume_mult"] >= vol_mult
        else:
            g["volume_confirm"] = True
        if s.get("require_stock_trend_filter", True):
            g["trend_filter"] = close > g["sma_trend"]
        else:
            g["trend_filter"] = True
        g["donchian_exit"] = donchian_exit(low, int(s["exit_lookback"]))
        g["breakout_strength"] = (close - g["prior_entry_high"]) / g["atr"]
        g["momentum_126"] = close / close.shift(126) - 1.0
        parts.append(g)
    feat = pd.concat(parts, ignore_index=True)
    return feat


def attach_benchmark_regime(feat: pd.DataFrame, config: Mapping) -> pd.DataFrame:
    bench = str(config["data"]["benchmark"]).upper().replace(".US", "")
    b = feat[feat["symbol"] == bench][["date", "adjusted_close", "sma_trend"]].copy()
    if b.empty:
        # try permanent id patterns
        b = feat[feat["symbol"].str.upper() == bench][["date", "adjusted_close", "sma_trend"]].copy()
    b = b.rename(
        columns={
            "adjusted_close": "benchmark_close",
            "sma_trend": "benchmark_sma",
        }
    )
    if b.empty:
        feat = feat.copy()
        feat["benchmark_close"] = float("nan")
        feat["benchmark_sma"] = float("nan")
        feat["market_regime"] = False
        return feat
    out = feat.merge(b, on="date", how="left")
    if config["signal"].get("benchmark_regime_filter", True):
        out["market_regime"] = out["benchmark_close"] > out["benchmark_sma"]
    else:
        out["market_regime"] = True
    return out


def compute_entry_signals(
    feat: pd.DataFrame,
    config: Mapping,
    earnings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Vectorized entry/exit signal columns for all rows."""
    out = feat.copy()
    blackout = earnings_blackout_mask(out, earnings if earnings is not None else pd.DataFrame(), config)
    out["earnings_blackout"] = blackout
    elig = eligible_mask(out, config)
    # do not trade the benchmark ETF as a stock unless configured; exclude pure ETF if exclude_etfs
    out["eligibility_pass"] = elig & ~out["earnings_blackout"]
    # keep benchmark for regime but mark not eligible for trading if etf excluded
    reasons = []
    reasons.append((~elig).map(lambda x: "universe" if x else ""))
    reasons.append(out["earnings_blackout"].map(lambda x: "earnings" if x else ""))
    out["eligibility_reasons"] = [
        ",".join(p for p in parts if p) for parts in zip(*[r.tolist() for r in reasons])
    ]

    out["entry_signal"] = (
        out["breakout"].fillna(False)
        & out["volume_confirm"].fillna(False)
        & out["trend_filter"].fillna(False)
        & out["market_regime"].fillna(False)
        & out["eligibility_pass"].fillna(False)
    )
    # Exit signal on owned names handled in engine; flag technical exit here
    out["exit_signal"] = out["donchian_exit"].fillna(False)
    return out
