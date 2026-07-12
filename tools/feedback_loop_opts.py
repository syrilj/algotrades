#!/usr/bin/env python3
"""Continuous feedback loop: failures → hypotheses → backtests → keep winners.

Learns from option trade PnL + econ/calendar narrative (tools/econ_narrative.py).

Generation 2 lessons (from v27 autopsy):
  - Broad narrative size-down cut winners; only FOMC∧VIX elevated matched the MU blowup.
  - Second MU loss was RISK_ON_QUIET → ticker loss cooloff, not macro.

Usage:
  .venv/bin/python tools/feedback_loop_opts.py
  .venv/bin/python tools/feedback_loop_opts.py --only baseline_v27_conf,v28_surgical_fomc_vix
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from backtest.runner import main as bt_main

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "poc_va_feedback_loop"
STATE = RUNS / "LOOP_STATE.json"
AUTOPSY = RUNS / "FAILURE_AUTOPSY.md"
ENG_V28 = ROOT / "models" / "poc_va_macdha" / "v28_feedback_opts" / "signal_engine.py"
ENG_V22 = ROOT / "models" / "poc_va_macdha" / "v22_opts_live" / "signal_engine.py"
ENG_V27 = ROOT / "models" / "poc_va_macdha" / "v27_lse_opts" / "signal_engine.py"

BASE_CODES = ["IONQ.US", "AVGO.US", "HOOD.US", "MU.US"]
WINDOW = ("2024-08-01", "2026-07-11")

COMMON = {
    "dte_days": 14,
    "otm_pct": 0.0,
    "halt_dd": 0.28,
    "flatten_dd": 0.42,
    "use_conf_tier": True,
    "initial_cash": 1_000_000,
    "contract_multiplier": 100,
    "max_contracts": 500,
}

# Hypotheses spawned from failure autopsy + prior loops
EXPERIMENTS = [
    {
        "id": "baseline_v27_conf",
        "engine": "v27",
        "hc": {
            **COMMON,
            "risk_pct": 0.10,
            "use_vol_scale": False,
            "use_dd_scale": False,
        },
        "failure_addressed": "baseline (LSE conf-tier only)",
    },
    {
        "id": "v28_surgical_fomc_vix",
        "engine": "v28",
        "hc": {
            **COMMON,
            "risk_pct": 0.10,
            "use_narrative": True,
            "narrative_mode": "surgical",
            "loss_cooloff_days": 0,
        },
        "failure_addressed": "block only FOMC day AND elevated VIX (Dec-18 MU)",
    },
    {
        "id": "v28_fomc_day_only",
        "engine": "v28",
        "hc": {
            **COMMON,
            "risk_pct": 0.10,
            "use_narrative": True,
            "narrative_mode": "fomc_day",
            "loss_cooloff_days": 0,
        },
        "failure_addressed": "skip all FOMC decision days",
    },
    {
        "id": "v28_event_vix_calendar",
        "engine": "v28",
        "hc": {
            **COMMON,
            "risk_pct": 0.10,
            "use_narrative": True,
            "narrative_mode": "event_vix",
            "loss_cooloff_days": 0,
        },
        "failure_addressed": "FOMC/CPI/NFP day + elevated VIX skip",
    },
    {
        "id": "v28_surgical_plus_cooloff",
        "engine": "v28",
        "hc": {
            **COMMON,
            "risk_pct": 0.10,
            "use_narrative": True,
            "narrative_mode": "surgical",
            "loss_cooloff_days": 10,
        },
        "failure_addressed": "surgical FOMC∧VIX + 10d cooloff after ticker loss (Nov-25 MU)",
    },
    {
        "id": "v28_broad_narrative",
        "engine": "v28",
        "hc": {
            **COMMON,
            "risk_pct": 0.10,
            "use_narrative": True,
            "narrative_mode": "broad",
            "loss_cooloff_days": 0,
        },
        "failure_addressed": "control: broad size-down (known to cut winners)",
    },
    {
        "id": "v26_plain_14dte",
        "engine": "v22",
        "hc": {
            "risk_pct": 0.10,
            "dte_days": 14,
            "otm_pct": 0.0,
            "halt_dd": 0.30,
            "flatten_dd": 0.45,
            "initial_cash": 1_000_000,
            "contract_multiplier": 100,
            "max_contracts": 500,
        },
        "failure_addressed": "structure baseline without LSE conf",
    },
]


def _engine_text(kind: str) -> str:
    if kind == "v28":
        return ENG_V28.read_text()
    if kind == "v27":
        return ENG_V27.read_text()
    return ENG_V22.read_text()


def run_one(exp: dict) -> dict:
    run_dir = RUNS / exp["id"]
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "code").mkdir(parents=True)
    cfg = {
        "source": "yfinance",
        "codes": BASE_CODES,
        "start_date": WINDOW[0],
        "end_date": WINDOW[1],
        "initial_cash": 1_000_000,
        "commission": 0.001,
        "engine": "options",
        "interval": "1D",
        "options_config": {
            "risk_free_rate": 0.05,
            "contract_multiplier": 100,
            "exercise_style": "american",
        },
        "strategy": {
            "model_version": exp["id"],
            "failure_addressed": exp["failure_addressed"],
        },
    }
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    (run_dir / "code" / "hunt_config.json").write_text(json.dumps(exp["hc"], indent=2))
    (run_dir / "code" / "signal_engine.py").write_text(_engine_text(exp["engine"]))
    print(f"==> testing {exp['id']} ({exp['failure_addressed']})", flush=True)
    bt_main(run_dir.resolve())
    row = next(csv.DictReader(open(run_dir / "artifacts" / "metrics.csv")))
    return {
        "id": exp["id"],
        "failure_addressed": exp["failure_addressed"],
        "ret": float(row["total_return"]),
        "dd": float(row["max_drawdown"]),
        "sharpe": float(row["sharpe"]),
        "n": int(float(row["trade_count"])),
        "wr": float(row["win_rate"]),
        "final": float(row["final_value"]),
        "run": str(run_dir),
    }


def score(r: dict) -> float:
    """Composite: reward return + WR, penalize DD (feedback objective)."""
    return (
        1.0 * r["ret"]
        + 0.15 * r["wr"]
        + 0.10 * min(r["sharpe"], 2.0) / 2.0
        - 0.40 * abs(r["dd"])
    )


def write_autopsy(baseline_run: Path) -> None:
    """Join baseline trades to narrative; write FAILURE_AUTOPSY.md for the loop."""
    trades_p = baseline_run / "artifacts" / "trades.csv"
    if not trades_p.exists():
        return
    sys.path.insert(0, str(ROOT / "tools"))
    from econ_narrative import MacroNarrative  # noqa: WPS433

    import pandas as pd

    trades = pd.read_csv(trades_p)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"])
    buys = trades[trades.side == "buy"].copy()
    exits = trades[trades.side.isin(["close", "exercise"])].copy()
    m = MacroNarrative("2024-01-01", "2026-08-01")
    lines = [
        "# Failure autopsy (baseline trades × econ/calendar narrative)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| code | entry | exit | pnl | narrative | vix_elev | fomc | size_surgical |",
        "|------|-------|------|-----|-----------|----------|------|---------------|",
    ]
    losses = []
    for _, b in buys.iterrows():
        code = b["code"]
        entry = b["timestamp"]
        cand = exits[
            (exits.code == code)
            & (pd.to_datetime(exits.entry_date) == pd.Timestamp(entry).normalize())
        ]
        if len(cand) == 0:
            cand = exits[
                (exits.code == code) & (exits.strike == b.strike) & (exits.timestamp >= entry)
            ].head(1)
        pnl = float(cand.iloc[0]["pnl"]) if len(cand) else float("nan")
        exit_ts = cand.iloc[0]["timestamp"] if len(cand) else None
        feat = m.features_on(entry, mode="surgical")
        feat_b = m.features_on(entry, mode="broad")
        lines.append(
            f"| {code} | {str(pd.Timestamp(entry).date())} | "
            f"{str(pd.Timestamp(exit_ts).date()) if exit_ts is not None else '-'} | "
            f"{pnl:,.0f} | {feat['narrative']} | {feat['vix_elevated']} | "
            f"{feat['days_to_fomc']} | {feat['size_mult']:.2f} |"
        )
        if pnl < 0:
            losses.append(
                {
                    "code": code,
                    "entry": str(pd.Timestamp(entry).date()),
                    "pnl": pnl,
                    "narrative": feat["narrative"],
                    "surgical_blocks": not feat["allow_entry"],
                    "broad_size": feat_b["size_mult"],
                }
            )
    lines += ["", "## Loss lessons", ""]
    for L in losses:
        lines.append(
            f"- **{L['code']} {L['entry']}** pnl={L['pnl']:,.0f} narrative=`{L['narrative']}` "
            f"surgical_blocks={L['surgical_blocks']} broad_size={L['broad_size']}"
        )
    lines += [
        "",
        "## Policy takeaway",
        "",
        "- Surgical block only when `fomc_day AND vix_elevated` (matches Dec-18 MU).",
        "- Broad size-down on FEAR/near-FOMC cuts winners; do not use as full-window gate.",
        "- RISK_ON_QUIET losses need cooloff/ticker rules, not macro narrative.",
        "",
    ]
    AUTOPSY.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default="", help="comma experiment ids")
    args = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    exps = EXPERIMENTS
    if args.only:
        want = set(args.only.split(","))
        exps = [e for e in EXPERIMENTS if e["id"] in want]

    results = []
    for exp in exps:
        try:
            results.append(run_one(exp))
        except Exception as e:  # noqa: BLE001
            results.append(
                {
                    "id": exp["id"],
                    "error": str(e),
                    "ret": -9,
                    "dd": -1,
                    "sharpe": 0,
                    "n": 0,
                    "wr": 0,
                    "failure_addressed": exp.get("failure_addressed", ""),
                }
            )
            print("FAIL", exp["id"], e, flush=True)

    ok = [r for r in results if "error" not in r]
    ok.sort(key=score, reverse=True)
    baseline = next((r for r in ok if r["id"] == "baseline_v27_conf"), ok[-1] if ok else None)
    winner = ok[0] if ok else None

    # Autopsy from baseline if present
    if baseline and Path(baseline["run"]).exists():
        try:
            write_autopsy(Path(baseline["run"]))
        except Exception as e:  # noqa: BLE001
            print("autopsy write failed:", e, flush=True)

    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "generation": 2,
        "window": list(WINDOW),
        "objective": "score = ret + 0.15*wr + 0.1*sharpe_n - 0.4*|dd|",
        "failure_lessons": [
            "MU −71k on 2024-12-18: FOMC day + elevated VIX + rates spike (surgical block)",
            "MU −60k on 2024-11-25: RISK_ON_QUIET — not macro; cooloff candidate",
            "Broad FEAR/near-FOMC size-down cut winners (AVGO near FOMC, MU under FEAR_VOL)",
            "Extra entry AND-filters previously destroyed options capacity",
            "Calendar narrative (FOMC/CPI/NFP) is useful live; full-window gates must be surgical",
        ],
        "ranking": ok,
        "winner": winner,
        "baseline": baseline,
        "beats_baseline": bool(
            winner and baseline and winner["id"] != baseline["id"] and score(winner) > score(baseline)
        ),
        "autopsy": str(AUTOPSY) if AUTOPSY.exists() else None,
    }
    STATE.write_text(json.dumps(state, indent=2))
    print("\n======== FEEDBACK LOOP RANKING (gen 2) ========")
    for r in ok:
        print(
            f"{r['id']:32} ret={r['ret']*100:6.1f}% dd={r['dd']*100:5.1f}% "
            f"sh={r['sharpe']:.2f} n={r['n']} wr={r['wr']*100:.0f}% score={score(r):.3f} "
            f"| {r['failure_addressed']}"
        )
    if winner:
        print(f"\nWINNER: {winner['id']}  beats_baseline={state['beats_baseline']}")
        if baseline and winner["id"] != baseline["id"]:
            dret = (winner["ret"] - baseline["ret"]) * 100
            print(f"  vs baseline: Δret={dret:+.1f}pp  Δdd={(winner['dd']-baseline['dd'])*100:+.1f}pp")
    print(f"State → {STATE}")
    if AUTOPSY.exists():
        print(f"Autopsy → {AUTOPSY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
