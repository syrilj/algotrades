#!/usr/bin/env python3
"""Head-to-head pure OOS challenge: v29 cold-start variants vs v22 champ.

Only pure OOS folds (no full-window promotion). Disk-light: one fold at a time,
delete non-essential intermediate artifacts after metrics read.

Usage:
  .venv/bin/python tools/oos_challenge_v29.py
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from backtest.runner import main as bt_main

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "poc_va_v29_oos_challenge"
STATE = OUT / "CHALLENGE.json"
REPORT = OUT / "REPORT.md"

ENG = {
    "v22": ROOT / "models" / "poc_va_macdha" / "v22_opts_live" / "signal_engine.py",
    "v29": ROOT / "models" / "poc_va_macdha" / "v29_coldstart_opts" / "signal_engine.py",
    "v26": ROOT / "models" / "poc_va_macdha" / "v22_opts_live" / "signal_engine.py",
}

CODES = ["IONQ.US", "AVGO.US", "HOOD.US", "MU.US"]
CASH = 1_000_000

# Pure OOS folds only (same as oos_rank_opts promotion set)
FOLDS = [
    ("holdout_late", "2025-07-01", "2026-07-11"),
    ("holdout_post_discovery", "2025-01-01", "2026-07-11"),
    ("wf_fold1", "2025-01-01", "2025-06-30"),
    ("wf_fold2", "2025-07-01", "2025-12-31"),
    ("wf_fold3", "2026-01-01", "2026-07-11"),
]

MODELS = [
    {
        "id": "v22_21dte",
        "engine": "v22",
        "hc": {
            "risk_pct": 0.10,
            "dte_days": 21,
            "otm_pct": 0.0,
            "halt_dd": 0.30,
            "flatten_dd": 0.45,
            "initial_cash": CASH,
            "contract_multiplier": 100,
            "max_contracts": 500,
        },
    },
    {
        "id": "v29_coldstart",
        "engine": "v29",
        "hc": json.loads(
            (ROOT / "models/poc_va_macdha/v29_coldstart_opts/hunt_config.json").read_text()
        ),
    },
    {
        "id": "v29_surgical_only",
        "engine": "v29",
        "hc": {
            "risk_pct": 0.10,
            "dte_days": 21,
            "otm_pct": 0.0,
            "halt_dd": 0.30,
            "flatten_dd": 0.45,
            "initial_cash": CASH,
            "contract_multiplier": 100,
            "max_contracts": 500,
            "use_narrative": True,
            "narrative_mode": "surgical",
            "loss_cooloff_days": 0,
            "streak_losses_for_cut": 99,
            "streak_size_mult": 1.0,
            "min_size_frac": 0.35,
            "max_size_frac": 1.0,
        },
    },
    {
        "id": "v29_cooloff_only",
        "engine": "v29",
        "hc": {
            "risk_pct": 0.10,
            "dte_days": 21,
            "otm_pct": 0.0,
            "halt_dd": 0.30,
            "flatten_dd": 0.45,
            "initial_cash": CASH,
            "contract_multiplier": 100,
            "max_contracts": 500,
            "use_narrative": False,
            "narrative_mode": "off",
            "loss_cooloff_days": 5,
            "streak_losses_for_cut": 99,
            "streak_size_mult": 1.0,
            "min_size_frac": 0.35,
            "max_size_frac": 1.0,
        },
    },
    {
        "id": "v26_14dte",
        "engine": "v26",
        "hc": {
            "risk_pct": 0.10,
            "dte_days": 14,
            "otm_pct": 0.0,
            "halt_dd": 0.30,
            "flatten_dd": 0.45,
            "initial_cash": CASH,
            "contract_multiplier": 100,
            "max_contracts": 500,
        },
    },
]


def score(r: dict) -> float:
    if r.get("n", 0) == 0:
        return -0.5 + 0.01 * r.get("ret", 0.0)
    return (
        1.0 * r["ret"]
        + 0.15 * r.get("wr", 0.0)
        + 0.10 * min(r.get("sharpe", 0.0), 2.0) / 2.0
        - 0.40 * abs(r.get("dd", 0.0))
    )


def run_one(model: dict, start: str, end: str, fold: str) -> dict:
    run_dir = OUT / fold / model["id"]
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "code").mkdir(parents=True)
    cfg = {
        "source": "yfinance",
        "codes": CODES,
        "start_date": start,
        "end_date": end,
        "initial_cash": CASH,
        "commission": 0.001,
        "engine": "options",
        "interval": "1D",
        "options_config": {
            "risk_free_rate": 0.05,
            "contract_multiplier": 100,
            "exercise_style": "american",
        },
        "strategy": {"model_version": model["id"], "fold": fold},
    }
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    (run_dir / "code" / "hunt_config.json").write_text(json.dumps(model["hc"], indent=2))
    (run_dir / "code" / "signal_engine.py").write_text(ENG[model["engine"]].read_text())
    print(f"  {fold} / {model['id']}  {start}→{end}", flush=True)
    try:
        bt_main(run_dir.resolve())
        row = next(csv.DictReader(open(run_dir / "artifacts" / "metrics.csv")))
        res = {
            "id": model["id"],
            "ret": float(row["total_return"]),
            "dd": float(row["max_drawdown"]),
            "sharpe": float(row["sharpe"]),
            "n": int(float(row["trade_count"])),
            "wr": float(row["win_rate"]),
            "final": float(row["final_value"]),
        }
        # disk: drop ohlcv copies after metrics
        art = run_dir / "artifacts"
        for p in art.glob("ohlcv_*.csv"):
            p.unlink(missing_ok=True)
        return res
    except Exception as e:  # noqa: BLE001
        print("   FAIL", e, flush=True)
        return {
            "id": model["id"],
            "error": str(e),
            "ret": -9.0,
            "dd": -1.0,
            "sharpe": 0.0,
            "n": 0,
            "wr": 0.0,
            "final": 0.0,
        }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fold_rankings = {}
    for name, start, end in FOLDS:
        print(f"\n======== {name} {start}→{end} ========", flush=True)
        rows = [run_one(m, start, end, name) for m in MODELS]
        ok = [r for r in rows if "error" not in r]
        ok.sort(key=score, reverse=True)
        fold_rankings[name] = ok
        for r in ok:
            print(
                f"  {r['id']:22} ret={r['ret']*100:7.1f}% dd={r['dd']*100:6.1f}% "
                f"sh={r['sharpe']:5.2f} n={r['n']:3d} wr={r['wr']*100:4.0f}% score={score(r):.3f}",
                flush=True,
            )

    ids = [m["id"] for m in MODELS]
    agg = []
    for mid in ids:
        scores, rets, dds, ns, wins = [], [], [], [], 0
        fold_rets = {}
        for fname, rows in fold_rankings.items():
            r = next((x for x in rows if x["id"] == mid), None)
            if not r:
                continue
            scores.append(score(r))
            rets.append(r["ret"])
            dds.append(r["dd"])
            ns.append(r["n"])
            fold_rets[fname] = r["ret"]
            if rows and rows[0]["id"] == mid:
                wins += 1
        if not scores:
            continue
        agg.append(
            {
                "id": mid,
                "mean_oos_score": mean(scores),
                "mean_oos_ret": mean(rets),
                "mean_oos_dd": mean(dds),
                "mean_oos_n": mean(ns),
                "fold_wins": wins,
                "n_folds": len(scores),
                "fold_rets": fold_rets,
            }
        )
    agg.sort(key=lambda x: (x["mean_oos_score"], x["fold_wins"]), reverse=True)
    champ = agg[0] if agg else None
    v22 = next((a for a in agg if a["id"] == "v22_21dte"), None)
    beats = bool(
        champ
        and v22
        and champ["id"] != "v22_21dte"
        and champ["mean_oos_score"] > v22["mean_oos_score"]
    )

    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "promotion_rule": "mean OOS score across pure folds; must beat v22_21dte",
        "folds": {k: v for k, v in fold_rankings.items()},
        "aggregate": agg,
        "champion": champ,
        "baseline_v22": v22,
        "beats_v22": beats,
    }
    STATE.write_text(json.dumps(state, indent=2))

    lines = [
        "# v29 cold-start OOS challenge",
        "",
        f"Generated: {state['updated_at']}",
        "",
        f"**beats_v22:** `{beats}`",
        f"**champion:** `{champ['id'] if champ else None}`",
        "",
        "## Aggregate (pure OOS)",
        "",
        "| model | mean score | mean ret | mean DD | fold wins |",
        "|-------|------------|----------|---------|-----------|",
    ]
    for a in agg:
        mark = " **← champ**" if champ and a["id"] == champ["id"] else ""
        lines.append(
            f"| {a['id']}{mark} | {a['mean_oos_score']:.3f} | {a['mean_oos_ret']*100:.1f}% | "
            f"{a['mean_oos_dd']*100:.1f}% | {a['fold_wins']}/{a['n_folds']} |"
        )
    lines += ["", "## Per-fold returns", ""]
    for fname, rows in fold_rankings.items():
        lines.append(f"### {fname}")
        for r in rows:
            lines.append(
                f"- {r['id']}: ret={r['ret']*100:.1f}% dd={r['dd']*100:.1f}% "
                f"n={r['n']} wr={r['wr']*100:.0f}% score={score(r):.3f}"
            )
        lines.append("")
    if beats and champ:
        lines += [
            "## Promotion",
            "",
            f"Promote `{champ['id']}` as OPTIONS default (beats v22 on pure OOS).",
            "",
        ]
    else:
        lines += [
            "## Promotion",
            "",
            "Do **not** replace v22 — no variant beat mean OOS score.",
            "Keep `OPTIONS_WINNER.json` → v22_opts_live.",
            "",
        ]
    REPORT.write_text("\n".join(lines))

    print("\n======== AGGREGATE ========", flush=True)
    for a in agg:
        print(
            f"{a['id']:22} mean_score={a['mean_oos_score']:.3f} "
            f"mean_ret={a['mean_oos_ret']*100:6.1f}% mean_dd={a['mean_oos_dd']*100:5.1f}% "
            f"wins={a['fold_wins']}/{a['n_folds']}",
            flush=True,
        )
    print(f"\nCHAMPION: {champ['id'] if champ else None}  beats_v22={beats}", flush=True)
    print(f"State → {STATE}", flush=True)
    print(f"Report → {REPORT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
