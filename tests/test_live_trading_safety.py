import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from live_plan import _build_ib_draft  # noqa: E402
from risk_manager import PortfolioState, SetupSnapshot, plan_entry  # noqa: E402


def _options_setup() -> SetupSnapshot:
    return SetupSnapshot(
        symbol="TEST",
        model_conf=1.0,
        vol_z=3.0,
        trend_ok=True,
        macro_ok=True,
        qqq_ok=True,
        options_affordable=True,
        liquidity_ok=True,
    )


def test_recent_loss_reduces_options_risk_below_base_floor():
    normal = plan_entry(
        _options_setup(),
        PortfolioState(equity=1000, peak=1000, trade_pnl_history=[]),
    )
    after_loss = plan_entry(
        _options_setup(),
        PortfolioState(equity=1000, peak=1000, trade_pnl_history=[-1.0]),
    )

    assert normal.mode == "OPTIONS_ATTACK"
    assert after_loss.mode == "OPTIONS_ATTACK"
    assert after_loss.risk_pct < normal.risk_pct
    assert after_loss.risk_pct < 0.12


def test_drawdown_throttle_reduces_options_risk_before_halt():
    normal = plan_entry(
        _options_setup(),
        PortfolioState(equity=1000, peak=1000),
    )
    throttled = plan_entry(
        _options_setup(),
        PortfolioState(equity=830, peak=1000),
    )

    assert throttled.mode == "OPTIONS_ATTACK"
    assert 0 < throttled.risk_pct < normal.risk_pct


def test_blocked_confidence_produces_inert_broker_draft():
    decision = type("Decision", (), {"vehicle": "equity", "mode": "EQUITY_HEDGE"})()
    draft = _build_ib_draft(
        symbol="TEST",
        model="v39d_confluence",
        live={"price": 100.0, "go_long": True},
        model_info={"ok": True, "entry": 100.0, "stop": 95.0},
        decision=decision,
        readiness={"ready": False, "status": "BLOCKED", "blockers": ["active_calibration"]},
        execution_risk={"effective_max_loss_dollars": 0.0},
    )

    assert draft["status"] == "BLOCKED"
    assert draft["side"] == "FLAT"
    assert draft["qty"] == 0
    assert draft["transmit_allowed"] is False


def test_options_never_produce_an_equity_broker_draft():
    decision = type("Decision", (), {"vehicle": "options", "mode": "OPTIONS_ATTACK"})()
    draft = _build_ib_draft(
        symbol="TEST",
        model="v39d_confluence",
        live={"price": 100.0, "go_long": True},
        model_info={"ok": True, "entry": 100.0, "stop": 95.0},
        decision=decision,
        readiness={"ready": True, "status": "READY_FOR_MANUAL_REVIEW", "blockers": []},
        execution_risk={"effective_max_loss_dollars": 200.0},
    )

    assert draft["status"] == "BLOCKED"
    assert draft["side"] == "FLAT"
    assert draft["qty"] == 0
    assert "broker_draft_equity_only" in draft["blockers"]
