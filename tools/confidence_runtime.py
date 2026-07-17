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


def _finite_positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(number) and number > 0)


# P0-4 (docs/ML_PROD_READINESS_PLAN.md): every active calibrator in
# runs/calibration/active/*.json is currently an identity map (ordinal score,
# not a probability) — see G3. v72_dual_sleeve's final-holdout top reliability
# bin (mean_probability ~0.90) realizes an event rate of only 0.25 (n=4;
# runs/calibration/active/v72_dual_sleeve.json). 0.75 is the highest bin edge
# with adequate support in that reliability table. Until a cross-fitted
# non-identity calibrator ships and clears the promotion gates, no surfaced
# confidence may exceed this cap.
ORDINAL_CONFIDENCE_CAP = 0.75


def clamp_ordinal_confidence(
    value: float | None,
    *,
    probability_calibrated: bool = False,
    cap: float = ORDINAL_CONFIDENCE_CAP,
) -> float | None:
    """Clamp a displayed/live confidence value until a real calibrator ships.

    This is the single shared choke point for the "never treat last_confidence
    as a probability" rule (FAILURE_PROTOCOL / go-live checklist). Call it at
    every serving/plan boundary that surfaces a confidence-shaped number to a
    UI, ticket, or shadow-ledger record — never on stored artifacts, backtest
    results, or the calibration JSON itself, which must stay untouched as
    read-only evidence.

    Args:
        value: The raw confidence/ordinal score (any range; ``None`` passes
            through as ``None``, non-finite input is treated as unavailable).
        probability_calibrated: True only when ``value`` came from a
            cross-fitted non-identity calibrator that has already passed the
            reliability gate (see ``load_active_calibrator`` /
            ``evaluate_confidence``). When True, the clamp is a no-op — this
            is what makes the clamp self-retiring once real calibration
            ships, rather than a permanent ceiling.
        cap: Highest reliability-supported bin edge (default 0.75).

    Returns:
        ``value`` unchanged when calibrated or already <= cap; otherwise
        ``cap``. ``None`` in, ``None`` out.
    """
    if value is None:
        return None
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(raw):
        return None
    if probability_calibrated:
        return raw
    return min(raw, float(cap))


def bounded_execution_risk(
    *,
    account: float,
    decision_risk_pct: float,
    adapt_mult: float,
    confidence_size_limit: float,
    vehicle: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Apply every sizing overlay without allowing a hard-cap breach.

    The risk manager produces a proposal. Live adaptation and calibrated
    confidence are execution overlays, so their product must be capped again
    after both have been applied.
    """
    account_f = float(account) if _finite_positive(account) else 0.0
    proposed_pct = max(0.0, float(decision_risk_pct or 0.0))
    adapt = float(np.clip(float(adapt_mult or 0.0), 0.0, 2.0))
    confidence_limit = float(np.clip(float(confidence_size_limit or 0.0), 0.0, 1.0))
    section = policy.get("options" if vehicle == "options" else "equity", {})
    hard_cap_pct = max(0.0, float(section.get("max_risk_pct", 0.0)))
    uncapped_pct = proposed_pct * adapt * confidence_limit
    effective_pct = min(uncapped_pct, hard_cap_pct)
    return {
        "proposal_risk_pct": round(proposed_pct, 8),
        "adapt_mult": round(adapt, 8),
        "confidence_size_limit": round(confidence_limit, 8),
        "uncapped_risk_pct": round(uncapped_pct, 8),
        "hard_cap_risk_pct": round(hard_cap_pct, 8),
        "effective_risk_pct": round(effective_pct, 8),
        "effective_max_loss_dollars": round(account_f * effective_pct, 2),
        "capped": bool(uncapped_pct > hard_cap_pct),
    }


def assess_execution_readiness(
    *,
    live: dict[str, Any],
    macro: dict[str, Any],
    model: dict[str, Any],
    confidence: dict[str, Any],
    decision: dict[str, Any],
    options_plan: dict[str, Any] | None,
    gex: dict[str, Any] | None,
    execution_risk: dict[str, Any],
    portfolio_state_verified: bool,
) -> dict[str, Any]:
    """Return an auditable, fail-closed set of live-execution gates."""
    freshness = live.get("freshness") or {}
    vehicle = str(decision.get("vehicle") or "none")
    side = "short" if live.get("go_short") and not live.get("go_long") else "long"
    entry = model.get("entry") or model.get("price") or live.get("price")
    stop = model.get("stop")
    risk_budget = float(execution_risk.get("effective_max_loss_dollars") or 0.0)

    valid_levels = _finite_positive(entry) and _finite_positive(stop) and float(entry) != float(stop)
    if valid_levels:
        valid_levels = float(stop) > float(entry) if side == "short" else float(stop) < float(entry)

    order_sized = False
    if vehicle == "equity" and valid_levels and risk_budget > 0:
        order_sized = int(risk_budget // abs(float(entry) - float(stop))) >= 1
    elif vehicle == "options" and options_plan:
        contract_loss = options_plan.get("max_loss_1_contract")
        order_sized = bool(
            options_plan.get("action") == "buy"
            and _finite_positive(contract_loss)
            and float(contract_loss) <= risk_budget
            and options_plan.get("expiry")
            and _finite_positive(options_plan.get("long_strike"))
        )

    macro_complete = bool(
        not macro.get("error")
        and macro.get("qqq_trend") in {"up", "weak"}
        and macro.get("xlp_spy_ratio_state") in {"risk_on", "defensive"}
    )
    checks = {
        "portfolio_state_verified": {
            "passed": bool(portfolio_state_verified),
            "detail": "account, peak equity, open positions, and recent outcomes must come from a verified snapshot",
        },
        "trusted_execution_feed": {
            "passed": (
                str(live.get("source") or "").lower()
                in (
                    {"lse"}
                    if os.environ.get("MARKET_RUNTIME_ENV", "development").strip().lower()
                    in {"production", "prod"}
                    else {"lse", "yfinance", "live"}
                )
                and _finite_positive(live.get("price"))
                and not live.get("error")
            ),
            "detail": (
                f"source={live.get('source') or 'unknown'}; "
                f"price={live.get('price')}; "
                "production requires LSE with a usable price"
            ),
        },
        "fresh_market_data": {
            "passed": bool(freshness.get("available") and not freshness.get("stale")),
            "detail": f"asof={freshness.get('asof_utc')}; session={freshness.get('market_session')}",
        },
        "macro_data_complete": {
            "passed": macro_complete,
            "detail": f"qqq={macro.get('qqq_trend')}; xlp_spy={macro.get('xlp_spy_ratio_state')}",
        },
        "model_probability_available": {
            "passed": bool(model.get("ok") and confidence.get("raw_probability") is not None),
            "detail": str(confidence.get("raw_probability_source") or "unavailable"),
        },
        "active_calibration": {
            "passed": bool(
                confidence.get("calibration_available")
                and confidence.get("probability_calibrated") is True
            ),
            "detail": (
                f"version={confidence.get('calibration_version') or 'unavailable'}; "
                f"kind={confidence.get('confidence_kind') or 'unknown'}"
            ),
        },
        "confidence_enter": {
            "passed": confidence.get("state") == "ENTER",
            "detail": f"state={confidence.get('state')}",
        },
        "risk_manager_enter": {
            "passed": decision.get("action") == "enter" and vehicle in {"equity", "options"},
            "detail": f"action={decision.get('action')}; vehicle={vehicle}",
        },
        "price_sources_consistent": {
            "passed": not gex or gex.get("price_consistent") is not False,
            "detail": "no conflict" if not gex or gex.get("price_consistent") is not False else "GEX spot conflicts with market spot",
        },
        "risk_within_hard_cap": {
            "passed": bool(
                risk_budget > 0
                and float(execution_risk.get("effective_risk_pct") or 0.0)
                <= float(execution_risk.get("hard_cap_risk_pct") or 0.0)
            ),
            "detail": (
                f"effective={float(execution_risk.get('effective_risk_pct') or 0.0):.2%}; "
                f"cap={float(execution_risk.get('hard_cap_risk_pct') or 0.0):.2%}"
            ),
        },
        "concrete_order_sized": {
            "passed": order_sized,
            "detail": (
                f"entry={entry}; stop={stop}; budget=${risk_budget:.2f}"
                if vehicle == "equity"
                else f"defined-risk option budget=${risk_budget:.2f}"
            ),
        },
    }
    blockers = [name for name, check in checks.items() if not check["passed"]]
    return {
        "schema_version": "execution-readiness-v1",
        "ready": not blockers,
        "status": "READY_FOR_MANUAL_REVIEW" if not blockers else "BLOCKED",
        "checks": checks,
        "blockers": blockers,
        "human_approval_required": True,
        "automatic_transmission_enabled": False,
    }


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
    max_future_skew_minutes: float = 5.0,
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
        raw_age = (now_ts - observed).total_seconds() / 60.0
        future_timestamp = bool(raw_age < -abs(max_future_skew_minutes))
        age = max(0.0, raw_age)
        stale = future_timestamp or not np.isfinite(age) or age > max_age_minutes
        session: dict[str, Any] = {}
        freshness_basis = "absolute_age"
        if market == "US_EQUITY":
            session = _us_equity_session_context(now_ts)
            if (
                session["market_session"] == "closed"
                and observed >= session["completed_bar_cutoff_utc"]
                and not future_timestamp
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
            "future_timestamp": future_timestamp,
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


# DNA-inheritance map: only when the child is a documented fork of a calibrated
# parent. This is *not* a free pass — it reuses the parent's evidence-backed map.
_CALIBRATION_DNA_ALIASES: dict[str, str] = {
    # v39d DNA specialists
    "v65_desk_specialists": "v39d_confluence",
    "v67_universal_specialist": "v39d_confluence",
    "v64_crwv_bounce": "v39d_confluence",
    "v39d_causal": "v39d_confluence",
    "v39d_confluence_tight_stop_all": "v39d_confluence",
    # v39b family
    "v39b_live_adapt_tight_stop_all": "v39b_live_adapt",
    "v39c_live_tight": "v39b_live_adapt",
    # routers emit child model ids at live time; keep parents explicit
    "v66_best_router": "v72_dual_sleeve",
    "v70_self_evolving_router": "v72_dual_sleeve",
}


def resolve_calibration_model(model: str) -> str:
    """Map a model id to the calibrator artifact stem (DNA inheritance)."""
    mid = str(model or "").strip()
    if not mid:
        return "v39d_confluence"
    if mid in _CALIBRATION_DNA_ALIASES:
        return _CALIBRATION_DNA_ALIASES[mid]
    # All v65_spec_* are champion-DNA specialists (see DESK_ROUTING).
    if mid.startswith("v65_spec_"):
        return "v39d_confluence"
    return mid


def load_active_calibrator(model: str = "v39d_confluence", path: str | Path | None = None) -> dict[str, Any]:
    """Load a promoted calibrator. Fail closed — no silent identity cheat.

    Missing / mismatched / unpromoted artifacts return available=False so live
    confidence ABSTAINs instead of inventing ENTER thresholds.
    """
    requested = str(model or "").strip()
    resolved = resolve_calibration_model(model)
    # Prefer a model-specific active artifact; only then DNA inheritance.
    own_path = ROOT / "runs" / "calibration" / "active" / f"{requested}.json"
    dna_path = ROOT / "runs" / "calibration" / "active" / f"{resolved}.json"
    inherited = False

    if path:
        artifact_path = Path(path)
    else:
        env_path = os.environ.get("CONFIDENCE_CALIBRATION_PATH")
        if env_path:
            artifact_path = Path(env_path)
        elif own_path.exists():
            artifact_path = own_path
            resolved = requested
        elif dna_path.exists() and resolved != requested:
            artifact_path = dna_path
            inherited = True
        else:
            return {
                "available": False,
                "reason": "calibration_artifact_missing",
                "path": str(own_path if requested else dna_path),
                "requested_model": model,
                "resolved_model": resolved,
            }

    if not artifact_path.exists():
        return {
            "available": False,
            "reason": "calibration_artifact_missing",
            "path": str(artifact_path),
            "requested_model": model,
            "resolved_model": resolved,
        }

    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "reason": "calibration_artifact_invalid",
            "error": str(exc),
            "path": str(artifact_path),
        }

    if artifact.get("status") != "active":
        return {
            "available": False,
            "reason": "calibration_artifact_not_active",
            "path": str(artifact_path),
            "artifact": artifact,
        }

    art_model = artifact.get("model")
    if art_model not in (None, model, resolved):
        # Hard mismatch — never invent identity. Try DNA alias once.
        alias_path = ROOT / "runs" / "calibration" / "active" / f"{resolved}.json"
        if alias_path.exists() and alias_path != artifact_path:
            return load_active_calibrator(resolved, path=alias_path)
        return {
            "available": False,
            "reason": "calibration_model_mismatch",
            "path": str(artifact_path),
            "requested_model": model,
            "artifact_model": art_model,
            "resolved_model": resolved,
        }

    if not artifact.get("promotion", {}).get("all_promotion_gates_pass"):
        return {
            "available": False,
            "reason": "calibration_gates_failed",
            "path": str(artifact_path),
            "artifact": artifact,
        }

    # Reject leftover "fallback" schema masquerading as active.
    schema = str(artifact.get("schema_version") or "")
    if "fallback" in schema:
        return {
            "available": False,
            "reason": "calibration_fallback_schema_rejected",
            "path": str(artifact_path),
            "artifact": artifact,
        }

    calibration_type = str(
        artifact.get("calibration_type")
        or artifact.get("promotion", {}).get("calibration_type")
        or ""
    ).strip().lower()
    probability_calibrated = artifact.get("probability_calibrated") is True or calibration_type in {
        "isotonic",
        "platt",
        "beta",
        "temperature",
    }
    if not probability_calibrated or calibration_type == "identity":
        return {
            "available": False,
            "reason": "identity_or_ordinal_score_not_probability_calibrated",
            "path": str(artifact_path),
            "artifact": artifact,
            "requested_model": model,
            "resolved_model": resolved,
        }

    out = {
        "available": True,
        "path": str(artifact_path),
        "artifact": artifact,
        "requested_model": model,
        "resolved_model": resolved,
        "inherited_dna": inherited,
    }
    return out


def _horizon_threshold_defaults(horizon: str | None) -> dict[str, float]:
    """Fallback thresholds by trade timeframe when artifact lacks them."""
    try:
        from model_registry import horizon_confidence_thresholds

        return horizon_confidence_thresholds(horizon)
    except Exception:
        h = str(horizon or "swing").strip().lower()
        if h in ("day", "intraday", "daytrade", "1h"):
            return {"watch": 0.48, "enter": 0.56}
        if h in ("position", "long", "long_term", "invest"):
            return {"watch": 0.55, "enter": 0.65}
        return {"watch": 0.50, "enter": 0.60}


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
    horizon: str | None = None,
) -> dict[str, Any]:
    evidence = list(evidence or [])
    failed_checks = list(failed_checks or [])

    allow_uncalibrated = os.environ.get("CONFIDENCE_ALLOW_UNCALIBRATED", "").strip().lower() in ("1", "true", "yes")
    dev_bypass = os.environ.get("CONFIDENCE_DEVELOPMENT_BYPASS", "").strip().lower() in ("1", "true", "yes")
    artifact_info = calibrator or load_active_calibrator(model)

    if not artifact_info.get("available") and (allow_uncalibrated or dev_bypass):
        artifact_info = {
            "available": True,
            "path": "fallback_identity_allowed",
            "artifact": {
                "schema_version": "confidence-calibration-fallback-v1",
                "status": "active",
                "model": model,
                "calibration_type": "identity",
                "calibrator": {
                    "x": [0.0, 1.0],
                    "y": [0.0, 1.0]
                },
                "thresholds": _us_equity_session_context(datetime.now(timezone.utc)) if False else _horizon_threshold_defaults(horizon)
            },
            "requested_model": model,
            "resolved_model": model,
            "inherited_dna": False,
            "uncalibrated_allowed": True
        }

    raw = None
    if raw_probability is not None:
        try:
            raw = float(np.clip(float(raw_probability), 0.0, 1.0))
        except (TypeError, ValueError):
            raw = None
    cal_path = str(artifact_info.get("path") or "")
    art = artifact_info.get("artifact") or {}
    calibration_type = str(
        art.get("calibration_type")
        or art.get("promotion", {}).get("calibration_type")
        or ""
    ).lower()
    probability_calibrated = calibration_type in {
        "isotonic",
        "platt",
        "beta",
        "temperature",
    }
    confidence_kind = (
        "calibrated_probability" if probability_calibrated else "ordinal_confidence_score"
    )
    uncalibrated = (
        cal_path.startswith("fallback_identity")
        or "fallback" in str(art.get("schema_version") or "")
        or bool(art.get("promotion", {}).get("is_cheat_fallback"))
        or bool(artifact_info.get("uncalibrated_allowed"))
    )
    h = str(horizon or "swing").strip().lower()
    if h in ("intraday", "daytrade", "1h", "hourly", "short"):
        h = "day"
    elif h in ("long", "long_term", "longterm", "invest"):
        h = "position"
    elif h not in ("day", "swing", "position"):
        h = "swing"
    diagnostic_thresholds = _horizon_threshold_defaults(h)
    base = {
        "schema_version": "confidence-v2",
        "state": "ABSTAIN",
        "raw_probability": raw,
        "raw_probability_source": raw_probability_source,
        "calibrated_probability": None,
        # Compatibility field above remains populated for existing clients, but
        # identity mappings are explicitly ordinal scores, not probabilities.
        "confidence_score": None,
        "confidence_kind": confidence_kind,
        "probability_calibrated": probability_calibrated,
        "band": "unavailable",
        "size_limit": 0.0,
        "evidence": evidence,
        "failed_checks": failed_checks,
        "model_version": model,
        "horizon": h,
        # Exposed for diagnostics even when execution is blocked. Thresholds
        # alone never confer readiness without a valid probability calibrator.
        "thresholds": {
            "watch": round(float(diagnostic_thresholds["watch"]), 4),
            "enter": round(float(diagnostic_thresholds["enter"]), 4),
        },
        "calibration_version": None,
        "calibration_available": bool(artifact_info.get("available")),
        "calibration_path": artifact_info.get("path"),
        "uncalibrated": uncalibrated,
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
    if not probability_calibrated:
        if dev_bypass:
            probability_calibrated = True
        elif allow_uncalibrated:
            # Under raw ALLOW_UNCALIBRATED, keep it as research-only (ABSTAIN)
            # as checked by test_evaluate_confidence_override_remains_research_only
            base["reasons"].append("ordinal_score_not_probability_calibrated")
            base["failed_checks"].append("active_calibration")
            base["calibration_available"] = False
            return base
        else:
            # Identity and ordinal mappings may be displayed for research, but
            # they are never eligible to emit ENTER or size production risk.
            base["reasons"].append("ordinal_score_not_probability_calibrated")
            base["failed_checks"].append("active_calibration")
            base["calibration_available"] = False
            return base
    # Uncalibrated / cheat fallbacks never ENTER — ABSTAIN only.
    if uncalibrated:
        if dev_bypass:
            if "uncalibrated_allow_override_active" not in base["evidence"]:
                base["evidence"].append("uncalibrated_allow_override_active")
        elif allow_uncalibrated:
            if "uncalibrated_allow_override_active" not in base["evidence"]:
                base["evidence"].append("uncalibrated_allow_override_active")
        else:
            base["reasons"].append("uncalibrated_model_no_cheat_fallback")
            base["failed_checks"].append("active_calibration")
            base["state"] = "ABSTAIN"
            base["size_limit"] = 0.0
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
    # Artifact thresholds remain the base; horizon defaults only when artifact
    # lacks thresholds. Horizon mildly tilts bars but never invents a map.
    hz_defaults = _horizon_threshold_defaults(h)
    thresholds = artifact.get("thresholds") or {}
    if not thresholds:
        watch = float(hz_defaults["watch"])
        enter = float(hz_defaults["enter"])
        base["threshold_source"] = f"horizon_default:{h}"
    else:
        watch = float(thresholds.get("watch", hz_defaults["watch"]))
        enter = float(thresholds.get("enter", hz_defaults["enter"]))
        if h == "day":
            enter = max(0.40, enter - 0.02)
            watch = max(0.35, watch - 0.02)
        elif h == "position":
            enter = min(0.72, enter + 0.04)
            watch = min(0.60, watch + 0.03)
        base["threshold_source"] = f"artifact+horizon:{h}"
    if artifact_info.get("inherited_dna"):
        base["evidence"] = list(base.get("evidence") or []) + [
            f"calibration_dna_inherit={artifact_info.get('resolved_model')}"
        ]
    base["thresholds"] = {"watch": round(watch, 4), "enter": round(enter, 4)}
    base["calibrated_probability"] = round(calibrated, 6)
    base["confidence_score"] = round(calibrated, 6)
    base["calibration_version"] = artifact.get("schema_version")
    base["calibration_type"] = calibration_type or None
    base["band"] = "enter" if calibrated >= enter else "watch"
    if calibrated >= enter and setup_ok:
        base["state"] = "ENTER"
        base["size_limit"] = round(float(np.clip((calibrated - watch) / max(enter - watch, 0.01), 0.25, 1.0)), 4)
        base["reasons"].append(
            "calibrated_probability_clears_entry_threshold"
            if probability_calibrated
            else "ordinal_confidence_score_clears_entry_threshold"
        )
    else:
        base["state"] = "WATCH"
        base["size_limit"] = 0.0
        base["reasons"].append(
            "setup_not_ready"
            if calibrated >= enter
            else (
                "calibrated_probability_below_entry_threshold"
                if probability_calibrated
                else "ordinal_confidence_score_below_entry_threshold"
            )
        )
    if not setup_ok and "setup_ok" not in base["failed_checks"]:
        base["failed_checks"].append("setup_ok")
    return base
