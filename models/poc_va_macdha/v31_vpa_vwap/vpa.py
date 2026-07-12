"""Coulling Volume Price Analysis (VPA) — effort vs result.

Source: Anna Coulling, *A Complete Guide to Volume Price Analysis*
(see books/WHAT_THE_BOOKS_SAY.md and books/Anna Coulling ...pdf).

Core law:
  Volume = effort, price spread = result. They should agree.
  Anomalies reveal smart-money absorption / distribution / traps.

Patterns used for short-term call/put flips:
  CALL bias:
    - stopping_volume (after fall: high vol + narrow spread) → watch
    - no_supply pullback (dip on low vol) after stop → buy test
    - stopping_reclaim / spring-like reclaim with volume
    - confirm_up (price↑ + volume↑) — harmony
  PUT bias:
    - topping_volume (after rally: high vol + narrow) → watch
    - no_demand rally (up on low vol) → short / put
    - upthrust_fail (break high fails) with telling volume
    - confirm_down / dump (price↓ + volume↑)
  BLOCK:
    - no_demand for calls
    - buying_climax chase
    - effort_anomaly (wide move on thin vol)
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(int(n), min_periods=max(2, n // 2)).mean()


def vpa_frame(
    df: pd.DataFrame,
    look: int = 5,
    vol_sma: int = 20,
    stop_look: int = 8,
) -> pd.DataFrame:
    """Return Coulling-style VPA flags + flip signals per bar.

    Expects daily OHLCV with columns open, high, low, close, volume.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    open_ = df["open"].astype(float)
    vol = df["volume"].astype(float)

    price_up = close > close.shift(look)
    price_dn = close < close.shift(look)
    vsma = _sma(vol, vol_sma)
    vol_up = vol > vsma
    vol_rising = vol > vol.shift(look)
    vol_falling = vol < vol.shift(look)

    spread = (high - low).replace(0, np.nan)
    spread_sma = _sma(spread, vol_sma)
    narrow = spread < (spread_sma * 0.75)
    wide = spread > (spread_sma * 1.25)
    vol_high = vol > (vsma * 1.5)
    vol_low = vol < (vsma * 0.70)
    vol_climax = vol > (vsma * 2.0)

    green = close > open_
    red = close < open_
    body = (close - open_) / open_.replace(0, np.nan)
    ret1 = close.pct_change(1)

    # --- Coulling primary patterns ---
    prior_dn = close.shift(1) < close.shift(look + 1)
    prior_up = close.shift(1) > close.shift(look + 1)
    # Stopping volume: fall then high vol + narrow (brakes / absorption)
    stopping_volume = (prior_dn & vol_high & narrow).fillna(False)
    # Topping volume: rally then high vol + narrow (distribution into strength)
    topping_volume = (prior_up & vol_high & narrow).fillna(False)
    # No demand: up bar / push on low volume (weak rally — trap)
    no_demand = ((price_up | green) & vol_low).fillna(False)
    # No supply: down / dip on low volume (test / weak selling)
    no_supply = ((price_dn | red) & vol_low).fillna(False)
    # Effort vs result
    effort_anomaly = (wide & vol_low) | (wide & price_up & ~vol_up & vol_falling)
    effort_ok = (~effort_anomaly).fillna(True)
    # Climax
    buying_climax = (price_up & vol_climax & wide).fillna(False)
    selling_climax = (price_dn & vol_climax & wide).fillna(False)
    # Confirm harmony
    confirm_up = (price_up & (vol_up | vol_rising)).fillna(False)
    confirm_down = (price_dn & (vol_up | vol_rising)).fillna(False)
    dump = (price_dn & vol_rising & vol_up).fillna(False)
    healthy_pull = (price_dn & vol_falling).fillna(False)

    # Stopping then reclaim (test of supply after absorption)
    stop_recent = stopping_volume.rolling(stop_look, min_periods=1).max().astype(bool)
    stopping_reclaim = (stop_recent & green & (ret1 > 0.005) & ~dump).fillna(False)
    # Topping then fail (first red with volume after top)
    top_recent = topping_volume.rolling(stop_look, min_periods=1).max().astype(bool)
    topping_fail = (top_recent & red & (ret1 < -0.005)).fillna(False)

    # Upthrust: break prior high, close back weak (trap)
    prior_high = high.shift(1).rolling(look, min_periods=2).max()
    upthrust = (high > prior_high) & (close < open_) & (close < prior_high)
    upthrust = upthrust.fillna(False)
    # Spring: break prior low, reclaim (accumulation test)
    prior_low = low.shift(1).rolling(look, min_periods=2).min()
    spring = (low < prior_low) & (close > open_) & (close > prior_low)
    spring = spring.fillna(False)

    # --- Flip entries (short-term call / put) ---
    # CALL (standard): after smart-money buy signals, not no-demand
    call_std = (
        (
            stopping_reclaim
            | (stop_recent & no_supply & green)
            | (spring & (vol_up | vol_high))
            | (confirm_up & green & (ret1 > 0.012) & effort_ok & ~no_demand)
        )
        & ~no_demand
        & ~buying_climax
        & ~topping_volume
    ).fillna(False)

    # PUT (standard)
    put_std = (
        (
            topping_fail
            | (top_recent & no_demand & red)
            | (upthrust & (vol_up | vol_high | vol_low))
            | (dump & red & (ret1 < -0.012) & effort_ok)
            | (no_demand & red & prior_up)
        )
        & ~no_supply
        & ~selling_climax
    ).fillna(False)

    vol_ratio_series = (vol / vsma.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    # SNIPER (high-selectivity — aim for high WR, fewer trades)
    # Only textbook Coulling setups with multi-confirm.
    call_sniper = (
        (
            (stopping_reclaim & effort_ok & (vol_ratio_series > 0.8))
            | (stop_recent & no_supply & green & effort_ok & (ret1 > 0.008))
            | (spring & vol_high & green & effort_ok)
        )
        & ~no_demand
        & ~buying_climax
        & ~topping_volume
        & ~effort_anomaly.fillna(False)
    ).fillna(False)

    put_sniper = (
        (
            (topping_fail & effort_ok)
            | (top_recent & no_demand & red & effort_ok)
            | (upthrust & vol_high & red)
        )
        & ~no_supply
        & ~selling_climax
        & ~effort_anomaly.fillna(False)
    ).fillna(False)

    # default export = standard; engine can switch via mode
    call = call_std
    put = put_std
    both = call & put
    call = call & ~both
    put = put & ~both
    both_s = call_sniper & put_sniper
    call_sniper = (call_sniper & ~both_s).fillna(False)
    put_sniper = (put_sniper & ~both_s).fillna(False)

    # Strength score for ranking multi-name days
    strength = ret1.abs().fillna(0.0)
    strength = strength + stopping_volume.astype(float) * 0.02 + topping_volume.astype(float) * 0.02
    strength = strength + vol_high.astype(float) * 0.01
    strength = strength + stopping_reclaim.astype(float) * 0.03 + topping_fail.astype(float) * 0.03

    iv = close.pct_change().rolling(20, min_periods=5).std(ddof=0) * np.sqrt(252)
    iv = iv.fillna(0.55).clip(0.20, 1.50)

    return pd.DataFrame(
        {
            "close": close,
            "ret1": ret1,
            "green": green.fillna(False),
            "red": red.fillna(False),
            "confirm_up": confirm_up,
            "confirm_down": confirm_down,
            "dump": dump,
            "healthy_pull": healthy_pull,
            "stopping_volume": stopping_volume,
            "topping_volume": topping_volume,
            "no_demand": no_demand,
            "no_supply": no_supply,
            "effort_ok": effort_ok,
            "effort_anomaly": effort_anomaly.fillna(False),
            "buying_climax": buying_climax,
            "selling_climax": selling_climax,
            "stopping_reclaim": stopping_reclaim,
            "topping_fail": topping_fail,
            "upthrust": upthrust,
            "spring": spring,
            "call": call,
            "put": put,
            "call_sniper": call_sniper,
            "put_sniper": put_sniper,
            "strength": strength,
            "iv": iv,
            "vol_ratio": vol_ratio_series,
        },
        index=df.index,
    )


def tag_bar(row: Dict[str, Any]) -> str:
    """Human VPA tag for desk / logging."""
    tags = []
    for k in (
        "stopping_volume",
        "topping_volume",
        "no_demand",
        "no_supply",
        "stopping_reclaim",
        "topping_fail",
        "upthrust",
        "spring",
        "buying_climax",
        "selling_climax",
        "effort_anomaly",
        "confirm_up",
        "dump",
    ):
        if row.get(k):
            tags.append(k)
    if row.get("call"):
        tags.append("CALL")
    if row.get("put"):
        tags.append("PUT")
    return "+".join(tags) if tags else "quiet"
