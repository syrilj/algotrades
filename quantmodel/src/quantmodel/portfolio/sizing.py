"""Risk-based position sizing."""

from __future__ import annotations

import math
from typing import Mapping, Optional


def risk_budget(equity: float, risk_per_trade: float) -> float:
    return equity * risk_per_trade


def stop_distance(atr: float, atr_multiple: float) -> float:
    return atr_multiple * atr


def risk_based_shares(equity: float, risk_per_trade: float, atr: float, atr_multiple: float) -> int:
    dist = stop_distance(atr, atr_multiple)
    if dist <= 0 or not math.isfinite(dist):
        return 0
    budget = risk_budget(equity, risk_per_trade)
    return int(math.floor(budget / dist))


def final_shares(
    *,
    equity: float,
    price: float,
    atr: float,
    config: Mapping,
    median_dv_20: float,
    available_heat: float,
    sector_exposure: float,
    allow_fractional: bool = False,
) -> int:
    """Apply all caps; return whole shares (or 0 if rejected)."""
    risk = config["risk"]
    uni = config["universe"]
    exe = config["execution"]
    atr_mult = float(risk["atr_multiple"])
    shares = risk_based_shares(equity, float(risk["risk_per_trade"]), atr, atr_mult)
    if shares <= 0 or price <= 0:
        return 0

    # max weight
    max_notional = float(risk.get("max_position_weight", 0.10)) * equity
    weight_shares = int(math.floor(max_notional / price))

    # ADV participation
    adv_frac = float(uni.get("max_position_fraction_of_adv", 0.01))
    if median_dv_20 > 0:
        liq_shares = int(math.floor((adv_frac * median_dv_20) / price))
    else:
        liq_shares = 0

    # heat: heat = shares * stop_distance / equity
    dist = stop_distance(atr, atr_mult)
    if dist > 0 and available_heat > 0:
        heat_shares = int(math.floor((available_heat * equity) / dist))
    else:
        heat_shares = 0

    # sector
    max_sector = float(risk.get("max_sector_weight", 0.30)) * equity
    sector_room = max(0.0, max_sector - sector_exposure)
    sector_shares = int(math.floor(sector_room / price)) if price > 0 else 0

    # volume participation limit on order
    vol_part = float(exe.get("volume_participation_limit", 0.01))
    # approximate ADV shares from median DV
    if median_dv_20 > 0 and price > 0:
        adv_shares = median_dv_20 / price
        vol_shares = int(math.floor(vol_part * adv_shares))
    else:
        vol_shares = 0

    final = min(shares, weight_shares, liq_shares, heat_shares, sector_shares, vol_shares)
    if allow_fractional:
        return max(final, 0)
    if final < 1:
        return 0
    return int(final)


def proposed_heat(shares: int, atr: float, atr_multiple: float, equity: float) -> float:
    if equity <= 0 or shares <= 0:
        return 0.0
    return (shares * stop_distance(atr, atr_multiple)) / equity
