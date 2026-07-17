from __future__ import annotations

import json
import math

import numpy as np
import pytest

from tools.deflated_sharpe import (
    _norm_cdf,
    _norm_ppf,
    build_report,
    deflated_sharpe_ratio,
    discover_trial_population,
    expected_max_sharpe,
    load_holdout_defaults,
    probabilistic_sharpe_ratio,
    skew_kurtosis,
)


def test_norm_ppf_is_inverse_of_norm_cdf():
    for p in (0.001, 0.01, 0.25, 0.5, 0.75, 0.99, 0.999):
        x = _norm_ppf(p)
        assert _norm_cdf(x) == pytest.approx(p, abs=1e-6)


def test_norm_ppf_rejects_out_of_range():
    with pytest.raises(ValueError):
        _norm_ppf(0.0)
    with pytest.raises(ValueError):
        _norm_ppf(1.0)


def test_skew_kurtosis_gaussian_default_on_short_series():
    assert skew_kurtosis([1.0, 2.0]) == (0.0, 3.0)


def test_skew_kurtosis_zero_variance_falls_back_to_gaussian():
    assert skew_kurtosis([1.0, 1.0, 1.0, 1.0]) == (0.0, 3.0)


def test_skew_kurtosis_recovers_normal_moments_on_large_sample():
    rng = np.random.default_rng(42)
    x = rng.normal(0.0, 1.0, size=20000)
    skew, kurt = skew_kurtosis(x.tolist())
    assert skew == pytest.approx(0.0, abs=0.1)
    assert kurt == pytest.approx(3.0, abs=0.2)


def test_probabilistic_sharpe_ratio_higher_sharpe_is_more_probable():
    low = probabilistic_sharpe_ratio(0.5, 0.0, n=100)
    high = probabilistic_sharpe_ratio(2.0, 0.0, n=100)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_probabilistic_sharpe_ratio_more_observations_increase_confidence():
    few = probabilistic_sharpe_ratio(1.0, 0.0, n=10)
    many = probabilistic_sharpe_ratio(1.0, 0.0, n=1000)
    assert many > few


def test_probabilistic_sharpe_ratio_insufficient_observations_is_nan():
    assert math.isnan(probabilistic_sharpe_ratio(1.0, 0.0, n=1))


def test_expected_max_sharpe_grows_with_trial_count():
    rng = np.random.default_rng(7)
    trials = rng.normal(0.0, 1.0, size=500).tolist()
    small = expected_max_sharpe(trials, n_trials=5)
    large = expected_max_sharpe(trials, n_trials=500)
    assert large > small > 0.0


def test_expected_max_sharpe_zero_when_population_too_small():
    assert expected_max_sharpe([0.4], n_trials=1) == 0.0
    assert expected_max_sharpe([], n_trials=0) == 0.0


def test_expected_max_sharpe_zero_when_dispersion_is_zero():
    assert expected_max_sharpe([1.0, 1.0, 1.0], n_trials=3) == 0.0


# ---------------------------------------------------------------------------
# Synthetic acceptance cases required by the task: high Sharpe + huge trial
# count must fail; modest trials + strong Sharpe must pass.
# ---------------------------------------------------------------------------


def test_dsr_fails_with_high_sharpe_but_huge_trial_count():
    rng = np.random.default_rng(1)
    trial_sharpes = rng.normal(0.0, 1.0, size=5000).tolist()
    # A Sharpe of 1.2 over 40 trades looks decent in isolation, but is
    # unremarkable after 5000 independent trials with sigma_sr=1.
    stats = deflated_sharpe_ratio(1.2, n=40, trial_sharpes=trial_sharpes, n_trials=5000)
    assert stats["dsr"] < 0.95
    assert stats["expected_max_sharpe"] > 1.2


def test_dsr_passes_with_modest_trials_and_strong_sharpe():
    rng = np.random.default_rng(2)
    trial_sharpes = rng.normal(0.0, 0.25, size=4).tolist()
    # A Sharpe of 3.0 over 200 trades against only 5 low-dispersion trials
    # should clear the 0.95 pass bar comfortably.
    stats = deflated_sharpe_ratio(3.0, n=200, trial_sharpes=trial_sharpes, n_trials=5)
    assert stats["dsr"] >= 0.95
    assert stats["expected_max_sharpe"] < 3.0


def test_dsr_never_exceeds_psr_because_expected_max_sharpe_is_nonneg():
    rng = np.random.default_rng(3)
    trial_sharpes = rng.normal(0.0, 0.5, size=50).tolist()
    stats = deflated_sharpe_ratio(1.5, n=80, trial_sharpes=trial_sharpes, n_trials=50)
    assert stats["dsr"] <= stats["psr"] + 1e-9


def test_deflated_sharpe_ratio_reports_expected_keys():
    stats = deflated_sharpe_ratio(1.5, n=80, trial_sharpes=[0.1, 0.2, -0.1, 0.3], n_trials=4)
    for key in ("dsr", "psr", "expected_max_sharpe", "n_trials", "n_observations", "skew", "kurtosis"):
        assert key in stats


# ---------------------------------------------------------------------------
# Trial-population discovery against the real repo tree.
# ---------------------------------------------------------------------------


def test_discover_trial_population_counts_real_repo_tree():
    population = discover_trial_population()
    # There are >100 v* directories under models/poc_va_macdha plus the
    # leaderboard; this is a sanity floor, not a pinned exact count, so the
    # test survives future model additions.
    assert population["n_trials"] >= 100
    assert population["n_with_sharpe"] <= population["n_trials"]
    assert population["n_with_sharpe"] > 0
    assert "v72_dual_sleeve" in population["trial_ids"]


def test_load_holdout_defaults_reads_real_state_json():
    holdout = load_holdout_defaults()
    assert holdout["available"] is True
    assert holdout["n"] == 84
    assert holdout["sharpe"] == pytest.approx(2.1988207636383037)


def test_load_holdout_defaults_missing_file_fails_closed(tmp_path):
    holdout = load_holdout_defaults(state_path=tmp_path / "missing.json")
    assert holdout["available"] is False


def test_load_holdout_defaults_missing_model_fails_closed(tmp_path):
    state_path = tmp_path / "STATE.json"
    state_path.write_text(json.dumps({"results": {"some_other_model": {"oos": {"sharpe": 1.0, "n": 10}}}}))
    holdout = load_holdout_defaults(state_path=state_path, model="v72_dual_sleeve")
    assert holdout["available"] is False
    assert holdout["reason"] == "model_not_in_state"


# ---------------------------------------------------------------------------
# End-to-end report.
# ---------------------------------------------------------------------------


def test_build_report_with_explicit_inputs_bypasses_state_file():
    report = build_report(sharpe=3.0, n=200, trials_override=5, returns=None)
    assert report["inputs"]["observed_sharpe"] == 3.0
    assert report["inputs"]["n_observations"] == 200
    assert report["inputs"]["n_trials"] == 5
    assert report["verdict"] in ("pass", "fail")
    assert report["pass_bar"] == pytest.approx(0.95)


def test_build_report_uses_real_holdout_when_sharpe_and_n_omitted():
    report = build_report()
    assert report["inputs"]["observed_sharpe"] == pytest.approx(2.1988207636383037)
    assert report["inputs"]["n_observations"] == 84
    assert report["holdout_evidence"]["available"] is True


def test_build_report_skew_kurtosis_from_returns():
    rng = np.random.default_rng(11)
    returns = rng.normal(0.01, 0.02, size=200).tolist()
    report = build_report(sharpe=1.5, n=80, trials_override=10, returns=returns)
    assert report["inputs"]["returns_provided"] == 200
    assert report["inputs"]["moments_source"] == "trade_returns"
