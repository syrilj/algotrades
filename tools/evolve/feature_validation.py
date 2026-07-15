"""Locked out-of-sample validation for causal confidence feature families.

This is a research path, not a live signal path. It joins only the last bar
available at each candidate timestamp, fits a small regularized logistic
selector on the training portion of each chronological fold, and refuses to
produce an active artifact unless the candidate beats the raw probability on
the locked metrics.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from .confidence_features import FEATURE_FAMILIES
    from .calibration import (
        DEFAULT_ENTER,
        _folds,
        bootstrap_mean_lower,
        calibration_metrics,
        load_candidate_files,
    )
except ImportError:  # CLI execution from tools/evolve
    from confidence_features import FEATURE_FAMILIES
    from calibration import (
        DEFAULT_ENTER,
        _folds,
        bootstrap_mean_lower,
        calibration_metrics,
        load_candidate_files,
    )


EPS = 1e-8
FEATURE_COLUMNS = {
    "confirmed_pivot": [
        "pivot_low_confirmed",
        "pivot_high_confirmed",
        "last_pivot_low",
        "last_pivot_high",
        "distance_last_pivot_low_atr",
        "distance_last_pivot_high_atr",
    ],
    "ohlcv_effort": [
        "volume_z",
        "body_to_range",
        "close_location",
        "effort_result",
        "range_pct",
    ],
}


def attach_entry_features(
    candidates: pd.DataFrame,
    *,
    bar_source: str | Path,
    feature_family: str,
    max_lag_hours: int = 2,
) -> pd.DataFrame:
    """Join causal features using the most recent bar at or before entry."""
    if feature_family not in FEATURE_FAMILIES:
        raise ValueError(f"feature_family must be one of {sorted(FEATURE_FAMILIES)}")
    source = Path(bar_source)
    required = {"entry_ts", "code", "exit_ts", "raw_probability", "label", "realized_r"}
    missing = required - set(candidates.columns)
    if missing:
        raise ValueError(f"candidate frame missing columns: {sorted(missing)}")

    feature_fn = FEATURE_FAMILIES[feature_family]
    feature_cols = FEATURE_COLUMNS[feature_family]
    rows: list[dict[str, Any]] = []
    for code, group in candidates.groupby("code", sort=False):
        symbol = str(code).split(".", 1)[0]
        path = source / f"{symbol}.parquet"
        if not path.exists():
            continue
        bars = pd.read_parquet(path).sort_index()
        bar_index = pd.to_datetime(bars.index)
        bars.index = bar_index.tz_convert(None) if bar_index.tz is not None else bar_index
        features = feature_fn(bars)[feature_cols].reset_index(names="bar_ts")
        left = group.sort_values("entry_ts").copy()
        left["join_ts"] = pd.to_datetime(left["entry_ts"], utc=True).dt.tz_convert(None)
        joined = pd.merge_asof(
            left,
            features,
            left_on="join_ts",
            right_on="bar_ts",
            direction="backward",
            tolerance=pd.Timedelta(hours=max_lag_hours),
        )
        rows.extend(joined.to_dict("records"))
    if not rows:
        raise ValueError(f"no candidate timestamps matched bars in {source}")
    out = pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)
    out[feature_cols] = out[feature_cols].replace([np.inf, -np.inf], np.nan)
    return out.dropna(subset=feature_cols).reset_index(drop=True)


def _fit_logistic(train: pd.DataFrame, columns: list[str], l2: float = 0.01) -> dict[str, Any]:
    """Fit a small ridge-logistic model without adding a runtime dependency."""
    x = train[columns].to_numpy(dtype=float)
    y = train["label"].to_numpy(dtype=float)
    mean = np.nanmean(x, axis=0)
    scale = np.nanstd(x, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > EPS), scale, 1.0)
    x = np.nan_to_num((x - mean) / scale, nan=0.0, posinf=0.0, neginf=0.0)
    design = np.column_stack([np.ones(len(x)), x])
    prior = float(np.clip(y.mean(), 1e-4, 1.0 - 1e-4))
    weights = np.zeros(design.shape[1], dtype=float)
    weights[0] = np.log(prior / (1.0 - prior))
    penalty = np.eye(design.shape[1], dtype=float) * float(l2)
    penalty[0, 0] = 1e-8
    for _ in range(100):
        z = np.clip(design @ weights, -30.0, 30.0)
        probability = 1.0 / (1.0 + np.exp(-z))
        gradient = design.T @ (probability - y) + penalty @ weights
        hessian = design.T @ ((probability * (1.0 - probability))[:, None] * design) + penalty
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            break
        weights -= step
        if float(np.max(np.abs(step))) < 1e-7:
            break
    return {"columns": columns, "mean": mean.tolist(), "scale": scale.tolist(), "weights": weights.tolist(), "l2": l2}


def _predict(frame: pd.DataFrame, model: dict[str, Any]) -> np.ndarray:
    x = frame[model["columns"]].to_numpy(dtype=float)
    mean = np.asarray(model["mean"], dtype=float)
    scale = np.asarray(model["scale"], dtype=float)
    weights = np.asarray(model["weights"], dtype=float)
    x = np.nan_to_num((x - mean) / scale, nan=0.0, posinf=0.0, neginf=0.0)
    z = np.clip(np.column_stack([np.ones(len(x)), x]) @ weights, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def evaluate_feature_family(
    frame: pd.DataFrame,
    *,
    feature_family: str,
    n_splits: int = 5,
    embargo_hours: int = 1,
    l2: float = 0.01,
    candidate_sharpe: float | None = None,
    candidate_dd: float | None = None,
    baseline_sharpe: float | None = None,
    baseline_dd: float | None = None,
) -> dict[str, Any]:
    """Evaluate one locked feature family with chronological OOF folds."""
    feature_cols = FEATURE_COLUMNS[feature_family]
    columns = ["raw_probability", *feature_cols]
    folds = _folds(frame.sort_values("entry_ts"), n_splits=n_splits, embargo=pd.Timedelta(hours=embargo_hours).to_pytimedelta())
    if not folds:
        raise ValueError("insufficient feature rows for sequential validation")
    oof: list[pd.DataFrame] = []
    for train, test in folds:
        model = _fit_logistic(train, columns, l2=l2)
        scored = test[["entry_ts", "code", "raw_probability", "label", "realized_r"]].copy()
        scored["candidate_probability"] = _predict(test, model)
        oof.append(scored)
    oof_frame = pd.concat(oof, ignore_index=True)
    raw_metrics = calibration_metrics(oof_frame["label"], oof_frame["raw_probability"])
    candidate_metrics = calibration_metrics(oof_frame["label"], oof_frame["candidate_probability"])
    action = oof_frame[oof_frame["candidate_probability"] >= DEFAULT_ENTER]
    action_lower = bootstrap_mean_lower(action["realized_r"]) if len(action) else None
    promotion = {
        "brier_improves_vs_raw": candidate_metrics["brier"] <= raw_metrics["brier"],
        "log_loss_improves_vs_raw": candidate_metrics["log_loss"] <= raw_metrics["log_loss"],
        "ece_pass": candidate_metrics["ece"] <= 0.05,
        "action_expectancy_pass": action_lower is not None and action_lower > 0.0,
        "oos_count_pass": len(oof_frame) >= 30,
    }
    promotion["all_calibration_gates_pass"] = all(promotion.values())
    portfolio_present = all(value is not None for value in (candidate_sharpe, candidate_dd, baseline_sharpe, baseline_dd))
    sharpe_delta = float(candidate_sharpe) - float(baseline_sharpe) if portfolio_present else None
    drawdown_delta = abs(float(candidate_dd)) - abs(float(baseline_dd)) if portfolio_present else None
    promotion["portfolio"] = {
        "inputs_present": portfolio_present,
        "candidate_sharpe": candidate_sharpe,
        "candidate_dd": candidate_dd,
        "baseline_sharpe": baseline_sharpe,
        "baseline_dd": baseline_dd,
        "sharpe_delta": sharpe_delta,
        "drawdown_delta": drawdown_delta,
        "sharpe_gate": bool(portfolio_present and sharpe_delta >= -0.03),
        "drawdown_gate": bool(portfolio_present and drawdown_delta <= 0.02),
    }
    promotion["all_promotion_gates_pass"] = bool(
        promotion["all_calibration_gates_pass"]
        and promotion["portfolio"]["sharpe_gate"]
        and promotion["portfolio"]["drawdown_gate"]
    )
    final_start = frame["entry_ts"].quantile(0.8)
    final_train = frame[frame["entry_ts"] < final_start]
    final_test = frame[frame["entry_ts"] >= final_start]
    final_model = _fit_logistic(final_train, columns, l2=l2)
    final_probability = _predict(final_test, final_model)
    final_raw_metrics = calibration_metrics(final_test["label"], final_test["raw_probability"])
    final_metrics = calibration_metrics(final_test["label"], final_probability)
    promotion.update(
        {
            "final_brier_improves_vs_raw": final_metrics["brier"] <= final_raw_metrics["brier"],
            "final_log_loss_improves_vs_raw": final_metrics["log_loss"] <= final_raw_metrics["log_loss"],
            "final_ece_pass": final_metrics["ece"] <= 0.05,
        }
    )
    promotion["all_calibration_gates_pass"] = all(
        bool(promotion[k])
        for k in (
            "brier_improves_vs_raw",
            "log_loss_improves_vs_raw",
            "ece_pass",
            "action_expectancy_pass",
            "oos_count_pass",
            "final_brier_improves_vs_raw",
            "final_log_loss_improves_vs_raw",
            "final_ece_pass",
        )
    )
    promotion["all_promotion_gates_pass"] = bool(
        promotion["all_calibration_gates_pass"]
        and promotion["portfolio"]["sharpe_gate"]
        and promotion["portfolio"]["drawdown_gate"]
    )
    return {
        "schema_version": "confidence-feature-candidate-v1",
        "status": "candidate",
        "model": "v39d_confluence",
        "feature_family": feature_family,
        "features": feature_cols,
        "selector": final_model,
        "metrics": {
            "raw_oof": raw_metrics,
            "candidate_oof": candidate_metrics,
            "raw_final_holdout": final_raw_metrics,
            "final_holdout": final_metrics,
        },
        "action_band": {
            "n": int(len(action)),
            "mean_realized_r": float(action["realized_r"].mean()) if len(action) else None,
            "bootstrap_p05_mean_realized_r": action_lower,
        },
        "dataset": {"n_rows": int(len(frame)), "n_oof": int(len(oof_frame)), "folds": len(folds), "embargo_hours": embargo_hours},
        "promotion": promotion,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate one causal confidence feature family")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--bar-source", required=True)
    parser.add_argument("--family", choices=sorted(FEATURE_FAMILIES), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--embargo-hours", type=int, default=1)
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--candidate-sharpe", type=float)
    parser.add_argument("--candidate-dd", type=float)
    parser.add_argument("--baseline-sharpe", type=float)
    parser.add_argument("--baseline-dd", type=float)
    args = parser.parse_args(argv)
    candidates = load_candidate_files(args.input)
    frame = attach_entry_features(candidates, bar_source=args.bar_source, feature_family=args.family)
    artifact = evaluate_feature_family(
        frame,
        feature_family=args.family,
        n_splits=args.splits,
        embargo_hours=args.embargo_hours,
        l2=args.l2,
        candidate_sharpe=args.candidate_sharpe,
        candidate_dd=args.candidate_dd,
        baseline_sharpe=args.baseline_sharpe,
        baseline_dd=args.baseline_dd,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(out), "feature_family": args.family, "promotion": artifact["promotion"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
