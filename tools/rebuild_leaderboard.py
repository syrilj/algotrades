#!/usr/bin/env python3
"""Rebuild Leaderboard — run backtests and write results.json for missing models.

Usage:
  .venv/bin/python tools/rebuild_leaderboard.py --all
  .venv/bin/python tools/rebuild_leaderboard.py --models v50_high_win_rate,v60_microstructure
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr
from evolve.cache import cache_key

MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
DEFAULT_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
START = "2024-08-01"
END = "2026-07-11"
CASH = 1_000_000


def get_model_symbols(model_id: str) -> list[str]:
    # Check DESK_ROUTING.json first
    routing_path = MODELS_ROOT / "DESK_ROUTING.json"
    if routing_path.exists():
        try:
            data = json.loads(routing_path.read_text())
            by_symbol = data.get("by_symbol", {})
            for sym, info in by_symbol.items():
                if info.get("model") == model_id:
                    return [sym]
        except Exception:
            pass

    # Check v65_spec_xxx
    if model_id.startswith("v65_spec_"):
        ticker = model_id.replace("v65_spec_", "").upper()
        if ticker == "GOOG":
            ticker = "GOOG.US"
        else:
            ticker = f"{ticker}.US"
        return [ticker]

    if model_id == "v64_crwv_bounce":
        return ["CRWV.US"]

    return DEFAULT_BAG


def process_model(model: dict[str, Any], cash: float, dry_run: bool = False) -> bool:
    mid = model["id"]
    model_dir = Path(model["model_dir"])
    results_path = model_dir / "results.json"

    # Determine symbols and mode
    from model_registry import engine_kind
    codes = get_model_symbols(mid)
    kind = engine_kind(mid)
    mode = "options" if kind == "options" else "daily"

    print(f"\n[rebuild] ---> Model: {mid} | Mode: {mode} | Symbols: {codes}", flush=True)

    if dry_run:
        print(f"[rebuild] [DRY RUN] Would backtest {mid} on {codes}", flush=True)
        return True

    try:
        # Run backtest
        print(f"[rebuild] Running backtest for {mid}...", flush=True)
        row = dmr.run_one(
            model,
            mode=mode,
            codes=codes,
            start=START,
            end=END,
            tag="leaderboard_rebuild",
            force_1d=False,
            reuse=True,
            cash=cash,
            source="local",
            interval="1H"
        )

        if row.get("error"):
            print(f"[rebuild] ERROR for {mid}: {row['error']}", flush=True)
            return False

        # Read run_card.json to get detailed metrics (like profit_factor)
        cash_tag = f"c{int(cash)}" if cash >= 1000 else f"c{cash:g}"
        run_dir = ROOT / "runs" / "poc_va_dynamic_rank" / "runs" / mid / f"leaderboard_rebuild__{mode}__{cash_tag}"
        run_card_path = run_dir / "run_card.json"

        if not run_card_path.exists():
            # Fallback to returned row metrics if run_card.json doesn't exist
            print(f"[rebuild] Warning: run_card.json not found for {mid}. Using fallback metrics.", flush=True)
            metrics = {
                "total_return": row.get("ret"),
                "max_drawdown": row.get("dd"),
                "sharpe": row.get("sharpe"),
                "profit_factor": 1.0,  # Default fallback
                "trade_count": row.get("n"),
                "win_rate": row.get("wr"),
                "final_value": row.get("final")
            }
        else:
            card = json.loads(run_card_path.read_text())
            card_metrics = card.get("metrics") or {}
            metrics = {
                "total_return": card_metrics.get("total_return", row.get("ret")),
                "max_drawdown": card_metrics.get("max_drawdown", row.get("dd")),
                "sharpe": card_metrics.get("sharpe", row.get("sharpe")),
                "profit_factor": card_metrics.get("profit_factor", 1.0),
                "trade_count": card_metrics.get("trade_count", row.get("n")),
                "win_rate": card_metrics.get("win_rate", row.get("wr")),
                "final_value": card_metrics.get("final_value", row.get("final"))
            }

        # Structure results.json exactly as expected by model_registry
        results = {
            "portfolio": metrics,
            "generated_utc": row.get("generated_at", ""),
            "codes": codes,
            "start": START,
            "end": END
        }

        results_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"[rebuild] Wrote results.json for {mid}: Sharpe={metrics['sharpe']:.2f}, WR={metrics['win_rate']*100:.1f}%, Return={metrics['total_return']*100:.1f}%", flush=True)
        return True

    except Exception as e:
        print(f"[rebuild] Exception running {mid}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Rebuild all models missing results.json")
    group.add_argument("--models", help="Comma-separated list of specific model IDs to run")
    ap.add_argument("--cash", type=float, default=CASH, help="Starting cash for backtests")
    ap.add_argument("--workers", type=int, default=2, help="Number of concurrent workers")
    ap.add_argument("--dry-run", action="store_true", help="Only list models that would be run")
    args = ap.parse_args()

    os.environ.setdefault("VIBE_TRADING_DATA_CACHE", "1")
    os.environ.setdefault("VIBE_TRADING_DATA_CACHE_ROOT", str(ROOT / "data_cache"))

    # Discover models
    all_models = dmr.discover_models()
    by_id = {m["id"]: m for m in all_models}

    # Filter to target models
    target_models = []
    if args.all:
        for mid, m in by_id.items():
            results_path = Path(m["model_dir"]) / "results.json"
            if not results_path.exists():
                target_models.append(m)
    else:
        m_list = [x.strip() for x in args.models.split(",") if x.strip()]
        for mid in m_list:
            if mid not in by_id:
                print(f"Error: Model '{mid}' not found in discovered models.")
                return 1
            target_models.append(by_id[mid])

    if not target_models:
        print("No models to process.")
        return 0

    print(f"[rebuild] Found {len(target_models)} models to process.", flush=True)

    # Run processing
    success_count = 0
    if args.workers > 1 and len(target_models) > 1 and not args.dry_run:
        print(f"[rebuild] Processing in parallel with {args.workers} workers...", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(process_model, m, args.cash, args.dry_run) for m in target_models]
            for f in futures:
                if f.result():
                    success_count += 1
    else:
        for m in target_models:
            if process_model(m, args.cash, args.dry_run):
                success_count += 1

    print(f"\n[rebuild] Done! Successfully rebuilt {success_count}/{len(target_models)} models.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
