#!/usr/bin/env python3
"""Regenerate MD/HTML audit reports from an existing run artifact directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantmodel.reporting.audit_report import write_markdown_audit
from quantmodel.reporting.html_report import write_html_audit


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: generate_audit_report.py <artifact_run_dir>")
        return 2
    art = Path(sys.argv[1])
    metrics = json.loads((art / "metrics.json").read_text())
    manifest = json.loads((art / "manifest.json").read_text())
    metadata = manifest.get("data_metadata") or {}
    write_markdown_audit(art / "audit_report.md", metrics=metrics, manifest=manifest, metadata=metadata)
    write_html_audit(art / "audit_report.html", metrics=metrics, manifest=manifest, metadata=metadata)
    print("wrote", art / "audit_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
