import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.confidence_features import confirmed_pivot_features, ohlcv_effort_features  # noqa: E402
from evolve.confidence_research import make_manifest, validate_manifest  # noqa: E402
from evolve.feature_validation import FEATURE_COLUMNS, _fit_logistic, _predict, attach_entry_features  # noqa: E402


def _ohlcv(n=80):
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = 100 + np.sin(np.arange(n) / 4.0) + np.arange(n) * 0.02
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 1000 + (np.arange(n) % 7) * 25,
        },
        index=idx,
    )


def test_confirmed_pivot_features_do_not_change_when_future_bars_are_appended():
    frame = _ohlcv()
    prefix = frame.iloc[:60]
    before = confirmed_pivot_features(prefix, length=5)
    after = confirmed_pivot_features(frame, length=5).iloc[:60]
    pd.testing.assert_frame_equal(before, after)


def test_ohlcv_effort_features_are_finite_and_have_no_orderflow_claim():
    features = ohlcv_effort_features(_ohlcv())
    assert np.isfinite(features.to_numpy()).all()
    assert "true_delta" not in features.columns
    assert "volume_z" in features.columns


def test_research_manifest_is_locked_and_rejects_unapproved_family():
    manifest = make_manifest(feature_family="confirmed_pivot")
    assert validate_manifest(manifest) == []
    manifest["feature_family"] = "pine_copy"
    assert validate_manifest(manifest)


def test_feature_selector_is_finite_and_uses_only_declared_family():
    frame = _ohlcv(100)
    features = confirmed_pivot_features(frame)
    data = pd.DataFrame(
        {
            "raw_probability": np.linspace(0.45, 0.75, len(frame)),
            "label": (np.arange(len(frame)) % 3 != 0).astype(float),
        },
        index=frame.index,
    )
    data = pd.concat([data, features], axis=1).reset_index(drop=True)
    columns = ["raw_probability", *FEATURE_COLUMNS["confirmed_pivot"]]
    model = _fit_logistic(data, columns)
    prediction = _predict(data, model)
    assert np.isfinite(prediction).all()
    assert set(model["columns"]) == set(columns)


def test_entry_feature_join_is_backward_only(tmp_path):
    bars = _ohlcv(50).copy()
    bars.to_parquet(tmp_path / "TEST.parquet")
    entries = pd.DataFrame(
        {
            "entry_ts": pd.to_datetime([bars.index[25], bars.index[25] + pd.Timedelta(minutes=30)], utc=True),
            "exit_ts": pd.to_datetime([bars.index[26], bars.index[26] + pd.Timedelta(hours=1)], utc=True),
            "code": ["TEST.US", "TEST.US"],
            "raw_probability": [0.6, 0.7],
            "label": [1.0, 0.0],
            "realized_r": [0.02, -0.01],
        }
    )
    joined = attach_entry_features(entries, bar_source=tmp_path, feature_family="confirmed_pivot")
    assert len(joined) == 2
    assert joined["bar_ts"].iloc[0] <= joined["entry_ts"].dt.tz_convert(None).iloc[0]
