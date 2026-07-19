"""Portfolio accounting and reconciliation."""

from __future__ import annotations

from typing import Dict, Tuple

from quantmodel.types import Position


class AccountingError(RuntimeError):
    pass


def mark_to_market(
    cash: float,
    positions: Dict[str, Position],
    marks: Dict[str, float],
) -> Tuple[float, float, float]:
    """Return (equity, gross_mv, unrealized_pnl)."""
    gross = 0.0
    unrealized = 0.0
    for sid, pos in positions.items():
        px = marks.get(sid)
        if px is None:
            raise AccountingError(f"Missing mark for {sid}")
        mv = pos.shares * px
        gross += mv
        unrealized += pos.shares * (px - pos.average_entry_price)
    equity = cash + gross
    return equity, gross, unrealized


def reconcile(equity: float, cash: float, gross_mv: float, tol: float = 0.01) -> None:
    expected = cash + gross_mv
    if abs(equity - expected) > tol:
        raise AccountingError(
            f"Accounting reconciliation failed: equity={equity:.4f} "
            f"cash+mv={expected:.4f} diff={equity - expected:.4f}"
        )
