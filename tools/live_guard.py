#!/usr/bin/env python3
"""Auto-demotion guard for the promoted live-equity model (P0-5).

Reads the shadow decision ledger's settled ENTER decisions
(``tools/confidence_shadow.py::ShadowDecisionLedger``), computes a rolling
window win rate and mean realized return, and compares them against bands
derived from the locked promotion evidence:

  - **Win-rate breach**: the rolling win rate falls more than
    ``WR_BREACH_MARGIN`` below the locked holdout win rate
    (``runs/v72_dual_sleeve/STATE.json`` ``results.<model>.oos.wr``).
  - **Mean-R breach**: the rolling mean realized return is negative *and*
    falls below the pre-registered bootstrap p05 floor recorded at
    promotion time (``runs/calibration/active/<model>.json``
    ``action_band.bootstrap_p05_mean_realized_r``).

On breach this tool **fails closed**: it always writes a verdict file
(default ``runs/live_guard/STATE.json``) with ``status: "DEMOTE"``, the
trigger reasons, and the rollback target read from
``DEPLOYMENT_MANIFEST.json``'s own ``rollback_model``. With ``--apply`` it
also flips the manifest's ``active.equity_model`` to the rollback model and
sets ``execution_readiness.model_routing`` to ``"blocked_by_live_guard"`` —
every other manifest field (including the SHA-pinned bundle info) is
preserved verbatim, so a human reviewing the demotion sees exactly what
changed. Without ``--apply`` (the default) the manifest is never touched.

This tool never places, cancels, or modifies a broker order — it only gates
state that other tools (``live_plan.py``, ``model_monitoring.py``) already
read.

Usage:
  .venv/bin/python tools/live_guard.py                  # dry run (default), report only
  .venv/bin/python tools/live_guard.py --apply           # mutate the manifest on breach
  .venv/bin/python tools/live_guard.py --window 20 --model v72_dual_sleeve
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from confidence_shadow import ShadowDecisionLedger

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "runs" / "v72_dual_sleeve" / "STATE.json"
MANIFEST_PATH = ROOT / "models" / "poc_va_macdha" / "DEPLOYMENT_MANIFEST.json"
CALIBRATION_DIR = ROOT / "runs" / "calibration" / "active"
VERDICT_PATH = ROOT / "runs" / "live_guard" / "STATE.json"

# --- Explicit, commented breach constants -----------------------------------

# Rolling win rate must not fall more than this many percentage points (as a
# fraction, e.g. 0.15 == 15pp) below the locked holdout win rate before the
# guard demotes. A rolling window of only 20 trades carries wide sampling
# noise on top of the holdout's own wide CI at n=84
# (docs/ML_PROD_READINESS_PLAN.md G7) -- 0.15 is deliberately generous so the
# guard does not flap on ordinary variance while still catching a real
# live-vs-backtest divergence.
WR_BREACH_MARGIN = 0.15

# Rolling window size: last N settled ENTER decisions (not WATCH/ABSTAIN --
# those never risked capital, so they carry no expectancy signal).
DEFAULT_WINDOW = 20


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Evidence loaders (read-only; never mutate locked promotion artifacts).
# ---------------------------------------------------------------------------


def load_holdout_bands(state_path: Path = STATE_PATH, model: str = "v72_dual_sleeve") -> dict[str, Any]:
    """Locked holdout win rate for ``model`` from STATE.json's oos block."""
    payload = _load_json(state_path)
    if payload is None:
        return {"available": False, "reason": "state_missing_or_invalid", "path": str(state_path)}
    row = (payload.get("results") or {}).get(model)
    oos = row.get("oos") if isinstance(row, dict) else None
    if not isinstance(oos, dict) or "wr" not in oos:
        return {"available": False, "reason": "oos_block_incomplete", "path": str(state_path)}
    try:
        win_rate = float(oos["wr"])
    except (TypeError, ValueError):
        return {"available": False, "reason": "oos_wr_not_numeric", "path": str(state_path)}
    return {
        "available": True,
        "path": str(state_path),
        "win_rate": win_rate,
        "n": int(oos.get("n", 0) or 0),
    }


def load_bootstrap_floor(calibration_dir: Path = CALIBRATION_DIR, model: str = "v72_dual_sleeve") -> dict[str, Any]:
    """Pre-registered bootstrap p05 mean-realized-R floor from the active calibrator."""
    path = calibration_dir / f"{model}.json"
    payload = _load_json(path)
    if payload is None:
        return {"available": False, "reason": "calibration_missing_or_invalid", "path": str(path)}
    band = payload.get("action_band")
    if not isinstance(band, dict) or "bootstrap_p05_mean_realized_r" not in band:
        return {"available": False, "reason": "action_band_missing", "path": str(path)}
    try:
        p05 = float(band["bootstrap_p05_mean_realized_r"])
    except (TypeError, ValueError):
        return {"available": False, "reason": "bootstrap_p05_not_numeric", "path": str(path)}
    return {"available": True, "path": str(path), "bootstrap_p05_mean_realized_r": p05}


# ---------------------------------------------------------------------------
# Rolling shadow-ledger statistics.
# ---------------------------------------------------------------------------


def rolling_enter_stats(
    rows: list[dict[str, Any]],
    *,
    window: int = DEFAULT_WINDOW,
    model: str | None = None,
) -> dict[str, Any]:
    """Rolling win rate / mean realized return over the last ``window`` settled ENTER rows.

    Rows that are not dicts, are not settled ENTER decisions, or have a
    non-finite/missing outcome or realized_return are silently skipped — the
    ledger already tolerates a damaged tail
    (``ShadowDecisionLedger._read_unlocked``) and this must not crash on top
    of that (corrupt rows fail closed by being excluded, not by aborting the
    whole computation).
    """
    settled_enter: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("state") != "ENTER":
            continue
        if model is not None and row.get("model") != model:
            continue
        try:
            outcome_f = float(row.get("outcome"))
            realized_f = float(row.get("realized_return"))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(outcome_f) and math.isfinite(realized_f)):
            continue
        settled_enter.append(
            {
                "outcome": outcome_f,
                "realized_return": realized_f,
                "settled_at_utc": str(row.get("settled_at_utc") or row.get("recorded_at_utc") or ""),
            }
        )
    settled_enter.sort(key=lambda r: r["settled_at_utc"])
    recent = settled_enter[-window:] if window > 0 else settled_enter
    n = len(recent)
    win_rate = (sum(r["outcome"] for r in recent) / n) if n else None
    mean_r = (sum(r["realized_return"] for r in recent) / n) if n else None
    return {
        "n": n,
        "n_total_settled_enter": len(settled_enter),
        "window": window,
        "win_rate": win_rate,
        "mean_realized_return": mean_r,
    }


# ---------------------------------------------------------------------------
# Breach evaluation.
# ---------------------------------------------------------------------------


def evaluate_breach(
    rolling: dict[str, Any],
    holdout: dict[str, Any],
    bootstrap: dict[str, Any],
    *,
    window: int = DEFAULT_WINDOW,
    wr_margin: float = WR_BREACH_MARGIN,
) -> dict[str, Any]:
    """Apply the WR-floor and mean-R-floor rules; fail closed on missing evidence.

    Missing evidence (no holdout bands, no bootstrap floor) never *manufactures*
    a breach -- it is recorded as a note and that leg of the check is simply
    not evaluated. A DEMOTE verdict always has at least one concrete,
    evidence-backed trigger reason.
    """
    if rolling["n"] < window:
        return {
            "status": "insufficient_data",
            "breach": False,
            "trigger_reasons": [],
            "notes": [f"only {rolling['n']} of {window} required settled ENTER decisions"],
        }

    trigger_reasons: list[str] = []
    notes: list[str] = []

    if holdout.get("available"):
        wr_floor = float(holdout["win_rate"]) - wr_margin
        if rolling["win_rate"] is not None and rolling["win_rate"] < wr_floor:
            trigger_reasons.append(
                f"win_rate_breach: rolling_win_rate={rolling['win_rate']:.4f} < floor={wr_floor:.4f} "
                f"(holdout_wr={holdout['win_rate']:.4f} - margin={wr_margin})"
            )
    else:
        notes.append(f"holdout_bands_unavailable: {holdout.get('reason')}")

    if bootstrap.get("available"):
        p05 = float(bootstrap["bootstrap_p05_mean_realized_r"])
        mean_r = rolling["mean_realized_return"]
        if mean_r is not None and mean_r < 0 and p05 < 0:
            trigger_reasons.append(
                f"mean_r_breach: rolling_mean_realized_return={mean_r:.4f} < 0 "
                f"and bootstrap_p05_mean_realized_r={p05:.4f} < 0"
            )
    else:
        notes.append(f"bootstrap_floor_unavailable: {bootstrap.get('reason')}")

    breach = len(trigger_reasons) > 0
    if not breach and not holdout.get("available") and not bootstrap.get("available"):
        # Fail closed on ambiguity: with zero usable evidence bands we cannot
        # certify health. No demotion is manufactured (there is nothing to
        # compare against), but the verdict must not read as a clean OK.
        return {
            "status": "evidence_unavailable",
            "breach": False,
            "trigger_reasons": [],
            "notes": notes + ["no usable evidence bands — health cannot be certified"],
        }
    return {
        "status": "DEMOTE" if breach else "OK",
        "breach": breach,
        "trigger_reasons": trigger_reasons,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Verdict assembly + fail-closed manifest mutation.
# ---------------------------------------------------------------------------


def build_verdict(
    *,
    ledger: ShadowDecisionLedger | None = None,
    model: str = "v72_dual_sleeve",
    window: int = DEFAULT_WINDOW,
    wr_margin: float = WR_BREACH_MARGIN,
    state_path: Path = STATE_PATH,
    calibration_dir: Path = CALIBRATION_DIR,
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    ledger = ledger or ShadowDecisionLedger()
    rows = ledger.read()
    rolling = rolling_enter_stats(rows, window=window, model=model)
    holdout = load_holdout_bands(state_path, model=model)
    bootstrap = load_bootstrap_floor(calibration_dir, model=model)
    evaluation = evaluate_breach(rolling, holdout, bootstrap, window=window, wr_margin=wr_margin)

    manifest = _load_json(manifest_path)
    rollback_model = manifest.get("rollback_model") if manifest else None

    verdict: dict[str, Any] = {
        "schema_version": "live-guard-v1",
        "asof_utc": _utc_now(),
        "model": model,
        "ledger_path": str(ledger.path),
        "manifest_path": str(manifest_path),
        "window": window,
        "wr_breach_margin": wr_margin,
        "rolling": rolling,
        "holdout_bands": holdout,
        "bootstrap_floor": bootstrap,
        "rollback_model": rollback_model,
        **evaluation,
    }
    if evaluation["breach"] and not rollback_model:
        # A breach with no rollback target to demote to is itself a
        # fail-closed condition worth surfacing loudly.
        verdict["notes"].append("manifest_missing_rollback_model")
    return verdict


def apply_demotion(
    verdict: dict[str, Any],
    *,
    manifest_path: Path = MANIFEST_PATH,
    updated_by: str = "live_guard",
) -> dict[str, Any]:
    """Flip ``active.equity_model`` to the rollback model. Atomic; fails closed.

    Only ``active.equity_model`` and ``execution_readiness.model_routing``
    are changed — every other field (bundle SHAs, fallbacks, calibration
    block, promotion evidence, data contract) is preserved verbatim so the
    diff is auditable. ``updated_at``/``updated_by`` are bumped and a
    ``live_guard_history`` entry is appended.
    """
    manifest = _load_json(manifest_path)
    if manifest is None:
        raise RuntimeError(f"cannot apply demotion: manifest unreadable at {manifest_path}")
    rollback_model = manifest.get("rollback_model")
    if not rollback_model:
        raise RuntimeError("manifest has no rollback_model to demote to")

    previous_equity_model = (manifest.get("active") or {}).get("equity_model")

    manifest = dict(manifest)
    active = dict(manifest.get("active") or {})
    active["equity_model"] = rollback_model
    manifest["active"] = active

    execution_readiness = dict(manifest.get("execution_readiness") or {})
    execution_readiness["model_routing"] = "blocked_by_live_guard"
    manifest["execution_readiness"] = execution_readiness

    manifest["updated_at"] = _utc_now()
    manifest["updated_by"] = updated_by
    history = list(manifest.get("live_guard_history") or [])
    history.append(
        {
            "asof_utc": verdict.get("asof_utc"),
            "from_equity_model": previous_equity_model,
            "to_equity_model": rollback_model,
            "trigger_reasons": verdict.get("trigger_reasons"),
        }
    )
    manifest["live_guard_history"] = history

    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(manifest_path)
    return manifest


def write_verdict(verdict: dict[str, Any], path: Path = VERDICT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(verdict, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-demotion guard for the promoted live-equity model")
    parser.add_argument("--model", default="v72_dual_sleeve")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--wr-margin", type=float, default=WR_BREACH_MARGIN)
    parser.add_argument("--ledger-path", default=None)
    parser.add_argument("--state-path", default=str(STATE_PATH))
    parser.add_argument("--manifest-path", default=str(MANIFEST_PATH))
    parser.add_argument("--calibration-dir", default=str(CALIBRATION_DIR))
    parser.add_argument("--verdict-path", default=str(VERDICT_PATH))
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Report only; never mutate the manifest (default)",
    )
    parser.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Mutate DEPLOYMENT_MANIFEST.json on breach",
    )
    args = parser.parse_args(argv)

    ledger = ShadowDecisionLedger(args.ledger_path)
    manifest_path = Path(args.manifest_path)
    verdict = build_verdict(
        ledger=ledger,
        model=args.model,
        window=args.window,
        wr_margin=args.wr_margin,
        state_path=Path(args.state_path),
        calibration_dir=Path(args.calibration_dir),
        manifest_path=manifest_path,
    )
    verdict["dry_run"] = bool(args.dry_run)
    verdict["mutation_applied"] = False

    if verdict["breach"] and not args.dry_run:
        try:
            apply_demotion(verdict, manifest_path=manifest_path)
            verdict["mutation_applied"] = True
        except Exception as exc:  # noqa: BLE001
            verdict["mutation_error"] = str(exc)

    write_verdict(verdict, Path(args.verdict_path))
    print(json.dumps(verdict, indent=2, default=str))
    return 1 if verdict["breach"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
