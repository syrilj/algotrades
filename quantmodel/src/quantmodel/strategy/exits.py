"""Exit decision helpers."""

from __future__ import annotations

from datetime import date
from typing import Optional

from quantmodel.portfolio.heat import ratchet_stop_up
from quantmodel.types import ExitReason, Position


def evaluate_exits_for_position(
    pos: Position,
    *,
    bar_low: float,
    bar_open: float,
    prior_exit_low: float,
    donchian_exit: bool,
    asof: date,
    max_holding_days: Optional[int],
    force_kill: bool = False,
    delisted: bool = False,
) -> Optional[ExitReason]:
    if force_kill:
        return ExitReason.KILL_SWITCH
    if delisted:
        return ExitReason.DELIST
    if max_holding_days is not None:
        held = (asof - pos.entry_date).days
        if held >= max_holding_days:
            return ExitReason.MAX_HOLD
    # ATR stop checked separately intraday; Donchian is close/low based signal for next open
    if donchian_exit or bar_low < prior_exit_low:
        return ExitReason.DONCHIAN
    return None


def stop_hit_intraday(pos: Position, bar_open: float, bar_low: float) -> tuple[bool, str]:
    """
    Returns (hit, fill_mode) where fill_mode is 'gap_open' or 'stop_price'.
    Only valid for positions that existed before the session.
    """
    stop = pos.stop_price
    if bar_open <= stop:
        return True, "gap_open"
    if bar_low <= stop:
        return True, "stop_price"
    return False, ""


def trail_stop_with_donchian(pos: Position, prior_exit_low: float) -> Position:
    """
    Ratchet long stop up to the prior N-day low (never down).

    prior_exit_low must exclude the current bar (computed with shift+rolling).
    """
    if prior_exit_low is None:
        return pos
    try:
        level = float(prior_exit_low)
    except (TypeError, ValueError):
        return pos
    if level != level:  # NaN
        return pos
    # Only trail if the channel low is above entry stop path and meaningful
    return ratchet_stop_up(pos, level)


def initial_stop_price(
    fill_price: float,
    atr: float,
    atr_multiple: float,
) -> float:
    return fill_price - float(atr_multiple) * float(atr)
