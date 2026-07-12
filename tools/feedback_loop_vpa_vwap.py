#!/usr/bin/env python3
"""Continuous feedback loop for v31 VPA+VWAP research stack.

Protocol (RESEARCH.md):
  autopsy lessons → ablations → pure OOS folds → promote only if beats baseline
  Never elect from full-window alone. WR reported; 80% WR needs n>=40 to claim.

Usage:
  .venv/bin/python tools/feedback_loop_vpa_vwap.py
  .venv/bin/python tools/feedback_loop_vpa_vwap.py --loop2   # DNA only, reuse Loop1
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from backtest.runner import main as bt_main

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "poc_va_v31_feedback"
STATE = OUT / "LOOP_STATE.json"
ENG_DIR = ROOT / "models" / "poc_va_macdha" / "v31_vpa_vwap"
DNA_FILE = ENG_DIR / "vwap_dna.json"

CODES = [
    "TSLA.US",
    "MSTR.US",
    "NVDA.US",
    "AMD.US",
    "META.US",
    "HOOD.US",
    "IONQ.US",
    "MU.US",
    "AVGO.US",
    "AAPL.US",
]

FOLDS = [
    ("holdout_late", "2025-07-01", "2026-07-11"),
    ("holdout_post_discovery", "2025-01-01", "2026-07-11"),
    ("wf_fold1", "2025-01-01", "2025-06-30"),
    ("wf_fold2", "2025-07-01", "2025-12-31"),
    ("wf_fold3", "2026-01-01", "2026-07-11"),
]

# Ablations from research (one change class each)
EXPERIMENTS = [
    {
        "id": "baseline_vpa_only",
        "hc": {
            "risk_pct": 0.50,
            "dte_days": 7,
            "max_hold_days": 5,
            "max_open_positions": 3,
            "vpa_mode": "standard",
            "require_peg": False,
            "peg_size_mult": 1.0,  # ignore peg
            "vol_z_boost": 1.0,
            "vol_z_thresh": 99,
            "initial_cash": 1_000_000,
            "contract_multiplier": 100,
            "max_contracts": 500,
            "quick_target_pct": 0.03,
            "cut_pct": 0.05,
            "otm_pct": 0.0,
            "codes": [],
        },
        "lesson": "VPA only control",
    },
    {
        "id": "v31_soft_vwap",
        "hc": {
            "risk_pct": 0.50,
            "dte_days": 7,
            "max_hold_days": 5,
            "max_open_positions": 3,
            "vpa_mode": "standard",
            "require_peg": False,
            "peg_size_mult": 0.5,
            "vol_z_boost": 1.15,
            "vol_z_thresh": 1.0,
            "initial_cash": 1_000_000,
            "contract_multiplier": 100,
            "max_contracts": 500,
            "quick_target_pct": 0.03,
            "cut_pct": 0.05,
            "otm_pct": 0.0,
            "codes": [],
        },
        "lesson": "VPA + soft VWAP size + vol_z boost (research default)",
    },
    {
        "id": "v31_sniper_soft",
        "hc": {
            "risk_pct": 0.50,
            "dte_days": 7,
            "max_hold_days": 3,
            "max_open_positions": 2,
            "vpa_mode": "sniper",
            "require_peg": False,
            "peg_size_mult": 0.5,
            "vol_z_boost": 1.2,
            "vol_z_thresh": 1.0,
            "initial_cash": 1_000_000,
            "contract_multiplier": 100,
            "max_contracts": 500,
            "quick_target_pct": 0.025,
            "cut_pct": 0.04,
            "otm_pct": 0.0,
            "codes": [],
        },
        "lesson": "Textbook VPA sniper + soft peg",
    },
    {
        "id": "v31_hard_peg",
        "hc": {
            "risk_pct": 0.50,
            "dte_days": 7,
            "max_hold_days": 5,
            "max_open_positions": 3,
            "vpa_mode": "standard",
            "require_peg": True,
            "peg_size_mult": 0.5,
            "vol_z_boost": 1.15,
            "vol_z_thresh": 1.0,
            "initial_cash": 1_000_000,
            "contract_multiplier": 100,
            "max_contracts": 500,
            "quick_target_pct": 0.03,
            "cut_pct": 0.05,
            "otm_pct": 0.0,
            "codes": [],
        },
        "lesson": "Hard VWAP gate (likely capacity kill — control)",
    },
]

# Loop 2: symbol-aware VWAP DNA (hard APLD/SPY/IONQ, soft majors, off TSLA/MU)
LOOP2_EXPERIMENTS = [
    {
        "id": "v31_symbol_dna",
        "hc": {
            "risk_pct": 0.50,
            "dte_days": 7,
            "max_hold_days": 5,
            "max_open_positions": 3,
            "vpa_mode": "standard",
            "require_peg": False,
            "use_symbol_dna": True,
            "peg_size_mult": 0.5,
            "vol_z_boost": 1.15,
            "vol_z_thresh": 1.0,
            "initial_cash": 1_000_000,
            "contract_multiplier": 100,
            "max_contracts": 500,
            "quick_target_pct": 0.03,
            "cut_pct": 0.05,
            "otm_pct": 0.0,
            "codes": [],
        },
        "lesson": "Loop2: per-symbol VWAP DNA hard/soft/off from FEATURE_INSIGHTS",
        "copy_dna": True,
    },
]


def score(r: dict) -> float:
    if r.get("n", 0) == 0:
        return -0.5
    return (
        1.0 * r["ret"]
        + 0.15 * r.get("wr", 0)
        + 0.10 * min(r.get("sharpe", 0), 2.0) / 2.0
        - 0.40 * abs(r.get("dd", 0))
    )


def run_one(exp: dict, fold: str, start: str, end: str) -> dict:
    run_dir = OUT / fold / exp["id"]
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "code").mkdir(parents=True)
    cfg = {
        "source": "yfinance",
        "codes": CODES,
        "start_date": start,
        "end_date": end,
        "initial_cash": 1_000_000,
        "commission": 0.001,
        "engine": "options",
        "interval": "1D",
        "options_config": {
            "risk_free_rate": 0.05,
            "contract_multiplier": 100,
            "exercise_style": "american",
        },
        "strategy": {"model_version": exp["id"], "fold": fold},
    }
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    (run_dir / "code" / "hunt_config.json").write_text(json.dumps(exp["hc"], indent=2))
    for name in ("signal_engine.py", "vpa.py", "vwap_peg.py"):
        (run_dir / "code" / name).write_text((ENG_DIR / name).read_text())
    if exp.get("copy_dna") and DNA_FILE.exists():
        (run_dir / "code" / "vwap_dna.json").write_text(DNA_FILE.read_text())
    print(f"  {fold}/{exp['id']} {start}→{end}", flush=True)
    try:
        bt_main(run_dir.resolve())
        row = next(csv.DictReader(open(run_dir / "artifacts" / "metrics.csv")))
        # drop ohlcv to save disk
        for p in (run_dir / "artifacts").glob("ohlcv_*.csv"):
            p.unlink(missing_ok=True)
        return {
            "id": exp["id"],
            "lesson": exp["lesson"],
            "ret": float(row["total_return"]),
            "dd": float(row["max_drawdown"]),
            "sharpe": float(row["sharpe"]),
            "n": int(float(row["trade_count"])),
            "wr": float(row["win_rate"]),
            "final": float(row["final_value"]),
        }
    except Exception as e:  # noqa: BLE001
        print("   FAIL", e)
        return {
            "id": exp["id"],
            "lesson": exp["lesson"],
            "error": str(e),
            "ret": -9,
            "dd": -1,
            "sharpe": 0,
            "n": 0,
            "wr": 0,
        }


def _aggregate(fold_rank: dict, experiments: list) -> list:
    ids = [e["id"] for e in experiments]
    lessons = {e["id"]: e["lesson"] for e in experiments}
    # also include any ids present only in fold_rank (reused Loop1)
    for fold, rows in fold_rank.items():
        for r in rows:
            if r["id"] not in lessons:
                lessons[r["id"]] = r.get("lesson", r["id"])
                if r["id"] not in ids:
                    ids.append(r["id"])
    agg = []
    for mid in ids:
        scores, rets, wrs, ns, wins = [], [], [], [], 0
        for fold, rows in fold_rank.items():
            r = next((x for x in rows if x["id"] == mid), None)
            if not r or "error" in r:
                continue
            scores.append(score(r))
            rets.append(r["ret"])
            wrs.append(r["wr"])
            ns.append(r["n"])
            if rows and rows[0]["id"] == mid:
                wins += 1
        if not scores:
            continue
        mean_wr = mean(wrs)
        agg.append(
            {
                "id": mid,
                "mean_oos_score": mean(scores),
                "mean_oos_ret": mean(rets),
                "mean_oos_wr": mean_wr,
                "mean_oos_n": mean(ns),
                "fold_wins": wins,
                "n_folds": len(scores),
                "pass_80_wr": mean_wr >= 0.80 and mean(ns) >= 8,
                "lesson": lessons.get(mid, mid),
            }
        )
    agg.sort(key=lambda x: x["mean_oos_score"], reverse=True)
    return agg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--loop2",
        action="store_true",
        help="Run symbol-DNA experiment only; merge with prior LOOP_STATE folds",
    )
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    experiments = EXPERIMENTS + LOOP2_EXPERIMENTS if not args.loop2 else LOOP2_EXPERIMENTS

    # Loop2: seed fold_rank from prior Loop1 state
    fold_rank: dict = {}
    if args.loop2 and STATE.exists():
        prev = json.loads(STATE.read_text())
        fold_rank = {k: list(v) for k, v in (prev.get("folds") or {}).items()}
        print(f"Reusing {len(fold_rank)} folds from prior LOOP_STATE", flush=True)

    for fold, start, end in FOLDS:
        print(f"\n======== {fold} ========", flush=True)
        new_rows = [run_one(exp, fold, start, end) for exp in experiments]
        if args.loop2:
            # merge: replace same id, keep others
            existing = {r["id"]: r for r in fold_rank.get(fold, [])}
            for r in new_rows:
                existing[r["id"]] = r
            merged = list(existing.values())
        else:
            merged = new_rows
        ok = [r for r in merged if "error" not in r]
        ok.sort(key=score, reverse=True)
        fold_rank[fold] = ok
        for r in ok:
            print(
                f"  {r['id']:20} ret={r['ret']*100:6.1f}% dd={r['dd']*100:5.1f}% "
                f"wr={r['wr']*100:4.0f}% n={r['n']:3d} score={score(r):.3f}"
            )

    all_exps = EXPERIMENTS + LOOP2_EXPERIMENTS
    agg = _aggregate(fold_rank, all_exps)
    champ = agg[0] if agg else None

    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "loop": 2 if args.loop2 else 1,
        "research": "models/poc_va_macdha/v31_vpa_vwap/RESEARCH.md",
        "promotion_rule": "mean pure OOS score; full-window not used; 80% WR claim needs mean_wr>=0.8 and adequate n",
        "failure_lessons": [
            "Hard multi-AND VPA+VWAP kills capacity (v17 lesson)",
            "Pure VPA flips ~39-50% WR — not 80% live bar",
            "Soft VWAP size + vol_z preferred over hard peg",
            "Full-window peaks ≠ OOS champions",
            "$1k→$1M/month is not a backtest KPI (lockup math)",
            "Loop2: symbol DNA (hard/soft/off) — test vs global soft/hard",
        ],
        "folds": fold_rank,
        "aggregate": agg,
        "champion": champ,
        "live_tab_80_wr": bool(champ and champ.get("pass_80_wr")),
        "vwap_dna": str(DNA_FILE.relative_to(ROOT)) if DNA_FILE.exists() else None,
    }
    STATE.write_text(json.dumps(state, indent=2))
    print("\n======== AGGREGATE OOS ========", flush=True)
    for a in agg:
        print(
            f"{a['id']:20} score={a['mean_oos_score']:.3f} ret={a['mean_oos_ret']*100:6.1f}% "
            f"wr={a['mean_oos_wr']*100:4.0f}% n≈{a['mean_oos_n']:.0f} wins={a['fold_wins']}/{a['n_folds']} "
            f"80gate={a['pass_80_wr']}"
        )
    if champ:
        print(f"\nCHAMPION: {champ['id']}  live_tab_80_wr={state['live_tab_80_wr']}")
    print(f"State → {STATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
