"""Background polling: `SqueezeWatcher` (one thread per symbol) + `SqueezeManager`.

Each watcher owns a :class:`SqueezeEngine` and :class:`SqueezeStore` for one
symbol and polls ``fetch_fn`` on a fixed cadence, feeding results through the
engine and persisting every snapshot/alert. A watcher self-terminates if it
has not received a `heartbeat()` within `cfg.heartbeat_ttl_seconds` -- callers
(the API layer, via `SqueezeManager.watch`) are expected to heartbeat on every
client-visible touch of the symbol, so idle desks stop polling on their own.

`SqueezeManager` is the process-wide registry: one watcher thread per symbol,
started lazily on first `watch()`.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import SqueezeConfig
from .engine import SqueezeEngine
from .evaluator import resolve_pending, track_factor
from .snapshot import SqueezeSnapshot
from .store import SqueezeStore

ROOT = Path(__file__).resolve().parents[3]

_DIVERGENCE_MARKER = "differs from trusted spot"


class SqueezeWatcher(threading.Thread):
    """Polls one symbol's gamma chain on `cfg.poll_seconds` cadence.

    Thread-safe: all mutable state is behind `self._lock`; `state()` may be
    called from any thread (typically the API request thread) while the
    watcher's own `run()` loop mutates that state on its own thread.
    """

    def __init__(
        self,
        symbol: str,
        cfg: SqueezeConfig,
        fetch_fn: Callable[[str], tuple[dict, bool]],
        store_root: Path | str | None = None,
        clock: Callable[[], float] = time.time,
        tick_wait: float | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"squeeze-watcher-{symbol.upper()}")
        self.symbol = symbol.upper()
        self.cfg = cfg
        self.fetch_fn = fetch_fn
        self._clock = clock
        self._tick_wait = tick_wait

        self._store = SqueezeStore(self.symbol, root=store_root)
        self._engine = SqueezeEngine(cfg)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        now = self._clock()
        self._last_heartbeat = now
        self._last_success_ts: float | None = None
        self._last_result: dict | None = None
        self._last_step = None
        self._last_snap: SqueezeSnapshot | None = None
        self._consecutive_failures = 0
        self._rejected_snapshots = 0
        self._backoff = float(cfg.poll_seconds)
        self._error: str | None = None

    # -- public API -----------------------------------------------------

    def heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat = self._clock()

    def request_stop(self) -> None:
        self._stop_event.set()

    def state(self) -> dict:
        now = self._clock()
        with self._lock:
            last_heartbeat = self._last_heartbeat
            last_success_ts = self._last_success_ts
            result = self._last_result or {}
            step = self._last_step
            snap = self._last_snap
            consecutive_failures = self._consecutive_failures
            rejected_snapshots = self._rejected_snapshots
            error = self._error

        watch_expires_in = max(0.0, self.cfg.heartbeat_ttl_seconds - (now - last_heartbeat))
        timeline = self._store.timeline(since_ts=now - 8 * 3600)
        ledger_stats = self._store.stats()
        alerts_today = self._store.alerts_since(since_ts=now - 24 * 3600)

        if step is None or snap is None:
            return {
                "symbol": self.symbol,
                "phase": "none",
                "direction": "none",
                "phase_seconds": 0.0,
                "score": 0.0,
                "structural": 0.0,
                "dynamic": 0.0,
                "confidence": 0.0,
                "confidence_parts": {},
                "components": {},
                "spot": None,
                "call_wall": None,
                "put_wall": None,
                "flip": None,
                "regime": None,
                "net_dealer_gex": None,
                "near_spot_dealer_gex": None,
                "expected_move_pct": None,
                "by_strike": [],
                "feed": "degraded",
                "stale": True,
                "last_poll_ts": None,
                "poll_age_seconds": None,
                "consecutive_failures": consecutive_failures,
                "rejected_snapshots": rejected_snapshots,
                "watch_expires_in": watch_expires_in,
                "timeline": timeline,
                "ledger_stats": ledger_stats,
                "alerts_today": alerts_today,
                "error": error,
                "asof": None,
            }

        poll_age_seconds = now - last_success_ts if last_success_ts is not None else None
        stale = poll_age_seconds is None or poll_age_seconds > (
            self.cfg.stale_after_polls * self.cfg.poll_seconds
        )
        asof = (
            datetime.fromtimestamp(last_success_ts, tz=timezone.utc).isoformat()
            if last_success_ts is not None
            else None
        )

        return {
            "symbol": self.symbol,
            "phase": step.phase,
            "direction": step.direction,
            "phase_seconds": step.phase_seconds,
            "score": step.score,
            "structural": step.structural,
            "dynamic": step.dynamic,
            "confidence": step.confidence,
            "confidence_parts": step.confidence_parts,
            "components": step.components,
            "spot": snap.spot,
            "call_wall": snap.call_wall,
            "put_wall": snap.put_wall,
            "flip": snap.flip,
            "regime": "positive_gamma" if snap.near_net >= 0 else "negative_gamma",
            "net_dealer_gex": snap.net_dealer,
            "near_spot_dealer_gex": snap.near_net,
            "expected_move_pct": snap.expected_move_pct,
            "by_strike": result.get("by_strike", []),
            "feed": "degraded" if snap.degraded else "lse",
            "stale": stale,
            "last_poll_ts": last_success_ts,
            "poll_age_seconds": poll_age_seconds,
            "consecutive_failures": consecutive_failures,
            "rejected_snapshots": rejected_snapshots,
            "watch_expires_in": watch_expires_in,
            "timeline": timeline,
            "ledger_stats": ledger_stats,
            "alerts_today": alerts_today,
            "error": error,
            "asof": asof,
        }

    # -- thread body ------------------------------------------------------

    def run(self) -> None:
        while not self._stop_event.is_set():
            now = self._clock()
            with self._lock:
                last_heartbeat = self._last_heartbeat
            if now - last_heartbeat > self.cfg.heartbeat_ttl_seconds:
                break

            self._poll_once()

            wait_seconds = self._tick_wait if self._tick_wait is not None else self._current_wait()
            if self._stop_event.wait(wait_seconds):
                break

        self._store.close()

    def _current_wait(self) -> float:
        with self._lock:
            if self._consecutive_failures > 0:
                return self._backoff
            return float(self.cfg.poll_seconds)

    def _poll_once(self) -> None:
        try:
            fetch_start = self._clock()
            result, degraded = self.fetch_fn(self.symbol)
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
            fetch_end = self._clock()
            chain_age_minutes = max(0.0, (fetch_end - fetch_start) / 60.0)

            snap = SqueezeSnapshot.from_gamma_result(result, ts=fetch_end, degraded=degraded)
            track = track_factor(self._store.stats(), self.cfg)
            step = self._engine.step(
                snap, track_factor=track, chain_age_minutes=chain_age_minutes
            )
            self._store.append(snap, step, self.cfg.weights_json())
            for alert in step.alerts:
                self._store.insert_alert(alert)
            resolve_pending(self._store, self.cfg, fetch_end)

            with self._lock:
                self._last_success_ts = fetch_end
                self._last_result = result
                self._last_step = step
                self._last_snap = snap
                self._consecutive_failures = 0
                self._backoff = float(self.cfg.poll_seconds)
                self._error = None
        except Exception as exc:  # noqa: BLE001 - watcher must never die on a bad poll
            message = str(exc)
            with self._lock:
                if _DIVERGENCE_MARKER in message:
                    self._rejected_snapshots += 1
                else:
                    self._consecutive_failures += 1
                    self._backoff = min(
                        self._backoff * 2.0, float(self.cfg.max_backoff_seconds)
                    )
                self._error = message


class SqueezeManager:
    """Process-wide registry of `SqueezeWatcher` threads, one per symbol."""

    def __init__(
        self,
        cfg: SqueezeConfig | None = None,
        fetch_fn: Callable[[str], tuple[dict, bool]] | None = None,
        store_root: Path | str | None = None,
    ) -> None:
        self.cfg = cfg or SqueezeConfig()
        self.fetch_fn = fetch_fn or default_fetch
        self.store_root = store_root
        self._lock = threading.Lock()
        self._watchers: dict[str, SqueezeWatcher] = {}

    def watch(self, symbol: str) -> dict:
        sym = symbol.upper()
        with self._lock:
            watcher = self._watchers.get(sym)
            if watcher is None or not watcher.is_alive():
                watcher = SqueezeWatcher(
                    sym,
                    self.cfg,
                    self.fetch_fn,
                    store_root=self.store_root,
                )
                self._watchers[sym] = watcher
                watcher.start()
            watcher.heartbeat()
        return watcher.state()

    def state(self, symbol: str) -> dict | None:
        watcher = self._watchers.get(symbol.upper())
        if watcher is None:
            return None
        return watcher.state()

    def ledger(self, symbol: str) -> dict | None:
        watcher = self._watchers.get(symbol.upper())
        if watcher is None:
            return None
        st = watcher.state()
        return {"alerts": st["alerts_today"], "stats": st["ledger_stats"]}

    def stop_all(self) -> None:
        with self._lock:
            watchers = list(self._watchers.values())
        for watcher in watchers:
            watcher.request_stop()
        for watcher in watchers:
            watcher.join(timeout=5)


def default_fetch(symbol: str) -> tuple[dict, bool]:
    """Imports tools.gamma_exposure.compute_gamma_exposure; degraded = result source != 'lse'."""
    for path in (str(ROOT), str(ROOT / "tools"), str(ROOT / "services")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from gamma_exposure import compute_gamma_exposure

    result = compute_gamma_exposure(symbol, spot_source="auto", source="auto")
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    degraded = str(result.get("source") or "") != "lse"
    return result, degraded
