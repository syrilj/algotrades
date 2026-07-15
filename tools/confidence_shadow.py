"""Append-only shadow decision ledger for live confidence outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "runs" / "live_confidence" / "shadow_decisions.jsonl"


class ShadowDecisionLedger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("CONFIDENCE_SHADOW_PATH") or DEFAULT_PATH)

    def record(self, payload: dict[str, Any]) -> str:
        event = dict(payload)
        event.setdefault("recorded_at_utc", datetime.now(timezone.utc).isoformat())
        basis = json.dumps(event, sort_keys=True, default=str).encode("utf-8")
        event_id = hashlib.sha256(basis).hexdigest()[:20]
        event["event_id"] = event_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
        return event_id

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def settle(self, event_id: str, *, outcome: float, settled_at: str | None = None) -> bool:
        rows = self.read()
        found = False
        for row in rows:
            if row.get("event_id") == event_id:
                row["outcome"] = float(outcome)
                row["settled_at_utc"] = settled_at or datetime.now(timezone.utc).isoformat()
                found = True
        if found:
            self.path.write_text("".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")
        return found

    def summary(self) -> dict[str, Any]:
        rows = self.read()
        settled = [r for r in rows if r.get("outcome") is not None]
        return {
            "path": str(self.path),
            "events": len(rows),
            "settled": len(settled),
            "mean_outcome": (sum(float(r["outcome"]) for r in settled) / len(settled)) if settled else None,
            "states": {state: sum(1 for r in rows if r.get("state") == state) for state in ("ENTER", "WATCH", "ABSTAIN")},
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or settle shadow confidence decisions")
    parser.add_argument("--path", default=None)
    parser.add_argument("--settle")
    parser.add_argument("--outcome", type=float)
    args = parser.parse_args(argv)
    ledger = ShadowDecisionLedger(args.path)
    if args.settle:
        if args.outcome is None:
            parser.error("--outcome is required with --settle")
        print(json.dumps({"settled": ledger.settle(args.settle, outcome=args.outcome), "event_id": args.settle}, indent=2))
    else:
        print(json.dumps(ledger.summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
