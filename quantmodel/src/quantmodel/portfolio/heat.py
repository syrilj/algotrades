"""Portfolio heat accounting."""

from __future__ import annotations

from typing import Dict

from quantmodel.types import Position


def position_heat(pos: Position, equity: float) -> float:
    if equity <= 0 or pos.shares <= 0:
        return 0.0
    risk_per_share = max(pos.average_entry_price - pos.stop_price, 0.0)
    # Prefer distance from current stop if entry-stop is stale; use stop distance
    # from entry price for initial heat definition per spec:
    # Heat = shares * max(entry - stop, 0) / equity
    return (pos.shares * risk_per_share) / equity


def portfolio_heat(positions: Dict[str, Position], equity: float) -> float:
    return sum(position_heat(p, equity) for p in positions.values())


def ratchet_stop_up(pos: Position, new_stop: float) -> Position:
    """Never allow stop to move downward for a long."""
    if new_stop > pos.stop_price:
        pos.stop_price = new_stop
        pos.highest_stop = max(pos.highest_stop, new_stop)
    return pos
