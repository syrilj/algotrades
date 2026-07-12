#!/usr/bin/env python3
"""v24_compound with feedback loop — compounds on v22_opts_live option trades.

Uses a trailing-performance feedback loop:
- size is scaled by recent win streak (full size after 3+ wins, half after 1-2, skip if last loss)
- prints 30-day rolling window results and whether the $1M target is hit.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
TRADES = ROOT / "runs" / "poc_va_v22_opts_live" / "artifacts" / "trades.csv"
OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
START_CASH = 10_000.0
WINDOW_DAYS = 30


@dataclass
class WindowResult:
    start: str
    end: str
    final: float
    ret: float
    max_dd: float
    n: int
    wr: float
    reached_1m: bool
    best_trade: float
    worst_trade: float


def load_trades(path: Path) -> pd.DataFrame:
    t = pd.read_csv(path, parse_dates=["timestamp"])
    t = t.sort_values("timestamp").reset_index(drop=True)
    return t


def roundtrips(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    open_by_key = {}
    for _, r in t.iterrows():
        key = (r["code"], r["option_type"], r["strike"], r["expiry"], r["entry_date"])
        if r["side"] == "buy":
            open_by_key[key] = r
        else:
            entry = open_by_key.pop(key, None)
            if entry is None:
                continue
            qty = float(entry["qty"])
            entry_price = float(entry["price"])
            exit_price = float(r["price"])
            pnl = float(r["pnl"])
            cost = entry_price * 100.0 * qty
            ret = pnl / cost if cost > 0 else 0.0
            rows.append({
                "code": r["code"],
                "entry": pd.Timestamp(r["entry_date"]),
                "exit": pd.Timestamp(r["timestamp"]),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "qty": qty,
                "pnl": pnl,
                "ret": ret,
                "cost": cost,
            })
    return pd.DataFrame(rows).sort_values("entry").reset_index(drop=True)


def _size_mult(history: list) -> float:
    """Feedback loop: scale next trade by recent win streak.

    - 3+ recent wins -> full size
    - 1-2 recent wins -> 0.5x
    - last trade was a loss -> 0.25x (still take a shot, but tiny)
    """
    if not history:
        return 1.0
    if history[-1] < 0:
        return 0.25
    wins = 0
    for p in reversed(history):
        if p > 0:
            wins += 1
        else:
            break
    if wins >= 3:
        return 1.0
    if wins >= 1:
        return 0.5
    return 0.25


def simulate_window(rts: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, start_cash: float) -> WindowResult:
    mask = (rts["entry"] >= start) & (rts["entry"] <= end)
    subset = rts.loc[mask].copy()
    cash = start_cash
    peak = cash
    max_dd = 0.0
    best = -1e9
    worst = 1e9
    wins = 0
    n = 0
    history = []

    for _, tr in subset.iterrows():
        cost_per_contract = tr["entry_price"] * 100.0
        if cost_per_contract <= 0 or cash <= 0:
            continue
        mult = _size_mult(history)
        qty = int(cash * mult // cost_per_contract)
        if qty < 1:
            continue
        ret = tr["ret"]
        pnl = cost_per_contract * qty * ret
        cash = cash + pnl
        history.append(pnl)
        best = max(best, pnl)
        worst = min(worst, pnl)
        wins += int(pnl > 0)
        n += 1
        peak = max(peak, max(cash, 0.0))
        max_dd = min(max_dd, max(cash, 0.0) / peak - 1.0)

    final = max(cash, 0.0)
    return WindowResult(
        start=str(start.date()),
        end=str(end.date()),
        final=final,
        ret=final / start_cash - 1.0,
        max_dd=float(max_dd),
        n=n,
        wr=wins / n if n else 0.0,
        reached_1m=final >= 1_000_000.0,
        best_trade=float(best) if n else 0.0,
        worst_trade=float(worst) if n else 0.0,
    )


def main():
    t = load_trades(TRADES)
    rts = roundtrips(t)
    print(f"Built {len(rts)} option roundtrips from v22_opts_live")
    if rts.empty:
        return

    overall_start = rts["entry"].min()
    overall_end = rts["entry"].max()
    print(f"History spans {overall_start.date()} -> {overall_end.date()}")

    results = []
    for s in pd.date_range(overall_start, overall_end - pd.Timedelta(days=WINDOW_DAYS), freq="1D"):
        e = s + pd.Timedelta(days=WINDOW_DAYS)
        res = simulate_window(rts, s, e, START_CASH)
        results.append(asdict(res))

    df = pd.DataFrame(results)
    out_json = OUT / "OPTIONS_V24_COMPOUND_FEEDBACK_10K.json"
    out_json.write_text(json.dumps({
        "start_cash": START_CASH,
        "target": 1_000_000,
        "window_days": WINDOW_DAYS,
        "windows_tested": len(results),
        "best_window": df.sort_values("final", ascending=False).iloc[0].to_dict() if not df.empty else None,
        "worst_window": df.sort_values("final", ascending=True).iloc[0].to_dict() if not df.empty else None,
        "reached_1m": int(df["reached_1m"].sum()),
        "results": results,
    }, indent=2, default=str))

    print(f"\nTested {len(results)} windows. Results saved to {out_json}")
    if df.empty:
        return
    print("\n=== Best window ===")
    print(df.sort_values("final", ascending=False).iloc[0].to_string())
    print("\n=== Worst window ===")
    print(df.sort_values("final", ascending=True).iloc[0].to_string())
    print("\n=== Reached 1M? ===")
    print(df["reached_1m"].value_counts())


if __name__ == "__main__":
    main()
