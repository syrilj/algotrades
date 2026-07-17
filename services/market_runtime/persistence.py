from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import List, Optional

from .contracts import Tick


class TickPersistence:
    def __init__(self, path: str = ":memory:", commit_every: int = 100) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._commit_every = max(1, int(commit_every))
        self._pending = 0

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ticks (
                    instrument_id TEXT NOT NULL,
                    price REAL NOT NULL,
                    size REAL NOT NULL,
                    market_asof TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    event_id TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ticks_instrument_time "
                "ON ticks (instrument_id, market_asof DESC)"
            )
            self._conn.commit()
        return self._conn

    def append(self, tick: Tick) -> None:
        with self._lock:
            self._connection().execute(
                "INSERT INTO ticks VALUES (?, ?, ?, ?, ?, ?)",
                (
                    tick.instrument_id,
                    tick.price,
                    tick.size,
                    tick.market_asof.isoformat(),
                    tick.received_at.isoformat(),
                    tick.event_id,
                ),
            )
            self._pending += 1
            if self._pending >= self._commit_every:
                self.flush()

    def flush(self) -> None:
        """Durably commit pending ticks without reopening the database."""
        with self._lock:
            if self._conn is not None and self._pending:
                self._conn.commit()
                self._pending = 0

    def query(self, instrument_id: str, limit: int = 1000) -> List[Tick]:
        with self._lock:
            rows = self._connection().execute(
                "SELECT instrument_id, price, size, market_asof, received_at, event_id "
                "FROM ticks WHERE instrument_id = ? ORDER BY market_asof DESC LIMIT ?",
                (instrument_id, limit),
            ).fetchall()
        return [
            Tick(
                instrument_id=row[0],
                price=row[1],
                size=row[2],
                market_asof=datetime.fromisoformat(row[3]),
                received_at=datetime.fromisoformat(row[4]),
                event_id=row[5],
            )
            for row in reversed(rows)
        ]

    def prune_before(self, cutoff: datetime) -> int:
        """Apply an explicit retention boundary and return deleted row count."""
        with self._lock:
            cursor = self._connection().execute(
                "DELETE FROM ticks WHERE market_asof < ?", (cutoff.isoformat(),)
            )
            self._connection().commit()
            self._pending = 0
            return max(0, int(cursor.rowcount))

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                if self._pending:
                    self._conn.commit()
                self._conn.close()
                self._conn = None
                self._pending = 0

    def __enter__(self) -> "TickPersistence":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False
