import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import trade_desk  # noqa: E402
import live_plan  # noqa: E402


def _state():
    return {
        "risk_per_share": 2.0,
        "sleeve_fraction": 1.0,
        "price": 100.0,
        "setup_ok": True,
        "trail_arm": 106.0,
        "symbol": "TESTSYM",
        "model": "test_model",
    }


def test_half_percent_risk_on_10k_is_50_dollars():
    sz = trade_desk._position_math(_state(), account=10_000.0, risk_pct=0.005)
    assert sz["risk_budget"] == 50.0
    assert sz["shares"] == 25            # 50 // 2.0
    assert sz["dollar_risk"] == 50.0
    assert sz["risk_pct"] == 0.005       # fraction, not percent points


def test_rr_not_floored_when_arm_below_price():
    st = _state()
    st["trail_arm"] = 99.0  # arm BELOW price → reward must be negative, not floored to rps
    sz = trade_desk._position_math(st, account=10_000.0, risk_pct=0.005)
    assert sz["rr_to_arm"] < 0


def test_risk_budget_is_account_times_risk_pct():
    """Canonical contract: risk_budget = account × risk_pct (fraction)."""
    for account, risk_pct, expected in [
        (1_000.0, 0.01, 10.0),
        (25_000.0, 0.005, 125.0),
        (100_000.0, 0.02, 2_000.0),
    ]:
        sz = trade_desk._position_math(_state(), account=account, risk_pct=risk_pct)
        assert sz["risk_budget"] == expected
        assert abs(sz["risk_budget"] - account * risk_pct) < 1e-9


def test_shares_from_risk_per_share_floor_division():
    """shares = floor(risk_budget / risk_per_share), not rounded up."""
    st = _state()
    st["risk_per_share"] = 3.0
    # budget 50, rps 3 → floor(50/3) = 16, not 17
    sz = trade_desk._position_math(st, account=10_000.0, risk_pct=0.005)
    assert sz["shares"] == 16
    assert sz["dollar_risk"] == 48.0  # 16 * 3, not full budget


def test_sleeve_cap_limits_shares_below_risk_budget():
    st = _state()
    # After live_adapt, sleeve is floored at 0.15 → max notional 1500 on 10k
    st["sleeve_fraction"] = 0.10
    st["price"] = 100.0
    st["risk_per_share"] = 1.0
    # risk alone would allow 50 shares @ 1 rps; sleeve min 0.15 → 15 sh
    sz = trade_desk._position_math(st, account=10_000.0, risk_pct=0.005)
    assert sz["shares"] == 15
    assert sz["notional"] == 1_500.0
    assert sz["shares"] < 50  # still below pure risk budget

def test_zero_risk_per_share_yields_zero_shares():
    st = _state()
    st["risk_per_share"] = 0.0
    sz = trade_desk._position_math(st, account=10_000.0, risk_pct=0.01)
    assert sz["shares"] == 0


def test_live_plan_ac_shares_respects_risk_budget():
    """solve_ac_shares: uncapped path is floor(max_loss / risk_per_share)."""
    shares, impact = live_plan.solve_ac_shares(
        max_loss=100.0,
        entry=50.0,
        stop=48.0,  # rps = 2
        adv=0.0,  # force simple path (no impact loop)
        vol=0.0,
        eta=0.1,
        gamma=0.02,
        beta=0.5,
        side="long",
        account=10_000.0,
    )
    assert shares == 50  # 100 // 2
    assert impact == 0.0


def test_live_plan_ac_shares_caps_by_account_notional():
    shares, _ = live_plan.solve_ac_shares(
        max_loss=50_000.0,
        entry=100.0,
        stop=90.0,  # rps = 10 → risk would allow 5000 sh
        adv=0.0,
        vol=0.0,
        eta=0.1,
        gamma=0.02,
        beta=0.5,
        side="long",
        account=1_000.0,  # only 10 shares affordable
    )
    assert shares == 10
