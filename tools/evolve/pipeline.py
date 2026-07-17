"""Orchestrate rank / loop / meta phases."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.data_contracts import DataTrack  # noqa: E402
from evolve.farm import (  # noqa: E402
    WINDOWS,
    bags_for_track,
    discover,
    filter_track,
    pick_mode,
    rank_rows,
    run_batch,
    run_one_cached,
)
from evolve.gates import claim_min_trades, multi_lock_verdict  # noqa: E402
from evolve.meta_train import train_meta_recipe  # noqa: E402
from evolve.model_feedback import (  # noqa: E402
    DEFAULT_MEMORY_PATH,
    load_memory,
    prioritize_mutation_menu,
    rank_model_runs,
    save_memory,
    update_memory,
)
from evolve.mutations import MUTATION_MENU, spawn_mutations  # noqa: E402
from evolve.finalize import write_finalize_report, write_phases_doc  # noqa: E402
from evolve.report import write_leaderboard, write_state  # noqa: E402

# Equity CLAIM contenders + options RESEARCH contenders (OPTIONS_WINNER included).
DEFAULT_POOL = [
    # equity primary
    "v23_devin_overlay",
    "v20b_macro_light",
    "v15_meta_xgb",
    "v14_risk_kelly",
    "v8_4h_daily",
    "v13_specialists",
    "v12_regime_router",
    "v16_meta_risk",
    "v25_regime_grow",
    "v19_node_cloud",
    # options research (synthetic BS — never auto-promote)
    "v35_softstruct_bag8",
    "v34_bag6_opts",
    "v32_soft_react_opts",
    "v30_feedback_pro",
    "v28_feedback_opts",
    "v29_coldstart_opts",
    "v26_opts_evolve",
    "v22_opts_live",
    "v31_selective_nodes_opts",
]

EQUITY_ELITE = [
    "v23_devin_overlay",
    "v20b_macro_light",
    "v15_meta_xgb",
    "v14_risk_kelly",
    "v8_4h_daily",
    "v13_specialists",
    "v12_regime_router",
    "v16_meta_risk",
    "v25_regime_grow",
]

OPTS_ELITE = [
    "v35_softstruct_bag8",
    "v34_bag6_opts",
    "v32_soft_react_opts",
    "v30_feedback_pro",
    "v29_coldstart_opts",
    "v28_feedback_opts",
    "v31_selective_nodes_opts",
]


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _setup_dmr_out(run_root: Path) -> None:
    bt = run_root / "bt"
    bt.mkdir(parents=True, exist_ok=True)
    dmr.OUT = bt


def run_rank(
    *,
    family: str = "poc_va_macdha",
    track: str = DataTrack.EQUITY_OHLCV.value,
    cash: float = 10_000,
    top: int = 8,
    models: list[str] | None = None,
    reuse: bool = True,
    workers: int = 1,
    budget: int | None = None,
    multi_lock: bool = True,
    quick: bool = False,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Phase 0+1: discover → screen → deep → optional multi-lock → leaderboard."""
    out = out_dir or (ROOT / "runs" / f"evolve_rank_{_now_tag()}")
    out.mkdir(parents=True, exist_ok=True)
    _setup_dmr_out(out)
    dmr.CASH = cash

    bag, core = bags_for_track(track)
    found = discover(models, family=family)
    found = filter_track(found, track)
    if not found:
        found = discover(models, family=family)

    print(f"[evolve] rank track={track} models={len(found)} cash=${cash:,.0f}", flush=True)

    s0, e0 = WINDOWS["screen"] if not quick else WINDOWS["late"]
    screen = rank_rows(
        run_batch(
            found,
            codes=bag if not quick else core,
            start=s0,
            end=e0,
            tag="screen",
            cash=cash,
            track=track,
            reuse=reuse,
            workers=workers,
            budget=budget,
            on_each=lambda r: print(
                f"  screen {r.get('id'):32} util={float(r.get('utility') or 0):6.3f} "
                f"n={r.get('n')} {r.get('claim_level')} cache={r.get('from_cache') or r.get('reused')}",
                flush=True,
            ),
        )
    )

    top_ids = [r["id"] for r in screen if not r.get("error") and int(r.get("n") or 0) > 0][:top]
    by_id = {m["id"]: m for m in found}
    deep_models = [by_id[i] for i in top_ids if i in by_id]

    deep_rows: list[dict[str, Any]] = []
    deep_by_id: dict[str, list] = {m["id"]: [] for m in deep_models}
    if deep_models and not quick:
        print(f"[evolve] deep-test top {len(deep_models)}", flush=True)
        for m in deep_models:
            for tag, (ws, we), codes in (
                ("deep_full", WINDOWS["full"], bag),
                ("deep_late", WINDOWS["late"], bag),
                ("deep_core", WINDOWS["full"], core),
                ("deep_oos", WINDOWS["oos"], bag),
            ):
                r = run_one_cached(
                    m,
                    mode=pick_mode(m, track),
                    codes=codes,
                    start=ws,
                    end=we,
                    tag=tag,
                    cash=cash,
                    reuse=reuse,
                )
                deep_by_id[m["id"]].append(r)
                deep_rows.append(r)

    ml_out: dict[str, Any] = {}
    if multi_lock and deep_models and not quick:
        print("[evolve] multi-lock holdouts", flush=True)
        for m in deep_models[:5]:
            train = run_one_cached(
                m,
                mode=pick_mode(m, track),
                codes=core,
                start=WINDOWS["early_train"][0],
                end=WINDOWS["early_train"][1],
                tag="lock_train",
                cash=cash,
                reuse=reuse,
            )
            hold = run_one_cached(
                m,
                mode=pick_mode(m, track),
                codes=core,
                start=WINDOWS["oos"][0],
                end=WINDOWS["oos"][1],
                tag="lock_oos",
                cash=cash,
                reuse=reuse,
            )
            train["is_holdout"] = False
            hold["is_holdout"] = True
            ml_out[m["id"]] = multi_lock_verdict([train, hold])

    # Robust aggregation uses all comparable deep runs, penalizes dispersion
    # and OOS reversal, and exposes structured failure reasons.  Quick mode
    # has one comparable screen run per model.
    from evolve.gates import apply_gates

    rank_inputs = (
        {mid: tests for mid, tests in deep_by_id.items() if tests}
        if any(deep_by_id.values())
        else {row["id"]: [row] for row in screen}
    )
    ranking = rank_model_runs(
        rank_inputs,
        multi_lock=ml_out,
        min_trades=claim_min_trades(),
        expected_runs=4 if any(deep_by_id.values()) else 1,
    )
    for row in ranking:
        gated = apply_gates(row)
        row.update(gated)
        lock = ml_out.get(row["id"])
        if multi_lock and not quick and (not lock or not lock.get("ok")):
            row["may_auto_promote"] = False

    state = {
        "phase": "rank",
        "family": family,
        "track": track,
        "cash": cash,
        "screen": screen,
        "deep_by_id": {k: v for k, v in deep_by_id.items()},
        "ranking": ranking,
        "multi_lock": ml_out,
        "promote": [r["id"] for r in ranking if r.get("may_auto_promote")][:5],
        "state_path": str((out / "STATE.json").relative_to(ROOT)),
        "run_dir": str(out.relative_to(ROOT)),
    }
    write_state(out / "STATE.json", state)
    write_leaderboard(out / "LEADERBOARD.md", state)
    write_finalize_report(out, state)
    write_phases_doc()
    # convenience pointer
    latest = ROOT / "runs" / "evolve_latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(out.name, target_is_directory=True)
    except OSError:
        (ROOT / "runs" / "evolve_latest_path.txt").write_text(str(out))

    print(f"[evolve] wrote {out / 'LEADERBOARD.md'} + FINALIZE.md", flush=True)
    return state


def run_loop(
    *,
    family: str = "poc_va_macdha",
    track: str = DataTrack.EQUITY_OHLCV.value,
    cash: float = 10_000,
    gens: int = 3,
    top: int = 5,
    models: list[str] | None = None,
    reuse: bool = True,
    workers: int = 1,
    max_mutations: int = 8,
    max_backtests_per_gen: int = 40,
    epsilon: float = 0.02,
    out_dir: Path | None = None,
    memory_path: Path | None = None,
) -> dict[str, Any]:
    """Phase 2 (+3 if options track): multi-gen feedback + constrained mutations."""
    out = out_dir or (ROOT / "runs" / f"evolve_loop_{_now_tag()}")
    out.mkdir(parents=True, exist_ok=True)
    _setup_dmr_out(out)
    dmr.CASH = cash

    bag, _core = bags_for_track(track)
    pool_ids = models or DEFAULT_POOL
    found = {m["id"]: m for m in discover(pool_ids, family=family)}
    survivors = [found[i] for i in pool_ids if i in found]
    if not survivors:
        survivors = discover(None, family=family)
        survivors = filter_track(survivors, track)[:12]

    generations: list[dict[str, Any]] = []
    feedback_path = memory_path or DEFAULT_MEMORY_PATH
    memory = load_memory(feedback_path)
    best_u = -999.0
    no_improve = 0
    ranking: list[dict[str, Any]] = []

    for gen in range(1, gens + 1):
        print(f"\n[evolve] ===== GEN {gen}/{gens} survivors={len(survivors)} =====", flush=True)
        budget = max_backtests_per_gen
        screen_rows = run_batch(
                survivors,
                codes=bag,
                start=WINDOWS["full"][0],
                end=WINDOWS["full"][1],
                tag=f"G{gen}_screen",
                cash=cash,
                track=track,
                reuse=reuse,
                workers=workers,
                budget=budget,
            )
        screen = rank_model_runs(
            {row["id"]: [row] for row in screen_rows},
            min_trades=claim_min_trades(),
            expected_runs=1,
        )
        budget -= len(survivors)

        top_ids = [r["id"] for r in screen if not r.get("error") and int(r.get("n") or 0) > 0][:top]
        by_id = {m["id"]: m for m in survivors}
        elite = [by_id[i] for i in top_ids if i in by_id]

        # Mutations from elite parents
        mut_dir = out / "mutations" / f"gen{gen}"
        guided_menu = prioritize_mutation_menu(
            MUTATION_MENU,
            [row.get("failure_profile") or {} for row in screen],
            memory,
        )
        muts = spawn_mutations(
            elite[:3],
            mut_dir,
            max_mutations=min(max_mutations, max(0, budget)),
            menu=guided_menu,
        )
        mut_rows: list[dict[str, Any]] = []
        if muts:
            print(f"[evolve] gen{gen} mutations={len(muts)}", flush=True)
            raw_mut_rows = run_batch(
                    muts,
                    # Mutations and parents must use the identical evaluation
                    # contract or their scores are not rank-comparable.
                    codes=bag,
                    start=WINDOWS["full"][0],
                    end=WINDOWS["full"][1],
                    tag=f"G{gen}_mut",
                    cash=cash,
                    track=track,
                    reuse=reuse,
                    workers=workers,
                )
            mut_by_id = {m["id"]: m for m in muts}
            for row in raw_mut_rows:
                meta = mut_by_id.get(row["id"], {})
                row.update(
                    {
                        "is_mutation": True,
                        "parent": meta.get("parent"),
                        "mutation_name": meta.get("mutation_name"),
                        "mutation_targets": meta.get("mutation_targets", []),
                        "feedback_priority": meta.get("feedback_priority"),
                    }
                )
            mut_rows = rank_model_runs(
                {row["id"]: [row] for row in raw_mut_rows},
                min_trades=claim_min_trades(),
                expected_runs=1,
            )
            # merge mut models into pool for next gen if RESEARCH+
            for mr in mut_rows:
                mm = mut_by_id.get(mr["id"])
                if mm is None:
                    continue
                if mr.get("error"):
                    continue
                if str(mr.get("claim_level")) in ("RESEARCH", "CLAIM") and float(mr.get("utility") or -99) > -1:
                    survivors.append(mm)
                    by_id[mm["id"]] = mm

        combined = sorted(
            screen + mut_rows,
            key=lambda row: float(row.get("rank_score") or -99),
            reverse=True,
        )
        for index, row in enumerate(combined, 1):
            row["rank"] = index
        ranking = combined
        gen_best = next((r for r in combined if not r.get("error")), None)
        gu = float(gen_best.get("rank_score") or -99) if gen_best else -99
        parent_scores = {
            row["id"]: float(row.get("rank_score") or -99)
            for row in screen
        }
        memory = update_memory(memory, combined, generation=gen, parent_scores=parent_scores)
        save_memory(memory, feedback_path)
        generations.append(
            {
                "gen": gen,
                "best_id": gen_best.get("id") if gen_best else None,
                "best_utility": gu,
                "n_mutations": len(muts),
                "top": [r["id"] for r in combined[:8]],
                "top_failures": (gen_best.get("failure_profile") or {}).get("failure_tags", [])
                if gen_best
                else [],
                "mutation_priorities": [
                    {
                        "name": spec.get("name"),
                        "priority": spec.get("feedback_priority"),
                        "targets": spec.get("feedback_targets"),
                    }
                    for spec in guided_menu[:8]
                ],
            }
        )
        print(f"[evolve] gen{gen} best={gen_best and gen_best.get('id')} util={gu:.3f}", flush=True)

        if gu > best_u + epsilon:
            best_u = gu
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= 2:
                print("[evolve] early stop: no utility improve for 2 gens", flush=True)
                break

        # kill bottom half of non-mutation pool for next gen
        keep_ids = [r["id"] for r in combined if not r.get("error")][: max(3, top)]
        survivors = []
        seen = set()
        for mid in keep_ids:
            if mid in seen:
                continue
            if mid in by_id:
                survivors.append(by_id[mid])
                seen.add(mid)
            elif mid in found:
                survivors.append(found[mid])
                seen.add(mid)

    state = {
        "phase": "loop",
        "family": family,
        "track": track,
        "cash": cash,
        "generations": generations,
        "ranking": ranking,
        "promote": [r["id"] for r in ranking if r.get("may_auto_promote")][:5],
        "best_utility": best_u,
        "state_path": str((out / "STATE.json").relative_to(ROOT)),
        "run_dir": str(out.relative_to(ROOT)),
        "feedback_memory": str(feedback_path.relative_to(ROOT))
        if feedback_path.is_relative_to(ROOT)
        else str(feedback_path),
        "honesty": {
            "options_auto_promote": False,
            "mutations_are_config_patches": True,
            "primary_side_unchanged": True,
        },
    }
    write_state(out / "STATE.json", state)
    write_leaderboard(out / "LEADERBOARD.md", state)
    write_finalize_report(out, state)
    write_phases_doc()
    print(f"[evolve] loop done → {out / 'LEADERBOARD.md'} + FINALIZE.md", flush=True)
    return state


def run_meta(
    *,
    codes: list[str] | None = None,
    start: str = "2024-08-01",
    end: str = "2026-07-11",
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Phase 4: feature mine + meta MLP recipe (secondary only)."""
    out = out_dir or (ROOT / "runs" / f"evolve_meta_{_now_tag()}")
    bag = codes or EQUITY_CORE_FROM_FARM()
    recipe = train_meta_recipe(bag, start=start, end=end, out_dir=out)
    state = {
        "phase": "meta",
        "meta": recipe,
        "ranking": [],
        "track": DataTrack.EQUITY_OHLCV.value,
        "cash": 0,
        "state_path": str((out / "STATE.json").relative_to(ROOT)),
        "run_dir": str(out.relative_to(ROOT)),
    }
    write_state(out / "STATE.json", state)
    write_leaderboard(out / "LEADERBOARD.md", state)
    return state


def EQUITY_CORE_FROM_FARM() -> list[str]:
    from evolve.farm import EQUITY_CORE

    return list(EQUITY_CORE)


def run_all(
    *,
    family: str = "poc_va_macdha",
    cash: float = 10_000,
    gens: int = 2,
    quick: bool = False,
    workers: int = 1,
    skip_meta: bool = False,
    skip_options: bool = False,
) -> dict[str, Any]:
    """Run equity rank + loop; optional options research rank; optional meta."""
    root = ROOT / "runs" / f"evolve_all_{_now_tag()}"
    root.mkdir(parents=True, exist_ok=True)

    equity_rank = run_rank(
        family=family,
        track=DataTrack.EQUITY_OHLCV.value,
        cash=cash,
        quick=quick,
        workers=workers,
        multi_lock=not quick,
        out_dir=root / "equity_rank",
    )
    equity_loop = run_loop(
        family=family,
        track=DataTrack.EQUITY_OHLCV.value,
        cash=cash,
        gens=1 if quick else gens,
        workers=workers,
        max_mutations=4 if quick else 8,
        out_dir=root / "equity_loop",
    )

    options_rank = None
    if not skip_options:
        options_rank = run_rank(
            family=family,
            track=DataTrack.OPTIONS_SYNTHETIC.value,
            cash=min(cash, 5_000),
            quick=True if quick else False,
            top=6,
            multi_lock=False,
            workers=workers,
            out_dir=root / "options_rank",
        )

    meta = None
    if not skip_meta and not quick:
        meta = run_meta(out_dir=root / "meta")

    summary = {
        "phase": "all",
        "run_dir": str(root.relative_to(ROOT)),
        "equity_promote": equity_rank.get("promote"),
        "equity_loop_best": (equity_loop.get("generations") or [{}])[-1:],
        "options_top": [r.get("id") for r in (options_rank or {}).get("ranking", [])[:5]],
        "meta_ok": bool((meta or {}).get("meta", {}).get("ok")),
        "track": "multi",
        "cash": cash,
        "ranking": equity_rank.get("ranking") or [],
        "honesty": {
            "equity_may_promote": True,
            "options_research_only": True,
            "gex_not_in_pipeline": True,
        },
    }
    write_state(root / "STATE.json", summary)
    write_leaderboard(root / "LEADERBOARD.md", {**summary, "family": family})
    print(f"[evolve] ALL complete → {root}", flush=True)
    return summary
