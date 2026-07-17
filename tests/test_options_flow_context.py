"""Causal and fail-closed contracts for Vault options activity snapshots."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import options_flow_context as flow  # noqa: E402


NOW = datetime(2026, 7, 16, 18, 35, tzinfo=timezone.utc)


def _row(ts: str, volume: float, ticker: str = "TSLA260821C00350000", **extra):
    return {"ts": ts, "ticker": ticker, "volume": volume, **extra}


def test_normalizes_utc_timestamp_and_contract_identity():
    context = flow.normalize_options_activity(
        [_row("2026-07-16 18:30:00", 100, ticker=" tsla 260821c00350000 ")],
        now=NOW,
    )

    assert context["ok"] is True
    assert context["rows"][0]["timestamp"] == "2026-07-16T18:30:00Z"
    assert context["rows"][0]["contract_id"] == "TSLA260821C00350000"
    assert context["rows"][0]["underlying"] == "TSLA"
    assert context["rows"][0]["expiry"] == "2026-08-21"
    assert context["rows"][0]["right"] == "C"
    assert context["rows"][0]["strike"] == 350.0


def test_component_contract_normalizes_to_same_osi_id():
    components = {
        "underlying": "tsla.us",
        "expiration_date": "2026-08-21",
        "option_type": "call",
        "strike_price": "350",
    }
    assert flow.normalize_contract_id(components) == "TSLA260821C00350000"
    assert flow.normalize_contract_id("O:TSLA260821C00350000") == "TSLA260821C00350000"
    assert flow.normalize_timestamp(1_784_226_600_000) == "2026-07-16T18:30:00Z"


def test_deduplicates_then_computes_causal_nonnegative_increments():
    rows = [
        _row("2026-07-16T18:31:00Z", 150),
        _row("2026-07-16T18:30:00Z", 100),
        _row("2026-07-16T18:31:00Z", 150),  # duplicate poll
        _row("2026-07-16T18:32:00Z", 140),  # bad/reset counter
        _row("2026-07-16T18:33:00Z", 145),
    ]
    context = flow.normalize_options_activity(rows, now=NOW)

    assert [row["volume_increment"] for row in context["rows"]] == [100, 50, 0, 5]
    assert context["activity"]["total_volume_increment"] == 155
    assert context["data_quality"]["duplicate_rows_removed"] == 1
    assert context["data_quality"]["same_session_volume_decreases"] == 1
    assert context["data_quality"]["status"] == "degraded"
    assert context["ok"] is False
    assert context["signal"]["abstain"] is True


def test_increments_are_isolated_by_contract_and_reset_each_session():
    put = "TSLA260821P00250000"
    context = flow.normalize_options_activity(
        [
            _row("2026-07-15T18:30:00Z", 10),
            _row("2026-07-15T18:31:00Z", 14),
            _row("2026-07-15T18:30:00Z", 7, ticker=put),
            _row("2026-07-16T18:30:00Z", 3),
            _row("2026-07-16T18:30:00Z", 2, ticker=put),
        ],
        now=NOW,
        stale_after=120,
    )

    calls = [row for row in context["rows"] if row["right"] == "C"]
    puts = [row for row in context["rows"] if row["right"] == "P"]
    assert [row["volume_increment"] for row in calls] == [10, 4, 3]
    assert [row["volume_increment"] for row in puts] == [7, 2]
    assert context["activity"]["call_volume_increment"] == 17
    assert context["activity"]["put_volume_increment"] == 9


def test_call_heavy_rows_never_claim_bullish_or_hidden_trade_direction():
    context = flow.normalize_options_activity(
        [
            _row(
                "2026-07-16T18:30:00Z",
                5000,
                aggressor="buy",
                opening=True,
                dealer_side="short",
            ),
            _row("2026-07-16T18:30:00Z", 1, ticker="TSLA260821P00250000"),
        ],
        now=NOW,
    )

    assert context["activity"]["call_share_of_known_type_activity"] > 0.99
    assert context["bias"] == "neutral"
    assert context["bullish_supported"] is False
    assert context["actionable"] is False
    assert context["signal"]["semantic_label"] == "neutral_activity_only_bullish_unsupported"
    assert context["signal"]["action"] == "abstain"
    for row in context["rows"]:
        assert row["aggressor_side"] is None
        assert row["opening_closing"] is None
        assert row["dealer_direction"] is None
        assert row["directionality"] == "unknown"


def test_missing_or_invalid_required_data_fails_closed():
    context = flow.build_options_flow_context(
        [
            {"timestamp": "bad", "ticker": "TSLA", "volume": -1},
            {"timestamp": "2026-07-16T18:30:00Z", "volume": 10},
            "not-a-row",
        ],
        now=NOW,
    )

    assert context["ok"] is False
    assert context["rows"] == []
    assert context["data_quality"]["status"] == "invalid"
    assert context["completeness"]["required_fields_complete"] is False
    assert context["freshness"]["status"] == "unknown"
    assert context["signal"]["direction"] == "neutral"
    assert context["signal"]["abstain"] is True
    assert context["bullish_supported"] is False


def test_empty_and_non_collection_inputs_fail_closed_instead_of_raising():
    for bad_input in (None, {}, "not rows", 42):
        context = flow.normalize_options_flow_context(bad_input, now=NOW)
        assert context["ok"] is False
        assert context["bias"] == "neutral"
        assert context["abstain"] is True
        assert context["data_quality"]["status"] == "invalid"


def test_stale_or_future_data_is_explicit_and_non_actionable():
    stale = flow.normalize_options_activity(
        [_row("2026-07-16T17:00:00Z", 100)],
        now=NOW,
        stale_after=60,
    )
    future = flow.normalize_options_activity(
        [_row("2026-07-16T19:00:00Z", 100)],
        now=NOW,
        future_tolerance=60,
    )

    assert stale["freshness"]["status"] == "stale"
    assert stale["freshness"]["is_stale"] is True
    assert stale["ok"] is False
    assert future["freshness"]["status"] == "future"
    assert future["freshness"]["is_future"] is True
    assert future["signal"]["abstain"] is True


def test_conflicting_same_key_snapshots_are_deduped_and_degraded():
    context = flow.normalize_options_activity(
        [
            _row("2026-07-16T18:30:00Z", 120),
            _row("2026-07-16T18:30:00+00:00", 100),
        ],
        now=NOW,
    )

    assert len(context["rows"]) == 1
    assert context["rows"][0]["cumulative_volume"] == 100
    assert context["data_quality"]["duplicate_rows_removed"] == 1
    assert context["data_quality"]["conflicting_duplicate_keys"] == 1
    assert context["completeness"]["required_fields_complete"] is False
    assert context["signal"]["abstain"] is True


def test_wrapper_payload_is_supported_but_does_not_claim_tape_completeness():
    context = flow.normalize_lse_options_activity(
        {"data": [_row("2026-07-16T18:30:00Z", 100)]},
        now=NOW,
    )

    assert context["data_quality"]["input_rows"] == 1
    assert context["completeness"]["status"] == "complete_required_fields"
    assert context["completeness"]["tape_completeness"] == "unknown"
    assert context["completeness"]["tape_complete"] is None
