#!/usr/bin/env python3
"""Train / freeze / OOS-verify v71_live_confidence.

Protocol (anti-overfit)
-----------------------
1. Enumerate a small pre-registered variant menu (no free-form search).
2. Score variants ONLY on train window: 2024-08-01 → 2025-08-01.
3. Freeze the best hunt_config into models/.../v71_live_confidence/.
4. Evaluate once on locked holdout: 2025-08-01 → 2026-07-11.
5. Also report full-window and v50 baselines for comparison.
6. Never retune after seeing holdout.

Usage
-----
  .venv/bin/python tools/train_v71_live_confidence.py --workers 4 --cash 1000
  .venv/bin/python tools/train_v71_live_confidence.py --skip-train   # re-verify frozen
  .venv/bin/python tools/train_v71_live_confidence.py --quick        # 4 variants only
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.farm import EQUITY_WINNER_BAG, run_batch  # noqa: E402

MODELS = ROOT / "models" / "poc_va_macdha"
TARGET = MODELS / "v71_live_confidence"
OUT = ROOT / "runs" / "v71_live_confidence"
SCRATCH = MODELS / "_v71_scratch"

TRAIN = ("2024-08-01", "2025-08-01")
HOLDOUT = ("2025-08-01", "2026-07-11")
FULL = ("2024-08-01", "2026-07-11")

# Pre-registered promotion floors (holdout). Written into STATE before train.
PROMOTION = {
    "min_wr": 0.75,
    "min_n": 20,
    "min_ret": 0.0,
    "min_sharpe": 1.0,
    "max_dd": -0.25,  # more negative is worse; require dd >= max_dd
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_hunt() -> dict[str, Any]:
    return {
        "base_models": ["v45_ultimate_rsi"],
        "primary": "v45_ultimate_rsi",
        "secondary": None,
        "secondary_agree_boost": True,
        "agree_boost_mult": 1.15,
        "trend_filter": {
            "lookback": 250,
            "price_col": "close",
            "direction": "above",
            "apply": "entry",
        },
        "quality": {"enabled": True, "min_score": 1},
        "confidence": {
            "use_rsi_depth": True,
            "quality_weight": 0.65,
            "rsi_weight": 0.35,
            "min_scale_frac": 0.5,
            "max_scale_frac": 1.0,
        },
        "signal_scale": 0.225,
        "max_scale_cap": 0.35,
        "stop_loss_pct": 0.0,
        "selection_rule": "frozen_before_oos_eval",
        "train_window_end": TRAIN[1],
    }


def variant_menu(quick: bool = False) -> list[tuple[str, dict[str, Any]]]:
    """Pre-registered variants — do not expand after seeing holdout."""
    b = _base_hunt()
    variants: list[tuple[str, dict[str, Any]]] = []

    def add(name: str, **patches: Any) -> None:
        h = deepcopy(b)
        for k, v in patches.items():
            if isinstance(v, dict) and isinstance(h.get(k), dict):
                h[k] = {**h[k], **v}
            else:
                h[k] = v
        h["variant_id"] = name
        variants.append((name, h))

    # A — size-UP on conf, quality floor=1 (frozen winner 2026-07-15)
    add(
        "sizeup_q1",
        confidence={
            "use_rsi_depth": True,
            "quality_weight": 0.65,
            "rsi_weight": 0.35,
            "min_scale_frac": 1.0,
            "max_scale_frac": 1.55,
        },
        max_scale_cap=0.40,
    )
    # B — soft size-down (ablation; historically underperformed)
    add(
        "soft_q1_rsi",
        confidence={
            "use_rsi_depth": True,
            "quality_weight": 0.65,
            "rsi_weight": 0.35,
            "min_scale_frac": 0.5,
            "max_scale_frac": 1.0,
        },
    )
    # C — harder floor=2 size-up (high WR, often thins OOS n)
    add(
        "sizeup_q2",
        quality={"enabled": True, "min_score": 2},
        signal_scale=0.25,
        confidence={
            "use_rsi_depth": True,
            "quality_weight": 0.65,
            "rsi_weight": 0.35,
            "min_scale_frac": 1.0,
            "max_scale_frac": 1.4,
        },
        max_scale_cap=0.40,
    )
    # D — no quality gate, conf from RSI only
    add(
        "trend_rsi_only",
        quality={"enabled": False, "min_score": 0},
        confidence={
            "use_rsi_depth": True,
            "quality_weight": 0.0,
            "rsi_weight": 1.0,
            "min_scale_frac": 0.6,
            "max_scale_frac": 1.0,
        },
    )
    # E — v50 clone ablation (never eligible for freeze)
    add(
        "v50_clone",
        quality={"enabled": False, "min_score": 0},
        confidence={
            "use_rsi_depth": False,
            "quality_weight": 1.0,
            "rsi_weight": 0.0,
            "min_scale_frac": 1.0,
            "max_scale_frac": 1.0,
        },
        _ablation=True,
    )
    # F — secondary agreement boost with v39d
    add(
        "sizeup_q1_v39d",
        base_models=["v45_ultimate_rsi", "v39d_confluence"],
        secondary="v39d_confluence",
        secondary_agree_boost=True,
        agree_boost_mult=1.2,
        confidence={
            "use_rsi_depth": True,
            "quality_weight": 0.65,
            "rsi_weight": 0.35,
            "min_scale_frac": 1.0,
            "max_scale_frac": 1.55,
        },
        max_scale_cap=0.40,
    )
    # G — hard quality=1 fixed size ablation
    add(
        "hard_q1_fixed",
        confidence={
            "use_rsi_depth": False,
            "quality_weight": 1.0,
            "rsi_weight": 0.0,
            "min_scale_frac": 1.0,
            "max_scale_frac": 1.0,
        },
        _ablation=True,
    )

    if quick:
        keep = {"sizeup_q1", "sizeup_q2", "trend_rsi_only", "soft_q1_rsi"}
        variants = [(n, h) for n, h in variants if n in keep]
    return variants


def _materialize_variant(name: str, hunt: dict[str, Any]) -> Path:
    """Copy target model into a scratch model dir with this hunt_config."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    dest = SCRATCH / f"v71__{name}"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for fname in (
        "signal_engine.py",
        "gates.py",
        "config.json",
        "DEPENDENCIES.json",
        "MODEL.md",
    ):
        src = TARGET / fname
        if src.exists():
            shutil.copy2(src, dest / fname)
    # Point strategy name at scratch id so run artifacts are distinct
    cfg_path = dest / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        cfg.setdefault("strategy", {})
        cfg["strategy"]["name"] = f"v71__{name}"
        cfg["strategy"]["model_version"] = f"v71__{name}"
        cfg_path.write_text(json.dumps(cfg, indent=2))
    (dest / "hunt_config.json").write_text(json.dumps(hunt, indent=2))
    return dest


def _cleanup_scratch() -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH, ignore_errors=True)


def _train_score(row: dict[str, Any], *, ablation: bool = False) -> float:
    """Train selection score: prefer high WR with enough trades + return + sharpe.

    Composite is pre-registered. Does NOT use holdout.
    Ablation arms (pure v50 clone, fixed-size controls) are scored but ineligible.
    """
    if ablation:
        return -1e8
    if row.get("error"):
        return -1e9
    wr = float(row.get("wr") or 0.0)
    n = int(row.get("n") or 0)
    ret = float(row.get("ret") or 0.0)
    sharpe = float(row.get("sharpe") or 0.0)
    dd = float(row.get("dd") or 0.0)
    if n < 12:
        return -1e6 + n  # insufficient sample
    if ret <= -0.05:
        return -1e5 + ret
    # Prefer high WR + capacity, then risk-adjusted return.
    return (
        120.0 * wr
        + 28.0 * math.sqrt(max(n, 0))
        + 35.0 * max(sharpe, 0.0)
        + 25.0 * max(ret, 0.0)
        + 12.0 * max(0.0, 0.25 + dd)  # dd is negative
    )


def _oos_composite(row: dict[str, Any]) -> float:
    wr = float(row.get("wr") or 0.0)
    n = int(row.get("n") or 0)
    sharpe = float(row.get("sharpe") or 0.0)
    return wr * math.sqrt(max(n, 0)) * max(sharpe, 0.0)


def _passes_promotion(row: dict[str, Any], v50_oos: dict[str, Any] | None) -> bool:
    if row.get("error"):
        return False
    wr = float(row.get("wr") or 0.0)
    n = int(row.get("n") or 0)
    ret = float(row.get("ret") or 0.0)
    sharpe = float(row.get("sharpe") or 0.0)
    dd = float(row.get("dd") or 0.0)
    if wr < PROMOTION["min_wr"]:
        return False
    if n < PROMOTION["min_n"]:
        return False
    if ret <= PROMOTION["min_ret"]:
        return False
    if sharpe < PROMOTION["min_sharpe"]:
        return False
    if dd < PROMOTION["max_dd"]:
        return False
    if v50_oos and not v50_oos.get("error"):
        better_comp = _oos_composite(row) >= _oos_composite(v50_oos) * 0.98
        better_ret = ret >= float(v50_oos.get("ret") or 0.0) and wr >= PROMOTION["min_wr"]
        return better_comp or better_ret
    return True


def _fmt(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"{row.get('id', '?'):32} FAIL {str(row['error'])[:100]}"
    return (
        f"{row.get('id', '?'):32} wr={float(row.get('wr', 0))*100:5.1f}% "
        f"ret={float(row.get('ret', 0))*100:7.1f}% "
        f"dd={abs(float(row.get('dd', 0)))*100:5.1f}% "
        f"sharpe={float(row.get('sharpe', 0)):5.2f} "
        f"n={int(row.get('n', 0)):3d} "
        f"final=${float(row.get('final_at_cash') or row.get('final') or 0):,.0f}"
    )


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in row.items()
        if isinstance(v, (str, int, float, bool, list, dict, type(None)))
    }


def _run_baselines(cash: float, source: str, workers: int) -> dict[str, Any]:
    """v50 full + holdout and v39d full for comparison."""
    models = dmr.discover_models(["v50_high_win_rate", "v39d_confluence", "v70_high_confidence_wr"])
    by_id = {m["id"]: m for m in models}
    out: dict[str, Any] = {}
    jobs = [
        ("v50_train", "v50_high_win_rate", TRAIN),
        ("v50_oos", "v50_high_win_rate", HOLDOUT),
        ("v50_full", "v50_high_win_rate", FULL),
        ("v39d_full", "v39d_confluence", FULL),
        ("v70_full", "v70_high_confidence_wr", FULL),
        ("v70_oos", "v70_high_confidence_wr", HOLDOUT),
    ]
    # Sequential for clarity (baselines are few)
    for key, mid, (start, end) in jobs:
        m = by_id.get(mid)
        if not m:
            out[key] = {"error": f"missing model {mid}", "id": mid}
            continue
        try:
            row = dmr.run_one(
                m,
                mode="daily",
                codes=EQUITY_WINNER_BAG,
                start=start,
                end=end,
                tag=f"v71base_{key}",
                cash=cash,
                force_1d=False,
                source=source,
                interval="1H",
                reuse=True,
            )
            out[key] = _clean_row(row)
            print(f"  baseline {key:12} {_fmt(row)}", flush=True)
        except Exception as exc:
            out[key] = {"error": str(exc), "id": mid}
            print(f"  baseline {key:12} FAIL {exc}", flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Train + OOS-verify v71_live_confidence")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cash", type=float, default=1000.0)
    parser.add_argument("--source", type=str, default="local")
    parser.add_argument("--quick", action="store_true", help="4-variant train menu only")
    parser.add_argument("--skip-train", action="store_true", help="Skip train sweep; verify frozen hunt only")
    parser.add_argument("--keep-scratch", action="store_true", help="Keep temporary variant model dirs")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "updated_at": _now(),
        "protocol": {
            "train": list(TRAIN),
            "holdout": list(HOLDOUT),
            "full": list(FULL),
            "bag": EQUITY_WINNER_BAG,
            "source": args.source,
            "cash": args.cash,
            "promotion": PROMOTION,
        },
        "promoted": False,
    }

    print("=== v71 baselines ===", flush=True)
    baselines = _run_baselines(args.cash, args.source, args.workers)
    state["baselines"] = baselines

    best_hunt: dict[str, Any] | None = None
    best_name = "soft_q1_rsi"
    train_rows: list[dict[str, Any]] = []

    if not args.skip_train:
        print("\n=== v71 train-window variant sweep ===", flush=True)
        menu = variant_menu(quick=args.quick)
        scratch_dirs: list[Path] = []
        model_specs: list[dict[str, Any]] = []
        name_by_id: dict[str, str] = {}
        hunt_by_name: dict[str, dict[str, Any]] = {}

        try:
            for name, hunt in menu:
                dest = _materialize_variant(name, hunt)
                scratch_dirs.append(dest)
                hunt_by_name[name] = hunt
                # discover_models only looks under models/poc_va_macdha/* dirs
                # Our scratch is models/poc_va_macdha/_v71_scratch/v71__name — nested, won't discover.
                # So register a top-level alias dir.
                alias = MODELS / f"v71__{name}"
                if alias.exists():
                    shutil.rmtree(alias)
                shutil.copytree(dest, alias)
                scratch_dirs.append(alias)
                mid = f"v71__{name}"
                name_by_id[mid] = name

            models = dmr.discover_models([f"v71__{n}" for n, _ in menu])
            if not models:
                print("ERROR: no variant models discovered", flush=True)
                return 1

            rows = run_batch(
                models,
                codes=EQUITY_WINNER_BAG,
                start=TRAIN[0],
                end=TRAIN[1],
                tag="v71_train",
                cash=args.cash,
                source=args.source,
                track="equity",
                workers=args.workers,
                reuse=False,
            )
            for r in rows:
                cr = _clean_row(r)
                vname = str(name_by_id.get(str(r.get("id")), r.get("id")))
                cr["variant"] = vname
                hunt = hunt_by_name.get(vname, {})
                ablation = bool(hunt.get("_ablation")) or vname in {"v50_clone", "hard_q1_fixed"}
                cr["ablation"] = ablation
                cr["train_score"] = _train_score(r, ablation=ablation)
                train_rows.append(cr)
                print(f"  train {_fmt(r)}  score={cr['train_score']:.2f}", flush=True)

            train_rows.sort(key=lambda x: float(x.get("train_score", -1e9)), reverse=True)
            if not train_rows or train_rows[0].get("error"):
                print("ERROR: all train variants failed", flush=True)
                state["train"] = train_rows
                (OUT / "STATE.json").write_text(json.dumps(state, indent=2))
                return 1

            best = train_rows[0]
            best_name = str(best.get("variant") or best_name)
            best_hunt = hunt_by_name[best_name]
            best_hunt["selected_from_train"] = {
                "variant": best_name,
                "train_score": best.get("train_score"),
                "train_wr": best.get("wr"),
                "train_ret": best.get("ret"),
                "train_n": best.get("n"),
                "train_sharpe": best.get("sharpe"),
                "selected_at": _now(),
            }
            print(f"\n  SELECTED train winner: {best_name}", flush=True)
            print(f"  {_fmt(best)}", flush=True)

            # Freeze into canonical model dir
            (TARGET / "hunt_config.json").write_text(json.dumps(best_hunt, indent=2))
            state["selected_variant"] = best_name
            state["frozen_hunt"] = best_hunt
        finally:
            if not args.keep_scratch:
                _cleanup_scratch()
                for name, _ in menu:
                    alias = MODELS / f"v71__{name}"
                    if alias.exists():
                        shutil.rmtree(alias, ignore_errors=True)
    else:
        hunt_path = TARGET / "hunt_config.json"
        best_hunt = json.loads(hunt_path.read_text()) if hunt_path.exists() else _base_hunt()
        best_name = str(best_hunt.get("variant_id") or best_hunt.get("selected_from_train", {}).get("variant") or "frozen")
        state["selected_variant"] = best_name
        state["frozen_hunt"] = best_hunt
        print(f"Using frozen hunt ({best_name})", flush=True)

    state["train"] = train_rows

    # ---- Holdout + full verification on frozen v71 ----
    print("\n=== v71 locked holdout + full ===", flush=True)
    m71 = dmr.discover_models(["v71_live_confidence"])[0]
    verify: dict[str, Any] = {}
    for key, (start, end) in (("oos", HOLDOUT), ("full", FULL), ("train", TRAIN)):
        try:
            row = dmr.run_one(
                m71,
                mode="daily",
                codes=EQUITY_WINNER_BAG,
                start=start,
                end=end,
                tag=f"v71_verify_{key}",
                cash=args.cash,
                force_1d=False,
                source=args.source,
                interval="1H",
                reuse=False,
            )
            verify[key] = _clean_row(row)
            print(f"  v71 {key:6} {_fmt(row)}", flush=True)
        except Exception as exc:
            verify[key] = {"error": str(exc), "id": "v71_live_confidence"}
            print(f"  v71 {key:6} FAIL {exc}", flush=True)

    state["verify"] = verify
    v50_oos = baselines.get("v50_oos")
    oos = verify.get("oos") or {}
    promoted = _passes_promotion(oos, v50_oos)
    state["promoted"] = promoted
    state["promotion_detail"] = {
        "passes": promoted,
        "oos_composite": _oos_composite(oos) if not oos.get("error") else None,
        "v50_oos_composite": _oos_composite(v50_oos) if v50_oos and not v50_oos.get("error") else None,
        "gates": PROMOTION,
    }

    # Write results.json into model dir (full-window contract)
    full = verify.get("full") or {}
    if not full.get("error"):
        results = {
            "portfolio": {
                "total_return": full.get("ret"),
                "max_drawdown": full.get("dd"),
                "sharpe": full.get("sharpe"),
                "trade_count": full.get("n"),
                "win_rate": full.get("wr"),
                "final_value": full.get("final"),
            },
            "holdout": {
                "total_return": oos.get("ret"),
                "max_drawdown": oos.get("dd"),
                "sharpe": oos.get("sharpe"),
                "trade_count": oos.get("n"),
                "win_rate": oos.get("wr"),
                "final_value": oos.get("final"),
            },
            "selected_variant": best_name,
            "promoted": promoted,
            "generated_utc": _now(),
            "codes": EQUITY_WINNER_BAG,
            "start": FULL[0],
            "end": FULL[1],
            "holdout_start": HOLDOUT[0],
            "holdout_end": HOLDOUT[1],
        }
        (TARGET / "results.json").write_text(json.dumps(results, indent=2))

    # Leaderboard markdown
    lines = [
        f"# v71_live_confidence train/verify ({_now()})",
        "",
        f"- Selected variant: `{best_name}`",
        f"- Promoted: **{promoted}**",
        f"- Train: `{TRAIN[0]}` → `{TRAIN[1]}`",
        f"- Holdout: `{HOLDOUT[0]}` → `{HOLDOUT[1]}`",
        f"- Full: `{FULL[0]}` → `{FULL[1]}`",
        "",
        "## Frozen model (verify)",
        "",
        "| window | wr | ret | dd | sharpe | n | final |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key in ("train", "oos", "full"):
        r = verify.get(key) or {}
        if r.get("error"):
            lines.append(f"| {key} | ERR | | | | | |")
        else:
            lines.append(
                f"| {key} | {float(r.get('wr', 0))*100:.1f}% | {float(r.get('ret', 0))*100:.1f}% | "
                f"{abs(float(r.get('dd', 0)))*100:.1f}% | {float(r.get('sharpe', 0)):.2f} | "
                f"{int(r.get('n', 0))} | ${float(r.get('final') or 0):,.0f} |"
            )
    lines += ["", "## Baselines", ""]
    for key, r in baselines.items():
        lines.append(f"- `{key}`: {_fmt(r)}")
    if train_rows:
        lines += ["", "## Train variants (ranked)", ""]
        for i, r in enumerate(train_rows, 1):
            lines.append(
                f"{i}. `{r.get('variant')}` score={float(r.get('train_score', 0)):.1f} — {_fmt(r)}"
            )
    lines += [
        "",
        "## Promotion gates",
        "",
        f"- min WR {PROMOTION['min_wr']*100:.0f}%, min n {PROMOTION['min_n']}, "
        f"min Sharpe {PROMOTION['min_sharpe']}, max |DD| {abs(PROMOTION['max_dd'])*100:.0f}%",
        f"- must match/beat v50 OOS composite or return (with WR floor)",
        f"- result: **{'PASS' if promoted else 'FAIL — research artifact, not promoted'}**",
        "",
    ]
    board = "\n".join(lines)
    (OUT / "LEADERBOARD.md").write_text(board)
    (OUT / "STATE.json").write_text(json.dumps(state, indent=2))
    print("\n" + board, flush=True)
    print(f"\nWrote {OUT / 'LEADERBOARD.md'} and {OUT / 'STATE.json'}", flush=True)
    return 0 if not oos.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
