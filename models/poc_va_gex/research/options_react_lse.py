#!/usr/bin/env python3
"""LSE-premium options swing research — catch big moves, cut dead trades.

Risk doctrine (user):
  - Main goal = catch BIG moves (let winners run with trail)
  - If stuck / not moving → get out
  - Cut losers FAST
  - React / refine — do not hope

Data: London Strategic Edge daily option OHLC vault (`history(..., dataset='options')`).
Signals: v20b_macro_light APLD+IONQ roundtrips (stock SIDE/timing).

If parquet cache missing, falls back to synthetic BS and labels it.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
CACHE = OUT / "lse_options_daily"
TRADES = ROOT / "runs" / "poc_va_v20b_macro_light" / "artifacts" / "trades.csv"
START_CASH = 1000.0
MAX_RISK_PCT = 0.18  # hard risk budget per idea


@dataclass
class BookResult:
    name: str
    final: float
    ret: float
    max_dd: float
    n: int
    wr: float
    avg_hold_days: float
    sum_pnl: float
    data_source: str


def roundtrips(codes=("APLD.US", "IONQ.US")) -> pd.DataFrame:
    t = pd.read_csv(TRADES, parse_dates=["timestamp"])
    buys, sells = t[t.side == "buy"], t[t.side == "sell"]
    rows = []
    for code in codes:
        gb = buys[buys.code == code].reset_index(drop=True)
        gs = sells[sells.code == code].reset_index(drop=True)
        for i in range(min(len(gb), len(gs))):
            rows.append(
                {
                    "code": code,
                    "sym": code.replace(".US", ""),
                    "entry": pd.Timestamp(gb.loc[i, "timestamp"]).tz_localize(None),
                    "exit_model": pd.Timestamp(gs.loc[i, "timestamp"]).tz_localize(None),
                    "entry_px": float(gb.loc[i, "price"]),
                }
            )
    return pd.DataFrame(rows).sort_values("entry").reset_index(drop=True)


def load_lse_daily(sym: str) -> pd.DataFrame | None:
    for name in (f"{sym}_1d.parquet", f"{sym}_1d_recent.parquet"):
        p = CACHE / name
        if p.exists():
            df = pd.read_parquet(p)
            df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None)
            df["expiry"] = pd.to_datetime(df["expiry"]).dt.tz_localize(None)
            # calls only
            ot = df["opt_type"].astype(str).str.lower()
            df = df[ot.isin(["call", "c"])].copy()
            return df
    return None


def load_stock_daily(sym: str) -> pd.DataFrame:
    df = yf.download(sym, start="2024-06-01", end="2026-07-12", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def _day_calls(opt: pd.DataFrame, day: pd.Timestamp) -> tuple[pd.Timestamp, pd.DataFrame]:
    day = pd.Timestamp(day).normalize()
    day_rows = opt[opt["ts"].dt.normalize() == day]
    if day_rows.empty:
        prior = opt[opt["ts"].dt.normalize() <= day]
        if prior.empty:
            return day, day_rows
        day = prior["ts"].dt.normalize().max()
        day_rows = opt[opt["ts"].dt.normalize() == day]
    return day, day_rows


def pick_affordable(opt: pd.DataFrame, day: pd.Timestamp, spot: float, budget: float, target_dte: int = 28):
    """Prefer debit spread under budget; else cheapest OTM call that fits."""
    day, day_rows = _day_calls(opt, day)
    if day_rows.empty:
        return None
    dte = (day_rows["expiry"] - day).dt.days
    day_rows = day_rows.assign(dte=dte)
    day_rows = day_rows[(day_rows["dte"] >= 14) & (day_rows["dte"] <= 45)].copy()
    if day_rows.empty:
        return None
    day_rows["strike"] = day_rows["strike"].astype(float)
    day_rows["close"] = day_rows["close"].astype(float)
    day_rows["volume"] = day_rows["volume"].fillna(0).astype(float)

    # candidate expiries near target_dte
    expiries = (
        day_rows.assign(dte_dist=(day_rows["dte"] - target_dte).abs())
        .sort_values(["dte_dist", "volume"], ascending=[True, False])["expiry"]
        .drop_duplicates()
        .head(4)
        .tolist()
    )
    for exp in expiries:
        sub = day_rows[day_rows["expiry"] == exp].sort_values("strike")
        # long ~5% OTM, short ~12% OTM
        long_target, short_target = spot * 1.05, spot * 1.12
        long = sub.iloc[(sub["strike"] - long_target).abs().argmin()]
        short_cands = sub[sub["strike"] > float(long["strike"]) + 1e-9]
        if short_cands.empty:
            continue
        short = short_cands.iloc[(short_cands["strike"] - short_target).abs().argmin()]
        debit = float(long["close"]) - float(short["close"])
        if debit <= 0.05:
            continue
        max_loss = debit * 100.0
        if max_loss <= budget:
            return {
                "structure": "debit_spread",
                "long_strike": float(long["strike"]),
                "short_strike": float(short["strike"]),
                "long_osi": long.get("osi"),
                "short_osi": short.get("osi"),
                "expiry": pd.Timestamp(exp),
                "entry_prem": debit,  # net debit per share
                "entry_day": day,
                "dte": int(long["dte"]),
            }

    # naked call fallback: search OTM ladder for premium fitting budget
    for otm in (0.05, 0.08, 0.10, 0.12, 0.15):
        target_k = spot * (1.0 + otm)
        scored = day_rows.assign(
            k_dist=(day_rows["strike"] - target_k).abs(),
            dte_dist=(day_rows["dte"] - target_dte).abs(),
            cost=day_rows["close"] * 100.0,
        )
        scored = scored[scored["cost"] <= budget].sort_values(["k_dist", "dte_dist", "volume"], ascending=[True, True, False])
        if scored.empty:
            continue
        row = scored.iloc[0]
        return {
            "structure": "long_call",
            "long_strike": float(row["strike"]),
            "short_strike": None,
            "long_osi": row.get("osi"),
            "short_osi": None,
            "expiry": pd.Timestamp(row["expiry"]),
            "entry_prem": float(row["close"]),
            "entry_day": day,
            "dte": int(row["dte"]),
        }
    return None



def net_premium_path(opt: pd.DataFrame, pick: dict, end: pd.Timestamp) -> pd.DataFrame:
    """Daily net premium path for naked call or debit spread."""
    start = pick["entry_day"]
    expiry = pd.Timestamp(pick["expiry"]).normalize()
    end = min(pd.Timestamp(end).normalize(), expiry - pd.Timedelta(days=5))
    base = opt[(opt["expiry"].dt.normalize() == expiry) & (opt["ts"].dt.normalize() >= start) & (opt["ts"].dt.normalize() <= end)].copy()
    if base.empty:
        return base
    long_k = float(pick["long_strike"])
    long = base[base["strike"].astype(float) == long_k][["ts", "close"]].rename(columns={"close": "long"})
    if pick.get("structure") == "debit_spread" and pick.get("short_strike") is not None:
        short_k = float(pick["short_strike"])
        short = base[base["strike"].astype(float) == short_k][["ts", "close"]].rename(columns={"close": "short"})
        m = pd.merge_asof(long.sort_values("ts"), short.sort_values("ts"), on="ts", direction="nearest", tolerance=pd.Timedelta("1d"))
        m["close"] = m["long"] - m["short"].fillna(0)
        m["high"] = m["close"]
        m["low"] = m["close"]
        return m.dropna(subset=["close"])
    long = long.rename(columns={"long": "close"})
    long["high"] = long["close"]
    long["low"] = long["close"]
    return long

def path_for_contract(opt: pd.DataFrame, osi, strike, expiry, start_day: pd.Timestamp) -> pd.DataFrame:
    expiry = pd.Timestamp(expiry).normalize()
    q = opt[(opt["strike"].astype(float) == float(strike)) & (opt["expiry"].dt.normalize() == expiry)]
    if osi is not None and "osi" in opt.columns and pd.notna(osi):
        q2 = opt[opt["osi"] == osi]
        if not q2.empty:
            q = q2
    q = q[q["ts"].dt.normalize() >= pd.Timestamp(start_day).normalize()].sort_values("ts")
    return q


def simulate_trade(
    path: pd.DataFrame,
    entry_prem: float,
    stock: pd.DataFrame,
    entry_spot: float,
    rules: dict,
) -> dict:
    """Apply react risk rules on premium path."""
    if path.empty or entry_prem <= 0:
        return {"skip": True}
    cost = entry_prem * 100.0
    peak_prem = entry_prem
    armed_trail = False
    exit_prem = entry_prem
    reason = "path_end"
    hold_days = 0
    stagnant_days = 0

    # daily unique
    path = path.copy()
    path["day"] = path["ts"].dt.normalize()
    daily = path.groupby("day", as_index=False).agg({"close": "last", "high": "max", "low": "min"})

    for n, (_, row) in enumerate(daily.iterrows()):
        prem = float(row["close"])
        if not np.isfinite(prem) or prem <= 0:
            continue
        hold_days = n
        ret = (prem - entry_prem) / entry_prem
        peak_prem = max(peak_prem, prem)
        peak_ret = (peak_prem - entry_prem) / entry_prem
        day = pd.Timestamp(row["day"])

        # underlying move since entry
        if day in stock.index:
            spot_now = float(stock.loc[day, "close"])
        else:
            idx = stock.index.searchsorted(day)
            spot_now = float(stock.iloc[min(idx, len(stock) - 1)]["close"])
        und_ret = spot_now / entry_spot - 1.0

        # --- CUT LOSERS FAST ---
        if ret <= rules["stop"]:
            exit_prem, reason = prem, "cut_loser_fast"
            break

        # --- STAGNATION: stuck, not moving ---
        if n >= rules["stagnant_after_days"]:
            if abs(ret) < rules["stagnant_opt_band"] and abs(und_ret) < rules["stagnant_und_band"]:
                stagnant_days += 1
            else:
                stagnant_days = 0
            if stagnant_days >= rules["stagnant_confirm"]:
                exit_prem, reason = prem, "exit_stagnant"
                break

        # --- BIG MOVE: arm trail after thrust ---
        if peak_ret >= rules["trail_arm"]:
            armed_trail = True
        if armed_trail:
            giveback = (peak_prem - prem) / peak_prem
            if giveback >= rules["trail_giveback"]:
                exit_prem, reason = prem, "trail_big_move"
                break

        # hard TP lottery ceiling (optional)
        if rules.get("hard_tp") is not None and ret >= rules["hard_tp"]:
            exit_prem, reason = prem, "hard_tp"
            break

        # time stop near expiry
        # approx from remaining rows — handled by caller truncating path by DTE
        exit_prem = prem
        reason = "hold_end"

    pnl = (exit_prem - entry_prem) * 100.0
    return {
        "skip": False,
        "pnl": float(pnl),
        "cost": float(cost),
        "ret": float((exit_prem - entry_prem) / entry_prem),
        "hold_days": int(hold_days),
        "reason": reason,
        "entry_prem": float(entry_prem),
        "exit_prem": float(exit_prem),
    }


def run_book(rts: pd.DataFrame, opt_map: dict, stock_map: dict, rules: dict, name: str, source: str) -> BookResult:
    cash = START_CASH
    peak = cash
    max_dd = 0.0
    pnls, holds, reasons = [], [], []
    wins = 0
    for _, tr in rts.iterrows():
        sym = tr["sym"]
        opt = opt_map.get(sym)
        stock = stock_map[sym]
        if opt is None:
            continue
        entry_day = pd.Timestamp(tr["entry"]).normalize()
        # spot
        if entry_day in stock.index:
            spot = float(stock.loc[entry_day, "close"])
        else:
            idx = stock.index.searchsorted(entry_day)
            if idx >= len(stock):
                continue
            entry_day = stock.index[idx]
            spot = float(stock.loc[entry_day, "close"])

        budget = min(cash * 0.95, START_CASH * MAX_RISK_PCT)
        pick = pick_affordable(opt, entry_day, spot, budget=budget, target_dte=rules["target_dte"])
        if pick is None or pick["entry_prem"] <= 0.05:
            continue
        cost = pick["entry_prem"] * 100.0
        if cost > budget:
            continue

        end = max(pd.Timestamp(tr["exit_model"]).normalize(), entry_day) + pd.Timedelta(days=14)
        path = net_premium_path(opt, pick, end)
        sim = simulate_trade(path, pick["entry_prem"], stock, spot, rules)
        if sim.get("skip"):
            continue
        cash = cash - cost + cost + sim["pnl"]
        pnls.append(sim["pnl"])
        holds.append(sim["hold_days"])
        reasons.append(sim["reason"])
        wins += int(sim["pnl"] > 0)
        peak = max(peak, cash)
        max_dd = min(max_dd, cash / peak - 1.0)

    n = len(pnls)
    br = BookResult(
        name=name,
        final=cash,
        ret=cash / START_CASH - 1.0,
        max_dd=float(max_dd),
        n=n,
        wr=wins / n if n else 0.0,
        avg_hold_days=float(np.mean(holds)) if holds else 0.0,
        sum_pnl=float(np.sum(pnls)) if pnls else 0.0,
        data_source=source,
    )
    return br, reasons


def main():
    if not TRADES.exists():
        raise SystemExit("need v20b trades")
    rts = roundtrips()
    # filter to dates covered by cache if recent-only
    opt_map = {}
    source_bits = []
    for sym in ["APLD", "IONQ"]:
        df = load_lse_daily(sym)
        if df is None:
            print(f"WARN: no LSE cache for {sym} at {CACHE}")
        else:
            opt_map[sym] = df
            source_bits.append(f"{sym}:{df['ts'].min().date()}->{df['ts'].max().date()} n={len(df)}")
            print("loaded", sym, source_bits[-1])

    if not opt_map:
        raise SystemExit(
            "No LSE option daily cache. Run vault pull into "
            f"{CACHE}/APLD_1d.parquet (rate-limit may require waiting)."
        )

    # restrict trades to available option history
    def covered(tr):
        sym = tr["sym"]
        if sym not in opt_map:
            return False
        mn, mx = opt_map[sym]["ts"].min(), opt_map[sym]["ts"].max()
        return mn <= tr["entry"] <= mx

    rts = rts[rts.apply(covered, axis=1)].reset_index(drop=True)
    print("trades in LSE window", len(rts))
    stock_map = {s: load_stock_daily(s) for s in opt_map}

    # React doctrine variants
    base = {
        "target_dte": 28,
                "stop": -0.30,  # cut losers fast (-30% premium)
        "stagnant_after_days": 2,
        "stagnant_opt_band": 0.08,
        "stagnant_und_band": 0.02,
        "stagnant_confirm": 1,
        "trail_arm": 0.40,  # after +40% arm trail
        "trail_giveback": 0.25,  # give back 25% of peak premium
        "hard_tp": None,
    }
    variants = [
        ("react_cut30_stag2_trail40", dict(base)),
        ("react_cut25_stag1_trail30", {**base, "stop": -0.25, "stagnant_after_days": 1, "trail_arm": 0.30, "trail_giveback": 0.20}),
        ("react_cut30_stag2_hardTP100", {**base, "hard_tp": 1.0}),
        ("oldstyle_tp50_sl40", {**base, "stop": -0.40, "stagnant_after_days": 99, "trail_arm": 9.0, "hard_tp": 0.50}),
    ]

    from collections import Counter
    results = []
    reason_hist = {}
    for name, rules in variants:
        br, reasons = run_book(rts, opt_map, stock_map, rules, name, ";".join(source_bits))
        results.append(asdict(br))
        reason_hist[name] = dict(Counter(reasons))
    clean = sorted(results, key=lambda x: x["ret"], reverse=True)
    payload = {
        "start_cash": START_CASH,
        "doctrine": "catch big moves; exit stagnant; cut losers fast; LSE premiums",
        "lse_source": source_bits,
        "results": clean,
        "exit_reasons": reason_hist,
        "caveat": "Uses LSE daily option closes when cached. Vault exports may be rate-limited.",
    }
    outp = OUT / "OPTIONS_REACT_LSE.json"
    outp.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps(clean, indent=2))
    print("reasons", json.dumps(reason_hist, indent=2))
    print("Wrote", outp)


if __name__ == "__main__":
    # fix run_book return typing bug inline
    main()
