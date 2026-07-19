"""Paper-trading broker interface (no live routing)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List

from quantmodel.types import Fill, Order, OrderStatus


@dataclass
class PaperBroker:
    """Records intended orders for paper reconciliation. Does not send live orders."""

    fills: List[Fill] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    live_routing_enabled: bool = False

    def submit(self, order: Order) -> Order:
        if self.live_routing_enabled:
            raise RuntimeError("Live routing is hard-disabled until promotion gates pass")
        order.status = OrderStatus.PENDING
        self.orders.append(order)
        return order

    def record_fill(self, fill: Fill) -> None:
        self.fills.append(fill)
