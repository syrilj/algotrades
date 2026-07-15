#!/usr/bin/env python3
"""Beat-champion campaign: freeze v39d_confluence, run 3 sequential bets.

Ladder D:
  - Hunt: full champion window (screen)
  - Promote: lockbox multi-lock on ret + sharpe + dd vs frozen baseline lockbox

Bets (stop at first promote or after 3 fails):
  1. v61_meta_ledger  — secondary logistic on candidate ledger
  2. exit/stop/size grid on frozen v39d (≤7 configs; best hunt → lockbox)
  3. v62_macro_softsize — soft size mult from regime features

Usage:
  .venv/bin/python tools/feedback_loop_beat_champion.py --cash 1000
  .venv/bin/python tools/feedback_loop_beat_champion.py --cash 1000 --baseline-only
  .venv/bin/python tools/feedback_loop_beat_champion.py --cash 1000 --from-bet 2
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dynamic_model_rank as dmr

ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
OUT = ROOT / "runs" / "beat_champion_v1"

EQUITY_WINNER_BAG = [
    "TSLA.US",
    "MU.US",
    "SPY.US",
    "IONQ.US",
    "APLD.US",
    "XLP.US",
    "QQQ.US",
]

HUNT_START = "2024-08-01"
HUNT_END = "2026-07-11"
TRAIN_END = "2025-08-01"  # exclusive end for train / start of lockbox
LOCKBOX_START = "2025-08-01"
LOCKBOX_END = "2026-07-11"

PROMOTION_GATES = {
    "min_n_hunt": 30,
    "min_n_lockbox": 10,
    "min_ret": 0.0,
    "max_abs_dd": 0.25,
    "min_sharpe": 1.0,
    "dd_slack": 0.02,
}

# Pre-registered Bet 2 grid (≤7). Only best hunt config goes to lockbox.
BET2_GRID: list[dict[str, Any]] = [
    {"id": "stop_atr_1_0", "stop_atr": 1.0},
    {"id": "stop_atr_1_2", "stop_atr": 1.2},
    {"id": "stop_atr_0_8", "stop_atr": 0.8},
    {"id": "stop_1_0_trail_2_0", "stop_atr": 1.0, "trail_atr": 2.0},
    {"id": "stop_1_0_trail_1_5", "stop_atr": 1.0, "trail_atr": 1.5},
    {"id": "stop_1_2_trail_2_0", "stop_atr": 1.2, "trail_atr": 2.0},
    {"id": "stop_1_0_arm_0_5", "stop_atr": 1.0, "arm_trail_atr": 0.5},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metric_view(row: dict[str, Any]) -> dict[str, Any]:
    """Slim metrics for STATE / leaderboard."""
    if row.get("error"):
        return {
            "id": row.get("id"),
            "error": row["error"],
            "ret": row.get("ret", -9.0),
            "dd": row.get("dd", -1.0),
            "sharpe": row.get("sharpe", 0.0),
            "n": row.get("n", 0),
            "wr": row.get("wr", 0.0),
            "final": row.get("final_at_cash", row.get("final", 0.0)),
        }
    return {
        "id": row.get("id"),
        "ret": float(row["ret"]),
        "dd": float(row["dd"]),
        "sharpe": float(row["sharpe"]),
        "n": int(row["n"]),
        "wr": float(row["wr"]),
        "final": float(row.get("final_at_cash", row.get("final", 0.0))),
        "reused": bool(row.get("reused", False)),
        "path": row.get("path"),
    }


def passes_promotion_gates(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    *,
    min_n: int | None = None,
    require_hunt_floors: bool = False,
) -> tuple[bool, str]:
    """Multi-lock promote decision. Returns (ok, reason).

    Candidate must beat baseline on ret and sharpe, not be materially worse on
    drawdown, and clear absolute floors.
    """
    min_n = int(min_n if min_n is not None else PROMOTION_GATES["min_n_lockbox"])
    if candidate.get("error"):
        return False, f"candidate_error:{candidate['error']}"
    if baseline.get("error"):
        return False, f"baseline_error:{baseline['error']}"

    n = int(candidate.get("n", 0))
    if n < min_n:
        return False, f"n={n}<{min_n}"

    ret = float(candidate.get("ret", 0.0))
    dd = float(candidate.get("dd", 0.0))
    sharpe = float(candidate.get("sharpe", 0.0))
    wr = float(candidate.get("wr", 0.0))

    if ret < PROMOTION_GATES["min_ret"]:
        return False, f"ret={ret:.4f}<min_ret"
    if abs(dd) > PROMOTION_GATES["max_abs_dd"]:
        return False, f"abs_dd={abs(dd):.4f}>max"
    if sharpe < PROMOTION_GATES["min_sharpe"]:
        return False, f"sharpe={sharpe:.3f}<min_sharpe"

    if require_hunt_floors and n < PROMOTION_GATES["min_n_hunt"]:
        return False, f"hunt_n={n}<{PROMOTION_GATES['min_n_hunt']}"

    b_ret = float(baseline["ret"])
    b_sh = float(baseline["sharpe"])
    b_dd = float(baseline["dd"])

    if not (ret > b_ret):
        return False, f"ret_not_gt_baseline ({ret:.4f}<={b_ret:.4f})"
    if not (sharpe > b_sh):
        return False, f"sharpe_not_gt_baseline ({sharpe:.3f}<={b_sh:.3f})"
    if abs(dd) > abs(b_dd) + PROMOTION_GATES["dd_slack"]:
        return False, (
            f"dd_worse (abs_dd={abs(dd):.4f} > baseline {abs(b_dd):.4f}"
            f"+{PROMOTION_GATES['dd_slack']})"
        )
    return True, "multi_lock_ok"


def _fmt(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"{row.get('id', '?'):40} FAIL {str(row['error'])[:80]}"
    return (
        f"{row.get('id', '?'):40} ret={float(row['ret'])*100:7.1f}% "
        f"dd={abs(float(row['dd']))*100:6.1f}% "
        f"sharpe={float(row['sharpe']):5.2f} "
        f"n={int(row['n']):3d} wr={float(row['wr'])*100:4.0f}% "
        f"final=${float(row.get('final_at_cash', row.get('final', 0))):>10,.2f}"
    )


def _run(
    model: dict[str, Any],
    *,
    start: str,
    end: str,
    tag: str,
    cash: float,
    extra_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return dmr.run_one(
        model,
        mode="daily",
        codes=EQUITY_WINNER_BAG,
        start=start,
        end=end,
        tag=tag,
        force_1d=False,
        reuse=True,
        cash=cash,
        source="local",
        interval="1H",
        extra_cfg=extra_cfg,
    )


def _discover(name: str) -> dict[str, Any]:
    models = dmr.discover_models(only=[name])
    if not models:
        raise FileNotFoundError(f"model not found: {name}")
    return models[0]


def _patch_routing_stops(
    src_dir: Path,
    dst_dir: Path,
    *,
    stop_atr: float | None = None,
    trail_atr: float | None = None,
    arm_trail_atr: float | None = None,
) -> None:
    """Copy v39d engine and patch per-symbol routing stop/trail knobs."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "signal_engine.py",
        "meta_config.json",
        "meta_xgb_final.json",
        "candidate_ledger.py",
        "config.json",
    ):
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, dst_dir / name)
    # Prefer shared ledger if model-local missing
    if not (dst_dir / "candidate_ledger.py").exists():
        shared = MODELS_ROOT / "_shared" / "candidate_ledger.py"
        if shared.exists():
            shutil.copy2(shared, dst_dir / "candidate_ledger.py")

    eng = (dst_dir / "signal_engine.py").read_text(encoding="utf-8")
    # Prefer the single assignment line starting with _ROUTING (v39d style).
    lines = eng.splitlines(keepends=True)
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("_ROUTING")), None)
    if idx is None:
        raise RuntimeError("could not find _ROUTING in signal_engine.py")
    line = lines[idx]
    eq = line.find("=")
    if eq < 0:
        raise RuntimeError("_ROUTING assignment missing '='")
    literal = line[eq + 1 :].strip()
    # Controlled model source only (not user input).
    routing = eval(literal, {"__builtins__": {}})  # noqa: S307
    if not isinstance(routing, dict):
        raise RuntimeError("_ROUTING is not a dict")
    for _sym, cfg in routing.items():
        if not isinstance(cfg, dict):
            continue
        if stop_atr is not None:
            cfg["stop_atr"] = float(stop_atr)
        if trail_atr is not None:
            cfg["trail_atr"] = float(trail_atr)
        if arm_trail_atr is not None:
            cfg["arm_trail_atr"] = float(arm_trail_atr)
    # Preserve original newline
    nl = "\n" if line.endswith("\n") else ""
    lines[idx] = "_ROUTING = " + repr(routing) + nl
    (dst_dir / "signal_engine.py").write_text("".join(lines), encoding="utf-8")


def _make_bet2_model(parent: Path, variant: dict[str, Any]) -> dict[str, Any]:
    vid = str(variant["id"])
    (OUT / "variants").mkdir(parents=True, exist_ok=True)
    tmp = OUT / "variants" / f"v39d_{vid}"
    if tmp.exists():
        shutil.rmtree(tmp)
    _patch_routing_stops(
        parent,
        tmp,
        stop_atr=variant.get("stop_atr"),
        trail_atr=variant.get("trail_atr"),
        arm_trail_atr=variant.get("arm_trail_atr"),
    )
    # Fake discover-shaped model dict
    return {
        "id": f"v39d_{vid}",
        "src_dir": tmp,
        "model_dir": tmp,
        "interval": "1H",
        "has_hunt": False,
    }


def _write_leaderboard(state: dict[str, Any], cash: float) -> None:
    lines = [
        "# Beat champion campaign leaderboard\n",
        f"- cash: ${cash:,.0f}\n",
        f"- hunt: {HUNT_START} → {HUNT_END}\n",
        f"- lockbox: {LOCKBOX_START} → {LOCKBOX_END}\n",
        f"- source: local 1H | bag: EQUITY_WINNER_BAG\n",
        f"- promoted_best: {state.get('promoted_best')}\n",
        f"- plateau: {state.get('plateau')}\n",
        "",
        "## Baseline (v39d_confluence)\n",
    ]
    b = state.get("baseline") or {}
    for phase in ("hunt", "lockbox"):
        row = b.get(phase) or {}
        if row.get("error"):
            lines.append(f"- {phase}: FAIL {row['error']}\n")
        else:
            lines.append(
                f"- {phase}: ret={float(row.get('ret',0))*100:.1f}% "
                f"dd={abs(float(row.get('dd',0)))*100:.1f}% "
                f"sharpe={float(row.get('sharpe',0)):.2f} "
                f"n={int(row.get('n',0))} wr={float(row.get('wr',0))*100:.0f}%\n"
            )
    lines.append("\n## Bets\n")
    lines.append("| bet | status | phase | ret | dd | sharpe | n | wr | reason |\n")
    lines.append("|-----|--------|-------|-----|----|--------|---|----|--------|\n")
    for bet in state.get("bets") or []:
        for phase in ("hunt", "lockbox"):
            row = bet.get(phase) or {}
            if not row:
                continue
            lines.append(
                f"| {bet.get('id')} | {bet.get('status')} | {phase} | "
                f"{float(row.get('ret',0))*100:.1f}% | "
                f"{abs(float(row.get('dd',0)))*100:.1f}% | "
                f"{float(row.get('sharpe',0)):.2f} | "
                f"{int(row.get('n',0))} | "
                f"{float(row.get('wr',0))*100:.0f}% | "
                f"{bet.get('reason','')} |\n"
            )
        if bet.get("status") in {"fail", "promote"} and not bet.get("lockbox"):
            lines.append(
                f"| {bet.get('id')} | {bet.get('status')} | — |  |  |  |  |  | {bet.get('reason','')} |\n"
            )

    if state.get("plateau"):
        lines.extend(
            [
                "\n## Plateau\n",
                "All three pre-registered bets failed lockbox multi-lock against frozen "
                "`v39d_confluence`. Do not promote hunt-only winners. Residual plateau is "
                "treated as a valid research result under OHLCV + 2y bag for this attack surface.\n",
            ]
        )
    if state.get("promoted_best"):
        lines.extend(
            [
                "\n## Promote\n",
                f"**{state['promoted_best']}** multi-locked on lockbox. "
                "Human confirm before updating AGENTS.md champion.\n",
            ]
        )

    (OUT / "LEADERBOARD.md").write_text("".join(lines), encoding="utf-8")


def _save_state(state: dict[str, Any], cash: float) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "STATE.json").write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    _write_leaderboard(state, cash)


def run_baseline(cash: float) -> dict[str, Any]:
    print("[beat-champ] freeze baseline v39d_confluence", flush=True)
    m = _discover("v39d_confluence")
    # Keep id stable for readability
    hunt = _run(m, start=HUNT_START, end=HUNT_END, tag="bc_base_hunt", cash=cash)
    print(f"  hunt    {_fmt(hunt)}", flush=True)
    lock = _run(m, start=LOCKBOX_START, end=LOCKBOX_END, tag="bc_base_lock", cash=cash)
    print(f"  lockbox {_fmt(lock)}", flush=True)
    return {"hunt": _metric_view(hunt), "lockbox": _metric_view(lock)}


def run_bet1(cash: float, baseline_lock: dict[str, Any]) -> dict[str, Any]:
    """Bet 1: train secondary meta on train-window ledger, evaluate v61."""
    print("[beat-champ] Bet 1: meta ledger (v61_meta_ledger)", flush=True)
    train_script = ROOT / "tools" / "train_v61_meta_ledger.py"
    model_dir = MODELS_ROOT / "v61_meta_ledger"
    if not model_dir.exists() or not (model_dir / "signal_engine.py").exists():
        return {
            "id": "bet1_meta_ledger",
            "status": "fail",
            "reason": "v61_meta_ledger not scaffolded",
            "hunt": {},
            "lockbox": {},
        }

    # Train (fits on train window only)
    import subprocess

    cmd = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(train_script),
        "--cash",
        str(cash),
        "--train-start",
        HUNT_START,
        "--train-end",
        TRAIN_END,
    ]
    print(f"  train: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "train failed")[-400:]
        print(f"  train FAIL: {err}", flush=True)
        return {
            "id": "bet1_meta_ledger",
            "status": "fail",
            "reason": f"train_failed:{err[:200]}",
            "hunt": {},
            "lockbox": {},
        }
    print(proc.stdout[-800:] if proc.stdout else "  train ok", flush=True)

    try:
        m = _discover("v61_meta_ledger")
    except FileNotFoundError as e:
        return {
            "id": "bet1_meta_ledger",
            "status": "fail",
            "reason": str(e),
            "hunt": {},
            "lockbox": {},
        }

    hunt = _run(m, start=HUNT_START, end=HUNT_END, tag="bc_bet1_hunt", cash=cash)
    print(f"  hunt    {_fmt(hunt)}", flush=True)
    lock = _run(m, start=LOCKBOX_START, end=LOCKBOX_END, tag="bc_bet1_lock", cash=cash)
    print(f"  lockbox {_fmt(lock)}", flush=True)

    ok, reason = passes_promotion_gates(lock, baseline_lock, min_n=PROMOTION_GATES["min_n_lockbox"])
    # Also require hunt floor n
    if ok and int(hunt.get("n", 0)) < PROMOTION_GATES["min_n_hunt"]:
        ok, reason = False, f"hunt_n={hunt.get('n')}<{PROMOTION_GATES['min_n_hunt']}"
    return {
        "id": "bet1_meta_ledger",
        "status": "promote" if ok else "fail",
        "reason": reason,
        "hunt": _metric_view(hunt),
        "lockbox": _metric_view(lock),
    }


def run_bet2(cash: float, baseline_lock: dict[str, Any]) -> dict[str, Any]:
    print("[beat-champ] Bet 2: exit/stop grid on v39d", flush=True)
    parent = MODELS_ROOT / "v39d_confluence"
    (OUT / "variants").mkdir(parents=True, exist_ok=True)

    hunt_rows: list[dict[str, Any]] = []
    for variant in BET2_GRID:
        model = _make_bet2_model(parent, variant)
        # Register for discover by using model dict directly (already shaped)
        row = _run(
            model,
            start=HUNT_START,
            end=HUNT_END,
            tag=f"bc_bet2_{variant['id']}_hunt",
            cash=cash,
        )
        row["variant_id"] = variant["id"]
        print(f"  hunt {variant['id']:24} {_fmt(row)}", flush=True)
        hunt_rows.append(row)

    # Pick best by ret among non-error with n floor
    viable = [
        r
        for r in hunt_rows
        if not r.get("error") and int(r.get("n", 0)) >= PROMOTION_GATES["min_n_hunt"]
    ]
    if not viable:
        return {
            "id": "bet2_exit_size",
            "status": "fail",
            "reason": "no_viable_hunt_grid_member",
            "hunt": {},
            "lockbox": {},
            "grid": [_metric_view(r) for r in hunt_rows],
        }

    best = max(viable, key=lambda r: (float(r["ret"]), float(r["sharpe"])))
    print(f"  best hunt: {best.get('variant_id')} → lockbox", flush=True)

    # Rebuild same variant model for lockbox
    variant = next(v for v in BET2_GRID if v["id"] == best["variant_id"])
    model = _make_bet2_model(parent, variant)
    lock = _run(
        model,
        start=LOCKBOX_START,
        end=LOCKBOX_END,
        tag=f"bc_bet2_{variant['id']}_lock",
        cash=cash,
    )
    print(f"  lockbox {_fmt(lock)}", flush=True)
    ok, reason = passes_promotion_gates(lock, baseline_lock, min_n=PROMOTION_GATES["min_n_lockbox"])
    return {
        "id": "bet2_exit_size",
        "status": "promote" if ok else "fail",
        "reason": reason,
        "best_variant": variant["id"],
        "hunt": _metric_view(best),
        "lockbox": _metric_view(lock),
        "grid": [_metric_view(r) for r in hunt_rows],
    }


def run_bet3(cash: float, baseline_lock: dict[str, Any]) -> dict[str, Any]:
    print("[beat-champ] Bet 3: macro soft-size (v62_macro_softsize)", flush=True)
    model_dir = MODELS_ROOT / "v62_macro_softsize"
    if not model_dir.exists() or not (model_dir / "signal_engine.py").exists():
        return {
            "id": "bet3_macro_softsize",
            "status": "fail",
            "reason": "v62_macro_softsize not scaffolded",
            "hunt": {},
            "lockbox": {},
        }
    try:
        m = _discover("v62_macro_softsize")
    except FileNotFoundError as e:
        return {
            "id": "bet3_macro_softsize",
            "status": "fail",
            "reason": str(e),
            "hunt": {},
            "lockbox": {},
        }

    hunt = _run(m, start=HUNT_START, end=HUNT_END, tag="bc_bet3_hunt", cash=cash)
    print(f"  hunt    {_fmt(hunt)}", flush=True)
    lock = _run(m, start=LOCKBOX_START, end=LOCKBOX_END, tag="bc_bet3_lock", cash=cash)
    print(f"  lockbox {_fmt(lock)}", flush=True)
    ok, reason = passes_promotion_gates(lock, baseline_lock, min_n=PROMOTION_GATES["min_n_lockbox"])
    if ok and int(hunt.get("n", 0)) < PROMOTION_GATES["min_n_hunt"]:
        ok, reason = False, f"hunt_n={hunt.get('n')}<{PROMOTION_GATES['min_n_hunt']}"
    return {
        "id": "bet3_macro_softsize",
        "status": "promote" if ok else "fail",
        "reason": reason,
        "hunt": _metric_view(hunt),
        "lockbox": _metric_view(lock),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Beat v39d_confluence campaign")
    parser.add_argument("--cash", type=float, default=1000.0)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--from-bet", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--skip-bet1", action="store_true")
    parser.add_argument("--skip-bet2", action="store_true")
    parser.add_argument("--skip-bet3", action="store_true")
    args = parser.parse_args()
    cash = float(args.cash)

    OUT.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "started_at": _now(),
        "finished_at": None,
        "cash": cash,
        "codes": EQUITY_WINNER_BAG,
        "hunt_window": [HUNT_START, HUNT_END],
        "lockbox_window": [LOCKBOX_START, LOCKBOX_END],
        "baseline": {},
        "bets": [],
        "promoted": [],
        "promoted_best": None,
        "plateau": False,
        "promotion_gates": PROMOTION_GATES,
    }

    state["baseline"] = run_baseline(cash)
    _save_state(state, cash)
    if args.baseline_only:
        state["finished_at"] = _now()
        _save_state(state, cash)
        print("[beat-champ] baseline-only done", flush=True)
        return 0

    baseline_lock = state["baseline"]["lockbox"]
    runners = []
    if not args.skip_bet1 and args.from_bet <= 1:
        runners.append(("bet1", run_bet1))
    if not args.skip_bet2 and args.from_bet <= 2:
        runners.append(("bet2", run_bet2))
    if not args.skip_bet3 and args.from_bet <= 3:
        runners.append(("bet3", run_bet3))

    # If from_bet > 1, still allow later bets
    if args.from_bet == 2:
        runners = [r for r in runners if r[0] != "bet1"]
    if args.from_bet == 3:
        runners = [r for r in runners if r[0] == "bet3"]

    promoted = False
    for _name, fn in runners:
        result = fn(cash, baseline_lock)
        state["bets"].append(result)
        _save_state(state, cash)
        if result.get("status") == "promote":
            state["promoted"] = [result["id"]]
            state["promoted_best"] = result["id"]
            promoted = True
            print(f"[beat-champ] PROMOTED {result['id']}: {result.get('reason')}", flush=True)
            break
        print(f"[beat-champ] FAIL {result['id']}: {result.get('reason')}", flush=True)

    if not promoted:
        fails = [b for b in state["bets"] if b.get("status") == "fail"]
        # Full campaign plateau: all three bet slots failed (even if resumed).
        attempted_ids = {b.get("id") for b in state["bets"]}
        full_set = {"bet1_meta_ledger", "bet2_exit_size", "bet3_macro_softsize"}
        if full_set.issubset(attempted_ids) and len(fails) >= 3:
            state["plateau"] = True
        elif len(fails) >= len(runners) and len(runners) >= 3:
            state["plateau"] = True

    state["finished_at"] = _now()
    _save_state(state, cash)
    print(
        f"[beat-champ] done promoted_best={state['promoted_best']} plateau={state['plateau']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
