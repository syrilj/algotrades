"""Stationary bootstrap confidence intervals."""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from quantmodel.validation.metrics import sharpe_ratio
import pandas as pd


def stationary_bootstrap_indices(
    n: int,
    samples: int,
    mean_block: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return (samples, n) index array via Politis-Romano stationary bootstrap."""
    if n <= 0:
        return np.zeros((samples, 0), dtype=int)
    p = 1.0 / max(mean_block, 1.0)
    out = np.empty((samples, n), dtype=int)
    for s in range(samples):
        idx = np.empty(n, dtype=int)
        idx[0] = rng.integers(0, n)
        for t in range(1, n):
            if rng.random() < p:
                idx[t] = rng.integers(0, n)
            else:
                idx[t] = (idx[t - 1] + 1) % n
        out[s] = idx
    return out


def bootstrap_metrics(
    returns: Sequence[float],
    *,
    samples: int = 1000,
    seed: int = 42,
    mean_block: float | None = None,
) -> dict[str, dict[str, float]]:
    r = np.asarray(list(returns), dtype=float)
    n = len(r)
    if n < 5:
        return {}
    mb = mean_block if mean_block is not None else max(n ** (1 / 3), 1.0)
    rng = np.random.default_rng(seed)
    idxs = stationary_bootstrap_indices(n, samples, mb, rng)

    sharpes = []
    cagrs = []
    mdds = []
    for i in range(samples):
        boot = r[idxs[i]]
        s = pd.Series(boot)
        sharpes.append(sharpe_ratio(s))
        # approx CAGR from mean return
        eq = np.cumprod(1 + boot)
        days = n
        cagrs.append(float(eq[-1] ** (252 / days) - 1) if eq[-1] > 0 else -1.0)
        peak = np.maximum.accumulate(eq)
        dd = eq / peak - 1
        mdds.append(float(dd.min()))

    def ci(arr: list[float]) -> dict[str, float]:
        a = np.asarray(arr, dtype=float)
        return {
            "mean": float(a.mean()),
            "p05": float(np.percentile(a, 5)),
            "p50": float(np.percentile(a, 50)),
            "p95": float(np.percentile(a, 95)),
        }

    return {
        "sharpe": ci(sharpes),
        "cagr": ci(cagrs),
        "max_drawdown": ci(mdds),
    }
