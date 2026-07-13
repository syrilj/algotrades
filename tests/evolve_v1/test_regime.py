"""Tests for tools/regime.py and tools/evolve/regime_gate.py."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from tools.evolve import regime_gate


def test_regime_at_returns_t_1_lag(tmp_path: Path):
    df = pd.DataFrame(
        {"score": [0.5, 0.2, -0.4], "label": ["risk_on", "neutral", "risk_off"]},
        index=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
    )
    df.index.name = "date"
    p = tmp_path / "regime.parquet"
    df.to_parquet(p)

    r = regime_gate.regime_at("2025-01-04", p)
    assert r["label"] == "risk_off"
    assert r["score"] == -0.4

    r = regime_gate.regime_at("2025-01-02", p)
    assert r["label"] == "risk_on"

    r = regime_gate.regime_at("2025-01-03", p)
    assert r["label"] == "neutral"


def test_sector_gate(tmp_path: Path):
    df = pd.DataFrame(
        {
            "score": [0.5, 0.5, 0.5],
            "label": ["risk_on", "risk_on", "risk_on"],
            "sector_ok_XLY.US": [True, True, False],
        },
        index=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
    )
    df.index.name = "date"
    p = tmp_path / "regime.parquet"
    df.to_parquet(p)

    g = regime_gate.gate("TSLA.US", "2025-01-04", {"TSLA.US": "XLY.US"}, p)
    assert g["regime"] == "risk_on"
    assert g["sector_ok"] is False
