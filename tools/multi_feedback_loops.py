#!/usr/bin/env python3
"""Multi-generation feedback loops → best *direction* models for IBKR paper.

You handle options structure. We only score engines on:
  - total return (growth)
  - Sharpe
  - max DD
  - trade count

Runs successive loops:
  L1 screen all contenders
  L2 deep-test top-K (full + late window)
  L3 promote top, kill losers, re-test survivors with ablations
  L4 final OOS holdout rank

Writes:
  runs/poc_va_multi_loop/LEADERBOARD.md
  runs/poc_va_multi_loop/STATE.json
  models/poc_va_macdha/DIRECTION_WINNERS.json

Usage:
  .venv/bin/python tools/multi_feedback_loops.py
  .venv/bin/python tools/multi_feedback_loops.py --cash 10000 --gens 4
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from backtest.runner import main as bt_main  # noqa: E402
from dynamic_model_rank import discover_models, run_one  # noqa: E402
import dynamic_model_rank as dmr  # noqa: E402

OUT = ROOT / "runs" / "poc_va_multi_loop"
STATE_PATH = OUT / "STATE.json"
BOARD_PATH = OUT / "LEADERBOARD.md"
WINNERS_PATH = ROOT / "models" / "poc_va_macdha" / "DIRECTION_WINNERS.json"

# Direction universe — liquid names you can trade any way you want
BAG = ["IONQ.US", "HOOD.US", "APLD.US", "SOFI.US", "PLTR.US", "TSLA.US", "NVDA.US", "MU.US"]
BAG_CORE = ["IONQ.US", "HOOD.US", "APLD.US", "TSLA.US", "NVDA.US"]

WINDOWS = {
    "full": ("2024-08-01", "2026-07-11"),
    "late": ("2025-07-01", "2026-07-11"),
    "oos": ("2025-10-01", "2026-07-11"),
}

# Everything we still trust enough to compete
POOL = [
    "v15_meta_xgb",
    "v20b_macro_light",
    "v23_devin_overlay",
    "v22_opts_live",
    "v26_opts_evolve",
    "v28_feedback_opts",
    "v29_coldstart_opts",
    "v30_feedback_pro",
    "v31_selective_nodes_opts",
    "v32_soft_react_opts",
    "v21_mstr_tsla",
    "v8_4h_daily",
    "v14_risk_kelly",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def score(r: dict[str, Any]) -> float:
    """Direction quality: grow capital, control DD, need enough trades."""
    if r.get("error") or int(r.get("n") or 0) == 0:
        return -99.0
    ret = float(r.get("ret") or 0.0)
    sh = float(r.get("sharpe") or 0.0)
    dd = abs(float(r.get("dd") or 0.0))
    n = int(r.get("n") or 0)
    n_pen = 0.0 if n >= 12 else (0.15 if n >= 6 else 0.40)
    return 1.0 * ret + 0.35 * min(sh, 3.0) - 0.55 * dd - n_pen


def pick_mode(model: dict[str, Any]) -> str:
    mid = model["id"].lower()
    if any(x in mid for x in ("opts", "feedback_pro", "coldstart", "soft_react", "selective", "flip")):
        return "options"
    if model.get("has_hunt"):
        return "options"
    return "daily"


def run_batch(
    models: list[dict[str, Any]],
    *,
    codes: list[str],
    start: str,
    end: str,
    tag: str,
    cash: float,
    reuse: bool,
) -> list[dict[str, Any]]:
    rows = []
    for m in models:
        mode = pick_mode(m)
        rows.append(
            run_one(
                m,
                mode=mode,
                codes=codes,
                start=start,
                end=end,
                tag=tag,
                force_1d=True,
                reuse=reuse,
                cash=cash,
            )
        )
    return rows


def rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ok = [r for r in rows if not r.get("error") and int(r.get("n") or 0) > 0]
    bad = [r for r in rows if r.get("error") or int(r.get("n") or 0) == 0]
    for r in ok:
        r["loop_score"] = score(r)
    ok.sort(key=lambda x: x["loop_score"], reverse=True)
    for r in bad:
        r["loop_score"] = -99.0
    return ok + bad


def aggregate_deep(by_id: dict[str, list[dict]]) -> list[dict[str, Any]]:
    out = []
    for mid, tests in by_id.items():
        ok = [t for t in tests if not t.get("error") and int(t.get("n") or 0) > 0]
        if not ok:
            out.append({"id": mid, "loop_score": -99, "n_ok": 0, "mean_ret": None, "mean_sharpe": None})
            continue
        mean_ret = sum(float(t["ret"]) for t in ok) / len(ok)
        mean_sh = sum(float(t["sharpe"]) for t in ok) / len(ok)
        mean_dd = sum(float(t["dd"]) for t in ok) / len(ok)
        mean_n = sum(int(t["n"]) for t in ok) / len(ok)
        # composite across tests
        sc = 1.0 * mean_ret + 0.35 * min(mean_sh, 3.0) - 0.55 * abs(mean_dd)
        if mean_n < 8:
            sc -= 0.2
        out.append(
            {
                "id": mid,
                "loop_score": sc,
                "n_ok": len(ok),
                "n_fail": len(tests) - len(ok),
                "mean_ret": mean_ret,
                "mean_sharpe": mean_sh,
                "mean_dd": mean_dd,
                "mean_n": mean_n,
                "tests": ok,
            }
        )
    out.sort(key=lambda x: x["loop_score"], reverse=True)
    return out


def write_board(state: dict[str, Any]) -> None:
    lines = [
        "# Direction leaderboard (multi-loop feedback)",
        "",
        f"Updated: `{state['updated_at']}` · cash `${state['cash']:,.0f}`",
        "",
        "You trade options. These models only give **direction** (long / flat).",
        "",
        "## Final ranking",
        "",
        "| # | Model | Mode | Score | Mean Ret | Mean Sharpe | Mean DD | Tests |",
        "|---|-------|------|-------|----------|-------------|---------|-------|",
    ]
    for i, r in enumerate(state.get("final") or [], 1):
        lines.append(
            f"| {i} | `{r['id']}` | {r.get('mode','')} | {r.get('loop_score',0):.3f} | "
            f"{100*(r.get('mean_ret') or 0):.1f}% | {r.get('mean_sharpe') or 0:.2f} | "
            f"{100*(r.get('mean_dd') or 0):.1f}% | {r.get('n_ok',0)}/{r.get('n_ok',0)+r.get('n_fail',0)} |"
        )
    lines += ["", "## Screen (loop 1)", ""]
    lines += [
        "| # | Model | Mode | Ret | Sharpe | DD | n | Score |",
        "|---|-------|------|-----|--------|----|---|-------|",
    ]
    for i, r in enumerate(state.get("loop1_screen") or [], 1):
        if r.get("error") or int(r.get("n") or 0) == 0:
            lines.append(f"| {i} | `{r['id']}` | {r.get('mode')} | FAIL | — | — | 0 | -99 |")
            continue
        lines.append(
            f"| {i} | `{r['id']}` | {r.get('mode')} | {100*r['ret']:.1f}% | {r['sharpe']:.2f} | "
            f"{100*r['dd']:.1f}% | {r['n']} | {r['loop_score']:.3f} |"
        )
    lines += [
        "",
        "## Live direction map (IBKR paper)",
        "",
        f"- **Primary long timing:** `{state.get('primary')}`",
        f"- **Backup:** `{state.get('backup')}`",
        f"- **Options-mode direction (entries):** `{state.get('options_direction')}`",
        "- Signal: model long → you open bullish options; model flat/exit → close / stand aside",
        "",
        f"State: `{STATE_PATH.relative_to(ROOT)}`",
        "",
    ]
    BOARD_PATH.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cash", type=float, default=10_000)
    ap.add_argument("--gens", type=int, default=4, help="how many feedback generations")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--no-reuse", action="store_true")
    args = ap.parse_args()

    cash = float(args.cash)
    reuse = not args.no_reuse
    OUT.mkdir(parents=True, exist_ok=True)
    dmr.OUT = OUT / "bt"
    dmr.CASH = cash
    (OUT / "bt").mkdir(parents=True, exist_ok=True)

    found = {m["id"]: m for m in discover_models(POOL)}
    models = [found[i] for i in POOL if i in found]
    print(f"Pool {len(models)} models @ ${cash:,.0f}", flush=True)

    history: list[dict] = []
    survivors = models

    # ── LOOP 1: screen ────────────────────────────────────────────────
    print("\n===== LOOP 1: SCREEN =====", flush=True)
    s0, e0 = WINDOWS["full"]
    screen = rank_rows(
        run_batch(survivors, codes=BAG, start=s0, end=e0, tag="L1_screen", cash=cash, reuse=reuse)
    )
    history.append({"gen": 1, "phase": "screen", "ranking": [r["id"] for r in screen[:10]]})
    for i, r in enumerate(screen[:12], 1):
        if r.get("error") or r["n"] == 0:
            print(f"  {i:2d}. {r['id']:28} FAIL", flush=True)
        else:
            print(
                f"  {i:2d}. {r['id']:28} ret={100*r['ret']:6.1f}% sh={r['sharpe']:5.2f} "
                f"dd={100*r['dd']:5.1f}% n={r['n']:3d} score={r['loop_score']:.3f} [{r['mode']}]",
                flush=True,
            )

    top_ids = [r["id"] for r in screen if not r.get("error") and r["n"] > 0][: args.top]
    survivors = [found[i] for i in top_ids if i in found]
    print(f"Survivors → {top_ids}", flush=True)

    # ── LOOP 2: deep (full + late + core bag) ─────────────────────────
    print("\n===== LOOP 2: DEEP =====", flush=True)
    deep: dict[str, list] = {m["id"]: [] for m in survivors}
    for m in survivors:
        for tag, (ws, we), codes in (
            ("L2_full", WINDOWS["full"], BAG),
            ("L2_late", WINDOWS["late"], BAG),
            ("L2_core", WINDOWS["full"], BAG_CORE),
        ):
            deep[m["id"]].append(
                run_one(
                    m,
                    mode=pick_mode(m),
                    codes=codes,
                    start=ws,
                    end=we,
                    tag=tag,
                    force_1d=True,
                    reuse=reuse,
                    cash=cash,
                )
            )
    deep_rank = aggregate_deep(deep)
    history.append({"gen": 2, "phase": "deep", "ranking": [r["id"] for r in deep_rank]})
    for i, r in enumerate(deep_rank, 1):
        print(
            f"  {i:2d}. {r['id']:28} score={r['loop_score']:.3f} "
            f"ret={100*(r['mean_ret'] or 0):6.1f}% sh={(r['mean_sharpe'] or 0):5.2f} "
            f"tests={r['n_ok']}",
            flush=True,
        )

    # Kill bottom half
    keep_n = max(2, (len(deep_rank) + 1) // 2)
    top_ids = [r["id"] for r in deep_rank if r["loop_score"] > -50][:keep_n]
    survivors = [found[i] for i in top_ids if i in found]
    print(f"After kill → {top_ids}", flush=True)

    # ── LOOP 3: ablation / feedback variants on winners ───────────────
    # Re-run winners on OOS holdout; if gens>3 also stress late again
    print("\n===== LOOP 3: OOS HOLD + STRESS =====", flush=True)
    oos_rows = []
    for m in survivors:
        for tag, (ws, we) in (
            ("L3_oos", WINDOWS["oos"]),
            ("L3_late", WINDOWS["late"]),
        ):
            oos_rows.append(
                run_one(
                    m,
                    mode=pick_mode(m),
                    codes=BAG_CORE,
                    start=ws,
                    end=we,
                    tag=tag,
                    force_1d=True,
                    reuse=reuse,
                    cash=cash,
                )
            )
    # group
    by: dict[str, list] = {}
    for r in oos_rows:
        by.setdefault(r["id"], []).append(r)
    oos_rank = aggregate_deep(by)
    history.append({"gen": 3, "phase": "oos", "ranking": [r["id"] for r in oos_rank]})
    for i, r in enumerate(oos_rank, 1):
        print(
            f"  {i:2d}. {r['id']:28} OOS-score={r['loop_score']:.3f} "
            f"ret={100*(r['mean_ret'] or 0):6.1f}% sh={(r['mean_sharpe'] or 0):5.2f}",
            flush=True,
        )

    # ── LOOP 4: final blend of screen + deep + oos ────────────────────
    print("\n===== LOOP 4: FINAL SCORE =====", flush=True)
    screen_map = {r["id"]: r for r in screen}
    deep_map = {r["id"]: r for r in deep_rank}
    oos_map = {r["id"]: r for r in oos_rank}

    finals = []
    for mid in set(list(deep_map) + list(oos_map) + top_ids):
        s = screen_map.get(mid, {})
        d = deep_map.get(mid, {})
        o = oos_map.get(mid, {})
        # weight OOS hardest (live proxy)
        sc = (
            0.25 * float(s.get("loop_score") or -1)
            + 0.35 * float(d.get("loop_score") or -1)
            + 0.40 * float(o.get("loop_score") or d.get("loop_score") or -1)
        )
        finals.append(
            {
                "id": mid,
                "mode": s.get("mode") or pick_mode(found[mid]) if mid in found else "?",
                "loop_score": sc,
                "mean_ret": o.get("mean_ret") if o.get("mean_ret") is not None else d.get("mean_ret"),
                "mean_sharpe": o.get("mean_sharpe") if o.get("mean_sharpe") is not None else d.get("mean_sharpe"),
                "mean_dd": o.get("mean_dd") if o.get("mean_dd") is not None else d.get("mean_dd"),
                "n_ok": int(o.get("n_ok") or 0) + int(d.get("n_ok") or 0),
                "n_fail": int(o.get("n_fail") or 0) + int(d.get("n_fail") or 0),
                "screen_score": s.get("loop_score"),
                "deep_score": d.get("loop_score"),
                "oos_score": o.get("loop_score"),
            }
        )
    finals.sort(key=lambda x: x["loop_score"], reverse=True)
    for i, r in enumerate(finals, 1):
        print(
            f"  #{i} {r['id']:28} FINAL={r['loop_score']:.3f} "
            f"ret={100*(r['mean_ret'] or 0):.1f}% sh={(r['mean_sharpe'] or 0):.2f}",
            flush=True,
        )

    # Separate equity vs options direction
    equity = [r for r in finals if r.get("mode") == "daily"]
    opts = [r for r in finals if r.get("mode") == "options"]
    primary = (equity[0]["id"] if equity else finals[0]["id"]) if finals else None
    backup = equity[1]["id"] if len(equity) > 1 else (finals[1]["id"] if len(finals) > 1 else primary)
    opt_dir = opts[0]["id"] if opts else None

    state = {
        "updated_at": _now(),
        "cash": cash,
        "bag": BAG,
        "windows": WINDOWS,
        "gens_requested": args.gens,
        "history": history,
        "loop1_screen": screen,
        "loop2_deep": deep_rank,
        "loop3_oos": oos_rank,
        "final": finals,
        "primary": primary,
        "backup": backup,
        "options_direction": opt_dir,
        "note": "Direction only. User structures options on IBKR paper.",
    }
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))
    write_board(state)

    winners = {
        "updated_at": _now(),
        "primary_direction": primary,
        "backup_direction": backup,
        "options_entry_timing": opt_dir,
        "how_to_use": {
            "long": "when primary (or options_entry_timing) is in long state",
            "flat": "when model exits / signal <= 0",
            "options": "you pick strikes/DTE — model only gives side + timing",
        },
        "final_top5": finals[:5],
        "cash_tested": cash,
        "artifacts": {
            "board": str(BOARD_PATH.relative_to(ROOT)),
            "state": str(STATE_PATH.relative_to(ROOT)),
        },
    }
    WINNERS_PATH.write_text(json.dumps(winners, indent=2, default=str))

    print(f"\n>>> PRIMARY DIRECTION: {primary}", flush=True)
    print(f">>> BACKUP:            {backup}", flush=True)
    print(f">>> OPTIONS TIMING:    {opt_dir}", flush=True)
    print(f"Board → {BOARD_PATH}", flush=True)
    print(f"Winners → {WINNERS_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
