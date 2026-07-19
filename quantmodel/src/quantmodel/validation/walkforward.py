"""Anchored walk-forward validation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from quantmodel.backtest.engine import run_backtest


@dataclass
class WalkForwardFold:
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    is_sharpe: float
    oos_sharpe: float
    oos_total_return: float
    run_id_oos: str


def anchored_folds(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    initial_train_years: int,
    test_years: int,
    step_years: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Return list of (train_start, train_end, test_start, test_end)."""
    folds = []
    train_end = start + pd.DateOffset(years=initial_train_years) - pd.Timedelta(days=1)
    while True:
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.DateOffset(years=test_years) - pd.Timedelta(days=1)
        if test_start > end:
            break
        if test_end > end:
            test_end = end
        if test_start >= test_end:
            break
        folds.append((start, train_end, test_start, test_end))
        train_end = train_end + pd.DateOffset(years=step_years)
        if train_end >= end:
            break
    return folds


def run_walkforward(
    config: Mapping[str, Any],
    *,
    experiment_base: int = 0,
) -> dict[str, Any]:
    """
    Run anchored walk-forward on fixed config (no IS param search in v1 base).
    Parameter search can wrap this later; each fold still counts as experiment.
    """
    from quantmodel.data.loader import load_market_data

    data = load_market_data(config, run_id="wf_probe")
    bars = data["bars"]
    if bars.empty:
        return {"folds": [], "error": "no_data"}
    start = pd.Timestamp(bars["date"].min())
    end = pd.Timestamp(bars["date"].max())
    wf = config["validation"]["walkforward"]
    fold_defs = anchored_folds(
        start,
        end,
        initial_train_years=int(wf.get("initial_train_years", 2)),
        test_years=int(wf.get("test_years", 1)),
        step_years=int(wf.get("step_years", 1)),
    )
    results: list[WalkForwardFold] = []
    exp_n = experiment_base
    for i, (ts, te, xs, xe) in enumerate(fold_defs, start=1):
        exp_n += 1
        # IS
        cfg_is = deepcopy(dict(config))
        cfg_is["data"] = dict(cfg_is["data"])
        cfg_is["data"]["start_date"] = ts.strftime("%Y-%m-%d")
        cfg_is["data"]["end_date"] = te.strftime("%Y-%m-%d")
        cfg_is["run"] = dict(cfg_is["run"])
        cfg_is["run"]["name"] = f"{config['run']['name']}_wf{i}_is"
        try:
            is_res = run_backtest(cfg_is, experiment_number=exp_n, notes=f"walkforward fold {i} IS")
            is_sharpe = float(is_res["metrics"].get("sharpe", 0.0))
        except Exception:
            is_sharpe = 0.0

        exp_n += 1
        cfg_oos = deepcopy(dict(config))
        cfg_oos["data"] = dict(cfg_oos["data"])
        # include warmup history before test for indicators
        warm = xs - pd.DateOffset(days=400)
        cfg_oos["data"]["start_date"] = max(start, warm).strftime("%Y-%m-%d")
        cfg_oos["data"]["end_date"] = xe.strftime("%Y-%m-%d")
        cfg_oos["run"] = dict(cfg_oos["run"])
        cfg_oos["run"]["name"] = f"{config['run']['name']}_wf{i}_oos"
        oos_res = run_backtest(cfg_oos, experiment_number=exp_n, notes=f"walkforward fold {i} OOS")
        oos_m = oos_res["metrics"]
        results.append(
            WalkForwardFold(
                fold=i,
                train_start=ts.strftime("%Y-%m-%d"),
                train_end=te.strftime("%Y-%m-%d"),
                test_start=xs.strftime("%Y-%m-%d"),
                test_end=xe.strftime("%Y-%m-%d"),
                is_sharpe=is_sharpe,
                oos_sharpe=float(oos_m.get("sharpe", 0.0)),
                oos_total_return=float(oos_m.get("total_return", 0.0)),
                run_id_oos=str(oos_res["run_id"]),
            )
        )

    if not results:
        return {"folds": [], "oos_sharpe_mean": 0.0, "is_sharpe_mean": 0.0, "oos_is_ratio": 0.0}

    oos_mean = sum(f.oos_sharpe for f in results) / len(results)
    is_mean = sum(f.is_sharpe for f in results) / len(results)
    ratio = oos_mean / is_mean if is_mean != 0 else 0.0
    return {
        "folds": [f.__dict__ for f in results],
        "oos_sharpe_mean": oos_mean,
        "is_sharpe_mean": is_mean,
        "oos_is_ratio": ratio,
        "n_folds": len(results),
        "experiments_used": exp_n - experiment_base,
    }
