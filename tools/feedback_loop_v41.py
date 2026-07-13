#!/usr/bin/env python3
"""Feedback loop: grid-search v41_ensemble_feedback perf_weighted variants.

Searches base-model combinations, perf_lookback, perf_temperature, and
perf_forward. Reuses backtest artifacts when a variant has already been run.

Usage:
    .venv/bin/python tools/feedback_loop_v41.py --cash 1000 --quick
    .venv/bin/python tools/feedback_loop_v41.py --cash 1000 --workers 1
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dynamic_model_rank as dmr

ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
V41_DIR = MODELS_ROOT / "v41_ensemble_feedback"

CODES = [
    "TSLA.US",
    "MU.US",
    "SPY.US",
    "IONQ.US",
    "APLD.US",
    "XLP.US",
    "QQQ.US",
]

START = "2024-08-01"
END = "2026-07-11"
TAG = "v41_perf_grid"

OUT = ROOT / "runs" / "feedback_loop_v41"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(parts: list[str]) -> str:
    return "_".join(p.replace(".", "p").replace("[", "").replace("]", "").replace(" ", "_") for p in parts)


def _copy_signal_engine(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "signal_engine.py", dst_dir / "signal_engine.py")


def _make_variant_model(
    variant_id: str,
    hunt_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Create a temp src_dir with a patched hunt_config for one variant."""
    tmp = Path(tempfile.mkdtemp(prefix=f"v41_{variant_id}_", dir=OUT))
    _copy_signal_engine(V41_DIR, tmp)

    base_hunt = json.loads((V41_DIR / "hunt_config.json").read_text())
    base_hunt.update(hunt_overrides)
    (tmp / "hunt_config.json").write_text(json.dumps(base_hunt, indent=2))

    return {
        "id": variant_id,
        "src_dir": tmp,
        "model_dir": V41_DIR,
        "interval": "1H",
        "has_hunt": True,
    }


def _run_model(model: dict[str, Any], cash: float, tag: str, source: str = "yfinance", interval: str | None = None) -> dict[str, Any]:
    return dmr.run_one(
        model,
        mode="daily",
        codes=CODES,
        start=START,
        end=END,
        tag=tag or TAG,
        force_1d=False,
        reuse=True,
        cash=cash,
        source=source,
        interval=interval,
    )


def _fmt(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"{row['id']:48} FAIL {row['error'][:80]}"
    return (
        f"{row['id']:48} ret={row['ret']*100:7.1f}% "
        f"dd={abs(row['dd'])*100:6.1f}% "
        f"sharpe={row['sharpe']:5.2f} "
        f"n={row['n']:3d} wr={row['wr']*100:4.0f}% "
        f"final=${row['final_at_cash']:>10,.2f}"
    )


def _variant_id(overrides: dict[str, Any]) -> str:
    mode = overrides.get("mode", "perf_weighted")
    if mode == "perf_weighted":
        base = "v41_perf"
    elif mode == "sgd_binary":
        base = "v41_sgdb"
    elif mode == "sgd_proba":
        base = "v41_sgdp"
    elif mode == "sgd_regression":
        base = "v41_sgr"
    else:
        base = f"v41_{mode}"
    models = overrides["base_models"]
    models_short = []
    for m in models:
        if m == "v39b_live_adapt":
            models_short.append("b39b")
        elif m == "v39d_confluence":
            models_short.append("b39d")
        elif m == "v39b_live_adapt_tight_stop_all":
            models_short.append("tsb")
        elif m == "v39d_confluence_tight_stop_all":
            models_short.append("tsd")
        elif m == "v12_regime_router":
            models_short.append("v12")
        elif m == "v42_trend_breakout":
            models_short.append("v42")
        elif m == "v44_true_levels":
            models_short.append("v44")
        else:
            models_short.append(m)
    base += "_" + "".join(models_short)
    if mode == "perf_weighted":
        base += f"_l{overrides['perf_lookback']}"
        t = overrides["perf_temperature"]
        base += f"_t{t:g}".replace(".", "p")
        if overrides.get("perf_forward", 1) != 1:
            base += f"_f{overrides['perf_forward']}"
        if overrides.get("perf_min_weight", 0.0) > 0.0:
            base += f"_mw{overrides['perf_min_weight']}"
        if overrides.get("perf_metric", "raw_return") != "raw_return":
            base += f"_m{overrides['perf_metric'][:3]}"
    else:
        base += f"_lr{overrides.get('learning_rate', 0.02):.3f}".replace(".", "p")
        base += f"_w{overrides.get('warmup', 80)}"
        base += f"_fb{overrides.get('forward_bars', 3)}"
    return base


def build_variants(quick: bool, focused: bool = False) -> list[dict[str, Any]]:
    if quick:
        param_sets = [
            {"base_models": ["v39b_live_adapt", "v39d_confluence"], "perf_lookback": 60, "perf_temperature": 0.5, "perf_forward": 1},
            {"base_models": ["v39b_live_adapt_tight_stop_all", "v39d_confluence"], "perf_lookback": 60, "perf_temperature": 0.5, "perf_forward": 1},
            {"base_models": ["v39b_live_adapt_tight_stop_all", "v44_true_levels"], "perf_lookback": 60, "perf_temperature": 0.5, "perf_forward": 1},
            {"base_models": ["v39d_confluence", "v44_true_levels"], "perf_lookback": 60, "perf_temperature": 0.5, "perf_forward": 1},
            {"base_models": ["v39d_confluence", "v44_true_levels"], "perf_lookback": 90, "perf_temperature": 0.5, "perf_forward": 1},
            {"base_models": ["v39d_confluence", "v44_true_levels"], "perf_lookback": 90, "perf_temperature": 0.5, "perf_forward": 3, "perf_metric": "raw_return"},
        ]
    elif focused:
        model_combos = [
            ["v39b_live_adapt", "v39d_confluence"],
            ["v39b_live_adapt_tight_stop_all", "v39d_confluence"],
            ["v39b_live_adapt_tight_stop_all", "v39d_confluence_tight_stop_all"],
            ["v39d_confluence"],
        ]
        lookbacks = [60, 90]
        temperatures = [0.5, 1.0]
        forwards = [1, 3]
        min_weights = [0.0, 0.1]

        param_sets = []
        for models in model_combos:
            for lookback in lookbacks:
                for temp in temperatures:
                    for forward in forwards:
                        for min_weight in min_weights:
                            param_sets.append({
                                "base_models": models,
                                "perf_lookback": lookback,
                                "perf_temperature": temp,
                                "perf_forward": forward,
                                "perf_min_weight": min_weight,
                            })
    else:
        model_combos = [
            ["v39b_live_adapt", "v39d_confluence"],
            ["v39b_live_adapt_tight_stop_all", "v39d_confluence"],
            ["v39b_live_adapt_tight_stop_all", "v39d_confluence_tight_stop_all"],
            ["v39d_confluence"],
            ["v39b_live_adapt"],
            ["v39b_live_adapt", "v39d_confluence", "v12_regime_router"],
            ["v39b_live_adapt_tight_stop_all", "v39d_confluence", "v12_regime_router"],
        ]
        lookbacks = [30, 60, 90, 120]
        temperatures = [0.25, 0.5, 1.0, 2.0]
        forwards = [1, 3]
        min_weights = [0.0, 0.1]

        param_sets = []
        for models in model_combos:
            for lookback in lookbacks:
                for temp in temperatures:
                    for forward in forwards:
                        for min_weight in min_weights:
                            param_sets.append({
                                "base_models": models,
                                "perf_lookback": lookback,
                                "perf_temperature": temp,
                                "perf_forward": forward,
                                "perf_min_weight": min_weight,
                            })

    variants = []
    for overrides in param_sets:
        variants.append(_make_variant_model(_variant_id(overrides), overrides))
    return variants


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cash", type=float, default=1000.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--quick", action="store_true", help="Run focused 6-variant quick sweep")
    parser.add_argument("--focused", action="store_true", help="Run medium 42-variant focused sweep")
    parser.add_argument("--tag", type=str, default=TAG, help="Run tag for cache grouping")
    parser.add_argument("--source", type=str, default="yfinance", help="Data source: local or yfinance")
    parser.add_argument("--interval", type=str, default=None, help="Data interval (e.g. 1H)")
    args = parser.parse_args()

    cash = args.cash
    OUT.mkdir(parents=True, exist_ok=True)

    if not V41_DIR.exists():
        raise FileNotFoundError(f"v41 model not found: {V41_DIR}")

    # Discover teacher baselines for comparison.
    baseline_models = dmr.discover_models(only=["v39b_live_adapt", "v39d_confluence", "v39b_live_adapt_tight_stop_all", "v44_true_levels"])
    if not baseline_models:
        raise FileNotFoundError("baseline models not found")

    # Existing v41 as configured.
    v41_models = dmr.discover_models(only=["v41_ensemble_feedback"])
    if not v41_models:
        raise FileNotFoundError("v41_ensemble_feedback not found")
    v41_base = v41_models[0]

    variants = build_variants(args.quick, args.focused)

    tag = args.tag
    if args.source != "yfinance":
        tag = f"{tag}_{args.source}"

    print(f"[v41-feedback] cash=${cash:,.0f} source={args.source} interval={args.interval or 'default'} codes={len(CODES)} variants={len(variants)}", flush=True)
    rows: list[dict[str, Any]] = []

    # Teacher baselines.
    for m in baseline_models:
        print(f"[v41-feedback] baseline {m['id']}", flush=True)
        r = _run_model(m, cash, tag, source=args.source, interval=args.interval)
        print(f"  {_fmt(r)}", flush=True)
        rows.append(r)

    # Current v41 config.
    print("[v41-feedback] current v41_ensemble_feedback", flush=True)
    r = _run_model(v41_base, cash, tag, source=args.source, interval=args.interval)
    print(f"  {_fmt(r)}", flush=True)
    rows.append(r)

    # Variants.
    for m in variants:
        print(f"[v41-feedback] variant {m['id']}", flush=True)
        r = _run_model(m, cash, tag, source=args.source, interval=args.interval)
        print(f"  {_fmt(r)}", flush=True)
        rows.append(r)

    # Rank by risk-adjusted score (ret/dd) with small-n penalty.
    ranked = []
    for r in rows:
        if r.get("error") or r.get("n", 0) == 0:
            score = -9.0
        else:
            ret = float(r["ret"])
            dd = max(abs(float(r["dd"])), 0.02)
            sh = float(r["sharpe"])
            n = int(r["n"])
            n_pen = 0.0 if n >= 10 else 0.25
            score = (ret / dd) + 0.15 * min(sh, 3.0) - n_pen
        r["score"] = score
        ranked.append(r)

    ranked.sort(key=lambda x: x["score"], reverse=True)

    state = {
        "timestamp": _now(),
        "cash": cash,
        "source": args.source,
        "interval": args.interval,
        "codes": CODES,
        "start": START,
        "end": END,
        "ranking": ranked,
        "best": ranked[0]["id"] if ranked else None,
    }

    (OUT / "STATE.json").write_text(json.dumps(state, indent=2, default=str))

    lines = [
        "# v41 ensemble feedback leaderboard\n",
        f"- cash: ${cash:,.0f}\n",
        f"- source: {args.source}\n",
        f"- interval: {args.interval or 'default'}\n",
        f"- period: {START} to {END}\n",
        f"- variants: {len(variants)}\n",
        ""
    ]
    lines.append("| model | ret | dd | sharpe | n | wr | final | score |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in ranked:
        if r.get("error"):
            lines.append(f"| {r['id']} | FAIL | {r.get('error','')[:40]} | | | | | |")
        else:
            lines.append(
                f"| {r['id']} | {r['ret']*100:6.1f}% | {abs(r['dd'])*100:5.1f}% | "
                f"{r['sharpe']:4.2f} | {r['n']} | {r['wr']*100:3.0f}% | "
                f"${r['final_at_cash']:,.2f} | {r['score']:6.2f} |"
            )
    (OUT / "LEADERBOARD.md").write_text("\n".join(lines))

    print(f"\n[v41-feedback] best: {state['best']}", flush=True)
    print(f"[v41-feedback] leaderboard: {OUT / 'LEADERBOARD.md'}", flush=True)


if __name__ == "__main__":
    main()
