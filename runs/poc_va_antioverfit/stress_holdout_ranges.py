#!/usr/bin/env python3
"""Anti-overfit stress: frozen rules on held-out date ranges.

Goal (user ask): make sure models are not just optimizing known data —
test whether the SAME frozen filters still work on later / different ranges
they were not tuned on.

Protocol
--------
1. LOCK: choose / freeze filters using ONLY trades with entry_ts < lock_date
   (train WR lift only; never peek at post-lock outcomes for selection).
2. HOLD: score the frozen mask on entry_ts >= lock_date (true post-sample).
3. SLICES: also report metrics on fixed calendar slices (quarters / halves)
   under the frozen mask — stability check, not retuning.
4. FAIL FLAGS:
   - post-lock WR collapses >15pp vs lock-train WR
   - post-lock expectancy <= 0 while lock-train expectancy > 0
   - post-lock n < 5 (too thin to claim)
   - only early slices look good; late slices fail

This is trade-level meta stress on enriched_trades (v14 pool). Engine
re-runs on alternate start/end dates remain the gold standard for claim.

Outputs → runs/poc_va_antioverfit/artifacts/
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "artifacts"
OUT.mkdir(parents=True, exist_ok=True)
SRC = ROOT / "runs" / "poc_va_wr80" / "artifacts" / "enriched_trades.csv"


def _metrics(sub: pd.DataFrame) -> dict:
    if sub.empty:
        return {"n": 0, "wr": 0.0, "expectancy": 0.0, "pf": 0.0, "avg_ret": 0.0}
    wins = sub.loc[sub["win"] == 1, "return_pct"]
    losses = sub.loc[sub["win"] == 0, "return_pct"]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float((-losses).sum()) if len(losses) else 0.0
    pf = gp / gl if gl > 0 else (99.0 if gp > 0 else 0.0)
    return {
        "n": int(len(sub)),
        "wr": float(sub["win"].mean()),
        "expectancy": float(sub["return_pct"].mean()),
        "pf": float(pf),
        "avg_ret": float(sub["return_pct"].mean()),
    }


def _apply(df: pd.DataFrame, filters: list[str]) -> pd.DataFrame:
    out = df
    for f in filters:
        if f not in out.columns:
            raise KeyError(f"missing filter column: {f}")
        out = out[out[f].astype(bool)]
    return out


def _bool_filter_cols(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in df.columns:
        if c.startswith("f_") or c.startswith("drop_"):
            cols.append(c)
    return cols


def choose_filters_prelock(
    train: pd.DataFrame,
    candidates: list[str],
    max_filters: int = 3,
    min_retention: float = 0.2,
) -> list[str]:
    """Greedy train-only filter pick (never sees holdout)."""
    chosen: list[str] = []
    cur = train
    base_wr = float(cur["win"].mean()) if len(cur) else 0.0
    for _ in range(max_filters):
        best = None
        best_lift = -1e9
        for c in candidates:
            if c in chosen or c not in cur.columns:
                continue
            sub = cur[cur[c].astype(bool)]
            if len(sub) < max(5, int(len(train) * min_retention * 0.5)):
                continue
            if len(sub) / max(len(train), 1) < min_retention and len(chosen) > 0:
                # allow first filter to cut harder
                if len(chosen) >= 1 and len(sub) / max(len(cur), 1) < 0.25:
                    continue
            wr = float(sub["win"].mean())
            lift = wr - float(cur["win"].mean())
            if lift > best_lift:
                best_lift = lift
                best = c
        if best is None or best_lift < 0.01:
            break
        chosen.append(best)
        cur = cur[cur[best].astype(bool)]
    # if nothing beaten base, still return empty (honest)
    _ = base_wr
    return chosen


def stress_lock_dates(df: pd.DataFrame, lock_dates: list[str], preset_filters: dict[str, list[str]]) -> dict:
    report: dict = {"locks": {}, "presets": {}}
    candidates = _bool_filter_cols(df)

    for lock in lock_dates:
        lock_ts = pd.Timestamp(lock)
        train = df[df["entry_ts"] < lock_ts]
        hold = df[df["entry_ts"] >= lock_ts]
        auto = choose_filters_prelock(train, candidates)
        auto_train = _metrics(_apply(train, auto)) if auto else _metrics(train)
        auto_hold = _metrics(_apply(hold, auto)) if auto else _metrics(hold)
        flags = []
        if auto_hold["n"] < 5:
            flags.append("holdout_too_thin")
        if auto_train["n"] >= 8 and auto_hold["n"] >= 5:
            if auto_hold["wr"] < auto_train["wr"] - 0.15:
                flags.append("wr_collapse_gt_15pp")
            if auto_train["expectancy"] > 0 and auto_hold["expectancy"] <= 0:
                flags.append("expectancy_sign_flip")
        hard = [f for f in flags if f != "holdout_too_thin"]
        if hard:
            verdict = "FAIL"
        elif "holdout_too_thin" in flags:
            verdict = "THIN"
        else:
            verdict = "PASS"
        report["locks"][lock] = {
            "auto_filters_train_only": auto,
            "train": auto_train,
            "holdout": auto_hold,
            "flags": flags,
            "verdict": verdict,
        }

    # Preset frozen stacks (already decided models) — score across locks
    for name, filters in preset_filters.items():
        by_lock = {}
        for lock in lock_dates:
            lock_ts = pd.Timestamp(lock)
            # CRITICAL: presets are frozen; we only SCORE holdout, we do not rechoose
            train = df[df["entry_ts"] < lock_ts]
            hold = df[df["entry_ts"] >= lock_ts]
            tr = _metrics(_apply(train, filters))
            ho = _metrics(_apply(hold, filters))
            flags = []
            if ho["n"] < 5:
                flags.append("holdout_too_thin")
            if tr["n"] >= 8 and ho["n"] >= 5:
                if ho["wr"] < tr["wr"] - 0.15:
                    flags.append("wr_collapse_gt_15pp")
                if tr["expectancy"] > 0 and ho["expectancy"] <= 0:
                    flags.append("expectancy_sign_flip")
            hard = [f for f in flags if f != "holdout_too_thin"]
            if hard:
                verdict = "FAIL"
            elif "holdout_too_thin" in flags:
                verdict = "THIN"
            else:
                verdict = "PASS"
            by_lock[lock] = {
                "filters": filters,
                "train_pre_lock": tr,
                "holdout_post_lock": ho,
                "flags": flags,
                "verdict": verdict,
            }
        report["presets"][name] = by_lock
    return report


def calendar_slices(df: pd.DataFrame, filters: list[str]) -> dict:
    """Stability under frozen filters across calendar halves/quarters."""
    sub = _apply(df, filters)
    out = {"overall": _metrics(sub), "by_half": {}, "by_quarter": {}}
    if sub.empty:
        return out
    s = sub.copy()
    s["half"] = s["entry_ts"].apply(lambda t: f"{t.year}-H{1 if t.month <= 6 else 2}")
    s["quarter"] = s["entry_ts"].dt.to_period("Q").astype(str)
    for k, col in [("by_half", "half"), ("by_quarter", "quarter")]:
        for key, g in s.groupby(col):
            out[k][key] = _metrics(g)
    return out


def main() -> None:
    df = pd.read_csv(SRC)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"])
    df = df.sort_values("entry_ts").reset_index(drop=True)

    # Frozen stacks from existing research (do not retune here)
    presets = {
        "v15_qqq_trend_nonspy_proxy": ["f_qqq_trend"],
        "feedback_v16_path": ["f_not_red_flag", "drop_ARM.US", "f_qqq_trend"]
        if "f_not_red_flag" in df.columns
        else ["f_qqq_trend", "drop_ARM.US"],
        "sniper_apld_ionq_qqq": [
            c
            for c in ["f_qqq_trend", "drop_ARM.US", "drop_SPY.US", "drop_TSLA.US", "drop_MU.US"]
            if c in df.columns
        ],
    }
    # prefer explicit keep via drop others for sniper
    if "f_vol_expand" in df.columns or "f_volume_expand" in df.columns:
        ve = "f_vol_expand" if "f_vol_expand" in df.columns else "f_volume_expand"
        presets["sniper_plus_volexp"] = presets["sniper_apld_ionq_qqq"] + [ve]

    # Use mid-sample lock dates so both sides have trades
    lock_dates = ["2025-03-01", "2025-07-01", "2025-11-01", "2026-02-01"]

    report = {
        "source": str(SRC.relative_to(ROOT)),
        "n_trades": int(len(df)),
        "span": [str(df["entry_ts"].min().date()), str(df["entry_ts"].max().date())],
        "protocol": [
            "Choose filters only on pre-lock data (or use frozen presets)",
            "Score post-lock holdout without retuning",
            "Calendar slice stability under frozen mask",
            "FAIL if WR collapses >15pp or expectancy flips non-positive on holdout",
        ],
        "lock_stress": stress_lock_dates(df, lock_dates, presets),
        "calendar_stability": {
            name: calendar_slices(df, fl) for name, fl in presets.items()
        },
    }

    # Summary rollup
    summary_rows = []
    for name, by_lock in report["lock_stress"]["presets"].items():
        for lock, row in by_lock.items():
            summary_rows.append(
                {
                    "preset": name,
                    "lock_date": lock,
                    "verdict": row["verdict"],
                    "flags": ",".join(row["flags"]),
                    "train_n": row["train_pre_lock"]["n"],
                    "train_wr": row["train_pre_lock"]["wr"],
                    "hold_n": row["holdout_post_lock"]["n"],
                    "hold_wr": row["holdout_post_lock"]["wr"],
                    "hold_exp": row["holdout_post_lock"]["expectancy"],
                }
            )
    for lock, row in report["lock_stress"]["locks"].items():
        summary_rows.append(
            {
                "preset": "auto_train_only",
                "lock_date": lock,
                "verdict": row["verdict"],
                "flags": ",".join(row["flags"]),
                "train_n": row["train"]["n"],
                "train_wr": row["train"]["wr"],
                "hold_n": row["holdout"]["n"],
                "hold_wr": row["holdout"]["wr"],
                "hold_exp": row["holdout"]["expectancy"],
                "filters": ",".join(row["auto_filters_train_only"]),
            }
        )

    summary = pd.DataFrame(summary_rows)
    summary_path = OUT / "HOLDOUT_SUMMARY.csv"
    summary.to_csv(summary_path, index=False)
    report_path = OUT / "HOLDOUT_STRESS.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))

    fails = summary[summary["verdict"] == "FAIL"]
    print("Wrote", report_path)
    print("Wrote", summary_path)
    print(summary.to_string(index=False))
    print(
        "\nROLLUP:",
        f"PASS={int((summary.verdict=='PASS').sum())}",
        f"THIN={int((summary.verdict=='THIN').sum())}",
        f"FAIL={int((summary.verdict=='FAIL').sum())}",
    )
    if len(fails):
        print("OVERFIT RISK on rows:\n", fails.to_string(index=False))


if __name__ == "__main__":
    main()
