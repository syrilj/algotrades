#!/usr/bin/env python3
"""Production model-health report for shadow and paper outcomes.

The report is deterministic and offline by default. ``--settle-due`` closes
mature shadow decisions from the versioned local daily-bar snapshot before the
report is calculated.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from confidence_shadow import ShadowDecisionLedger


ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_MANIFEST = ROOT / "models" / "poc_va_macdha" / "DEPLOYMENT_MANIFEST.json"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def calibration_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = []
    for row in rows:
        probability = _finite(row.get("calibrated_probability"))
        outcome = _finite(row.get("outcome"))
        if probability is not None and outcome is not None:
            pairs.append((float(np.clip(probability, 0.0, 1.0)), float(outcome > 0.5)))
    if not pairs:
        return {"n": 0, "brier": None, "base_rate": None, "brier_skill": None, "ece": None}
    probabilities = np.asarray([p for p, _ in pairs], dtype=float)
    outcomes = np.asarray([y for _, y in pairs], dtype=float)
    brier = float(np.mean((probabilities - outcomes) ** 2))
    base_rate = float(np.mean(outcomes))
    base_brier = float(np.mean((base_rate - outcomes) ** 2))
    brier_skill = 1.0 - brier / base_brier if base_brier > 1e-12 else None
    ece = 0.0
    reliability = []
    for lower in np.linspace(0.0, 0.9, 10):
        upper = lower + 0.1
        mask = (probabilities >= lower) & (probabilities < upper if upper < 1.0 else probabilities <= upper)
        if not np.any(mask):
            continue
        mean_score = float(np.mean(probabilities[mask]))
        event_rate = float(np.mean(outcomes[mask]))
        count = int(np.sum(mask))
        ece += count / len(probabilities) * abs(mean_score - event_rate)
        reliability.append(
            {"lower": round(float(lower), 2), "upper": round(float(upper), 2), "n": count,
             "mean_score": mean_score, "event_rate": event_rate}
        )
    calibrated_n = sum(1 for row in rows if row.get("probability_calibrated") is True and row.get("outcome") is not None)
    return {
        "n": len(pairs),
        "brier": brier,
        "base_rate": base_rate,
        "base_rate_brier": base_brier,
        "brier_skill": brier_skill,
        "ece": float(ece),
        "probability_calibrated_n": calibrated_n,
        "score_only_n": len(pairs) - calibrated_n,
        "reliability": reliability,
    }


def _psi(reference: list[float], recent: list[float]) -> float | None:
    if len(reference) < 20 or len(recent) < 10:
        return None
    edges = np.linspace(0.0, 1.0, 11)
    ref_hist, _ = np.histogram(np.clip(reference, 0, 1), bins=edges)
    new_hist, _ = np.histogram(np.clip(recent, 0, 1), bins=edges)
    ref_pct = np.maximum(ref_hist / max(ref_hist.sum(), 1), 1e-6)
    new_pct = np.maximum(new_hist / max(new_hist.sum(), 1), 1e-6)
    return float(np.sum((new_pct - ref_pct) * np.log(new_pct / ref_pct)))


def _deployment() -> dict[str, Any]:
    if not DEPLOYMENT_MANIFEST.exists():
        return {"available": False, "path": str(DEPLOYMENT_MANIFEST)}
    try:
        payload = json.loads(DEPLOYMENT_MANIFEST.read_text(encoding="utf-8"))
        return {"available": True, "path": str(DEPLOYMENT_MANIFEST), **payload}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "path": str(DEPLOYMENT_MANIFEST), "error": str(exc)}


def build_health_report(
    ledger: ShadowDecisionLedger | None = None,
    *,
    settle_due: bool = False,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    ledger = ledger or ShadowDecisionLedger()
    settlement = ledger.settle_due(data_dir=data_dir) if settle_due else None
    rows = ledger.read()
    settled = [row for row in rows if row.get("outcome") is not None]
    scored = [
        float(row["calibrated_probability"])
        for row in rows
        if _finite(row.get("calibrated_probability")) is not None
    ]
    recent = scored[-50:]
    reference = scored[:-50]

    by_model_raw: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_model_raw[str(row.get("model") or "unknown")].append(row)
    by_model = {}
    for model, model_rows in sorted(by_model_raw.items()):
        model_settled = [row for row in model_rows if row.get("outcome") is not None]
        returns = [float(row["realized_return"]) for row in model_settled if _finite(row.get("realized_return")) is not None]
        by_model[model] = {
            "events": len(model_rows),
            "settled": len(model_settled),
            "enter": sum(1 for row in model_rows if row.get("state") == "ENTER"),
            "win_rate": (
                sum(float(row["outcome"]) for row in model_settled) / len(model_settled)
                if model_settled else None
            ),
            "mean_realized_return": sum(returns) / len(returns) if returns else None,
            "calibration": calibration_metrics(model_settled),
        }

    calibration = calibration_metrics(settled)
    settlement_ratio = len(settled) / len(rows) if rows else 0.0
    alerts: list[dict[str, str]] = []
    if rows and not settled:
        alerts.append({"severity": "critical", "code": "no_settled_shadow_outcomes"})
    elif rows and settlement_ratio < 0.25:
        alerts.append({"severity": "warning", "code": "low_shadow_settlement_coverage"})
    if calibration.get("n", 0) >= 30 and (calibration.get("ece") or 0.0) > 0.10:
        alerts.append({"severity": "critical", "code": "confidence_ece_high"})
    if calibration.get("n", 0) >= 30 and (calibration.get("brier_skill") or 0.0) <= 0.0:
        alerts.append({"severity": "critical", "code": "confidence_no_brier_skill"})
    psi = _psi(reference, recent)
    if psi is not None and psi > 0.25:
        alerts.append({"severity": "critical", "code": "prediction_distribution_drift"})
    deployment = _deployment()
    if not deployment.get("available"):
        alerts.append({"severity": "critical", "code": "deployment_manifest_missing_or_invalid"})

    try:
        import paper_ledger

        paper = paper_ledger.compute_stats()
    except Exception as exc:  # noqa: BLE001
        paper = {"error": str(exc)}

    return {
        "schema_version": "model-health-v1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "status": "critical" if any(a["severity"] == "critical" for a in alerts) else "warning" if alerts else "ok",
        "deployment": deployment,
        "shadow": {
            **ledger.summary(),
            "settlement_ratio": settlement_ratio,
            "calibration": calibration,
            "prediction_drift": {
                "reference_n": len(reference),
                "recent_n": len(recent),
                "reference_mean": float(np.mean(reference)) if reference else None,
                "recent_mean": float(np.mean(recent)) if recent else None,
                "psi": psi,
            },
            "by_model": by_model,
        },
        "paper": paper,
        "settlement_run": settlement,
        "alerts": alerts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the production model-health report")
    parser.add_argument("--settle-due", action="store_true")
    parser.add_argument("--data-dir")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = build_health_report(settle_due=args.settle_due, data_dir=args.data_dir)
    text = json.dumps(report, indent=2, default=str) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(output)
    print(text, end="")
    return 0 if report["status"] != "critical" else 2


if __name__ == "__main__":
    raise SystemExit(main())
