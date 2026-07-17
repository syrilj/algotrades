import unittest

import httpx

from services.market_runtime.vault_client import LSEVaultClient, LSEVaultError


class VaultClientTests(unittest.TestCase):
    def test_sends_key_query_and_reports_metered_bytes(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["request"] = request
            return httpx.Response(
                200,
                json=[{"symbol": "AAPL", "close": 200.0}],
                headers={"X-Data-Bytes": "321"},
            )

        transport = httpx.MockTransport(handler)
        http = httpx.Client(transport=transport)
        client = LSEVaultClient(
            "lse_live_test",
            base_url="https://vault.test/vault",
            client=http,
        )

        result = client.candles(symbol="AAPL", timeframe="1h", limit=10)

        self.assertEqual(result.data[0]["close"], 200.0)
        self.assertEqual(result.data_bytes, 321)
        request = seen["request"]
        self.assertEqual(request.headers["x-api-key"], "lse_live_test")
        self.assertEqual(request.url.path, "/vault/candles")
        self.assertEqual(request.url.params["symbol"], "AAPL")
        self.assertEqual(request.url.params["timeframe"], "1h")

    def test_retries_rate_limit_and_respects_retry_after(self):
        calls = 0
        sleeps = []

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    429,
                    json={"detail": "rate limit"},
                    headers={"Retry-After": "0.01"},
                )
            return httpx.Response(200, json={"calls_per_minute": 100})

        client = LSEVaultClient(
            "lse_live_test",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=sleeps.append,
        )

        result = client.usage()

        self.assertEqual(result.data["calls_per_minute"], 100)
        self.assertEqual(calls, 2)
        self.assertEqual(sleeps, [0.01])

    def test_surfaces_provider_detail_without_retrying_client_error(self):
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(403, json={"detail": "key expired"})

        client = LSEVaultClient(
            "lse_live_test",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaises(LSEVaultError) as ctx:
            client.meta()

        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(ctx.exception.detail, "key expired")
        self.assertEqual(calls, 1)

    def test_missing_key_fails_before_network_call(self):
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        client = LSEVaultClient(
            None,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        with self.assertRaises(LSEVaultError) as ctx:
            client.catalog()

        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(calls, 0)

    def test_rejects_unknown_reference_dataset_locally(self):
        client = LSEVaultClient(
            "lse_live_test",
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, json=[])
                )
            ),
        )

        with self.assertRaises(LSEVaultError) as ctx:
            client.reference_rows("../../secret")

        self.assertEqual(ctx.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
