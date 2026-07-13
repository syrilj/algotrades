from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from threading import RLock
from typing import DefaultDict, Dict, Iterable, Optional, Tuple

from .contracts import Bar, Tick, require_utc


_TIMEFRAMES = {"1m": 60, "5m": 300}
TickIdentity = Tuple[object, ...]
BarKey = Tuple[str, str, datetime]


class LatestTickState:
    def __init__(self) -> None:
        self._latest: Dict[str, Tick] = {}
        self._lock = RLock()

    def update(self, tick: Tick) -> bool:
        with self._lock:
            current = self._latest.get(tick.instrument_id)
            if current is None:
                self._latest[tick.instrument_id] = tick
                return True
            if tick.market_asof < current.market_asof:
                return False
            if tick.market_asof == current.market_asof:
                if (tick.event_id and tick.event_id == current.event_id) or (
                    tick.price == current.price and tick.size == current.size
                ):
                    return False
                if (tick.received_at, tick.price, tick.size) <= (
                    current.received_at,
                    current.price,
                    current.size,
                ):
                    return False
            self._latest[tick.instrument_id] = tick
            return True

    def get(self, instrument_id: str) -> Optional[Tick]:
        with self._lock:
            return self._latest.get(instrument_id)

    def snapshot(self) -> Dict[str, Tick]:
        with self._lock:
            return dict(self._latest)


class TickBarAggregator:
    def __init__(self, timeframes: Iterable[str] = ("1m", "5m")) -> None:
        configured = tuple(timeframes)
        unsupported = set(configured) - set(_TIMEFRAMES)
        if unsupported:
            raise ValueError(f"unsupported timeframes: {sorted(unsupported)}")
        if not configured:
            raise ValueError("at least one timeframe is required")
        self._timeframes = configured
        self._ticks: DefaultDict[BarKey, Dict[TickIdentity, Tick]] = defaultdict(dict)
        self._computed_at: Dict[BarKey, datetime] = {}
        self._lock = RLock()

    @staticmethod
    def _identity(tick: Tick) -> TickIdentity:
        if tick.event_id is not None:
            return ("event", tick.event_id)
        return ("values", tick.market_asof, tick.price, tick.size)

    @staticmethod
    def _bucket_start(market_asof: datetime, seconds: int) -> datetime:
        epoch_seconds = int(market_asof.timestamp())
        return datetime.fromtimestamp(epoch_seconds - epoch_seconds % seconds, tz=timezone.utc)

    def add(self, tick: Tick, computed_at: datetime) -> Tuple[Bar, ...]:
        require_utc(computed_at, "computed_at")
        identity = self._identity(tick)
        affected = []
        with self._lock:
            for timeframe in self._timeframes:
                bucket_start = self._bucket_start(tick.market_asof, _TIMEFRAMES[timeframe])
                key = (tick.instrument_id, timeframe, bucket_start)
                if identity not in self._ticks[key]:
                    self._ticks[key][identity] = tick
                    previous = self._computed_at.get(key)
                    self._computed_at[key] = max(previous, computed_at) if previous else computed_at
                affected.append(self._bar(key))
        return tuple(affected)

    def _bar(self, key: BarKey) -> Bar:
        instrument_id, timeframe, bucket_start = key
        ticks = sorted(
            self._ticks[key].values(),
            key=lambda tick: (
                tick.market_asof,
                tick.received_at,
                tick.event_id or "",
                tick.price,
                tick.size,
            ),
        )
        prices = [tick.price for tick in ticks]
        return Bar(
            instrument_id=instrument_id,
            timeframe=timeframe,
            bucket_start=bucket_start,
            open=prices[0],
            high=max(prices),
            low=min(prices),
            close=prices[-1],
            volume=sum(tick.size for tick in ticks),
            market_asof=max(tick.market_asof for tick in ticks),
            received_at=max(tick.received_at for tick in ticks),
            computed_at=self._computed_at[key],
        )

    def bars(self, instrument_id: str, timeframe: str) -> Tuple[Bar, ...]:
        if timeframe not in self._timeframes:
            raise ValueError(f"timeframe is not configured: {timeframe}")
        with self._lock:
            keys = sorted(
                (
                    key
                    for key in self._ticks
                    if key[0] == instrument_id and key[1] == timeframe
                ),
                key=lambda key: key[2],
            )
            return tuple(self._bar(key) for key in keys)
