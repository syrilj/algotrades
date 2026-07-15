"""Live scan ranks operator plays ahead of stand-aside / avoid."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from live_plan import _scan_action_rank  # noqa: E402


def test_buy_ranks_before_stand_aside():
    buy = {"analysis_action": "BUY NOW", "confidence_state": "ENTER", "mode": "EQUITY_HEDGE"}
    aside = {"analysis_action": "STAND ASIDE", "confidence_state": "ABSTAIN", "mode": "STAND_ASIDE"}
    assert _scan_action_rank(buy) < _scan_action_rank(aside)


def test_breakout_watch_ranks_before_avoid():
    watch = {"analysis_action": "BREAKOUT WATCH", "confidence_state": "WATCH", "mode": "STAND_ASIDE"}
    avoid = {"analysis_action": "AVOID", "confidence_state": "ABSTAIN", "mode": "STAND_ASIDE"}
    assert _scan_action_rank(watch) < _scan_action_rank(avoid)


def test_enter_equity_ranks_high():
    enter = {"analysis_action": "WAIT", "confidence_state": "ENTER", "mode": "EQUITY_HEDGE"}
    wait = {"analysis_action": "WAIT", "confidence_state": "WATCH", "mode": "STAND_ASIDE"}
    assert _scan_action_rank(enter) < _scan_action_rank(wait)
