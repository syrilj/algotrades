"""v82_frequent_confidence: two-tier 1H swing routing.

The model increases opportunity through universe breadth while preserving two
different entry standards:

* liquid core: v71 soft confidence sizing for more frequent swing entries;
* volatile satellites: v70's stricter quality gate;
* bond ETFs: flat, because the equity mean-reversion teacher is not intended
  for their return process.

``last_confidence`` is an *ordinal rank score*, not a calibrated probability.
Consumers must inspect ``confidence_kind`` and ``last_strict_tier`` rather
than interpreting 0.75 as a 75% chance of winning.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set

import numpy as np
import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_engine(repo_root: Path, model_name: str, prefix: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Base engine {model_name} not found at {path}")
    module_name = f"{prefix}_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_hunt(self_dir: Path) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "balanced_model": "v71_live_confidence",
        "strict_model": "v70_high_confidence_wr",
        "balanced_symbols": [
            "SPY.US", "QQQ.US", "XLP.US", "MU.US", "NVDA.US", "TSLA.US"
        ],
        "excluded_symbols": ["HYG.US", "LQD.US"],
        "strict_rank_score": 0.75,
        "max_weight": 0.35,
        "confidence_kind": "uncalibrated_ordinal_rank_not_probability",
    }
    path = self_dir / "hunt_config.json"
    if path.exists():
        try:
            overrides = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(overrides, dict):
                defaults.update(overrides)
        except json.JSONDecodeError:
            pass
    return defaults


class SignalEngine:
    """Route core symbols to v71 and satellites to the stricter v70 gate."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._hunt = _load_hunt(self_dir)

        self._balanced_symbols: Set[str] = {
            str(x).upper() for x in self._hunt.get("balanced_symbols", [])
        }
        self._excluded_symbols: Set[str] = {
            str(x).upper() for x in self._hunt.get("excluded_symbols", [])
        }
        self._strict_rank_score = float(self._hunt.get("strict_rank_score", 0.75))
        self._max_weight = float(self._hunt.get("max_weight", 0.35))
        self.confidence_kind = str(
            self._hunt.get("confidence_kind", "uncalibrated_ordinal_rank_not_probability")
        )

        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_tier: Dict[str, pd.Series] = {}  # 0=flat/excluded, 1=core, 2=strict satellite
        self.last_strict_tier: Dict[str, pd.Series] = {}

        self._balanced: Optional[Any] = None
        self._strict: Optional[Any] = None
        try:
            self._balanced = _load_engine(
                repo_root,
                str(self._hunt.get("balanced_model", "v71_live_confidence")),
                "v82_balanced",
            )
        except Exception as exc:
            print(f"[v82] warning: balanced engine failed: {exc}")
        try:
            self._strict = _load_engine(
                repo_root,
                str(self._hunt.get("strict_model", "v70_high_confidence_wr")),
                "v82_strict",
            )
        except Exception as exc:
            print(f"[v82] warning: strict engine failed: {exc}")

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        balanced_map: Dict[str, pd.Series] = {}
        strict_map: Dict[str, pd.Series] = {}
        if self._balanced is not None:
            try:
                balanced_map = self._balanced.generate(data_map)
            except Exception as exc:
                print(f"[v82] warning: balanced generate failed: {exc}")
        if self._strict is not None:
            try:
                strict_map = self._strict.generate(data_map)
            except Exception as exc:
                print(f"[v82] warning: strict generate failed: {exc}")

        balanced_conf = getattr(self._balanced, "last_confidence", None) or {}
        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        self.last_tier = {}
        self.last_strict_tier = {}

        max_weight = max(0.0, self._max_weight)
        strict_score = float(np.clip(self._strict_rank_score, 0.0, 1.0))
        for code, df in data_map.items():
            idx = df.index
            code_key = str(code).upper()
            zero = pd.Series(0.0, index=idx)

            if code_key in self._excluded_symbols:
                weight = zero
                conf = zero
                tier = pd.Series(0, index=idx, dtype=int)
            elif code_key in self._balanced_symbols:
                raw = balanced_map.get(code)
                weight = zero if raw is None else raw.reindex(idx).fillna(0.0).astype(float)
                raw_conf = balanced_conf.get(code) if isinstance(balanced_conf, dict) else None
                conf = zero if raw_conf is None else raw_conf.reindex(idx).fillna(0.0).astype(float)
                active = weight.abs() > 1e-9
                tier = pd.Series(0, index=idx, dtype=int).where(~active, 1)
            else:
                raw = strict_map.get(code)
                weight = zero if raw is None else raw.reindex(idx).fillna(0.0).astype(float)
                active = weight.abs() > 1e-9
                conf = zero.where(~active, strict_score)
                tier = pd.Series(0, index=idx, dtype=int).where(~active, 2)

            weight = weight.clip(-max_weight, max_weight)
            conf = conf.clip(0.0, 1.0).where(weight.abs() > 1e-9, 0.0)
            strict = tier.eq(2) & (weight.abs() > 1e-9)

            out[code] = weight.astype(float)
            self.last_confidence[code] = conf.astype(float)
            self.last_tier[code] = tier.astype(int)
            self.last_strict_tier[code] = strict.astype(bool)

        return out
