#!/usr/bin/env python3
"""Honest OOS / walk-forward ranking for top options models.

Splits the full research window so ranking is not only on the same data
that produced failure-driven rules.

Schemes:
  1) Chronological holdout: IS = 2024-08→2025-06-30, OOS = 2025-07→2026-07-11
  2) Discovery holdout:     IS = 2024-08→2024-12-31, OOS = 2025-01→2026-07-11
     (cooloff/HOOD edge was mostly 2025 — this is the hard test)
  3) Walk-forward 3 folds (expanding IS, fixed OOS length ~6m)

Usage:
  .venv/bin/python tools/oos_rank_opts.py
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from backtest.runner import main as bt_main

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "poc_va_oos_rank"
STATE = OUT / "OOS_RANKING.json"
FINDINGS = OUT / "FINDINGS.md"

ENG = {
    "v22": ROOT / "models" / "poc_va_macdha" / "v22_opts_live" / "signal_engine.py",
    "v26": ROOT / "models" / "poc_va_macdha" / "v22_opts_live" / "signal_engine.py",  # same DNA, 14dte via hc
    "v27": ROOT / "models" / "poc_va_macdha" / "v27_lse_opts" / "signal_engine.py",
    "v28": ROOT / "models" / "poc_va_macdha" / "v28_feedback_opts" / "signal_engine.py",
}

BASE_CODES = ["IONQ.US", "AVGO.US", "HOOD.US", "MU.US"]
CASH = 1_000_000

COMMON = {
    "dte_days": 14,
    "otm_pct": 0.0,
    "halt_dd": 0.28,
    "flatten_dd": 0.42,
    "initial_cash": CASH,
    "contract_multiplier": 100,
    "max_contracts": 500,
    "risk_pct": 0.10,
}

# Contenders from full-window feedback ranking + structure baseline
MODELS = [
    {
        "id": "v28_surgical_cooloff",
        "engine": "v28",
        "hc": {
            **COMMON,
            "use_conf_tier": True,
            "use_narrative": True,
            "narrative_mode": "surgical",
            "loss_cooloff_days": 10,
        },
        "label": "full-window feedback winner",
    },
    {
        "id": "v27_conf",
        "engine": "v27",
        "hc": {
            **COMMON,
            "use_vol_scale": False,
            "use_conf_tier": True,
            "use_dd_scale": False,
        },
        "label": "prior champ LSE conf-tier",
    },
    {
        "id": "v28_surgical_only",
        "engine": "v28",
        "hc": {
            **COMMON,
            "use_conf_tier": True,
            "use_narrative": True,
            "narrative_mode": "surgical",
            "loss_cooloff_days": 0,
        },
        "label": "FOMC∧VIX only (no cooloff)",
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
        "label": "v22 DNA 14 DTE plain",
    },
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
        "label": "original v22 live defaults",
    },
]

# Validation windows (start, end) — OOS only is what we rank on for promotion
FOLDS = [
    {
        "name": "holdout_late",
        "desc": "IS through mid-2025; OOS last ~12m (capacity/regime shift test)",
        "is": ("2024-08-01", "2025-06-30"),
        "oos": ("2025-07-01", "2026-07-11"),
    },
    {
        "name": "holdout_post_discovery",
        "desc": "Hard OOS: all 2025–2026 (cooloff HOOD edge lives here — honesty check)",
        "is": ("2024-08-01", "2024-12-31"),
        "oos": ("2025-01-01", "2026-07-11"),
    },
    {
        "name": "wf_fold1",
        "desc": "WF expanding: IS→2024-12, OOS 2025-H1",
        "is": ("2024-08-01", "2024-12-31"),
        "oos": ("2025-01-01", "2025-06-30"),
    },
    {
        "name": "wf_fold2",
        "desc": "WF expanding: IS→2025-06, OOS 2025-H2",
        "is": ("2024-08-01", "2025-06-30"),
        "oos": ("2025-07-01", "2025-12-31"),
    },
    {
        "name": "wf_fold3",
        "desc": "WF expanding: IS→2025-12, OOS 2026-H1",
        "is": ("2024-08-01", "2025-12-31"),
        "oos": ("2026-01-01", "2026-07-11"),
    },
    {
        "name": "full_window",
        "desc": "Reference only (NOT pure OOS) — same as feedback loop",
        "is": ("2024-08-01", "2026-07-11"),
        "oos": ("2024-08-01", "2026-07-11"),
        "reference_only": True,
    },
]


def score(r: dict) -> float:
    if r.get("error") or r.get("n", 0) == 0 and r.get("ret", 0) == 0:
        # empty book: neutral-low score (no trades is not a win)
        if r.get("n", 0) == 0:
            return -0.5 + 0.01 * r.get("ret", 0)
    return (
        1.0 * r["ret"]
        + 0.15 * r.get("wr", 0)
        + 0.10 * min(r.get("sharpe", 0), 2.0) / 2.0
        - 0.40 * abs(r.get("dd", 0))
    )


def run_one(model: dict, start: str, end: str, tag: str) -> dict:
    run_dir = OUT / tag / model["id"]
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "code").mkdir(parents=True)
    cfg = {
        "source": "yfinance",
        "codes": BASE_CODES,
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
        "strategy": {"model_version": model["id"], "window": f"{start}_{end}"},
    }
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    (run_dir / "code" / "hunt_config.json").write_text(json.dumps(model["hc"], indent=2))
    (run_dir / "code" / "signal_engine.py").write_text(ENG[model["engine"]].read_text())
    print(f"  → {model['id']}  {start}→{end}", flush=True)
    try:
        bt_main(run_dir.resolve())
        row = next(csv.DictReader(open(run_dir / "artifacts" / "metrics.csv")))
        return {
            "id": model["id"],
            "label": model["label"],
            "start": start,
            "end": end,
            "ret": float(row["total_return"]),
            "dd": float(row["max_drawdown"]),
            "sharpe": float(row["sharpe"]),
            "n": int(float(row["trade_count"])),
            "wr": float(row["win_rate"]),
            "final": float(row["final_value"]),
            "run": str(run_dir),
        }
    except Exception as e:  # noqa: BLE001
        print("    FAIL", e, flush=True)
        return {
            "id": model["id"],
            "label": model["label"],
            "start": start,
            "end": end,
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
    fold_results = {}

    for fold in FOLDS:
        print(f"\n======== FOLD {fold['name']}: OOS {fold['oos'][0]} → {fold['oos'][1]} ========", flush=True)
        print(f"  {fold['desc']}", flush=True)
        rows = []
        for model in MODELS:
            rows.append(run_one(model, fold["oos"][0], fold["oos"][1], f"{fold['name']}_oos"))
        # IS not re-run here — promotion uses pure OOS only (keeps loop fast).
        ok = [r for r in rows if "error" not in r]
        ok.sort(key=score, reverse=True)
        fold_results[fold["name"]] = {
            "desc": fold["desc"],
            "is_window": list(fold["is"]),
            "oos_window": list(fold["oos"]),
            "reference_only": bool(fold.get("reference_only")),
            "oos_ranking": ok,
            "oos_winner": ok[0] if ok else None,
        }
        print("  OOS rank:", flush=True)
        for r in ok:
            print(
                f"    {r['id']:28} ret={r['ret']*100:7.1f}% dd={r['dd']*100:6.1f}% "
                f"sh={r['sharpe']:5.2f} n={r['n']:3d} wr={r['wr']*100:4.0f}% score={score(r):.3f}",
                flush=True,
            )

    # Aggregate pure-OOS folds (exclude full_window reference)
    pure = [n for n, f in fold_results.items() if not f.get("reference_only")]
    model_ids = [m["id"] for m in MODELS]
    aggregate = []
    for mid in model_ids:
        oos_scores = []
        oos_rets = []
        oos_dds = []
        oos_ns = []
        wins = 0
        for fname in pure:
            ranking = fold_results[fname]["oos_ranking"]
            row = next((r for r in ranking if r["id"] == mid), None)
            if not row:
                continue
            oos_scores.append(score(row))
            oos_rets.append(row["ret"])
            oos_dds.append(row["dd"])
            oos_ns.append(row["n"])
            if fold_results[fname]["oos_winner"] and fold_results[fname]["oos_winner"]["id"] == mid:
                wins += 1
        if not oos_scores:
            continue
        aggregate.append(
            {
                "id": mid,
                "label": next(m["label"] for m in MODELS if m["id"] == mid),
                "mean_oos_score": sum(oos_scores) / len(oos_scores),
                "mean_oos_ret": sum(oos_rets) / len(oos_rets),
                "mean_oos_dd": sum(oos_dds) / len(oos_dds),
                "mean_oos_n": sum(oos_ns) / len(oos_ns),
                "fold_wins": wins,
                "n_folds": len(oos_scores),
                "fold_scores": {fname: next(score(r) for r in fold_results[fname]["oos_ranking"] if r["id"] == mid) for fname in pure},
                "fold_rets": {fname: next(r["ret"] for r in fold_results[fname]["oos_ranking"] if r["id"] == mid) for fname in pure},
            }
        )
    aggregate.sort(key=lambda x: (x["fold_wins"], x["mean_oos_score"]), reverse=True)
    champion = aggregate[0] if aggregate else None

    # Full-window reference ranking for completeness
    full = fold_results.get("full_window", {}).get("oos_ranking", [])

    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "score = ret + 0.15*wr + 0.1*sharpe_n - 0.4*|dd|",
        "promotion_rule": (
            "Champion = best mean OOS score across pure OOS folds "
            "(holdout_late, holdout_post_discovery, wf_fold1-3). "
            "full_window is reference only and does NOT elect the default."
        ),
        "codes": BASE_CODES,
        "folds": fold_results,
        "aggregate_oos": aggregate,
        "champion": champion,
        "full_window_reference_winner": full[0] if full else None,
    }
    STATE.write_text(json.dumps(state, indent=2))
    write_findings(state)
    print("\n======== AGGREGATE OOS (promotion) ========", flush=True)
    for a in aggregate:
        print(
            f"{a['id']:28} mean_score={a['mean_oos_score']:.3f} "
            f"mean_ret={a['mean_oos_ret']*100:6.1f}% mean_dd={a['mean_oos_dd']*100:5.1f}% "
            f"fold_wins={a['fold_wins']}/{a['n_folds']}",
            flush=True,
        )
    if champion:
        print(f"\nCHAMPION (OOS): {champion['id']}", flush=True)
    print(f"State → {STATE}", flush=True)
    print(f"Findings → {FINDINGS}", flush=True)
    return 0


def write_findings(state: dict) -> None:
    ch = state.get("champion") or {}
    lines = [
        "# OOS ranking findings — options stack",
        "",
        f"Generated: {state['updated_at']}",
        "",
        "## Promotion rule",
        "",
        state["promotion_rule"],
        "",
        "## Champion (unseen-data aggregate)",
        "",
    ]
    if ch:
        lines += [
            f"- **id:** `{ch['id']}`",
            f"- **label:** {ch['label']}",
            f"- **mean OOS score:** {ch['mean_oos_score']:.3f}",
            f"- **mean OOS return:** {ch['mean_oos_ret']*100:.1f}%",
            f"- **mean OOS DD:** {ch['mean_oos_dd']*100:.1f}%",
            f"- **fold wins:** {ch['fold_wins']}/{ch['n_folds']}",
            "",
            "### Per-fold OOS return",
            "",
        ]
        for k, v in ch.get("fold_rets", {}).items():
            lines.append(f"- `{k}`: {v*100:.1f}%")
    else:
        lines.append("- No champion elected.")

    lines += [
        "",
        "## Aggregate table (all contenders)",
        "",
        "| model | mean OOS score | mean ret | mean DD | fold wins |",
        "|-------|----------------|----------|---------|-----------|",
    ]
    for a in state.get("aggregate_oos", []):
        lines.append(
            f"| {a['id']} | {a['mean_oos_score']:.3f} | {a['mean_oos_ret']*100:.1f}% | "
            f"{a['mean_oos_dd']*100:.1f}% | {a['fold_wins']}/{a['n_folds']} |"
        )

    lines += [
        "",
        "## Issues / errors / rules for future loops",
        "",
        "### Confirmed failure modes (keep as rules)",
        "",
        "1. **FOMC day + elevated VIX** — MU 2024-12-18 (−71k). Surgical block only; do not haircut all FEAR days.",
        "2. **Broad narrative size-down** — cuts winners (AVGO near FOMC, MU under FEAR_VOL). Never promote `narrative_mode=broad`.",
        "3. **Aggressive calendar (CPI/NFP + VIX)** — raised WR but destroyed capacity (few trades, weak return).",
        "4. **Hard entry AND-filters** — historically killed options capacity; size/gates secondary only.",
        "5. **Ticker re-entry after loss** — IONQ Feb 2025 double-tap; 10d cooloff fixed path-dependent blowup.",
        "6. **Full-window ranking ≠ OOS ranking** — always re-rank on holdout before promoting default.",
        "7. **Internal equity mtm is crude** — signal engine sizing equity ≠ true option PnL; can halt/capacity-skew. Future: mark with BS mid.",
        "8. **Small sample** — bag is 4 names; fold with n=0 trades is not a win. Prefer models that trade *and* survive OOS.",
        "9. **Theoretical compound ledgers** ($1k→$2M window artifacts) overstate open capital — report full-window portfolio metrics only.",
        "10. **Equity WINNER.json (v23_devin)** is a different book** — do not confuse equity overlay champ with options stack default.",
        "",
        "### Errors to watch in code",
        "",
        "- AST sandbox: no top-level Path assigns in signal engines.",
        "- Macro download failure must fail-open (allow_entry=True) so live/backtest still runs.",
        "- Cooloff uses engine mtm sign, not realized option PnL — can false-cooloff on path noise.",
        "",
        "### What to try next",
        "",
        "- Mark-to-model premium for cooloff/loss detection.",
        "- Earnings calendar per ticker (MU dumps).",
        "- Dual sleeve: OOS champ growth + v26 high-Sharpe smoother.",
        "- Expand bag only after OOS re-rank (no silent symbol add).",
        "",
    ]
    FINDINGS.write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
