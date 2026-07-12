"""v30_flip_tsla_mstr — TSLA/MSTR preset of v30_flip_any."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List


def _load_any_cls():
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "v30_flip_any" / "signal_engine.py",
        here.parents[3] / "models" / "poc_va_macdha" / "v30_flip_any" / "signal_engine.py",
        Path("/Users/syriljacob/Desktop/TradingAlgoWork/models/poc_va_macdha/v30_flip_any/signal_engine.py"),
    ]
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("v30_flip_any_se", p)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            return mod.SignalEngine
    raise FileNotFoundError("v30_flip_any not found")


class SignalEngine:
    def __init__(self):
        # Force universe to TSLA/MSTR for this preset without rewriting files.
        Eng = _load_any_cls()
        self._inner = Eng()
        self._inner.allow_codes = {"TSLA.US", "MSTR.US", "TSLA", "MSTR"}

    def generate(self, data_map: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self._inner.generate(data_map)
