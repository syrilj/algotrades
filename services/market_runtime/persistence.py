from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import List, Optional

from .contracts import Tick


class TickPersistence:
    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
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
                "CREATE INDEX IF NOT EXISTS idx_ticks_instrument ON ticks (instrument_id)"
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
            self._connection().commit()

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

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "TickPersistence":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False
