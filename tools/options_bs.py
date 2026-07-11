"""Black–Scholes helpers for live picker + synthetic options research."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm


def bs_price(S: float, K: float, T: float, r: float, sigma: float, call: bool = True) -> float:
    if S <= 0 or K <= 0 or sigma <= 0:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    if T <= 1e-8:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    if call:
        return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    return float(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def bs_delta(S: float, K: float, T: float, r: float, sigma: float, call: bool = True) -> float:
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 1e-8:
        if call:
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    return float(norm.cdf(d1) if call else norm.cdf(d1) - 1.0)


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float, call: bool = True) -> dict:
    """Return price, delta, approx theta (per day), vega (per 1 vol point)."""
    px = bs_price(S, K, T, r, sigma, call)
    delta = bs_delta(S, K, T, r, sigma, call)
    if T <= 1e-8 or sigma <= 0 or S <= 0:
        return {"price": px, "delta": delta, "theta_day": 0.0, "vega_1pp": 0.0}
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    pdf = float(norm.pdf(d1))
    vega = S * pdf * sqrtT / 100.0  # per 1 percentage point
    if call:
        theta = (-S * pdf * sigma / (2 * sqrtT) - r * K * math.exp(-r * T) * float(norm.cdf(d2))) / 365.0
    else:
        theta = (-S * pdf * sigma / (2 * sqrtT) + r * K * math.exp(-r * T) * float(norm.cdf(-d2))) / 365.0
    return {"price": px, "delta": delta, "theta_day": float(theta), "vega_1pp": float(vega)}


def strike_for_delta(S: float, T: float, r: float, sigma: float, target_delta: float, call: bool = True) -> float:
    """Binary search strike for target |delta| on calls (0<delta<1)."""
    target = abs(float(target_delta))
    lo, hi = S * 0.5, S * 1.5
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        d = abs(bs_delta(S, mid, T, r, sigma, call))
        if call:
            # higher strike → lower delta
            if d > target:
                lo = mid
            else:
                hi = mid
        else:
            if d > target:
                hi = mid
            else:
                lo = mid
    return 0.5 * (lo + hi)


def round_strike(S: float, raw_k: float) -> float:
    """Heuristic strike increment by spot level."""
    if S < 25:
        step = 0.5
    elif S < 100:
        step = 1.0
    elif S < 500:
        step = 2.5 if S < 200 else 5.0
    else:
        step = 10.0
    return round(raw_k / step) * step


@dataclass
class ContractPick:
    symbol: str
    structure: str
    expiry: str
    long_strike: float
    short_strike: float | None
    long_delta: float
    short_delta: float | None
    debit: float  # per share
    max_loss: float  # dollars for 1 contract
    iv: float
    spot: float
    dte: int
    note: str
