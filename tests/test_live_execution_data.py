import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "services"))

import gamma_exposure  # noqa: E402
import live_plan  # noqa: E402
import services.market_runtime as market_runtime  # noqa: E402


class _RecordingClient:
    def __init__(self):
        self.starts: list[str] = []

    def candles(self, symbol, interval, *, start, limit):
        self.starts.append(start)
        freq = "h" if interval == "1h" else "D"
        timestamps = pd.date_range("2026-07-10", periods=30, freq=freq, tz="UTC")
        return [
            {
                "timestamp": ts.isoformat(),
                "open": 28.0,
                "high": 29.0,
                "low": 27.5,
                "close": 28.5,
                "volume": 1000,
            }
            for ts in timestamps
        ]


class _Adapter:
    def __init__(self):
        self.client = _RecordingClient()


def test_lse_candle_requests_use_calendar_dates():
    adapter = _Adapter()

    intraday = live_plan._intraday_df_lse(adapter, "APLD")
    daily = live_plan._daily_close_lse(adapter, "APLD")

    assert intraday is not None and not intraday.empty
    assert not daily.empty
    assert adapter.client.starts
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) for start in adapter.client.starts)


def test_standard_gex_is_dollars_per_one_percent_move():
    value = gamma_exposure._gex_per_one_percent(
        gamma=0.2,
        contracts=10,
        spot=25.0,
    )

    assert value == 1250.0


def test_standard_gex_vectorizes_across_an_option_chain():
    values = gamma_exposure._gex_per_one_percent(
        gamma=pd.Series([0.2, 0.1]),
        contracts=pd.Series([10, 20]),
        spot=25.0,
    )

    assert values.tolist() == [1250.0, 1250.0]


def test_option_underlying_price_must_agree_with_trusted_spot():
    result = gamma_exposure._price_consistency(
        trusted_spot=28.80,
        option_spot=36.37,
        max_divergence_pct=5.0,
    )

    assert result["consistent"] is False
    assert result["divergence_pct"] > 25


def test_gamma_spot_uses_latest_available_lse_candle(monkeypatch):
    rows = [
        {"timestamp": "2026-07-10T18:00:00Z", "close": 27.0},
        {"timestamp": "2026-07-10T19:00:00Z", "close": 28.0},
        {"timestamp": "2026-07-10T20:00:00Z", "close": 29.0},
    ]

    class FakeClient:
        def candles(self, symbol, interval, *, start, limit):
            return rows[:limit]

    class FakeAdapter:
        def __init__(self, api_key=None):
            self.client = FakeClient()

    monkeypatch.setenv("LSE_API_KEY", "test")
    monkeypatch.setattr(market_runtime, "LSEAdapter", FakeAdapter)

    spot, error = gamma_exposure._get_spot_lse("APLD")

    assert error is None
    assert spot == 29.0
