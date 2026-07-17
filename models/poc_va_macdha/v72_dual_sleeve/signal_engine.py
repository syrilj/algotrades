"""v72_dual_sleeve: hierarchical live book — v71 high-WR sniper + v39d core.

Design (pre-registered, anti-blend)
-----------------------------------
Naive averaging of teachers has repeatedly underperformed the best teacher.
v72 does **not** average signals. It uses a hierarchical portfolio merge:

1. **Sniper first** — if `v71_live_confidence` is long, take that weight
   (already confidence-sized, high win-rate mean-rev path).
2. **Core fill** — else take a scaled `v39d_confluence` weight (return champion).
3. **Both fire** — take sniper full + a fraction of core, hard-capped
   (no runaway leverage).
4. **Portfolio cap** — per-symbol target weight ≤ `max_weight`.

Confidence for live desk:
- Prefer sniper entry confidence when sniper is active.
- Else map core size into a soft confidence band.
- Exposed via `last_confidence` and `last_sleeve` for trade-desk / live_plan.

Parameters live in hunt_config.json; freeze before OOS.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_base_engine(repo_root: Path, model_name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Base engine {model_name} not found at {path}")
    module_name = f"v72_base_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_hunt(self_dir: Path) -> Dict[str, Any]:
    defaults = {
        "sniper_model": "v71_live_confidence",
        "core_model": "v39d_confluence",
        "core_scale": 0.85,
        "both_core_frac": 0.35,
        "max_weight": 0.50,
        "sniper_min_conf": 0.0,
        "selection_rule": "frozen_before_oos_eval",
        "train_window_end": "2025-08-01",
    }
    hunt_path = self_dir / "hunt_config.json"
    if hunt_path.exists():
        try:
            overrides = json.loads(hunt_path.read_text(encoding="utf-8"))
            if isinstance(overrides, dict):
                defaults.update(overrides)
        except json.JSONDecodeError:
            pass
    return defaults


class SignalEngine:
    """Hierarchical dual-sleeve portfolio engine for live equity."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        self._hunt = _load_hunt(self_dir)

        self._sniper_name = str(self._hunt.get("sniper_model", "v71_live_confidence"))
        self._core_name = str(self._hunt.get("core_model", "v39d_confluence"))
        self._core_scale = float(self._hunt.get("core_scale", 0.85))
        self._both_core_frac = float(self._hunt.get("both_core_frac", 0.35))
        self._max_weight = float(self._hunt.get("max_weight", 0.50))
        self._sniper_min_conf = float(self._hunt.get("sniper_min_conf", 0.0))

        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_sleeve: Dict[str, pd.Series] = {}  # 0=flat, 1=sniper, 2=core, 3=both

        self._sniper: Optional[Any] = None
        self._core: Optional[Any] = None
        try:
            self._sniper = _load_base_engine(repo_root, self._sniper_name)
        except Exception as exc:
            print(f"[v72] warning: sniper {self._sniper_name} failed: {exc}")
        try:
            self._core = _load_base_engine(repo_root, self._core_name)
        except Exception as exc:
            print(f"[v72] warning: core {self._core_name} failed: {exc}")

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        if self._sniper is None and self._core is None:
            return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}

        sniper_sigs: Dict[str, pd.Series] = {}
        core_sigs: Dict[str, pd.Series] = {}
        sniper_conf: Dict[str, pd.Series] = {}

        if self._sniper is not None:
            try:
                sniper_sigs = self._sniper.generate(data_map)
                raw = getattr(self._sniper, "last_confidence", None) or {}
                if isinstance(raw, dict):
                    sniper_conf = raw
            except Exception as exp:
                print(f"[v72] warning: sniper generate failed: {exp}")
                sniper_sigs = {}

        if self._core is not None:
            try:
                core_sigs = self._core.generate(data_map)
            except Exception as exp:
                print(f"[v72] warning: core generate failed: {exp}")
                core_sigs = {}

        out: Dict[str, pd.Series] = {}
        self.last_confidence = {}
        self.last_sleeve = {}
        cap = self._max_weight
        core_scale = self._core_scale
        both_frac = self._both_core_frac
        min_conf = self._sniper_min_conf

        for code, df in data_map.items():
            if df is None or df.empty:
                out[code] = pd.Series(0.0, index=pd.DatetimeIndex([]))
                continue
            idx = df.index

            sn = sniper_sigs.get(code)
            if sn is None or (hasattr(sn, "empty") and sn.empty):
                sn = pd.Series(0.0, index=idx)
            sn = sn.reindex(idx).fillna(0.0).astype(float)

            co = core_sigs.get(code)
            if co is None or (hasattr(co, "empty") and co.empty):
                co = pd.Series(0.0, index=idx)
            co = co.reindex(idx).fillna(0.0).astype(float)

            sc = sniper_conf.get(code)
            if sc is None or (hasattr(sc, "empty") and sc.empty):
                # Fallback: infer conf from sniper size vs typical base 0.225
                sc = (sn / 0.225).clip(0.0, 1.0)
            sc = sc.reindex(idx).fillna(0.0).astype(float)

            # Vectorized hierarchical merge
            sniper_on = (sn > 1e-9) & (sc >= min_conf)
            core_on = co > 1e-9

            both = sniper_on & core_on
            sniper_only = sniper_on & ~core_on
            core_only = core_on & ~sniper_on

            weight = pd.Series(0.0, index=idx)
            conf = pd.Series(0.0, index=idx)
            sleeve = pd.Series(0, index=idx, dtype=int)

            # sniper only
            weight = weight.where(~sniper_only, sn.clip(upper=cap))
            conf = conf.where(~sniper_only, sc.clip(0.0, 1.0))
            sleeve = sleeve.where(~sniper_only, 1)

            # core only
            core_w = (co * core_scale).clip(upper=cap)
            # soft conf from core size intensity
            core_conf = (0.45 + 0.45 * (co.clip(0.0, 1.0))).clip(0.35, 0.92)
            weight = weight.where(~core_only, core_w)
            conf = conf.where(~core_only, core_conf)
            sleeve = sleeve.where(~core_only, 2)

            # both: sniper full + fractional core, cap
            stacked = (sn + both_frac * co * core_scale).clip(upper=cap)
            both_conf = (0.55 * sc + 0.45 * core_conf).clip(0.40, 0.95)
            weight = weight.where(~both, stacked)
            conf = conf.where(~both, both_conf)
            sleeve = sleeve.where(~both, 3)

            # flat remains 0
            out[code] = weight.astype(float)
            self.last_confidence[code] = conf.astype(float)
            self.last_sleeve[code] = sleeve.astype(int)

        return out
