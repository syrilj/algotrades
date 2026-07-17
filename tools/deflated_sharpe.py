#!/usr/bin/env python3
"""Deflated Sharpe Ratio (DSR) for the poc_va_macdha promoted model.

Implements Bailey & Lopez de Prado's Probabilistic Sharpe Ratio (PSR) and
Deflated Sharpe Ratio (DSR):

  Bailey, D. H. and Lopez de Prado, M. (2012), "The Sharpe Ratio Efficient
  Frontier", Journal of Risk.
  Bailey, D. H. and Lopez de Prado, M. (2014), "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality",
  Journal of Portfolio Management.

PSR(SR*) is the probability that the *true* Sharpe ratio exceeds a benchmark
SR*, given the observed Sharpe ratio, the number of return observations, and
the skew/kurtosis of the return distribution (non-normal returns shrink the
effective sample size). DSR is PSR evaluated at SR* = the *expected maximum*
Sharpe ratio one would observe by chance alone after searching N independent
trials (``expected_max_sharpe``) — i.e. "how likely is it that this Sharpe
is real skill, not the best of N noisy draws".

This module is offline/deterministic: no network calls, no mutation of any
locked evidence file. It only reads:
  - runs/v72_dual_sleeve/STATE.json (oos block: sharpe, n) for defaults
  - models/poc_va_macdha/v*/ directories + TRAINING_LEADERBOARD.json for the
    trial population (count and, best-effort, their Sharpe ratios)

Usage:
  .venv/bin/python tools/deflated_sharpe.py
  .venv/bin/python tools/deflated_sharpe.py --sharpe 2.1988 --n 84 --trials 200
  .venv/bin/python tools/deflated_sharpe.py --returns-csv runs/x/trades.csv --returns-col pnl_pct
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "models" / "poc_va_macdha"
LEADERBOARD_PATH = FAMILY_DIR / "TRAINING_LEADERBOARD.json"
STATE_PATH = ROOT / "runs" / "v72_dual_sleeve" / "STATE.json"

EULER_MASCHERONI = 0.5772156649015329
PASS_BAR_DEFAULT = 0.95


# ---------------------------------------------------------------------------
# Normal distribution helpers (no scipy dependency).
# ---------------------------------------------------------------------------


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (probit) via Acklam's rational approximation.

    Accurate to ~1.15e-9 absolute error, ample for this use.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


# ---------------------------------------------------------------------------
# Return-distribution moments.
# ---------------------------------------------------------------------------


def skew_kurtosis(returns: Sequence[float]) -> tuple[float, float]:
    """Sample skew (gamma3) and *non-excess* kurtosis (gamma4; normal == 3.0).

    Falls back to the Gaussian moments (0.0, 3.0) when there are too few
    observations or the series is degenerate (zero variance).
    """
    x = np.asarray([float(v) for v in returns if v is not None and math.isfinite(float(v))], dtype=float)
    if x.size < 3:
        return 0.0, 3.0
    sigma = float(x.std(ddof=1))
    if sigma <= 1e-15:
        return 0.0, 3.0
    z = (x - float(x.mean())) / sigma
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    return skew, kurt


# ---------------------------------------------------------------------------
# Core Bailey & Lopez de Prado statistics.
# ---------------------------------------------------------------------------


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    benchmark_sharpe: float,
    n: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """PSR(SR*): P(true Sharpe > benchmark_sharpe | observed_sharpe, n obs).

    ``skew``/``kurtosis`` are the sample moments of the *per-observation*
    returns backing ``observed_sharpe`` (non-normal returns shrink the
    effective sample size via the denominator below).
    """
    if n is None or n < 2:
        return float("nan")
    denom = 1.0 - skew * observed_sharpe + (kurtosis - 1.0) / 4.0 * observed_sharpe**2
    if denom <= 1e-12:
        # Degenerate higher-moment adjustment (pathological skew/kurtosis
        # input) — fail back to the Gaussian denominator rather than blow up.
        denom = 1.0
    stat = (observed_sharpe - benchmark_sharpe) * math.sqrt(n - 1) / math.sqrt(denom)
    return _norm_cdf(stat)


def expected_max_sharpe(trial_sharpes: Sequence[float], n_trials: int | None = None) -> float:
    """E[max Sharpe] across ``n_trials`` independent trials (Bailey & LdP 2014, eq. 8).

    Approximates the trial Sharpe-ratio population as i.i.d. N(0, sigma_sr^2)
    under the null of no skill, with sigma_sr estimated as the sample std of
    the observed trial Sharpes. If fewer than 2 usable trial Sharpes are
    available, sigma_sr cannot be estimated and this returns 0.0 (no
    deflation — the caller should treat that as "insufficient trial
    evidence", not "no selection bias").
    """
    trials = [float(s) for s in trial_sharpes if s is not None and math.isfinite(float(s))]
    n = int(n_trials) if n_trials is not None else len(trials)
    if n < 2 or len(trials) < 2:
        return 0.0
    sigma_sr = float(np.std(trials, ddof=1))
    if sigma_sr <= 1e-12:
        return 0.0
    e_max = sigma_sr * (
        (1.0 - EULER_MASCHERONI) * _norm_ppf(1.0 - 1.0 / n)
        + EULER_MASCHERONI * _norm_ppf(1.0 - 1.0 / (n * math.e))
    )
    return float(e_max)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n: int,
    trial_sharpes: Sequence[float],
    n_trials: int | None = None,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> dict[str, Any]:
    """Full DSR computation: PSR(0), expected max Sharpe of N trials, DSR."""
    n_trials_eff = int(n_trials) if n_trials is not None else len(trial_sharpes)
    sr_benchmark = expected_max_sharpe(trial_sharpes, n_trials_eff)
    psr = probabilistic_sharpe_ratio(observed_sharpe, 0.0, n, skew, kurtosis)
    dsr = probabilistic_sharpe_ratio(observed_sharpe, sr_benchmark, n, skew, kurtosis)
    return {
        "dsr": dsr,
        "psr": psr,
        "expected_max_sharpe": sr_benchmark,
        "n_trials": n_trials_eff,
        "n_observations": int(n),
        "skew": skew,
        "kurtosis": kurtosis,
    }


# ---------------------------------------------------------------------------
# Trial-population discovery (N, and best-effort Sharpe harvesting for sigma_sr).
# ---------------------------------------------------------------------------


def _extract_sharpe(payload: Any) -> float | None:
    """Best-effort Sharpe extraction across the family's varied result shapes."""
    if not isinstance(payload, dict):
        return None
    candidates: list[Any] = []
    port = payload.get("portfolio")
    if isinstance(port, dict):
        candidates.append(port.get("sharpe"))
    for key in ("oos", "full", "holdout"):
        block = payload.get(key)
        if isinstance(block, dict):
            candidates.append(block.get("sharpe"))
    candidates.append(payload.get("sharpe"))
    candidates.append(payload.get("median_sharpe"))
    for value in candidates:
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            return f
    return None


def discover_model_dirs(family_dir: Path = FAMILY_DIR) -> list[str]:
    """Canonical trial ids from ``models/poc_va_macdha/v*`` directories."""
    if not family_dir.exists():
        return []
    return sorted(
        p.name for p in family_dir.iterdir() if p.is_dir() and p.name.startswith("v")
    )


def discover_leaderboard_entries(path: Path = LEADERBOARD_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def discover_trial_population(
    family_dir: Path = FAMILY_DIR,
    leaderboard_path: Path = LEADERBOARD_PATH,
) -> dict[str, Any]:
    """Union of version directories and leaderboard variants (deduped by id).

    Returns the trial count (``n_trials``), the sub-population size for which
    a Sharpe ratio could be recovered (``n_with_sharpe``), and the list of
    recovered Sharpes (used to estimate sigma_sr for ``expected_max_sharpe``).
    Trials without a recoverable Sharpe still count toward ``n_trials`` — the
    multiple-testing correction should reflect every trial actually run, not
    only the ones with clean output.
    """
    trial_ids: set[str] = set(discover_model_dirs(family_dir))
    leaderboard = discover_leaderboard_entries(leaderboard_path)
    for row in leaderboard:
        variant = row.get("variant") if isinstance(row, dict) else None
        if variant:
            trial_ids.add(str(variant))

    sharpe_by_id: dict[str, float] = {}
    for row in leaderboard:
        if not isinstance(row, dict):
            continue
        variant = row.get("variant")
        sharpe = _extract_sharpe(row)
        if variant and sharpe is not None:
            sharpe_by_id[str(variant)] = sharpe

    for name in discover_model_dirs(family_dir):
        if name in sharpe_by_id:
            continue  # leaderboard entry already gave us a Sharpe for this id
        for filename in ("results.json", "STATE.json", "COMPARE.json", "WINNER.json"):
            fp = family_dir / name / filename
            if not fp.exists():
                continue
            try:
                payload = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            sharpe = _extract_sharpe(payload)
            if sharpe is None and isinstance(payload, dict):
                # COMPARE.json / STATE.json shape: {model_id: {train/oos/full: {...}}}
                inner = payload.get(name) if name in payload else None
                sharpe = _extract_sharpe(inner) if inner else None
            if sharpe is not None:
                sharpe_by_id[name] = sharpe
                break

    return {
        "n_trials": len(trial_ids),
        "n_with_sharpe": len(sharpe_by_id),
        "trial_ids": sorted(trial_ids),
        "trial_sharpes": sharpe_by_id,
    }


# ---------------------------------------------------------------------------
# Evidence loaders.
# ---------------------------------------------------------------------------


def load_holdout_defaults(state_path: Path = STATE_PATH, model: str = "v72_dual_sleeve") -> dict[str, Any]:
    """Read the promoted model's oos block from STATE.json (read-only evidence)."""
    if not state_path.exists():
        return {"available": False, "reason": "state_missing", "path": str(state_path)}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"state_invalid: {exc}", "path": str(state_path)}
    results = payload.get("results", {})
    row = results.get(model)
    if not isinstance(row, dict):
        return {"available": False, "reason": "model_not_in_state", "path": str(state_path)}
    oos = row.get("oos")
    if not isinstance(oos, dict) or "sharpe" not in oos or "n" not in oos:
        return {"available": False, "reason": "oos_block_incomplete", "path": str(state_path)}
    return {
        "available": True,
        "path": str(state_path),
        "model": model,
        "sharpe": float(oos["sharpe"]),
        "n": int(oos["n"]),
        "win_rate": oos.get("wr"),
        "total_return": oos.get("ret"),
        "max_drawdown": oos.get("dd"),
    }


def load_returns_from_csv(path: Path, column: str) -> list[float]:
    """Read a per-trade/per-bar return column from a CSV (for skew/kurtosis)."""
    out: list[float] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw = row.get(column)
            if raw in (None, ""):
                continue
            try:
                out.append(float(raw))
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_report(
    *,
    sharpe: float | None = None,
    n: int | None = None,
    trials_override: int | None = None,
    returns: Sequence[float] | None = None,
    period: str = "1H",
    model: str = "v72_dual_sleeve",
    pass_bar: float = PASS_BAR_DEFAULT,
) -> dict[str, Any]:
    holdout = load_holdout_defaults(model=model)
    if sharpe is None:
        if not holdout.get("available"):
            raise ValueError(
                f"--sharpe not provided and holdout defaults unavailable ({holdout.get('reason')})"
            )
        sharpe = holdout["sharpe"]
    if n is None:
        if not holdout.get("available"):
            raise ValueError("--n not provided and holdout defaults unavailable")
        n = holdout["n"]

    population = discover_trial_population()
    n_trials = trials_override if trials_override is not None else population["n_trials"]
    trial_sharpes = list(population["trial_sharpes"].values())

    skew, kurtosis = (0.0, 3.0)
    returns_used = 0
    if returns:
        skew, kurtosis = skew_kurtosis(returns)
        returns_used = len(returns)

    stats = deflated_sharpe_ratio(
        float(sharpe), int(n), trial_sharpes, n_trials=n_trials, skew=skew, kurtosis=kurtosis
    )
    verdict = "pass" if math.isfinite(stats["dsr"]) and stats["dsr"] >= pass_bar else "fail"

    return {
        "schema_version": "deflated-sharpe-v1",
        "model": model,
        "period": period,
        "inputs": {
            "observed_sharpe": float(sharpe),
            "n_observations": int(n),
            "n_trials": n_trials,
            "n_trials_with_recovered_sharpe": population["n_with_sharpe"],
            "trial_sharpe_sigma": (
                float(np.std(trial_sharpes, ddof=1)) if len(trial_sharpes) >= 2 else None
            ),
            "skew": skew,
            "kurtosis": kurtosis,
            "returns_provided": returns_used,
            "moments_source": "trade_returns" if returns_used else "gaussian_default",
        },
        "holdout_evidence": holdout,
        "dsr": stats["dsr"],
        "psr": stats["psr"],
        "expected_max_sharpe": stats["expected_max_sharpe"],
        "pass_bar": pass_bar,
        "verdict": verdict,
        "notes": [
            "DSR/PSR follow Bailey & Lopez de Prado (2012, 2014).",
            "n_trials counts models/poc_va_macdha/v* directories unioned with "
            "TRAINING_LEADERBOARD.json variants (deduped by id); every attempted "
            "trial counts even when its Sharpe could not be recovered.",
            "sigma_sr (trial-Sharpe dispersion) is estimated only from the "
            "sub-population where a Sharpe could be parsed from results.json / "
            "STATE.json / COMPARE.json / WINNER.json / the leaderboard row.",
            (
                "skew/kurtosis were fit from provided trade-level returns."
                if returns_used
                else "skew/kurtosis default to the Gaussian case (0, 3) — no "
                "trade-level return series was provided for this run."
            ),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--model", default="v72_dual_sleeve")
    parser.add_argument("--sharpe", type=float, default=None, help="Observed (holdout) Sharpe; default reads STATE.json oos block")
    parser.add_argument("--n", type=int, default=None, help="Number of return observations backing the Sharpe; default reads STATE.json oos.n")
    parser.add_argument("--trials", type=int, default=None, help="Override the auto-discovered trial count N")
    parser.add_argument("--period", default="1H")
    parser.add_argument("--pass-bar", type=float, default=PASS_BAR_DEFAULT)
    parser.add_argument("--returns-csv", default=None, help="Optional CSV of trade-level returns for skew/kurtosis")
    parser.add_argument("--returns-col", default="return_pct")
    args = parser.parse_args(argv)

    returns: list[float] | None = None
    if args.returns_csv:
        returns = load_returns_from_csv(Path(args.returns_csv), args.returns_col)

    report = build_report(
        sharpe=args.sharpe,
        n=args.n,
        trials_override=args.trials,
        returns=returns,
        period=args.period,
        model=args.model,
        pass_bar=args.pass_bar,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
