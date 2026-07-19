"""Shared types and dataclasses for quantmodel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    PARTIAL = "PARTIAL"


class OrderType(str, Enum):
    MARKET_NEXT_OPEN = "MARKET_NEXT_OPEN"
    STOP = "STOP"


class ExitReason(str, Enum):
    DONCHIAN = "DONCHIAN"
    ATR_STOP = "ATR_STOP"
    KILL_SWITCH = "KILL_SWITCH"
    DELIST = "DELIST"
    INELIGIBLE = "INELIGIBLE"
    MAX_HOLD = "MAX_HOLD"
    EARNINGS = "EARNINGS"


class DeploymentStatus(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    VALIDATION_PASS = "VALIDATION_PASS"
    DEPLOYMENT_BLOCKED = "DEPLOYMENT_BLOCKED"
    PAPER_READY = "PAPER_READY"
    LIVE_DISABLED = "LIVE_DISABLED"


@dataclass(frozen=True)
class Bar:
    permanent_security_id: str
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_open: float
    adjusted_high: float
    adjusted_low: float
    adjusted_close: float
    adjusted_volume: float
    split_factor: float = 1.0
    cash_dividend: float = 0.0
    exchange: str = "UNKNOWN"
    security_type: str = "common_stock"
    is_delisted: bool = False
    delisting_date: Optional[date] = None
    vendor_timestamp: Optional[str] = None
    sector: str = "UNKNOWN"


@dataclass
class Position:
    permanent_security_id: str
    symbol: str
    shares: int
    average_entry_price: float
    entry_date: date
    stop_price: float
    atr_at_entry: float
    sector: str = "UNKNOWN"
    highest_stop: float = 0.0  # ratchet floor for longs (never decreases stop)

    def __post_init__(self) -> None:
        if self.highest_stop == 0.0:
            self.highest_stop = self.stop_price


@dataclass
class Order:
    order_id: str
    created_date: date
    intended_fill_date: date
    permanent_security_id: str
    symbol: str
    side: Side
    order_type: OrderType
    requested_shares: int
    reference_price: float
    signal_reason: str
    risk_budget: float = 0.0
    stop_price: Optional[float] = None
    expected_heat: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    rejection_reason: Optional[str] = None
    atr_for_stop: Optional[float] = None
    sector: str = "UNKNOWN"


@dataclass
class Fill:
    fill_id: str
    order_id: str
    fill_date: date
    permanent_security_id: str
    symbol: str
    side: Side
    shares: int
    reference_price: float
    fill_price: float
    slippage_bps: float
    commission: float
    liquidity_fraction: float = 0.0
    reason: str = ""


@dataclass
class SignalRow:
    date: date
    permanent_security_id: str
    symbol: str
    entry_signal: bool
    exit_signal: bool
    prior_55d_high: float
    prior_20d_low: float
    close: float
    volume: float
    median_volume_50d: float
    volume_multiple: float
    sma_200: float
    benchmark_close: float
    benchmark_sma_200: float
    atr_20: float
    eligibility_pass: bool
    eligibility_reasons: str
    rank: Optional[int] = None
    breakout_strength: float = 0.0
    momentum_126: float = 0.0
    median_dv_20: float = 0.0


@dataclass
class DailyPortfolioSnapshot:
    date: date
    cash: float
    gross_exposure: float
    net_exposure: float
    equity: float
    peak_equity: float
    drawdown: float
    portfolio_heat: float
    open_positions: int
    pending_orders: int
    kill_switch_active: bool
    shadow_equity: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    commissions: float = 0.0
    slippage_cost: float = 0.0
    dividends: float = 0.0


@dataclass
class ExperimentManifest:
    run_id: str
    run_name: str
    created_at_utc: datetime
    git_commit: str
    git_dirty_flag: bool
    python_version: str
    dependency_lock_hash: str
    config_hash: str
    data_manifest_hash: str
    random_seed: int
    experiment_number: int
    parent_run_id: Optional[str] = None
    notes: str = ""
    deployment_status: str = DeploymentStatus.RESEARCH_ONLY.value
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityIssue:
    run_id: str
    security_id: str
    symbol: str
    date: Optional[date]
    issue_code: str
    raw_values: str
    resolution: str
