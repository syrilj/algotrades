#!/usr/bin/env python3
"""CLI: run a single backtest from YAML config."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantmodel.backtest.engine import run_backtest
from quantmodel.config import load_config
from quantmodel.experiments.registry import append_experiment, next_experiment_number
from quantmodel.reporting.audit_report import write_markdown_audit
from quantmodel.reporting.html_report import write_html_audit


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--notes", default="")
    args = p.parse_args()
    cfg = load_config(args.config)
    exp = next_experiment_number()
    res = run_backtest(cfg, experiment_number=exp, notes=args.notes)
    append_experiment(
        {
            "run_id": res["run_id"],
            "run_name": cfg["run"]["name"],
            "deployment_status": res["manifest"].deployment_status,
            "sharpe": res["metrics"].get("sharpe"),
            "notes": args.notes,
        }
    )
    art = Path(res["artifact_dir"])
    write_markdown_audit(
        art / "audit_report.md",
        metrics=res["metrics"],
        manifest=asdict(res["manifest"]),
        metadata=res["metadata"],
    )
    write_html_audit(
        art / "audit_report.html",
        metrics=res["metrics"],
        manifest=asdict(res["manifest"]),
        metadata=res["metadata"],
    )
    print(res["run_id"], res["artifact_dir"], res["manifest"].deployment_status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
