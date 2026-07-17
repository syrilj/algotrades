"""v81_high_confidence_boost: v72 book with a v70 precision size-up overlay.

The v72 dual-sleeve remains the primary side and exit authority.  The v70
high-quality mean-reversion sleeve may only raise an already-active v72 target
to a configured floor.  It cannot create a new trade, reverse direction, or
exceed the v72 per-symbol cap.

``last_confidence`` remains available to the desk.  A 0.90 value identifies a
v70-qualified entry/holding episode; it is a research target supported by thin
historical evidence, not a guarantee.  ``last_high_confidence`` makes that
distinction explicit for consumers that do not want to infer it from a float.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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
    defaults = {
        "base_model": "v72_dual_sleeve",
        "precision_model": "v70_high_confidence_wr",
        "precision_target_weight": 0.45,
        "max_weight": 0.50,
        "high_confidence_target": 0.90,
        "allow_precision_orphans": False,
        "selection_rule": "train_only_then_locked_holdout",
        "train_window_end": "2025-08-01",
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
    """Return v72 targets, raising only v70-qualified active positions."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._hunt = _load_hunt(self_dir)
        self._target = float(self._hunt.get("precision_target_weight", 0.45))
        self._max_weight = float(self._hunt.get("max_weight", 0.50))
        self._high_conf = float(self._hunt.get("high_confidence_target", 0.90))
        self._allow_orphans = bool(self._hunt.get("allow_precision_orphans", False))

        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_high_confidence: Dict[str, pd.Series] = {}
        self.last_sleeve: Dict[str, pd.Series] = {}

        self._base: Optional[Any] = None
        self._precision: Optional[Any] = None
        try:
            self._base = _load_engine(
                repo_root,
                str(self._hunt.get("base_model", "v72_dual_sleeve")),
                "v81_base",
            )
        except Exception as exc:
            print(f"[v81] warning: base engine failed: {exc}")
        try:
            self._precision = _load_engine(
                repo_root,
                str(self._hunt.get("precision_model", "v70_high_confidence_wr")),
                "v81_precision",
            )
        except Exception as exc:
            print(f"[v81] warning: precision engine failed: {exc}")

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        if self._base is None:
            return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}

        try:
            base_map = self._base.generate(data_map)
        except Exception as exc:
            print(f"[v81] warning: base generate failed: {exc}")
            base_map = {}

        precision_map: Dict[str, pd.Series] = {}
        if self._precision is not None:
            try:
                precision_map = self._precision.generate(data_map)
            except Exception as exc:
                print(f"[v81] warning: precision generate failed: {exc}")

        raw_conf = getattr(self._base, "last_confidence", None) or {}
        raw_sleeve = getattr(self._base, "last_sleeve", None) or {}
        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        self.last_high_confidence = {}
        self.last_sleeve = {}

        target = float(np.clip(self._target, 0.0, self._max_weight))
        max_weight = max(0.0, self._max_weight)
        high_conf = float(np.clip(self._high_conf, 0.0, 1.0))

        for code, df in data_map.items():
            idx = df.index
            base = base_map.get(code)
            if base is None or base.empty:
                base = pd.Series(0.0, index=idx)
            base = base.reindex(idx).fillna(0.0).astype(float).clip(-max_weight, max_weight)

            precision = precision_map.get(code)
            if precision is None or precision.empty:
                precision = pd.Series(0.0, index=idx)
            precision = precision.reindex(idx).fillna(0.0).astype(float)

            precision_on = precision > 1e-9
            base_on = base > 1e-9
            qualified = precision_on & (base_on | self._allow_orphans)

            weight = base.copy()
            if self._allow_orphans:
                weight = weight.where(~qualified, np.maximum(weight, target))
            else:
                boost = qualified & base_on
                weight = weight.where(~boost, np.maximum(weight, target))
            weight = weight.clip(-max_weight, max_weight)

            conf = raw_conf.get(code) if isinstance(raw_conf, dict) else None
            if conf is None or getattr(conf, "empty", True):
                conf = pd.Series(0.0, index=idx)
            conf = conf.reindex(idx).fillna(0.0).astype(float).clip(0.0, 1.0)
            conf = conf.where(~qualified, np.maximum(conf, high_conf))

            sleeve = raw_sleeve.get(code) if isinstance(raw_sleeve, dict) else None
            if sleeve is None or getattr(sleeve, "empty", True):
                sleeve = pd.Series(0, index=idx, dtype=int)
            sleeve = sleeve.reindex(idx).fillna(0).astype(int)

            out[code] = weight.astype(float)
            self.last_confidence[code] = conf.astype(float)
            self.last_high_confidence[code] = qualified.astype(bool)
            self.last_sleeve[code] = sleeve

        return out
