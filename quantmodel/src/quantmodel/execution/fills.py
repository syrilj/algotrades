"""Fill generation."""

from __future__ import annotations

from datetime import date
from typing import Mapping, Optional, Tuple
from uuid import uuid4

from quantmodel.execution.commissions import commission_for_fill
from quantmodel.execution.slippage import (
    apply_buy_slippage,
    apply_sell_slippage,
    capacity_slippage_bps,
)
from quantmodel.types import Fill, Order, OrderStatus, Side


def fill_order(
    order: Order,
    *,
    fill_date: date,
    open_price: float,
    config: Mapping,
    median_dv_20: float = 0.0,
    reference_override: Optional[float] = None,
) -> Tuple[Order, Fill]:
    ref = reference_override if reference_override is not None else open_price
    notional = order.requested_shares * ref
    slip = capacity_slippage_bps(
        config=config,
        order_notional=notional,
        median_dv_20=median_dv_20,
    )
    if order.side == Side.BUY:
        px = apply_buy_slippage(ref, slip)
    else:
        px = apply_sell_slippage(ref, slip)
    comm = commission_for_fill(order.requested_shares, config)
    fill = Fill(
        fill_id=str(uuid4()),
        order_id=order.order_id,
        fill_date=fill_date,
        permanent_security_id=order.permanent_security_id,
        symbol=order.symbol,
        side=order.side,
        shares=order.requested_shares,
        reference_price=ref,
        fill_price=px,
        slippage_bps=slip,
        commission=comm,
        liquidity_fraction=(notional / median_dv_20) if median_dv_20 > 0 else 0.0,
        reason=order.signal_reason,
    )
    order.status = OrderStatus.FILLED
    return order, fill


def fill_stop(
    *,
    order_id: str,
    fill_date: date,
    permanent_security_id: str,
    symbol: str,
    shares: int,
    reference_price: float,
    mode: str,
    stop_price: float,
    open_price: float,
    config: Mapping,
    median_dv_20: float = 0.0,
) -> Fill:
    from quantmodel.execution.slippage import apply_sell_slippage, base_slippage_bps

    if mode == "gap_open":
        ref = open_price
    else:
        ref = stop_price
    slip = base_slippage_bps(config)
    px = apply_sell_slippage(ref, slip)
    comm = commission_for_fill(shares, config)
    return Fill(
        fill_id=str(uuid4()),
        order_id=order_id,
        fill_date=fill_date,
        permanent_security_id=permanent_security_id,
        symbol=symbol,
        side=Side.SELL,
        shares=shares,
        reference_price=ref,
        fill_price=px,
        slippage_bps=slip,
        commission=comm,
        liquidity_fraction=(shares * ref / median_dv_20) if median_dv_20 > 0 else 0.0,
        reason=f"ATR_STOP_{mode}",
    )
