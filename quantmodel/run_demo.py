#!/usr/bin/env python3
"""End-to-end demo: synthetic (and optional LSE) Donchian backtest + audit artifacts."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

# Ensure src on path when run without install
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from quantmodel.backtest.engine import run_backtest  # noqa: E402
from quantmodel.config import load_config  # noqa: E402
from quantmodel.experiments.registry import append_experiment  # noqa: E402
from quantmodel.reporting.audit_report import write_markdown_audit  # noqa: E402
from quantmodel.reporting.html_report import write_html_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run quantmodel Donchian demo")
    parser.add_argument(
        "--config",
        default=str(ROOT / "configs" / "demo_v2_fixed.yaml"),
        help="Path to YAML config (default: fixed v2 research profile)",
    )
    parser.add_argument("--notes", default="demo run", help="Registry notes")
    args = parser.parse_args()

    config = load_config(args.config)
    result = run_backtest(config, notes=args.notes)
    manifest = result["manifest"]
    metrics = result["metrics"]
    metadata = result["metadata"]
    art = Path(result["artifact_dir"])

    exp_n = append_experiment(
        {
            "run_id": result["run_id"],
            "run_name": config["run"]["name"],
            "config_hash": manifest.config_hash,
            "data_manifest_hash": manifest.data_manifest_hash,
            "deployment_status": manifest.deployment_status,
            "sharpe": metrics.get("sharpe"),
            "notes": args.notes,
        }
    )
    # re-stamp experiment number on manifest file is optional

    write_markdown_audit(
        art / "audit_report.md",
        metrics=metrics,
        manifest={**asdict(manifest), "experiment_number": exp_n},
        metadata=metadata,
        promotion=metrics.get("promotion"),
    )
    write_html_audit(
        art / "audit_report.html",
        metrics=metrics,
        manifest={**asdict(manifest), "experiment_number": exp_n},
        metadata=metadata,
        promotion=metrics.get("promotion"),
    )

    print("=== quantmodel demo complete ===")
    print(f"run_id:     {result['run_id']}")
    print(f"artifacts:  {art}")
    print(f"equity:     {metrics.get('final_equity', 0):,.2f}")
    print(f"sharpe:     {metrics.get('sharpe', 0):.3f}")
    print(f"max_dd:     {metrics.get('max_drawdown', 0):.2%}")
    print(f"fills:      {metrics.get('n_fills', 0)}")
    print(f"status:     {manifest.deployment_status}")
    print(f"experiment: {exp_n}")
    print(f"audit:      {art / 'audit_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
