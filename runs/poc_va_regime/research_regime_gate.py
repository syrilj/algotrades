#!/usr/bin/env python3
"""Walk-forward regime research for poc_va_macdha.

Hypothesis (user): high-beta names (TSLA/ARM/IONQ/APLD) are pegged to Nasdaq;
if Mag7 / QQQ is dumping, technical longs fail. Gate entries on index regime.

Anti-overfit rules:
- Only binary / structural gates (no continuous threshold grid search)
- Select gate combo on TRAIN half only; report TEST (OOS) metrics separately
- Promote only if OOS win-rate lift > 0 AND OOS expectancy not worse
- Writes proof JSON for audit; does not mutate WINNER unless OOS passes

LSE drawdown framing (https://londonstrategicedge.com/machine-learning/risk-management/drawdown-analysis/):
fewer, higher-quality trades + risk overlay > more trades chasing WR vanity.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)

HIGH_BETA = {"TSLA.US", "ARM.US", "IONQ.US", "APLD.US"}
MAG7_YF = ["AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "TSLA"]
START, END = "2024-07-01", "2026-07-12"  # pad before window for MAs


def _to_bt(code: str) -> str:
    return code if code.endswith(".US") else f"{code}.US"


def fetch_daily(tickers: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for t in tickers:
        df = yf.download(t, start=START, end=END, interval="1d", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        out[_to_bt(t)] = df
    return out


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def ha_macd_green(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.Series:
    """MACD hist >0 and rising; decision uses prior bar only (no lookahead)."""
    c = df["close"]
    macd = ema(c, fast) - ema(c, slow)
    sig = ema(macd, signal)
    hist = macd - sig
    green = (hist > 0) & (hist > hist.shift(1))
    return green.shift(1).fillna(False)


def above_sma(df: pd.DataFrame, n: int = 20) -> pd.Series:
    sma = df["close"].rolling(n, min_periods=n).mean()
    return (df["close"] > sma).shift(1).fillna(False)


def build_regime(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    qqq = data["QQQ.US"]
    idx = qqq.index
    mag7 = []
    for t in MAG7_YF:
        code = _to_bt(t)
        if code not in data:
            continue
        mag7.append(above_sma(data[code], 20).reindex(idx).ffill().fillna(False))
    breadth = pd.concat(mag7, axis=1).sum(axis=1) if mag7 else pd.Series(0, index=idx)
    n_mag = max(len(mag7), 1)
    regime = pd.DataFrame(
        {
            "qqq_htf_green": ha_macd_green(qqq).reindex(idx).fillna(False),
            "qqq_above_sma20": above_sma(qqq, 20).reindex(idx).fillna(False),
            "qqq_ret5_pos": (qqq["close"].pct_change(5) > 0).shift(1).fillna(False),
            "mag7_breadth": breadth,
            "mag7_breadth_ge4": (breadth >= 4).astype(bool),
            "mag7_breadth_ge5": (breadth >= 5).astype(bool),
            "mag7_frac": breadth / n_mag,
        },
        index=idx,
    )
    regime["gate_qqq_green"] = regime["qqq_htf_green"]
    regime["gate_qqq_trend"] = regime["qqq_htf_green"] & regime["qqq_above_sma20"]
    regime["gate_mag7_majority"] = regime["mag7_breadth_ge4"]
    regime["gate_qqq_and_mag7"] = regime["qqq_htf_green"] & regime["mag7_breadth_ge4"]
    regime["gate_full"] = (
        regime["qqq_htf_green"] & regime["qqq_above_sma20"] & regime["mag7_breadth_ge4"]
    )
    return regime


def load_roundtrips(path: Path, label: str) -> pd.DataFrame:
    t = pd.read_csv(path, parse_dates=["timestamp"])
    buys = t[t.side == "buy"].reset_index(drop=True)
    sells = t[t.side == "sell"].reset_index(drop=True)
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
                    "exit_ts": gs.loc[i, "timestamp"],
                    "pnl": float(gs.loc[i, "pnl"]),
                    "return_pct": float(gs.loc[i, "return_pct"]),
                    "holding_days": float(gs.loc[i, "holding_days"]),
                    "win": float(gs.loc[i, "pnl"] > 0),
                    "bucket": (
                        "high_beta"
                        if code in HIGH_BETA
                        else ("index" if code == "SPY.US" else "traditional")
                    ),
                }
            )
    return pd.DataFrame(rows)


def attach_regime(trades: pd.DataFrame, regime: pd.DataFrame) -> pd.DataFrame:
    r = regime.copy()
    r.index = pd.to_datetime(r.index)
    dates = pd.to_datetime(trades["entry_ts"]).dt.normalize()
    joined = trades.copy()
    for col in r.columns:
        joined[col] = dates.map(lambda d, c=col: r[c].asof(d) if d >= r.index.min() else np.nan)
    bool_cols = [
        c
        for c in r.columns
        if c.startswith("gate_") or c.startswith("qqq_") or c.startswith("mag7_breadth_ge")
    ]
    for col in bool_cols:
        joined[col] = joined[col].fillna(False).astype(bool)
    return joined


def metrics(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {"n": 0, "wr": np.nan, "exp": np.nan, "avg_ret": np.nan}
    return {
        "n": int(len(df)),
        "wr": float(df["win"].mean()),
        "exp": float(df["return_pct"].mean()),
        "avg_ret": float(df["return_pct"].mean()),
        "sum_pnl": float(df["pnl"].sum()),
    }


def walk_forward_select(trades: pd.DataFrame, gates: list[str], apply_mask: pd.Series) -> dict:
    """Chronological 50/50 split. Pick best gate on train; evaluate on test only."""
    t = trades.sort_values("entry_ts").reset_index(drop=True)
    apply_mask = apply_mask.reindex(t.index).fillna(False)
    mid = len(t) // 2
    train, test = t.iloc[:mid], t.iloc[mid:]
    base_train, base_test = metrics(train), metrics(test)

    candidates = []
    for g in gates:
        keep_train = (~apply_mask.loc[train.index]) | train[g].astype(bool)
        keep_test = (~apply_mask.loc[test.index]) | test[g].astype(bool)
        tr, te = train[keep_train], test[keep_test]
        mt, me = metrics(tr), metrics(te)
        retention = mt["n"] / max(base_train["n"], 1)
        lift_train = (mt["wr"] - base_train["wr"]) if mt["n"] else -1.0
        lift_test = (me["wr"] - base_test["wr"]) if me["n"] else -1.0
        candidates.append(
            {
                "gate": g,
                "train": mt,
                "test": me,
                "train_retention": float(retention),
                "lift_wr_train": float(lift_train),
                "lift_wr_test": float(lift_test),
                "lift_exp_test": float((me["exp"] - base_test["exp"]) if me["n"] else -999),
                "eligible_train": bool(retention >= 0.40 and mt["n"] >= 20),
            }
        )

    eligible = [c for c in candidates if c["eligible_train"]]
    eligible.sort(key=lambda c: (c["lift_wr_train"], c["train"]["exp"]), reverse=True)
    winner = eligible[0] if eligible else None

    oos_pass = False
    if winner is not None:
        # Require positive train AND test lift — no promoting train losers that luck into OOS.
        oos_pass = (
            winner["lift_wr_train"] > 0.0
            and winner["lift_wr_test"] > 0.0
            and winner["lift_exp_test"] >= -0.05
            and winner["test"]["n"] >= 15
        )

    return {
        "base_train": base_train,
        "base_test": base_test,
        "candidates": candidates,
        "selected_on_train": winner["gate"] if winner else None,
        "selected": winner,
        "oos_pass": bool(oos_pass),
        "selection_rule": (
            "max train WR lift among gates with train retention>=40% and n>=20; "
            "OOS pass if test WR lift>0, exp not worse by >5bp, n>=15"
        ),
    }


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    return o


def main():
    print("Fetching QQQ + Mag7 daily…")
    data = fetch_daily(["QQQ"] + MAG7_YF)
    regime = build_regime(data)
    regime.to_csv(OUT / "regime_daily.csv")

    trade_files = {
        "v13_specialists": ROOT / "runs" / "poc_va_macdha" / "artifacts" / "trades.csv",
        "v14_risk_kelly": ROOT / "runs" / "poc_va_risk" / "artifacts" / "trades.csv",
    }
    gates = [
        "gate_qqq_green",
        "gate_qqq_trend",
        "gate_mag7_majority",
        "gate_qqq_and_mag7",
        "gate_full",
    ]

    report = {
        "hypothesis": (
            "High-beta longs need constructive Nasdaq (QQQ) + Mag7 breadth; "
            "block when mega-caps dump."
        ),
        "anti_overfit": [
            "binary/structural gates only",
            "gate chosen on train half only",
            "OOS test must show WR lift and stable expectancy",
            "no continuous threshold grid search",
        ],
        "lse_reference": (
            "https://londonstrategicedge.com/machine-learning/risk-management/drawdown-analysis/"
        ),
        "sources": {},
        "regime_feature_defs": {
            "qqq_htf_green": "prior-bar QQQ daily MACD hist >0 and rising",
            "qqq_above_sma20": "prior-bar close > SMA20",
            "mag7_breadth_ge4": ">=4 of Mag7 above own SMA20 (prior bar)",
            "gate_qqq_and_mag7": "qqq_htf_green AND mag7_breadth_ge4",
        },
    }

    for label, path in trade_files.items():
        if not path.exists():
            print(f"skip missing {path}")
            continue
        trades = load_roundtrips(path, label)
        trades = attach_regime(trades, regime)
        trades.to_csv(OUT / f"trades_with_regime_{label}.csv", index=False)

        desc = {}
        for g in gates:
            for bucket, sub in trades.groupby("bucket"):
                on = sub[sub[g]]
                off = sub[~sub[g]]
                desc[f"{bucket}|{g}"] = {
                    "wr_on": metrics(on),
                    "wr_off": metrics(off),
                    "lift": (
                        (metrics(on)["wr"] - metrics(off)["wr"])
                        if len(on) and len(off)
                        else None
                    ),
                }

        apply_hb = trades["bucket"].isin(["high_beta", "traditional"])
        wf_hb = walk_forward_select(trades, gates, apply_hb)

        hb_only = trades[trades["bucket"] == "high_beta"].copy()
        apply_all = pd.Series(True, index=hb_only.index)
        wf_strict = walk_forward_select(hb_only, gates, apply_all)

        report["sources"][label] = {
            "n_trades": int(len(trades)),
            "base_wr": float(trades["win"].mean()),
            "descriptive_lifts": desc,
            "walk_forward_apply_to_non_SPY": wf_hb,
            "walk_forward_high_beta_only": wf_strict,
        }
        print(f"\n=== {label} ===")
        print(f"base WR={trades['win'].mean()*100:.1f}% n={len(trades)}")
        print(f"WF non-SPY selected={wf_hb['selected_on_train']} OOS_pass={wf_hb['oos_pass']}")
        if wf_hb["selected"]:
            s = wf_hb["selected"]
            print(
                f"  train lift WR={s['lift_wr_train']*100:+.1f}pp ret={s['train_retention']*100:.0f}% | "
                f"OOS lift WR={s['lift_wr_test']*100:+.1f}pp n={s['test']['n']} expΔ={s['lift_exp_test']:+.3f}"
            )
        print(f"WF high_beta selected={wf_strict['selected_on_train']} OOS_pass={wf_strict['oos_pass']}")
        if wf_strict["selected"]:
            s = wf_strict["selected"]
            print(
                f"  train lift WR={s['lift_wr_train']*100:+.1f}pp | "
                f"OOS lift WR={s['lift_wr_test']*100:+.1f}pp n={s['test']['n']}"
            )

    # Rank all OOS-passing selections by OOS WR lift (audit: not first-match).
    promote_candidates = []
    for label in ("v14_risk_kelly", "v13_specialists"):
        src = report["sources"].get(label)
        if not src:
            continue
        for key in ("walk_forward_apply_to_non_SPY", "walk_forward_high_beta_only"):
            wf = src[key]
            if wf.get("oos_pass") and wf.get("selected"):
                promote_candidates.append(
                    {
                        "base_model": label,
                        "gate": wf["selected_on_train"],
                        "apply_to": "high_beta" if "high_beta" in key else "non_SPY",
                        "wf_key": key,
                        "oos_test": wf["selected"]["test"],
                        "lift_wr_train": wf["selected"]["lift_wr_train"],
                        "lift_wr_test": wf["selected"]["lift_wr_test"],
                        "lift_exp_test": wf["selected"]["lift_exp_test"],
                        "train_retention": wf["selected"]["train_retention"],
                    }
                )
    promote_candidates.sort(
        key=lambda c: (c["lift_wr_test"], c["lift_exp_test"], c["lift_wr_train"]),
        reverse=True,
    )
    # Prefer risk-overlay base when lifts are close (<1pp WR)
    promote = promote_candidates[0] if promote_candidates else None
    if len(promote_candidates) > 1:
        best = promote_candidates[0]
        for alt in promote_candidates[1:]:
            if (
                alt["base_model"] == "v14_risk_kelly"
                and best["base_model"] != "v14_risk_kelly"
                and (best["lift_wr_test"] - alt["lift_wr_test"]) < 0.01
            ):
                promote = alt
                break

    report["promote"] = promote
    report["promote_candidates"] = promote_candidates
    report["promote_rule"] = (
        "OOS_pass requires train+test WR lift>0, exp stable, n_test>=15. "
        "Rank by OOS WR lift; prefer v14_risk_kelly when within 1pp (drawdown control)."
    )

    out_path = OUT / "REGIME_PROOF.json"
    out_path.write_text(json.dumps(_clean(report), indent=2))
    print(f"\nWrote {out_path}")
    print("PROMOTE:", json.dumps(promote, indent=2))


if __name__ == "__main__":
    main()
