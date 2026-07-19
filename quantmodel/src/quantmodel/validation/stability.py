"""Parameter stability helpers."""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Any, Mapping

from quantmodel.backtest.engine import run_backtest


def small_parameter_grid() -> list[dict[str, Any]]:
    entries = [40, 55, 70]
    exits = [10, 20, 30]
    vols = [1.2, 1.5, 2.0]
    atrs = [1.5, 2.0, 2.5]
    # Keep grid small for demo: sample corners + defaults
    combos = [
        {"entry_lookback": 55, "exit_lookback": 20, "volume_multiple": 1.5, "atr_multiple": 2.0},
        {"entry_lookback": 40, "exit_lookback": 10, "volume_multiple": 1.2, "atr_multiple": 1.5},
        {"entry_lookback": 70, "exit_lookback": 30, "volume_multiple": 2.0, "atr_multiple": 2.5},
        {"entry_lookback": 55, "exit_lookback": 20, "volume_multiple": 2.0, "atr_multiple": 2.0},
        {"entry_lookback": 40, "exit_lookback": 20, "volume_multiple": 1.5, "atr_multiple": 2.5},
    ]
    return combos


def run_stability_sweep(
    base_config: Mapping[str, Any],
    *,
    experiment_base: int = 0,
) -> list[dict[str, Any]]:
    results = []
    exp = experiment_base
    for params in small_parameter_grid():
        exp += 1
        cfg = deepcopy(dict(base_config))
        cfg["signal"] = dict(cfg["signal"])
        cfg["risk"] = dict(cfg["risk"])
        cfg["run"] = dict(cfg["run"])
        cfg["signal"]["entry_lookback"] = params["entry_lookback"]
        cfg["signal"]["exit_lookback"] = params["exit_lookback"]
        cfg["signal"]["volume_multiple"] = params["volume_multiple"]
        cfg["risk"]["atr_multiple"] = params["atr_multiple"]
        cfg["run"]["name"] = (
            f"{base_config['run']['name']}_e{params['entry_lookback']}"
            f"_x{params['exit_lookback']}_v{params['volume_multiple']}_a{params['atr_multiple']}"
        )
        try:
            res = run_backtest(cfg, experiment_number=exp, notes="stability_sweep")
            results.append(
                {
                    **params,
                    "sharpe": res["metrics"].get("sharpe"),
                    "cagr": res["metrics"].get("cagr"),
                    "max_drawdown": res["metrics"].get("max_drawdown"),
                    "run_id": res["run_id"],
                    "experiment_number": exp,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({**params, "error": str(exc), "experiment_number": exp})
    return results
