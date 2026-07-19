"""Minimal HTML audit report (no heavy deps required)."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Mapping


def write_html_audit(
    path: Path,
    *,
    metrics: Mapping[str, Any],
    manifest: Mapping[str, Any],
    metadata: Mapping[str, Any],
    promotion: Mapping[str, Any] | None = None,
) -> Path:
    promo = promotion or metrics.get("promotion") or {}
    status = escape(str(promo.get("deployment_status", "UNKNOWN")))
    rows = []
    for k in (
        "final_equity",
        "total_return",
        "cagr",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "n_fills",
        "cost_drag",
    ):
        v = metrics.get(k, "")
        if isinstance(v, float) and k in {"total_return", "cagr", "max_drawdown", "cost_drag"}:
            disp = f"{v:.2%}"
        elif isinstance(v, float):
            disp = f"{v:.4f}"
        else:
            disp = str(v)
        rows.append(f"<tr><td>{escape(k)}</td><td>{escape(disp)}</td></tr>")

    lims = metadata.get("limitations") or []
    lim_html = "".join(f"<li>{escape(str(x))}</li>" for x in lims) or "<li>none</li>"
    reasons = promo.get("reasons") or []
    reason_html = "".join(f"<li>{escape(str(x))}</li>" for x in reasons) or "<li>none</li>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Audit {escape(str(manifest.get('run_name','')))}</title>
  <style>
    body {{ font-family: 'IBM Plex Sans', system-ui, sans-serif; background:#0f1419; color:#e7ecf1; margin:2rem; }}
    h1,h2 {{ font-family: 'Source Serif 4', Georgia, serif; color:#9fd3c7; }}
    table {{ border-collapse: collapse; width: min(640px, 100%); }}
    td, th {{ border: 1px solid #2a3540; padding: 0.4rem 0.6rem; }}
    .status {{ font-size: 1.2rem; font-weight: 700; color: #f0b429; }}
    code {{ color: #9fd3c7; }}
  </style>
</head>
<body>
  <h1>Audit Report</h1>
  <p class="status">Deployment: {status}</p>
  <p>Run ID: <code>{escape(str(manifest.get('run_id','')))}</code></p>
  <p>Git: <code>{escape(str(manifest.get('git_commit','')))}</code> dirty={escape(str(manifest.get('git_dirty_flag')))}</p>
  <p>Config hash: <code>{escape(str(manifest.get('config_hash','')))}</code></p>
  <p>Data hash: <code>{escape(str(manifest.get('data_manifest_hash','')))}</code></p>
  <h2>Metrics</h2>
  <table><tbody>{''.join(rows)}</tbody></table>
  <h2>Data limitations</h2>
  <ul>{lim_html}</ul>
  <h2>Promotion reasons</h2>
  <ul>{reason_html}</ul>
  <p><em>Research software only. Live routing disabled.</em></p>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
