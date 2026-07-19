"""Sizing and heat tests."""

from __future__ import annotations

from quantmodel.portfolio.heat import portfolio_heat, position_heat, ratchet_stop_up
from quantmodel.portfolio.sizing import final_shares, risk_based_shares
from quantmodel.types import Position
from datetime import date


def test_risk_based_shares_1m_account() -> None:
    # $1M, 0.5% risk, stop dist = 2*ATR, ATR=5 => dist=10 => shares=5000/10=500
    shares = risk_based_shares(1_000_000, 0.005, atr=5.0, atr_multiple=2.0)
    assert shares == 500


def test_heat_cap_logic() -> None:
    pos = Position(
        permanent_security_id="A",
        symbol="A",
        shares=100,
        average_entry_price=50.0,
        entry_date=date(2020, 1, 1),
        stop_price=45.0,
        atr_at_entry=2.5,
    )
    # heat = 100 * 5 / 1e6 = 0.0005
    assert abs(position_heat(pos, 1_000_000) - 0.0005) < 1e-12
    assert abs(portfolio_heat({"A": pos}, 1_000_000) - 0.0005) < 1e-12


def test_stop_never_decreases() -> None:
    pos = Position(
        permanent_security_id="A",
        symbol="A",
        shares=10,
        average_entry_price=100.0,
        entry_date=date(2020, 1, 1),
        stop_price=90.0,
        atr_at_entry=5.0,
        highest_stop=90.0,
    )
    ratchet_stop_up(pos, 95.0)
    assert pos.stop_price == 95.0
    ratchet_stop_up(pos, 92.0)
    assert pos.stop_price == 95.0


def test_final_shares_rejects_below_one() -> None:
    cfg = {
        "risk": {
            "atr_multiple": 2.0,
            "risk_per_trade": 0.005,
            "max_position_weight": 0.10,
            "max_sector_weight": 0.30,
        },
        "universe": {"max_position_fraction_of_adv": 0.01},
        "execution": {"volume_participation_limit": 0.01},
    }
    # tiny ADV => 0 shares
    s = final_shares(
        equity=1_000_000,
        price=100.0,
        atr=2.0,
        config=cfg,
        median_dv_20=10.0,
        available_heat=0.04,
        sector_exposure=0.0,
    )
    assert s == 0
