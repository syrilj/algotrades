#!/usr/bin/env python3
"""Apply Coulling book VPA findings to GEX/volume-z trade meta.

Ports the WORKING subset from v17b (no-demand block idea as effort/result check
at daily grain) onto existing stock-model trades used by volume_z_meta.

Filters tested (prior-day, no lookahead):
  - no_demand: daily return >0 and volume < 0.7 * 20d SMA
  - effort_ok: NOT (wide range + thin volume on up day)
  - stopping_reclaim proxy: prior 5d had high-vol narrow down day, then up day
  - combo with vol_z>=1 / >=2

Writes: models/poc_va_gex/artifacts/BOOK_VPA_META.json
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
    "v17b": ROOT / "runs" / "poc_va_book_vpa_light" / "artifacts" / "trades.csv",
}


def load_roundtrips(path, label):
    if not path.exists():
        return pd.DataFrame()
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


def daily_features(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, start="2024-06-01", end="2026-07-12", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    v = df["volume"].astype(float)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vsma = v.rolling(20, min_periods=10).mean()
    spread = (high - low).replace(0, np.nan)
    ssma = spread.rolling(20, min_periods=10).mean()
    ret = close.pct_change()
    price_up = ret > 0
    price_dn = ret < 0
    vol_low = v < (vsma * 0.7)
    vol_high = v > (vsma * 1.5)
    narrow = spread < (ssma * 0.75)
    wide = spread > (ssma * 1.25)
    no_demand = price_up & vol_low
    effort_anomaly = wide & vol_low
    effort_ok = ~effort_anomaly
    stopping = price_dn & vol_high & narrow
    stop_recent = stopping.rolling(5, min_periods=1).max().astype(bool)
    stopping_reclaim = stop_recent & price_up
    mu = v.rolling(20, min_periods=10).mean()
    sd = v.rolling(20, min_periods=10).std()
    vol_z = ((v - mu) / sd.replace(0, np.nan)).shift(1)
    out = pd.DataFrame(
        {
            "no_demand": no_demand.shift(1),  # prior day only
            "effort_ok": effort_ok.shift(1),
            "stopping_reclaim": stopping_reclaim.shift(1),
            "vol_z_20": vol_z,
        },
        index=df.index,
    )
    return out


def attach(trades: pd.DataFrame) -> pd.DataFrame:
    cache = {}
    rows = []
    for _, r in trades.iterrows():
        yf_t = r["code"].replace(".US", "")
        if yf_t not in cache:
            cache[yf_t] = daily_features(yf_t)
        feat = cache[yf_t]
        d = pd.Timestamp(r["entry_ts"]).normalize()
        if d < feat.index.min():
            rows.append({**r.to_dict(), "no_demand": np.nan, "effort_ok": np.nan, "stopping_reclaim": np.nan, "vol_z_20": np.nan})
            continue
        row = feat.asof(d)
        rows.append(
            {
                **r.to_dict(),
                "no_demand": bool(row["no_demand"]) if pd.notna(row["no_demand"]) else False,
                "effort_ok": bool(row["effort_ok"]) if pd.notna(row["effort_ok"]) else True,
                "stopping_reclaim": bool(row["stopping_reclaim"]) if pd.notna(row["stopping_reclaim"]) else False,
                "vol_z_20": float(row["vol_z_20"]) if pd.notna(row["vol_z_20"]) else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    out["not_no_demand"] = ~out["no_demand"].astype(bool)
    out["vol_z_ge1"] = out["vol_z_20"] >= 1.0
    out["vol_z_ge2"] = out["vol_z_20"] >= 2.0
    out["book_light"] = out["not_no_demand"] & out["effort_ok"]
    out["book_plus_volz1"] = out["book_light"] & out["vol_z_ge1"]
    return out


def wr(df):
    return float(df["win"].mean()) if len(df) else float("nan")


def exp(df):
    return float(df["return_pct"].mean()) if len(df) else float("nan")


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
        "train_lift": (wr(tr_on) - wr(train)) if len(tr_on) else None,
        "test_lift": (wr(te_on) - wr(test)) if len(te_on) else None,
        "train_exp": exp(tr_on),
        "test_exp": exp(te_on),
        "base_test_exp": exp(test),
        "test_exp_lift": (exp(te_on) - exp(test)) if len(te_on) else None,
    }


def main():
    frames = []
    for label, path in TRADE_FILES.items():
        df = load_roundtrips(path, label)
        if len(df):
            frames.append(df)
    if not frames:
        raise SystemExit("no trades found")
    trades = attach(pd.concat(frames, ignore_index=True))
    filters = ["not_no_demand", "effort_ok", "book_light", "vol_z_ge1", "vol_z_ge2", "book_plus_volz1", "stopping_reclaim"]
    report = {
        "hypothesis": "Coulling no-demand/effort filters from books lift OOS WR on stock trades; combine with vol_z for GEX path",
        "n_trades": int(len(trades)),
        "sources": {k: int((trades.source == k).sum()) for k in trades.source.unique()},
        "walk_forward": [walk_forward(trades, c) for c in filters],
    }
    # pick best OOS by test_lift then test_exp_lift
    ranked = sorted(
        [w for w in report["walk_forward"] if w["test_n"] and w["test_n"] >= 10],
        key=lambda w: (w["test_lift"] or -1, w["test_exp_lift"] or -1),
        reverse=True,
    )
    report["best_oos"] = ranked[0] if ranked else None
    report["verdict"] = (
        "USE"
        if ranked and (ranked[0]["test_lift"] or 0) > 0 and (ranked[0]["test_exp_lift"] or 0) >= 0
        else "WEAK_OR_FAIL"
    )
    out_path = OUT / "BOOK_VPA_META.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(json.dumps({"verdict": report["verdict"], "best_oos": report["best_oos"], "out": str(out_path)}, indent=2))


if __name__ == "__main__":
    main()
