"""Exactly-once completed-bar replay state for adaptive signal engines.

The online router can be reconstructed deterministically from an immutable,
fixed-anchor bar ledger.  This is intentionally simpler and safer than saving
opaque in-memory model objects: restarts replay the same frozen bundle over the
same ordered inputs, while duplicate or out-of-order market events fail closed.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


SCHEMA_VERSION = "adaptive-replay-v1"
OHLCV = ("open", "high", "low", "close", "volume")


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("market_asof must include an explicit timezone")
    return timestamp.tz_convert("UTC")


def _finite(value: Any, name: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or (positive and number <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return number


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _payload_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class AdaptiveReplayStore:
    """SQLite WAL ledger scoped to one model and frozen dependency bundle."""

    def __init__(
        self,
        path: str | Path,
        *,
        model: str,
        bundle_hash: str,
        anchor: Any,
    ) -> None:
        self.path = str(path)
        self.model = str(model)
        self.bundle_hash = str(bundle_hash)
        if not self.model or not self.bundle_hash:
            raise ValueError("model and bundle_hash are required")
        self.anchor = _utc_timestamp(anchor)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            parent = Path(self.path).expanduser().resolve().parent
            parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, check_same_thread=False)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS adaptive_bars (
                    model TEXT NOT NULL,
                    bundle_hash TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_asof TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    source TEXT NOT NULL,
                    event_id TEXT,
                    payload_hash TEXT NOT NULL,
                    PRIMARY KEY (model, bundle_hash, symbol, market_asof)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_adaptive_bar_event
                    ON adaptive_bars(model, bundle_hash, source, event_id)
                    WHERE event_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_adaptive_bar_order
                    ON adaptive_bars(model, bundle_hash, symbol, market_asof);

                CREATE TABLE IF NOT EXISTS adaptive_decisions (
                    model TEXT NOT NULL,
                    bundle_hash TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_asof TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    PRIMARY KEY (model, bundle_hash, symbol, market_asof)
                );
                """
            )
            connection.commit()
            self._connection = connection
        return self._connection

    def append_completed_bar(
        self,
        symbol: str,
        market_asof: Any,
        values: Mapping[str, Any],
        *,
        source: str,
        event_id: str | None = None,
        complete: bool = True,
    ) -> bool:
        """Append one completed bar; return False for an identical duplicate."""
        if not complete:
            raise ValueError("incomplete bars cannot enter adaptive state")
        normalized_symbol = str(symbol).strip().upper()
        normalized_source = str(source).strip().lower()
        if not normalized_symbol or not normalized_source:
            raise ValueError("symbol and source are required")
        timestamp = _utc_timestamp(market_asof)
        if timestamp < self.anchor:
            raise ValueError("bar predates the fixed replay anchor")
        numbers = {
            "open": _finite(values.get("open"), "open", positive=True),
            "high": _finite(values.get("high"), "high", positive=True),
            "low": _finite(values.get("low"), "low", positive=True),
            "close": _finite(values.get("close"), "close", positive=True),
            "volume": _finite(values.get("volume"), "volume"),
        }
        if numbers["volume"] < 0.0:
            raise ValueError("volume must be non-negative")
        if numbers["low"] > min(numbers["open"], numbers["close"], numbers["high"]):
            raise ValueError("low is inconsistent with OHLC")
        if numbers["high"] < max(numbers["open"], numbers["close"], numbers["low"]):
            raise ValueError("high is inconsistent with OHLC")
        asof_text = timestamp.isoformat()
        payload = {
            "symbol": normalized_symbol,
            "market_asof": asof_text,
            **numbers,
            "source": normalized_source,
            "event_id": str(event_id) if event_id is not None else None,
        }
        digest = _payload_hash(payload)

        with self._lock:
            connection = self._conn()
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT payload_hash FROM adaptive_bars "
                    "WHERE model=? AND bundle_hash=? AND symbol=? AND market_asof=?",
                    (self.model, self.bundle_hash, normalized_symbol, asof_text),
                ).fetchone()
                if existing is not None:
                    if str(existing[0]) != digest:
                        raise ValueError("conflicting duplicate bar")
                    connection.rollback()
                    return False
                latest = connection.execute(
                    "SELECT MAX(market_asof) FROM adaptive_bars "
                    "WHERE model=? AND bundle_hash=? AND symbol=?",
                    (self.model, self.bundle_hash, normalized_symbol),
                ).fetchone()[0]
                if latest is not None and timestamp <= pd.Timestamp(latest):
                    raise ValueError("out-of-order completed bar")
                connection.execute(
                    "INSERT INTO adaptive_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        self.model,
                        self.bundle_hash,
                        normalized_symbol,
                        asof_text,
                        numbers["open"],
                        numbers["high"],
                        numbers["low"],
                        numbers["close"],
                        numbers["volume"],
                        normalized_source,
                        str(event_id) if event_id is not None else None,
                        digest,
                    ),
                )
                connection.commit()
                return True
            except Exception:
                connection.rollback()
                raise

    def load_frames(self, symbols: Iterable[str] | None = None) -> dict[str, pd.DataFrame]:
        selected = {str(symbol).strip().upper() for symbol in symbols or [] if str(symbol).strip()}
        params: list[Any] = [self.model, self.bundle_hash]
        where = "model=? AND bundle_hash=?"
        if selected:
            placeholders = ",".join("?" for _ in selected)
            where += f" AND symbol IN ({placeholders})"
            params.extend(sorted(selected))
        with self._lock:
            rows = self._conn().execute(
                "SELECT symbol, market_asof, open, high, low, close, volume "
                f"FROM adaptive_bars WHERE {where} ORDER BY symbol, market_asof",
                params,
            ).fetchall()
        grouped: dict[str, list[tuple[Any, ...]]] = {}
        for row in rows:
            grouped.setdefault(str(row[0]), []).append(row)
        frames: dict[str, pd.DataFrame] = {}
        for symbol, values in grouped.items():
            index = pd.DatetimeIndex([pd.Timestamp(row[1]) for row in values])
            frames[symbol] = pd.DataFrame(
                [[float(value) for value in row[2:]] for row in values],
                index=index,
                columns=OHLCV,
            )
        return frames

    def input_hash(self) -> str:
        with self._lock:
            rows = self._conn().execute(
                "SELECT symbol, market_asof, payload_hash FROM adaptive_bars "
                "WHERE model=? AND bundle_hash=? ORDER BY symbol, market_asof",
                (self.model, self.bundle_hash),
            ).fetchall()
        return _payload_hash([list(row) for row in rows])

    def append_decision(self, payload: Mapping[str, Any]) -> bool:
        symbol = str(payload.get("symbol") or "").strip().upper()
        timestamp = _utc_timestamp(payload.get("market_asof"))
        input_hash = str(payload.get("input_hash") or "")
        if not symbol or not input_hash:
            raise ValueError("decision symbol and input_hash are required")
        body = dict(payload)
        body["symbol"] = symbol
        body["market_asof"] = timestamp.isoformat()
        body["model"] = self.model
        body["bundle_hash"] = self.bundle_hash
        body["schema_version"] = SCHEMA_VERSION
        text = _canonical_json(body)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            connection = self._conn()
            existing = connection.execute(
                "SELECT payload_hash FROM adaptive_decisions "
                "WHERE model=? AND bundle_hash=? AND symbol=? AND market_asof=?",
                (self.model, self.bundle_hash, symbol, timestamp.isoformat()),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != digest:
                    raise ValueError("conflicting duplicate adaptive decision")
                return False
            connection.execute(
                "INSERT INTO adaptive_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self.model,
                    self.bundle_hash,
                    symbol,
                    timestamp.isoformat(),
                    input_hash,
                    text,
                    digest,
                ),
            )
            connection.commit()
            return True

    def decisions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = [self.model, self.bundle_hash]
        where = "model=? AND bundle_hash=?"
        if symbol:
            where += " AND symbol=?"
            params.append(str(symbol).strip().upper())
        with self._lock:
            rows = self._conn().execute(
                f"SELECT payload_json FROM adaptive_decisions WHERE {where} "
                "ORDER BY market_asof",
                params,
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> "AdaptiveReplayStore":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.close()
        return False


def _last_mapping_value(engine: Any, attribute: str, symbol: str, default: Any) -> Any:
    mapping = getattr(engine, attribute, None)
    if not isinstance(mapping, Mapping):
        return default
    value = mapping.get(symbol)
    if value is None:
        return default
    series = pd.Series(value).dropna()
    return series.iloc[-1] if not series.empty else default


def replay_latest_decisions(
    engine: Any,
    store: AdaptiveReplayStore,
    target_symbols: Iterable[str],
    *,
    options_context: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Replay frozen state and append idempotent latest-bar decisions."""
    engine_bundle = str(getattr(engine, "bundle_hash", ""))
    if engine_bundle != store.bundle_hash:
        raise ValueError("engine bundle hash does not match replay state")
    contexts = options_context or {}
    for symbol, context in contexts.items():
        if context.get("actionable") is True or str(context.get("bias", "neutral")) != "neutral":
            raise ValueError(f"directional options inference is forbidden for {symbol}")

    frames = store.load_frames()
    if not frames:
        raise ValueError("adaptive replay ledger has no bars")
    signals = engine.generate(frames)
    input_hash = store.input_hash()
    decisions: list[dict[str, Any]] = []
    for raw_symbol in target_symbols:
        symbol = str(raw_symbol).strip().upper()
        frame = frames.get(symbol)
        signal = signals.get(symbol) if isinstance(signals, Mapping) else None
        if frame is None or frame.empty or signal is None:
            continue
        series = pd.Series(signal).reindex(frame.index).dropna()
        if series.empty:
            continue
        market_asof = _utc_timestamp(series.index[-1])
        decision = {
            "symbol": symbol,
            "market_asof": market_asof.isoformat(),
            "input_hash": input_hash,
            "target_weight": _finite(series.iloc[-1], "target_weight"),
            "expert": str(_last_mapping_value(engine, "last_expert", symbol, "CASH")),
            "ordinal_support": _finite(
                _last_mapping_value(engine, "last_confidence", symbol, 0.0),
                "ordinal_support",
            ),
            "confidence_kind": str(
                getattr(engine, "confidence_kind", "ordinal_score_not_probability")
            ),
            "context_quality": _finite(
                _last_mapping_value(engine, "last_context_quality", symbol, 0.0),
                "context_quality",
            ),
            "context_evidence": int(
                _last_mapping_value(engine, "last_evidence", symbol, 0)
            ),
            "regime": int(_last_mapping_value(engine, "last_regime", symbol, -1)),
            "options_observation": contexts.get(symbol),
        }
        decision["inserted"] = store.append_decision(decision)
        decisions.append(decision)
    return decisions
