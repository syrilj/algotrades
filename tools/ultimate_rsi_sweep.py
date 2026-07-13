#!/usr/bin/env python3
"""Sweep the v45_ultimate_rsi model across timeframes and parameters.

Usage:
    .venv/bin/python tools/ultimate_rsi_sweep.py --quick
    .venv/bin/python tools/ultimate_rsi_sweep.py --grid
    .venv/bin/python tools/ultimate_rsi_sweep.py --source yfinance --cash 1000
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr
from evolve.cache import data_bundle_hash, env_versions  # noqa: E402

WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
START = "2024-08-01"
END = "2026-07-11"


def _safe_tag(label: str) -> str:
    return label.replace(" ", "_").replace(".", "_").replace("/", "_")


def _run(
    model: dict[str, Any],
    tag: str,
    cash: float,
    source: str,
    extra: dict[str, Any],
    fallback_source: str | None = "yfinance",
) -> dict[str, Any]:
    """Run one backtest with a given config, optionally falling back to yfinance."""
    row = dmr.run_one(
        model,
        mode="daily",
        codes=WINNER_BAG,
        start=START,
        end=END,
        tag=tag,
        cash=cash,
        force_1d=False,
        source=source,
        interval="1H",
        reuse=False,
        extra_cfg=extra,
    )
    if row.get("error") and fallback_source and source != fallback_source:
        print(f"    {tag} failed on {source}: {row.get('error')}. Retrying with {fallback_source}...")
        row = dmr.run_one(
            model,
            mode="daily",
            codes=WINNER_BAG,
            start=START,
            end=END,
            tag=f"{tag}__fb_{fallback_source}",
            cash=cash,
            force_1d=False,
            source=fallback_source,
            interval="1H",
            reuse=False,
            extra_cfg=extra,
        )
    return row


def _baseline_sweep(model: dict[str, Any], cash: float, source: str) -> list[dict[str, Any]]:
    """Run the baseline config across 1H, 2H, 4H signal timeframes."""
    print("\n======== ULTIMATE RSI BASELINE SWEEP (timeframes) ========", flush=True)
    rows: list[dict[str, Any]] = []
    for tf in [None, "2h", "4h"]:
        label = f"tf_{tf.lower() if tf else '1h'}"
        extra: dict[str, Any] = {"signal_tf": tf}
        tag = _safe_tag(label)
        row = _run(model, tag, cash, source, extra)
        rows.append(row)
        if not row.get("error"):
            print(
                f"  {label:12} ret={row['ret']*100:6.1f}% dd={row['dd']*100:5.1f}% "
                f"sh={row['sharpe']:4.2f} n={row['n']:3d} wr={row['wr']*100:3.0f}%"
            )
    return rows


def _param_grid(
    model: dict[str, Any], cash: float, source: str, best_tf: str | None
) -> list[dict[str, Any]]:
    """Staged grid over the best interval."""
    print(f"\n======== PARAMETER GRID on best_tf={best_tf or 'native 1H'} ========", flush=True)
    lengths = [14, 21]
    smooths = [14, 21]
    thresholds = [(80.0, 20.0), (70.0, 30.0)]
    smo1s = ["RMA", "EMA"]
    smo2s = ["EMA", "SMA"]

    rows: list[dict[str, Any]] = []
    for length, smooth, (ob, os), smo1, smo2 in itertools.product(
        lengths, smooths, thresholds, smo1s, smo2s
    ):
        extra = {
            "length": length,
            "smooth": smooth,
            "ob_value": ob,
            "os_value": os,
            "smo_type1": smo1,
            "smo_type2": smo2,
            "signal_tf": best_tf if best_tf else None,
        }
        label = f"tf_{best_tf or '1h'}_len{length}_sm{smooth}_ob{int(ob)}_os{int(os)}_{smo1}_{smo2}"
        tag = _safe_tag(label)
        row = _run(model, tag, cash, source, extra)
        rows.append(row)
        if not row.get("error"):
            print(
                f"  {label:55} ret={row['ret']*100:6.1f}% dd={row['dd']*100:5.1f}% "
                f"sh={row['sharpe']:4.2f} n={row['n']:3d} wr={row['wr']*100:3.0f}%"
            )
    return rows


def _param_grid_stops(
    model: dict[str, Any], cash: float, source: str, best_tf: str | None
) -> list[dict[str, Any]]:
    """ATR stop + regime grid around the best 4h RSI parameters."""
    print(f"\n======== STOP/REGIME GRID on best_tf={best_tf or 'native 1H'} ========", flush=True)
    atr_mults = [2.0, 2.25, 2.5, 2.75, 3.0]
    use_trails = [True, False]
    regime_periods = [0]

    rows: list[dict[str, Any]] = []
    for atr_mult, use_trail, regime_period in itertools.product(
        atr_mults, use_trails, regime_periods
    ):
        extra = {
            "length": 21,
            "smooth": 14,
            "ob_value": 70.0,
            "os_value": 30.0,
            "smo_type1": "RMA",
            "smo_type2": "EMA",
            "signal_tf": best_tf if best_tf else "4h",
            "use_atr_stop": True,
            "atr_mult": atr_mult,
            "use_trail": use_trail,
            "atr_period": 14,
            "regime_period": regime_period,
            "use_regime": regime_period > 0,
        }
        label = (
            f"tf_{best_tf or '4h'}_len21_sm14_ob70_os30_RMA_EMA_"
            f"atr{atr_mult}_trail{use_trail}_reg{regime_period}"
        )
        tag = _safe_tag(label)
        row = _run(model, tag, cash, source, extra)
        rows.append(row)
        if not row.get("error"):
            print(
                f"  {label:55} ret={row['ret']*100:6.1f}% dd={row['dd']*100:5.1f}% "
                f"sh={row['sharpe']:4.2f} n={row['n']:3d} wr={row['wr']*100:3.0f}%"
            )
    return rows


def _rank_by_ret(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ok = [r for r in rows if not r.get("error") and r.get("n", 0) > 0]
    ok.sort(key=lambda r: (float(r.get("ret", -1)), float(r.get("sharpe", 0))), reverse=True)
    return ok


def _rank_by_risk_adj(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ok = [r for r in rows if not r.get("error") and r.get("n", 0) > 0]

    def _score(r: dict[str, Any]) -> float:
        ret = float(r.get("ret", 0.0))
        dd = abs(float(r.get("dd", 0.0)))
        sh = float(r.get("sharpe", 0.0))
        n = int(r.get("n", 0))
        if dd <= 0.0:
            dd = 0.01
        return (ret / dd) + 0.25 * min(sh, 3.0) + (0.0 if n >= 10 else -0.5)

    ok.sort(key=_score, reverse=True)
    return ok


def _best_tf(baseline_rows: list[dict[str, Any]]) -> str | None:
    """Pick the best signal_tf by risk-adjusted return."""
    ranked = _rank_by_risk_adj(baseline_rows)
    if not ranked:
        return None
    # The best row's tag contains the tf. Easier: the signal_tf is encoded in the run config,
    # but we can read it from the run_dir/config.json. Keep it simple by re-running with the
    # top-level extra we set. We stored extra on the config under the run_dir, not the returned row.
    # We can parse the tag to find the tf, or open the run_dir config.json.
    best = ranked[0]
    run_dir = ROOT / best["path"]
    try:
        cfg = json.loads((run_dir / "config.json").read_text())
        tf = cfg.get("signal_tf")
        return tf
    except Exception:
        return None


def _write_report(
    model_dir: Path,
    model_id: str,
    baseline_rows: list[dict[str, Any]],
    grid_rows: list[dict[str, Any]],
    cash: float,
    source: str,
) -> None:
    ranked_ret = _rank_by_ret(baseline_rows + grid_rows)
    ranked_risk = _rank_by_risk_adj(baseline_rows + grid_rows)

    best_ret = ranked_ret[0] if ranked_ret else None
    best_risk = ranked_risk[0] if ranked_risk else None

    results = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "cash": cash,
        "codes": WINNER_BAG,
        "start": START,
        "end": END,
        "source": source,
        "baseline_interval": "1H",
        "baseline_count": len(baseline_rows),
        "grid_count": len(grid_rows),
        "best_by_return": best_ret,
        "best_by_risk_adj": best_risk,
        "top_by_return": ranked_ret[:10],
        "top_by_risk_adj": ranked_risk[:10],
        "errors": [r for r in baseline_rows + grid_rows if r.get("error")],
    }

    results_path = model_dir / "results.json"
    results_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote results.json: {results_path}")

    # Build a human-readable report.
    lines = [
        f"# {model_id} Sweep Report",
        "",
        f"Generated: {results['generated_utc']}",
        f"Cash: ${cash:,.0f} | Source: {source} | Window: {START} → {END}",
        f"Universe: {', '.join(WINNER_BAG)}",
        "",
        "## Interpretation of the rule",
        "",
        "- The LuxAlgo Ultimate RSI line is **red** when `arsi < os_value` (oversold).",
        "- It is **green** when `arsi > ob_value` (overbought).",
        "- This model goes **long** when the line crosses into red and **exits** when it crosses into green.",
        "",
        "## Best by total return",
        "",
    ]
    if best_ret:
        lines += [
            f"- **Tag:** `{best_ret.get('tag')}`",
            f"- **Total return:** {best_ret.get('ret')*100:.1f}%",
            f"- **Max drawdown:** {best_ret.get('dd')*100:.1f}%",
            f"- **Sharpe:** {best_ret.get('sharpe'):.2f}",
            f"- **Trades:** {best_ret.get('n')} | Win rate: {best_ret.get('wr')*100:.0f}%",
            f"- **Final value:** ${best_ret.get('final_at_cash', 0):,.0f}",
            "",
        ]
    else:
        lines += ["No successful runs.\n"]

    lines += ["## Best by risk-adjusted return (return / |drawdown|)", ""]
    if best_risk:
        lines += [
            f"- **Tag:** `{best_risk.get('tag')}`",
            f"- **Total return:** {best_risk.get('ret')*100:.1f}%",
            f"- **Max drawdown:** {best_risk.get('dd')*100:.1f}%",
            f"- **Sharpe:** {best_risk.get('sharpe'):.2f}",
            f"- **Trades:** {best_risk.get('n')} | Win rate: {best_risk.get('wr')*100:.0f}%",
            f"- **Final value:** ${best_risk.get('final_at_cash', 0):,.0f}",
            "",
        ]
    else:
        lines += ["No successful runs.\n"]

    lines += ["## Top 10 by total return", ""]
    if ranked_ret:
        lines += [
            "| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |",
            "|------|-----|--------|----|--------|--------|----|-------|",
        ]
        for i, r in enumerate(ranked_ret[:10], 1):
            lines.append(
                f"| {i} | `{r.get('tag')}` | {r.get('ret')*100:.1f}% | "
                f"{r.get('dd')*100:.1f}% | {r.get('sharpe'):.2f} | {r.get('n')} | "
                f"{r.get('wr')*100:.0f}% | ${r.get('final_at_cash', 0):,.0f} |"
            )
    else:
        lines += ["No runs.\n"]

    lines += ["", "## Top 10 by risk-adjusted", ""]
    if ranked_risk:
        lines += [
            "| Rank | Tag | Return | DD | Sharpe | Trades | WR | Final |",
            "|------|-----|--------|----|--------|--------|----|-------|",
        ]
        for i, r in enumerate(ranked_risk[:10], 1):
            lines.append(
                f"| {i} | `{r.get('tag')}` | {r.get('ret')*100:.1f}% | "
                f"{r.get('dd')*100:.1f}% | {r.get('sharpe'):.2f} | {r.get('n')} | "
                f"{r.get('wr')*100:.0f}% | ${r.get('final_at_cash', 0):,.0f} |"
            )
    else:
        lines += ["No runs.\n"]

    lines += [
        "",
        "## Errors",
        "",
    ]
    errors = [r for r in baseline_rows + grid_rows if r.get("error")]
    if errors:
        for r in errors[:10]:
            lines.append(f"- `{r.get('tag')}`: {r.get('error')}")
    else:
        lines += ["None.\n"]

    lines += [
        "",
        "## Suggested next improvements",
        "",
        "1. Add a trailing ATR stop once in profit; mean-reversion can turn into a trend move against the position.",
        "2. Use the Ultimate RSI **signal line** for confirmation: e.g., require `arsi` to cross back above its signal line before exiting, or use signal-line crossovers for entry.",
        "3. Add a volume confirmation: only enter red if volume is expanding or above its average.",
        "4. Add a regime filter: avoid long-only entries in strong downtrends (e.g., price below a long-period SMA).",
        "5. Consider a short leg: sell short when the line becomes green (overbought) and cover when it becomes red.",
        "6. Use adaptive thresholds: widen ob/os in high-volatility periods (e.g., ATR-based bands).",
        "7. Walk-forward test: reserve the most recent 6 months for OOS validation instead of optimizing on the whole window.",
        "",
    ]

    report_path = model_dir / "REPORT.md"
    report_path.write_text("\n".join(lines))
    print(f"Wrote REPORT.md: {report_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default="v45_ultimate_rsi", help="Model directory id to sweep")
    ap.add_argument("--cash", type=float, default=1000)
    ap.add_argument("--source", type=str, default="local")
    ap.add_argument("--quick", action="store_true", help="Run baseline timeframe sweep only")
    ap.add_argument("--grid", action="store_true", help="Run classic RSI parameter grid")
    ap.add_argument("--grid-stops", action="store_true", help="Run ATR stop + regime grid")
    ap.add_argument("--no-fallback", action="store_true", help="Do not fall back to yfinance if local fails")
    args = ap.parse_args()

    cash = float(args.cash)
    source = args.source
    fallback = None if args.no_fallback else "yfinance"

    os.environ.setdefault("VIBE_TRADING_DATA_CACHE", "1")
    os.environ.setdefault("VIBE_TRADING_DATA_CACHE_ROOT", str(ROOT / "data_cache"))

    models = dmr.discover_models([args.model])
    if not models:
        print(f"Model {args.model} not found")
        return 1
    model = models[0]
    model_id = model["id"]
    model_dir = Path(model["model_dir"])

    baseline_rows = _baseline_sweep(model, cash, source)
    for r in baseline_rows:
        if r.get("error"):
            print(f"  BASELINE FAIL {r.get('tag')}: {r.get('error')}")

    grid_rows: list[dict[str, Any]] = []
    if args.grid or args.grid_stops or not args.quick:
        best_tf = _best_tf(baseline_rows)
        if args.grid_stops:
            grid_rows = _param_grid_stops(model, cash, source, best_tf)
        else:
            grid_rows = _param_grid(model, cash, source, best_tf)
        for r in grid_rows:
            if r.get("error"):
                print(f"  GRID FAIL {r.get('tag')}: {r.get('error')}")

    _write_report(model_dir, model_id, baseline_rows, grid_rows, cash, source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
