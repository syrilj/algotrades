"""Trailing Donchian stop ratchet tests."""

from __future__ import annotations

from datetime import date

from quantmodel.strategy.exits import initial_stop_price, trail_stop_with_donchian
from quantmodel.types import Position


def test_initial_stop() -> None:
    assert initial_stop_price(100.0, atr=5.0, atr_multiple=3.0) == 85.0


def test_trail_only_up() -> None:
    pos = Position(
        permanent_security_id="A",
        symbol="A",
        shares=10,
        average_entry_price=100.0,
        entry_date=date(2020, 1, 1),
        stop_price=85.0,
        atr_at_entry=5.0,
        highest_stop=85.0,
    )
    trail_stop_with_donchian(pos, 90.0)
    assert pos.stop_price == 90.0
    trail_stop_with_donchian(pos, 88.0)
    assert pos.stop_price == 90.0
