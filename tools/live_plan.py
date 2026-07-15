#!/usr/bin/env python3
"""Live trading plan — one call for a symbol in a live desk environment.

Combines:
  1) Universal live features (vol_z, MACD, VWAP) from services/live_signal
  2) Optional model engine conf from trade_desk / v25 / v23 when available
  3) Macro gates (QQQ trend, XLP/SPY defensive) from winner research
  4) v25 risk_manager vehicle + size (equity hedge vs options attack)
  5) options_picker structure when OPTIONS_ATTACK

Usage:
  python3 tools/live_plan.py --symbol APLD --account 1000 --json
  python3 tools/live_plan.py --symbol IONQ --account 5000 --peak 5200 --history 1,1,-1
  python3 tools/live_plan.py --scan --account 1000 --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "services"))

from live_signal import LiveSignalEngine  # noqa: E402
from services.market_runtime import LSEAdapter  # noqa: E402
from options_picker import propose as options_propose  # noqa: E402
from risk_manager import (  # noqa: E402
    PortfolioState,
    SetupSnapshot,
    decision_to_dict,
    drawdown,
    load_policy,
    plan_entry,
)
from confidence_runtime import (  # noqa: E402
    assess_execution_readiness,
    assess_data_freshness,
    bounded_execution_risk,
    evaluate_confidence,
    load_active_calibrator,
)
from confidence_shadow import ShadowDecisionLedger  # noqa: E402


def _yf_symbol(sym: str) -> str:
    s = sym.strip().upper().replace(".US", "")
    return s


def _daily_close(ticker: str, period: str = "6mo") -> pd.Series:
    t = yf.Ticker(ticker)
    h = t.history(period=period, interval="1d", auto_adjust=True)
    if h is None or h.empty:
        return pd.Series(dtype=float)
    s = h["Close"].astype(float)
    s.index = pd.to_datetime(s.index)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    return s.dropna()


def _lse_symbol(sym: str) -> str:
    s = sym.strip().upper().replace(".US", "")
    # LSE FX convention is CCY/CCY (e.g. EUR/GBP)
    if len(s) == 6 and s.isalpha() and "/" not in s:
        s = f"{s[:3]}/{s[3:]}"
    return s


def _lse_candles_to_df(candles: list[dict]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            df[col] = 0.0
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df


def _daily_close_lse(adapter: LSEAdapter, ticker: str) -> pd.Series:
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%d")
        candles = adapter.client.candles(_lse_symbol(ticker), "1d", start=start, limit=500)
        df = _lse_candles_to_df(candles)
        if not df.empty:
            s = df["Close"].astype(float)
            s.index = pd.to_datetime(s.index)
            if getattr(s.index, "tz", None) is not None:
                s.index = s.index.tz_localize(None)
            return s.dropna()
    except Exception as e:  # noqa: BLE001
        print(f"[live_plan] LSE daily close failed for {ticker}: {e}", file=sys.stderr)
    return pd.Series(dtype=float)


def _intraday_df_lse(adapter: LSEAdapter, symbol: str) -> pd.DataFrame | None:
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
        candles = adapter.client.candles(_lse_symbol(symbol), "1h", start=start, limit=2000)
        df = _lse_candles_to_df(candles)
        if not df.empty and len(df) >= 20:
            return df
    except Exception as e:  # noqa: BLE001
        print(f"[live_plan] LSE intraday failed for {symbol}: {e}", file=sys.stderr)
    return None


def macro_regime(adapter: LSEAdapter | None = None) -> dict[str, Any]:
    """Research-backed macro: QQQ trend + XLP/SPY defensive block (v20b/v23)."""
    out: dict[str, Any] = {
        "qqq_ok": True,
        "macro_ok": True,
        "defensive": False,
        "qqq_trend": None,
        "xlp_spy_ratio_state": None,
        "error": None,
    }
    try:
        if adapter is not None:
            qqq = _daily_close_lse(adapter, "QQQ")
            spy = _daily_close_lse(adapter, "SPY")
            xlp = _daily_close_lse(adapter, "XLP")
        else:
            qqq = _daily_close("QQQ")
            spy = _daily_close("SPY")
            xlp = _daily_close("XLP")
        if len(qqq) >= 50:
            ema20 = qqq.ewm(span=20, adjust=False).mean()
            ema50 = qqq.ewm(span=50, adjust=False).mean()
            out["qqq_ok"] = bool(qqq.iloc[-1] > ema50.iloc[-1] and ema20.iloc[-1] >= ema50.iloc[-1] * 0.98)
            out["qqq_trend"] = "up" if out["qqq_ok"] else "weak"
        if len(spy) >= 50 and len(xlp) >= 50:
            idx = xlp.index.intersection(spy.index)
            ratio = xlp.reindex(idx) / spy.reindex(idx)
            ma20 = ratio.rolling(20, min_periods=20).mean()
            ma50 = ratio.rolling(50, min_periods=50).mean()
            defensive = bool(ratio.iloc[-1] > ma20.iloc[-1] and ma20.iloc[-1] > ma50.iloc[-1])
            out["defensive"] = defensive
            out["macro_ok"] = not defensive
            out["xlp_spy_ratio_state"] = "defensive" if defensive else "risk_on"
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


def _default_equity_model(symbol: str | None = None) -> str:
    try:
        from model_registry import equity_model_for_symbol, equity_default_model

        if symbol:
            return equity_model_for_symbol(symbol)
        return equity_default_model()
    except Exception:
        return "v39b_live_adapt"


def try_model_confidence(symbol: str, model: str | None = None) -> dict[str, Any]:
    """Best-effort model conf from trade_desk analyze (may be slow / fail offline)."""
    model = model or _default_equity_model(symbol)
    try:
        from trade_desk import analyze  # local tools/

        payload = analyze(symbol, account=100_000, risk_pct=0.01, period="60d", model=model)
        state = payload.get("state") or {}
        raw_probability = state.get("hit_probability")
        raw_source = "trade_desk_hit_probability"
        if raw_probability is None:
            raw_probability = state.get("confidence")
            raw_source = "trade_desk_confidence_fallback"
        return {
            "ok": True,
            "model": payload.get("model") or model,
            "confidence": float(raw_probability) if raw_probability is not None else None,
            "raw_probability": float(raw_probability) if raw_probability is not None else None,
            "raw_probability_source": raw_source,
            "setup_ok": state.get("setup_ok"),
            "price": state.get("price"),
            "entry": state.get("entry"),
            "stop": state.get("stop"),
            "action_hint": (payload.get("plan") or {}).get("action"),
            "flags": state.get("flags"),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "model": model, "confidence": None}


def blend_confidence(live_conf: float, model_conf: float | None, go_long: bool, trend_ok: bool) -> float:
    """Blend universal live features with model conf (research: meta sizes, not primary side)."""
    base = float(np.clip(live_conf, 0.0, 1.0))
    if model_conf is not None and np.isfinite(model_conf):
        m = float(np.clip(model_conf, 0.0, 1.0))
        # model gets more weight when available
        conf = 0.45 * base + 0.55 * m
    else:
        conf = base
    if go_long and trend_ok:
        conf = min(1.0, conf + 0.05)
    if not go_long and model_conf is None:
        conf = min(conf, 0.55)
    return float(np.clip(conf, 0.0, 1.0))


def solve_ac_shares(
    max_loss: float,
    entry: float,
    stop: float,
    adv: float,
    vol: float,
    eta: float,
    gamma: float,
    beta: float,
    side: str,
    account: float
) -> tuple[int, float]:
    """Iteratively solve for optimal shares under Almgren-Chriss impact cost."""
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0 or adv <= 0 or vol <= 0 or max_loss <= 0:
        shares = int(max_loss // risk_per_share) if risk_per_share > 0 else 0
        return min(shares, int(account // entry)) if entry > 0 else 0, 0.0

    # Start with uncapped shares
    shares = int(max_loss // risk_per_share)
    shares = min(shares, int(account // entry))
    
    impact = 0.0
    for _ in range(5):
        if shares <= 0:
            break
        rate = min(shares / adv, 1.0)
        temp = eta * (rate ** beta) * vol * entry
        perm = gamma * rate * entry
        impact = temp + perm
        
        effective_risk = risk_per_share + impact
        if effective_risk > 0:
            shares = int(max_loss // effective_risk)
            shares = min(shares, int(account // entry))
        else:
            break
            
    # Recalculate final impact
    if shares > 0:
        rate = min(shares / adv, 1.0)
        impact = (eta * (rate ** beta) * vol * entry) + (gamma * rate * entry)
    else:
        impact = 0.0
        
    return shares, impact


def _build_ib_draft(
    *,
    symbol: str,
    model: str,
    live: dict[str, Any],
    model_info: dict[str, Any],
    decision: Any,
    readiness: dict[str, Any],
    execution_risk: dict[str, Any],
    sizing_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a broker-shaped draft that cannot look executable when blocked."""
    entry = model_info.get("entry") or model_info.get("price") or live.get("price")
    stop = model_info.get("stop")
    max_loss = float(execution_risk.get("effective_max_loss_dollars") or 0.0)
    qty = 0
    try:
        risk_per_share = abs(float(entry) - float(stop))
        if readiness.get("ready") and decision.vehicle == "equity" and risk_per_share > 0:
            if sizing_info and sizing_info.get("use_impact"):
                qty = sizing_info["shares"]
                entry = sizing_info["effective_entry"]
            else:
                qty = int(max_loss // risk_per_share)
    except (TypeError, ValueError):
        qty = 0
    draft_ready = bool(readiness.get("ready") and decision.vehicle == "equity" and qty > 0)
    blockers = list(readiness.get("blockers") or [])
    if decision.vehicle != "equity":
        blockers.append("broker_draft_equity_only")
    side = "FLAT"
    if draft_ready:
        side = "SELL" if live.get("go_short") and not live.get("go_long") else "BUY"
    return {
        "status": "READY_FOR_MANUAL_REVIEW" if draft_ready else "BLOCKED",
        "transmit_allowed": False,
        "human_approval_required": True,
        "execution_blocked": not draft_ready,
        "blockers": blockers,
        "symbol": symbol,
        "side": side,
        "qty": max(0, qty),
        "order_type": "LMT",
        "limit": entry,
        "stop": stop,
        "tif": "DAY",
        "model": model_info.get("model") or model,
        "vehicle": decision.vehicle,
        "mode": decision.mode,
        "max_loss_dollars": max_loss,
    }


def plan_symbol(
    symbol: str,
    account: float = 1000.0,
    peak: float | None = None,
    history: list[float] | None = None,
    model: str | None = None,
    use_model: bool = True,
    open_equity: int = 0,
    open_options: int = 0,
    portfolio_state_verified: bool = False,
    lse_adapter: LSEAdapter | None = None,
    use_impact: bool = False,
    ac_eta: float = 0.1,
    ac_gamma: float = 0.0,
    ac_beta: float = 0.5,
    ac_adv_days: int = 20,
    ac_vol_days: int = 20,
) -> dict[str, Any]:
    model = model or _default_equity_model(symbol)
    pol = load_policy()
    eng = LiveSignalEngine()
    portfolio_snapshot_valid = bool(
        portfolio_state_verified
        and account > 0
        and peak is not None
        and peak >= account
        and open_equity >= 0
        and open_options >= 0
    )

    # Prefer LSE when an adapter is available, otherwise live_signal fetches yfinance.
    adapter = lse_adapter
    if adapter is None and os.environ.get("LSE_API_KEY"):
        adapter = LSEAdapter(api_key=os.environ.get("LSE_API_KEY"))
    df = _intraday_df_lse(adapter, symbol) if adapter is not None else None
    if df is not None and (df.empty or len(df) < 20):
        df = None
    live = eng.analyze(symbol, df=df)
    live["source"] = "lse" if df is not None else "yfinance"
    live["interval"] = "1h"
    if live.get("error"):
        return {
            "ok": False,
            "symbol": symbol,
            "error": live.get("error"),
            "confidence": evaluate_confidence(
                None,
                model_ok=False,
                setup_ok=False,
                freshness=assess_data_freshness(None),
                model=model,
            ),
            "asof_utc": datetime.now(timezone.utc).isoformat(),
        }

    freshness = assess_data_freshness(live.get("timestamp"), market="US_EQUITY")
    live["freshness"] = freshness
    live["market_session"] = freshness.get("market_session", "unknown")

    macro = macro_regime(adapter)
    model_info: dict[str, Any] = {"ok": False, "skipped": not use_model}
    if use_model:
        # trade_desk understands auto / WINNER ids
        model_info = try_model_confidence(
            symbol, model="auto" if model in ("", "auto") else model
        )

    go_long = bool(live.get("go_long"))
    go_short = bool(live.get("go_short"))
    soft_long = bool(live.get("soft_long"))
    soft_short = bool(live.get("soft_short"))

    # Side from explicit signals only. Flat tape is neutral-long for desk risk
    # (equity path is long-only) — never invent a short bias just because trend
    # is soft. That was flipping flat names into "macro bullish — stand aside
    # for shorts" while analysis still showed long-biased structure.
    if go_short and not go_long:
        side = "short"
        trend_ok = not bool(
            live.get("swing_uptrend") or live.get("above_vwap") or live.get("macd_positive")
        )
        live_conf = float(live.get("confidence_bear") or 0.0)
        model_conf = model_info.get("confidence")
        model_conf_bear = 1.0 - model_conf if (model_conf is not None) else None
        conf = blend_confidence(
            live_conf,
            model_conf_bear if model_info.get("ok") else None,
            go_short,
            trend_ok,
        )
        setup_trend_ok = trend_ok and bool(
            (not live.get("macd_positive")) or go_short or soft_short or conf >= 0.65
        )
    else:
        side = "long"
        trend_ok = bool(
            live.get("swing_uptrend") or live.get("above_vwap") or live.get("macd_positive")
        )
        live_conf = float(live.get("confidence") or 0.0)
        model_conf = model_info.get("confidence")
        conf = blend_confidence(
            live_conf,
            model_conf if model_info.get("ok") else None,
            go_long,
            trend_ok,
        )
        # Flat long: keep structure confidence for display. setup_for_confidence
        # accepts hard go_long, soft_long, or model setup_ok (desk classic_buy).
        setup_trend_ok = trend_ok and bool(
            live.get("macd_positive") or go_long or soft_long or conf >= 0.65
        )

    model_probability = model_info.get("raw_probability") if model_info.get("ok") else None
    model_setup_ok = bool(model_info.get("setup_ok")) if model_info.get("ok") else False
    # Hard go_* still preferred; soft live + model setup unlock WATCH→ENTER when
    # calibrated probability clears the threshold (execution readiness remains fail-closed).
    side_ready = bool(go_long or go_short or soft_long or soft_short or model_setup_ok)
    setup_for_confidence = bool(
        setup_trend_ok
        and side_ready
        and bool(macro.get("macro_ok", True))
    )
    # Resolve real engine id for calibration (never pass "auto" into the artifact matcher).
    cal_model = str(
        (model_info.get("model") if model_info.get("ok") else None)
        or (model if model not in ("", "auto", None) else "")
        or _default_equity_model(symbol)
    )
    if cal_model in ("", "auto"):
        cal_model = _default_equity_model(symbol)
    confidence = evaluate_confidence(
        model_probability,
        model_ok=bool(model_info.get("ok")) and model_probability is not None,
        setup_ok=setup_for_confidence,
        freshness=freshness,
        model=cal_model,
        calibrator=load_active_calibrator(cal_model),
        raw_probability_source=model_info.get("raw_probability_source"),
        evidence=[
            f"side={side}",
            f"vol_z={live.get('vol_z')}",
            f"go_long={go_long}",
            f"soft_long={soft_long}",
            f"model_setup_ok={model_setup_ok}",
            f"macd_positive={live.get('macd_positive')}",
            f"above_vwap={live.get('above_vwap')}",
            f"swing_uptrend={live.get('swing_uptrend')}",
            f"macro_ok={macro.get('macro_ok')}",
            f"cal_model={cal_model}",
        ],
        failed_checks=list(model_info.get("flags") or []) if isinstance(model_info.get("flags"), list) else [],
    )

    # Options affordability heuristic from research playbook
    ysym = _yf_symbol(symbol)
    options_affordable = ysym not in {"MU"}  # MU ATM often too rich on $1k
    if account < 1500 and ysym in {"TSLA", "NVDA", "META", "AVGO"}:
        options_affordable = account >= 2000  # spreads only on larger book; still allow try

    # Fetch option positioning & GEX
    gex_data = {}
    try:
        from gamma_exposure import compute_gamma_exposure
        gex_src = "lse" if os.environ.get("LSE_API_KEY") else "oi"
        gex_data = compute_gamma_exposure(symbol, spot_source="auto", source=gex_src)
    except Exception:
        try:
            from gamma_exposure import compute_gamma_exposure
            gex_data = compute_gamma_exposure(symbol, spot_source="yfinance", source="oi")
        except Exception:
            pass

    setup = SetupSnapshot(
        symbol=ysym,
        model_conf=conf,
        vol_z=float(live.get("vol_z") or 0.0),
        trend_ok=setup_trend_ok,
        macro_ok=bool(macro.get("macro_ok", True)),
        qqq_ok=bool(macro.get("qqq_ok", True)),
        options_affordable=options_affordable,
        liquidity_ok=True,
        side=side,
        gex_regime=str(gex_data.get("regime", "flat")),
        gex_sign=int(gex_data.get("gex_sign", 0)),
        approx_flip_strike=gex_data.get("approx_flip_strike"),
        call_wall=gex_data.get("call_wall"),
        put_wall=gex_data.get("put_wall"),
        squeeze_score=float(gex_data.get("squeeze_score", 0.0)),
        squeeze_label=str(gex_data.get("squeeze_label", "neutral")),
        spot_price=gex_data.get("spot"),
    )
    peak_eq = float(peak if peak and peak > 0 else account)
    state = PortfolioState(
        equity=float(account),
        peak=peak_eq,
        open_equity_n=open_equity,
        open_options_n=open_options,
        trade_pnl_history=list(history or []),
    )
    decision = plan_entry(setup, state, pol)
    dec = decision_to_dict(decision)
    dec["risk_manager_action"] = dec.get("action")
    dec["confidence_state"] = confidence["state"]
    dec["confidence_reasons"] = confidence.get("reasons", [])

    options_plan = None
    if decision.mode == "OPTIONS_ATTACK" and decision.action == "enter":
        try:
            options_plan = options_propose(
                ysym,
                account=account,
                max_risk_pct=float(decision.risk_pct),
                prefer_spread=True,
                side=setup.side,
            )
        except Exception as e:  # noqa: BLE001
            options_plan = {"error": str(e), "action": "skip"}

    # Operator ticket
    ticket = {
        "mode": decision.mode,
        "vehicle": decision.vehicle,
        "action": decision.action,
        "symbol": ysym,
        "max_loss_dollars": decision.max_loss_dollars,
        "risk_pct": decision.risk_pct,
        "size_mult": decision.size_mult,
        "conviction": decision.conviction,
        "exit_rules": decision.exit_rules,
        "steps": [],
        "confidence_state": confidence["state"],
        "confidence_size_limit": confidence["size_limit"],
    }
    if decision.mode == "OPTIONS_ATTACK" and options_plan and options_plan.get("action") == "buy":
        ticket["steps"] = [
            f"Buy {options_plan.get('structure')} {ysym} exp {options_plan.get('expiry')}",
            f"Long {options_plan.get('long_strike')} / short {options_plan.get('short_strike')}",
            f"Debit ~${options_plan.get('debit_per_share')} · max loss ${options_plan.get('max_loss_1_contract')} (budget ${options_plan.get('budget')})",
            "Tape exit: cut −30% · trail after +40% · flat by 5 DTE",
        ]
    elif decision.mode == "OPTIONS_ATTACK" and options_plan and options_plan.get("action") == "skip":
        ticket["steps"] = [
            f"Options skipped: {options_plan.get('reason')}",
            "Fall back to EQUITY_HEDGE or stand aside — do not force lottery premium",
        ]
        # Downgrade to equity if model/live still ok
        if setup.model_conf >= 0.60 and setup.trend_ok and setup.macro_ok:
            setup2 = SetupSnapshot(**{**setup.__dict__, "options_affordable": False})
            decision2 = plan_entry(setup2, state, pol)
            decision = decision2
            dec = decision_to_dict(decision2)
            dec["risk_manager_action"] = dec.get("action")
            dec["confidence_state"] = confidence["state"]
            dec["confidence_reasons"] = confidence.get("reasons", [])
            ticket["mode"] = decision2.mode
            ticket["vehicle"] = decision2.vehicle
            ticket["action"] = decision2.action
            ticket["max_loss_dollars"] = decision2.max_loss_dollars
            ticket["risk_pct"] = decision2.risk_pct
            ticket["steps"].append(f"Auto-fallback → {decision2.mode}")
            if decision2.mode == "EQUITY_HEDGE":
                ticket["steps"].append(
                    f"Equity risk {decision2.risk_pct:.1%} → max loss ${decision2.max_loss_dollars:.0f}; use desk stops"
                )
    elif decision.mode == "EQUITY_HEDGE":
        entry = (model_info.get("entry") if model_info.get("ok") else None) or live.get("price")
        stop = model_info.get("stop") if model_info.get("ok") else None
        ticket["steps"] = [
            f"EQUITY_HEDGE {ysym} — park capital until A+ options",
            f"Risk {decision.risk_pct:.1%} of book → max loss ${decision.max_loss_dollars:.0f}",
            f"Entry ref ~{entry} stop ~{stop or 'ATR from desk'}",
            "Exit if macro flips defensive or model side off",
        ]
    elif decision.mode == "STAND_ASIDE":
        # Use real risk-manager reasons — never invent "defensive macro".
        rm_reasons = [str(r) for r in (decision.reasons or []) if r]
        if not rm_reasons:
            rm_reasons = ["No tradeable edge — cash is a position"]
        ticket["steps"] = rm_reasons[:4]
    elif decision.mode in ("FLATTEN", "HALT_NEW"):
        ticket["steps"] = list(decision.reasons)

    # Live adaptation is an execution overlay. It is bounded again below after
    # calibrated confidence is applied, so it can never breach the hard policy.
    adapt_mult = 1.0
    adapt_snap: dict[str, Any] = {}
    try:
        import live_adapt as la

        adapt_mult = float(la.size_mult_for(model, ysym))
        adapt_snap = la.snapshot()
        ticket["live_adapt_mult"] = adapt_mult
    except Exception:
        pass

    # Confidence layer is fail-closed for *execution* only.
    # Keep risk-manager action/mode/reasons intact so analysis UI does not
    # contradict the setup narrative (e.g. BUY NOW facts + ABSTAIN gate).
    rm_action = dec.get("action")
    dec["risk_manager_action"] = rm_action
    if confidence["state"] != "ENTER":
        ticket["action"] = confidence["state"].lower()
        ticket["execution_blocked"] = True
        ticket["steps"] = [
            f"Execution gate: {confidence['state']}",
            *[str(reason) for reason in confidence.get("reasons", [])],
            *ticket.get("steps", []),
        ]
        dec["execution_action"] = confidence["state"].lower()
        dec["execution_blocked"] = True
        # Do NOT overwrite dec["action"] / mode — those are analysis truth.
    else:
        ticket["execution_blocked"] = False
        dec["execution_action"] = rm_action
        dec["execution_blocked"] = False

    # Operator-facing setup label from the model plan (BUY NOW / WATCH / AVOID).
    mode_now = ticket.get("mode") or dec.get("mode")
    analysis_action = model_info.get("action_hint") or (
        "BUY NOW"
        if rm_action == "enter" and mode_now in ("EQUITY_HEDGE", "OPTIONS_ATTACK")
        else "STAND ASIDE"
        if mode_now == "STAND_ASIDE"
        else str(mode_now or "WAIT")
    )
    dec["analysis_action"] = analysis_action
    ticket["analysis_action"] = analysis_action
    dec["mode"] = mode_now
    dec["confidence_state"] = confidence["state"]

    execution_risk = bounded_execution_risk(
        account=account,
        decision_risk_pct=float(decision.risk_pct),
        adapt_mult=adapt_mult,
        confidence_size_limit=float(confidence.get("size_limit") or 0.0),
        vehicle=decision.vehicle,
        policy=pol,
    )
    ticket["proposed_risk_pct"] = float(decision.risk_pct)
    ticket["proposed_max_loss_dollars"] = float(decision.max_loss_dollars)
    ticket["risk_pct_adapted"] = execution_risk["effective_risk_pct"]
    ticket["max_loss_adapted"] = execution_risk["effective_max_loss_dollars"]
    # The executable fields always reflect the fully gated, post-cap budget.
    ticket["risk_pct"] = execution_risk["effective_risk_pct"]
    ticket["max_loss_dollars"] = execution_risk["effective_max_loss_dollars"]

    readiness = assess_execution_readiness(
        live=live,
        macro=macro,
        model=model_info,
        confidence=confidence,
        decision=dec,
        options_plan=options_plan,
        gex=gex_data,
        execution_risk=execution_risk,
        portfolio_state_verified=portfolio_snapshot_valid,
    )
    ticket["execution_readiness"] = readiness["status"]
    ticket["execution_blocked"] = not readiness["ready"]
    dec["execution_blocked"] = not readiness["ready"]
    if not readiness["ready"]:
        ticket["action"] = "abstain"
        dec["execution_action"] = "abstain"
        ticket["steps"] = [
            f"Execution readiness: {readiness['status']}",
            *[f"Blocked: {name}" for name in readiness["blockers"]],
            *ticket.get("steps", []),
        ]

    # Solve shares under AC impact cost
    sizing_info = None
    entry_val = (model_info.get("entry") if model_info.get("ok") else None) or live.get("price")
    stop_val = model_info.get("stop") if model_info.get("ok") else None
    if decision.vehicle == "equity" and entry_val is not None and stop_val is not None:
        try:
            import impact_model
            # Estimate ADV and Volatility
            bars_per_day = 7.0
            df_for_est = df
            if df_for_est is None:
                try:
                    t = yf.Ticker(_yf_symbol(symbol))
                    df_yf = t.history(period="60d", interval="1h", auto_adjust=True)
                    if df_yf is not None and not df_yf.empty:
                        df_yf = df_yf.rename(columns={"Volume": "volume", "Close": "close"})
                        df_for_est = df_yf
                except Exception:
                    pass

            adv = 0.0
            vol = 0.0
            if df_for_est is not None and not df_for_est.empty:
                adv = impact_model.estimate_adv(df_for_est, bars_per_day, ac_adv_days)
                vol = impact_model.estimate_volatility(df_for_est, bars_per_day, ac_vol_days)
            
            side = "short" if go_short and not go_long else "long"
            shares, impact = solve_ac_shares(
                max_loss=ticket["max_loss_dollars"],
                entry=entry_val,
                stop=stop_val,
                adv=adv,
                vol=vol,
                eta=ac_eta if use_impact else 0.0,
                gamma=ac_gamma if use_impact else 0.0,
                beta=ac_beta,
                side=side,
                account=account
            )
            
            original_shares = int(ticket["max_loss_dollars"] // abs(entry_val - stop_val)) if abs(entry_val - stop_val) > 0 else 0
            original_shares = min(original_shares, int(account // entry_val)) if entry_val > 0 else 0
            
            eff_entry = entry_val + impact if side == "long" else entry_val - impact
            eff_risk = abs(eff_entry - stop_val)
            
            sizing_info = {
                "shares": shares,
                "entry": entry_val,
                "effective_entry": eff_entry,
                "stop": stop_val,
                "risk_per_share": abs(entry_val - stop_val),
                "effective_risk_per_share": eff_risk,
                "dollar_risk": shares * eff_risk,
                "impact_per_share": impact,
                "total_impact_cost": shares * impact,
                "adv": adv,
                "volatility": vol,
                "use_impact": use_impact,
                "original_shares": original_shares,
            }
        except Exception as e:
            risk_per_share = abs(entry_val - stop_val)
            shares = int(ticket["max_loss_dollars"] // risk_per_share) if risk_per_share > 0 else 0
            shares = min(shares, int(account // entry_val)) if entry_val > 0 else 0
            sizing_info = {
                "shares": shares,
                "entry": entry_val,
                "effective_entry": entry_val,
                "stop": stop_val,
                "risk_per_share": risk_per_share,
                "effective_risk_per_share": risk_per_share,
                "dollar_risk": shares * risk_per_share,
                "impact_per_share": 0.0,
                "total_impact_cost": 0.0,
                "adv": 0.0,
                "volatility": 0.0,
                "use_impact": False,
                "original_shares": shares,
                "error": str(e)
            }

    # The broker-shaped file is deliberately inert unless all readiness gates
    # pass, and even a ready draft still requires human review/transmission.
    try:
        import live_adapt as la

        la.export_ib_ticket(
            _build_ib_draft(
                symbol=ysym,
                model=model,
                live=live,
                model_info=model_info,
                decision=decision,
                readiness=readiness,
                execution_risk=execution_risk,
                sizing_info=sizing_info,
            )
        )
    except Exception:
        pass

    out = {
        "ok": True,
        "symbol": ysym,
        "account": account,
        "peak": peak_eq,
        "drawdown": round(drawdown(account, peak_eq), 4),
        "portfolio_state_verified": portfolio_snapshot_valid,
        "live": live,
        "macro": macro,
        "model": model_info,
        "gex": gex_data,
        "blended_confidence": round(conf, 4),
        "confidence": confidence,
        "decision": dec,
        "options": options_plan,
        "ticket": ticket,
        "live_adapt": {"size_mult": adapt_mult, "snapshot": adapt_snap},
        "execution_risk": execution_risk,
        "execution_readiness": readiness,
        "ib_ticket_path": "runs/live_adapt/LAST_TICKET.json",
        "policy_version": pol.get("version"),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "live_ready": readiness["ready"],
        "decision_support_ready": confidence["state"] != "ABSTAIN",
        "sizing": sizing_info,
        "notes": [
            "SIDE research DNA: v23/v20b macro + vol_z conviction; vehicle from v25 risk",
            "Do not retune primary rules on today's tape; only size/vehicle react",
        ],
    }
    try:
        out["shadow_event_id"] = ShadowDecisionLedger().record(
            {
                "symbol": ysym,
                "model": model,
                "state": confidence["state"],
                "ticket_action": ticket.get("action"),
                "raw_probability": confidence.get("raw_probability"),
                "calibrated_probability": confidence.get("calibrated_probability"),
                "size_limit": confidence.get("size_limit"),
                "data_freshness": confidence.get("data_freshness"),
                "asof_utc": out["asof_utc"],
            }
        )
    except Exception:
        out["shadow_event_id"] = None
    return out


DEFAULT_SCAN = [
    "APLD", "IONQ", "TSLA", "MU", "NVDA", "AMD", "META", "AVGO", "SMCI", "HOOD",
]


def _scan_action_rank(row: dict[str, Any]) -> int:
    """Lower = better operator play. Prefer buys / watches over stand-aside."""
    analysis = str(row.get("analysis_action") or "").upper()
    conf_state = str(row.get("confidence_state") or "").upper()
    mode = str(row.get("mode") or "").upper()
    if "BUY NOW" in analysis or "BUY BREAKOUT" in analysis:
        return 0
    if conf_state == "ENTER" and mode in ("OPTIONS_ATTACK", "EQUITY_HEDGE"):
        return 1
    if "BREAKOUT WATCH" in analysis or "PULLBACK" in analysis:
        return 2
    if conf_state == "WATCH":
        return 3
    if mode in ("OPTIONS_ATTACK", "EQUITY_HEDGE"):
        return 4
    if "WAIT" in analysis or "ALMOST" in analysis:
        return 5
    if mode == "STAND_ASIDE":
        return 6
    if "AVOID" in analysis:
        return 7
    return 8


def scan(
    symbols: list[str] | None = None,
    account: float = 1000.0,
    peak: float | None = None,
    use_model: bool = True,
    lse_adapter: LSEAdapter | None = None,
) -> dict[str, Any]:
    """Scan universe for ranked plays.

    Default uses per-symbol model analyze so the board can surface BUY / WATCH
    levels. Pass ``use_model=False`` for a fast live-features-only pass.
    """
    syms = symbols or DEFAULT_SCAN
    macro = macro_regime(lse_adapter)
    rows = []
    for s in syms:
        plan = plan_symbol(
            s,
            account=account,
            peak=peak,
            use_model=use_model,
            model=_default_equity_model(s),
            lse_adapter=lse_adapter,
        )
        if not plan.get("ok"):
            continue
        t = plan["ticket"]
        dec = plan.get("decision") or {}
        conf = plan.get("confidence") or {}
        live = plan.get("live") or {}
        analysis_action = (
            t.get("analysis_action")
            or dec.get("analysis_action")
            or (plan.get("model") or {}).get("action_hint")
            or t.get("mode")
        )
        rows.append({
            "symbol": plan["symbol"],
            "mode": t["mode"],
            "vehicle": t["vehicle"],
            "action": t["action"],
            "analysis_action": analysis_action,
            "conviction": t.get("conviction"),
            "risk_pct": t.get("risk_pct"),
            "max_loss_dollars": t.get("max_loss_dollars"),
            "vol_z": live.get("vol_z"),
            "price": live.get("price"),
            "go_long": live.get("go_long"),
            "soft_long": live.get("soft_long"),
            "blended_confidence": plan.get("blended_confidence"),
            "confidence_state": conf.get("state"),
            "calibrated_probability": conf.get("calibrated_probability"),
            "uncalibrated": conf.get("uncalibrated"),
            "do_next": (t.get("steps") or [None])[0],
        })
    # rank: operator plays first, then conviction / calibrated conf
    rows.sort(
        key=lambda r: (
            _scan_action_rank(r),
            -(float(r.get("calibrated_probability") or r.get("blended_confidence") or 0.0)),
            -(float(r.get("conviction") or 0.0)),
        )
    )
    return {
        "ok": True,
        "account": account,
        "macro": macro,
        "count": len(rows),
        "use_model": use_model,
        "rows": rows,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live trading plan (hybrid desk + WINNER equity)")
    ap.add_argument("--symbol", type=str, default="")
    ap.add_argument("--account", type=float, default=1000.0)
    ap.add_argument("--peak", type=float, default=0.0)
    ap.add_argument("--history", type=str, default="")
    ap.add_argument("--open-equity", type=int, default=0)
    ap.add_argument("--open-options", type=int, default=0)
    ap.add_argument(
        "--portfolio-verified",
        action="store_true",
        help="Assert account/peak/open-position inputs came from a verified portfolio snapshot",
    )
    ap.add_argument(
        "--model",
        type=str,
        default="",
        help="Equity engine (default: WINNER.json via equity_default_model)",
    )
    ap.add_argument("--no-model", action="store_true", help="Skip trade_desk model analyze (faster)")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--symbols", type=str, default="", help="Comma list for scan")
    ap.add_argument("--use-impact", action="store_true")
    ap.add_argument("--ac-eta", type=float, default=0.1)
    ap.add_argument("--ac-gamma", type=float, default=0.0)
    ap.add_argument("--ac-beta", type=float, default=0.5)
    ap.add_argument("--ac-adv-days", type=int, default=20)
    ap.add_argument("--ac-vol-days", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not str(args.model).strip():
        args.model = _default_equity_model()

    hist = []
    if args.history.strip():
        hist = [float(x) for x in args.history.split(",") if x.strip()]

    lse_api_key = os.environ.get("LSE_API_KEY")
    lse_adapter = LSEAdapter(api_key=lse_api_key) if lse_api_key else None

    if args.scan:
        syms = [s.strip() for s in args.symbols.split(",") if s.strip()] or None
        # Default: model-aware ranked plays. --no-model for live-features-only speed.
        out = scan(
            syms,
            account=args.account,
            peak=args.peak or None,
            use_model=not args.no_model,
            lse_adapter=lse_adapter,
        )
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(
                f"SCAN account=${args.account:,.0f}  models={'on' if not args.no_model else 'off'}  "
                f"macro={out['macro'].get('xlp_spy_ratio_state')} qqq={out['macro'].get('qqq_trend')}"
            )
            for r in out["rows"][:15]:
                print(
                    f"  {r['symbol']:6} {(r.get('analysis_action') or r['mode']):18} "
                    f"{r.get('confidence_state') or '—':8} "
                    f"cal={r.get('calibrated_probability') or 0:.2f} "
                    f"volz={r.get('vol_z')} px={r.get('price')}"
                )
        return 0

    if not args.symbol:
        print("Pass --symbol or --scan", file=sys.stderr)
        return 2

    out = plan_symbol(
        args.symbol,
        account=args.account,
        peak=args.peak or None,
        history=hist,
        model=args.model,
        use_model=not args.no_model,
        open_equity=args.open_equity,
        open_options=args.open_options,
        portfolio_state_verified=args.portfolio_verified,
        lse_adapter=lse_adapter,
        use_impact=args.use_impact,
        ac_eta=args.ac_eta,
        ac_gamma=args.ac_gamma,
        ac_beta=args.ac_beta,
        ac_adv_days=args.ac_adv_days,
        ac_vol_days=args.ac_vol_days,
    )
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        if not out.get("ok"):
            print("ERROR", out.get("error"))
            return 1
        t = out["ticket"]
        print(f"=== LIVE PLAN  {out['symbol']}  ${args.account:,.0f} ===")
        print(f"MODE {t['mode']}  VEHICLE {t['vehicle']}  ACTION {t['action']}")
        print(f"CONF blended={out['blended_confidence']:.2f}  live_vol_z={out['live'].get('vol_z')}  go_long={out['live'].get('go_long')}")
        print(f"MACRO qqq={out['macro'].get('qqq_trend')}  {out['macro'].get('xlp_spy_ratio_state')}")
        print(f"RISK {t['risk_pct']:.1%} → max loss ${t['max_loss_dollars']:,.0f}")
        print("TICKET")
        for s in t.get("steps") or []:
            print(f"  • {s}")
        if out.get("options") and out["options"].get("action") == "buy":
            o = out["options"]
            print(f"OPTIONS {o.get('structure')} exp={o.get('expiry')} debit={o.get('debit_per_share')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
