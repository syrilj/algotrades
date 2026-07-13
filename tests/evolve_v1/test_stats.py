"""Tests for tools/evolve/stats.py."""
from __future__ import annotations

import numpy as np

from tools.evolve import stats


def test_signflip_permutation_positive():
    pnls = np.random.default_rng(1).normal(0.5, 1.0, 80)
    res = stats.signflip_permutation(pnls, n_perm=500, seed=1)
    assert res["n"] == 80
    assert 0.0 <= res["p_value"] <= 1.0


def test_deflated_sharpe_positive():
    returns = np.random.default_rng(2).normal(0.001, 0.01, 200)
    sr = float(returns.mean() / returns.std() * np.sqrt(252))
    skew = 0.0
    kurt = 3.0
    res = stats.deflated_sharpe(sr, 200, skew, kurt, 1, 0.0)
    assert "dsr" in res
    assert "psr" in res
    assert res["dsr"] == res["psr"]


def test_deflated_sharpe_multiple_trials():
    res = stats.deflated_sharpe(1.0, 250, 0.0, 3.0, 20, 0.04)
    assert 0.0 <= res["dsr"] <= 1.0
    assert res["sr0"] >= 0
