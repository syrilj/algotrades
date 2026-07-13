from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Tuple, Union


class InstrumentCategory(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    FX = "fx"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    INDEX = "index"
    FUTURE = "future"
    OPTION = "option"
    ECONOMICS = "economics"
    BOND = "bond"
    YIELD = "yield"
    INTEREST_RATE = "interest_rate"
    CURRENCY_INDEX = "currency_index"
    UNKNOWN = "unknown"


class InstrumentClassification(str, Enum):
    TRADABLE = "tradable"
    CONTEXT_ONLY = "context_only"
    UNSUPPORTED = "unsupported"


class CoverageMode(str, Enum):
    FULL = "FULL"
    WARMING = "WARMING"
    DEGRADED_RANKED = "DEGRADED_RANKED"
    STALE = "STALE"


class Horizon(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"


def require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


class JsonContract:
    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class Instrument(JsonContract):
    symbol: str
    name: str
    category: InstrumentCategory
    classification: InstrumentClassification
    asset_class: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.asset_class.strip():
            raise ValueError("asset_class is required")


@dataclass(frozen=True)
class Tick(JsonContract):
    instrument_id: str
    price: float
    size: float
    market_asof: datetime
    received_at: datetime
    event_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.instrument_id.strip():
            raise ValueError("instrument_id is required")
        if not math.isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be positive and finite")
        if not math.isfinite(self.size) or self.size < 0:
            raise ValueError("size must be non-negative and finite")
        require_utc(self.market_asof, "market_asof")
        require_utc(self.received_at, "received_at")


@dataclass(frozen=True)
class Bar(JsonContract):
    instrument_id: str
    timeframe: str
    bucket_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    market_asof: datetime
    received_at: datetime
    computed_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.bucket_start, "bucket_start")
        require_utc(self.market_asof, "market_asof")
        require_utc(self.received_at, "received_at")
        require_utc(self.computed_at, "computed_at")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        if self.high < self.low:
            raise ValueError("high must not be below low")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")


@dataclass(frozen=True)
class DataFreshness(JsonContract):
    category: InstrumentCategory
    market_asof: datetime
    computed_at: datetime
    age: timedelta
    threshold: timedelta
    is_stale: bool

    def __post_init__(self) -> None:
        require_utc(self.market_asof, "market_asof")
        require_utc(self.computed_at, "computed_at")
        if self.age < timedelta(0):
            raise ValueError("age must be non-negative")
        if self.threshold <= timedelta(0):
            raise ValueError("threshold must be positive")


EvidenceValue = Union[float, int, str, bool]


@dataclass(frozen=True)
class OpportunityEvidence(JsonContract):
    name: str
    value: EvidenceValue
    market_asof: datetime

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("evidence name is required")
        require_utc(self.market_asof, "market_asof")


@dataclass(frozen=True)
class TradePlan(JsonContract):
    side: str
    entry_zone: Tuple[float, float]
    entry_trigger: str
    invalidation: str
    stop: float
    targets: Tuple[float, ...]
    trailing_rule: Optional[str]
    time_stop: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_zone", tuple(self.entry_zone))
        object.__setattr__(self, "targets", tuple(self.targets))
        if not self.side.strip():
            raise ValueError("side is required")
        if len(self.entry_zone) != 2 or self.entry_zone[0] > self.entry_zone[1]:
            raise ValueError("entry_zone must contain an ordered lower and upper bound")
        if not self.entry_trigger.strip():
            raise ValueError("entry_trigger is required")
        if not self.invalidation.strip():
            raise ValueError("invalidation is required")
        if not math.isfinite(self.stop):
            raise ValueError("stop must be finite")
        if not self.targets and not (self.trailing_rule and self.trailing_rule.strip()):
            raise ValueError("targets or trailing_rule is required")
        if not self.time_stop.strip():
            raise ValueError("time_stop is required")


@dataclass(frozen=True)
class Opportunity(JsonContract):
    instrument: Instrument
    horizon: Horizon
    score: float
    actionable: bool
    evidence: Tuple[OpportunityEvidence, ...]
    freshness: DataFreshness
    trade_plan: Optional[TradePlan]
    computed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        require_utc(self.computed_at, "computed_at")
        if not math.isfinite(self.score):
            raise ValueError("score must be finite")
        if self.actionable and self.trade_plan is None:
            raise ValueError("actionable opportunities require a trade_plan")


@dataclass(frozen=True)
class CoverageHealth(JsonContract):
    mode: CoverageMode
    catalog_total: int
    streamable_total: int
    subscribed_count: int
    stale_count: int
    allowance_ok: bool
    allowance_reason: Optional[str]
    computed_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.computed_at, "computed_at")
        counts = (
            self.catalog_total,
            self.streamable_total,
            self.subscribed_count,
            self.stale_count,
        )
        if any(count < 0 for count in counts):
            raise ValueError("coverage counts must be non-negative")


@dataclass(frozen=True)
class RankedOpportunity(JsonContract):
    opportunity: Opportunity
    cohort_rank: int
    cohort_size: int
    cohort_score: float
    priority: float
