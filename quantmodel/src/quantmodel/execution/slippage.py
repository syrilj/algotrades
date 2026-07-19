"""Equity slippage models."""

from __future__ import annotations

import math
from typing import Mapping


def base_slippage_bps(config: Mapping) -> float:
    return float(config["execution"]["slippage_bps"])


def capacity_slippage_bps(
    *,
    config: Mapping,
    order_notional: float,
    median_dv_20: float,
    volatility: float = 0.0,
) -> float:
    """Optional capacity-aware model: b0 + b1*sqrt(notional/ADV) + b2*vol."""
    cap = config["execution"].get("capacity_slippage") or {}
    if not cap.get("enabled", False):
        return base_slippage_bps(config)
    b0 = float(cap.get("b0", 5.0))
    b1 = float(cap.get("b1", 10.0))
    b2 = float(cap.get("b2", 0.0))
    if median_dv_20 <= 0:
        return b0 + 50.0  # penalize unknown liquidity
    ratio = max(order_notional, 0.0) / median_dv_20
    return b0 + b1 * math.sqrt(ratio) + b2 * volatility


def apply_buy_slippage(price: float, slippage_bps: float) -> float:
    return price * (1.0 + slippage_bps / 10_000.0)


def apply_sell_slippage(price: float, slippage_bps: float) -> float:
    return price * (1.0 - slippage_bps / 10_000.0)
