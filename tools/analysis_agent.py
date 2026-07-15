#!/usr/bin/env python3
"""Analysis Agent — structured Facts → Decision → Suggestion report per ticker.

Reuses the existing runtime stack without modifying any model engine:
  - live_plan.plan_symbol for live features, macro, GEX, risk decision, ticket
  - model_registry.rank_models_for_symbol for per-symbol model leaderboard

Usage:
  .venv/bin/python tools/analysis_agent.py --symbol TSLA --json
  .venv/bin/python tools/analysis_agent.py --symbol AAPL --account 5000 --model v39d_confluence --json
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from typing import Any

import live_plan as _lp
import model_registry as _mr


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _fmt_pct(value: float | None) -> str:
    v = _safe_float(value)
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%"


def _rank_models_for_symbol(symbol: str, top_n: int = 3) -> list[dict[str, Any]]:
    rows = _mr.rank_models_for_symbol(symbol)
    return rows[:top_n]


def _resolve_analysis_model(symbol: str, model: str | None) -> tuple[str | None, dict[str, Any] | None]:
    """Prefer explicit model; else desk specialist routing; else WINNER."""
    if model and str(model).strip() and str(model).strip().lower() not in {"auto", "best", "default"}:
        return str(model).strip(), None
    try:
        rec = _mr.recommend_model(symbol, desk_only=True)
        return rec.get("model"), rec
    except Exception:
        try:
            return _mr.equity_model_for_symbol(symbol), {
                "model": _mr.equity_model_for_symbol(symbol),
                "source": "desk_or_winner",
                "reason": "equity_model_for_symbol fallback",
            }
        except Exception:
            return None, None


def _build_facts(plan: dict[str, Any], ranks: list[dict[str, Any]]) -> dict[str, Any]:
    live = plan.get("live") or {}
    model = plan.get("model") or {}
    macro = plan.get("macro") or {}
    gex = plan.get("gex") or {}

    return {
        "symbol": plan.get("symbol"),
        "price": _safe_float(
            live.get("price") or model.get("price") or gex.get("spot")
        ),
        "asof_utc": plan.get("asof_utc"),
        "live": {
            "price": _safe_float(live.get("price")),
            "vol_z": _safe_float(live.get("vol_z")),
            "atr_pct": _safe_float(live.get("atr_pct")),
            "go_long": bool(live.get("go_long")),
            "go_short": bool(live.get("go_short")),
            "above_vwap": bool(live.get("above_vwap")),
            "swing_uptrend": bool(live.get("swing_uptrend")),
            "macd_positive": bool(live.get("macd_positive")),
            "signal_strength": _safe_float(live.get("signal_strength")),
            "timestamp": live.get("timestamp"),
        },
        "macro": {
            "qqq_ok": bool(macro.get("qqq_ok")),
            "macro_ok": bool(macro.get("macro_ok")),
            "defensive": bool(macro.get("defensive")),
            "qqq_trend": macro.get("qqq_trend"),
            "xlp_spy_ratio_state": macro.get("xlp_spy_ratio_state"),
        },
        "gex": {
            "regime": gex.get("regime", "unknown"),
            "gex_sign": gex.get("gex_sign"),
            "spot": _safe_float(gex.get("spot")),
            "call_wall": _safe_float(gex.get("call_wall")),
            "put_wall": _safe_float(gex.get("put_wall")),
            "approx_flip_strike": _safe_float(gex.get("approx_flip_strike")),
            "squeeze_score": _safe_float(gex.get("squeeze_score")),
            "squeeze_label": gex.get("squeeze_label", "neutral"),
            "expected_move_pct": _safe_float(gex.get("expected_move_pct")),
            "max_pain": _safe_float(gex.get("max_pain")),
        },
        "model": {
            "model": model.get("model") or plan.get("model_used"),
            "ok": bool(model.get("ok")),
            "confidence": _safe_float(model.get("confidence")),
            "setup_ok": bool(model.get("setup_ok")) if model.get("setup_ok") is not None else None,
            "entry": _safe_float(model.get("entry")),
            "stop": _safe_float(model.get("stop")),
            "action_hint": model.get("action_hint"),
            "raw_probability_source": model.get("raw_probability_source"),
        },
        "top_models": ranks,
    }


def _operator_action(plan: dict[str, Any], decision: dict[str, Any], model: dict[str, Any]) -> str:
    """Primary chip label: setup analysis, not the execution-gate string."""
    hint = model.get("action_hint") or decision.get("analysis_action") or (plan.get("ticket") or {}).get("analysis_action")
    if hint and str(hint).strip():
        return str(hint).strip()
    rm = decision.get("risk_manager_action") or decision.get("action")
    mode = decision.get("mode")
    if rm == "enter" and mode == "OPTIONS_ATTACK":
        return "BUY NOW"
    if rm == "enter" and mode == "EQUITY_HEDGE":
        return "BUY NOW"
    if mode == "STAND_ASIDE":
        return "STAND ASIDE"
    if mode in ("FLATTEN", "HALT_NEW"):
        return str(mode)
    return str(rm or mode or "WAIT")


def _build_decision(plan: dict[str, Any]) -> dict[str, Any]:
    decision = plan.get("decision") or {}
    confidence = plan.get("confidence") or {}
    ticket = plan.get("ticket") or {}
    live = plan.get("live") or {}
    model = plan.get("model") or {}

    price = _safe_float(model.get("price") or live.get("price") or plan.get("price"))
    entry = _safe_float(model.get("entry") or live.get("price") or plan.get("price"))
    stop = _safe_float(model.get("stop"))
    max_loss = _safe_float(decision.get("max_loss_dollars") or ticket.get("max_loss_dollars"))
    go_short = bool(live.get("go_short"))
    go_long = bool(live.get("go_long"))
    side = "short" if go_short else ("long" if go_long else "neutral")

    sizing = None
    # Execution math stays valid whenever levels + risk budget exist, even if
    # the confidence gate is ABSTAIN (sizing is illustrative until ENTER).
    if entry is not None and stop is not None and max_loss is not None and max_loss > 0:
        risk_per_share = abs(entry - stop)
        if risk_per_share > 0:
            shares = int(max_loss / risk_per_share)
            sizing = {
                "price": price,
                "entry": entry,
                "stop": stop,
                "risk_per_share": risk_per_share,
                "shares": max(0, shares),
                "notional": shares * entry,
                "target": entry + 2.0 * risk_per_share * (1.0 if side != "short" else -1.0),
                "side": side,
            }

    conf_state = confidence.get("state") or decision.get("confidence_state")
    rm_action = decision.get("risk_manager_action") or decision.get("action")
    exec_action = decision.get("execution_action") or ticket.get("action")
    analysis_action = _operator_action(plan, decision, model)

    return {
        "confidence_state": conf_state,
        "blended_confidence": _safe_float(plan.get("blended_confidence")),
        "mode": decision.get("mode") or ticket.get("mode"),
        "vehicle": decision.get("vehicle") or ticket.get("vehicle"),
        # Primary operator action = setup analysis (matches Analyze/Watch language).
        "action": analysis_action,
        "analysis_action": analysis_action,
        "risk_manager_action": rm_action,
        "execution_action": exec_action,
        "execution_blocked": bool(
            decision.get("execution_blocked")
            or ticket.get("execution_blocked")
            or (conf_state not in (None, "ENTER"))
        ),
        "risk_pct": _safe_float(decision.get("risk_pct") or ticket.get("risk_pct")),
        "max_loss_dollars": max_loss,
        "conviction": _safe_float(decision.get("conviction")),
        "reasons": decision.get("reasons") or confidence.get("reasons") or [],
        "exit_rules": decision.get("exit_rules") or ticket.get("exit_rules") or {},
        "confidence": {
            "state": conf_state,
            "band": confidence.get("band"),
            "raw_probability": _safe_float(confidence.get("raw_probability")),
            "calibrated_probability": _safe_float(confidence.get("calibrated_probability")),
            "size_limit": _safe_float(confidence.get("size_limit")),
            "evidence": confidence.get("evidence", []),
            "failed_checks": confidence.get("failed_checks", []),
            "reasons": confidence.get("reasons", []),
        },
        "sizing": sizing,
    }


def _build_suggestion(plan: dict[str, Any]) -> dict[str, Any]:
    ticket = plan.get("ticket") or {}
    options = plan.get("options") or {}
    return {
        "ticket": {
            "mode": ticket.get("mode"),
            "vehicle": ticket.get("vehicle"),
            "action": ticket.get("action"),
            "analysis_action": ticket.get("analysis_action"),
            "execution_blocked": bool(ticket.get("execution_blocked")),
            "symbol": ticket.get("symbol"),
            "max_loss_dollars": _safe_float(ticket.get("max_loss_dollars")),
            "risk_pct": _safe_float(ticket.get("risk_pct")),
            "conviction": _safe_float(ticket.get("conviction")),
            "steps": ticket.get("steps") or [],
            "exit_rules": ticket.get("exit_rules") or {},
        },
        "options": {
            "action": options.get("action"),
            "structure": options.get("structure"),
            "expiry": options.get("expiry"),
            "dte": options.get("dte"),
            "long_strike": _safe_float(options.get("long_strike")),
            "short_strike": _safe_float(options.get("short_strike")),
            "debit_per_share": _safe_float(options.get("debit_per_share")),
            "max_loss_1_contract": _safe_float(options.get("max_loss_1_contract")),
            "budget": _safe_float(options.get("budget")),
            "reason": options.get("reason"),
        } if options else None,
    }


def _build_rationale_and_drivers(facts: dict[str, Any], decision: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    live = facts.get("live") or {}
    macro = facts.get("macro") or {}
    gex = facts.get("gex") or {}
    model = facts.get("model") or {}
    ticket = (facts.get("suggestion") or {}).get("ticket") or decision

    symbol = facts.get("symbol") or "?"
    price = facts.get("price")
    price_txt = f"${price:.2f}" if price is not None else "unknown price"

    drivers: list[dict[str, Any]] = []

    # Volume / live signal
    vol_z = live.get("vol_z")
    if vol_z is not None:
        drivers.append({
            "name": "Volume expansion",
            "value": f"vol_z={vol_z:.2f}",
            "impact": "positive" if vol_z >= 1.5 else "neutral" if vol_z >= 0.5 else "negative",
        })

    # Trend
    macd_positive = live.get("macd_positive")
    if macd_positive is not None:
        drivers.append({
            "name": "MACD histogram",
            "value": "positive" if macd_positive else "negative",
            "impact": "positive" if macd_positive else "negative",
        })
    above_vwap = live.get("above_vwap")
    if above_vwap is not None:
        drivers.append({
            "name": "VWAP",
            "value": "above" if above_vwap else "below",
            "impact": "positive" if above_vwap else "negative",
        })
    swing_up = live.get("swing_uptrend")
    if swing_up is not None:
        drivers.append({
            "name": "Swing VWAP trend",
            "value": "up" if swing_up else "down",
            "impact": "positive" if swing_up else "negative",
        })

    # Macro
    macro_ok = macro.get("macro_ok")
    if macro_ok is not None:
        drivers.append({
            "name": "Macro regime",
            "value": macro.get("xlp_spy_ratio_state") or ("risk-on" if macro_ok else "defensive"),
            "impact": "positive" if macro_ok else "negative",
        })
    qqq_ok = macro.get("qqq_ok")
    if qqq_ok is not None:
        drivers.append({
            "name": "QQQ trend",
            "value": macro.get("qqq_trend") or ("up" if qqq_ok else "weak"),
            "impact": "positive" if qqq_ok else "negative",
        })

    # GEX
    gex_regime = gex.get("regime")
    if gex_regime and gex_regime != "unknown":
        drivers.append({
            "name": "GEX regime",
            "value": str(gex_regime),
            "impact": "positive" if "bull" in str(gex_regime).lower() else "negative" if "bear" in str(gex_regime).lower() else "neutral",
        })

    # Model
    model_conf = model.get("confidence")
    if model_conf is not None:
        drivers.append({
            "name": "Model confidence",
            "value": f"{model_conf:.2f}",
            "impact": "positive" if model_conf >= 0.65 else "neutral" if model_conf >= 0.50 else "negative",
        })
    if model.get("setup_ok") is not None:
        drivers.append({
            "name": "Model setup",
            "value": "ok" if model.get("setup_ok") else "not ok",
            "impact": "positive" if model.get("setup_ok") else "negative",
        })

    # Confidence gate
    conf_state = decision.get("confidence_state")
    if conf_state:
        drivers.append({
            "name": "Confidence gate",
            "value": conf_state,
            "impact": "positive" if conf_state == "ENTER" else "neutral" if conf_state == "WATCH" else "negative",
        })

    # Build rationale — keep setup analysis and execution gate as separate sentences.
    side = "long" if live.get("go_long") else ("short" if live.get("go_short") else "flat")
    macro_state = macro.get("xlp_spy_ratio_state") or ("risk-on" if macro.get("macro_ok") else "defensive")
    qqq_state = macro.get("qqq_trend") or ("up" if macro.get("qqq_ok") else "weak")
    analysis_action = decision.get("analysis_action") or decision.get("action") or "WAIT"
    conf_state = decision.get("confidence_state") or "ABSTAIN"
    mode = ticket.get("mode") or decision.get("mode") or "STAND_ASIDE"
    rm_action = decision.get("risk_manager_action")

    rationale = (
        f"{symbol} at {price_txt} — live side {side}, "
        f"macro {macro_state}, QQQ {qqq_state}, "
        f"GEX {gex.get('regime', 'unknown')}. "
    )
    if model_conf is not None:
        rationale += f"Model {model.get('model') or 'auto'} structure conf {model_conf:.2f}. "
    setup_ok = model.get("setup_ok")
    if setup_ok is True:
        rationale += "Setup is live. "
    elif setup_ok is False:
        rationale += "Setup not ready. "
    rationale += f"Analysis: {analysis_action}"
    if mode:
        rationale += f" · risk mode {mode}"
    if rm_action and rm_action != ticket.get("action"):
        rationale += f" · risk mgr {rm_action}"
    rationale += f". Execution gate: {conf_state}"
    if decision.get("execution_blocked") or conf_state != "ENTER":
        gate_reasons = (decision.get("confidence") or {}).get("reasons") or []
        if gate_reasons:
            rationale += f" ({', '.join(str(r) for r in gate_reasons[:2])})"
        rationale += " — levels/math may still show; do not size until ENTER."
    else:
        rationale += " — ready to size."

    # Alternatives — only suggest what is still missing (no contradictory prompts).
    alternatives: list[str] = []
    conf_reasons = set(str(r) for r in ((decision.get("confidence") or {}).get("reasons") or []))
    failed = set(str(r) for r in ((decision.get("confidence") or {}).get("failed_checks") or []))

    if conf_state == "ENTER" and (rm_action == "enter" or ticket.get("action") == "enter"):
        alternatives.append("Cut size or stand aside if live vol_z drops below 1.0 or macro flips defensive.")
        alternatives.append("Trail stop per ticket exit rules if position moves in your favor.")
    else:
        if "calibration_artifact_missing" in conf_reasons or "active_calibration" in failed:
            alternatives.append(
                "Execution is blocked by missing active calibration — analysis can still show levels, but do not paper/live size until the gate clears."
            )
        if "market_data_stale_or_unavailable" in conf_reasons or "fresh_data" in failed:
            alternatives.append("Refresh market data; gate is blocked on stale/unavailable feed.")
        needs: list[str] = []
        if not live.get("macd_positive") and side != "short":
            needs.append("MACD turns positive")
        if (live.get("vol_z") or 0) < 1.5:
            needs.append("vol_z ≥ 1.5")
        if not live.get("above_vwap") and side != "short":
            needs.append("price reclaims VWAP")
        if not live.get("go_long") and not live.get("go_short"):
            needs.append("live signal prints go_long/go_short")
        if not macro.get("qqq_ok") and side != "short":
            needs.append("QQQ trend improves")
        if needs:
            alternatives.append("Watch for: " + "; ".join(needs[:4]) + ".")
        else:
            alternatives.append(
                "Tape already has several bullish pieces — wait for specialist/generate size > 0 or a volume surge through the breakout level."
            )
        if setup_ok is False:
            aa = str(analysis_action or "").upper()
            if "AVOID" in aa or "STAND" in aa:
                alternatives.append(
                    "No force entry — cash is fine. Prefer names with BREAKOUT WATCH / PULLBACK ZONE and a clear level."
                )
            else:
                alternatives.append(
                    f"Setup path: follow '{analysis_action}' levels (dip zone / breakout trigger) — not a force entry."
                )

    return rationale, drivers, alternatives


def run_analysis(
    symbol: str,
    account: float = 1000.0,
    model: str | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """Generate one structured Facts → Decision → Suggestion report."""
    if not symbol or not symbol.strip():
        return {"ok": False, "error": "symbol required", "asof_utc": _now()}

    raw_symbol = symbol.strip().upper()
    resolved_model, model_selection = _resolve_analysis_model(raw_symbol, model)
    # live_plan handles both TSLA and TSLA.US; routes desk specialists via model_registry
    plan = _lp.plan_symbol(
        raw_symbol,
        account=account,
        model=resolved_model,
        use_model=True,
    )

    if not plan.get("ok"):
        return {
            "ok": False,
            "symbol": raw_symbol,
            "error": plan.get("error") or "live plan failed",
            "asof_utc": plan.get("asof_utc") or _now(),
            "model_selection": model_selection,
        }

    ranks = _rank_models_for_symbol(raw_symbol, top_n=top_n)
    facts = _build_facts(plan, ranks)
    if model_selection:
        facts["model_selection"] = {
            "model": model_selection.get("model") or resolved_model or plan.get("model_used"),
            "reason": model_selection.get("reason"),
            "source": model_selection.get("source"),
            "specialist": model_selection.get("specialist"),
            "family": model_selection.get("family"),
            "code": model_selection.get("code"),
        }
    decision = _build_decision(plan)
    suggestion = _build_suggestion(plan)
    rationale, drivers, alternatives = _build_rationale_and_drivers(
        {**facts, "suggestion": suggestion}, decision
    )
    suggestion["rationale"] = rationale
    suggestion["drivers"] = drivers
    suggestion["alternatives"] = alternatives
    if model_selection and model_selection.get("source") == "desk_specialist":
        drivers = list(drivers or [])
        drivers.insert(
            0,
            {
                "name": "Model route",
                "value": (
                    f"{model_selection.get('model')} "
                    f"({model_selection.get('specialist') or model_selection.get('family') or 'DNA'})"
                ),
                "impact": "neutral",
            },
        )
        suggestion["drivers"] = drivers

    return {
        "ok": True,
        "symbol": plan.get("symbol") or raw_symbol,
        "asof_utc": plan.get("asof_utc") or _now(),
        "model_used": resolved_model or plan.get("model_used"),
        "model_selection": model_selection,
        "report": {
            "facts": facts,
            "decision": decision,
            "suggestion": suggestion,
        },
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_nan(obj: Any) -> Any:
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _print_report(report: dict[str, Any]) -> None:
    if not report.get("ok"):
        print(f"ERROR: {report.get('error')}")
        return
    r = report["report"]
    facts = r["facts"]
    decision = r["decision"]
    suggestion = r["suggestion"]
    print(f"=== ANALYSIS AGENT  {report['symbol']}  {report['asof_utc']} ===")
    print()
    print("FACTS")
    print(f"  Price: ${facts['price']:.2f}" if facts.get("price") is not None else "  Price: n/a")
    live = facts.get("live") or {}
    print(f"  Live: vol_z={live.get('vol_z')} macd={live.get('macd_positive')} vwap={live.get('above_vwap')} swing={live.get('swing_uptrend')}")
    macro = facts.get("macro") or {}
    print(f"  Macro: QQQ {macro.get('qqq_trend')} / {macro.get('xlp_spy_ratio_state')}")
    gex = facts.get("gex") or {}
    print(f"  GEX: {gex.get('regime')} squeeze={gex.get('squeeze_label')}")
    model = facts.get("model") or {}
    print(f"  Model: {model.get('model')} conf={model.get('confidence')} setup_ok={model.get('setup_ok')}")
    print()
    print("DECISION")
    print(f"  Confidence: {decision.get('confidence_state')} (blended {decision.get('blended_confidence')})")
    print(f"  Mode: {decision.get('mode')} / {decision.get('vehicle')} / {decision.get('action')}")
    print(f"  Risk: {decision.get('risk_pct')}% → max loss ${decision.get('max_loss_dollars')}")
    print()
    print("SUGGESTION")
    ticket = suggestion.get("ticket") or {}
    for step in ticket.get("steps") or []:
        print(f"  • {step}")
    print()
    print(f"RATIONALE: {suggestion.get('rationale')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analysis Agent — structured per-ticker report")
    ap.add_argument("--symbol", type=str, required=True, help="Ticker symbol")
    ap.add_argument("--account", type=float, default=1000.0, help="Account size")
    ap.add_argument("--model", type=str, default="", help="Equity engine (default: WINNER.json)")
    ap.add_argument("--top-n", type=int, default=3, help="Number of top models to include")
    ap.add_argument("--json", action="store_true", help="Emit JSON report")
    args = ap.parse_args(argv)

    report = run_analysis(
        symbol=args.symbol,
        account=args.account,
        model=args.model or None,
        top_n=args.top_n,
    )
    report = _sanitize_nan(report)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
