"""Manifest and role boundaries for calibrated-confidence experiments."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
ALLOWED_FEATURE_FAMILIES = {"confirmed_pivot", "ohlcv_effort"}
AGENT_ROLES = {
    "coordinator": "Locks dataset, model, feature family, trial count, and promotion gates.",
    "feature": "Proposes one point-in-time feature family and records its causal contract.",
    "validation": "Runs only locked out-of-sample evaluation and cannot edit the candidate artifact.",
    "operator": "Checks ENTER/WATCH/ABSTAIN explanations, freshness, and risk sizing presentation.",
}


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()[:12]
    except Exception:  # noqa: BLE001
        return "unknown"


def make_manifest(
    *,
    model: str = "v39d_confluence",
    feature_family: str = "baseline",
    source: str = "local",
    interval: str = "1H",
    start: str = "2024-08-01",
    end: str = "2026-07-11",
) -> dict[str, Any]:
    if feature_family not in {"baseline", *ALLOWED_FEATURE_FAMILIES}:
        raise ValueError(f"feature_family must be one of baseline, {sorted(ALLOWED_FEATURE_FAMILIES)}")
    created = datetime.now(timezone.utc).isoformat()
    basis = f"{model}|{feature_family}|{source}|{interval}|{start}|{end}|{created}|{_git_sha()}".encode()
    return {
        "schema_version": "confidence-research-v1",
        "trial_id": hashlib.sha256(basis).hexdigest()[:16],
        "created_at_utc": created,
        "git_sha": _git_sha(),
        "model": model,
        "feature_family": feature_family,
        "source": source,
        "interval": interval,
        "codes": WINNER_BAG,
        "window": {"start": start, "end": end},
        "agent_roles": AGENT_ROLES,
        "promotion_gates": {
            "ece_max": 0.05,
            "min_oos_events": 30,
            "sharpe_delta_min": -0.03,
            "drawdown_delta_max": 0.02,
            "action_expectancy_lower_bound_min": 0.0,
        },
        "status": "locked",
    }


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("status") != "locked":
        errors.append("manifest must be locked before evaluation")
    if manifest.get("feature_family") not in {"baseline", *ALLOWED_FEATURE_FAMILIES}:
        errors.append("feature family is not approved")
    if manifest.get("source") != "local":
        errors.append("confidence research must use the local adjusted-data contract")
    if manifest.get("interval") != "1H":
        errors.append("confidence research must use the 1H contract")
    if len(manifest.get("codes", [])) != len(WINNER_BAG):
        errors.append("winner bag changed")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a locked confidence research manifest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="v39d_confluence")
    parser.add_argument("--feature-family", default="baseline")
    args = parser.parse_args(argv)
    manifest = make_manifest(model=args.model, feature_family=args.feature_family)
    path = write_manifest(manifest, args.output)
    print(json.dumps({"path": str(path), "trial_id": manifest["trial_id"], "errors": validate_manifest(manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
