from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from .contracts import (
    Bar,
    CoverageHealth,
    CoverageMode,
    Instrument,
    InstrumentCategory,
    InstrumentClassification,
    Tick,
)
from .decision import evaluate_freshness
from .persistence import TickPersistence
from .state import LatestTickState, TickBarAggregator


DEFAULT_FRESHNESS_THRESHOLDS = {
    InstrumentCategory.STOCK: timedelta(minutes=5),
    InstrumentCategory.ETF: timedelta(minutes=5),
    InstrumentCategory.FX: timedelta(minutes=1),
    InstrumentCategory.CRYPTO: timedelta(minutes=1),
    InstrumentCategory.COMMODITY: timedelta(minutes=2),
    InstrumentCategory.INDEX: timedelta(minutes=5),
    InstrumentCategory.FUTURE: timedelta(minutes=2),
    InstrumentCategory.OPTION: timedelta(minutes=2),
    InstrumentCategory.ECONOMICS: timedelta(hours=1),
    InstrumentCategory.BOND: timedelta(hours=1),
    InstrumentCategory.YIELD: timedelta(hours=1),
    InstrumentCategory.INTEREST_RATE: timedelta(hours=1),
    InstrumentCategory.CURRENCY_INDEX: timedelta(hours=1),
}


class StreamSupervisor:
    def __init__(
        self,
        adapter: Any,
        max_symbols: int = 1000,
        freshness_thresholds: Optional[Dict[InstrumentCategory, timedelta]] = None,
        warming_seconds: float = 10.0,
        stale_window_seconds: float = 300.0,
        selector: Optional[Callable[[List[Instrument]], List[Instrument]]] = None,
        persistence: Optional[TickPersistence] = None,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
    ) -> None:
        self._adapter = adapter
        self._max_symbols = max(1, int(max_symbols))
        self._freshness_thresholds = freshness_thresholds or DEFAULT_FRESHNESS_THRESHOLDS
        self._warming_seconds = float(warming_seconds)
        self._stale_window_seconds = float(stale_window_seconds)
        self._selector = selector
        self._persistence = persistence
        self._reconnect_initial_seconds = max(0.01, float(reconnect_initial_seconds))
        self._reconnect_max_seconds = max(
            self._reconnect_initial_seconds, float(reconnect_max_seconds)
        )

        self._state = LatestTickState()
        self._aggregator = TickBarAggregator(("1m", "5m"))
        self._catalog: List[Instrument] = []
        self._instrument_map: Dict[str, Instrument] = {}
        self._symbols: List[str] = []
        self._fallback = False

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._started_at: Optional[datetime] = None
        self._last_tick_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    def start(self, symbols: Optional[Iterable[str]] = None) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("supervisor is already running")
        self._stop_event.clear()
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        self._last_error = None

        if symbols is None:
            try:
                self._catalog = self._adapter.catalog()
            except Exception as e:  # noqa: BLE001
                self._last_error = str(e)
                self._catalog = []
        else:
            self._catalog = []

        self._instrument_map = {i.symbol: i for i in self._catalog}

        if symbols is None:
            tradable = [i for i in self._catalog if i.classification == InstrumentClassification.TRADABLE]
            if len(tradable) > self._max_symbols:
                ranked = self._selector(tradable) if self._selector else tradable
                selected = ranked[: self._max_symbols]
                self._fallback = True
            else:
                selected = tradable
                self._fallback = False
            self._symbols = [i.symbol for i in selected]
        else:
            self._symbols = [s for s in symbols]
            self._fallback = False

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        backoff = self._reconnect_initial_seconds
        while not self._stop_event.is_set():
            try:
                for tick in self._adapter.stream(self._symbols):
                    if self._stop_event.is_set():
                        break
                    self._on_tick(tick)
                    backoff = self._reconnect_initial_seconds
                # Keep the supervisor alive until stop() is called. A real LSE
                # stream does not end; finite injected streams are replay/tests.
                if not self._stop_event.is_set():
                    self._stop_event.wait()
                break
            except Exception as e:  # noqa: BLE001
                self._last_error = str(e)
                if self._stop_event.wait(backoff):
                    break
                backoff = min(self._reconnect_max_seconds, backoff * 2.0)
        self._running = False

    def _on_tick(self, tick: Tick) -> None:
        self._state.update(tick)
        computed_at = datetime.now(timezone.utc)
        self._aggregator.add(tick, computed_at)
        if self._persistence is not None:
            self._persistence.append(tick)
        self._last_tick_at = computed_at

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        try:
            self._adapter.disconnect()
        except Exception:  # noqa: BLE001
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        if self._persistence is not None:
            try:
                self._persistence.flush()
            except Exception:  # noqa: BLE001
                pass
        self._running = False

    def is_running(self) -> bool:
        return self._running and (self._thread is not None and self._thread.is_alive())

    @property
    def adapter(self) -> Any:
        return self._adapter

    def runtime_status(self) -> dict[str, Any]:
        return {
            "running": self.is_running(),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_error": self._last_error,
        }

    def latest(self, instrument_id: str) -> Optional[Tick]:
        return self._state.get(instrument_id)

    def bars(self, instrument_id: str, timeframe: str) -> tuple[Bar, ...]:
        return self._aggregator.bars(instrument_id, timeframe)

    def instruments(self) -> List[Instrument]:
        return list(self._catalog)

    def coverage(self) -> CoverageHealth:
        computed_at = datetime.now(timezone.utc)
        latest = self._state.snapshot()
        catalog_total = len(self._catalog)
        streamable_total = len(
            [i for i in self._catalog if i.classification == InstrumentClassification.TRADABLE]
        )
        subscribed_count = len(self._symbols)

        stale_count = 0
        for symbol in self._symbols:
            tick = latest.get(symbol)
            instrument = self._instrument_map.get(symbol)
            if tick is None or instrument is None:
                stale_count += 1
            else:
                freshness = evaluate_freshness(
                    instrument, tick.market_asof, computed_at, self._freshness_thresholds
                )
                if freshness.is_stale:
                    stale_count += 1

        allowance_ok = subscribed_count <= self._max_symbols
        allowance_reason = None
        if self._fallback:
            allowance_reason = "ranked fallback active"
        elif not allowance_ok:
            allowance_reason = "subscription cap"

        if not self._running:
            mode = CoverageMode.STALE
        elif self._started_at is not None and (
            computed_at - self._started_at < timedelta(seconds=self._warming_seconds)
        ):
            mode = CoverageMode.WARMING
        elif subscribed_count == 0:
            mode = CoverageMode.STALE
        elif stale_count >= subscribed_count:
            mode = CoverageMode.STALE
        elif self._fallback:
            mode = CoverageMode.DEGRADED_RANKED
        elif subscribed_count == streamable_total and stale_count == 0:
            mode = CoverageMode.FULL
        else:
            mode = CoverageMode.DEGRADED_RANKED

        return CoverageHealth(
            mode=mode,
            catalog_total=catalog_total,
            streamable_total=streamable_total,
            subscribed_count=subscribed_count,
            stale_count=stale_count,
            allowance_ok=allowance_ok,
            allowance_reason=allowance_reason,
            computed_at=computed_at,
        )
