import time
import unittest
from datetime import datetime, timezone

from services.market_runtime import (
    CoverageMode,
    StreamSupervisor,
    Tick,
    instrument_from_catalog,
)


class FakeAdapter:
    def __init__(self, catalog, ticks):
        self._catalog = catalog
        self._ticks = ticks
        self._symbols = []
        self._disconnected = False

    def catalog(self, category=None):
        return self._catalog

    def stream(self, symbols, start=None):
        self._symbols = list(symbols)
        for t in self._ticks:
            yield t

    def disconnect(self):
        self._disconnected = True


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.catalog = [
            instrument_from_catalog("A.L", "A", "stock"),
            instrument_from_catalog("B.L", "B", "stock"),
            instrument_from_catalog("C.L", "C", "stock"),
            instrument_from_catalog("UK10Y", "UK 10Y", "bonds"),
        ]
        self.ticks = [
            Tick(
                instrument_id="A.L",
                price=100.0,
                size=1.0,
                market_asof=datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc),
                received_at=datetime(2026, 7, 13, 10, 0, 1, tzinfo=timezone.utc),
            ),
            Tick(
                instrument_id="B.L",
                price=200.0,
                size=1.0,
                market_asof=datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc),
                received_at=datetime(2026, 7, 13, 10, 0, 1, tzinfo=timezone.utc),
            ),
            Tick(
                instrument_id="C.L",
                price=300.0,
                size=1.0,
                market_asof=datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc),
                received_at=datetime(2026, 7, 13, 10, 0, 1, tzinfo=timezone.utc),
            ),
        ]

    def test_start_streaming_updates_tick_state_and_bars(self):
        adapter = FakeAdapter(self.catalog, self.ticks)
        supervisor = StreamSupervisor(adapter, max_symbols=10, warming_seconds=0)
        supervisor.start()
        time.sleep(0.1)
        supervisor.stop()
        self.assertEqual(supervisor.latest("A.L").price, 100.0)
        bars = supervisor.bars("A.L", "1m")
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].close, 100.0)

    def test_coverage_full_when_all_tradable_subscribed_and_no_stale(self):
        adapter = FakeAdapter(self.catalog, self.ticks)
        supervisor = StreamSupervisor(adapter, max_symbols=10, warming_seconds=0)
        supervisor.start()
        time.sleep(0.1)
        coverage = supervisor.coverage()
        supervisor.stop()
        self.assertEqual(coverage.mode, CoverageMode.FULL)
        self.assertEqual(coverage.catalog_total, 4)
        self.assertEqual(coverage.streamable_total, 3)
        self.assertEqual(coverage.subscribed_count, 3)
        self.assertEqual(coverage.stale_count, 0)

    def test_ranked_fallback_activates_when_tradable_exceeds_max(self):
        adapter = FakeAdapter(self.catalog, self.ticks)
        supervisor = StreamSupervisor(adapter, max_symbols=2, warming_seconds=0)
        supervisor.start()
        time.sleep(0.1)
        coverage = supervisor.coverage()
        supervisor.stop()
        self.assertEqual(coverage.mode, CoverageMode.DEGRADED_RANKED)
        self.assertEqual(coverage.subscribed_count, 2)
        self.assertEqual(coverage.streamable_total, 3)

    def test_stale_mode_when_no_ticks_received(self):
        adapter = FakeAdapter(self.catalog, [])
        supervisor = StreamSupervisor(adapter, max_symbols=10, warming_seconds=0)
        supervisor.start()
        time.sleep(0.1)
        coverage = supervisor.coverage()
        supervisor.stop()
        self.assertEqual(coverage.mode, CoverageMode.STALE)

    def test_persistence_receives_ticks(self):
        from services.market_runtime import TickPersistence

        persistence = TickPersistence(":memory:")
        adapter = FakeAdapter(self.catalog, self.ticks)
        supervisor = StreamSupervisor(adapter, max_symbols=10, warming_seconds=0, persistence=persistence)
        supervisor.start()
        time.sleep(0.1)
        supervisor.stop()
        persisted = persistence.query("A.L")
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].price, 100.0)
