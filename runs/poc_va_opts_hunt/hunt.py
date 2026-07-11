#!/usr/bin/env python3
"""Parallel options-stock hunt with feedback loops.

Prior notes baked in:
- v20 stock PnL leaders: MU > APLD > IONQ > TSLA (MSTR not in book)
- v21 MSTR+TSLA equity FAILED (-6%); options ATM modest +9%
- v15 wins Sharpe; v12/v14/v20 win raw money on diversified book
- Goal ask: grow $1k → $1M (1000x). Over ~1.9y that needs ~CAGR 2000%+ — hunt max multiple,
  report years-to-1000x at realized CAGR, do not fake a guarantee.

Runs many single-name + bag options experiments in parallel.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUNT = ROOT / "runs" / "poc_va_opts_hunt"
ENGINE_SRC = HUNT / "code" / "signal_engine.py"
OUT = HUNT / "artifacts"
LOOPS = HUNT / "loops"

# Universe: prior winners + liquid optionable high-beta / mega-cap / ETF proxies
UNIVERSE = [
    "MU.US", "APLD.US", "IONQ.US", "TSLA.US", "ARM.US", "MSTR.US",
    "NVDA.US", "AMD.US", "COIN.US", "MARA.US", "SMCI.US", "PLTR.US",
    "SOFI.US", "HOOD.US", "META.US", "AMZN.US", "QQQ.US", "SPY.US",
    "GME.US", "RKLB.US", "AVGO.US", "CRM.US",
]

# Approaches (style knobs) — run in parallel with stocks
STYLES = {
    "atm5_30": {"risk_pct": 0.05, "dte_days": 30, "otm_pct": 0.0, "halt_dd": 0.25, "flatten_dd": 0.40},
    "atm10_21": {"risk_pct": 0.10, "dte_days": 21, "otm_pct": 0.0, "halt_dd": 0.30, "flatten_dd": 0.45},
    "otm8_14": {"risk_pct": 0.08, "dte_days": 14, "otm_pct": 0.05, "halt_dd": 0.30, "flatten_dd": 0.50},
    "lotto15_10": {"risk_pct": 0.15, "dte_days": 10, "otm_pct": 0.08, "halt_dd": 0.35, "flatten_dd": 0.55},
}

WINDOW = {"start_date": "2024-08-01", "end_date": "2026-07-11", "interval": "1D"}
INITIAL = 1_000_000.0  # scale to $1k later
YEARS = 1.93  # approx window length


def _years_to_1000x(total_return: float) -> float | None:
    """Years to turn 1→1000 at constant CAGR matching this window's total return."""
    if total_return <= -0.999:
        return None
    multiple = 1.0 + total_return
    if multiple <= 1.0:
        return None
    cagr = multiple ** (1.0 / YEARS) - 1.0
    if cagr <= 0:
        return None
    return math.log(1000.0) / math.log(1.0 + cagr)


def run_experiment(name: str, codes: list[str], style: str) -> dict:
    run_dir = LOOPS / name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    code_dir = run_dir / "code"
    code_dir.mkdir(parents=True)
    shutil.copy2(ENGINE_SRC, code_dir / "signal_engine.py")
    style_cfg = dict(STYLES[style])
    style_cfg["initial_cash"] = INITIAL
    style_cfg["contract_multiplier"] = 100
    (code_dir / "hunt_config.json").write_text(json.dumps(style_cfg, indent=2))
    cfg = {
        "source": "yfinance",
        "codes": codes,
        "initial_cash": INITIAL,
        "commission": 0.001,
        "engine": "options",
        **WINDOW,
        "options_config": {
            "risk_free_rate": 0.05,
            "contract_multiplier": 100,
            "exercise_style": "american",
        },
        "strategy": {"model_version": name, "style": style, "codes": codes},
    }
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    t0 = time.time()
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; from backtest.runner import main; "
                f"main(Path({str(run_dir)!r}).resolve())",
            ],
            capture_output=True,
            text=True,
            timeout=900,
            cwd=str(ROOT),
        )
        elapsed = time.time() - t0
        metrics_path = run_dir / "artifacts" / "metrics.csv"
        if not metrics_path.exists():
            return {
                "name": name,
                "ok": False,
                "error": (proc.stderr or proc.stdout or "no metrics")[-500:],
                "elapsed": elapsed,
                "codes": codes,
                "style": style,
            }
        import pandas as pd

        m = pd.read_csv(metrics_path).iloc[0].to_dict()
        tr = float(m.get("total_return", 0))
        end_1k = 1000.0 * (1.0 + tr)
        y1000 = _years_to_1000x(tr)
        return {
            "name": name,
            "ok": True,
            "codes": codes,
            "style": style,
            "elapsed": elapsed,
            "final_value": float(m.get("final_value", 0)),
            "total_return": tr,
            "max_drawdown": float(m.get("max_drawdown", 0)),
            "sharpe": float(m.get("sharpe", 0) or 0),
            "win_rate": float(m.get("win_rate", 0) or 0),
            "profit_factor": float(m.get("profit_factor", 0) or 0) if "profit_factor" in m else None,
            "trade_count": int(float(m.get("trade_count", 0) or 0)),
            "end_per_1000": end_1k,
            "years_to_1000x_at_cagr": y1000,
            "survived": float(m.get("max_drawdown", 0)) > -0.55,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "ok": False,
            "error": str(exc),
            "elapsed": time.time() - t0,
            "codes": codes,
            "style": style,
        }


def build_jobs() -> list[tuple[str, list[str], str]]:
    jobs: list[tuple[str, list[str], str]] = []
    # Round 1: every name × core styles (atm5 + atm10) — find best underlyings
    for code in UNIVERSE:
        sym = code.replace(".US", "").lower()
        jobs.append((f"solo_{sym}__atm5_30", [code], "atm5_30"))
        jobs.append((f"solo_{sym}__atm10_21", [code], "atm10_21"))
    # Round 2: prior-winner bags
    bags = {
        "bag_v20winners": ["MU.US", "APLD.US", "IONQ.US", "TSLA.US"],
        "bag_crypto_beta": ["COIN.US", "MSTR.US", "MARA.US"],
        "bag_semi": ["MU.US", "NVDA.US", "AMD.US", "AVGO.US", "ARM.US"],
        "bag_ai_retail": ["PLTR.US", "SMCI.US", "SOFI.US", "HOOD.US"],
        "bag_mega": ["META.US", "AMZN.US", "QQQ.US"],
    }
    for bname, codes in bags.items():
        for style in ("atm5_30", "atm10_21", "otm8_14"):
            jobs.append((f"{bname}__{style}", codes, style))
    # Round 3: lottery style on prior + volatile names only
    for code in ["APLD.US", "IONQ.US", "MARA.US", "GME.US", "MSTR.US", "SMCI.US"]:
        sym = code.replace(".US", "").lower()
        jobs.append((f"lotto_{sym}__lotto15_10", [code], "lotto15_10"))
    return jobs


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    LOOPS.mkdir(parents=True, exist_ok=True)
    jobs = build_jobs()
    notes = {
        "prior_notes": [
            "v20 stock leaders MU/APLD/IONQ/TSLA",
            "v21 MSTR+TSLA equity failed; options small win",
            "Diversified equity compounds better than 2-name focus",
            "Account floor required (flatten before blowup)",
            "$1k→$1M = 1000x; report years-to-target at realized CAGR",
        ],
        "n_jobs": len(jobs),
        "window": WINDOW,
    }
    (OUT / "NOTES_START.json").write_text(json.dumps(notes, indent=2))
    print(f"Launching {len(jobs)} experiments...", flush=True)
    results: list[dict] = []
    # Parallelism: 4 workers to avoid Yahoo rate limits
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(run_experiment, n, c, s): n for n, c, s in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            status = "OK" if r.get("ok") else "FAIL"
            extra = ""
            if r.get("ok"):
                extra = f" ret={r['total_return']*100:.1f}% dd={r['max_drawdown']*100:.1f}% end1k=${r['end_per_1000']:.0f}"
            print(f"[{i}/{len(jobs)}] {status} {r['name']}{extra}", flush=True)

    (OUT / "ALL_RESULTS.json").write_text(json.dumps(results, indent=2))
    ok = [r for r in results if r.get("ok")]
    ok.sort(key=lambda r: r.get("total_return", -9e9), reverse=True)
    (OUT / "LEADERBOARD.json").write_text(json.dumps(ok[:30], indent=2))

    # Feedback: top underlyings by avg return across styles
    from collections import defaultdict

    by_code: dict[str, list[float]] = defaultdict(list)
    for r in ok:
        if len(r.get("codes", [])) == 1:
            by_code[r["codes"][0]].append(r["total_return"])
    code_rank = sorted(
        ((c, sum(v) / len(v), max(v), len(v)) for c, v in by_code.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    best = ok[0] if ok else None
    synthesis = {
        "best_experiment": best,
        "top10": ok[:10],
        "best_underlyings_avg_ret": [
            {"code": c, "avg_ret": a, "best_ret": b, "n": n} for c, a, b, n in code_rank[:15]
        ],
        "goal_1000_to_1m": {
            "required_multiple": 1000,
            "best_end_per_1000": best.get("end_per_1000") if best else None,
            "best_years_to_1000x": best.get("years_to_1000x_at_cagr") if best else None,
            "honest": "If years_to_1000x is huge or None, this window/style cannot hit the goal without unreal leverage / lucky OTM lottery paths.",
        },
        "live_recommendation_rule": "Prefer high avg_ret underlying with DD > -45%, trades>=8, and bag diversification from top3 underlyings.",
    }
    (OUT / "SYNTHESIS.json").write_text(json.dumps(synthesis, indent=2))

    # Markdown report
    lines = [
        "# Options hunt synthesis",
        "",
        f"Jobs: {len(jobs)} · OK: {len(ok)} · FAIL: {len(results)-len(ok)}",
        "",
        "## Best experiments (by total return)",
        "",
        "| rank | name | ret | DD | Sharpe | n | end/$1k | yrs→$1M |",
        "|-----:|------|----:|---:|-------:|--:|--------:|--------:|",
    ]
    for i, r in enumerate(ok[:15], 1):
        y = r.get("years_to_1000x_at_cagr")
        y_s = f"{y:.1f}" if isinstance(y, (int, float)) else "—"
        lines.append(
            f"| {i} | `{r['name']}` | {r['total_return']*100:.1f}% | {r['max_drawdown']*100:.1f}% | "
            f"{r['sharpe']:.2f} | {r['trade_count']} | ${r['end_per_1000']:.0f} | {y_s} |"
        )
    lines += ["", "## Best underlyings (avg across solo styles)", ""]
    for c, a, b, n in code_rank[:10]:
        lines.append(f"- **{c}**: avg {a*100:.1f}% · best {b*100:.1f}% · ({n} styles)")
    if best:
        lines += [
            "",
            "## Live candidate seed",
            "",
            f"- Experiment: `{best['name']}`",
            f"- Codes: {best['codes']}",
            f"- Style: `{best['style']}`",
            f"- End per $1k: **${best['end_per_1000']:.0f}**",
            f"- Years to $1M at this CAGR: **{best.get('years_to_1000x_at_cagr')}**",
        ]
    (OUT / "SYNTHESIS.md").write_text("\n".join(lines) + "\n")
    print("\nDone. See runs/poc_va_opts_hunt/artifacts/SYNTHESIS.md", flush=True)
    if best:
        print(
            f"BEST {best['name']} ret={best['total_return']*100:.1f}% end1k=${best['end_per_1000']:.0f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
