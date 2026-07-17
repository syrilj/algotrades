from __future__ import annotations

import json

import pytest

from backtest.engines.global_equity import GlobalEquityEngine
from tools.stress_backtest import (
    PASS_BAR,
    StressedGlobalEquityEngine,
    build_run_config,
    evaluate_pass_bar,
    load_manifest_contract,
    load_stress_scenarios,
)


BASE_CFG = {"initial_cash": 1000}


def _engine(**stress) -> StressedGlobalEquityEngine:
    return StressedGlobalEquityEngine({**BASE_CFG, **stress}, market="us")


# ---------------------------------------------------------------------------
# Default behavior must be bit-identical to the promotion engine (no silent
# cost changes when stress keys are absent).
# ---------------------------------------------------------------------------


def test_defaults_reproduce_global_equity_engine_costs():
    plain = GlobalEquityEngine(dict(BASE_CFG), market="us")
    stressed = _engine()  # no stress keys at all
    for price, direction in ((100.0, 1), (100.0, -1), (57.31, 1)):
        assert stressed.apply_slippage(price, direction) == pytest.approx(
            plain.apply_slippage(price, direction)
        )
    for size, price, is_open in ((10, 100.0, True), (3.5, 250.0, False)):
        assert stressed.calc_commission(size, price, 1, is_open) == pytest.approx(
            plain.calc_commission(size, price, 1, is_open)
        )


def test_zero_valued_stress_keys_also_reproduce_baseline():
    plain = GlobalEquityEngine(dict(BASE_CFG), market="us")
    stressed = _engine(stress_commission_per_side=0.0, slippage_bps={})
    assert stressed.apply_slippage(100.0, 1) == pytest.approx(plain.apply_slippage(100.0, 1))
    assert stressed.calc_commission(10, 100.0, 1, True) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Commission stress arithmetic.
# ---------------------------------------------------------------------------


def test_commission_stress_charges_notional_rate_per_side():
    eng = _engine(stress_commission_per_side=0.002)
    # US base commission is zero, so the full charge is the stress rate.
    assert eng.calc_commission(10, 100.0, 1, is_open=True) == pytest.approx(2.0)
    assert eng.calc_commission(10, 110.0, 1, is_open=False) == pytest.approx(2.2)


# ---------------------------------------------------------------------------
# Slippage stress arithmetic.
# ---------------------------------------------------------------------------


def test_slippage_bps_adds_to_base_rate_per_side():
    eng = _engine(slippage_bps={"IONQ.US": 20})
    eng._active_symbol = "IONQ.US"
    # base 5 bps + extra 20 bps = 25 bps per side
    assert eng.apply_slippage(100.0, 1) == pytest.approx(100.0 * 1.0025)
    assert eng.apply_slippage(100.0, -1) == pytest.approx(100.0 * 0.9975)


def test_slippage_bps_falls_back_to_bare_symbol_then_default():
    eng = _engine(slippage_bps={"TSLA": 10, "default": 7})
    eng._active_symbol = "TSLA.US"
    assert eng.apply_slippage(100.0, 1) == pytest.approx(100.0 * (1 + 0.0005 + 0.0010))
    eng._active_symbol = "NVDA.US"  # unmapped → default 7 bps
    assert eng.apply_slippage(100.0, 1) == pytest.approx(100.0 * (1 + 0.0005 + 0.0007))


def test_unmapped_symbol_without_default_gets_base_slippage_only():
    eng = _engine(slippage_bps={"IONQ.US": 20})
    eng._active_symbol = "SPY.US"
    assert eng.apply_slippage(100.0, 1) == pytest.approx(100.0 * 1.0005)


# ---------------------------------------------------------------------------
# Synthetic round trip: known price move, expected P&L reduction.
# ---------------------------------------------------------------------------


def test_synthetic_round_trip_pnl_reduction():
    """Buy 10 sh @ 100, sell @ 110: stress must cost exactly the added bps + commission."""
    baseline = GlobalEquityEngine(dict(BASE_CFG), market="us")
    stressed = _engine(stress_commission_per_side=0.002, slippage_bps={"XYZ.US": 20})
    stressed._active_symbol = "XYZ.US"
    size = 10.0

    def round_trip_pnl(eng) -> float:
        entry = eng.apply_slippage(100.0, 1)   # buying pays up
        exit_ = eng.apply_slippage(110.0, -1)  # selling receives less
        pnl = (exit_ - entry) * size
        pnl -= eng.calc_commission(size, entry, 1, is_open=True)
        pnl -= eng.calc_commission(size, exit_, 1, is_open=False)
        return pnl

    pnl_base = round_trip_pnl(baseline)
    pnl_stress = round_trip_pnl(stressed)

    # Baseline: entry 100.05, exit 109.945, zero commission.
    assert pnl_base == pytest.approx((109.945 - 100.05) * size)

    # Stressed: 25 bps per side slippage; 0.002 commission per side.
    entry_s = 100.0 * 1.0025
    exit_s = 110.0 * 0.9975
    expected = (exit_s - entry_s) * size - 0.002 * size * (entry_s + exit_s)
    assert pnl_stress == pytest.approx(expected)
    assert pnl_stress < pnl_base  # stress always reduces P&L on this trade


# ---------------------------------------------------------------------------
# Config plumbing against the real repo artifacts (read-only).
# ---------------------------------------------------------------------------


def test_load_manifest_contract_reads_locked_windows():
    contract = load_manifest_contract()
    assert contract["windows"]["train"] == ("2024-08-01", "2025-08-01")
    assert contract["windows"]["holdout"] == ("2025-08-01", "2026-07-11")
    assert "TSLA.US" in contract["universe"]
    assert contract["interval"] == "1H"
    assert contract["source"] == "local"


def test_load_stress_scenarios_has_both_plan_variants():
    scenarios = load_stress_scenarios()
    ids = {s["id"] for s in scenarios}
    assert "commission_2x" in ids
    assert "commission_2x_plus_spread" in ids
    by_id = {s["id"]: s for s in scenarios}
    assert by_id["commission_2x"]["stress_commission_per_side"] == pytest.approx(0.002)
    slip = by_id["commission_2x_plus_spread"]["slippage_bps"]
    # Plan: thin names carry AT LEAST 2x the SPY haircut (spec example pins
    # SPY/QQQ/XLP at 5 bps and IONQ/APLD at 20 bps per side).
    assert slip["IONQ.US"] >= 2 * slip["SPY.US"]
    assert slip["APLD.US"] >= 2 * slip["SPY.US"]
    assert slip["SPY.US"] == 5
    assert slip["IONQ.US"] == 20


def test_build_run_config_baseline_has_no_stress_keys():
    contract = load_manifest_contract()
    cfg = build_run_config(contract, contract["windows"]["holdout"], None)
    assert "stress_commission_per_side" not in cfg
    assert "slippage_bps" not in cfg
    assert cfg["start_date"] == "2025-08-01"
    assert cfg["end_date"] == "2026-07-11"


def test_build_run_config_scenario_carries_stress_keys():
    contract = load_manifest_contract()
    scenario = {"id": "x", "stress_commission_per_side": 0.002, "slippage_bps": {"SPY.US": 5}}
    cfg = build_run_config(contract, contract["windows"]["train"], scenario)
    assert cfg["stress_commission_per_side"] == pytest.approx(0.002)
    assert cfg["slippage_bps"] == {"SPY.US": 5}
    assert cfg["strategy"]["stress_scenario"] == "x"


# ---------------------------------------------------------------------------
# Pass-bar evaluation is fail-closed.
# ---------------------------------------------------------------------------


def test_pass_bar_requires_stressed_holdout_rows():
    out = evaluate_pass_bar([])
    assert out["pass"] is False
    assert out["reason"] == "no_stressed_holdout_runs"


def test_pass_bar_passes_only_when_ret_positive_and_sharpe_at_least_one():
    rows = [
        {"scenario": "commission_2x", "window": "holdout", "ret": 0.4, "sharpe": 1.5, "error": None},
        {"scenario": "commission_2x_plus_spread", "window": "holdout", "ret": 0.2, "sharpe": 0.9, "error": None},
    ]
    out = evaluate_pass_bar(rows)
    assert out["scenarios"]["commission_2x"]["pass"] is True
    assert out["scenarios"]["commission_2x_plus_spread"]["pass"] is False
    assert out["pass"] is False


def test_pass_bar_run_error_fails_that_scenario():
    rows = [{"scenario": "commission_2x", "window": "holdout", "error": "boom"}]
    out = evaluate_pass_bar(rows)
    assert out["pass"] is False
    assert out["scenarios"]["commission_2x"]["pass"] is False


def test_pass_bar_ignores_baseline_and_train_rows():
    rows = [
        {"scenario": "baseline", "window": "holdout", "ret": -1.0, "sharpe": -5.0, "error": None},
        {"scenario": "commission_2x", "window": "train", "ret": -1.0, "sharpe": -5.0, "error": None},
        {"scenario": "commission_2x", "window": "holdout", "ret": 0.3, "sharpe": 1.2, "error": None},
    ]
    out = evaluate_pass_bar(rows)
    assert out["pass"] is True


def test_pass_bar_constant_matches_plan():
    assert PASS_BAR["holdout_return_gt"] == 0.0
    assert PASS_BAR["holdout_sharpe_gte"] == 1.0
