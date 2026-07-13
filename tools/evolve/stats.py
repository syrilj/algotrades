"""Statistical robustness helpers: sign-flip permutation and deflated Sharpe."""
from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy import stats


def signflip_permutation(
    pnls: Sequence[float], n_perm: int = 2000, seed: int = 7
) -> dict:
    """Two-sided sign-flip permutation test for mean PnL.

    Returns p_value, obs_mean, n, n_perm.
    """
    arr = np.array(pnls, dtype=float)
    n = int(len(arr))
    if n == 0:
        return {"p_value": 1.0, "obs_mean": 0.0, "n": 0, "n_perm": n_perm}
    obs_mean = float(arr.mean())
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=n)
        sim_mean = float((arr * signs).mean())
        if sim_mean >= obs_mean:
            count += 1
    # two-sided p by doubling the one-sided tail
    p = 2.0 * min(count / n_perm, 1.0 - count / n_perm) if n_perm else 1.0
    return {"p_value": p, "obs_mean": obs_mean, "n": n, "n_perm": n_perm}


def _psr(sr_hat: float, n_obs: int, skew: float, kurt: float, sr0: float) -> float:
    """Probabilistic Sharpe Ratio: P(true SR > sr0)."""
    if n_obs < 4 or not np.isfinite(sr_hat):
        return 0.5
    denom = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * sr_hat * sr_hat
    if denom <= 0 or not np.isfinite(denom):
        return 0.5
    z = (sr_hat - sr0) * np.sqrt(n_obs - 1) / np.sqrt(denom)
    return float(stats.norm.cdf(z))


def deflated_sharpe(
    sr_hat: float,
    n_obs: int,
    skew: float,
    kurt: float,
    n_trials: int,
    var_trials_sr: float,
) -> dict:
    """Bailey-López de Prado deflated Sharpe ratio.

    Returns {dsr, sr0, psr} where psr is vs 0 and dsr is vs the
    expected maximum Sharpe under multiple trials.
    """
    if n_obs < 4 or n_trials < 2:
        psr = _psr(sr_hat, n_obs, skew, kurt, 0.0)
        return {"dsr": psr, "sr0": 0.0, "psr": psr}

    std = max(np.sqrt(var_trials_sr), 1e-12)
    gamma = 0.5772156649015329  # Euler-Mascheroni
    try:
        t1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
        t2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    except ValueError:
        t1 = t2 = 0.0
    sr0 = float(std * ((1.0 - gamma) * t1 + gamma * t2))
    sr0 = max(0.0, sr0)

    psr = _psr(sr_hat, n_obs, skew, kurt, 0.0)
    dsr = _psr(sr_hat, n_obs, skew, kurt, sr0)
    return {"dsr": dsr, "sr0": sr0, "psr": psr}
