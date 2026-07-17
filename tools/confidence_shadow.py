"""Append-only shadow decision ledger for live confidence outcomes."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "runs" / "live_confidence" / "shadow_decisions.jsonl"
HORIZON_BUSINESS_DAYS = {"day": 1, "swing": 5, "position": 20}


class ShadowDecisionLedger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("CONFIDENCE_SHADOW_PATH") or DEFAULT_PATH)
        self._thread_lock = threading.RLock()

    @contextmanager
    def _locked(self):
        """Serialize append/rewrite operations across threads and processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with self._thread_lock, lock_path.open("a+", encoding="utf-8") as lock_handle:
            try:
                import fcntl

                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
            try:
                yield
            finally:
                try:
                    import fcntl

                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # A damaged tail must not hide earlier valid evidence.
                continue
        return rows

    def _write_unlocked(self, rows: list[dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def record(self, payload: dict[str, Any]) -> str:
        event = dict(payload)
        event.setdefault("recorded_at_utc", datetime.now(timezone.utc).isoformat())
        basis = json.dumps(event, sort_keys=True, default=str).encode("utf-8")
        event_id = hashlib.sha256(basis).hexdigest()[:20]
        event["event_id"] = event_id
        with self._locked():
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return event_id

    def read(self) -> list[dict[str, Any]]:
        with self._locked():
            return self._read_unlocked()

    def settle(self, event_id: str, *, outcome: float, settled_at: str | None = None) -> bool:
        with self._locked():
            rows = self._read_unlocked()
            found = False
            for row in rows:
                if row.get("event_id") == event_id:
                    row["outcome"] = float(outcome)
                    row["settled_at_utc"] = settled_at or datetime.now(timezone.utc).isoformat()
                    found = True
            if found:
                self._write_unlocked(rows)
            return found

    def settle_due(
        self,
        *,
        data_dir: str | Path | None = None,
        now: str | datetime | None = None,
    ) -> dict[str, Any]:
        """Settle mature decisions from immutable local daily bars.

        Events without a recorded reference price remain pending. We deliberately
        do not infer an entry from an end-of-day bar because that could introduce
        look-ahead for intraday decisions.
        """
        import pandas as pd

        bars_root = Path(data_dir or (ROOT / "data_cache" / "1d"))
        now_ts = pd.Timestamp(now or datetime.now(timezone.utc))
        if now_ts.tzinfo is not None:
            now_ts = now_ts.tz_convert("UTC").tz_localize(None)
        settled = 0
        pending = 0
        skipped: dict[str, int] = {}
        cache: dict[str, Any] = {}

        with self._locked():
            rows = self._read_unlocked()
            for row in rows:
                if row.get("outcome") is not None:
                    continue
                reference = row.get("reference_price")
                if reference is None:
                    skipped["missing_reference_price"] = skipped.get("missing_reference_price", 0) + 1
                    continue
                try:
                    reference_f = float(reference)
                except (TypeError, ValueError):
                    skipped["invalid_reference_price"] = skipped.get("invalid_reference_price", 0) + 1
                    continue
                if not (reference_f > 0):
                    skipped["invalid_reference_price"] = skipped.get("invalid_reference_price", 0) + 1
                    continue

                horizon = str(row.get("horizon") or "swing").lower()
                business_days = HORIZON_BUSINESS_DAYS.get(horizon)
                if business_days is None:
                    skipped["unknown_horizon"] = skipped.get("unknown_horizon", 0) + 1
                    continue
                try:
                    event_ts = pd.Timestamp(row.get("asof_utc") or row.get("recorded_at_utc"))
                    if event_ts.tzinfo is not None:
                        event_ts = event_ts.tz_convert("UTC").tz_localize(None)
                except Exception:
                    skipped["invalid_timestamp"] = skipped.get("invalid_timestamp", 0) + 1
                    continue
                maturity = (event_ts.normalize() + pd.offsets.BDay(business_days)).normalize()
                if now_ts < maturity:
                    pending += 1
                    continue

                symbol = str(row.get("symbol") or "").upper().replace(".US", "")
                if not symbol:
                    skipped["missing_symbol"] = skipped.get("missing_symbol", 0) + 1
                    continue
                if symbol not in cache:
                    path = bars_root / f"{symbol}.parquet"
                    if not path.exists():
                        cache[symbol] = None
                    else:
                        frame = pd.read_parquet(path).sort_index()
                        idx = pd.to_datetime(frame.index)
                        if getattr(idx, "tz", None) is not None:
                            idx = idx.tz_convert("UTC").tz_localize(None)
                        frame.index = idx
                        cache[symbol] = frame
                frame = cache[symbol]
                if frame is None or frame.empty:
                    skipped["missing_bars"] = skipped.get("missing_bars", 0) + 1
                    continue
                close_col = "close" if "close" in frame.columns else "Close" if "Close" in frame.columns else None
                if close_col is None:
                    skipped["missing_close"] = skipped.get("missing_close", 0) + 1
                    continue
                eligible = frame.loc[frame.index >= maturity, close_col].dropna()
                if eligible.empty or eligible.index[0] > now_ts:
                    pending += 1
                    continue
                exit_price = float(eligible.iloc[0])
                direction = -1.0 if str(row.get("direction") or "long").lower() == "short" else 1.0
                realized_return = direction * (exit_price / reference_f - 1.0)
                row.update(
                    {
                        "outcome": 1.0 if realized_return > 0 else 0.0,
                        "realized_return": realized_return,
                        "reference_price": reference_f,
                        "exit_price": exit_price,
                        "maturity_date": maturity.date().isoformat(),
                        "exit_bar_utc": pd.Timestamp(eligible.index[0]).isoformat(),
                        "settlement_source": "local_adjusted_daily",
                        "settled_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                )
                settled += 1
            if settled:
                self._write_unlocked(rows)
        return {"settled": settled, "pending": pending, "skipped": skipped, "events": len(rows)}

    def summary(self) -> dict[str, Any]:
        rows = self.read()
        settled = [r for r in rows if r.get("outcome") is not None]
        probabilities = [
            (float(r["calibrated_probability"]), float(r["outcome"]))
            for r in settled
            if r.get("calibrated_probability") is not None
        ]
        brier = (
            sum((probability - outcome) ** 2 for probability, outcome in probabilities) / len(probabilities)
            if probabilities
            else None
        )
        return {
            "path": str(self.path),
            "events": len(rows),
            "settled": len(settled),
            "mean_outcome": (sum(float(r["outcome"]) for r in settled) / len(settled)) if settled else None,
            "mean_realized_return": (
                sum(float(r["realized_return"]) for r in settled if r.get("realized_return") is not None)
                / max(1, sum(1 for r in settled if r.get("realized_return") is not None))
            ) if settled else None,
            "score_brier": brier,
            "score_brier_n": len(probabilities),
            "states": {state: sum(1 for r in rows if r.get("state") == state) for state in ("ENTER", "WATCH", "ABSTAIN")},
            "settled_states": {
                state: sum(1 for r in settled if r.get("state") == state)
                for state in ("ENTER", "WATCH", "ABSTAIN")
            },
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or settle shadow confidence decisions")
    parser.add_argument("--path", default=None)
    parser.add_argument("--settle")
    parser.add_argument("--outcome", type=float)
    parser.add_argument("--settle-due", action="store_true")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)
    ledger = ShadowDecisionLedger(args.path)
    if args.settle_due:
        print(json.dumps(ledger.settle_due(data_dir=args.data_dir), indent=2))
    elif args.settle:
        if args.outcome is None:
            parser.error("--outcome is required with --settle")
        print(json.dumps({"settled": ledger.settle(args.settle, outcome=args.outcome), "event_id": args.settle}, indent=2))
    else:
        print(json.dumps(ledger.summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
