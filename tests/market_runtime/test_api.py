import time
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from services.market_runtime import StreamSupervisor, Tick, instrument_from_catalog
from services.market_runtime.api import create_app


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


class APITests(unittest.TestCase):
    def setUp(self):
        self.catalog = [instrument_from_catalog("A.L", "A", "stock")]
        tick_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.ticks = [
            Tick(
                instrument_id="A.L",
                price=100.0,
                size=1.0,
                market_asof=tick_time,
                received_at=tick_time,
            ),
        ]
        self.adapter = FakeAdapter(self.catalog, self.ticks)
        self.supervisor = StreamSupervisor(self.adapter, max_symbols=10, warming_seconds=0)
        self.supervisor.start()
        time.sleep(0.1)
        self.client = TestClient(create_app(self.supervisor))

    def tearDown(self):
        self.supervisor.stop()

    def test_health_returns_running_supervisor_state(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["running"])

    def test_coverage_endpoint_returns_mode_and_counts(self):
        res = self.client.get("/coverage")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["mode"], "FULL")
        self.assertEqual(body["catalog_total"], 1)
        self.assertEqual(body["streamable_total"], 1)

    def test_instruments_list_and_tick_lookup(self):
        res = self.client.get("/instruments")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["instruments"]), 1)

        res = self.client.get("/ticks/A.L")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["price"], 100.0)

        res = self.client.get("/ticks/MISSING")
        self.assertEqual(res.status_code, 404)

    def test_bars_endpoint_returns_aggregated_bars(self):
        res = self.client.get("/bars/A.L?timeframe=1m")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["bars"]), 1)
        self.assertEqual(body["bars"][0]["close"], 100.0)

    def test_opportunities_endpoint_returns_empty_list_when_none_set(self):
        res = self.client.get("/opportunities")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["opportunities"], [])
