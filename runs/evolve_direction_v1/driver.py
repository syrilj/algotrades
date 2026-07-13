#!/usr/bin/env python3
"""Driver for evolve_direction_v1 work packages.

Commands:
  phase0        Re-run v39b baseline through full fold/audit pipeline.
  campaign      2-generation smoke campaign.
  campaign-full Run a larger autonomous campaign.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.evolve.loop_core import run_campaign, run_phase0

EVOLVE_DIR = Path(__file__).resolve().parent


def _copy_audit_to_evolve_dir(audit_path: Path) -> Path:
    """Copy the generated audit markdown into the work-package root."""
    md = audit_path.with_suffix(".md")
    if md.exists():
        dest = EVOLVE_DIR / "AUDIT.md"
        shutil.copy2(md, dest)
        return dest
    return audit_path


def cmd_phase0(args: argparse.Namespace) -> None:
    print("[driver] Phase 0: v39b baseline audit", flush=True)
    candidate, audit_path = run_phase0(cash=args.cash)
    dest = _copy_audit_to_evolve_dir(audit_path)
    print(f"[driver] Audit written: {audit_path}")
    print(f"[driver] Copied to: {dest}")
    print(f"[driver] All gates passed: {candidate.get('audit', {}).get('all_pass', False)}")


def cmd_campaign(args: argparse.Namespace) -> None:
    print(f"[driver] Smoke campaign: {args.generations} generations", flush=True)
    base = ROOT / "models" / "poc_va_macdha" / "v39b_live_adapt"
    results = run_campaign(base, generations=args.generations, cash=args.cash)
    print(f"[driver] Campaign finished. Variants run: {len(results)}")


def cmd_full(args: argparse.Namespace) -> None:
    print("[driver] Full autonomous campaign", flush=True)
    base = ROOT / "models" / "poc_va_macdha" / "v39b_live_adapt"
    results = run_campaign(
        base,
        generations=args.generations,
        cash=args.cash,
        campaign_id="evolve_campaign_full",
    )
    print(f"[driver] Full campaign finished. Variants run: {len(results)}")


def main():
    p = argparse.ArgumentParser(description="evolve_direction_v1 driver")
    p.add_argument("--cash", type=float, default=1_000_000)
    sub = p.add_subparsers(dest="cmd", required=True)
    phase0 = sub.add_parser("phase0", help="Re-run v39b baseline and render AUDIT.md")
    phase0.set_defaults(func=cmd_phase0)
    camp = sub.add_parser("campaign", help="Smoke campaign (2 generations)")
    camp.add_argument("--generations", type=int, default=2)
    camp.set_defaults(func=cmd_campaign)
    full = sub.add_parser("campaign-full", help="Full autonomous campaign")
    full.add_argument("--generations", type=int, default=10)
    full.set_defaults(func=cmd_full)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
