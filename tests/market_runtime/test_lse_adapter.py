import unittest
from datetime import datetime, timezone

from lse import Tick as LSETick

from services.market_runtime import LSEAdapter, Tick


class FakeLSEClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self._disconnected = False

    def catalog(self, category=None):
        return [
            {
                "symbol": "VOD.L",
                "name": "Vodafone Group PLC",
                "category": "Stocks",
                "dataset": "stocks",
                "ticks": 1000,
                "first": "2025-01-01",
                "last": "2026-07-01",
                "country": "UK",
            },
            {
                "symbol": "UK10Y",
                "name": "UK 10Y Gilt",
                "category": "Bonds",
                "dataset": "bonds",
                "ticks": 500,
                "first": "2020-01-01",
                "last": "2026-07-01",
                "country": "UK",
            },
            {
                "symbol": "EURGBP",
                "name": "EUR/GBP",
                "category": "Forex",
                "dataset": "forex",
                "ticks": 2000,
                "first": "2020-01-01",
                "last": "2026-07-01",
                "country": None,
            },
        ]

    def stream(self, symbols, start=None):
        for sym in symbols:
            yield LSETick(symbol=sym, price=100.0, volume=1.0, timestamp="2026-07-13T10:00:00Z")
            yield LSETick(symbol=sym, price=101.0, volume=2.0, timestamp="2026-07-13T10:00:01Z")

    def disconnect(self):
        self._disconnected = True


class LSEAdapterTests(unittest.TestCase):
    def test_catalog_maps_rows_to_instruments(self):
        adapter = LSEAdapter(client_factory=FakeLSEClient)
        instruments = adapter.catalog()
        symbols = {i.symbol: i for i in instruments}
        self.assertEqual(symbols["VOD.L"].category.value, "stock")
        self.assertEqual(symbols["VOD.L"].classification.value, "tradable")
        self.assertEqual(symbols["UK10Y"].classification.value, "context_only")
        self.assertEqual(symbols["EURGBP"].category.value, "fx")
        self.assertEqual(symbols["EURGBP"].classification.value, "tradable")

    def test_stream_converts_lse_ticks_to_contracts(self):
        adapter = LSEAdapter(client_factory=FakeLSEClient)
        ticks = list(adapter.stream(["VOD.L"]))
        self.assertEqual(len(ticks), 2)
        self.assertEqual(ticks[0].instrument_id, "VOD.L")
        self.assertEqual(ticks[0].price, 100.0)
        self.assertEqual(ticks[0].size, 1.0)
        self.assertEqual(
            ticks[0].market_asof,
            datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(ticks[0].event_id, "2026-07-13T10:00:00Z")

    def test_disconnect_closes_client(self):
        adapter = LSEAdapter(client_factory=FakeLSEClient)
        self.assertFalse(adapter.client._disconnected)
        adapter.disconnect()
        self.assertTrue(adapter.client._disconnected)

    def test_adapter_can_be_used_as_context_manager(self):
        with LSEAdapter(client_factory=FakeLSEClient) as adapter:
            instruments = adapter.catalog()
        self.assertEqual(len(instruments), 3)
        self.assertTrue(adapter.client._disconnected)
