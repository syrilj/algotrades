from services.market_runtime.squeeze import SqueezeConfig, SqueezeEngine, SqueezeSnapshot
from services.market_runtime.squeeze.store import SqueezeStore


def snap(ts, structural=0.0, spot=100.0, degraded=False, n_contracts=250):
    return SqueezeSnapshot(
        ts=ts, spot=spot, structural_score=structural, structural_components={"regime_score": 1.0},
        call_wall=102.0, put_wall=95.0, call_wall_gex=1e9, put_wall_gex=1e9,
        flip=98.0, near_net=-5e9, net_dealer=-6e9, abs_book=4e9,
        otm_call_volume=0.0, otm_put_volume=0.0, expected_move_pct=4.0,
        n_contracts=n_contracts, degraded=degraded,
    )


def _append(store, engine, ts, **kw):
    s = snap(ts, **kw)
    step = engine.step(s)
    store.append(s, step, engine.cfg.weights_json())
    return s, step


BULL_ALERT = {
    "ts": 1000.0,
    "direction": "bull",
    "transition": "enter_building",
    "score": 30.0,
    "spot": 100.0,
    "confidence": 80.0,
    "components": {"wall_build_score": 5.0},
}


def test_append_persists_snapshot_row_visible_in_timeline(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(SqueezeConfig())
    s, step = _append(store, engine, 1000.0, structural=40.0)

    rows = store.timeline(since_ts=0.0)
    assert len(rows) == 1
    assert rows[0]["ts"] == 1000.0
    assert rows[0]["score"] == step.score
    assert rows[0]["phase"] == step.phase
    assert rows[0]["direction"] == step.direction
    assert rows[0]["spot"] == s.spot
    store.close()


def test_insert_alert_and_alerts_without_outcome(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    alert_id = store.insert_alert(BULL_ALERT)
    assert isinstance(alert_id, int) and alert_id > 0

    pending = store.alerts_without_outcome(30)
    assert len(pending) == 1
    assert pending[0]["id"] == alert_id
    assert pending[0]["direction"] == "bull"
    assert pending[0]["transition"] == "enter_building"
    assert pending[0]["components"] == {"wall_build_score": 5.0}
    store.close()


def test_insert_outcome_clears_pending_and_updates_stats(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    alert_id = store.insert_alert(BULL_ALERT)

    store.insert_outcome(alert_id, 30, realized_ret_pct=0.5, hit=True, resolved_ts=2000.0)

    assert store.alerts_without_outcome(30) == []

    stats = store.stats()
    assert stats["alerts_total"] == 1
    assert stats["resolved_total"] == 1
    assert stats["by_horizon"]["30"] == {"n": 1, "hits": 1, "hit_rate": 1.0}
    store.close()


def test_stats_by_direction_and_extremes(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    bull_id = store.insert_alert(BULL_ALERT)
    bear_alert = dict(BULL_ALERT, ts=1500.0, direction="bear", transition="enter_building")
    bear_id = store.insert_alert(bear_alert)

    store.insert_outcome(bull_id, 30, realized_ret_pct=0.5, hit=True, resolved_ts=2000.0)
    store.insert_outcome(bear_id, 30, realized_ret_pct=-0.9, hit=False, resolved_ts=2500.0)

    stats = store.stats()
    assert stats["by_direction"]["bull"] == {"n": 1, "hits": 1, "hit_rate": 1.0}
    assert stats["by_direction"]["bear"] == {"n": 1, "hits": 0, "hit_rate": 0.0}
    assert stats["avg_favorable_pct"] == 0.5
    assert stats["worst_adverse_pct"] == -0.9
    store.close()


def test_spot_at_or_after_picks_first_ts_ge_target_and_respects_not_after(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(SqueezeConfig())
    for ts, spot in [(1000.0, 100.0), (1090.0, 100.5), (1180.0, 101.0), (1270.0, 101.5)]:
        _append(store, engine, ts, spot=spot)

    assert store.spot_at_or_after(1150.0) == (1180.0, 101.0)
    assert store.spot_at_or_after(1000.0) == (1000.0, 100.0)
    assert store.spot_at_or_after(1150.0, not_after=1170.0) is None
    assert store.spot_at_or_after(1150.0, not_after=1180.0) == (1180.0, 101.0)
    assert store.spot_at_or_after(5000.0) is None
    store.close()


def test_last_spot_of_day_picks_last_within_range(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(SqueezeConfig())
    for ts, spot in [(1000.0, 100.0), (2000.0, 101.0), (3000.0, 102.0), (9000.0, 999.0)]:
        _append(store, engine, ts, spot=spot)

    result = store.last_spot_of_day(day_start_ts=0.0, day_end_ts=5000.0)
    assert result == (3000.0, 102.0)
    assert store.last_spot_of_day(day_start_ts=0.0, day_end_ts=500.0) is None
    store.close()


def test_timeline_ordered_ascending_regardless_of_insert_order(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(SqueezeConfig())
    for ts in [3000.0, 1000.0, 2000.0]:
        _append(store, engine, ts)

    rows = store.timeline(since_ts=0.0)
    assert [r["ts"] for r in rows] == [1000.0, 2000.0, 3000.0]
    filtered = store.timeline(since_ts=1500.0)
    assert [r["ts"] for r in filtered] == [2000.0, 3000.0]
    store.close()


def test_snapshots_between_reconstructs_snapshot_with_empty_payload(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(SqueezeConfig())
    _append(store, engine, 1000.0, structural=10.0, spot=100.0)
    _append(store, engine, 1090.0, structural=20.0, spot=101.0)
    _append(store, engine, 5000.0, structural=30.0, spot=102.0)

    out = store.snapshots_between(900.0, 2000.0)
    assert len(out) == 2
    assert [round(s.ts) for s in out] == [1000, 1090]
    assert isinstance(out[0], SqueezeSnapshot)
    assert out[0].spot == 100.0
    assert out[0].structural_score == 10.0
    assert out[0].payload == {}
    store.close()


def test_alerts_since_returns_joined_outcomes(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    old_alert = dict(BULL_ALERT, ts=100.0)
    recent_alert = dict(BULL_ALERT, ts=5000.0, transition="enter_peaking")
    store.insert_alert(old_alert)
    recent_id = store.insert_alert(recent_alert)
    store.insert_outcome(recent_id, 30, realized_ret_pct=0.3, hit=True, resolved_ts=6000.0)

    recent_only = store.alerts_since(1000.0)
    assert len(recent_only) == 1
    assert recent_only[0]["ts"] == 5000.0
    assert recent_only[0]["transition"] == "enter_peaking"
    assert recent_only[0]["outcomes"] == [
        {"horizon_min": 30, "realized_ret_pct": 0.3, "hit": True, "resolved_ts": 6000.0}
    ]

    all_alerts = store.alerts_since(0.0)
    assert len(all_alerts) == 2
    assert all_alerts[0]["outcomes"] == []
    store.close()


def test_reopen_same_path_persists_data(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(SqueezeConfig())
    _append(store, engine, 1000.0, structural=40.0)
    alert_id = store.insert_alert(BULL_ALERT)
    store.insert_outcome(alert_id, 30, realized_ret_pct=0.5, hit=True, resolved_ts=2000.0)
    store.close()

    reopened = SqueezeStore("TSLA", root=tmp_path)
    assert reopened.timeline(since_ts=0.0)[0]["ts"] == 1000.0
    assert reopened.alerts_without_outcome(30) == []
    assert reopened.stats()["resolved_total"] == 1
    reopened.close()


def test_db_path_uses_symbol_upper_under_root(tmp_path):
    store = SqueezeStore("tsla", root=tmp_path)
    assert store.path == tmp_path / "TSLA.sqlite"
    assert store.path.exists()
    store.close()
