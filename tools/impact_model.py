"""Almgren-Chriss market impact model.

A simplified, production-usable approximation that plugs into the backtester
or live execution engine. It estimates the execution shortfall per share
(temporary + permanent impact) for a single slice of a larger order.

References:
    Almgren & Chriss (2000). Optimal execution of portfolio transactions.
    Kissell & Glantz (2003). Optimal Trading Strategies.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


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
    """Total market impact per share in price units.

    Temporary impact is modelled as a square-root (or power-law) function of
    the participation rate, scaled by volatility and price:

        temp_impact = eta * (participation_rate ** beta) * volatility * price

    Permanent impact is linear in the participation rate:

        perm_impact = gamma * participation_rate * price

    Args:
        shares: number of shares traded in this slice.
        price: current reference price (usually the open of the execution bar).
        adv: average daily volume in shares.
        volatility: per-bar return volatility (std of log returns on the bar
            interval the engine is using, e.g. 1H or 1D).
        eta: temporary impact coefficient.
        gamma: permanent impact coefficient.
        beta: participation-rate exponent. 0.5 = square-root law, 1.0 = linear.

    Returns:
        Estimated impact in dollars per share (positive).
    """
    if shares <= 0 or price <= 0 or adv <= 0 or volatility <= 0:
        return 0.0
    participation_rate = min(shares / adv, 1.0)  # cap at 100% ADV
    temporary = eta * (participation_rate ** beta) * volatility * price
    permanent = gamma * participation_rate * price
    return temporary + permanent


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

    Minimises E[IS] + lambda * Var[IS] over a fixed horizon. The closed-form
    continuous solution is x(t) = X * sinh(kappa * (T - t)) / sinh(kappa * T)
    with kappa = sqrt(lambda * sigma^2 / eta). This discretisation evaluates
    that curve at bar boundaries.

    Args:
        total_shares: total shares to liquidate (positive for selling).
        n_bars: number of bars over which to trade.
        eta: temporary impact coefficient.
        gamma: permanent impact coefficient (ignored in trajectory, used in
            cost accounting via impact_per_share).
        sigma: per-bar return volatility.
        lambda_: urgency / risk-aversion parameter.

    Returns:
        List of remaining shares at the start of each bar, ending at 0.
    """
    if n_bars <= 0 or total_shares <= 0:
        return [0.0]

    if eta <= 0 or lambda_ <= 0 or sigma <= 0:
        # Degenerate high-urgency or zero-impact case: linear liquidation.
        return [total_shares * (1 - i / n_bars) for i in range(n_bars + 1)]

    kappa = math.sqrt(lambda_ * sigma * sigma / eta)
    kappa_t = kappa * n_bars
    if kappa_t < 1e-9:
        return [total_shares * (1 - i / n_bars) for i in range(n_bars + 1)]

    trajectory: list[float] = []
    for i in range(n_bars + 1):
        t = n_bars - i
        numerator = math.sinh(kappa * t)
        denominator = math.sinh(kappa_t)
        trajectory.append(total_shares * numerator / denominator)

    # Force exact final value to avoid tiny residual.
    trajectory[-1] = 0.0
    return trajectory


def estimate_adv(df, bars_per_day: float, lookback_days: int = 20) -> float:
    """Estimate average daily volume from a bar DataFrame.

    Args:
        df: DataFrame with a 'volume' column.
        bars_per_day: typical number of bars per trading day for this interval.
        lookback_days: number of trading days to average.

    Returns:
        Estimated ADV in shares.
    """
    window = max(1, int(lookback_days * bars_per_day))
    if len(df) == 0 or "volume" not in df.columns:
        return 0.0
    avg_bar_volume = df["volume"].tail(window).mean()
    return float(avg_bar_volume * bars_per_day) if pd.notna(avg_bar_volume) else 0.0


def estimate_volatility(df, bars_per_day: float, lookback_days: int = 20) -> float:
    """Estimate per-bar return volatility from a bar DataFrame.

    Args:
        df: DataFrame with a 'close' column.
        bars_per_day: typical number of bars per trading day for this interval.
        lookback_days: number of trading days to average.

    Returns:
        Estimated per-bar standard deviation of log returns.
    """
    window = max(2, int(lookback_days * bars_per_day))
    if len(df) < 2 or "close" not in df.columns:
        return 0.0
    closes = df["close"].tail(window)
    log_returns = np.log(closes).diff().dropna()
    return float(log_returns.std()) if len(log_returns) > 1 else 0.0


import pandas as pd  # noqa: E402 - imported at the end for estimate_ helpers
