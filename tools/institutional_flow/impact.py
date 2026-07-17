"""Almgren-Chriss impact wrapper and helpers.

This is a thin wrapper around the existing `tools/impact_model.py` so the
research pipeline imports all execution-cost logic from one place.  The
functions are bar-frequency agnostic: the caller provides ADV and per-bar
volatility, or a DataFrame from which those values are estimated.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

# Make tools/impact_model.py discoverable regardless of how this package is
# imported (root, tools/, or as a package).
TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
import impact_model


def impact_per_share(
    shares: float,
    price: float,
    adv: float,
    volatility: float,
    *,
    eta: float = 0.1,
    gamma: float = 0.0,
    beta: float = 0.5,
) -> float:
    """Total Almgren-Chriss temporary + permanent impact per share.

    Temporary impact follows a power-law of the participation rate:

        temp = eta * (participation_rate ** beta) * volatility * price

    Permanent impact is linear in participation rate:

        perm = gamma * participation_rate * price

    Args:
        shares: shares traded in this slice.
        price: reference price.
        adv: average daily volume in shares.
        volatility: per-bar return volatility (std of log returns on the bar
            interval the engine is using, e.g. 1m or 1H).
        eta: temporary impact coefficient.
        gamma: permanent impact coefficient.
        beta: participation-rate exponent. 0.5 = square-root law.

    Returns:
        Estimated impact in dollars per share (positive).
    """
    return impact_model.impact_per_share(
        shares=shares,
        price=price,
        adv=adv,
        volatility=volatility,
        eta=eta,
        gamma=gamma,
        beta=beta,
    )


def impact_for_notional(
    notional: float,
    price: float,
    adv: float,
    volatility: float,
    *,
    eta: float = 0.1,
    gamma: float = 0.0,
    beta: float = 0.5,
) -> float:
    """Impact cost in dollars for a given notional trade size."""
    if price <= 0 or notional <= 0:
        return 0.0
    shares = notional / price
    return impact_per_share(shares, price, adv, volatility, eta=eta, gamma=gamma, beta=beta) * shares


def optimal_trajectory(
    total_shares: float,
    n_bars: int,
    *,
    eta: float = 0.1,
    gamma: float = 0.0,
    sigma: float = 0.02,
    lambda_: float = 1.0,
) -> list[float]:
    """Discrete Almgren-Chriss optimal remaining-position trajectory.

    Returns the remaining shares at the start of each bar, ending at 0.
    """
    return impact_model.optimal_trajectory(
        total_shares=total_shares,
        n_bars=n_bars,
        eta=eta,
        gamma=gamma,
        sigma=sigma,
        lambda_=lambda_,
    )


def estimate_adv(df: pd.DataFrame, bars_per_day: float, lookback_days: int = 20) -> float:
    """Estimate average daily volume from a bar DataFrame.

    Args:
        df: DataFrame with a 'volume' column.
        bars_per_day: typical number of bars per trading day (e.g. 390 for 1m).
        lookback_days: number of trading days to average.
    """
    return impact_model.estimate_adv(df, bars_per_day, lookback_days)


def estimate_volatility(df: pd.DataFrame, bars_per_day: float, lookback_days: int = 20) -> float:
    """Estimate per-bar return volatility from a bar DataFrame."""
    return impact_model.estimate_volatility(df, bars_per_day, lookback_days)


def cost_for_trade(
    df: pd.DataFrame,
    price: float,
    notional: float,
    interval: str = "1m",
    *,
    eta: float = 0.1,
    gamma: float = 0.0,
    beta: float = 0.5,
    adv_days: int = 20,
    vol_days: int = 20,
) -> dict[str, float]:
    """Estimate AC impact cost for a single trade slice from a bar history.

    This is a convenience for the research pipeline; it does not account for
    order splitting across bars.  Use `optimal_trajectory` for full slices.

    Returns:
        {
            "shares": float,
            "participation_rate": float,
            "impact_per_share": float,
            "total_cost": float,
            "adv": float,
            "volatility": float,
        }
    """
    bars_per_day = _bars_per_day(interval)
    adv = estimate_adv(df, bars_per_day, adv_days)
    vol = estimate_volatility(df, bars_per_day, vol_days)
    if price <= 0 or notional <= 0 or adv <= 0 or vol <= 0:
        return {
            "shares": 0.0,
            "participation_rate": 0.0,
            "impact_per_share": 0.0,
            "total_cost": 0.0,
            "adv": adv,
            "volatility": vol,
        }
    shares = notional / price
    per_share = impact_per_share(shares, price, adv, vol, eta=eta, gamma=gamma, beta=beta)
    return {
        "shares": shares,
        "participation_rate": shares / adv,
        "impact_per_share": per_share,
        "total_cost": per_share * shares,
        "adv": adv,
        "volatility": vol,
    }


def _bars_per_day(interval: str) -> float:
    """Typical number of bars per US equity trading day for a given interval."""
    interval = str(interval).lower()
    mapping = {
        "1m": 390.0,
        "5m": 78.0,
        "15m": 26.0,
        "30m": 13.0,
        "1h": 7.0,
        "4h": 1.0,
        "1d": 1.0,
    }
    return mapping.get(interval, 1.0)


def _cost_curve_for_trajectory(
    df: pd.DataFrame,
    price: float,
    total_notional: float,
    n_bars: int,
    interval: str = "1m",
    *,
    eta: float = 0.1,
    gamma: float = 0.0,
    beta: float = 0.5,
    lambda_: float = 1.0,
) -> dict[str, float]:
    """Estimate cost for an order split over an optimal AC trajectory.

    Returns:
        {
            "total_cost": float,
            "avg_impact_per_share": float,
            "adv": float,
            "volatility": float,
            "trajectory": list[float],
        }
    """
    bars_per_day = _bars_per_day(interval)
    adv = estimate_adv(df, bars_per_day, lookback_days=20)
    vol = estimate_volatility(df, bars_per_day, lookback_days=20)
    if price <= 0 or total_notional <= 0 or adv <= 0 or vol <= 0:
        return {
            "total_cost": 0.0,
            "avg_impact_per_share": 0.0,
            "adv": adv,
            "volatility": vol,
            "trajectory": [0.0],
        }
    total_shares = total_notional / price
    traj = optimal_trajectory(total_shares, n_bars, eta=eta, gamma=gamma, sigma=vol, lambda_=lambda_)
    # differences between consecutive remaining positions give the trade size per bar
    shares_per_bar = [traj[i] - traj[i + 1] for i in range(len(traj) - 1)]
    total_cost = sum(
        impact_per_share(sh, price, adv, vol, eta=eta, gamma=gamma, beta=beta) * sh
        for sh in shares_per_bar
    )
    return {
        "total_cost": total_cost,
        "avg_impact_per_share": total_cost / total_shares if total_shares > 0 else 0.0,
        "adv": adv,
        "volatility": vol,
        "trajectory": traj,
    }
