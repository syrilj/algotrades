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
        start = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
        candles = adapter.client.candles(_lse_symbol(ticker), "1d", start=start, limit=500)
        df = _lse_candles_to_df(candles)
        if not df.empty:
            s = df["Close"].astype(float)
            s.index = pd.to_datetime(s.index)
            if getattr(s.index, "tz", None) is not None:
                s.index = s.index.tz_localize(None)
            return s.dropna()
    except Exception as e:  # noqa: BLE001
        print(f"[live_plan] LSE daily close failed for {ticker}: {e}")
    return pd.Series(dtype=float)


def _intraday_df_lse(adapter: LSEAdapter, symbol: str) -> pd.DataFrame | None:
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        candles = adapter.client.candles(_lse_symbol(symbol), "1h", start=start, limit=2000)
        df = _lse_candles_to_df(candles)
        if not df.empty and len(df) >= 20:
            return df
    except Exception as e:  # noqa: BLE001
        print(f"[live_plan] LSE intraday failed for {symbol}: {e}")
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


def _default_equity_model() -> str:
    try:
        from model_registry import equity_default_model

        return equity_default_model()
    except Exception:
        return "v39b_live_adapt"


def try_model_confidence(symbol: str, model: str | None = None) -> dict[str, Any]:
    """Best-effort model conf from trade_desk analyze (may be slow / fail offline)."""
    model = model or _default_equity_model()
    try:
        from trade_desk import analyze  # local tools/

        payload = analyze(symbol, account=100_000, risk_pct=0.01, period="60d", model=model)
        state = payload.get("state") or {}
        conf = state.get("confidence")
        if conf is None:
            conf = state.get("hit_probability")
        return {
            "ok": True,
            "model": payload.get("model") or model,
            "confidence": float(conf) if conf is not None else None,
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


def plan_symbol(
    symbol: str,
    account: float = 1000.0,
    peak: float | None = None,
    history: list[float] | None = None,
    model: str | None = None,
    use_model: bool = True,
    open_equity: int = 0,
    open_options: int = 0,
    lse_adapter: LSEAdapter | None = None,
) -> dict[str, Any]:
    model = model or _default_equity_model()
    pol = load_policy()
    eng = LiveSignalEngine()

    # Prefer LSE when an adapter is available, otherwise live_signal fetches yfinance.
    adapter = lse_adapter
    if adapter is None and os.environ.get("LSE_API_KEY"):
        adapter = LSEAdapter(api_key=os.environ.get("LSE_API_KEY"))
    df = _intraday_df_lse(adapter, symbol) if adapter is not None else None
    if df is not None and (df.empty or len(df) < 20):
        df = None
    live = eng.analyze(symbol, df=df)
    if live.get("error"):
        return {
            "ok": False,
            "symbol": symbol,
            "error": live.get("error"),
            "asof_utc": datetime.now(timezone.utc).isoformat(),
        }

    macro = macro_regime(adapter)
    model_info: dict[str, Any] = {"ok": False, "skipped": not use_model}
    if use_model:
        # trade_desk understands auto / WINNER ids
        model_info = try_model_confidence(
            symbol, model="auto" if model in ("", "auto") else model
        )

    live_conf = float(live.get("confidence") or 0.0)
    model_conf = model_info.get("confidence")
    trend_ok = bool(live.get("swing_uptrend") or live.get("above_vwap") or live.get("macd_positive"))
    conf = blend_confidence(live_conf, model_conf if model_info.get("ok") else None, bool(live.get("go_long")), trend_ok)

    # Options affordability heuristic from research playbook
    ysym = _yf_symbol(symbol)
    options_affordable = ysym not in {"MU"}  # MU ATM often too rich on $1k
    if account < 1500 and ysym in {"TSLA", "NVDA", "META", "AVGO"}:
        options_affordable = account >= 2000  # spreads only on larger book; still allow try

    setup = SetupSnapshot(
        symbol=ysym,
        model_conf=conf,
        vol_z=float(live.get("vol_z") or 0.0),
        trend_ok=trend_ok and bool(live.get("macd_positive") or live.get("go_long") or conf >= 0.65),
        macro_ok=bool(macro.get("macro_ok", True)),
        qqq_ok=bool(macro.get("qqq_ok", True)),
        options_affordable=options_affordable,
        liquidity_ok=True,
        side="long",
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

    options_plan = None
    if decision.mode == "OPTIONS_ATTACK" and decision.action == "enter":
        try:
            options_plan = options_propose(
                ysym,
                account=account,
                max_risk_pct=float(decision.risk_pct),
                prefer_spread=True,
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
            dec = decision_to_dict(decision2)
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
        ticket["steps"] = ["No edge / defensive macro — cash is a position"]
    elif decision.mode in ("FLATTEN", "HALT_NEW"):
        ticket["steps"] = list(decision.reasons)

    # Live adapt size mult (from paper closes) + optional IB-ready export
    adapt_mult = 1.0
    adapt_snap: dict[str, Any] = {}
    try:
        import live_adapt as la

        adapt_mult = float(la.size_mult_for(model, ysym))
        adapt_snap = la.snapshot()
        ticket["live_adapt_mult"] = adapt_mult
        ticket["risk_pct_adapted"] = float(decision.risk_pct) * adapt_mult
        ticket["max_loss_adapted"] = float(decision.max_loss_dollars) * adapt_mult
        # Flat IB-ready order draft (never auto-sent)
        qty_hint = 0
        try:
            if model_info.get("ok") and model_info.get("stop") and model_info.get("price"):
                rps = abs(float(model_info["price"]) - float(model_info["stop"]))
                if rps > 0:
                    qty_hint = int((float(decision.max_loss_dollars) * adapt_mult) // rps)
        except Exception:
            qty_hint = 0
        la.export_ib_ticket(
            {
                "symbol": ysym,
                "side": "BUY" if decision.action == "enter" else "FLAT",
                "qty": max(0, qty_hint),
                "order_type": "LMT",
                "limit": model_info.get("entry") or model_info.get("price") or live.get("price"),
                "stop": model_info.get("stop"),
                "tif": "DAY",
                "model": model_info.get("model") or model,
                "vehicle": decision.vehicle,
                "mode": decision.mode,
                "max_loss_dollars": float(decision.max_loss_dollars) * adapt_mult,
            }
        )
    except Exception:
        pass

    return {
        "ok": True,
        "symbol": ysym,
        "account": account,
        "peak": peak_eq,
        "drawdown": round(drawdown(account, peak_eq), 4),
        "live": live,
        "macro": macro,
        "model": model_info,
        "blended_confidence": round(conf, 4),
        "decision": dec,
        "options": options_plan,
        "ticket": ticket,
        "live_adapt": {"size_mult": adapt_mult, "snapshot": adapt_snap},
        "ib_ticket_path": "runs/live_adapt/LAST_TICKET.json",
        "policy_version": pol.get("version"),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "live_ready": True,
        "notes": [
            "SIDE research DNA: v23/v20b macro + vol_z conviction; vehicle from v25 risk",
            "Do not retune primary rules on today's tape; only size/vehicle react",
        ],
    }


DEFAULT_SCAN = [
    "APLD", "IONQ", "TSLA", "MU", "NVDA", "AMD", "META", "AVGO", "SMCI", "HOOD",
]


def scan(
    symbols: list[str] | None = None,
    account: float = 1000.0,
    peak: float | None = None,
    use_model: bool = False,
    lse_adapter: LSEAdapter | None = None,
) -> dict[str, Any]:
    """Scan universe; default skips heavy model analyze for speed (live features + macro)."""
    syms = symbols or DEFAULT_SCAN
    macro = macro_regime(lse_adapter)
    rows = []
    for s in syms:
        # light path: no per-symbol model for scan speed
        plan = plan_symbol(
            s,
            account=account,
            peak=peak,
            use_model=use_model,
            model=_default_equity_model(),
            lse_adapter=lse_adapter,
        )
        if not plan.get("ok"):
            continue
        t = plan["ticket"]
        rows.append({
            "symbol": plan["symbol"],
            "mode": t["mode"],
            "vehicle": t["vehicle"],
            "action": t["action"],
            "conviction": t.get("conviction"),
            "risk_pct": t.get("risk_pct"),
            "max_loss_dollars": t.get("max_loss_dollars"),
            "vol_z": (plan.get("live") or {}).get("vol_z"),
            "price": (plan.get("live") or {}).get("price"),
            "go_long": (plan.get("live") or {}).get("go_long"),
            "blended_confidence": plan.get("blended_confidence"),
        })
    # rank: attack first, then equity, by conviction
    order = {"OPTIONS_ATTACK": 0, "EQUITY_HEDGE": 1, "HALT_NEW": 2, "STAND_ASIDE": 3, "FLATTEN": 4}
    rows.sort(key=lambda r: (order.get(str(r["mode"]), 9), -(r.get("conviction") or 0)))
    return {
        "ok": True,
        "account": account,
        "macro": macro,
        "count": len(rows),
        "rows": rows,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live trading plan (hybrid desk + WINNER equity)")
    ap.add_argument("--symbol", type=str, default="")
    ap.add_argument("--account", type=float, default=1000.0)
    ap.add_argument("--peak", type=float, default=0.0)
    ap.add_argument("--history", type=str, default="")
    ap.add_argument(
        "--model",
        type=str,
        default="",
        help="Equity engine (default: WINNER.json via equity_default_model)",
    )
    ap.add_argument("--no-model", action="store_true", help="Skip trade_desk model analyze (faster)")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--symbols", type=str, default="", help="Comma list for scan")
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
        # default scan is light (no per-name model analyze) for live speed
        out = scan(syms, account=args.account, peak=args.peak or None, use_model=False, lse_adapter=lse_adapter)
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print(f"SCAN account=${args.account:,.0f}  macro={out['macro'].get('xlp_spy_ratio_state')} qqq={out['macro'].get('qqq_trend')}")
            for r in out["rows"][:15]:
                print(
                    f"  {r['symbol']:6} {r['mode']:16} {r['vehicle']:8} "
                    f"conv={r.get('conviction') or 0:.2f} volz={r.get('vol_z')} px={r.get('price')}"
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
        lse_adapter=lse_adapter,
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
