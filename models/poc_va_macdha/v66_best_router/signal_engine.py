"""v66_best_router — competitive best-model router engine.

For each symbol, scores specialist DNA vs standard bag models (v39d, v39b, …)
via tools.model_registry.route_best_model, then emits the winning engine's
signal series.

This is the desk's meta-model: the best model is the one that routes to the
best model.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists() and (p / "tools").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_engine(repo_root: Path, model_name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"engine missing: {model_name}")
    module_name = f"v66_child_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    # Unique module key so multiple children coexist.
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[arg-type]
    return mod.SignalEngine()


class SignalEngine:
    """Route each symbol to the best child model, then generate."""

    def __init__(self) -> None:
        self_dir = Path(__file__).resolve().parent
        self._repo = _find_repo_root(self_dir)
        tools = str(self._repo / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)

        hunt_path = self_dir / "hunt_config.json"
        self._hunt: Dict[str, Any] = {}
        if hunt_path.exists():
            try:
                self._hunt = json.loads(hunt_path.read_text(encoding="utf-8"))
            except Exception:
                self._hunt = {}

        self._engine_cache: Dict[str, Any] = {}
        self._last_routes: Dict[str, Any] = {}

    def last_routes(self) -> Dict[str, Any]:
        return dict(self._last_routes)

    def _child(self, model_name: str) -> Any:
        if model_name not in self._engine_cache:
            self._engine_cache[model_name] = _load_engine(self._repo, model_name)
        return self._engine_cache[model_name]

    def _select(self, code: str) -> Dict[str, Any]:
        import model_registry as mr  # noqa: WPS433 — runtime path

        return mr.route_best_model(code, desk_only=True)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        out: Dict[str, pd.Series] = {}
        self._last_routes = {}

        # Group symbols by chosen model to call each child once.
        by_model: Dict[str, Dict[str, pd.DataFrame]] = {}
        picks: Dict[str, Dict[str, Any]] = {}
        for code, df in data_map.items():
            try:
                pick = self._select(code)
            except Exception as exc:
                pick = {
                    "model": "v39d_confluence",
                    "reason": f"router error: {exc}",
                    "source": "best_router_fallback",
                }
            model = str(pick.get("model") or "v39d_confluence")
            picks[code] = pick
            by_model.setdefault(model, {})[code] = df

        for model, subset in by_model.items():
            try:
                eng = self._child(model)
                child_out = eng.generate(subset)
            except Exception as exc:
                print(f"[v66_best_router] child {model} failed: {exc}")
                child_out = {
                    c: pd.Series(0.0, index=df.index) for c, df in subset.items()
                }
            for code, sig in child_out.items():
                out[code] = sig

        # Ensure every input code has a series.
        for code, df in data_map.items():
            if code not in out:
                out[code] = pd.Series(0.0, index=df.index)
            self._last_routes[code] = {
                "model": picks.get(code, {}).get("model"),
                "score": picks.get(code, {}).get("score"),
                "track": picks.get(code, {}).get("track"),
                "reason": picks.get(code, {}).get("reason"),
                "candidates": picks.get(code, {}).get("candidates"),
            }
        return out
