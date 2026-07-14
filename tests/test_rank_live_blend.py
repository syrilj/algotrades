import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import model_registry  # noqa: E402
import paper_ledger  # noqa: E402


# ---------------------------------------------------------------------------
# _live_factor unit tests
# ---------------------------------------------------------------------------

def test_live_factor_below_min_n_returns_neutral():
    assert model_registry._live_factor(5, 0.5) == 1.0


def test_live_factor_none_avg_r_returns_neutral_even_at_high_n():
    assert model_registry._live_factor(50, None) == 1.0


def test_live_factor_positive_r_at_threshold():
    assert model_registry._live_factor(10, 0.4) == pytest.approx(1.10)


def test_live_factor_clamps_extreme_negative_r():
    assert model_registry._live_factor(10, -2.0) == pytest.approx(0.85)


def test_live_factor_clamps_extreme_positive_r():
    assert model_registry._live_factor(10, 2.0) == pytest.approx(1.15)


def test_live_factor_gated_just_below_threshold():
    assert model_registry._live_factor(9, 0.6) == 1.0


# ---------------------------------------------------------------------------
# rank_models() integration -- live blend
# ---------------------------------------------------------------------------

_FIXTURE_CARDS = [
    {
        "model": "model_a",
        "has_engine": True,
        "source": "TEST",
        "portfolio": {
            "win_rate": 0.50,
            "sharpe": 1.0,
            "profit_factor": 1.4,
            "max_drawdown": 0.10,
            "total_return": 0.20,
            "trade_count": 40,
        },
        "per_symbol": {},
    },
    {
        "model": "model_b",
        "has_engine": True,
        "source": "TEST",
        "portfolio": {
            "win_rate": 0.52,
            "sharpe": 1.0,
            "profit_factor": 1.4,
            "max_drawdown": 0.10,
            "total_return": 0.22,
            "trade_count": 40,
        },
        "per_symbol": {},
    },
]


def _fixture_compute_stats(symbol=None, model=None):
    # Two per-(model,symbol) buckets for model_a only; model_b has no live trades.
    # Deliberately different per-bucket avg_R (0.6 and -0.2) so a naive average
    # of the two bucket averages (0.2) would be WRONG -- the correct
    # trade-weighted avg_R is sum_R / n = 8.0 / 20 = 0.4.
    return {
        "rows": [
            {
                "model": "model_a", "symbol": "AAPL.US",
                "n": 15, "wins": 10, "losses": 5,
                "total_pnl": 900.0, "sum_R": 9.0,
                "live_wr": 10 / 15, "avg_R": 0.6,
                "last_close_ts": "2026-07-01T00:00:00Z",
            },
            {
                "model": "model_a", "symbol": "MSFT.US",
                "n": 5, "wins": 1, "losses": 4,
                "total_pnl": -150.0, "sum_R": -1.0,
                "live_wr": 1 / 5, "avg_R": -0.2,
                "last_close_ts": "2026-07-02T00:00:00Z",
            },
        ],
        "overall": {
            "n": 20, "wins": 11, "losses": 9,
            "live_wr": 0.55, "total_pnl": 750.0,
            "avg_R": 0.4, "sum_R": 8.0,
        },
        "asof": "2026-07-02T00:00:00Z",
    }


def test_rank_models_blends_live_and_sorts_by_blended_score(monkeypatch):
    monkeypatch.setattr(model_registry, "all_model_cards", lambda engines_only=False: _FIXTURE_CARDS)
    monkeypatch.setattr(paper_ledger, "compute_stats", _fixture_compute_stats)

    ranked = model_registry.rank_models()
    by_model = {r["model"]: r for r in ranked}

    a, b = by_model["model_a"], by_model["model_b"]

    expected_score_a = round(model_registry.score_metrics(0.50, 1.0, 1.4, 0.10), 4)
    expected_score_b = round(model_registry.score_metrics(0.52, 1.0, 1.4, 0.10), 4)
    assert a["score"] == expected_score_a
    assert b["score"] == expected_score_b
    # Sanity: on raw backtest score alone, B would outrank A.
    assert expected_score_b > expected_score_a

    # model_a live aggregate must be trade-weighted across its two symbol
    # buckets, not a naive mean of the two buckets' avg_R values.
    assert a["live_n"] == 20
    assert a["live_wr"] == pytest.approx(11 / 20)
    assert a["live_avg_R"] == pytest.approx(0.4)
    assert a["live_pnl"] == pytest.approx(750.0)
    assert a["live_status"] == "confirming"

    expected_factor_a = model_registry._live_factor(20, 0.4)
    expected_blended_a = round(expected_score_a * expected_factor_a, 4)
    assert a["blended_score"] == expected_blended_a

    # model_b has no live trades at all -- fields default, blended == score.
    assert b["live_n"] == 0
    assert b["live_wr"] is None
    assert b["live_avg_R"] is None
    assert b["live_pnl"] is None
    assert b["live_status"] == "none"
    assert b["blended_score"] == expected_score_b

    # The live blend flips the ranking: model_a's live outperformance
    # (bounded, capped) pushes it above model_b despite the lower backtest score.
    assert ranked[0]["model"] == "model_a"
    assert ranked[1]["model"] == "model_b"
    assert [r["rank"] for r in ranked] == [1, 2]


def test_rank_models_defaults_when_compute_stats_raises(monkeypatch):
    """A missing/corrupt ledger (or a paper_ledger import failure) must never
    crash ranking -- all live fields degrade to their neutral defaults."""
    monkeypatch.setattr(model_registry, "all_model_cards", lambda engines_only=False: _FIXTURE_CARDS)

    def _boom(*args, **kwargs):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(paper_ledger, "compute_stats", _boom)

    ranked = model_registry.rank_models()
    assert len(ranked) == 2
    for r in ranked:
        assert r["live_n"] == 0
        assert r["live_wr"] is None
        assert r["live_avg_R"] is None
        assert r["live_pnl"] is None
        assert r["live_status"] == "none"
        assert r["blended_score"] == r["score"]
