#!/usr/bin/env python3
"""Local Mag7-aware engine smoke/backtest for v18_dual_sleeve.

Uses cached OHLCV under runs/poc_va_wr80/artifacts (no live download).
Produces trades + PASS_BAR check. Not a substitute for the full run harness,
but enough to gate promotion claims before wiring an official run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = ROOT / "runs" / "poc_va_wr80" / "artifacts"
ENG_DIR = ROOT / "models" / "poc_va_macdha" / "v18_dual_sleeve"
PASS_BAR = json.loads((ROOT / "models" / "_shared" / "PASS_BAR.json").read_text())

CODES = [
    "APLD.US",
    "IONQ.US",
    "TSLA.US",
    "MU.US",
    "QQQ.US",
    "AAPL.US",
    "MSFT.US",
    "NVDA.US",
    "GOOGL.US",
    "AMZN.US",
    "META.US",
]


def load(code: str) -> pd.DataFrame:
    p = CACHE / f"ohlcv_{code}.csv"
    if not p.exists():
        raise FileNotFoundError(p)
    df = pd.read_csv(p)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def signals_to_trades(code: str, sig: pd.Series, px: pd.Series) -> list[dict]:
    """Entry on signal rising from 0; exit on return to 0. PnL on close-to-close."""
    s = sig.fillna(0.0).astype(float)
    p = px.reindex(s.index).ffill()
    trades = []
    in_pos = False
    entry_ts = entry_px = None
    for ts, v in s.items():
        if not in_pos and v > 0:
            in_pos = True
            entry_ts = ts
            entry_px = float(p.loc[ts])
        elif in_pos and v <= 0:
            exit_px = float(p.loc[ts])
            ret = (exit_px / entry_px - 1.0) * 100.0 if entry_px else 0.0
            trades.append(
                {
                    "code": code,
                    "entry_ts": str(entry_ts),
                    "exit_ts": str(ts),
                    "entry_px": entry_px,
                    "exit_px": exit_px,
                    "return_pct": ret,
                    "win": int(ret > 0),
                    "sleeve": "sniper" if code in ("APLD.US", "IONQ.US") else "large",
                }
            )
            in_pos = False
    return trades


def metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "avg_return": 0.0,
            "total_return_sum_pct": 0.0,
        }
    wins = trades.loc[trades.win == 1, "return_pct"]
    losses = trades.loc[trades.win == 0, "return_pct"]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float((-losses).sum()) if len(losses) else 0.0
    pf = gp / gl if gl > 0 else (99.0 if gp > 0 else 0.0)
    # crude Sharpe on trade returns (not equity curve)
    r = trades["return_pct"].astype(float)
    sharpe = float(r.mean() / r.std() * np.sqrt(len(r))) if r.std() > 0 else 0.0
    return {
        "trade_count": int(len(trades)),
        "win_rate": float(trades.win.mean()),
        "expectancy": float(r.mean()),
        "profit_factor": float(pf),
        "avg_return": float(r.mean()),
        "total_return_sum_pct": float(r.sum()),
        "sharpe_trade_proxy": sharpe,
        "max_loss_pct": float(r.min()) if len(r) else 0.0,
    }


def pass_bar_check(m: dict) -> dict:
    g = PASS_BAR["gates"]
    reasons = []
    if m["profit_factor"] < g["profit_factor_min"]:
        reasons.append(f"PF {m['profit_factor']:.2f} < {g['profit_factor_min']}")
    if m["trade_count"] < g["min_trades"]:
        reasons.append(f"trades {m['trade_count']} < {g['min_trades']}")
    if m.get("expectancy", 0) < g["expectancy_after_costs_min"]:
        reasons.append("expectancy <= 0")
    # DD / sharpe need equity curve — mark as not_evaluated for DD
    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "note": "Local proxy: DD/equity Sharpe not fully evaluated; trade Sharpe is proxy only",
    }


def main() -> None:
    sys.path.insert(0, str(ENG_DIR))
    import signal_engine as se  # noqa: E402

    data_map = {c: load(c) for c in CODES}
    eng = se.SignalEngine()
    sigs = eng.generate(data_map)

    trades = []
    for code in ("APLD.US", "IONQ.US", "TSLA.US", "MU.US"):
        trades.extend(signals_to_trades(code, sigs[code], data_map[code]["close"]))
    tdf = pd.DataFrame(trades)
    if not tdf.empty:
        tdf["entry_ts"] = pd.to_datetime(tdf["entry_ts"])
        tdf = tdf.sort_values("entry_ts")
    tdf.to_csv(OUT / "v18_dual_sleeve_trades.csv", index=False)

    overall = metrics(tdf)
    by_sleeve = {}
    if not tdf.empty:
        for sleeve, g in tdf.groupby("sleeve"):
            by_sleeve[sleeve] = metrics(g)
        by_code = {code: metrics(g) for code, g in tdf.groupby("code")}
    else:
        by_code = {}

    # chronological 60/40 OOS on engine trades
    oos = {}
    if len(tdf) >= 8:
        cut = int(len(tdf) * 0.6)
        oos = {
            "train": metrics(tdf.iloc[:cut]),
            "test": metrics(tdf.iloc[cut:]),
        }

    pb = pass_bar_check(overall)
    report = {
        "model": "v18_dual_sleeve",
        "source_cache": str(CACHE.relative_to(ROOT)),
        "window": [
            str(min(df.index.min() for df in data_map.values()).date()),
            str(max(df.index.max() for df in data_map.values()).date()),
        ],
        "overall": overall,
        "by_sleeve": by_sleeve,
        "by_code": by_code,
        "oos_60_40": oos,
        "pass_bar": pb,
        "promote": False,
        "promote_reason": (
            "PASS_BAR cleared on local proxy — still need official run harness equity/DD"
            if pb["passed"]
            else "Do not promote: " + "; ".join(pb["reasons"])
        ),
    }
    (OUT / "V18_ENGINE_PROXY.json").write_text(json.dumps(report, indent=2))
    (ENG_DIR / "results_proxy.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
