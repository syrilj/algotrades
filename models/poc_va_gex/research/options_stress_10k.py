#!/usr/bin/env python3
"""30-day 10k -> 1M options stress test.

Uses v23 APLD+IONQ stock entries (blind to the user, simulated by fetching
real prices and pricing calls via Black-Scholes with IV=20d realized vol).

Tests rolling 30-day windows with a compounding options book. Max risk per
window is the full account (no refill).

Honest caveat: 100x in 30 days is a lottery-ticket goal. This script is a
stress test, not a promoted strategy.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[3]
import sys

sys.path.insert(0, str(ROOT / "tools"))
from options_bs import bs_price, round_strike  # noqa: E402

OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)
TRADES = ROOT / "runs" / "poc_va_v23_devin_overlay" / "artifacts" / "trades.csv"
START_CASH = 10_000.0
CODES = ["APLD.US", "IONQ.US"]
WINDOW_DAYS = 30


@dataclass
class WindowResult:
    start: str
    end: str
    strategy: str
    final: float
    ret: float
    max_dd: float
    n: int
    wr: float
    reached_1m: bool
    best_trade: float
    worst_trade: float


def roundtrips(path: Path, codes: list[str]) -> pd.DataFrame:
    t = pd.read_csv(path, parse_dates=["timestamp"])
    buys, sells = t[t.side == "buy"], t[t.side == "sell"]
    rows = []
    for code in codes:
        gb = buys[buys.code == code].reset_index(drop=True)
        gs = sells[sells.code == code].reset_index(drop=True)
        n = min(len(gb), len(gs))
        for i in range(n):
            rows.append(
                {
                    "code": code,
                    "entry": gb.loc[i, "timestamp"],
                    "exit": gs.loc[i, "timestamp"],
                    "entry_px": float(gb.loc[i, "price"]),
                    "exit_px": float(gs.loc[i, "price"]),
                    "stock_pnl": float(gs.loc[i, "pnl"]),
                    "stock_ret": float(gs.loc[i, "return_pct"]),
                }
            )
    return pd.DataFrame(rows).sort_values("entry").reset_index(drop=True)


def load_daily(yf_sym: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(yf_sym, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df["ret"] = df["close"].pct_change()
    df["rv20"] = df["ret"].rolling(20).std() * np.sqrt(252)
    df["rv20"] = df["rv20"].clip(0.15, 1.5).fillna(0.5)
    return df


def option_path_pnl(
    daily: pd.DataFrame,
    entry: pd.Timestamp,
    exit_: pd.Timestamp,
    moneyness: str,
    dte_entry: int,
    early_tp: float | None,
    early_sl: float | None,
    min_dte_exit: int,
) -> dict:
    entry_d = pd.Timestamp(entry).normalize()
    exit_d = pd.Timestamp(exit_).normalize()
    if entry_d not in daily.index:
        idx = daily.index.searchsorted(entry_d)
        if idx >= len(daily):
            return {"pnl": 0.0, "skip": True}
        entry_d = daily.index[idx]
    if exit_d not in daily.index:
        idx = daily.index.searchsorted(exit_d)
        if idx == 0:
            return {"pnl": 0.0, "skip": True}
        exit_d = daily.index[min(idx, len(daily) - 1)]

    S0 = float(daily.loc[entry_d, "close"])
    iv0 = float(daily.loc[entry_d, "rv20"])
    T0 = dte_entry / 365.25
    if moneyness == "atm":
        K = round_strike(S0, S0)
    elif moneyness == "otm5":
        K = round_strike(S0, S0 * 1.05)
    elif moneyness == "otm10":
        K = round_strike(S0, S0 * 1.10)
    else:
        K = round_strike(S0, S0)

    entry_prem = bs_price(S0, K, T0, 0.0, iv0, True)
    if entry_prem < 0.05:
        return {"pnl": 0.0, "skip": True, "reason": "prem_too_cheap"}

    cost = entry_prem * 100.0
    window = daily.loc[entry_d:exit_d]
    if window.empty:
        return {"pnl": 0.0, "skip": True}

    exit_prem = entry_prem
    hold_days = 0
    for i, (ts, row) in enumerate(window.iterrows()):
        hold_days = i
        S = float(row["close"])
        iv = float(row["rv20"])
        dte_left = max(dte_entry - i, 0)
        T = dte_left / 365.25
        prem = bs_price(S, K, T, 0.0, iv, True)
        ret = (prem - entry_prem) / entry_prem
        if early_tp is not None and ret >= early_tp and i > 0:
            exit_prem = prem
            break
        if early_sl is not None and ret <= early_sl and i > 0:
            exit_prem = prem
            break
        if dte_left <= min_dte_exit and i > 0:
            exit_prem = prem
            break
        exit_prem = prem
        if ts >= exit_d:
            break

    pnl = (exit_prem - entry_prem) * 100.0
    return {
        "pnl": float(pnl),
        "skip": False,
        "cost": float(cost),
        "entry_prem": float(entry_prem),
        "exit_prem": float(exit_prem),
        "K": float(K),
        "S0": S0,
        "hold_days": hold_days,
        "opt_ret": float((exit_prem - entry_prem) / entry_prem),
    }


def _feedback_params(recent_pnls: list, base_variant: dict) -> dict:
    """Adjust option structure and size based on last 3 option trades.

    This is the feedback loop: past failures shrink size and go defensive,
    past wins grow size and reach for bigger OTM gamma.  No margin beyond 1x
    cash — the compounding is the accelerator, not a loan.
    """
    recent = [p for p in recent_pnls[-3:] if p != 0.0]
    wins = sum(1 for p in recent if p > 0)
    n = len(recent)
    wr = wins / n if n else 0.0
    cum = sum(recent)

    if wr >= 0.67 and cum > 0:
        # Hot streak: reach for OTM10, 3DTE, high TP, full cash
        return {
            "moneyness": "otm10",
            "dte": 3,
            "tp": 3.00,
            "sl": -0.50,
            "risk_frac": 1.0,
            "min_dte_exit": 0,
        }
    if wr <= 0.33 or cum < 0:
        # Cold streak / losing feedback: shrink, go ATM/ITM, longer DTE
        return {
            "moneyness": "atm",
            "dte": 14,
            "tp": 0.50,
            "sl": -0.30,
            "risk_frac": 0.25,
            "min_dte_exit": 5,
        }
    # Neutral: balanced OTM5
    return {
        "moneyness": "otm5",
        "dte": 7,
        "tp": 1.00,
        "sl": -0.50,
        "risk_frac": 1.0,
        "min_dte_exit": 1,
    }


def simulate_window(
    rts: pd.DataFrame,
    dailies: dict,
    variant: dict,
    start_cash: float,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> WindowResult:
    """Compounding options book over a 30-day window."""
    mask = (rts["entry"] >= window_start) & (rts["entry"] <= window_end)
    subset = rts.loc[mask].copy()
    cash = start_cash
    peak = cash
    max_dd = 0.0
    pnls = []
    wins = 0
    n = 0
    best = -1e9
    worst = 1e9
    recent_pnls = []

    for _, tr in subset.iterrows():
        code = tr["code"]
        daily = dailies[code]

        if variant.get("feedback"):
            params = _feedback_params(recent_pnls, variant)
        else:
            params = variant

        probe = option_path_pnl(
            daily,
            tr["entry"],
            tr["exit"],
            params["moneyness"],
            params["dte"],
            params.get("tp"),
            params.get("sl"),
            params.get("min_dte_exit", 5),
        )
        if probe.get("skip"):
            continue
        cost = probe["cost"]
        # risk budget: allow up to 2x margin in feedback hot streak, but floor cash at 0
        budget = max(cash, 0.0) * params["risk_frac"]
        if budget < cost or budget <= 0:
            continue
        qty = int(budget // cost)
        if qty < 1:
            continue
        pnl = probe["pnl"] * qty
        cash = cash - cost * qty + (cost * qty + pnl)
        recent_pnls.append(pnl)
        pnls.append(pnl)
        best = max(best, pnl)
        worst = min(worst, pnl)
        wins += int(pnl > 0)
        n += 1
        peak = max(peak, max(cash, 0.0))
        max_dd = min(max_dd, max(cash, 0.0) / peak - 1.0)

    final = max(cash, 0.0)
    ret = final / start_cash - 1.0
    return WindowResult(
        start=str(window_start.date()),
        end=str(window_end.date()),
        strategy=variant["name"],
        final=final,
        ret=ret,
        max_dd=float(max_dd),
        n=n,
        wr=wins / n if n else 0.0,
        reached_1m=final >= 1_000_000.0,
        best_trade=float(best) if n else 0.0,
        worst_trade=float(worst) if n else 0.0,
    )


def main():
    rts = roundtrips(TRADES, CODES)
    print(f"Loaded {len(rts)} roundtrips from {TRADES.name}")
    if rts.empty:
        return

    overall_start = rts["entry"].min()
    overall_end = rts["entry"].max()
    print(f"Trade history spans {overall_start.date()} -> {overall_end.date()} for {CODES}")

    # Pre-load daily data for the whole span (plus buffer)
    fetch_start = (overall_start - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
    fetch_end = (overall_end + pd.Timedelta(days=40)).strftime("%Y-%m-%d")
    dailies = {}
    for code in CODES:
        yf_sym = code.replace(".US", "")
        dailies[code] = load_daily(yf_sym, fetch_start, fetch_end)

    variants = [
        {"name": "conservative_atm14_tp50_sl40", "moneyness": "atm", "dte": 14, "tp": 0.50, "sl": -0.40, "risk_frac": 0.25, "min_dte_exit": 5},
        {"name": "aggressive_otm5_7d_tp100_sl50", "moneyness": "otm5", "dte": 7, "tp": 1.00, "sl": -0.50, "risk_frac": 1.00, "min_dte_exit": 1},
        {"name": "yolo_otm10_3d_tp200_sl50", "moneyness": "otm10", "dte": 3, "tp": 2.00, "sl": -0.50, "risk_frac": 1.00, "min_dte_exit": 0},
        {"name": "feedback_adaptive", "feedback": True, "moneyness": "otm5", "dte": 7, "tp": 1.00, "sl": -0.50, "risk_frac": 1.00, "min_dte_exit": 1},
    ]

    results = []
    for start in pd.date_range(overall_start, overall_end - pd.Timedelta(days=WINDOW_DAYS), freq="7D"):
        end = start + pd.Timedelta(days=WINDOW_DAYS)
        for variant in variants:
            res = simulate_window(rts, dailies, variant, START_CASH, start, end)
            results.append(asdict(res))

    df = pd.DataFrame(results)
    out_json = OUT / "OPTIONS_STRESS_10K.json"
    if df.empty:
        out_json.write_text(json.dumps({
            "start_cash": START_CASH,
            "target": 1_000_000,
            "window_days": WINDOW_DAYS,
            "windows_tested": 0,
            "best_window": None,
            "worst_window": None,
            "results": results,
            "note": "No 30-day windows could be tested from the available trade history.",
        }, indent=2, default=str))
        print(f"\nNo 30-day windows available. Results saved to {out_json}")
        return

    out_json.write_text(json.dumps({
        "start_cash": START_CASH,
        "target": 1_000_000,
        "window_days": WINDOW_DAYS,
        "windows_tested": len(results),
        "best_window": df.sort_values("final", ascending=False).iloc[0].to_dict(),
        "worst_window": df.sort_values("final", ascending=True).iloc[0].to_dict(),
        "results": results,
    }, indent=2, default=str))

    print(f"\nTested {len(results)} windows. Results saved to {out_json}")
    print("\n=== Best window ===")
    best = df.sort_values("final", ascending=False).iloc[0]
    print(best.to_string())
    print("\n=== Worst window ===")
    worst = df.sort_values("final", ascending=True).iloc[0]
    print(worst.to_string())
    print("\n=== Reached 1M? ===")
    print(df["reached_1m"].value_counts())
    print("\n=== Strategy summary ===")
    print(df.groupby("strategy")[["final", "ret", "max_dd", "n", "wr"]].agg(["mean", "median", "min", "max"]).round(4))


if __name__ == "__main__":
    main()
