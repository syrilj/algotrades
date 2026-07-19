#!/usr/bin/env python3
"""Run Donchian ablations from a base config; write comparison CSV + print table."""

from __future__ import annotations

import csv
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantmodel.backtest.engine import run_backtest
from quantmodel.config import load_config
from quantmodel.experiments.registry import append_experiment
from quantmodel.reporting.audit_report import write_markdown_audit
from quantmodel.reporting.html_report import write_html_audit


def _variants(base: dict) -> list[tuple[str, dict]]:
    def make(name: str, mut: Callable[[dict], None]) -> tuple[str, dict]:
        cfg = deepcopy(base)
        cfg["run"] = dict(cfg["run"])
        cfg["signal"] = dict(cfg["signal"])
        cfg["risk"] = dict(cfg["risk"])
        cfg["run"]["name"] = name
        mut(cfg)
        return name, cfg

    def donchian_only(c: dict) -> None:
        c["signal"]["require_volume_confirm"] = False
        c["signal"]["require_stock_trend_filter"] = False
        c["signal"]["benchmark_regime_filter"] = False

    def plus_volume(c: dict) -> None:
        c["signal"]["require_volume_confirm"] = True
        c["signal"]["require_stock_trend_filter"] = False
        c["signal"]["benchmark_regime_filter"] = False

    def plus_stock_sma(c: dict) -> None:
        c["signal"]["require_volume_confirm"] = True
        c["signal"]["require_stock_trend_filter"] = True
        c["signal"]["benchmark_regime_filter"] = False

    def tight_atr(c: dict) -> None:
        c["risk"]["atr_multiple"] = 2.0

    def no_trail(c: dict) -> None:
        c["risk"]["trail_with_donchian"] = False

    def entry55(c: dict) -> None:
        c["signal"]["entry_lookback"] = 55

    return [
        make("v2_full_fixed", lambda c: None),
        make("abl_donchian_only", donchian_only),
        make("abl_plus_volume", plus_volume),
        make("abl_plus_stock_sma", plus_stock_sma),
        make("abl_tight_atr2", tight_atr),
        make("abl_no_trail", no_trail),
        make("abl_entry55", entry55),
    ]


def main() -> int:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "configs" / "demo_v2_fixed.yaml")
    base = load_config(cfg_path)
    rows = []
    print(f"{'variant':22} {'ret':>8} {'sharpe':>8} {'mdd':>8} {'fills':>6} {'status'}")
    print("-" * 72)
    for name, cfg in _variants(base):
        try:
            res = run_backtest(cfg, notes=f"ablation:{name}")
            m = res["metrics"]
            status = res["manifest"].deployment_status
            row = {
                "variant": name,
                "run_id": res["run_id"],
                "total_return": m.get("total_return"),
                "cagr": m.get("cagr"),
                "sharpe": m.get("sharpe"),
                "max_drawdown": m.get("max_drawdown"),
                "n_fills": m.get("n_fills"),
                "avg_positions": m.get("avg_positions"),
                "final_equity": m.get("final_equity"),
                "deployment_status": status,
            }
            rows.append(row)
            append_experiment(
                {
                    "run_id": res["run_id"],
                    "run_name": name,
                    "sharpe": m.get("sharpe"),
                    "deployment_status": status,
                    "notes": f"ablation:{name}",
                }
            )
            art = Path(res["artifact_dir"])
            write_markdown_audit(
                art / "audit_report.md",
                metrics=m,
                manifest=asdict(res["manifest"]),
                metadata=res["metadata"],
            )
            write_html_audit(
                art / "audit_report.html",
                metrics=m,
                manifest=asdict(res["manifest"]),
                metadata=res["metadata"],
            )
            print(
                f"{name:22} {m.get('total_return', 0):8.2%} {m.get('sharpe', 0):8.3f} "
                f"{m.get('max_drawdown', 0):8.2%} {m.get('n_fills', 0):6d} {status}"
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"variant": name, "error": str(exc)})
            print(f"{name:22} ERROR {exc}")

    out_csv = ROOT / "artifacts" / "ablation_summary.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        keys = sorted({k for r in rows for k in r.keys()})
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print(f"\nWrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
