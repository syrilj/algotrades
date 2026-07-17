from __future__ import annotations

from tools.model_monitoring import calibration_metrics


def test_calibration_metrics_distinguish_ordinal_scores():
    rows = [
        {"calibrated_probability": 0.8, "outcome": 1.0, "probability_calibrated": False},
        {"calibrated_probability": 0.2, "outcome": 0.0, "probability_calibrated": False},
        {"calibrated_probability": 0.7, "outcome": 1.0, "probability_calibrated": True},
    ]
    metrics = calibration_metrics(rows)
    assert metrics["n"] == 3
    assert metrics["probability_calibrated_n"] == 1
    assert metrics["score_only_n"] == 2
    assert metrics["brier"] < metrics["base_rate_brier"]
    assert metrics["brier_skill"] > 0

