from __future__ import annotations

import json

import pandas as pd

from tools.confidence_shadow import ShadowDecisionLedger


def test_settle_due_uses_recorded_price_and_future_daily_bar(tmp_path, monkeypatch):
    ledger = ShadowDecisionLedger(tmp_path / "shadow.jsonl")
    event_id = ledger.record(
        {
            "symbol": "TSLA",
            "model": "v72_dual_sleeve",
            "state": "ENTER",
            "calibrated_probability": 0.7,
            "probability_calibrated": False,
            "reference_price": 100.0,
            "direction": "long",
            "horizon": "day",
            "asof_utc": "2026-01-02T18:00:00+00:00",
        }
    )
    data_dir = tmp_path / "bars"
    data_dir.mkdir()
    (data_dir / "TSLA.parquet").touch()
    frame = pd.DataFrame(
        {"close": [110.0]}, index=pd.to_datetime(["2026-01-05"])
    )
    monkeypatch.setattr(pd, "read_parquet", lambda _path: frame.copy())

    result = ledger.settle_due(data_dir=data_dir, now="2026-01-06T00:00:00Z")

    assert result["settled"] == 1
    row = next(item for item in ledger.read() if item["event_id"] == event_id)
    assert row["outcome"] == 1.0
    assert abs(row["realized_return"] - 0.10) < 1e-9
    assert row["settlement_source"] == "local_adjusted_daily"


def test_settle_due_never_infers_missing_reference_price(tmp_path):
    ledger = ShadowDecisionLedger(tmp_path / "shadow.jsonl")
    ledger.record(
        {
            "symbol": "TSLA",
            "horizon": "day",
            "asof_utc": "2020-01-01T00:00:00Z",
        }
    )
    result = ledger.settle_due(data_dir=tmp_path, now="2026-01-01T00:00:00Z")
    assert result["settled"] == 0
    assert result["skipped"]["missing_reference_price"] == 1


def test_corrupt_tail_does_not_hide_valid_events(tmp_path):
    path = tmp_path / "shadow.jsonl"
    ledger = ShadowDecisionLedger(path)
    ledger.record({"symbol": "SPY", "state": "WATCH"})
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{bad-json\n")
    assert len(ledger.read()) == 1

