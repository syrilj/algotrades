"""Small deterministic anti-overfit statistics for the v48 campaign."""
from __future__ import annotations

from itertools import combinations
from statistics import NormalDist
from typing import Iterable

import numpy as np
import pandas as pd


def deflated_sharpe_ratio(sharpe: float, observations: int, trials: int) -> float:
    """Conservative normal-return DSR approximation using the global trial count."""
    if observations < 2 or trials < 1:
        return 0.0
    expected_max = NormalDist().inv_cdf(1.0 - 1.0 / max(2, trials)) / np.sqrt(max(observations - 1, 1))
    z_score = (float(sharpe) - expected_max) * np.sqrt(max(observations - 1, 1))
    return float(NormalDist().cdf(z_score))


def moving_block_bootstrap_lower_bound(
    candidate_returns: Iterable[float], baseline_returns: Iterable[float], *, block: int = 20, samples: int = 1000, seed: int = 42
) -> float:
    candidate = np.asarray(list(candidate_returns), dtype=float)
    baseline = np.asarray(list(baseline_returns), dtype=float)
    if candidate.size != baseline.size or candidate.size < 2:
        raise ValueError("paired return series with at least two observations are required")
    diff = candidate - baseline
    rng = np.random.default_rng(seed)
    n = len(diff)
    block = min(max(1, int(block)), n)
    values = []
    for _ in range(samples):
        indices: list[int] = []
        while len(indices) < n:
            start = int(rng.integers(0, n))
            indices.extend((start + offset) % n for offset in range(block))
        values.append(float(diff[np.asarray(indices[:n])].mean()))
    return float(np.quantile(values, 0.05))


def probability_of_backtest_overfitting(score_table: pd.DataFrame) -> float:
    """CSCV-style PBO: share of train winners below median on the held-out half."""
    if score_table.shape[0] < 2 or score_table.shape[1] < 4:
        return 1.0
    columns = list(score_table.columns)
    half = len(columns) // 2
    failures = 0
    total = 0
    for train_columns in combinations(columns, half):
        test_columns = [column for column in columns if column not in train_columns]
        train_scores = score_table.loc[:, train_columns].mean(axis=1)
        winner = train_scores.idxmax()
        test_scores = score_table.loc[:, test_columns].mean(axis=1)
        percentile = float((test_scores <= test_scores.loc[winner]).mean())
        failures += int(percentile < 0.5)
        total += 1
    return float(failures / max(total, 1))


def fold_gate(rows: list[dict], *, global_trials: int) -> dict[str, object]:
    """Return the pre-registered historical gate verdict for one policy."""
    if not rows:
        return {"passed": False, "reasons": ["no_folds"]}
    frame = pd.DataFrame(rows)
    utility_positive = int((frame["ret"].astype(float) > 0.0).sum())
    trade_count = int(frame["n"].sum())
    pooled_sharpe = float(frame["sharpe"].astype(float).mean())
    reasons = []
    if utility_positive < 3:
        reasons.append("fewer_than_three_positive_folds")
    if (frame["dd"].astype(float).abs() > 0.25).any():
        reasons.append("fold_drawdown_over_25pct")
    if (frame["n"].astype(int) < 20).any() or trade_count < 100:
        reasons.append("insufficient_trade_count")
    if pooled_sharpe < 0.80:
        reasons.append("sharpe_below_0_80")
    dsr = deflated_sharpe_ratio(pooled_sharpe, trade_count, global_trials)
    if dsr < 0.95:
        reasons.append("dsr_below_0_95")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "positive_folds": utility_positive,
        "trade_count": trade_count,
        "mean_sharpe": pooled_sharpe,
        "dsr": dsr,
    }
