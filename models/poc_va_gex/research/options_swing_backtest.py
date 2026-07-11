#!/usr/bin/env python3
"""Synthetic options swing backtest on v20b APLD/IONQ stock signals.

Honest caveat: premiums are Black–Scholes with IV = trailing realized vol
(not live chain). Use for structure/exit research, not as a promoted WINNER.

Compares:
  - stock swing (same entries) vs long calls (ATM / OTM / target-delta)
  - hold to model exit vs early +50% / -40% / time-stop
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
from options_bs import bs_price, round_strike, strike_for_delta  # noqa: E402

OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)
TRADES = ROOT / "runs" / "poc_va_v20b_macro_light" / "artifacts" / "trades.csv"
START_CASH = 1000.0
CODES = ["APLD.US", "IONQ.US"]


@dataclass
class VariantResult:
    name: str
    final: float
    ret: float
    max_dd: float
    n: int
    wr: float
    avg_hold_days: float
    sum_pnl: float


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
    target_delta: float | None,
    dte_entry: int,
    early_tp: float | None,
    early_sl: float | None,
    min_dte_exit: int,
) -> dict:
    """Mark-to-market synthetic call from entry→exit with optional early rules."""
    entry_d = pd.Timestamp(entry).normalize()
    exit_d = pd.Timestamp(exit_).normalize()
    # align to trading days
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
    elif moneyness == "delta":
        raw = strike_for_delta(S0, T0, 0.0, iv0, target_delta or 0.40, True)
        K = round_strike(S0, raw)
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
        # early exits
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


def simulate_book(rts: pd.DataFrame, dailies: dict, variant: dict, start_cash: float) -> VariantResult:
    cash = start_cash
    equity = [cash]
    pnls = []
    holds = []
    wins = 0
    n = 0
    peak = cash
    max_dd = 0.0
    for _, tr in rts.iterrows():
        code = tr["code"]
        yf_sym = code.replace(".US", "")
        daily = dailies[yf_sym]
        # one contract only if affordable
        probe = option_path_pnl(
            daily,
            tr["entry"],
            tr["exit"],
            variant["moneyness"],
            variant.get("target_delta"),
            variant["dte"],
            variant.get("tp"),
            variant.get("sl"),
            variant.get("min_dte_exit", 5),
        )
        if probe.get("skip"):
            continue
        cost = probe["cost"]
        if cost > cash * 0.95 or cost > start_cash * 0.25:
            # too rich for book — skip (selectivity)
            continue
        cash -= cost
        # during hold we mark only at exit for simplicity (path used for early exit)
        cash += cost + probe["pnl"]
        pnls.append(probe["pnl"])
        holds.append(probe["hold_days"])
        wins += int(probe["pnl"] > 0)
        n += 1
        equity.append(cash)
        peak = max(peak, cash)
        max_dd = min(max_dd, cash / peak - 1.0)

    final = cash
    return VariantResult(
        name=variant["name"],
        final=final,
        ret=final / start_cash - 1.0,
        max_dd=float(max_dd),
        n=n,
        wr=wins / n if n else 0.0,
        avg_hold_days=float(np.mean(holds)) if holds else 0.0,
        sum_pnl=float(np.sum(pnls)) if pnls else 0.0,
    )


def stock_book(rts: pd.DataFrame, dailies: dict, start_cash: float) -> VariantResult:
    """Same entries: buy max shares with 20% of book (cap), hold to model exit."""
    cash = start_cash
    equity = [cash]
    pnls = []
    holds = []
    wins = 0
    n = 0
    peak = cash
    max_dd = 0.0
    for _, tr in rts.iterrows():
        yf_sym = tr["code"].replace(".US", "")
        daily = dailies[yf_sym]
        entry_d = pd.Timestamp(tr["entry"]).normalize()
        exit_d = pd.Timestamp(tr["exit"]).normalize()
        if entry_d not in daily.index:
            idx = daily.index.searchsorted(entry_d)
            if idx >= len(daily):
                continue
            entry_d = daily.index[idx]
        if exit_d not in daily.index:
            idx = daily.index.searchsorted(exit_d)
            exit_d = daily.index[min(max(idx - 1, 0), len(daily) - 1)]
        px0 = float(daily.loc[entry_d, "close"])
        px1 = float(daily.loc[exit_d, "close"])
        budget = min(cash * 0.95, start_cash * 0.25)
        shares = int(budget // px0)
        if shares <= 0:
            continue
        cost = shares * px0
        pnl = shares * (px1 - px0)
        cash = cash - cost + cost + pnl
        pnls.append(pnl)
        holds.append(max((exit_d - entry_d).days, 0))
        wins += int(pnl > 0)
        n += 1
        equity.append(cash)
        peak = max(peak, cash)
        max_dd = min(max_dd, cash / peak - 1.0)
    return VariantResult(
        name="stock_20pct_clip",
        final=cash,
        ret=cash / start_cash - 1.0,
        max_dd=float(max_dd),
        n=n,
        wr=wins / n if n else 0.0,
        avg_hold_days=float(np.mean(holds)) if holds else 0.0,
        sum_pnl=float(np.sum(pnls)) if pnls else 0.0,
    )


def main():
    if not TRADES.exists():
        raise SystemExit(f"missing {TRADES} — run v20b stock backtest first")
    rts = roundtrips(TRADES, CODES)
    print(f"sniper roundtrips from v20b: {len(rts)}")
    start = "2024-07-01"
    end = "2026-07-12"
    dailies = {c.replace(".US", ""): load_daily(c.replace(".US", ""), start, end) for c in CODES}

    variants = [
        {"name": "call_atm_21d_hold_model", "moneyness": "atm", "dte": 21, "tp": None, "sl": None, "min_dte_exit": 2},
        {"name": "call_otm5_21d_hold_model", "moneyness": "otm5", "dte": 21, "tp": None, "sl": None, "min_dte_exit": 2},
        {"name": "call_otm10_21d_hold_model", "moneyness": "otm10", "dte": 21, "tp": None, "sl": None, "min_dte_exit": 2},
        {"name": "call_d40_28d_hold_model", "moneyness": "delta", "target_delta": 0.40, "dte": 28, "tp": None, "sl": None, "min_dte_exit": 5},
        {"name": "call_d40_28d_tp50_sl40", "moneyness": "delta", "target_delta": 0.40, "dte": 28, "tp": 0.50, "sl": -0.40, "min_dte_exit": 5},
        {"name": "call_d45_35d_tp100_sl40", "moneyness": "delta", "target_delta": 0.45, "dte": 35, "tp": 1.00, "sl": -0.40, "min_dte_exit": 7},
        {"name": "call_otm5_21d_tp50_sl40", "moneyness": "otm5", "dte": 21, "tp": 0.50, "sl": -0.40, "min_dte_exit": 3},
        {"name": "call_atm_14d_tp50_sl40", "moneyness": "atm", "dte": 14, "tp": 0.50, "sl": -0.40, "min_dte_exit": 2},
    ]

    results = [stock_book(rts, dailies, START_CASH)]
    for v in variants:
        results.append(simulate_book(rts, dailies, v, START_CASH))

    rows = [asdict(r) for r in results]
    rows = sorted(rows, key=lambda x: x["ret"], reverse=True)
    out_path = OUT / "OPTIONS_SWING_BACKTEST.json"
    payload = {
        "start_cash": START_CASH,
        "signals": "v20b_macro_light APLD+IONQ roundtrips",
        "pricing": "BS with IV=20d realized vol (synthetic — not exchange marks)",
        "caveat": "Not a promoted WINNER. Directional research only.",
        "results": rows,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(rows, indent=2))
    print("Wrote", out_path)
    best = rows[0]
    print(f"\nBEST by return: {best['name']}  final=${best['final']:.0f}  ret={best['ret']:.1%}  DD={best['max_dd']:.1%}  n={best['n']} WR={best['wr']:.1%}")


if __name__ == "__main__":
    main()
