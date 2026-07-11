"""Record and query durable model-improvement findings.

Shared module for every family under models/. Success and failure both get logged.
Failures drive the re-research loop (see models/_shared/FAILURE_PROTOCOL.md).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "models" / "_shared"
FINDINGS_PATH = SHARED / "findings.jsonl"
PASS_BAR_PATH = SHARED / "PASS_BAR.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_pass_bar() -> dict[str, Any]:
    return json.loads(PASS_BAR_PATH.read_text())


def load_findings() -> list[dict[str, Any]]:
    if not FINDINGS_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in FINDINGS_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def append_finding(row: dict[str, Any]) -> dict[str, Any]:
    SHARED.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    payload.setdefault("ts", _utc_now())
    with FINDINGS_PATH.open("a") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def extract_portfolio(metrics_obj: Any) -> dict[str, Any] | None:
    if not isinstance(metrics_obj, dict):
        return None
    port = metrics_obj.get("portfolio")
    if isinstance(port, dict) and ("sharpe" in port or "win_rate" in port):
        return port
    if "sharpe" in metrics_obj and "win_rate" in metrics_obj:
        return metrics_obj
    return None


def check_pass_bar(portfolio: dict[str, Any] | None) -> dict[str, Any]:
    bar = load_pass_bar()
    gates = bar.get("gates") or {}
    if not portfolio:
        return {"passed": False, "reasons": ["missing_portfolio"], "gates": gates}

    def f(key: str, default: float = 0.0) -> float:
        try:
            v = float(portfolio.get(key, default))
            return default if v != v else v
        except (TypeError, ValueError):
            return default

    pf = f("profit_factor", 1.0)
    dd = abs(f("max_drawdown", 0.0))
    sharpe = f("sharpe", 0.0)
    trades = f("trade_count", 0.0)
    reasons: list[str] = []
    if pf < float(gates.get("profit_factor_min", 1.2)):
        reasons.append(f"profit_factor {pf:.3f} < {gates['profit_factor_min']}")
    if dd > float(gates.get("max_drawdown_max_abs", 0.25)):
        reasons.append(f"|max_drawdown| {dd:.3f} > {gates['max_drawdown_max_abs']}")
    if sharpe < float(gates.get("sharpe_min", 0.5)):
        reasons.append(f"sharpe {sharpe:.3f} < {gates['sharpe_min']}")
    if trades < float(gates.get("min_trades", 40)):
        reasons.append(f"trade_count {trades:.0f} < {gates['min_trades']}")
    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
        "snapshot": {
            "profit_factor": pf,
            "max_drawdown": -dd if f("max_drawdown") < 0 else dd,
            "sharpe": sharpe,
            "trade_count": trades,
            "win_rate": f("win_rate"),
        },
        "gates": gates,
    }


def recent_fail_streak(kind: str | None = None, limit: int = 20) -> int:
    """Count consecutive fails at end of log (optionally filtered by kind)."""
    rows = load_findings()
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    rows = rows[-limit:]
    streak = 0
    for row in reversed(rows):
        if row.get("status") == "fail":
            streak += 1
        else:
            break
    return streak


def next_actions() -> list[str]:
    actions: list[str] = []
    fails = [r for r in load_findings() if r.get("status") == "fail"]
    if not fails:
        actions.append(
            "No recorded failures. Read PLAYBOOK.md and apply WORKING findings to next version."
        )
        return actions
    last = fails[-1]
    actions.append(
        f"Last fail: {last.get('version')} ({last.get('kind')}): {last.get('summary')}"
    )
    if last.get("failure_class"):
        actions.append(f"Failure class: {last['failure_class']}")
    if last.get("next_action"):
        actions.append(f"Prescribed next: {last['next_action']}")
    streak = recent_fail_streak(kind=last.get("kind"))
    if streak >= 3:
        actions.append(
            f"ESCALATE: {streak} consecutive fails on kind={last.get('kind')}. "
            "Stop coding. Run a new EDGE_RESEARCH pass before vN+1."
        )
    else:
        actions.append(
            "Follow models/_shared/FAILURE_PROTOCOL.md — re-research, then small lake fix."
        )
    actions.append("Do not stack vanity win-rate filters.")
    return actions


def cmd_list(_: argparse.Namespace) -> int:
    rows = load_findings()
    if not rows:
        print("No findings yet.")
        return 0
    for row in rows:
        print(
            f"{row.get('ts', '?'):20}  {row.get('status', '?'):7}  "
            f"{row.get('family', '?'):16}  {row.get('version', '?'):20}  "
            f"{row.get('kind', '?'):16}  {row.get('summary', '')}"
        )
    return 0


def cmd_working(_: argparse.Namespace) -> int:
    for row in load_findings():
        if row.get("status") == "working":
            print(f"- [{row.get('kind')}] {row.get('summary')}")
    return 0


def cmd_failed(_: argparse.Namespace) -> int:
    for row in load_findings():
        if row.get("status") == "fail":
            print(
                f"- [{row.get('failure_class') or 'unclassified'}] "
                f"{row.get('version')}: {row.get('summary')} → {row.get('next_action')}"
            )
    return 0


def cmd_next(_: argparse.Namespace) -> int:
    for line in next_actions():
        print(line)
    return 0


def cmd_check(ns: argparse.Namespace) -> int:
    path = Path(ns.metrics_json)
    obj = json.loads(path.read_text())
    port = extract_portfolio(obj)
    result = check_pass_bar(port)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


def cmd_record(ns: argparse.Namespace) -> int:
    metrics_path = ns.metrics_json
    portfolio = None
    pass_check = None
    if metrics_path:
        p = Path(metrics_path)
        metrics_obj = json.loads(p.read_text())
        portfolio = extract_portfolio(metrics_obj)
        pass_check = check_pass_bar(portfolio)
        if ns.status == "auto":
            ns.status = "pass" if pass_check["passed"] else "fail"

    row: dict[str, Any] = {
        "ts": _utc_now(),
        "family": ns.family,
        "version": ns.version,
        "status": ns.status,
        "kind": ns.kind,
        "summary": ns.summary,
        "evidence": ([metrics_path] if metrics_path else []) + (ns.evidence or []),
        "failure_class": ns.failure_class,
        "next_action": ns.next_action,
        "source": ns.source or "cli",
    }
    if portfolio:
        row["metrics"] = {
            k: portfolio.get(k)
            for k in (
                "win_rate",
                "sharpe",
                "profit_factor",
                "max_drawdown",
                "total_return",
                "trade_count",
            )
            if k in portfolio
        }
    if pass_check is not None:
        row["pass_bar"] = pass_check
        if ns.status == "fail" and not ns.failure_class:
            row["failure_class"] = "pass_bar_miss"
        if ns.status == "fail" and not ns.next_action:
            row["next_action"] = (
                "Follow FAILURE_PROTOCOL.md; re-research before next version. "
                + "; ".join(pass_check.get("reasons") or [])
            )

    saved = append_finding(row)
    print(json.dumps(saved, indent=2))
    if ns.status == "fail":
        print("---")
        for line in next_actions():
            print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Shared model findings log")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Print all findings").set_defaults(func=cmd_list)
    sub.add_parser("working", help="Print working findings only").set_defaults(
        func=cmd_working
    )
    sub.add_parser("failed", help="Print failed findings only").set_defaults(
        func=cmd_failed
    )
    sub.add_parser("next", help="Suggest next action from latest failures").set_defaults(
        func=cmd_next
    )

    c = sub.add_parser("check", help="Check metrics JSON against PASS_BAR")
    c.add_argument("--metrics-json", required=True)
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("record", help="Append a finding")
    r.add_argument("--family", required=True)
    r.add_argument("--version", required=True)
    r.add_argument(
        "--status", required=True, choices=["working", "pass", "fail", "auto"]
    )
    r.add_argument("--kind", required=True)
    r.add_argument("--summary", required=True)
    r.add_argument("--metrics-json", default=None)
    r.add_argument("--failure-class", default=None)
    r.add_argument("--next-action", default=None)
    r.add_argument("--evidence", action="append", default=[])
    r.add_argument("--source", default="cli")
    r.set_defaults(func=cmd_record)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
