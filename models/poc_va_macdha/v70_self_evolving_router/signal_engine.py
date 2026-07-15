"""v70_self_evolving_router — Dynamic self-evolving model selection engine.

For each symbol, dynamically evaluates candidate models causally over a rolling
walk-forward window, selecting the best model bar-by-bar based on recent performance
and regime.
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
        if (p / "models" / "poc_va_macdha").exists() and (p / "tools").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_engine(repo_root: Path, model_name: str) -> Any:
    path = repo_root / "models" / "poc_va_macdha" / model_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"engine missing: {model_name}")
    module_name = f"v70_child_{model_name.replace('.', '_')}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    # Unique module key so multiple children coexist
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[arg-type]
    return mod.SignalEngine()


class SignalEngine:
    """Dynamic model selection and routing engine."""

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

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        import model_registry as mr  # noqa: WPS433 — runtime import

        lookback = int(self._hunt.get("lookback_bars", 60))
        metric = str(self._hunt.get("metric", "composite"))
        switching_penalty = float(self._hunt.get("switching_penalty", 0.02))
        use_specialist = bool(self._hunt.get("use_specialist", True))
        base_models: List[str] = list(self._hunt.get("base_models", ["v39d_confluence", "v39b_live_adapt", "v50_high_win_rate", "v63_spy_prune"]))
        fallback = str(self._hunt.get("fallback", "v39d_confluence"))
        warmup = int(self._hunt.get("warmup", 80))

        out: Dict[str, pd.Series] = {}
        self._last_routes = {}

        for code, df in data_map.items():
            close = df["close"].astype(float)
            idx = df.index
            n_bars = len(idx)

            # Build list of candidate models for this symbol
            symbol_candidates = list(base_models)
            spec_model = None

            if use_specialist:
                spec = mr.desk_specialist_for_symbol(code)
                if spec and spec.get("model"):
                    spec_model = str(spec["model"])
                    if spec_model not in symbol_candidates:
                        symbol_candidates.append(spec_model)

            # Generate signals for all candidates
            signals: Dict[str, np.ndarray] = {}
            for model in symbol_candidates:
                try:
                    eng = self._child(model)
                    # Pass the subset data_map with just this symbol to the child
                    child_out = eng.generate({code: df})
                    signals[model] = child_out[code].reindex(idx).fillna(0.0).to_numpy(dtype=float)
                except Exception as exc:
                    print(f"[v70_self_evolving_router] candidate {model} failed for {code}: {exc}")
                    signals[model] = np.zeros(n_bars, dtype=float)

            # Compute percentage returns causally
            close_arr = close.to_numpy(dtype=float)
            returns = np.zeros(n_bars, dtype=float)
            if n_bars > 1:
                returns[1:] = (close_arr[1:] - close_arr[:-1]) / np.maximum(close_arr[:-1], 1e-12)

            # Track routing decisions and final signal series
            routed_signals = np.zeros(n_bars, dtype=float)
            chosen_models: List[str] = [fallback] * n_bars

            # Warmup period routes to fallback
            if fallback not in signals:
                fallback_active = symbol_candidates[0]
            else:
                fallback_active = fallback

            actual_warmup = min(warmup, n_bars)
            for t in range(actual_warmup):
                chosen_models[t] = fallback_active
                routed_signals[t] = signals[fallback_active][t]

            # Pre-compute realized causal PnL series for each model:
            # PnL realized at t is signal from t-1 * return at t
            realized_pnl: Dict[str, np.ndarray] = {}
            for model in symbol_candidates:
                pnl = np.zeros(n_bars, dtype=float)
                if n_bars > 1:
                    pnl[1:] = signals[model][:-1] * returns[1:]
                realized_pnl[model] = pnl

            # Routing loop
            active_model = fallback_active
            for t in range(actual_warmup, n_bars):
                scores: Dict[str, float] = {}
                for model in symbol_candidates:
                    # Rolling realized PnL window up to bar t-1 (inclusive)
                    start_w = max(0, t - lookback)
                    window_pnl = realized_pnl[model][start_w:t]

                    if len(window_pnl) == 0:
                        score = 0.0
                    else:
                        if metric == "return":
                            score = float(np.sum(window_pnl))
                        elif metric == "sharpe":
                            mean = np.mean(window_pnl)
                            std = np.std(window_pnl)
                            score = float(mean / std * np.sqrt(1764)) if std > 1e-6 else float(mean)
                        elif metric == "win_rate":
                            score = float(np.sum(window_pnl > 0) / len(window_pnl))
                        elif metric == "composite":
                            mean = np.mean(window_pnl)
                            std = np.std(window_pnl)
                            sr = float(mean / std * np.sqrt(1764)) if std > 1e-6 else float(mean)
                            tot_ret = float(np.sum(window_pnl))
                            score = 0.60 * tot_ret + 0.40 * sr
                        else:
                            score = float(np.sum(window_pnl))

                    # Apply model priors
                    if model == spec_model:
                        score += float(self._hunt.get("specialist_bias", 0.005))
                    elif model == "v39d_confluence":
                        score += float(self._hunt.get("standard_bias", 0.002))

                    # Apply switching penalty
                    if model != active_model:
                        score -= switching_penalty

                    scores[model] = score

                best_model = max(scores, key=scores.get)  # type: ignore[arg-type]
                active_model = best_model
                chosen_models[t] = active_model
                routed_signals[t] = signals[active_model][t]

            out[code] = pd.Series(routed_signals, index=idx)

            # Store routes in last_routes
            self._last_routes[code] = {
                "chosen_models": chosen_models,
                "candidates": symbol_candidates,
                "specialist": spec_model,
            }

        return out
