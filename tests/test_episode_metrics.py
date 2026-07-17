from __future__ import annotations

import pandas as pd

from tools.evolve.episode_metrics import long_episode_metrics, wilson_interval


def test_partial_resizes_are_one_episode_and_commissions_reconcile():
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01", "code": "A.US", "side": "buy", "price": 10, "qty": 10, "pnl": 0, "commission": 1},
            {"timestamp": "2026-01-02", "code": "A.US", "side": "sell", "price": 12, "qty": 4, "pnl": 8, "commission": 0.5},
            {"timestamp": "2026-01-03", "code": "A.US", "side": "buy", "price": 11, "qty": 2, "pnl": 0, "commission": 0.2},
            {"timestamp": "2026-01-04", "code": "A.US", "side": "sell", "price": 12, "qty": 8, "pnl": 14, "commission": 0.8},
            {"timestamp": "2026-01-05", "code": "A.US", "side": "buy", "price": 12, "qty": 2, "pnl": 0, "commission": 0.2},
            {"timestamp": "2026-01-06", "code": "A.US", "side": "sell", "price": 10, "qty": 2, "pnl": -4, "commission": 0.3},
        ]
    )
    # Episode P&L: 19.5 then -4.5 = 15.0.
    result = long_episode_metrics(trades, initial_cash=100, final_value=115)

    assert result["closed_episodes"] == 2
    assert result["wins"] == 1
    assert result["win_rate"] == 0.5
    assert result["closed_episode_net_pnl"] == 15.0
    assert result["reconciles_final_value"] is True


def test_wilson_interval_is_bounded_and_contains_observed_rate():
    low, high = wilson_interval(10, 11)
    assert low is not None and high is not None
    assert 0.0 <= low < 10 / 11 < high <= 1.0
