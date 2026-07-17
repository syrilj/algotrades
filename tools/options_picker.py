#!/usr/bin/env python3
"""Live options picker for $1k book — scanner/model timing → concrete contract.

Uses yfinance chain when available; falls back to BS target-delta if chain thin.
Default: bull call debit spread, 14–45 DTE, max loss ≤ budget.

When the first ATM-ish structure is over budget, searches tighter widths,
lower target deltas, and alternate expiries to find an affordable defined-risk
structure (common for MSTR / TSLA / SKHY on small books).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from options_bs import bs_delta, bs_greeks, round_strike  # noqa: E402

OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)

# Prefer sniper names on small accounts; high-beta names need tighter structures
PREFERRED = ["APLD", "IONQ", "TSLA", "MSTR", "SKHY"]
SKIP_ATM_COSTLY = {"MU", "TSLA", "MSTR", "SKHY", "SOXX"}  # search cheaper structures

# Desk aliases (mirror DESK_ROUTING.json)
_SYMBOL_ALIASES = {
    "INFQ": "IONQ",
    "INFQ.US": "IONQ",
    "GOOGL": "GOOG",
    "GOOGL.US": "GOOG",
}


def _norm_symbol(symbol: str) -> str:
    s = (symbol or "").upper().replace(".US", "").strip()
    return _SYMBOL_ALIASES.get(s, _SYMBOL_ALIASES.get(f"{s}.US", s))


def _mid(bid, ask, last) -> float:
    try:
        b, a = float(bid or 0), float(ask or 0)
        if b > 0 and a > 0:
            return 0.5 * (b + a)
        return float(last or 0)
    except Exception:
        return 0.0


def _list_expiries(expiries: list[str], min_dte: int = 14, max_dte: int = 45) -> list[tuple[str, int]]:
    """Return (expiry, dte) sorted by preference for ~21–35 DTE, then all in range."""
    now = pd.Timestamp.utcnow().tz_localize(None).normalize()
    scored: list[tuple[int, str, int]] = []
    for e in expiries:
        try:
            dt = pd.Timestamp(e)
        except Exception:
            continue
        dte = int((dt - now).days)
        if min_dte <= dte <= max_dte:
            scored.append((abs(dte - 28), e, dte))
    scored.sort()
    return [(e, dte) for _, e, dte in scored]


def _prepare_chain_side(opts: pd.DataFrame, spot: float, T: float, is_call: bool) -> pd.DataFrame:
    if opts is None or opts.empty:
        return pd.DataFrame()
    out = opts.copy()
    out["mid"] = [_mid(r.bid, r.ask, r.lastPrice) for r in out.itertuples()]
    out["iv"] = out["impliedVolatility"].astype(float)
    out = out[(out["mid"] > 0) & (out["iv"] > 0.01)].copy()
    if out.empty:
        return out
    deltas = [
        bs_delta(spot, float(r.strike), T, 0.045, float(r.iv), is_call)
        for r in out.itertuples()
    ]
    out["delta_bs"] = deltas
    out["spread_pct"] = (
        (out["ask"].astype(float) - out["bid"].astype(float))
        / out["mid"].clip(lower=1e-6)
    )
    # Allow slightly wider quotes on expensive names; still filter junk
    out = out[out["spread_pct"] < 0.20]
    return out


def _candidate_from_legs(
    *,
    sym: str,
    spot: float,
    exp: str,
    dte: int,
    T: float,
    long_row,
    short_row,
    is_call: bool,
    account: float,
    max_risk: float,
    search_tag: str | None = None,
) -> dict:
    long_k = float(long_row.strike)
    long_mid = float(long_row.mid)
    long_iv = float(long_row.iv)
    long_delta = float(long_row.delta_bs)

    if short_row is None:
        structure = "long_call" if is_call else "long_put"
        short_k = None
        short_delta = None
        debit = long_mid
        note = f"no short leg in chain — naked long {'call' if is_call else 'put'}"
    else:
        short_k = float(short_row.strike)
        short_mid = float(short_row.mid)
        short_delta = float(short_row.delta_bs)
        debit = max(long_mid - short_mid, 0.01)
        structure = "bull_call_debit_spread" if is_call else "bear_put_debit_spread"
        note = f"OIC {'bull call' if is_call else 'bear put'} spread — defined risk"

    max_loss = debit * 100.0
    g = bs_greeks(spot, long_k, T, 0.045, long_iv, is_call)
    out = {
        "symbol": sym,
        "action": "buy" if max_loss <= max_risk else "skip",
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
        "proposed_debit": round(debit, 4),
    }
    if search_tag:
        out["search_tag"] = search_tag
    if dte < 10:
        out["warnings"].append("short DTE — theta/gamma risk high")
    if long_iv > 0.9:
        out["warnings"].append("very high IV — prefer spread; watch earnings crush")
    if abs(long_delta) < 0.30:
        out["warnings"].append("long leg fairly OTM — needs bigger swing")
    if abs(long_delta) > 0.65:
        out["warnings"].append("long leg deep — expensive / stock-like")
    if max_loss > max_risk:
        out["reason"] = (
            f"spread max_loss ${max_loss:.0f} > budget ${max_risk:.0f} — wait cheaper IV/DTE"
            if structure.endswith("spread")
            else f"option debit ${max_loss:.0f} > budget ${max_risk:.0f}"
        )
    return out


def _build_candidates_for_expiry(
    *,
    sym: str,
    spot: float,
    exp: str,
    dte: int,
    opts: pd.DataFrame,
    is_call: bool,
    account: float,
    max_risk: float,
    prefer_spread: bool,
    target_deltas: list[float],
    width_pcts: list[float],
) -> list[dict]:
    if opts.empty:
        return []
    T = max(dte, 1) / 365.25
    cands: list[dict] = []

    for td in target_deltas:
        work = opts.copy()
        work["abs_dd"] = (work["delta_bs"].abs() - td).abs()
        # top few long legs near target delta with OK liquidity
        longs = work.sort_values(["abs_dd", "spread_pct"]).head(6)
        for long_row in longs.itertuples():
            long_k = float(long_row.strike)
            for w_pct in width_pcts:
                width = max(round_strike(spot, spot * w_pct), 0.5 if spot < 25 else 1.0)
                # Prefer integer/half-dollar widths that actually exist on the chain
                if is_call:
                    short_floor = long_k + max(width * 0.5, 0.5)
                    short_cands = opts[opts["strike"] >= short_floor - 1e-9].sort_values("strike")
                else:
                    short_ceil = long_k - max(width * 0.5, 0.5)
                    short_cands = opts[opts["strike"] <= short_ceil + 1e-9].sort_values(
                        "strike", ascending=False
                    )

                if short_cands.empty:
                    if not prefer_spread:
                        cands.append(
                            _candidate_from_legs(
                                sym=sym,
                                spot=spot,
                                exp=exp,
                                dte=dte,
                                T=T,
                                long_row=long_row,
                                short_row=None,
                                is_call=is_call,
                                account=account,
                                max_risk=max_risk,
                                search_tag=f"naked_d{td:.2f}",
                            )
                        )
                    continue

                # Try first 4 short strikes so we explore tight vs wider spreads
                for short_row in short_cands.head(4).itertuples():
                    # Enforce minimum width of one strike step
                    if is_call and float(short_row.strike) <= long_k + 1e-9:
                        continue
                    if (not is_call) and float(short_row.strike) >= long_k - 1e-9:
                        continue
                    cands.append(
                        _candidate_from_legs(
                            sym=sym,
                            spot=spot,
                            exp=exp,
                            dte=dte,
                            T=T,
                            long_row=long_row,
                            short_row=short_row,
                            is_call=is_call,
                            account=account,
                            max_risk=max_risk,
                            search_tag=f"d{td:.2f}_w{w_pct:.2f}",
                        )
                    )
    return cands


def _rank_key(c: dict) -> tuple:
    """Prefer buy, then closer to ~0.40 long delta, lower max loss, ~28 DTE."""
    action_rank = 0 if c.get("action") == "buy" else 1
    max_loss = float(c.get("max_loss_1_contract") or 1e9)
    long_d = abs(float(c.get("long_delta") or 0.0))
    dte = int(c.get("dte") or 28)
    is_spread = 0 if "spread" in str(c.get("structure") or "") else 1
    return (
        action_rank,
        is_spread,
        abs(long_d - 0.40),
        max_loss,
        abs(dte - 28),
    )


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
    sym = _norm_symbol(symbol)
    max_risk = account * max_risk_pct
    t = yf.Ticker(sym)
    hist = t.history(period="5d")
    if hist.empty:
        return {"error": f"no spot for {sym}", "symbol": sym}
    spot = float(hist["Close"].iloc[-1])

    expiries = list(t.options or [])
    if not expiries:
        return {"error": f"no options chain for {sym}", "spot": spot, "symbol": sym}

    expiry_list = _list_expiries(expiries, min_dte, max_dte)
    if not expiry_list:
        return {
            "error": f"no expiry in {min_dte}-{max_dte} DTE",
            "spot": spot,
            "symbol": sym,
            "expiries": expiries[:8],
        }

    is_call = side == "long"
    # Search space: primary delta/width first, then cheaper OTM / tighter spreads
    def _uniq(seq: list[float]) -> list[float]:
        seen: set[float] = set()
        out: list[float] = []
        for x in seq:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    target_deltas = _uniq([target_delta, 0.40, 0.35, 0.30, 0.25])
    width_pcts = _uniq([spread_width_pct, 0.06, 0.05, 0.04, 0.03, 0.02])

    all_cands: list[dict] = []
    chain_errors: list[str] = []

    # Cap chain fetches for latency (prefer best DTEs first). Stop early once
    # we have a few affordable buys so desk latency stays usable.
    for exp, dte in expiry_list[:4]:
        try:
            chain = t.option_chain(exp)
        except Exception as e:
            chain_errors.append(f"{exp}:{e}")
            continue
        raw = chain.calls if is_call else chain.puts
        T = max(dte, 1) / 365.25
        opts = _prepare_chain_side(raw, spot, T, is_call)
        if opts.empty:
            chain_errors.append(f"{exp}:no priced legs")
            continue
        all_cands.extend(
            _build_candidates_for_expiry(
                sym=sym,
                spot=spot,
                exp=exp,
                dte=dte,
                opts=opts,
                is_call=is_call,
                account=account,
                max_risk=max_risk,
                prefer_spread=prefer_spread,
                target_deltas=target_deltas,
                width_pcts=width_pcts,
            )
        )
        if sum(1 for c in all_cands if c.get("action") == "buy") >= 3:
            break

    if not all_cands:
        return {
            "error": "no priced structures found",
            "symbol": sym,
            "spot": spot,
            "chain_errors": chain_errors[:6],
        }

    affordable = [c for c in all_cands if c.get("action") == "buy"]
    if affordable:
        best = sorted(affordable, key=_rank_key)[0]
        # Clean internal fields for ticket consumers
        if best.get("search_tag") and best.get("search_tag") != "d0.45_w0.08":
            best.setdefault("warnings", []).append(
                f"structure found via affordability search ({best['search_tag']})"
            )
        best.pop("proposed_debit", None)
        best.pop("reason", None)
        return best

    # Nothing fits budget — return cheapest skip as diagnostic
    cheapest = sorted(all_cands, key=lambda c: float(c.get("max_loss_1_contract") or 1e9))[0]
    return {
        "symbol": sym,
        "action": "skip",
        "reason": cheapest.get("reason")
        or f"no structure under budget ${max_risk:.0f} (cheapest ~${cheapest.get('max_loss_1_contract')})",
        "spot": spot,
        "expiry": cheapest.get("expiry"),
        "dte": cheapest.get("dte"),
        "proposed_debit": cheapest.get("debit_per_share"),
        "long_strike": cheapest.get("long_strike"),
        "short_strike": cheapest.get("short_strike"),
        "max_loss_1_contract": cheapest.get("max_loss_1_contract"),
        "budget": round(max_risk, 2),
        "structure": cheapest.get("structure"),
        "n_candidates_scanned": len(all_cands),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


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
    path = OUT / f"options_pick_{_norm_symbol(args.symbol)}.json"
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
            print(
                f"  spot={out['spot']:.2f}  long {out['long_strike']} Δ={out['long_delta']}  short {out['short_strike']}"
            )
            print(
                f"  debit=${out['debit_per_share']:.2f}/sh  max_loss=${out['max_loss_1_contract']:.0f}  (budget ${out['budget']:.0f})"
            )
            print(f"  IV={out['iv_long']:.0%}  theta/day≈{out['theta_day_approx']}")
            for w in out.get("warnings") or []:
                print("  WARN:", w)
            print(f"  note: {out['note']}")
        print("Wrote", path)


if __name__ == "__main__":
    main()
