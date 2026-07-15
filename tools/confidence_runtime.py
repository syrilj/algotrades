"""Fail-closed runtime adapter for calibrated live confidence."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from evolve.calibration import apply_isotonic


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACTIVE = ROOT / "runs" / "calibration" / "active" / "v39d_confluence.json"


def _us_equity_session_context(now: Any) -> dict[str, Any]:
    """Return a conservative weekday US-equity session window.

    Holidays intentionally fail closed as regular weekdays: a holiday bar can
    be marked stale during nominal market hours, but an old bar is never
    treated as live while a session is expected to be open.
    """
    import pandas as pd

    now_utc = pd.Timestamp(now)
    if now_utc.tzinfo is None:
        now_utc = now_utc.tz_localize("UTC")
    now_utc = now_utc.tz_convert("UTC")
    eastern = now_utc.tz_convert("America/New_York")
    day = eastern.normalize()
    session_open = day + pd.Timedelta(hours=9, minutes=30)
    session_close = day + pd.Timedelta(hours=16)
    is_weekday = day.weekday() < 5
    is_open = bool(is_weekday and session_open <= eastern < session_close)

    next_day = day
    if not (is_weekday and eastern < session_open):
        next_day += pd.Timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += pd.Timedelta(days=1)
    next_open = next_day + pd.Timedelta(hours=9, minutes=30)

    previous_day = day
    if not (is_weekday and eastern >= session_close):
        previous_day -= pd.Timedelta(days=1)
    while previous_day.weekday() >= 5:
        previous_day -= pd.Timedelta(days=1)
    previous_close = previous_day + pd.Timedelta(hours=16)

    return {
        "market_session": "open" if is_open else "closed",
        "next_open_utc": next_open.tz_convert("UTC").isoformat(),
        "previous_close_utc": previous_close.tz_convert("UTC").isoformat(),
        # Hourly feeds often timestamp the last regular bar at its start.
        "completed_bar_cutoff_utc": (previous_close - pd.Timedelta(minutes=90)).tz_convert("UTC"),
    }


def assess_data_freshness(
    timestamp: Any,
    *,
    now: datetime | None = None,
    max_age_minutes: float = 180.0,
    market: str | None = "US_EQUITY",
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    try:
        import pandas as pd

        observed = pd.Timestamp(timestamp)
        if observed.tzinfo is None:
            observed = observed.tz_localize("UTC")
        observed = observed.tz_convert("UTC")
        now_ts = pd.Timestamp(now)
        if now_ts.tzinfo is None:
            now_ts = now_ts.tz_localize("UTC")
        now_ts = now_ts.tz_convert("UTC")
        age = max(0.0, (now_ts - observed).total_seconds() / 60.0)
        stale = not np.isfinite(age) or age > max_age_minutes
        session: dict[str, Any] = {}
        freshness_basis = "absolute_age"
        if market == "US_EQUITY":
            session = _us_equity_session_context(now_ts)
            if (
                session["market_session"] == "closed"
                and observed >= session["completed_bar_cutoff_utc"]
            ):
                stale = False
                freshness_basis = "latest_completed_session"
        session.pop("completed_bar_cutoff_utc", None)
        return {
            "available": True,
            "stale": bool(stale),
            "asof_utc": observed.isoformat(),
            "age_minutes": round(float(age), 2),
            "max_age_minutes": max_age_minutes,
            "freshness_basis": freshness_basis,
            **session,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "stale": True,
            "asof_utc": None,
            "age_minutes": None,
            "max_age_minutes": max_age_minutes,
            "market_session": "unknown",
            "error": str(exc),
        }


def load_active_calibrator(model: str = "v39d_confluence", path: str | Path | None = None) -> dict[str, Any]:
    raw_path = path or os.environ.get("CONFIDENCE_CALIBRATION_PATH") or DEFAULT_ACTIVE
    artifact_path = Path(raw_path)
    if not artifact_path.exists():
        return {"available": False, "reason": "calibration_artifact_missing", "path": str(artifact_path)}
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": "calibration_artifact_invalid", "error": str(exc), "path": str(artifact_path)}
    if artifact.get("status") != "active":
        return {"available": False, "reason": "calibration_artifact_not_active", "path": str(artifact_path), "artifact": artifact}
    if artifact.get("model") not in (None, model):
        return {"available": False, "reason": "calibration_model_mismatch", "path": str(artifact_path), "artifact": artifact}
    if not artifact.get("promotion", {}).get("all_promotion_gates_pass"):
        return {"available": False, "reason": "calibration_gates_failed", "path": str(artifact_path), "artifact": artifact}
    return {"available": True, "path": str(artifact_path), "artifact": artifact}


def evaluate_confidence(
    raw_probability: float | None,
    *,
    model_ok: bool,
    setup_ok: bool,
    freshness: dict[str, Any],
    model: str,
    calibrator: dict[str, Any] | None = None,
    raw_probability_source: str | None = None,
    evidence: list[str] | None = None,
    failed_checks: list[str] | None = None,
) -> dict[str, Any]:
    evidence = list(evidence or [])
    failed_checks = list(failed_checks or [])
    artifact_info = calibrator or load_active_calibrator(model)
    raw = None
    if raw_probability is not None:
        try:
            raw = float(np.clip(float(raw_probability), 0.0, 1.0))
        except (TypeError, ValueError):
            raw = None
    base = {
        "schema_version": "confidence-v1",
        "state": "ABSTAIN",
        "raw_probability": raw,
        "raw_probability_source": raw_probability_source,
        "calibrated_probability": None,
        "band": "unavailable",
        "size_limit": 0.0,
        "evidence": evidence,
        "failed_checks": failed_checks,
        "model_version": model,
        "calibration_version": None,
        "calibration_available": bool(artifact_info.get("available")),
        "calibration_path": artifact_info.get("path"),
        "data_freshness": freshness,
        "reasons": [],
    }
    if not model_ok:
        base["reasons"].append("model_probability_unavailable")
        base["failed_checks"].append("model_ok")
        return base
    if not freshness.get("available") or freshness.get("stale"):
        base["reasons"].append("market_data_stale_or_unavailable")
        base["failed_checks"].append("fresh_data")
        return base
    if not artifact_info.get("available"):
        base["reasons"].append(str(artifact_info.get("reason", "calibration_unavailable")))
        base["failed_checks"].append("active_calibration")
        return base
    if raw is None:
        base["reasons"].append("raw_probability_invalid")
        base["failed_checks"].append("raw_probability")
        return base
    artifact = artifact_info["artifact"]
    try:
        calibrated = float(apply_isotonic([raw], artifact["calibrator"])[0])
    except Exception as exc:  # noqa: BLE001
        base["reasons"].append("calibration_failed")
        base["failed_checks"].append(str(exc))
        return base
    thresholds = artifact.get("thresholds", {})
    watch = float(thresholds.get("watch", 0.50))
    enter = float(thresholds.get("enter", 0.60))
    base["calibrated_probability"] = round(calibrated, 6)
    base["calibration_version"] = artifact.get("schema_version")
    base["band"] = "enter" if calibrated >= enter else "watch"
    if calibrated >= enter and setup_ok:
        base["state"] = "ENTER"
        base["size_limit"] = round(float(np.clip((calibrated - watch) / max(enter - watch, 0.01), 0.25, 1.0)), 4)
        base["reasons"].append("calibrated_probability_clears_entry_threshold")
    else:
        base["state"] = "WATCH"
        base["size_limit"] = 0.0
        base["reasons"].append("setup_not_ready" if calibrated >= enter else "calibrated_probability_below_entry_threshold")
    if not setup_ok and "setup_ok" not in base["failed_checks"]:
        base["failed_checks"].append("setup_ok")
    return base
