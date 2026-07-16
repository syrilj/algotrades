"""v72b_trump_risk_soft: live-adapt teacher + soft size scale + crypto corridor.

Pipeline B (soft scale — distinct sensors/policy from v72 hard)
--------------------------------------------------------------
Teacher: v39b_live_adapt (live-oriented adaptive engine).
Risk: composite score with higher weight on vol + optional COIN/MSTR
crypto-proxy drawdown gated by rolling corr to SPY.
Continuous size mult in [size_floor, 1] — never a pure binary stand-aside,
so partial risk-off remains possible in elevated regimes.
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
    local = self_dir / "risk_features.py"
    if local.exists():
        return _load_module(local, "v72b_risk_features")
    shared = repo_root / "models" / "poc_va_macdha" / "_shared" / "drawdown_risk.py"
    return _load_module(shared, "v72b_drawdown_risk")


def _load_teacher(repo_root: Path, name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Teacher {name} missing at {path}")
    return _load_module(path, f"v72b_teacher_{name}").SignalEngine()


def _ensure_drawdown_risk_vendored(self_dir: Path, repo_root: Path) -> None:
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
        base = self._risk.default_params("soft")
        if hunt_path.exists():
            try:
                overrides = json.loads(hunt_path.read_text(encoding="utf-8"))
                if isinstance(overrides, dict):
                    base.update(overrides)
            except json.JSONDecodeError:
                pass
        self._params = base
        teacher_name = str(self._params.get("teacher", "v39b_live_adapt"))
        self._teacher = _load_teacher(repo_root, teacher_name)
        self.last_risk_score: pd.Series | None = None
        self.last_size_mult: pd.Series | None = None

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        base_sigs = self._teacher.generate(data_map)
        score = self._risk.score_from_data_map(data_map, self._params)
        mult = self._risk.size_multiplier(
            score,
            mode="soft",
            elevated_threshold=float(self._params.get("elevated_threshold", 0.50)),
            size_floor=float(self._params.get("size_floor", 0.15)),
            soft_power=float(self._params.get("soft_power", 1.25)),
        )
        self.last_risk_score = score
        self.last_size_mult = mult
        return self._risk.apply_size_mult(base_sigs, mult)
