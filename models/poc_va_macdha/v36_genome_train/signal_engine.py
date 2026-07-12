"""Train-loop wrapper: primary SIDE from base; genome scales secondary risk/filters."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Dict

import pandas as pd


class SignalEngine:
    """Secondary control only — does not invent long/short side."""

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        here = Path(__file__).resolve().parent
        base_path = here / "_base_engine.py"
        spec = importlib.util.spec_from_file_location("_train_base_engine", base_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        raw = mod.SignalEngine().generate(data_map)
        gpath = here / "GENOME.json"
        g = {}
        if gpath.exists():
            g = json.loads(gpath.read_text())
        risk = float(g.get("risk_pct", 0.10) or 0.10)
        min_conf = float(g.get("min_confidence", 0.55) or 0.55)
        # min_confidence 0.35..0.85 → zero weak |signal| up to ~0.35
        thr = max(0.0, (min_conf - 0.35) / 0.50) * 0.35
        scale = max(0.20, min(2.5, risk / 0.10))
        out: Dict[str, pd.Series] = {}
        for code, series in raw.items():
            s = series.astype(float) * scale
            if thr > 0:
                s = s.where(s.abs() >= thr, 0.0)
            out[code] = s
        return out
