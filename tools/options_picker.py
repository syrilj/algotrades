#!/usr/bin/env python3
"""Live options picker for $1k book — scanner/model timing → concrete contract.

Uses yfinance chain when available; falls back to BS target-delta if chain thin.
Default: bull call debit spread, 14–45 DTE, max loss ≤ budget.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from options_bs import bs_delta, bs_greeks, round_strike  # noqa: E402

OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)

# Prefer sniper names on small accounts
PREFERRED = ["APLD", "IONQ", "TSLA"]
SKIP_ATM_COSTLY = {"MU"}  # often unaffordable ATM on $1k


def _mid(bid, ask, last) -> float:
    try:
        b, a = float(bid or 0), float(ask or 0)
        if b > 0 and a > 0:
            return 0.5 * (b + a)
        return float(last or 0)
    except Exception:
        return 0.0


def _pick_expiry(expiries: list[str], min_dte: int = 14, max_dte: int = 45) -> str | None:
    now = pd.Timestamp.utcnow().tz_localize(None).normalize()
    scored = []
    for e in expiries:
        dt = pd.Timestamp(e)
        dte = (dt - now).days
        if min_dte <= dte <= max_dte:
            # prefer ~21–35 DTE
            scored.append((abs(dte - 28), e, dte))
    if not scored:
        return None
    scored.sort()
    return scored[0][1]


def propose(
    symbol: str,
    account: float = 1000.0,
    max_risk_pct: float = 0.18,
    target_delta: float = 0.45,
    spread_width_pct: float = 0.08,
    min_dte: int = 14,
    max_dte: int = 45,
    prefer_spread: bool = True,
    side: str = "long",
) -> dict:
    sym = symbol.upper().replace(".US", "")
    max_risk = account * max_risk_pct
    t = yf.Ticker(sym)
    hist = t.history(period="5d")
    if hist.empty:
        return {"error": f"no spot for {sym}"}
    spot = float(hist["Close"].iloc[-1])
    if sym in SKIP_ATM_COSTLY and prefer_spread:
        # still allow spreads with tight width later
        pass

    expiries = list(t.options or [])
    if not expiries:
        return {"error": f"no options chain for {sym}", "spot": spot}
    exp = _pick_expiry(expiries, min_dte, max_dte)
    if not exp:
        return {"error": f"no expiry in {min_dte}-{max_dte} DTE", "spot": spot, "expiries": expiries[:8]}

    chain = t.option_chain(exp)
    is_call = (side == "long")
    opts = chain.calls.copy() if is_call else chain.puts.copy()
    if opts.empty:
        return {"error": f"empty {'calls' if is_call else 'puts'}", "expiry": exp}

    now = pd.Timestamp.utcnow().tz_localize(None)
    dte = max((pd.Timestamp(exp) - now).days, 1)
    T = dte / 365.25

    # Choose long strike nearest target delta (use IV from chain when present)
    opts["mid"] = [_mid(r.bid, r.ask, r.lastPrice) for r in opts.itertuples()]
    opts["iv"] = opts["impliedVolatility"].astype(float)
    opts = opts[(opts["mid"] > 0) & (opts["iv"] > 0.01)].copy()
    if opts.empty:
        return {"error": f"no priced {'calls' if is_call else 'puts'}", "expiry": exp}

    # Prefer OTM / slight ITM around target delta
    if "delta" in [c.lower() for c in opts.columns]:
        # yfinance rarely has delta; compute BS delta from IV
        pass
    deltas = []
    for r in opts.itertuples():
        deltas.append(bs_delta(spot, float(r.strike), T, 0.0, float(r.iv), is_call))
    opts["delta_bs"] = deltas
    opts["abs_dd"] = (opts["delta_bs"].abs() - target_delta).abs()
    # liquidity: prefer tighter spreads
    opts["spread_pct"] = (opts["ask"].astype(float) - opts["bid"].astype(float)) / opts["mid"].clip(lower=1e-6)
    opts = opts[opts["spread_pct"] < 0.35]
    if opts.empty:
        return {"error": "all quotes too wide", "expiry": exp}

    long_row = opts.sort_values(["abs_dd", "spread_pct"]).iloc[0]
    long_k = float(long_row.strike)
    long_mid = float(long_row.mid)
    long_iv = float(long_row.iv)
    long_delta = float(long_row.delta_bs)

    # Short leg for debit spread: higher strike for calls, lower strike for puts
    width = max(round_strike(spot, spot * spread_width_pct), 0.5 if spot < 25 else 1.0)
    if is_call:
        short_k = round_strike(spot, long_k + width)
        short_cands = opts[opts["strike"] >= short_k - 1e-9].sort_values("strike")
    else:
        short_k = round_strike(spot, long_k - width)
        short_cands = opts[opts["strike"] <= short_k + 1e-9].sort_values("strike", ascending=False)

    if short_cands.empty:
        structure = "long_call" if is_call else "long_put"
        short_k = None
        short_mid = 0.0
        short_delta = None
        debit = long_mid
        max_loss = debit * 100.0
        note = f"no short leg in chain — naked long {'call' if is_call else 'put'}"
    else:
        short_row = short_cands.iloc[0]
        short_k = float(short_row.strike)
        short_mid = float(short_row.mid)
        short_delta = float(short_row.delta_bs)
        debit = max(long_mid - short_mid, 0.01)
        max_loss = debit * 100.0
        structure = "bull_call_debit_spread" if is_call else "bear_put_debit_spread"
        note = f"OIC {'bull call' if is_call else 'bear put'} spread — defined risk"

    # If naked contract too expensive or user prefers spread but spread still over budget, skip
    if prefer_spread and structure in ("long_call", "long_put") and max_loss > max_risk:
        return {
            "symbol": sym,
            "action": "skip",
            "reason": f"naked contract max_loss ${max_loss:.0f} > budget ${max_risk:.0f}",
            "spot": spot,
            "expiry": exp,
        }

    if max_loss > max_risk and structure in ("bull_call_debit_spread", "bear_put_debit_spread"):
        return {
            "symbol": sym,
            "action": "skip",
            "reason": f"spread max_loss ${max_loss:.0f} > budget ${max_risk:.0f} — wait cheaper IV/DTE",
            "spot": spot,
            "expiry": exp,
            "proposed_debit": debit,
            "long_strike": long_k,
            "short_strike": short_k,
        }

    if structure in ("long_call", "long_put") and max_loss > max_risk:
        return {
            "symbol": sym,
            "action": "skip",
            "reason": f"option debit ${max_loss:.0f} > budget ${max_risk:.0f}",
            "spot": spot,
        }

    g = bs_greeks(spot, long_k, T, 0.0, long_iv, is_call)
    out = {
        "symbol": sym,
        "action": "buy",
        "structure": structure,
        "spot": spot,
        "expiry": exp,
        "dte": dte,
        "long_strike": long_k,
        "short_strike": short_k,
        "long_delta": round(long_delta, 3),
        "short_delta": None if short_delta is None else round(short_delta, 3),
        "iv_long": round(long_iv, 4),
        "debit_per_share": round(debit, 4),
        "max_loss_1_contract": round(max_loss, 2),
        "contracts": 1,
        "account": account,
        "budget": round(max_risk, 2),
        "theta_day_approx": round(g["theta_day"], 4),
        "note": note,
        "warnings": [],
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "exit_plan": {
            "cut_loser": "exit if premium ≤ -30% from entry (do not hope)",
            "stagnant": "if 2 sessions pass with |opt| <8% and underlying <2% move → exit",
            "big_move": "after +40% premium, trail: exit if give back 25% of peak premium",
            "time": "flat by 5 DTE — no lottery holds",
            "goal": "catch big moves; cut dead trades; react",
        },
    }
    if dte < 10:
        out["warnings"].append("short DTE — theta/gamma risk high")
    if long_iv > 0.9:
        out["warnings"].append("very high IV — prefer spread; watch earnings crush")
    if abs(long_delta) < 0.30:
        out["warnings"].append("long leg fairly OTM — needs bigger swing")
    if abs(long_delta) > 0.65:
        out["warnings"].append("long leg deep — expensive / stock-like")
    return out



def main():
    ap = argparse.ArgumentParser(description="Pick option structure for $1k swing book")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--account", type=float, default=1000.0)
    ap.add_argument("--risk-pct", type=float, default=0.18)
    ap.add_argument("--target-delta", type=float, default=0.45)
    ap.add_argument("--min-dte", type=int, default=14)
    ap.add_argument("--max-dte", type=int, default=45)
    ap.add_argument("--long-call", action="store_true", help="Allow/prefer naked call if cheap")
    ap.add_argument("--side", type=str, default="long", choices=["long", "short"], help="Position side")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = propose(
        args.symbol,
        account=args.account,
        max_risk_pct=args.risk_pct,
        target_delta=args.target_delta,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        prefer_spread=not args.long_call,
        side=args.side,
    )
    path = OUT / f"options_pick_{args.symbol.upper().replace('.US','')}.json"
    path.write_text(json.dumps(out, indent=2))
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        if out.get("error"):
            print("ERROR", out)
        elif out.get("action") == "skip":
            print(f"SKIP {out['symbol']}: {out.get('reason')}")
        else:
            print(f"{out['symbol']}  {out['structure']}  exp={out['expiry']} ({out['dte']}d)")
            print(f"  spot={out['spot']:.2f}  long {out['long_strike']} Δ={out['long_delta']}  short {out['short_strike']}")
            print(f"  debit=${out['debit_per_share']:.2f}/sh  max_loss=${out['max_loss_1_contract']:.0f}  (budget ${out['budget']:.0f})")
            print(f"  IV={out['iv_long']:.0%}  theta/day≈{out['theta_day_approx']}")
            for w in out.get("warnings") or []:
                print("  WARN:", w)
            print(f"  note: {out['note']}")
        print("Wrote", path)


if __name__ == "__main__":
    main()
