import time

from services.market_runtime.squeeze import SqueezeConfig, SqueezeManager
from services.market_runtime.squeeze.store import SqueezeStore
from services.market_runtime.squeeze.watcher import SqueezeWatcher

GAMMA_RESULT = {
    "spot": 100.0,
    "squeeze_score": 30.0,
    "squeeze_components": {"regime_score": 10.0},
    "call_wall": 103.0,
    "put_wall": 90.0,
    "call_wall_gex": 3e9,
    "put_wall_gex": 1e9,
    "approx_flip_strike": 98.0,
    "near_spot_dealer_gex": -5e9,
    "net_dealer_gex": -6e9,
    "otm_call_volume": 400.0,
    "otm_put_volume": 100.0,
    "expected_move_pct": 4.0,
    "n_contracts": 250,
    "by_strike": [
        {"strike": 103.0, "net_gex": -3e9, "call_gex": -3e9, "put_gex": 0.0},
        {"strike": 90.0, "net_gex": -1e9, "call_gex": 0.0, "put_gex": -1e9},
    ],
    "source": "lse",
}


def _ok_fetch(symbol):
    return dict(GAMMA_RESULT), False


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_watcher_ticks_persist_snapshots_and_update_state(tmp_path):
    cfg = SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=5)
    watcher = SqueezeWatcher("TSLA", cfg, _ok_fetch, store_root=tmp_path, tick_wait=0.01)
    watcher.start()
    try:
        assert _wait_until(lambda: watcher.state()["score"] != 0.0)
        # give it a few more fast ticks so more than one snapshot lands
        time.sleep(0.2)
        st = watcher.state()
        assert st["score"] != 0.0
        assert st["feed"] == "lse"
        assert st["spot"] == 100.0
        assert st["error"] is None
    finally:
        watcher.request_stop()
        watcher.join(timeout=5)

    store = SqueezeStore("TSLA", root=tmp_path)
    rows = store.timeline(since_ts=0.0)
    assert len(rows) > 1
    store.close()


def test_ttl_expiry_stops_watcher_without_heartbeat(tmp_path):
    cfg = SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=1)
    watcher = SqueezeWatcher("TSLA", cfg, _ok_fetch, store_root=tmp_path, tick_wait=0.01)
    watcher.start()
    # No heartbeat() calls after start -> watcher should self-terminate once
    # clock() - last_heartbeat exceeds heartbeat_ttl_seconds.
    watcher.join(timeout=5)
    assert not watcher.is_alive()


def test_fetch_failure_increments_consecutive_failures_and_keeps_alive(tmp_path):
    def failing_fetch(symbol):
        raise ValueError("boom")

    cfg = SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=60)
    watcher = SqueezeWatcher(
        "TSLA", cfg, failing_fetch, store_root=tmp_path, tick_wait=5.0
    )
    watcher.start()
    try:
        assert _wait_until(lambda: watcher.state()["consecutive_failures"] >= 1)
        st = watcher.state()
        assert st["consecutive_failures"] == 1
        assert st["error"] is not None and "boom" in st["error"]
        assert st["rejected_snapshots"] == 0
        assert watcher.is_alive()
    finally:
        watcher.request_stop()
        watcher.join(timeout=5)


def test_divergence_error_counts_as_rejected_not_failure(tmp_path):
    def diverging_fetch(symbol):
        raise RuntimeError("spot 105.0 differs from trusted spot 100.0")

    cfg = SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=60)
    watcher = SqueezeWatcher(
        "TSLA", cfg, diverging_fetch, store_root=tmp_path, tick_wait=5.0
    )
    watcher.start()
    try:
        assert _wait_until(lambda: watcher.state()["rejected_snapshots"] >= 1)
        st = watcher.state()
        assert st["rejected_snapshots"] == 1
        assert st["consecutive_failures"] == 0
    finally:
        watcher.request_stop()
        watcher.join(timeout=5)


def test_manager_watch_starts_single_thread_and_lookup(tmp_path):
    manager = SqueezeManager(
        cfg=SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=60),
        fetch_fn=_ok_fetch,
        store_root=tmp_path,
    )
    state1 = manager.watch("tsla")
    watcher1 = manager._watchers["TSLA"]
    state2 = manager.watch("TSLA")
    watcher2 = manager._watchers["TSLA"]

    assert watcher1 is watcher2
    assert len(manager._watchers) == 1
    assert state1["symbol"] == "TSLA"
    assert state2["symbol"] == "TSLA"

    manager.stop_all()
    assert not watcher1.is_alive()


def test_manager_state_and_ledger_none_for_unwatched_symbol(tmp_path):
    manager = SqueezeManager(
        cfg=SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=60),
        fetch_fn=_ok_fetch,
        store_root=tmp_path,
    )
    assert manager.state("UNKNOWN") is None
    assert manager.ledger("UNKNOWN") is None

    manager.watch("TSLA")
    try:
        ledger = manager.ledger("TSLA")
        assert set(ledger.keys()) == {"alerts", "stats"}
        assert isinstance(ledger["alerts"], list)
        assert isinstance(ledger["stats"], dict)
    finally:
        manager.stop_all()
