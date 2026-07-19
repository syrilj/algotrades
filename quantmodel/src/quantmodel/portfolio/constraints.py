"""Portfolio constraints helpers."""

from __future__ import annotations

from typing import Dict, Mapping

from quantmodel.portfolio.heat import portfolio_heat
from quantmodel.types import Position


def can_open_new(
    *,
    positions: Dict[str, Position],
    equity: float,
    config: Mapping,
    kill_switch_active: bool,
    proposed_heat: float,
) -> tuple[bool, str]:
    risk = config["risk"]
    if kill_switch_active and not risk.get("allow_new_entries_during_kill_switch", False):
        return False, "kill_switch"
    if len(positions) >= int(risk["max_positions"]):
        return False, "max_positions"
    heat = portfolio_heat(positions, equity)
    if heat + proposed_heat > float(risk["max_portfolio_heat"]) + 1e-12:
        return False, "heat_cap"
    return True, ""


def sector_exposure(positions: Dict[str, Position], marks: Dict[str, float], sector: str) -> float:
    total = 0.0
    for sid, pos in positions.items():
        if pos.sector == sector:
            px = marks.get(sid, pos.average_entry_price)
            total += pos.shares * px
    return total
