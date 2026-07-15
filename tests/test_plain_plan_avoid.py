"""Operator plan labels: dry volume is WAIT with levels, not AVOID."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from trade_desk import _plain_plan  # noqa: E402


def _base_state(**overrides):
    state = {
        "price": 100.0,
        "stop": 95.0,
        "trail_arm": 105.0,
        "confidence": 0.55,
        "setup_kind": "wait",
        "setup_ok": False,
        "vol_dry": False,
        "flags": {
            "not_red_flag": True,
            "poc_hold": True,
            "in_value_area": False,
        },
        "missing": ["in_value_area", "vol_confirm_or_pull"],
        "ema22": 98.0,
        "ema200": 90.0,
        "val": 97.0,
        "vah": 102.0,
        "breakout_level": 103.0,
        "rvol": 0.6,
    }
    state.update(overrides)
    return state


def test_vol_dry_alone_is_wait_not_avoid():
    plan = _plain_plan(_base_state(vol_dry=True, setup_kind="wait"))
    assert plan["action"] == "WAIT"
    assert "AVOID" not in plan["action"]
    assert "22 EMA" in plan["do_next"] or "rvol" in plan["do_next"].lower() or "VAL" in plan["do_next"]


def test_red_flag_is_avoid():
    plan = _plain_plan(
        _base_state(
            vol_dry=True,
            setup_kind="wait",
            flags={"not_red_flag": False, "poc_hold": True},
        )
    )
    assert plan["action"] == "AVOID"


def test_explicit_avoid_kind_is_avoid():
    plan = _plain_plan(_base_state(setup_kind="avoid", vol_dry=False))
    assert plan["action"] == "AVOID"


def test_structural_break_labeled():
    plan = _plain_plan(_base_state(setup_kind="structural_break", ema200=110.0))
    assert "AVOID" in plan["action"]
    assert "200" in plan["why"]


def test_classic_buy_not_overridden_by_vol_dry():
    # vol_dry should not matter once kind is classic_buy (branch order).
    plan = _plain_plan(
        _base_state(
            setup_kind="classic_buy",
            setup_ok=True,
            vol_dry=True,
            confidence=0.72,
        )
    )
    assert plan["action"] == "BUY NOW"
