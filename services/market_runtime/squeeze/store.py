"""SQLite-backed persistence for the squeeze engine.

One database per symbol at ``data_cache/squeeze/{SYMBOL}.sqlite`` (or a
caller-supplied ``root``, used by tests and the replay harness). Stores
every snapshot, every phase-transition alert, and every resolved outcome
so the desk has a durable track record and ``replay.py`` has ground truth
to regress the engine against.

Thread-safe: one ``sqlite3`` connection (``check_same_thread=False``, WAL
journal mode) guarded by a single ``threading.Lock`` for every access —
reads included, since sqlite3 connections are not safe for concurrent use
across threads even for SELECTs.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .engine import StepResult
from .snapshot import SqueezeSnapshot

REPO_ROOT = Path(__file__).resolve().parents[3]

_DDL = """
CREATE TABLE IF NOT EXISTS snapshots(
  ts REAL PRIMARY KEY, spot REAL NOT NULL, score REAL NOT NULL,
  structural REAL NOT NULL, dynamic REAL NOT NULL, phase TEXT NOT NULL,
  direction TEXT NOT NULL, confidence REAL NOT NULL, components TEXT NOT NULL,
  weights TEXT NOT NULL, degraded INTEGER NOT NULL, n_contracts INTEGER NOT NULL,
  snap_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, direction TEXT NOT NULL,
  transition TEXT NOT NULL, score REAL NOT NULL, spot REAL NOT NULL,
  confidence REAL NOT NULL, components TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes(
  alert_id INTEGER NOT NULL, horizon_min INTEGER NOT NULL,
  realized_ret_pct REAL NOT NULL, hit INTEGER NOT NULL, resolved_ts REAL NOT NULL,
  PRIMARY KEY(alert_id, horizon_min));
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
"""


class SqueezeStore:
    """Durable per-symbol store: snapshots, alerts, and resolved outcomes."""

    def __init__(self, symbol: str, root: Path | str | None = None) -> None:
        self.symbol = symbol.upper()
        base = Path(root) if root is not None else REPO_ROOT / "data_cache" / "squeeze"
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / f"{self.symbol}.sqlite"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_DDL)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def append(self, snap: SqueezeSnapshot, step: StepResult, weights_json: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO snapshots
                   (ts, spot, score, structural, dynamic, phase, direction, confidence,
                    components, weights, degraded, n_contracts, snap_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    step.ts,
                    snap.spot,
                    step.score,
                    step.structural,
                    step.dynamic,
                    step.phase,
                    step.direction,
                    step.confidence,
                    json.dumps(step.components, sort_keys=True),
                    weights_json,
                    1 if snap.degraded else 0,
                    snap.n_contracts,
                    snap.to_json(),
                ),
            )
            self._conn.commit()

    def insert_alert(self, alert: dict) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO alerts (ts, direction, transition, score, spot, confidence, components)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    alert["ts"],
                    alert["direction"],
                    alert["transition"],
                    alert["score"],
                    alert["spot"],
                    alert["confidence"],
                    json.dumps(alert.get("components", {}), sort_keys=True),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def alerts_without_outcome(self, horizon_min: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT a.* FROM alerts a
                   LEFT JOIN outcomes o ON o.alert_id = a.id AND o.horizon_min = ?
                   WHERE o.alert_id IS NULL
                   ORDER BY a.ts ASC""",
                (horizon_min,),
            ).fetchall()
        return [self._alert_row_to_dict(r) for r in rows]

    def insert_outcome(
        self,
        alert_id: int,
        horizon_min: int,
        realized_ret_pct: float,
        hit: bool,
        resolved_ts: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO outcomes
                   (alert_id, horizon_min, realized_ret_pct, hit, resolved_ts)
                   VALUES (?,?,?,?,?)""",
                (alert_id, horizon_min, realized_ret_pct, 1 if hit else 0, resolved_ts),
            )
            self._conn.commit()

    def spot_at_or_after(
        self, ts: float, not_after: float | None = None
    ) -> tuple[float, float] | None:
        query = "SELECT ts, spot FROM snapshots WHERE ts >= ?"
        params: list[float] = [ts]
        if not_after is not None:
            query += " AND ts <= ?"
            params.append(not_after)
        query += " ORDER BY ts ASC LIMIT 1"
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return (row["ts"], row["spot"]) if row is not None else None

    def last_spot_of_day(
        self, day_start_ts: float, day_end_ts: float
    ) -> tuple[float, float] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT ts, spot FROM snapshots WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
                (day_start_ts, day_end_ts),
            ).fetchone()
        return (row["ts"], row["spot"]) if row is not None else None

    def timeline(self, since_ts: float) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, score, phase, direction, spot FROM snapshots WHERE ts >= ? ORDER BY ts ASC",
                (since_ts,),
            ).fetchall()
        return [
            {
                "ts": r["ts"],
                "score": r["score"],
                "phase": r["phase"],
                "direction": r["direction"],
                "spot": r["spot"],
            }
            for r in rows
        ]

    def snapshots_between(self, t0: float, t1: float) -> list[SqueezeSnapshot]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT snap_json FROM snapshots WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
                (t0, t1),
            ).fetchall()
        return [SqueezeSnapshot.from_json(r["snap_json"]) for r in rows]

    def alerts_since(self, since_ts: float) -> list[dict]:
        with self._lock:
            alert_rows = self._conn.execute(
                "SELECT * FROM alerts WHERE ts >= ? ORDER BY ts ASC", (since_ts,)
            ).fetchall()
            out = []
            for r in alert_rows:
                d = self._alert_row_to_dict(r)
                outcome_rows = self._conn.execute(
                    """SELECT horizon_min, realized_ret_pct, hit, resolved_ts
                       FROM outcomes WHERE alert_id = ? ORDER BY horizon_min ASC""",
                    (r["id"],),
                ).fetchall()
                d["outcomes"] = [
                    {
                        "horizon_min": o["horizon_min"],
                        "realized_ret_pct": o["realized_ret_pct"],
                        "hit": bool(o["hit"]),
                        "resolved_ts": o["resolved_ts"],
                    }
                    for o in outcome_rows
                ]
                out.append(d)
        return out

    def stats(self) -> dict:
        with self._lock:
            alerts_total = self._conn.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()["n"]
            resolved_total = self._conn.execute("SELECT COUNT(*) AS n FROM outcomes").fetchone()["n"]

            by_horizon: dict[str, dict] = {}
            for row in self._conn.execute(
                "SELECT horizon_min, COUNT(*) AS n, SUM(hit) AS hits FROM outcomes GROUP BY horizon_min"
            ):
                n = row["n"]
                hits = row["hits"] or 0
                by_horizon[str(row["horizon_min"])] = {
                    "n": n,
                    "hits": hits,
                    "hit_rate": (hits / n) if n else None,
                }

            by_direction: dict[str, dict] = {}
            for row in self._conn.execute(
                """SELECT a.direction AS direction, COUNT(*) AS n, SUM(o.hit) AS hits
                   FROM outcomes o JOIN alerts a ON a.id = o.alert_id
                   GROUP BY a.direction"""
            ):
                n = row["n"]
                hits = row["hits"] or 0
                by_direction[row["direction"]] = {
                    "n": n,
                    "hits": hits,
                    "hit_rate": (hits / n) if n else None,
                }

            avg_row = self._conn.execute(
                "SELECT AVG(realized_ret_pct) AS avg_fav FROM outcomes WHERE hit = 1"
            ).fetchone()
            worst_row = self._conn.execute(
                "SELECT MIN(realized_ret_pct) AS worst FROM outcomes"
            ).fetchone()

        return {
            "alerts_total": alerts_total,
            "resolved_total": resolved_total,
            "by_horizon": by_horizon,
            "by_direction": by_direction,
            "avg_favorable_pct": avg_row["avg_fav"],
            "worst_adverse_pct": worst_row["worst"],
        }

    @staticmethod
    def _alert_row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "ts": row["ts"],
            "direction": row["direction"],
            "transition": row["transition"],
            "score": row["score"],
            "spot": row["spot"],
            "confidence": row["confidence"],
            "components": json.loads(row["components"]),
        }
