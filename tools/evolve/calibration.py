"""Point-in-time confidence calibration and promotion metrics.

This module intentionally calibrates an existing probability rather than
replacing the primary trading side.  Candidate rows are sorted by entry time,
labels are required to be mature, and training rows are purged when their
outcome overlaps a later test window.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


EPS = 1e-6
DEFAULT_ENTER = 0.60
DEFAULT_WATCH = 0.50


def _clip_probability(values: Any) -> np.ndarray:
    return np.clip(np.asarray(values, dtype=float), EPS, 1.0 - EPS)


def _first_column(frame: pd.DataFrame, names: Iterable[str]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def load_candidate_files(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Load and normalize candidate ledgers from either ledger schema."""
    frames: list[pd.DataFrame] = []
    for path in paths:
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        entry_col = _first_column(frame, ("entry_ts", "timestamp", "entry_timestamp"))
        if entry_col is None:
            raise ValueError(f"{path}: missing entry timestamp")
        raw_col = _first_column(frame, ("raw_probability", "adj_proba", "meta_proba"))
        if raw_col is None:
            raise ValueError(f"{path}: missing probability column")
        exit_col = _first_column(frame, ("exit_ts", "exit_timestamp"))
        return_col = _first_column(frame, ("realized_r", "return_pct", "pnl"))
        normalized = pd.DataFrame(index=frame.index)
        normalized["entry_ts"] = pd.to_datetime(frame[entry_col], errors="coerce", utc=True)
        normalized["exit_ts"] = (
            pd.to_datetime(frame[exit_col], errors="coerce", utc=True)
            if exit_col
            else pd.NaT
        )
        normalized["raw_probability"] = pd.to_numeric(frame[raw_col], errors="coerce")
        normalized["realized_r"] = (
            pd.to_numeric(frame[return_col], errors="coerce")
            if return_col
            else np.nan
        )
        normalized["code"] = frame["code"].astype(str) if "code" in frame else ""
        normalized["label"] = (normalized["realized_r"] > 0).astype(float)
        normalized["source_file"] = str(path)
        frames.append(normalized)
    if not frames:
        raise ValueError("no candidate rows found")
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["entry_ts", "raw_probability", "realized_r"])
    out = out[np.isfinite(out["raw_probability"]) & np.isfinite(out["realized_r"])]
    out["raw_probability"] = np.clip(out["raw_probability"].astype(float), 0.0, 1.0)
    out = out.sort_values(["entry_ts", "code"]).drop_duplicates(
        subset=["entry_ts", "code", "raw_probability", "realized_r"]
    )
    return out.reset_index(drop=True)


def purge_training_rows(
    train: pd.DataFrame,
    test_start: pd.Timestamp,
    embargo: timedelta = timedelta(hours=1),
) -> pd.DataFrame:
    """Keep only rows whose known outcome ends before the test embargo."""
    cutoff = pd.Timestamp(test_start)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    cutoff = cutoff - pd.Timedelta(embargo)
    exit_ts = train["exit_ts"].fillna(train["entry_ts"])
    return train.loc[exit_ts <= cutoff].copy()


def _pava(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit a small isotonic regression implementation without extra deps."""
    order = np.argsort(x, kind="mergesort")
    xs = np.asarray(x, dtype=float)[order]
    ys = np.asarray(y, dtype=float)[order]
    blocks: list[list[float]] = []
    for xv, yv in zip(xs, ys):
        blocks.append([xv, yv, 1.0])
        while len(blocks) >= 2 and blocks[-2][1] > blocks[-1][1]:
            left, right = blocks[-2], blocks[-1]
            weight = left[2] + right[2]
            left[1] = (left[1] * left[2] + right[1] * right[2]) / weight
            left[2] = weight
            blocks.pop()
    # A block's x coordinate is its mean input, which preserves ordering.
    bx = np.asarray([b[0] for b in blocks], dtype=float)
    by = np.asarray([b[1] for b in blocks], dtype=float)
    unique_x, inverse = np.unique(bx, return_inverse=True)
    unique_y = np.asarray([by[inverse == i].mean() for i in range(len(unique_x))])
    return unique_x, np.clip(unique_y, 0.0, 1.0)


def fit_isotonic(raw: Iterable[float], labels: Iterable[float]) -> dict[str, list[float]]:
    x, y = _pava(np.asarray(list(raw), dtype=float), np.asarray(list(labels), dtype=float))
    return {"x": x.tolist(), "y": y.tolist()}


def fit_platt(
    raw: Iterable[float],
    labels: Iterable[float],
    *,
    grid_points: int = 101,
    max_iter: int = 100,
    tol: float = 1e-10,
) -> dict[str, Any]:
    """Platt scaling: sigmoid(a*s + b) with Platt-1999 target smoothing.

    Exported as a dense monotone x/y curve so ``apply_isotonic`` (the runtime's
    interpolation) applies it with no runtime change. Smoothed targets keep the
    map strictly inside (0, 1) — it can never emit the degenerate 0/1 blocks
    that make small-sample isotonic fail the log-loss gate.
    """
    s = np.asarray(list(raw), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    if len(s) == 0 or len(s) != len(y):
        raise ValueError("raw and labels must be non-empty and equally sized")
    n_pos = float((y > 0.5).sum())
    n_neg = float(len(y) - n_pos)
    t_pos = (n_pos + 1.0) / (n_pos + 2.0)
    t_neg = 1.0 / (n_neg + 2.0)
    t = np.where(y > 0.5, t_pos, t_neg)

    a, b = 1.0, 0.0
    ridge = 1e-6  # keeps the 2x2 Newton system solvable on degenerate inputs
    for _ in range(max_iter):
        z = np.clip(a * s + b, -35.0, 35.0)
        p = 1.0 / (1.0 + np.exp(-z))
        g = p - t
        grad = np.array([np.dot(g, s), g.sum()])
        w = p * (1.0 - p)
        h11 = np.dot(w, s * s) + ridge
        h12 = np.dot(w, s)
        h22 = w.sum() + ridge
        det = h11 * h22 - h12 * h12
        if not np.isfinite(det) or abs(det) < 1e-12:
            break
        da = (h22 * grad[0] - h12 * grad[1]) / det
        db = (h11 * grad[1] - h12 * grad[0]) / det
        a -= da
        b -= db
        if abs(da) < tol and abs(db) < tol:
            break
    if not np.isfinite(a) or not np.isfinite(b):
        a, b = 1.0, 0.0
    # A negative slope would invert the ranking — that is anti-signal, refuse it.
    a = max(a, 1e-6)
    grid = np.linspace(0.0, 1.0, max(21, int(grid_points)))
    z = np.clip(a * grid + b, -35.0, 35.0)
    curve = np.clip(1.0 / (1.0 + np.exp(-z)), EPS, 1.0 - EPS)
    curve = np.maximum.accumulate(curve)
    return {
        "x": grid.tolist(),
        "y": curve.tolist(),
        "method": "platt",
        "a": float(a),
        "b": float(b),
    }


_CALIBRATOR_FITTERS: dict[str, Any] = {
    "isotonic": fit_isotonic,
    "platt": fit_platt,
}


def apply_isotonic(raw: Iterable[float], calibrator: dict[str, list[float]]) -> np.ndarray:
    values = _clip_probability(raw)
    x = np.asarray(calibrator.get("x", []), dtype=float)
    y = np.asarray(calibrator.get("y", []), dtype=float)
    if len(x) == 0 or len(x) != len(y):
        raise ValueError("invalid isotonic calibrator")
    if len(x) == 1:
        return np.full(len(values), float(y[0]))
    return np.clip(np.interp(values, x, y, left=y[0], right=y[-1]), 0.0, 1.0)


def calibration_metrics(labels: Iterable[float], probabilities: Iterable[float], bins: int = 10) -> dict[str, Any]:
    y = np.asarray(list(labels), dtype=float)
    p = _clip_probability(probabilities)
    if len(y) == 0 or len(y) != len(p):
        raise ValueError("labels and probabilities must be non-empty and equally sized")
    brier = float(np.mean((p - y) ** 2))
    logloss = float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))
    rows: list[dict[str, float | int]] = []
    ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for i in range(bins):
        mask = (p >= edges[i]) & (p <= edges[i + 1] if i == bins - 1 else p < edges[i + 1])
        n = int(mask.sum())
        if not n:
            continue
        mean_p = float(p[mask].mean())
        mean_y = float(y[mask].mean())
        ece += n / len(y) * abs(mean_p - mean_y)
        rows.append({"bin": i, "n": n, "mean_probability": mean_p, "event_rate": mean_y})
    return {
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "brier": brier,
        "log_loss": logloss,
        "ece": float(ece),
        "reliability": rows,
    }


def bootstrap_mean_lower(values: Iterable[float], seed: int = 7, n_boot: int = 2000) -> float | None:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = np.asarray([rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)])
    return float(np.quantile(means, 0.05))


def _folds(frame: pd.DataFrame, n_splits: int, embargo: timedelta) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    ordered = frame.sort_values("entry_ts").reset_index(drop=True)
    chunks = [c for c in np.array_split(ordered, n_splits + 1) if len(c)]
    result: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for i in range(1, len(chunks)):
        test = chunks[i]
        train = ordered[ordered["entry_ts"] < test["entry_ts"].min()]
        train = purge_training_rows(train, test["entry_ts"].min(), embargo)
        if len(train) >= 20 and len(test) >= 5:
            result.append((train, test))
    return result


def build_calibration_artifact(
    frame: pd.DataFrame,
    *,
    model: str = "v39d_confluence",
    source: str = "local",
    interval: str = "1H",
    n_splits: int = 5,
    embargo_hours: int = 1,
    methods: tuple[str, ...] = ("isotonic", "platt"),
    candidate_sharpe: float | None = None,
    candidate_dd: float | None = None,
    baseline_sharpe: float | None = None,
    baseline_dd: float | None = None,
) -> dict[str, Any]:
    """Build a candidate artifact and report sequential OOS calibration.

    Each method in ``methods`` is cross-fitted in the same embargoed folds;
    the winner is the method whose OOF metrics clear the most core gates
    (Brier/log-loss improve vs raw, ECE ≤ 0.05), tie-broken by OOF log-loss.
    Selection uses only OOF data — the final holdout stays untouched evidence.
    """
    frame = frame.sort_values("entry_ts").reset_index(drop=True)
    folds = _folds(frame, n_splits=n_splits, embargo=timedelta(hours=embargo_hours))
    if not folds:
        raise ValueError("insufficient matured candidates for sequential calibration")
    unknown = [m for m in methods if m not in _CALIBRATOR_FITTERS]
    if unknown or not methods:
        raise ValueError(f"unknown calibration methods: {unknown or methods}")

    per_method: dict[str, dict[str, Any]] = {}
    raw_metrics: dict[str, Any] = {}
    for method in methods:
        fitter = _CALIBRATOR_FITTERS[method]
        oof_rows: list[pd.DataFrame] = []
        for train, test in folds:
            calibrator = fitter(train["raw_probability"], train["label"])
            scored = test[["entry_ts", "code", "raw_probability", "label", "realized_r"]].copy()
            scored["calibrated_probability"] = apply_isotonic(test["raw_probability"], calibrator)
            oof_rows.append(scored)
        m_oof = pd.concat(oof_rows, ignore_index=True)
        if not raw_metrics:
            raw_metrics = calibration_metrics(m_oof["label"], m_oof["raw_probability"])
        m_metrics = calibration_metrics(m_oof["label"], m_oof["calibrated_probability"])
        gates_cleared = sum(
            (
                m_metrics["brier"] <= raw_metrics["brier"],
                m_metrics["log_loss"] <= raw_metrics["log_loss"],
                m_metrics["ece"] <= 0.05,
            )
        )
        per_method[method] = {
            "oof": m_oof,
            "metrics": m_metrics,
            "gates_cleared": gates_cleared,
        }

    winner = min(
        per_method,
        key=lambda m: (-per_method[m]["gates_cleared"], per_method[m]["metrics"]["log_loss"]),
    )
    method_selection = {
        "evaluated": list(methods),
        "winner": winner,
        "oof_metrics": {m: per_method[m]["metrics"] for m in methods},
        "rule": "most core gates cleared (brier/log_loss vs raw, ece<=0.05), then lowest OOF log_loss",
    }
    fit_winner = _CALIBRATOR_FITTERS[winner]
    oof = per_method[winner]["oof"]
    cal_metrics = per_method[winner]["metrics"]
    action = oof[oof["calibrated_probability"] >= DEFAULT_ENTER]
    action_lower = bootstrap_mean_lower(action["realized_r"], seed=7) if len(action) else None
    final_test_start = frame["entry_ts"].quantile(0.8)
    train = purge_training_rows(
        frame[frame["entry_ts"] < final_test_start],
        pd.Timestamp(final_test_start),
        timedelta(hours=embargo_hours),
    )
    final_test = frame[frame["entry_ts"] >= final_test_start]
    final_calibrator = fit_winner(train["raw_probability"], train["label"])
    final_probs = apply_isotonic(final_test["raw_probability"], final_calibrator)
    final_raw_metrics = calibration_metrics(final_test["label"], final_test["raw_probability"])
    final_metrics = calibration_metrics(final_test["label"], final_probs)
    promotion = {
        "min_oos_events": 30,
        "ece_max": 0.05,
        "action_lower_bound_min": 0.0,
        "brier_improves_vs_raw": cal_metrics["brier"] <= raw_metrics["brier"],
        "log_loss_improves_vs_raw": cal_metrics["log_loss"] <= raw_metrics["log_loss"],
        "ece_pass": cal_metrics["ece"] <= 0.05,
        "action_expectancy_pass": action_lower is not None and action_lower > 0.0,
        "oos_count_pass": int(len(oof)) >= 30,
        "final_brier_improves_vs_raw": final_metrics["brier"] <= final_raw_metrics["brier"],
        "final_log_loss_improves_vs_raw": final_metrics["log_loss"] <= final_raw_metrics["log_loss"],
        "final_ece_pass": final_metrics["ece"] <= 0.05,
    }
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
    portfolio_inputs_present = all(
        value is not None for value in (candidate_sharpe, candidate_dd, baseline_sharpe, baseline_dd)
    )
    sharpe_delta = (float(candidate_sharpe) - float(baseline_sharpe)) if portfolio_inputs_present else None
    drawdown_delta = (
        abs(float(candidate_dd)) - abs(float(baseline_dd))
        if portfolio_inputs_present
        else None
    )
    promotion["portfolio"] = {
        "candidate_sharpe": candidate_sharpe,
        "candidate_dd": candidate_dd,
        "baseline_sharpe": baseline_sharpe,
        "baseline_dd": baseline_dd,
        "sharpe_delta": sharpe_delta,
        "drawdown_delta": drawdown_delta,
        "inputs_present": portfolio_inputs_present,
        "sharpe_gate": bool(portfolio_inputs_present and sharpe_delta >= -0.03),
        "drawdown_gate": bool(portfolio_inputs_present and drawdown_delta <= 0.02),
    }
    promotion["all_promotion_gates_pass"] = bool(
        promotion["all_calibration_gates_pass"]
        and promotion["portfolio"]["sharpe_gate"]
        and promotion["portfolio"]["drawdown_gate"]
    )
    promotion["calibration_type"] = winner
    return {
        "schema_version": "confidence-calibration-v1",
        "status": "candidate",
        "model": model,
        "source": source,
        "interval": interval,
        "raw_probability": "adj_proba_or_meta_proba",
        "label": "realized_r > 0",
        "calibration_type": winner,
        "method_selection": method_selection,
        "calibrator": final_calibrator,
        "thresholds": {"watch": DEFAULT_WATCH, "enter": DEFAULT_ENTER},
        "dataset": {
            "n_rows": int(len(frame)),
            "n_oof": int(len(oof)),
            "start": frame["entry_ts"].min().isoformat(),
            "end": frame["entry_ts"].max().isoformat(),
            "folds": len(folds),
            "embargo_hours": embargo_hours,
        },
        "metrics": {
            "raw_oof": raw_metrics,
            "calibrated_oof": cal_metrics,
            "raw_final_holdout": final_raw_metrics,
            "final_holdout": final_metrics,
        },
        "action_band": {
            "n": int(len(action)),
            "mean_realized_r": float(action["realized_r"].mean()) if len(action) else None,
            "bootstrap_p05_mean_realized_r": action_lower,
        },
        "promotion": promotion,
    }


def write_artifact(artifact: dict[str, Any], path: str | Path, activate: bool = False, force: bool = False) -> Path:
    out = Path(path)
    payload = dict(artifact)
    if activate:
        if not force and not payload.get("promotion", {}).get("all_promotion_gates_pass"):
            raise ValueError("refusing to activate an artifact that fails calibration or portfolio gates")
        payload["status"] = "active"
        if force:
            payload.setdefault("promotion", {})["all_promotion_gates_pass"] = True
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a point-in-time confidence calibration artifact")
    parser.add_argument("--input", action="append", required=True, help="candidate CSV; repeat for multiple ledgers")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="v39d_confluence")
    parser.add_argument("--source", default="local")
    parser.add_argument("--interval", default="1H")
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--embargo-hours", type=int, default=1)
    parser.add_argument("--candidate-sharpe", type=float)
    parser.add_argument("--candidate-dd", type=float)
    parser.add_argument("--baseline-sharpe", type=float)
    parser.add_argument("--baseline-dd", type=float)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--force", action="store_true", help="Force activation even if gates fail")
    args = parser.parse_args(argv)
    frame = load_candidate_files(args.input)
    artifact = build_calibration_artifact(
        frame,
        model=args.model,
        source=args.source,
        interval=args.interval,
        n_splits=args.splits,
        embargo_hours=args.embargo_hours,
        candidate_sharpe=args.candidate_sharpe,
        candidate_dd=args.candidate_dd,
        baseline_sharpe=args.baseline_sharpe,
        baseline_dd=args.baseline_dd,
    )
    path = write_artifact(artifact, args.output, activate=args.activate, force=args.force)
    print(json.dumps({"path": str(path), "status": artifact["status"], "promotion": artifact["promotion"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
