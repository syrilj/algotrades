#!/usr/bin/env python3
"""Aggressive big-move options hunt — high premium risk, short DTE, OTM."""
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
OUT = HUNT / "artifacts" / "aggressive"
LOOPS = HUNT / "loops_agg"

NAMES = [
    "IONQ.US", "APLD.US", "MSTR.US", "MARA.US", "GME.US", "SMCI.US",
    "TSLA.US", "COIN.US", "HOOD.US", "RKLB.US", "NVDA.US", "AMD.US",
    "MU.US", "AVGO.US",
]

STYLES = {
    "week_atm20": {"risk_pct": 0.20, "dte_days": 14, "otm_pct": 0.0, "halt_dd": 0.50, "flatten_dd": 0.80},
    "week_otm25": {"risk_pct": 0.25, "dte_days": 14, "otm_pct": 0.08, "halt_dd": 0.55, "flatten_dd": 0.85},
    "sprint_otm35": {"risk_pct": 0.35, "dte_days": 10, "otm_pct": 0.10, "halt_dd": 0.60, "flatten_dd": 0.90},
    "yolo_otm50": {"risk_pct": 0.50, "dte_days": 7, "otm_pct": 0.12, "halt_dd": 0.70, "flatten_dd": 0.95},
}

WINDOW = {"start_date": "2024-08-01", "end_date": "2026-07-11", "interval": "1D"}
INITIAL = 1_000_000.0
YEARS = 1.93


def _years_to_1000x(total_return: float):
    multiple = 1.0 + total_return
    if multiple <= 1.0:
        return None
    cagr = multiple ** (1.0 / YEARS) - 1.0
    if cagr <= 0:
        return None
    return math.log(1000.0) / math.log(1.0 + cagr)


def run_experiment(name: str, codes: list, style: str) -> dict:
    run_dir = LOOPS / name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    code_dir = run_dir / "code"
    code_dir.mkdir(parents=True)
    shutil.copy2(ENGINE_SRC, code_dir / "signal_engine.py")
    style_cfg = dict(STYLES[style])
    style_cfg["initial_cash"] = INITIAL
    style_cfg["contract_multiplier"] = 100
    style_cfg["max_contracts"] = 2000
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
        subprocess.run(
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
        import pandas as pd

        metrics_path = run_dir / "artifacts" / "metrics.csv"
        if not metrics_path.exists():
            return {"name": name, "ok": False, "error": "no metrics", "codes": codes, "style": style}
        m = pd.read_csv(metrics_path).iloc[0].to_dict()
        tr = float(m.get("total_return", 0))
        return {
            "name": name,
            "ok": True,
            "codes": codes,
            "style": style,
            "elapsed": time.time() - t0,
            "final_value": float(m.get("final_value", 0)),
            "total_return": tr,
            "max_drawdown": float(m.get("max_drawdown", 0)),
            "sharpe": float(m.get("sharpe", 0) or 0),
            "win_rate": float(m.get("win_rate", 0) or 0),
            "trade_count": int(float(m.get("trade_count", 0) or 0)),
            "end_per_1000": 1000.0 * (1.0 + tr),
            "years_to_1000x_at_cagr": _years_to_1000x(tr),
        }
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "ok": False, "error": str(exc), "codes": codes, "style": style, "elapsed": time.time() - t0}


def build_jobs():
    jobs = []
    for code in NAMES:
        sym = code.replace(".US", "").lower()
        for style in STYLES:
            jobs.append((f"agg_{sym}__{style}", [code], style))
    bags = {
        "agg_bag_ionq_apld_mstr": ["IONQ.US", "APLD.US", "MSTR.US"],
        "agg_bag_meme_crypto": ["GME.US", "MSTR.US", "MARA.US", "COIN.US"],
        "agg_bag_ai_vol": ["IONQ.US", "SMCI.US", "HOOD.US", "NVDA.US"],
        "agg_bag_all_torque": ["IONQ.US", "APLD.US", "MSTR.US", "GME.US", "MARA.US", "SMCI.US"],
    }
    for bname, codes in bags.items():
        for style in ("week_otm25", "sprint_otm35", "yolo_otm50"):
            jobs.append((f"{bname}__{style}", codes, style))
    return jobs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    LOOPS.mkdir(parents=True, exist_ok=True)
    jobs = build_jobs()
    print(f"Launching {len(jobs)} aggressive experiments...", flush=True)
    results = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(run_experiment, n, c, s): n for n, c, s in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            if r.get("ok"):
                print(
                    f"[{i}/{len(jobs)}] {r['name']} ret={r['total_return']*100:.0f}% "
                    f"dd={r['max_drawdown']*100:.0f}% $1k→${r['end_per_1000']:.0f}",
                    flush=True,
                )
            else:
                print(f"[{i}/{len(jobs)}] FAIL {r['name']}", flush=True)

    (OUT / "ALL.json").write_text(json.dumps(results, indent=2))
    ok = [r for r in results if r.get("ok")]
    ok.sort(key=lambda r: r.get("total_return", -9e9), reverse=True)
    (OUT / "LEADERBOARD.json").write_text(json.dumps(ok[:40], indent=2))
    hit10 = sum(1 for r in ok if r["end_per_1000"] >= 10000)
    hit100 = sum(1 for r in ok if r["end_per_1000"] >= 100000)
    hit1000 = sum(1 for r in ok if r["end_per_1000"] >= 1000000)
    lines = [
        "# Aggressive big-move hunt",
        "",
        f"Jobs {len(jobs)} · OK {len(ok)}",
        f"Multiples: 10x={hit10} · 100x={hit100} · 1000x={hit1000}",
        "",
        "| rank | name | ret | DD | end/$1k | yrs→$1M |",
        "|-----:|------|----:|---:|--------:|--------:|",
    ]
    for i, r in enumerate(ok[:20], 1):
        y = r.get("years_to_1000x_at_cagr")
        ys = f"{y:.1f}" if isinstance(y, (int, float)) else "—"
        lines.append(
            f"| {i} | `{r['name']}` | {r['total_return']*100:.0f}% | {r['max_drawdown']*100:.0f}% | "
            f"${r['end_per_1000']:.0f} | {ys} |"
        )
    best = ok[0] if ok else None
    if best:
        lines += [
            "",
            "## Best aggressive",
            f"- `{best['name']}` codes={best['codes']} style=`{best['style']}`",
            f"- end/$1k **${best['end_per_1000']:.0f}** DD {best['max_drawdown']*100:.0f}%",
            f"- yrs to $1M at CAGR: {best.get('years_to_1000x_at_cagr')}",
            "",
            "Note: even with YOLO risk, full-window CAGR still rarely hits 1000x. "
            "2-week *segments* can spike; check WEEKLY_SPIKES.json if present.",
        ]
    (OUT / "SYNTHESIS.md").write_text("\n".join(lines) + "\n")
    print("Done.", flush=True)
    if best:
        print(
            f"BEST {best['name']} ret={best['total_return']*100:.1f}% end1k=${best['end_per_1000']:.0f} "
            f"10x={hit10} 100x={hit100} 1000x={hit1000}",
            flush=True,
        )


if __name__ == "__main__":
    main()
