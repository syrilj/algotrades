#!/usr/bin/env python3
"""Unified model evolution pipeline (phases 0–4).

Honest automation:
  - equity OHLCV can CLAIM / promote
  - options synthetic is RESEARCH only (synthetic BS pricing)
  - GEX excluded from auto-promote
  - robust rank = mean utility − instability/OOS/lock/confidence penalties
  - persistent failure tags guide later mutation selection
  - content-addressed cache under runs/evolve_cache/
  - constrained mutations only (hunt/config patches)

Usage:
  .venv/bin/python tools/evolve_pipeline.py rank --track equity --quick
  .venv/bin/python tools/evolve_pipeline.py train --epochs 20 --base v23_devin_overlay
  .venv/bin/python tools/evolve_pipeline.py train --continuous --max-epochs 100
  .venv/bin/python tools/evolve_pipeline.py brain
  .venv/bin/python tools/evolve_pipeline.py loop --gens 3 --track equity
  .venv/bin/python tools/evolve_pipeline.py feedback
  .venv/bin/python tools/evolve_pipeline.py meta
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.data_contracts import DataTrack  # noqa: E402
from evolve.pipeline import (  # noqa: E402
    EQUITY_ELITE,
    OPTS_ELITE,
    run_all,
    run_loop,
    run_meta,
    run_rank,
)
from evolve.train_loop import run_train  # noqa: E402
from evolve.genome import DEFAULT_BRAIN, load_brain  # noqa: E402
from evolve.model_feedback import DEFAULT_MEMORY_PATH, load_memory  # noqa: E402
from evolve.auditor import audit_many, audit_model, write_audit  # noqa: E402


def _track(s: str) -> str:
    s = (s or "equity").lower().strip()
    if s in ("equity", "eq", "stock", "daily", DataTrack.EQUITY_OHLCV.value):
        return DataTrack.EQUITY_OHLCV.value
    if s in ("options", "opts", "option", DataTrack.OPTIONS_SYNTHETIC.value):
        return DataTrack.OPTIONS_SYNTHETIC.value
    if s in ("gex", DataTrack.GEX_LIVE_ONLY.value):
        return DataTrack.GEX_LIVE_ONLY.value
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="evolve_pipeline",
        description="Backtest farm + feedback loop + meta for all models",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--family", default="poc_va_macdha")
        p.add_argument("--cash", type=float, default=10_000)
        p.add_argument("--workers", type=int, default=1)
        p.add_argument("--no-reuse", action="store_true", help="ignore disk/content cache")
        p.add_argument("--models", type=str, default="", help="comma list; default = discover/pool")
        p.add_argument("--out", type=str, default="", help="output run dir")

    p_rank = sub.add_parser("rank", help="Phase 0+1: screen + deep + multi-lock")
    add_common(p_rank)
    p_rank.add_argument("--track", default="equity", help="equity | options")
    p_rank.add_argument("--top", type=int, default=8)
    p_rank.add_argument("--quick", action="store_true")
    p_rank.add_argument("--budget", type=int, default=0, help="max models to screen (0=all)")
    p_rank.add_argument("--no-multi-lock", action="store_true")
    p_rank.add_argument(
        "--elite",
        action="store_true",
        help="use EQUITY_ELITE or OPTS_ELITE pool when --models omitted",
    )

    p_loop = sub.add_parser("loop", help="Phase 2(+3): multi-gen feedback + mutations")
    add_common(p_loop)
    p_loop.add_argument("--track", default="equity")
    p_loop.add_argument("--gens", type=int, default=3)
    p_loop.add_argument("--top", type=int, default=5)
    p_loop.add_argument("--max-mutations", type=int, default=8)
    p_loop.add_argument("--max-bt-per-gen", type=int, default=40)
    p_loop.add_argument("--memory", type=str, default="", help="failure-memory JSON path")

    p_feedback = sub.add_parser("feedback", help="Show learned failures and mutation outcomes")
    p_feedback.add_argument("--memory", type=str, default="")
    p_feedback.add_argument("--model", type=str, default="", help="show one model record")
    p_feedback.add_argument("--json", action="store_true")

    p_meta = sub.add_parser("meta", help="Phase 4: meta MLP recipe (secondary only)")
    p_meta.add_argument("--codes", type=str, default="")
    p_meta.add_argument("--start", default="2024-08-01")
    p_meta.add_argument("--end", default="2026-07-11")
    p_meta.add_argument("--out", type=str, default="")

    p_all = sub.add_parser("all", help="Equity rank+loop, options research rank, meta")
    p_all.add_argument("--family", default="poc_va_macdha")
    p_all.add_argument("--cash", type=float, default=10_000)
    p_all.add_argument("--gens", type=int, default=2)
    p_all.add_argument("--workers", type=int, default=1)
    p_all.add_argument("--quick", action="store_true")
    p_all.add_argument("--skip-meta", action="store_true")
    p_all.add_argument("--skip-options", action="store_true")

    p_train = sub.add_parser(
        "train",
        help="Self-feedback train loop: mutate genome → OOS reward → keep improvements (like model training)",
    )
    p_train.add_argument("--epochs", type=int, default=8, help="training epochs this session")
    p_train.add_argument("--continuous", action="store_true", help="run until --max-epochs")
    p_train.add_argument("--max-epochs", type=int, default=50)
    p_train.add_argument("--base", type=str, default="", help="base model id (default brain or v23)")
    p_train.add_argument("--track", default="equity", help="equity | options")
    p_train.add_argument("--cash", type=float, default=10_000)
    p_train.add_argument("--seed", type=int, default=42)
    p_train.add_argument("--no-reuse", action="store_true")
    p_train.add_argument("--meta-every", type=int, default=5, help="retrain meta MLP every K epochs (0=off)")
    p_train.add_argument("--out", type=str, default="")
    p_train.add_argument("--brain", type=str, default="", help="path to BRAIN.json checkpoint")

    p_brain = sub.add_parser("brain", help="Show persistent train brain / best genome")
    p_brain.add_argument("--brain", type=str, default="")

    p_audit = sub.add_parser(
        "audit",
        help="Auditor model: check engines for overfit, bad practice, look-ahead, vanity metrics",
    )
    p_audit.add_argument(
        "--models",
        type=str,
        default="",
        help="comma list (default: WINNER + elite equity + brain base)",
    )
    p_audit.add_argument("--family", default="poc_va_macdha")
    p_audit.add_argument("--json", action="store_true", help="print JSON reports")

    args = ap.parse_args(argv)
    reuse = not getattr(args, "no_reuse", False)
    models = [x.strip() for x in (getattr(args, "models", "") or "").split(",") if x.strip()] or None
    out = Path(args.out) if getattr(args, "out", "") else None
    if out and not out.is_absolute():
        out = ROOT / out

    if args.cmd == "rank":
        tr = _track(args.track)
        if tr == DataTrack.GEX_LIVE_ONLY.value:
            print("GEX is live-only; cannot rank historically. Use equity or options.", file=sys.stderr)
            return 2
        if not models and getattr(args, "elite", False):
            models = (
                list(OPTS_ELITE)
                if tr == DataTrack.OPTIONS_SYNTHETIC.value
                else list(EQUITY_ELITE)
            )
            print(f"[evolve] elite pool ({len(models)}): {models}", flush=True)
        state = run_rank(
            family=args.family,
            track=tr,
            cash=args.cash,
            top=args.top,
            models=models,
            reuse=reuse,
            workers=args.workers,
            budget=args.budget or None,
            multi_lock=not args.no_multi_lock,
            quick=args.quick,
            out_dir=out,
        )
        print("promote:", state.get("promote"))
        return 0

    if args.cmd == "loop":
        tr = _track(args.track)
        if tr == DataTrack.GEX_LIVE_ONLY.value:
            print("GEX excluded from loop.", file=sys.stderr)
            return 2
        memory_path = Path(args.memory) if args.memory else None
        if memory_path and not memory_path.is_absolute():
            memory_path = ROOT / memory_path
        state = run_loop(
            family=args.family,
            track=tr,
            cash=args.cash,
            gens=args.gens,
            top=args.top,
            models=models,
            reuse=reuse,
            workers=args.workers,
            max_mutations=args.max_mutations,
            max_backtests_per_gen=args.max_bt_per_gen,
            out_dir=out,
            memory_path=memory_path,
        )
        print("best_utility:", state.get("best_utility"), "promote:", state.get("promote"))
        return 0

    if args.cmd == "feedback":
        memory_path = Path(args.memory) if args.memory else DEFAULT_MEMORY_PATH
        if not memory_path.is_absolute():
            memory_path = ROOT / memory_path
        memory = load_memory(memory_path)
        if args.model:
            payload = (memory.get("models") or {}).get(args.model)
            if payload is None:
                print(f"No feedback recorded for {args.model}", file=sys.stderr)
                return 1
            print(json.dumps({"model": args.model, **payload}, indent=2))
            return 0
        if args.json:
            print(json.dumps(memory, indent=2))
            return 0
        failure_totals: dict[str, int] = {}
        for model in (memory.get("models") or {}).values():
            for tag, count in (model.get("failures") or {}).items():
                failure_totals[tag] = failure_totals.get(tag, 0) + int(count)
        print(f"memory: {memory_path}")
        print("recurring failures:")
        for tag, count in sorted(failure_totals.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {tag:24} {count}")
        print("mutation outcomes:")
        mutations = memory.get("mutations") or {}
        for name, stat in sorted(
            mutations.items(),
            key=lambda item: float(item[1].get("mean_delta", 0)),
            reverse=True,
        ):
            print(
                f"  {name:24} attempts={stat.get('attempts', 0):3} "
                f"wins={stat.get('wins', 0):3} mean_delta={float(stat.get('mean_delta', 0)):+.3f}"
            )
        return 0

    if args.cmd == "meta":
        codes = [x.strip() for x in (args.codes or "").split(",") if x.strip()] or None
        state = run_meta(codes=codes, start=args.start, end=args.end, out_dir=out)
        print("meta_ok:", (state.get("meta") or {}).get("ok"))
        return 0

    if args.cmd == "all":
        state = run_all(
            family=args.family,
            cash=args.cash,
            gens=args.gens,
            quick=args.quick,
            workers=args.workers,
            skip_meta=args.skip_meta,
            skip_options=args.skip_options,
        )
        print("summary promote:", state.get("equity_promote"), "dir:", state.get("run_dir"))
        return 0

    if args.cmd == "train":
        tr = _track(args.track)
        if tr == DataTrack.GEX_LIVE_ONLY.value:
            print("GEX cannot train historically.", file=sys.stderr)
            return 2
        brain_p = Path(args.brain) if args.brain else DEFAULT_BRAIN
        if not brain_p.is_absolute():
            brain_p = ROOT / brain_p
        out = Path(args.out) if args.out else None
        if out and not out.is_absolute():
            out = ROOT / out
        base = args.base.strip() or None
        state = run_train(
            epochs=args.epochs,
            base_model=base,
            track=tr,
            cash=args.cash,
            seed=args.seed,
            reuse=not args.no_reuse,
            retrain_meta_every=args.meta_every,
            brain_path=brain_p,
            out_dir=out,
            continuous=args.continuous,
            max_epochs_continuous=args.max_epochs,
        )
        print(
            "train done best_oos=",
            state.get("best_utility_oos"),
            "epoch=",
            state.get("epoch"),
            "accepted=",
            state.get("accepted"),
        )
        return 0

    if args.cmd == "brain":
        brain_p = Path(args.brain) if args.brain else DEFAULT_BRAIN
        if not brain_p.is_absolute():
            brain_p = ROOT / brain_p
        b = load_brain(brain_p)
        print(json.dumps(b.to_dict(), indent=2, default=str)[:4000])
        return 0

    if args.cmd == "audit":
        ids = [x.strip() for x in (args.models or "").split(",") if x.strip()]
        if not ids:
            ids = [
                "v23_devin_overlay",
                "v20b_macro_light",
                "v15_meta_xgb",
                "v35_softstruct_bag8",
                "v30_feedback_pro",
            ]
            brain_p = DEFAULT_BRAIN
            if brain_p.exists():
                try:
                    b = load_brain(brain_p)
                    if b.genome.base_model and b.genome.base_model not in ids:
                        ids.insert(0, b.genome.base_model)
                except Exception:
                    pass
        reports = audit_many(ids, family=args.family)
        # also audit brain history if present
        if DEFAULT_BRAIN.exists():
            try:
                b = load_brain(DEFAULT_BRAIN)
                br = audit_model(
                    model_id="evolve_brain",
                    brain_history=b.history,
                    train_metrics={
                        "u_train": b.best_utility_train,
                        "utility": b.best_utility_oos,
                        "n": 0,
                    },
                    oos_metrics={
                        "u_oos": b.best_utility_oos,
                        "utility": b.best_utility_oos,
                        "n": 0,
                    },
                )
                # only keep brain-history findings
                from evolve.auditor import audit_brain_history, AuditReport, Finding

                hf = audit_brain_history(b.history)
                if hf:
                    br = AuditReport(
                        target="evolve_brain",
                        verdict="FAIL" if any(f.severity in ("fail", "block") for f in hf) else "WARN",
                        score=max(0, 100 - 15 * len(hf)),
                        findings=hf,
                    )
                    reports.append(br)
            except Exception as e:
                print(f"[audit] brain skip: {e}", flush=True)

        for r in reports:
            path = write_audit(r)
            if not args.json:
                print(
                    f"[{r.verdict:5}] {r.score:5.1f}  {r.target:32}  "
                    f"findings={len(r.findings)}  → {path.relative_to(ROOT)}",
                    flush=True,
                )
                for f in r.findings:
                    if f.severity in ("fail", "block", "warn"):
                        print(f"         - {f.severity}: {f.code}: {f.title}", flush=True)
        if args.json:
            print(json.dumps([r.to_dict() for r in reports], indent=2))
        # exit non-zero if any BLOCK/FAIL
        bad = [r for r in reports if r.verdict in ("FAIL", "BLOCK")]
        return 1 if bad else 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
