"""Config load and schema validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantmodel.config import ConfigError, load_config, validate_config
from quantmodel.hashing import hash_config

PACKAGE = Path(__file__).resolve().parents[2]
CONFIGS = PACKAGE / "configs"


def test_base_config_validates() -> None:
    cfg = load_config(CONFIGS / "base.yaml")
    assert cfg["run"]["initial_equity"] == 1_000_000
    assert cfg["signal"]["entry_lookback"] == 55
    assert "_meta" in cfg
    assert len(cfg["_meta"]["config_hash"]) == 64


def test_demo_synthetic_validates() -> None:
    cfg = load_config(CONFIGS / "demo_synthetic.yaml")
    assert cfg["data"]["vendor"] == "synthetic"
    assert cfg["data"]["survivorship_bias"] is False


def test_invalid_config_fails_loudly() -> None:
    bad = {
        "run": {"name": "x", "seed": 1, "initial_equity": -1},
        "data": {"vendor": "not_a_vendor", "benchmark": "SPY", "min_history_days": 1},
        "universe": {
            "min_price": 5,
            "min_median_dollar_volume_20d": 1,
            "max_position_fraction_of_adv": 0.01,
        },
        "signal": {
            "entry_lookback": 55,
            "exit_lookback": 20,
            "trend_sma_days": 200,
            "volume_lookback": 50,
            "volume_multiple": 1.5,
        },
        "risk": {
            "atr_days": 20,
            "atr_multiple": 2.0,
            "risk_per_trade": 0.005,
            "max_portfolio_heat": 0.04,
            "max_positions": 20,
            "kill_switch_drawdown": -0.12,
            "resume_drawdown": -0.08,
        },
        "execution": {
            "signal_to_fill": "next_open",
            "slippage_bps": 5,
            "commission_per_share": 0.005,
        },
        "validation": {"walkforward": {}, "bootstrap": {}, "promotion": {}},
    }
    errors = validate_config(bad)
    assert errors
    # writing to temp path via load would also fail
    assert any("initial_equity" in e or "vendor" in e for e in errors)


def test_kill_switch_resume_semantic() -> None:
    cfg = load_config(CONFIGS / "base.yaml")
    cfg["risk"]["kill_switch_drawdown"] = -0.08
    cfg["risk"]["resume_drawdown"] = -0.12
    errors = validate_config(cfg)
    assert any("resume_drawdown" in e for e in errors)


def test_config_hash_stable() -> None:
    a = load_config(CONFIGS / "base.yaml")
    b = load_config(CONFIGS / "base.yaml")
    ha = hash_config({k: v for k, v in a.items() if k != "_meta"})
    hb = hash_config({k: v for k, v in b.items() if k != "_meta"})
    assert ha == hb


def test_missing_config_raises() -> None:
    with pytest.raises(ConfigError):
        load_config(CONFIGS / "does_not_exist.yaml")
