"""Order factory helpers."""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import uuid4

from quantmodel.types import Order, OrderStatus, OrderType, Side


def new_order(
    *,
    created_date: date,
    intended_fill_date: date,
    permanent_security_id: str,
    symbol: str,
    side: Side,
    shares: int,
    reference_price: float,
    signal_reason: str,
    stop_price: Optional[float] = None,
    risk_budget: float = 0.0,
    expected_heat: float = 0.0,
    atr_for_stop: Optional[float] = None,
    sector: str = "UNKNOWN",
) -> Order:
    return Order(
        order_id=str(uuid4()),
        created_date=created_date,
        intended_fill_date=intended_fill_date,
        permanent_security_id=permanent_security_id,
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET_NEXT_OPEN,
        requested_shares=shares,
        reference_price=reference_price,
        signal_reason=signal_reason,
        risk_budget=risk_budget,
        stop_price=stop_price,
        expected_heat=expected_heat,
        status=OrderStatus.PENDING,
        atr_for_stop=atr_for_stop,
        sector=sector,
    )
