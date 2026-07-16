"""v72_trump_risk_hard: champion teacher + hard stand-aside on elevated swing risk.

Pipeline A (hard gate)
----------------------
Teacher: v39d_confluence (current equity champion).
Risk: composite causal score from SPY drawdown / vol / trend (+ QQQ DD).
When risk_score >= elevated_threshold → size multiplier = 0 (stand aside).
Otherwise identity sizing on teacher targets.

Designed for Trump second-term live window (from 2025-01-20): prioritize
cutting exposure into large multi-day swings over maximizing return.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_module(path: Path, key: str) -> Any:
    name = f"{key}_{id(path)}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load_risk(self_dir: Path, repo_root: Path) -> Any:
    # Prefer local risk_features (and vendored drawdown_risk)
    local = self_dir / "risk_features.py"
    if local.exists():
        return _load_module(local, "v72_risk_features")
    shared = repo_root / "models" / "poc_va_macdha" / "_shared" / "drawdown_risk.py"
    return _load_module(shared, "v72_drawdown_risk")


def _load_teacher(repo_root: Path, name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Teacher {name} missing at {path}")
    return _load_module(path, f"v72_teacher_{name}").SignalEngine()


def _ensure_drawdown_risk_vendored(self_dir: Path, repo_root: Path) -> None:
    """If drawdown_risk.py not next to us, copy from _shared for run isolation."""
    dest = self_dir / "drawdown_risk.py"
    if dest.exists():
        return
    src = repo_root / "models" / "poc_va_macdha" / "_shared" / "drawdown_risk.py"
    if src.exists():
        try:
            shutil.copy2(src, dest)
        except Exception:
            pass


class SignalEngine:
    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        repo_root = _find_repo_root(self_dir)
        _ensure_drawdown_risk_vendored(self_dir, repo_root)
        self._risk = _load_risk(self_dir, repo_root)

        hunt_path = self_dir / "hunt_config.json"
        base = self._risk.default_params("hard")
        if hunt_path.exists():
            try:
                overrides = json.loads(hunt_path.read_text(encoding="utf-8"))
                if isinstance(overrides, dict):
                    base.update(overrides)
            except json.JSONDecodeError:
                pass
        self._params = base
        teacher_name = str(self._params.get("teacher", "v39d_confluence"))
        self._teacher = _load_teacher(repo_root, teacher_name)
        # Live observability
        self.last_risk_score: pd.Series | None = None
        self.last_size_mult: pd.Series | None = None

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        base_sigs = self._teacher.generate(data_map)
        score = self._risk.score_from_data_map(data_map, self._params)
        mult = self._risk.size_multiplier(
            score,
            mode="hard",
            elevated_threshold=float(self._params.get("elevated_threshold", 0.55)),
            size_floor=float(self._params.get("size_floor", 0.0)),
        )
        self.last_risk_score = score
        self.last_size_mult = mult
        return self._risk.apply_size_mult(base_sigs, mult)
