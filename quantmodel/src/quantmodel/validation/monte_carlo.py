"""Monte Carlo drawdown analysis on daily returns."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def monte_carlo_drawdowns(
    returns: Sequence[float],
    *,
    samples: int = 2000,
    seed: int = 42,
    kill_switch_dd: float = -0.12,
) -> dict[str, float]:
    r = np.asarray(list(returns), dtype=float)
    n = len(r)
    if n < 5:
        return {}
    rng = np.random.default_rng(seed)
    max_dds = []
    hit_kill = 0
    for _ in range(samples):
        boot = rng.choice(r, size=n, replace=True)
        eq = np.cumprod(1 + boot)
        peak = np.maximum.accumulate(eq)
        dd = eq / peak - 1.0
        mdd = float(dd.min())
        max_dds.append(mdd)
        if mdd <= kill_switch_dd:
            hit_kill += 1
    a = np.asarray(max_dds)
    return {
        "median_max_drawdown": float(np.median(a)),
        "p75_max_drawdown": float(np.percentile(a, 75)),
        "p90_max_drawdown": float(np.percentile(a, 90)),
        "p95_max_drawdown": float(np.percentile(a, 95)),
        "p99_max_drawdown": float(np.percentile(a, 99)),
        "prob_hit_kill_switch": float(hit_kill / samples),
        "prob_loss_gt_20pct": float(np.mean(a <= -0.20)),
    }
