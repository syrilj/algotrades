"""DSR unit tests."""

from __future__ import annotations

from quantmodel.validation.deflated_sharpe import (
    deflated_sharpe_probability,
    expected_max_sharpe,
)


def test_expected_max_sharpe_increases_with_trials() -> None:
    assert expected_max_sharpe(1) == 0.0
    assert expected_max_sharpe(10) > expected_max_sharpe(2)


def test_dsr_high_sharpe_few_trials() -> None:
    p = deflated_sharpe_probability(observed_sr=2.0, n_obs=500, n_trials=1, skew=0.0, kurtosis=3.0)
    assert p > 0.9


def test_dsr_penalizes_many_trials() -> None:
    p_few = deflated_sharpe_probability(1.0, n_obs=252, n_trials=1)
    p_many = deflated_sharpe_probability(1.0, n_obs=252, n_trials=500)
    assert p_many < p_few
