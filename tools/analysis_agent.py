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


def _build_decision(plan: dict[str, Any]) -> dict[str, Any]:
    decision = plan.get("decision") or {}
    confidence = plan.get("confidence") or {}
    return {
        "confidence_state": confidence.get("state"),
        "blended_confidence": _safe_float(plan.get("blended_confidence")),
        "mode": decision.get("mode"),
        "vehicle": decision.get("vehicle"),
        "action": decision.get("action"),
        "risk_pct": _safe_float(decision.get("risk_pct")),
        "max_loss_dollars": _safe_float(decision.get("max_loss_dollars")),
        "conviction": _safe_float(decision.get("conviction")),
        "reasons": decision.get("reasons") or confidence.get("reasons") or [],
        "exit_rules": decision.get("exit_rules") or {},
    }


def _build_suggestion(plan: dict[str, Any]) -> dict[str, Any]:
    ticket = plan.get("ticket") or {}
    options = plan.get("options") or {}
    return {
        "ticket": {
            "mode": ticket.get("mode"),
            "vehicle": ticket.get("vehicle"),
            "action": ticket.get("action"),
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

    # Build rationale
    side = "long" if live.get("go_long") else ("short" if live.get("go_short") else "neutral")
    macro_state = macro.get("xlp_spy_ratio_state") or ("risk-on" if macro.get("macro_ok") else "defensive")
    qqq_state = macro.get("qqq_trend") or ("up" if macro.get("qqq_ok") else "weak")

    rationale = (
        f"{symbol} at {price_txt} — {side} live signal, "
        f"macro {macro_state}, QQQ {qqq_state}, "
        f"GEX {gex.get('regime', 'unknown')}. "
    )
    if model_conf is not None:
        rationale += f"Model {model.get('model') or 'auto'} confidence {model_conf:.2f}. "
    rationale += (
        f"Decision: {decision.get('confidence_state') or 'ABSTAIN'} → "
        f"{ticket.get('action') or 'stand aside'} "
        f"({ticket.get('mode') or 'STAND_ASIDE'})."
    )

    # Alternatives
    alternatives: list[str] = []
    if decision.get("action") == "enter":
        alternatives.append("Cut size or stand aside if live vol_z drops below 1.0 or macro flips defensive.")
        alternatives.append("Trail stop per ticket exit rules if position moves in your favor.")
    else:
        alternatives.append("Re-evaluate if MACD turns positive, vol_z exceeds 1.5, and QQQ trend improves.")
        alternatives.append("Watch the model confidence gate; ENTER requires setup_ok + macro_ok + confidence gate.")

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
    # live_plan handles both TSLA and TSLA.US
    plan = _lp.plan_symbol(
        raw_symbol,
        account=account,
        model=model or _lp._default_equity_model(),
        use_model=True,
    )

    if not plan.get("ok"):
        return {
            "ok": False,
            "symbol": raw_symbol,
            "error": plan.get("error") or "live plan failed",
            "asof_utc": plan.get("asof_utc") or _now(),
        }

    ranks = _rank_models_for_symbol(raw_symbol, top_n=top_n)
    facts = _build_facts(plan, ranks)
    decision = _build_decision(plan)
    suggestion = _build_suggestion(plan)
    rationale, drivers, alternatives = _build_rationale_and_drivers(
        {**facts, "suggestion": suggestion}, decision
    )
    suggestion["rationale"] = rationale
    suggestion["drivers"] = drivers
    suggestion["alternatives"] = alternatives

    return {
        "ok": True,
        "symbol": plan.get("symbol") or raw_symbol,
        "asof_utc": plan.get("asof_utc") or _now(),
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
