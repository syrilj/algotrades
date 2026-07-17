import time
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from services.market_runtime import StreamSupervisor, Tick, instrument_from_catalog
from services.market_runtime.api import create_app
from services.market_runtime.vault_client import LSEVaultError, VaultResult


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


class FakeVaultClient:
    def __init__(self):
        self.calls = []

    def close(self):
        pass

    def usage(self):
        return VaultResult({"calls_per_minute": 100, "max_rows_per_request": 5000})

    def reference_rows(self, dataset, **params):
        self.calls.append((dataset, params))
        if dataset == "unsupported":
            raise LSEVaultError(400, "unsupported reference dataset")
        return VaultResult(
            [{"datetime": "2026-07-29T14:00:00-04:00", "event": "FOMC"}],
            data_bytes=144,
        )

    def options_flow(self, **params):
        self.calls.append(("options_flow", params))
        return VaultResult([{"underlying": "TSLA", "premium": 250000}], 72)


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
        self.vault = FakeVaultClient()
        self.supervisor = StreamSupervisor(self.adapter, max_symbols=10, warming_seconds=0)
        self.supervisor.start()
        time.sleep(0.1)
        self.client = TestClient(create_app(self.supervisor, vault_client=self.vault))

    def tearDown(self):
        self.supervisor.stop()

    def test_health_returns_running_supervisor_state(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["running"])
        self.assertIsNone(body["last_error"])

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

    def test_vault_usage_is_available_without_exposing_api_key(self):
        res = self.client.get("/data/usage")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["calls_per_minute"], 100)
        self.assertEqual(body["meta"]["source"], "lse_vault")

    def test_economic_calendar_forwards_safe_filters_and_metering(self):
        res = self.client.get(
            "/data/reference/economic_calendar"
            "?region=US&event=cpi&order=asc&limit=20"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["data"][0]["event"], "FOMC")
        self.assertEqual(body["meta"]["data_bytes"], 144)
        dataset, params = self.vault.calls[-1]
        self.assertEqual(dataset, "economic_calendar")
        self.assertEqual(params["region"], "US")
        self.assertEqual(params["event"], "cpi")
        self.assertEqual(params["limit"], 20)

    def test_options_flow_endpoint_forwards_documented_filters(self):
        res = self.client.get(
            "/data/options/flow?underlying=TSLA&min_premium=100000&max_dte=7&limit=50"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["data"][0]["underlying"], "TSLA")
        _name, params = self.vault.calls[-1]
        self.assertEqual(params["min_premium"], 100000.0)
        self.assertEqual(params["max_dte"], 7)
        self.assertEqual(params["limit"], 50)

    def test_plan_degrades_only_in_development_when_stream_is_stopped(self):
        """Development keeps its diagnostic fallback; production does not."""
        import os
        from unittest.mock import patch

        self.supervisor.stop()
        self.assertEqual(self.client.get("/health").json()["status"], "degraded")

        fake_plan = {
            "ok": True,
            "symbol": "SPY",
            "action": "WAIT",
            "ticket": {"max_loss_dollars": 10.0},
        }
        with patch("live_plan.plan_symbol", return_value=fake_plan):
            res = self.client.post("/plan", json={"symbol": "SPY", "account": 1000, "no_model": True})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("action"), "WAIT")
        self.assertFalse(body.get("runtime", {}).get("stream_ready"))
        self.assertEqual(body.get("runtime", {}).get("data_path"), "development_fallback")

    def test_production_plan_fails_closed_even_if_override_disables_stream(self):
        import os

        self.supervisor.stop()
        with unittest.mock.patch.dict(
            os.environ,
            {"MARKET_RUNTIME_ENV": "production", "MARKET_RUNTIME_REQUIRE_STREAM": "0"},
        ):
            res = self.client.post("/plan", json={"symbol": "A.L"})
        self.assertEqual(res.status_code, 503)
        self.assertIn("market stream not ready", res.json()["detail"])

    def test_plan_fails_closed_when_require_stream_set(self):
        import os

        self.supervisor.stop()
        prev = os.environ.get("MARKET_RUNTIME_REQUIRE_STREAM")
        os.environ["MARKET_RUNTIME_REQUIRE_STREAM"] = "1"
        try:
            res = self.client.post("/plan", json={"symbol": "A.L"})
            self.assertEqual(res.status_code, 503)
            self.assertIn("market stream not ready", res.json()["detail"])
        finally:
            if prev is None:
                os.environ.pop("MARKET_RUNTIME_REQUIRE_STREAM", None)
            else:
                os.environ["MARKET_RUNTIME_REQUIRE_STREAM"] = prev

    def test_analyze_endpoint_returns_structured_report(self):
        from unittest.mock import patch

        fake = {
            "ok": True,
            "symbol": "TSLA",
            "report": {
                "facts": {},
                "decision": {"action": "WAIT"},
                "suggestion": {},
            },
        }
        with patch("analysis_agent.run_analysis", return_value=fake), patch(
            "analysis_agent._sanitize_nan", side_effect=lambda x: x
        ):
            res = self.client.post("/analyze", json={"symbol": "TSLA", "account": 1000})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("ok"))
        self.assertIn("report", body)
        self.assertIn("runtime", body)
