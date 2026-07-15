"""Evolve loop core for direction-equity strategies."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from backtest.metrics import calc_bars_per_year
from tools import snapshot_data
from tools.direction_report import build_direction_report, _md_report as _direction_md
from tools.dynamic_model_rank import OUT as DMR_OUT, run_one as dmr_run_one
from tools.evolve import audit_gen, costs, folds, validate_run

ROOT = Path(__file__).resolve().parents[2]
EVOLVE_DIR = ROOT / "runs" / "evolve_direction_v1"
TRIALS_PATH = ROOT / "models" / "_shared" / "trials.jsonl"


def _model_id(model_dir: Path) -> str:
    return model_dir.name


def _build_model(model_dir: Path) -> dict[str, Any]:
    src_dir = model_dir
    return {
        "id": model_dir.name,
        "model_dir": model_dir,
        "src_dir": src_dir,
        "modes": ["daily"],
        "interval": "1H",
        "has_hunt": False,
    }


def _codes_for_model(model_dir: Path) -> list[str]:
    cfg = model_dir / "config.json"
    if cfg.exists():
        try:
            return json.loads(cfg.read_text()).get("codes", [])
        except Exception:
            pass
    return ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]


def _load_cache_bars(codes: list[str], interval: str, start: str, end: str) -> dict[str, pd.DataFrame]:
    """Load OHLCV bars for the requested interval and window."""
    cache_dir = ROOT / "data_cache" / interval.lower()
    bars = {}
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    for code in codes:
        symbol = code.lstrip("^").replace(".US", "")
        p = cache_dir / f"{symbol}.parquet"
        if not p.exists():
            p = cache_dir / f"{symbol}.US.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if not df.empty:
            bars[code] = df[["open", "high", "low", "close", "volume"]].astype(float)
    return bars


def _bars_per_year(interval: str) -> int:
    return calc_bars_per_year(interval, "yfinance")


def _set_bridge(interval: str) -> Path:
    return snapshot_data.use_bridge(interval)


def _combined_dir(model_id: str, variant_id: str) -> Path:
    return DMR_OUT / "runs" / model_id / f"{variant_id}__combined"


def _write_combined_artifacts(run_dir: Path, trades: pd.DataFrame, equity: pd.DataFrame, cfg: dict) -> None:
    """Write a synthetic combined run_dir with trades/equity/config."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))

    art = run_dir / "artifacts"
    art.mkdir(parents=True, exist_ok=True)

    # trades in two-row-per-trade format
    trade_rows = []
    for _, t in trades.iterrows():
        entry_ts = t["entry_time"]
        exit_ts = t["exit_time"]
        side = "buy" if t["direction"] == 1 else "sell"
        trade_rows.append({
            "timestamp": str(entry_ts.date()) if hasattr(entry_ts, "date") else str(entry_ts),
            "code": t["symbol"],
            "side": side,
            "price": round(t["entry_price"], 4),
            "qty": round(t["size"], 6),
            "reason": "signal",
            "pnl": 0.0,
            "holding_days": 0,
            "return_pct": 0.0,
        })
        trade_rows.append({
            "timestamp": str(exit_ts.date()) if hasattr(exit_ts, "date") else str(exit_ts),
            "code": t["symbol"],
            "side": "sell" if t["direction"] == 1 else "buy",
            "price": round(t["exit_price"], 4),
            "qty": round(t["size"], 6),
            "reason": t["exit_reason"],
            "pnl": round(t["pnl"], 4),
            "holding_days": t["holding_days"],
            "return_pct": round(t["pnl_pct"], 2),
        })
    cols = ["timestamp", "code", "side", "price", "qty", "reason", "pnl", "holding_days", "return_pct"]
    pd.DataFrame(trade_rows, columns=cols).to_csv(art / "trades.csv", index=False)

    eq = equity.copy()
    port_ret = eq.pct_change().fillna(0.0)
    peak = eq.cummax()
    dd = (eq - peak) / peak.replace(0, 1)
    eq_df = pd.DataFrame({
        "ret": port_ret,
        "equity": eq,
        "drawdown": dd,
        "benchmark_equity": 0.0,
        "active_ret": port_ret,
    }, index=eq.index)
    eq_df.index.name = "timestamp"
    eq_df.to_csv(art / "equity.csv")


def _perturb_fitness(folds_data: list[tuple[pd.DataFrame, pd.Series, int]], base_slippage: float, cash: float) -> list[float]:
    """Fitness at slippage +/- 20%."""
    ratios = [0.8, 1.0, 1.2]
    fitnesses = []
    for r in ratios:
        s = base_slippage * r
        per_fold_ms = []
        for trades, equity, bpy in folds_data:
            adj_trades = costs.adjust_trades_for_slippage(trades, s)
            adj_equity = costs.adjust_equity_for_slippage(equity, trades, s, cash=cash)
            m = folds.fold_metrics(adj_trades, adj_equity, bpy)
            per_fold_ms.append(m)
        fitnesses.append(folds.fold_fitness(per_fold_ms))
    return fitnesses


def run_candidate(
    model: dict[str, Any],
    *,
    codes: list[str] | None = None,
    interval: str = "1H",
    slippage: float = costs.SLIPPAGE_BASE,
    cash: float = 1_000_000,
    campaign_id: str = "evolve",
    gen: int = 0,
    variant_id: str = "v0",
    parent: str = "",
    mutations: list[dict[str, Any]] | None = None,
    run_fn: Callable = dmr_run_one,
    fold_set: list[dict[str, Any]] | None = None,
    extra_cfg: dict[str, Any] | None = None,
    probe_slippage: bool = True,
) -> dict[str, Any]:
    """Run a single candidate across folds; return a candidate dict."""
    model_id = model["id"]
    if codes is None:
        codes = _codes_for_model(model["model_dir"])
    if fold_set is None:
        fold_set = folds.FOLDS_1H
    if extra_cfg is None:
        extra_cfg = {}
    extra_cfg = {**extra_cfg, "slippage_us": slippage}

    bpy = _bars_per_year(interval)
    all_fold_ms: list[dict[str, Any]] = []
    folds_data: list[tuple[pd.DataFrame, pd.Series, int]] = []
    fold_results: dict[str, Any] = {}
    oos_start = None
    oos_end = None
    base_run_dir = None

    for fold in fold_set:
        tag = f"{campaign_id}_g{gen}_{variant_id}_{fold['name']}"
        out = run_fn(
            model,
            mode="daily",
            codes=codes,
            start=fold["warmup_start"],
            end=fold["oos_end"],
            tag=tag,
            force_1d=False,
            cash=cash,
            source="local",
            interval=interval,
            extra_cfg=extra_cfg,
            reuse=False,
        )
        if out.get("error"):
            raise RuntimeError(f"fold {fold['name']} failed: {out['error']}")

        run_dir = ROOT / out["path"]
        if base_run_dir is None:
            base_run_dir = run_dir
            if oos_start is None:
                oos_start = fold["oos_start"]
            oos_end = fold["oos_end"]

        # probe slippage on first fold
        if probe_slippage and fold == fold_set[0]:
            costs.probe_slippage_applied(run_dir, expected_slippage=slippage, n_probe=3)

        trades, equity = folds.slice_oos(run_dir, fold["oos_start"], fold["oos_end"])
        m = folds.fold_metrics(trades, equity, bpy)
        all_fold_ms.append(m)
        fold_results[fold["name"]] = m
        folds_data.append((trades.copy(), equity.copy(), bpy))

    fitness = folds.fold_fitness(all_fold_ms)

    # Combine fold equity curves and trades
    combined_trades = pd.concat([t for t, _, _ in folds_data], ignore_index=True)
    combined_trades["entry_time"] = pd.to_datetime(combined_trades["entry_time"])
    combined_trades["exit_time"] = pd.to_datetime(combined_trades["exit_time"])

    running = 1.0
    equity_parts = []
    for _, equity, _ in folds_data:
        scaled = equity * running
        running = float(scaled.iloc[-1]) if not scaled.empty else running
        equity_parts.append(scaled)
    combined_equity = pd.concat(equity_parts).sort_index()
    if not combined_equity.empty:
        combined_equity = combined_equity / combined_equity.iloc[0]

    combined_dir = _combined_dir(model_id, variant_id)
    if combined_dir.exists():
        shutil.rmtree(combined_dir)
    cfg = {
        "source": "local",
        "codes": codes,
        "start_date": str(oos_start or combined_equity.index.min().date()),
        "end_date": str(oos_end or combined_equity.index.max().date()),
        "initial_cash": cash,
        "commission": 0.001,
        "engine": "daily",
        "interval": interval,
        "strategy": {"model_version": model_id, "variant": variant_id, "parent": parent},
    }
    _write_combined_artifacts(combined_dir, combined_trades, combined_equity, cfg)

    validation = validate_run.run_package_validation(combined_dir)

    bars = _load_cache_bars(codes, interval, str(oos_start or "2025-01-01"), str(oos_end or "2026-07-11"))
    direction_report = build_direction_report(combined_dir / "artifacts" / "trades.csv", bars)
    (combined_dir / "DIRECTION.json").write_text(json.dumps(direction_report, indent=2, default=float))
    (combined_dir / "DIRECTION.md").write_text(_direction_md(direction_report))

    perturb = _perturb_fitness(folds_data, slippage, cash)

    candidate = {
        "id": variant_id,
        "variant_id": variant_id,
        "gen": gen,
        "parent": parent,
        "campaign_id": campaign_id,
        "model_id": model_id,
        "mutations": mutations or [],
        "codes": codes,
        "interval": interval,
        "slippage": slippage,
        "cash": cash,
        "fold_metrics": fold_results,
        "fold_fitness": [folds.fold_utility(m) for m in all_fold_ms],
        "fitness": fitness,
        "trades": combined_trades,
        "equity": combined_equity,
        "bars_per_year": bpy,
        "validation": validation,
        "direction_report": direction_report,
        "perturb_fitness": perturb,
        "run_dir": str(combined_dir),
        "model_dir": str(model["model_dir"]),
        "lockbox": {},
        "track_b": {},
    }
    return candidate


def run_track_b(
    candidate: dict[str, Any],
    model: dict[str, Any],
    *,
    run_fn: Callable = dmr_run_one,
    extra_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Track B (1D calendar-year folds) and return pooled metrics.

    Folds that fail (e.g. symbols missing early history) are skipped.
    """
    tb_folds = folds.FOLDS_1D_TRACKB
    tb_bpy = _bars_per_year("1D")
    all_fold_ms: list[dict[str, Any]] = []
    folds_data: list[tuple[pd.DataFrame, pd.Series, int]] = []
    fold_results: dict[str, Any] = {}

    for fold in tb_folds:
        tag = f"{candidate['campaign_id']}_g{candidate['gen']}_{candidate['id']}_trackB_{fold['name']}"
        try:
            out = run_fn(
                model,
                mode="daily",
                codes=candidate["codes"],
                start=fold["warmup_start"],
                end=fold["oos_end"],
                tag=tag,
                force_1d=False,
                cash=candidate["cash"],
                source="local",
                interval="1D",
                extra_cfg={**(extra_cfg or {}), "slippage_us": candidate["slippage"]},
                reuse=False,
            )
        except Exception as exc:
            print(f"[track_b] {fold['name']} skipped: {exc}")
            continue
        if out.get("error"):
            print(f"[track_b] {fold['name']} skipped: {out['error']}")
            continue
        run_dir = ROOT / out["path"]
        trades, equity = folds.slice_oos(run_dir, fold["oos_start"], fold["oos_end"])
        m = folds.fold_metrics(trades, equity, tb_bpy)
        all_fold_ms.append(m)
        fold_results[fold["name"]] = m
        folds_data.append((trades.copy(), equity.copy(), tb_bpy))

    if not folds_data:
        return {"pooled_metrics": {}, "fold_metrics": {}}

    combined_trades = pd.concat([t for t, _, _ in folds_data], ignore_index=True)
    combined_trades["entry_time"] = pd.to_datetime(combined_trades["entry_time"])
    combined_trades["exit_time"] = pd.to_datetime(combined_trades["exit_time"])

    running = 1.0
    equity_parts = []
    for _, equity, _ in folds_data:
        scaled = equity * running
        running = float(scaled.iloc[-1]) if not scaled.empty else running
        equity_parts.append(scaled)
    combined_equity = pd.concat(equity_parts).sort_index()
    if not combined_equity.empty:
        combined_equity = combined_equity / combined_equity.iloc[0]

    pooled = folds.fold_metrics(combined_trades, combined_equity, tb_bpy)
    return {"pooled_metrics": pooled, "fold_metrics": fold_results}


def run_lockbox_and_audit(
    candidate: dict[str, Any],
    model: dict[str, Any],
    *,
    run_fn: Callable = dmr_run_one,
    extra_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run the lockbox fold and write audit."""
    lockbox = folds.LOCKBOX
    model_id = model["id"]
    variant_id = candidate["id"]
    tag = f"{candidate['campaign_id']}_g{candidate['gen']}_{variant_id}_LOCKBOX"
    out = run_fn(
        model,
        mode="daily",
        codes=candidate["codes"],
        start=lockbox["warmup_start"],
        end=lockbox["oos_end"],
        tag=tag,
        force_1d=False,
        cash=candidate["cash"],
        source="local",
        interval=candidate["interval"],
        extra_cfg={**(extra_cfg or {}), "slippage_us": candidate["slippage"]},
        reuse=False,
    )
    if out.get("error"):
        raise RuntimeError(f"lockbox failed: {out['error']}")
    run_dir = ROOT / out["path"]
    trades, equity = folds.slice_oos(run_dir, lockbox["oos_start"], lockbox["oos_end"])
    m = folds.fold_metrics(trades, equity, candidate["bars_per_year"])
    candidate["lockbox"] = {"fold_metrics": m, "fitness": folds.fold_utility(m)}

    if not candidate.get("track_b") or not candidate["track_b"].get("pooled_metrics"):
        candidate["track_b"] = run_track_b(candidate, model, run_fn=run_fn, extra_cfg=extra_cfg)

    out_path = Path(candidate["run_dir"]) / "AUDIT.json"
    audit_path = audit_gen.write_audit(candidate, None, out_path)
    return candidate, audit_path


def write_trial(candidate: dict[str, Any]) -> Path:
    """Append a candidate summary to models/_shared/trials.jsonl."""
    TRIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "campaign_id": candidate.get("campaign_id", ""),
        "gen": candidate.get("gen", 0),
        "variant_id": candidate.get("variant_id", candidate.get("id", "")),
        "parent": candidate.get("parent", ""),
        "fitness": candidate.get("fitness", 0.0),
        "fold_metrics": candidate.get("fold_metrics", {}),
        "lockbox_fitness": candidate.get("lockbox", {}).get("fitness", 0.0),
    }
    with TRIALS_PATH.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return TRIALS_PATH


def run_phase0(model_dir: Path | None = None, cash: float = 1_000_000) -> dict[str, Any]:
    """Run the v39b baseline through the full Phase 0 pipeline."""
    if model_dir is None:
        model_dir = ROOT / "models" / "poc_va_macdha" / "v39b_live_adapt"
    model = _build_model(model_dir)
    _set_bridge("1h")
    candidate = run_candidate(
        model,
        cash=cash,
        campaign_id="evolve_phase0",
        gen=0,
        variant_id="v39b_baseline",
        parent="",
        fold_set=folds.FOLDS_1H,
    )
    candidate["track_b"] = run_track_b(candidate, model)
    candidate, audit_path = run_lockbox_and_audit(candidate, model)
    try:
        candidate["audit"] = json.loads(audit_path.read_text())
    except Exception:
        candidate["audit"] = {}
    write_trial(candidate)
    return candidate, audit_path


def run_campaign(
    base_model_dir: Path,
    *,
    generations: int = 2,
    cash: float = 1_000_000,
    campaign_id: str = "evolve_campaign",
    menu: list[dict[str, Any]] | None = None,
    memory_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Run fold-ranked generations with persistent failure-guided mutations."""
    from tools.evolve import mutations as mut
    from tools.evolve.model_feedback import (
        DEFAULT_MEMORY_PATH,
        load_memory,
        prioritize_mutation_menu,
        rank_model_runs,
        save_memory,
        update_memory,
    )

    base_model = _build_model(base_model_dir)
    _set_bridge("1h")

    base_menu = menu or mut.COMBINED_MUTATION_MENU
    feedback_path = memory_path or DEFAULT_MEMORY_PATH
    memory = load_memory(feedback_path)
    guided_menu = prioritize_mutation_menu(
        base_menu,
        [{"model_id": base_model["id"], "failures": []}],
        memory,
    )
    variants = mut.spawn_direction_variants(base_model, menu=guided_menu)
    results: list[dict[str, Any]] = []

    for gen in range(generations):
        gen_results: list[dict[str, Any]] = []
        failed_rows: list[dict[str, Any]] = []
        for variant in variants:
            variant_id = variant["id"]
            parent = variant.get("parent", base_model["id"])
            extra = variant.get("extra_cfg", {})
            try:
                variant_model = _build_model(Path(variant["model_dir"]))
                candidate = run_candidate(
                    variant_model,
                    codes=variant["codes"],
                    slippage=extra.get("slippage_us", costs.SLIPPAGE_BASE),
                    cash=cash,
                    campaign_id=campaign_id,
                    gen=gen,
                    variant_id=variant_id,
                    parent=parent,
                    mutations=variant.get("mutations", []),
                    extra_cfg=extra,
                )
                candidate["mutation_name"] = variant.get("mutation_name")
                candidate["mutation_targets"] = variant.get("mutation_targets", [])
                candidate["feedback_priority"] = variant.get("feedback_priority")
                candidate["extra_cfg"] = extra
                gen_results.append(candidate)
                write_trial(candidate)
            except Exception as exc:
                print(f"  FAIL {variant_id}: {exc}", flush=True)
                failed_rows.append(
                    {
                        "id": variant_id,
                        "tag": f"generation_{gen}",
                        "error": str(exc)[:200],
                        "n": 0,
                        "ret": 0.0,
                        "dd": 0.0,
                        "sharpe": 0.0,
                        "parent": parent,
                        "mutation_name": variant.get("mutation_name"),
                        "mutation_targets": variant.get("mutation_targets", []),
                    }
                )

        if not gen_results:
            if failed_rows:
                failed_rankings = rank_model_runs(
                    {row["id"]: [row] for row in failed_rows},
                    expected_runs=len(folds.FOLDS_1H),
                )
                memory = update_memory(memory, failed_rankings, generation=gen)
                save_memory(memory, feedback_path)
            break

        # Rank each candidate across identical OOS folds.  This adds explicit
        # stability, confidence, and failure diagnostics to fold_fitness.
        by_candidate = {candidate["id"]: candidate for candidate in gen_results}
        fold_runs: dict[str, list[dict[str, Any]]] = {}
        for candidate in gen_results:
            fold_runs[candidate["id"]] = [
                {
                    **metrics,
                    "id": candidate["id"],
                    "tag": fold_name,
                    "utility": folds.fold_utility(metrics),
                }
                for fold_name, metrics in candidate.get("fold_metrics", {}).items()
            ]
        for row in failed_rows:
            fold_runs[row["id"]] = [row]
        rankings = rank_model_runs(
            fold_runs,
            min_trades=40,
            expected_runs=len(folds.FOLDS_1H),
        )
        for row in rankings:
            candidate = by_candidate.get(row["id"])
            if candidate is None:
                failed = next((item for item in failed_rows if item["id"] == row["id"]), {})
                row.update(
                    {
                        "parent": failed.get("parent"),
                        "mutation_name": failed.get("mutation_name"),
                        "mutation_targets": failed.get("mutation_targets", []),
                    }
                )
                continue
            candidate["rank"] = row["rank"]
            candidate["rank_score"] = row["rank_score"]
            candidate["rank_confidence"] = row["rank_confidence"]
            candidate["failure_profile"] = row["failure_profile"]
            row.update(
                {
                    "parent": candidate.get("parent"),
                    "mutation_name": candidate.get("mutation_name"),
                    "mutation_targets": candidate.get("mutation_targets", []),
                }
            )

        control = next(
            (row for row in rankings if row.get("mutation_name") == "base" and row["id"] in by_candidate),
            None,
        )
        parent_scores = {base_model["id"]: float(control["rank_score"])} if control else {}
        memory = update_memory(memory, rankings, generation=gen, parent_scores=parent_scores)
        save_memory(memory, feedback_path)

        best_row = next(row for row in rankings if row["id"] in by_candidate)
        best = by_candidate[best_row["id"]]
        print(
            f"  RANK #{best_row['rank']} {best['id']} score={best_row['rank_score']:.3f} "
            f"confidence={best_row['rank_confidence']:.0%} "
            f"failures={best_row['failure_profile']['failure_tags']}",
            flush=True,
        )
        try:
            best_model = _build_model(Path(best["model_dir"]))
            run_lockbox_and_audit(best, best_model, extra_cfg=best.get("extra_cfg", {}))
            write_trial(best)
        except Exception as exc:
            print(f"  LOCKBOX/audit fail for {best['id']}: {exc}", flush=True)
        results.extend(gen_results)
        # Next generation targets recurring failures and mutations that have
        # produced positive score deltas, while preserving exploration.
        base_model = _build_model(Path(best["model_dir"]))
        guided_menu = prioritize_mutation_menu(
            base_menu,
            [row.get("failure_profile") or {} for row in rankings],
            memory,
        )
        variants = mut.spawn_direction_variants(base_model, menu=guided_menu)

    return results
