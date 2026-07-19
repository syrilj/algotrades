"""Corporate action application on open positions."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from quantmodel.data.adjustments import apply_split_to_position_shares, apply_split_to_price
from quantmodel.types import Position


def apply_pre_session_actions(
    positions: Dict[str, Position],
    day_bars: pd.DataFrame,
    cash: float,
) -> Tuple[Dict[str, Position], float, List[dict]]:
    """
    Apply splits (share/price adjust) and cash dividends before the session.
    Returns updated positions, cash, event log.
    """
    events: List[dict] = []
    if day_bars.empty or not positions:
        return positions, cash, events

    by_id = day_bars.set_index("permanent_security_id", drop=False)
    for sid, pos in list(positions.items()):
        if sid not in by_id.index:
            continue
        row = by_id.loc[sid]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        split = float(row.get("split_factor", 1.0) or 1.0)
        div = float(row.get("cash_dividend", 0.0) or 0.0)
        if split != 1.0:
            old_shares = pos.shares
            pos.shares = apply_split_to_position_shares(pos.shares, split)
            pos.average_entry_price = apply_split_to_price(pos.average_entry_price, split)
            pos.stop_price = apply_split_to_price(pos.stop_price, split)
            pos.highest_stop = apply_split_to_price(pos.highest_stop, split)
            events.append(
                {
                    "type": "split",
                    "security_id": sid,
                    "split_factor": split,
                    "shares_before": old_shares,
                    "shares_after": pos.shares,
                }
            )
        if div > 0 and pos.shares > 0:
            cash += pos.shares * div
            events.append(
                {
                    "type": "dividend",
                    "security_id": sid,
                    "dividend_per_share": div,
                    "cash_in": pos.shares * div,
                }
            )
        positions[sid] = pos
    return positions, cash, events
