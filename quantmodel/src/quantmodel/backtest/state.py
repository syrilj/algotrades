"""Mutable backtest state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from quantmodel.portfolio.kill_switch import KillSwitchState
from quantmodel.types import DailyPortfolioSnapshot, Fill, Order, Position, SignalRow


@dataclass
class BacktestState:
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    pending_orders: List[Order] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    daily: List[DailyPortfolioSnapshot] = field(default_factory=list)
    signals: List[dict] = field(default_factory=list)
    peak_equity: float = 0.0
    realized_pnl: float = 0.0
    total_commissions: float = 0.0
    total_slippage_cost: float = 0.0
    total_dividends: float = 0.0
    kill_switch: KillSwitchState = field(default_factory=KillSwitchState)
    # shadow strategy equity (always fully invested path for kill switch resume)
    shadow_cash: float = 0.0
    shadow_positions: Dict[str, Position] = field(default_factory=dict)
    corporate_events: List[dict] = field(default_factory=list)
