from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.market_runtime.adaptive_replay import (
    AdaptiveReplayStore,
    replay_latest_decisions,
)


class _FakeAdaptiveEngine:
    bundle_hash = "frozen-bundle-1"
    confidence_kind = "ordinal_online_expert_support_not_probability"

    def generate(self, frames):
        output = {}
        self.last_expert = {}
        self.last_confidence = {}
        self.last_context_quality = {}
        self.last_evidence = {}
        self.last_regime = {}
        for symbol, frame in frames.items():
            signal = pd.Series(0.25 if len(frame) >= 2 else 0.0, index=frame.index)
            output[symbol] = signal
            self.last_expert[symbol] = pd.Series("DUAL", index=frame.index)
            self.last_confidence[symbol] = pd.Series(0.62, index=frame.index)
            self.last_context_quality[symbol] = pd.Series(1.0, index=frame.index)
            self.last_evidence[symbol] = pd.Series(len(frame), index=frame.index)
            self.last_regime[symbol] = pd.Series(1, index=frame.index)
        return output


def _bar(price: float) -> dict[str, float]:
    return {
        "open": price,
        "high": price + 1.0,
        "low": price - 1.0,
        "close": price + 0.5,
        "volume": 1000.0,
    }


def _store(path: Path) -> AdaptiveReplayStore:
    return AdaptiveReplayStore(
        path,
        model="v85_online_contextual",
        bundle_hash="frozen-bundle-1",
        anchor="2026-01-01T00:00:00Z",
    )


def test_completed_bar_ledger_is_exactly_once_and_rejects_conflicts(tmp_path):
    store = _store(tmp_path / "adaptive.db")
    assert store.append_completed_bar(
        "TSLA.US", "2026-01-02T15:30:00Z", _bar(100), source="lse", event_id="a"
    )
    assert not store.append_completed_bar(
        "TSLA.US", "2026-01-02T15:30:00Z", _bar(100), source="lse", event_id="a"
    )
    with pytest.raises(ValueError, match="conflicting duplicate"):
        store.append_completed_bar(
            "TSLA.US", "2026-01-02T15:30:00Z", _bar(101), source="lse", event_id="a"
        )
    with pytest.raises(ValueError, match="incomplete"):
        store.append_completed_bar(
            "TSLA.US", "2026-01-02T16:30:00Z", _bar(101), source="lse", complete=False
        )
    with pytest.raises(ValueError, match="out-of-order"):
        store.append_completed_bar(
            "TSLA.US", "2026-01-02T14:30:00Z", _bar(99), source="lse", event_id="old"
        )


def test_restart_replay_is_idempotent_and_new_bar_creates_one_decision(tmp_path):
    path = tmp_path / "adaptive.db"
    with _store(path) as store:
        for i, price in enumerate((100.0, 101.0, 102.0)):
            store.append_completed_bar(
                "TSLA.US",
                f"2026-01-02T{15 + i:02d}:30:00Z",
                _bar(price),
                source="lse",
                event_id=f"e{i}",
            )
        first = replay_latest_decisions(_FakeAdaptiveEngine(), store, ["TSLA.US"])
        assert first[0]["inserted"] is True
        assert first[0]["target_weight"] == 0.25
        assert "not_probability" in first[0]["confidence_kind"]

    with _store(path) as restarted:
        duplicate = replay_latest_decisions(_FakeAdaptiveEngine(), restarted, ["TSLA.US"])
        assert duplicate[0]["inserted"] is False
        assert len(restarted.decisions("TSLA.US")) == 1
        restarted.append_completed_bar(
            "TSLA.US",
            "2026-01-02T18:30:00Z",
            _bar(103.0),
            source="lse",
            event_id="e3",
        )
        next_decision = replay_latest_decisions(
            _FakeAdaptiveEngine(), restarted, ["TSLA.US"]
        )
        assert next_decision[0]["inserted"] is True
        assert len(restarted.decisions("TSLA.US")) == 2


def test_bundle_mismatch_and_directional_options_claim_fail_closed(tmp_path):
    store = _store(tmp_path / "adaptive.db")
    store.append_completed_bar(
        "TSLA.US", "2026-01-02T15:30:00Z", _bar(100), source="lse"
    )
    wrong = _FakeAdaptiveEngine()
    wrong.bundle_hash = "different"
    with pytest.raises(ValueError, match="bundle hash"):
        replay_latest_decisions(wrong, store, ["TSLA.US"])
    with pytest.raises(ValueError, match="directional options inference"):
        replay_latest_decisions(
            _FakeAdaptiveEngine(),
            store,
            ["TSLA.US"],
            options_context={"TSLA.US": {"actionable": True, "bias": "bullish"}},
        )
