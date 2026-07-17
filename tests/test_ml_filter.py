from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml_filter.features import FEATURE_COLUMNS, compute_feature_frame
from ml_filter.candidate_logger import COST_BUFFER, extract_candidates, tag_window
from ml_filter.train_xgb import prune_features, select_threshold, walk_forward_folds

ROOT = Path(__file__).resolve().parents[1]


def _synthetic_frame(n: int = 300, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-02 09:30", periods=n, freq="h")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    volume = rng.integers(1_000, 50_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx
    )


# ---------------------------------------------------------------------------
# Features: causal (truncation-invariant) and complete.
# ---------------------------------------------------------------------------


def test_feature_frame_has_all_columns_and_symbol_onehot():
    frame = _synthetic_frame()
    features = compute_feature_frame(frame, symbol="TSLA.US")
    assert list(features.columns) == FEATURE_COLUMNS
    assert features["sym_TSLA"].iloc[-1] == 1.0
    assert features["sym_SPY"].iloc[-1] == 0.0


def test_feature_frame_is_truncation_invariant_no_lookahead():
    frame = _synthetic_frame(300)
    full = compute_feature_frame(frame, symbol="MU.US")
    truncated = compute_feature_frame(frame.iloc[:210], symbol="MU.US")
    t = 200
    pd.testing.assert_series_equal(full.iloc[t], truncated.iloc[t], check_names=False)


def test_feature_frame_spy_regime_neutral_when_absent():
    frame = _synthetic_frame(100)
    features = compute_feature_frame(frame, symbol="QQQ.US", spy_close=None)
    assert (features["spy_regime"] == 0.5).all()


# ---------------------------------------------------------------------------
# Candidate extraction: fills, labels, fail-closed drops.
# ---------------------------------------------------------------------------


def _flat_features(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(0.1, index=frame.index, columns=FEATURE_COLUMNS)


def test_extract_candidates_uses_next_open_fills_and_rule_exit():
    frame = _synthetic_frame(12, seed=1)
    frame["open"] = np.arange(100.0, 112.0)  # deterministic opens
    weights = pd.Series(0.0, index=frame.index)
    weights.iloc[2:5] = 0.4  # entry at bar 2, exit bar 5 (first flat bar)
    rows = extract_candidates(weights, frame, _flat_features(frame), symbol="TSLA.US")
    assert len(rows) == 1
    row = rows[0]
    assert row["entry_fill"] == pytest.approx(103.0)  # open[3]
    assert row["exit_fill"] == pytest.approx(106.0)   # open[6]
    expected = 106.0 / 103.0 - 1.0 - COST_BUFFER
    assert row["realized_return"] == pytest.approx(expected)
    assert row["label"] == 1
    assert row["holding_bars"] == 3


def test_extract_candidates_losing_trade_labeled_zero():
    frame = _synthetic_frame(12, seed=1)
    frame["open"] = np.arange(112.0, 100.0, -1.0)  # falling opens
    weights = pd.Series(0.0, index=frame.index)
    weights.iloc[2:5] = 0.4
    rows = extract_candidates(weights, frame, _flat_features(frame), symbol="TSLA.US")
    assert len(rows) == 1
    assert rows[0]["label"] == 0
    assert rows[0]["realized_return"] < 0


def test_extract_candidates_drops_open_ended_trades():
    frame = _synthetic_frame(12, seed=1)
    weights = pd.Series(0.0, index=frame.index)
    weights.iloc[8:] = 0.4  # never exits inside the data
    rows = extract_candidates(weights, frame, _flat_features(frame), symbol="MU.US")
    assert rows == []


def test_extract_candidates_drops_rows_with_nan_features():
    frame = _synthetic_frame(12, seed=1)
    weights = pd.Series(0.0, index=frame.index)
    weights.iloc[2:5] = 0.4
    features = _flat_features(frame)
    features.iloc[2, 0] = np.nan  # entry bar has incomplete features
    rows = extract_candidates(weights, frame, features, symbol="MU.US")
    assert rows == []


def test_tag_window_respects_locked_boundaries():
    contract = {
        "train_window": ["2024-08-01", "2025-08-01"],
        "locked_holdout_window": ["2025-08-01", "2026-07-11"],
    }
    assert tag_window("2024-08-01T10:30:00", contract) == "train"
    assert tag_window("2025-07-31T15:30:00", contract) == "train"
    assert tag_window("2025-08-01T09:30:00", contract) == "holdout"
    assert tag_window("2026-07-11T15:30:00", contract) == "holdout"
    assert tag_window("2024-07-31T15:30:00", contract) == "other"


# ---------------------------------------------------------------------------
# Trainer plumbing: strictly time-ordered folds, validation-only threshold.
# ---------------------------------------------------------------------------


def test_walk_forward_folds_are_time_ordered_and_disjoint():
    folds = walk_forward_folds(100, n_folds=4)
    assert folds
    for train_idx, val_idx in folds:
        assert train_idx.max() < val_idx.min()  # never trains on the future
        assert len(np.intersect1d(train_idx, val_idx)) == 0
    # Expanding windows: each fold trains on at least as much as the last.
    sizes = [len(t) for t, _ in folds]
    assert sizes == sorted(sizes)


def test_walk_forward_folds_degrade_gracefully_on_small_n():
    folds = walk_forward_folds(45, n_folds=4)
    for train_idx, val_idx in folds:
        assert len(train_idx) >= 10
        assert len(val_idx) >= 5


def test_select_threshold_prefers_profitable_high_confidence_bucket():
    rng = np.random.default_rng(5)
    n = 200
    p_win = rng.uniform(0.3, 0.9, n)
    realized = np.where(p_win >= 0.6, 0.03, -0.01) + rng.normal(0, 0.001, n)
    pooled = pd.DataFrame(
        {"p_win": p_win, "realized_return": realized, "label": (realized > 0).astype(int)}
    )
    best = select_threshold(pooled)
    assert best["threshold"] >= 0.55
    assert best["accepted_mean_r"] > 0.02


def test_select_threshold_fails_soft_when_too_few_accepted():
    pooled = pd.DataFrame({"p_win": [0.9] * 5, "realized_return": [0.1] * 5, "label": [1] * 5})
    best = select_threshold(pooled)
    assert best["threshold"] == 0.5
    assert "note" in best


def test_prune_features_keeps_top_nonzero():
    shap = {"a": 0.5, "b": 0.2, "c": 0.0, "d": 0.1, "e": 0.05}
    assert prune_features(shap, keep_top=3) == ["a", "b", "d"]


# ---------------------------------------------------------------------------
# v88 engine: segment scaling is a pure, importable function.
# ---------------------------------------------------------------------------


def _load_v88_module():
    path = ROOT / "models" / "poc_va_macdha" / "v88_xgb_filter" / "signal_engine.py"
    spec = importlib.util.spec_from_file_location("v88_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scale_segments_halves_low_score_entries_only():
    v88 = _load_v88_module()
    idx = pd.date_range("2025-01-02", periods=10, freq="h")
    weights = pd.Series([0, 0.4, 0.4, 0, 0, 0.3, 0.3, 0.3, 0, 0], index=idx, dtype=float)
    scaled = v88.scale_segments(
        weights, {1: 0.9, 5: 0.4}, threshold=0.7, low_scale=0.5
    )
    assert scaled.iloc[1] == pytest.approx(0.4)   # high score: untouched
    assert scaled.iloc[2] == pytest.approx(0.4)
    assert scaled.iloc[5] == pytest.approx(0.15)  # low score: 0.5x whole segment
    assert scaled.iloc[7] == pytest.approx(0.15)
    assert scaled.iloc[0] == 0.0 and scaled.iloc[3] == 0.0


def test_scale_segments_unscored_entries_keep_full_weight():
    v88 = _load_v88_module()
    idx = pd.date_range("2025-01-02", periods=6, freq="h")
    weights = pd.Series([0, 0.4, 0.4, 0, 0, 0], index=idx, dtype=float)
    scaled = v88.scale_segments(weights, {}, threshold=0.7, low_scale=0.5)
    pd.testing.assert_series_equal(scaled, weights)


def test_scale_segments_never_creates_entries():
    v88 = _load_v88_module()
    idx = pd.date_range("2025-01-02", periods=6, freq="h")
    weights = pd.Series(0.0, index=idx)
    scaled = v88.scale_segments(weights, {2: 0.99}, threshold=0.7, low_scale=0.5)
    assert (scaled == 0.0).all()


# ---------------------------------------------------------------------------
# Frozen research bundle sanity (exists in-repo; research-only markers).
# ---------------------------------------------------------------------------


def test_filter_meta_declares_research_only_and_train_window_fit():
    import json

    meta_path = ROOT / "models" / "poc_va_macdha" / "v88_xgb_filter" / "filter_meta.json"
    if not meta_path.exists():
        pytest.skip("filter bundle not trained in this checkout")
    meta = json.loads(meta_path.read_text())
    assert meta["status"] == "research_only_not_promoted"
    assert meta["train_window_only"] is True
    assert 0.0 < meta["threshold"] < 1.0
    assert len(meta["features"]) >= 3
