#!/usr/bin/env python3
"""Volume z-score meta study on existing stock-model trades.

Fully backtestable (no options history). Tests whether vol_z>=2 at entry
lifts WR / expectancy — precursor to full GEX meta.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "models" / "poc_va_gex" / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)

TRADE_FILES = {
    "v15": ROOT / "runs" / "poc_va_regime" / "artifacts" / "trades.csv",
    "v14": ROOT / "runs" / "poc_va_risk" / "artifacts" / "trades.csv",
}


def load_roundtrips(path, label):
    t = pd.read_csv(path, parse_dates=["timestamp"])
    buys, sells = t[t.side == "buy"], t[t.side == "sell"]
    rows = []
    for code, gb in buys.groupby("code"):
        gs = sells[sells.code == code].reset_index(drop=True)
        gb = gb.reset_index(drop=True)
        n = min(len(gb), len(gs))
        for i in range(n):
            rows.append(
                {
                    "source": label,
                    "code": code,
                    "entry_ts": gb.loc[i, "timestamp"],
                    "pnl": float(gs.loc[i, "pnl"]),
                    "return_pct": float(gs.loc[i, "return_pct"]),
                    "win": float(gs.loc[i, "pnl"] > 0),
                }
            )
    return pd.DataFrame(rows)


def daily_vol_z(ticker: str) -> pd.Series:
    df = yf.download(ticker, start="2024-06-01", end="2026-07-12", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    v = df["volume"].astype(float)
    mu = v.rolling(20, min_periods=10).mean()
    sd = v.rolling(20, min_periods=10).std()
    z = (v - mu) / sd.replace(0, np.nan)
    # prior day only (no lookahead)
    return z.shift(1)


def attach(trades: pd.DataFrame) -> pd.DataFrame:
    cache = {}
    zs = []
    for _, r in trades.iterrows():
        yf_t = r["code"].replace(".US", "")
        if yf_t not in cache:
            cache[yf_t] = daily_vol_z(yf_t)
        zser = cache[yf_t]
        d = pd.Timestamp(r["entry_ts"]).normalize()
        zs.append(float(zser.asof(d)) if d >= zser.index.min() else np.nan)
    out = trades.copy()
    out["vol_z_20"] = zs
    out["vol_z_ge1"] = out["vol_z_20"] >= 1.0
    out["vol_z_ge2"] = out["vol_z_20"] >= 2.0
    out["vol_z_ge3"] = out["vol_z_20"] >= 3.0
    return out


def wr(df):
    return float(df["win"].mean()) if len(df) else float("nan")


def walk_forward(df, col):
    df = df.sort_values("entry_ts").reset_index(drop=True)
    mid = int(len(df) * 0.6)
    train, test = df.iloc[:mid], df.iloc[mid:]
    tr_on, te_on = train[train[col]], test[test[col]]
    return {
        "filter": col,
        "base_train_wr": wr(train),
        "base_test_wr": wr(test),
        "train_wr": wr(tr_on),
        "test_wr": wr(te_on),
        "train_n": int(len(tr_on)),
        "test_n": int(len(te_on)),
        "train_lift": wr(tr_on) - wr(train) if len(tr_on) else None,
        "test_lift": wr(te_on) - wr(test) if len(te_on) else None,
        "train_exp": float(tr_on["return_pct"].mean()) if len(tr_on) else None,
        "test_exp": float(te_on["return_pct"].mean()) if len(te_on) else None,
    }


def main():
    report = {"hypothesis": "vol_z>=2 at entry lifts OOS WR on stock-primary trades", "sources": {}}
    for label, path in TRADE_FILES.items():
        if not path.exists():
            continue
        trades = load_roundtrips(path, label)
        enr = attach(trades)
        enr.to_csv(OUT / f"trades_volz_{label}.csv", index=False)
        results = [walk_forward(enr, c) for c in ("vol_z_ge1", "vol_z_ge2", "vol_z_ge3")]
        report["sources"][label] = {
            "n": len(enr),
            "base_wr": wr(enr),
            "filters": results,
        }
        print(f"\n=== {label} base WR={wr(enr)*100:.1f}% n={len(enr)} ===")
        for r in results:
            print(
                f"  {r['filter']}: train {r['train_wr']*100 if r['train_wr']==r['train_wr'] else float('nan'):.1f}% "
                f"(n={r['train_n']}) | test {r['test_wr']*100 if r['test_wr']==r['test_wr'] else float('nan'):.1f}% "
                f"(n={r['test_n']}) lift_test={None if r['test_lift'] is None else round(100*r['test_lift'],1)}pp"
            )
    (OUT / "VOLUME_Z_META.json").write_text(json.dumps(report, indent=2))
    print("\nWrote", OUT / "VOLUME_Z_META.json")


if __name__ == "__main__":
    main()
