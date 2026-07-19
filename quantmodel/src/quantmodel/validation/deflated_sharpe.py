"""Deflated Sharpe Ratio (Bailey & Lopez de Prado)."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

EULER_MASCHERONI = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    # Acklam approximation
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    p_low = 0.02425
    p_high = 1 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        )
    q = math.sqrt(-2 * math.log(1 - p))
    return -(
        (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
        / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    )


def expected_max_sharpe(n_trials: int) -> float:
    """Expected maximum Sharpe under null for n independent trials."""
    n = max(int(n_trials), 1)
    if n == 1:
        return 0.0
    return (1 - EULER_MASCHERONI) * _norm_ppf(1 - 1 / n) + EULER_MASCHERONI * _norm_ppf(
        1 - 1 / (n * math.e)
    )


def deflated_sharpe_probability(
    observed_sr: float,
    n_obs: int,
    n_trials: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """
    Probability that true SR > 0 after deflating for selection bias.

    kurtosis: non-excess (normal=3). If excess kurtosis is provided, add 3.
    """
    if n_obs < 3 or n_trials < 1:
        return 0.0
    # If kurtosis looks like excess (< 1.5 typical for excess near 0), treat as excess
    k = kurtosis
    if k < 1.5:
        k = k + 3.0
    sr_std = math.sqrt(
        (1 - skew * observed_sr + (k - 1) / 4.0 * observed_sr**2) / (n_obs - 1)
    )
    if sr_std <= 0:
        return 0.0
    exp_max = expected_max_sharpe(n_trials)
    return float(_norm_cdf((observed_sr - exp_max) / sr_std))


def sharpe_from_returns(returns: Sequence[float], periods_per_year: int = 252) -> float:
    r = np.asarray(list(returns), dtype=float)
    if r.size < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * math.sqrt(periods_per_year))
