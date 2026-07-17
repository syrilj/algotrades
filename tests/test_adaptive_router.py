from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.adaptive_router import (  # noqa: E402
    RouterConfig,
    build_causal_context,
    counterfactual_net_utility,
    fixed_share_update,
    route_experts,
)


def _frame(n: int = 240, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-02 09:30", periods=n, freq="h")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.005, n)))
    open_ = np.r_[close[0], close[:-1]]
    spread = close * 0.003
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.integers(100, 1000, n),
        },
        index=index,
    )


def test_fixed_share_rewards_the_better_expert_and_keeps_recovery_mass():
    weights = np.array([0.45, 0.45, 0.10])
    for _ in range(30):
        weights = fixed_share_update(
            weights,
            np.array([0.02, -0.02, 0.0]),
            eta=0.2,
            share=0.02,
            utility_bound=0.03,
        )
    assert weights[0] > weights[1]
    assert np.all(weights > 0.0)
    assert np.isclose(weights.sum(), 1.0)


def test_counterfactual_utility_charges_entry_resize_and_exit_turnover():
    entry = counterfactual_net_utility(
        np.array([0.4, 0.0]),
        np.array([0.0, 0.0]),
        0.01,
        one_way_cost=0.001,
    )
    resize = counterfactual_net_utility(
        np.array([0.2, 0.0]),
        np.array([0.4, 0.0]),
        0.01,
        one_way_cost=0.001,
    )
    exit_ = counterfactual_net_utility(
        np.array([0.0, 0.0]),
        np.array([0.2, 0.0]),
        0.01,
        one_way_cost=0.001,
    )

    assert np.isclose(entry[0], 0.0036)
    assert np.isclose(resize[0], 0.0018)
    assert np.isclose(exit_[0], -0.0002)


def test_daily_context_uses_previous_session_close_and_is_prefix_invariant():
    frame = _frame(240)
    daily_index = pd.date_range("2025-12-01", periods=80, freq="B")
    vix = pd.DataFrame({"close": np.linspace(14.0, 30.0, len(daily_index))}, index=daily_index)
    hyg = pd.DataFrame({"close": np.linspace(75.0, 78.0, len(daily_index))}, index=daily_index)
    lqd = pd.DataFrame({"close": np.linspace(105.0, 104.0, len(daily_index))}, index=daily_index)
    full = build_causal_context(frame, spy=frame, vix_daily=vix, hyg_daily=hyg, lqd_daily=lqd)
    prefix_n = 180
    prefix = build_causal_context(
        frame.iloc[:prefix_n], spy=frame.iloc[:prefix_n], vix_daily=vix, hyg_daily=hyg, lqd_daily=lqd
    )
    pd.testing.assert_frame_equal(prefix, full.iloc[:prefix_n])

    # A same-date daily value is not available to that date's intraday bars.
    one_day = pd.DataFrame(
        {"close": [10.0, 99.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )
    short = build_causal_context(frame.iloc[:2], spy=frame.iloc[:2], vix_daily=one_day)
    assert (short["vix_level_prior_close"] == 10.0).all()


def test_daily_context_changes_are_measured_on_sessions_not_hourly_rows():
    daily_index = pd.date_range("2025-12-01", periods=30, freq="B")
    daily_values = pd.Series(np.arange(10.0, 40.0), index=daily_index)
    vix = pd.DataFrame({"close": daily_values})
    target_index = pd.date_range(
        f"{daily_index[-3].date()} 09:30", periods=12, freq="h"
    )
    frame = _frame(len(target_index))
    frame.index = target_index

    context = build_causal_context(frame, spy=frame, vix_daily=vix)
    known = daily_values.shift(1)
    expected = float(known.pct_change(5, fill_method=None).loc[daily_index[-3]])

    assert np.allclose(context["vix_change_5d"], expected)
    assert context["vix_change_5d"].nunique() == 1


def test_stale_external_context_loses_quality_and_cannot_open_new_risk():
    frame = _frame(80)
    stale_end = frame.index.min() - pd.Timedelta(days=10)
    stale_index = pd.date_range(end=stale_end, periods=30, freq="B")
    stale = pd.DataFrame({"close": np.linspace(10.0, 20.0, len(stale_index))}, index=stale_index)

    context = build_causal_context(
        frame,
        spy=stale,
        vix_daily=stale,
        hyg_daily=stale,
        lqd_daily=stale,
    )
    signal = pd.Series(0.4, index=frame.index)
    routed, diag = route_experts(
        frame["open"],
        {"primary": signal},
        context,
        config=RouterConfig(warmup_updates=0, min_bucket_updates=0),
    )

    assert context["context_quality"].iloc[-1] < 2.0 / 3.0
    assert routed.eq(0.0).all()
    assert diag["low_quality_entry_abstain"].any()


def test_router_is_future_invariant_and_never_switches_mid_episode():
    n = 140
    index = pd.date_range("2026-01-02 09:30", periods=n, freq="h")
    opens = pd.Series(100.0 * np.cumprod(np.r_[1.0, np.repeat(1.002, n - 1)]), index=index)
    a = pd.Series(0.0, index=index)
    b = pd.Series(0.0, index=index)
    a.iloc[5:45] = 0.40
    b.iloc[5:80] = 0.30
    a.iloc[90:120] = 0.40
    b.iloc[90:130] = 0.30
    context = pd.DataFrame(
        {
            "context_bucket": 0,
            "stress": False,
            "high_vol": False,
        },
        index=index,
    )
    cfg = RouterConfig(warmup_updates=2, fallback_expert=0, max_weight=0.5)
    full, diag = route_experts(opens, {"A": a, "B": b}, context, config=cfg)

    # A owns the first episode. When A exits, the router emits a flat bar and
    # does not jump straight into still-active B.
    assert (diag["selected_name"].iloc[5:45] == "A").all()
    assert full.iloc[45] == 0.0

    prefix_n = 100
    prefix, prefix_diag = route_experts(
        opens.iloc[:prefix_n],
        {"A": a.iloc[:prefix_n], "B": b.iloc[:prefix_n]},
        context.iloc[:prefix_n],
        config=cfg,
    )
    pd.testing.assert_series_equal(prefix, full.iloc[:prefix_n])
    pd.testing.assert_frame_equal(prefix_diag, diag.iloc[:prefix_n])


def test_stress_overlay_can_only_reduce_entry_size():
    index = pd.date_range("2026-01-02", periods=8, freq="h")
    opens = pd.Series(np.linspace(100, 101, len(index)), index=index)
    expert = pd.Series(0.50, index=index)
    context = pd.DataFrame(
        {"context_bucket": 6, "stress": True, "high_vol": True}, index=index
    )
    routed, _ = route_experts(
        opens,
        {"primary": expert},
        context,
        config=RouterConfig(warmup_updates=100, stress_high_vol_size=0.60),
    )
    assert routed.iloc[0] == 0.30
    assert routed.max() <= expert.max()


def test_new_stress_can_reduce_but_never_reincrease_an_open_episode():
    index = pd.date_range("2026-01-02", periods=8, freq="h")
    opens = pd.Series(np.linspace(100, 101, len(index)), index=index)
    expert = pd.Series(0.50, index=index)
    stress = pd.Series([False, False, True, True, False, False, False, False], index=index)
    context = pd.DataFrame(
        {
            "context_bucket": stress.astype(int) * 4,
            "stress": stress,
            "high_vol": False,
            "context_quality": 1.0,
        },
        index=index,
    )
    routed, _ = route_experts(
        opens,
        {"primary": expert},
        context,
        config=RouterConfig(warmup_updates=100, stress_size=0.70),
    )

    assert routed.iloc[0] == 0.50
    assert routed.iloc[2] == 0.35
    assert (routed.iloc[2:] == 0.35).all()


def test_low_quality_context_blocks_only_new_entries():
    index = pd.date_range("2026-01-02", periods=8, freq="h")
    opens = pd.Series(np.linspace(100, 101, len(index)), index=index)
    expert = pd.Series([0.5, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 0.5], index=index)
    quality = pd.Series([1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0], index=index)
    context = pd.DataFrame(
        {
            "context_bucket": 0,
            "stress": False,
            "high_vol": False,
            "context_quality": quality,
        },
        index=index,
    )
    routed, diag = route_experts(
        opens,
        {"primary": expert},
        context,
        config=RouterConfig(warmup_updates=100),
    )

    assert routed.iloc[1] == 0.5
    assert routed.iloc[3] == 0.0
    assert routed.iloc[4] == 0.5
    assert bool(diag["low_quality_entry_abstain"].iloc[3])
