import pytest

from services.market_runtime.squeeze import SqueezeConfig, SqueezeEngine, SqueezeSnapshot
from services.market_runtime.squeeze.evaluator import resolve_pending, track_factor
from services.market_runtime.squeeze.store import SqueezeStore

CFG = SqueezeConfig()


def snap(ts, spot=100.0):
    return SqueezeSnapshot(
        ts=ts, spot=spot, structural_score=0.0, structural_components={},
        call_wall=102.0, put_wall=95.0, call_wall_gex=1e9, put_wall_gex=1e9,
        flip=98.0, near_net=-5e9, net_dealer=-6e9, abs_book=4e9,
        otm_call_volume=0.0, otm_put_volume=0.0, expected_move_pct=4.0,
        n_contracts=250, degraded=False,
    )


def _append(store, engine, ts, spot=100.0):
    s = snap(ts, spot=spot)
    step = engine.step(s)
    store.append(s, step, engine.cfg.weights_json())
    return s, step


def _seed_ramp(store):
    """41 snapshots, 90s apart, spot ramping 100 -> 101 over 3600s (ts 1000..4600)."""
    engine = SqueezeEngine(CFG)
    for i in range(41):
        ts = 1000.0 + i * 90.0
        spot = 100.0 + (i / 40.0) * 1.0
        _append(store, engine, ts, spot=spot)


BULL_ALERT = {
    "ts": 1000.0,
    "direction": "bull",
    "transition": "enter_building",
    "score": 30.0,
    "spot": 100.0,
    "confidence": 80.0,
    "components": {},
}


def test_bull_alert_resolves_hit_at_30m(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    _seed_ramp(store)
    alert_id = store.insert_alert(BULL_ALERT)

    now = 1000.0 + 31 * 60.0  # deadline (2800) has passed
    n = resolve_pending(store, CFG, now_ts=now)

    assert n == 1
    assert store.alerts_without_outcome(30) == []
    outcomes = store.alerts_since(0.0)[0]["outcomes"]
    assert len(outcomes) == 1
    assert outcomes[0]["horizon_min"] == 30
    assert outcomes[0]["hit"] is True
    assert outcomes[0]["realized_ret_pct"] >= 0.2
    store.close()


def test_bear_alert_misses_on_rising_spot(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    _seed_ramp(store)
    bear_alert = dict(BULL_ALERT, direction="bear")
    store.insert_alert(bear_alert)

    now = 1000.0 + 31 * 60.0
    n = resolve_pending(store, CFG, now_ts=now)

    assert n == 1
    outcomes = store.alerts_since(0.0)[0]["outcomes"]
    assert outcomes[0]["hit"] is False
    assert outcomes[0]["realized_ret_pct"] < 0
    store.close()


def test_stays_pending_without_spot_or_backfill(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(CFG)
    _append(store, engine, 1090.0, spot=100.2)  # single early snapshot, well before deadline
    store.insert_alert(BULL_ALERT)

    now = 1000.0 + 31 * 60.0  # deadline passed but not deadline+3600 -> no session-end fallback
    n = resolve_pending(store, CFG, now_ts=now, backfill_fn=None)

    assert n == 0
    assert len(store.alerts_without_outcome(30)) == 1
    store.close()


def test_backfill_fn_resolves_when_no_stored_spot(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(CFG)
    _append(store, engine, 1090.0, spot=100.2)
    store.insert_alert(BULL_ALERT)

    now = 1000.0 + 31 * 60.0
    n = resolve_pending(store, CFG, now_ts=now, backfill_fn=lambda ts: 102.0)

    assert n == 1
    outcomes = store.alerts_since(0.0)[0]["outcomes"]
    assert outcomes[0]["realized_ret_pct"] == pytest.approx(2.0)
    assert outcomes[0]["hit"] is True
    store.close()


def test_enter_fading_alert_never_resolves(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    _seed_ramp(store)
    fading_alert = dict(BULL_ALERT, transition="enter_fading")
    store.insert_alert(fading_alert)

    now = 1000.0 + 31 * 60.0
    n = resolve_pending(store, CFG, now_ts=now, backfill_fn=lambda ts: 999.0)

    assert n == 0
    assert len(store.alerts_without_outcome(30)) == 1
    store.close()


def test_session_ended_falls_back_to_last_spot_of_day(tmp_path):
    store = SqueezeStore("TSLA", root=tmp_path)
    engine = SqueezeEngine(CFG)
    # last trade of the (UTC) day happens before the deadline; nothing after it.
    _append(store, engine, 2700.0, spot=105.0)
    store.insert_alert(BULL_ALERT)

    deadline = 1000.0 + 30 * 60.0  # 2800.0
    now = deadline + 3601.0  # past deadline + 3600s => session considered ended
    n = resolve_pending(store, CFG, now_ts=now, backfill_fn=None)

    assert n == 1
    outcomes = store.alerts_since(0.0)[0]["outcomes"]
    assert outcomes[0]["realized_ret_pct"] == pytest.approx(5.0)
    assert outcomes[0]["hit"] is True
    store.close()


def test_track_factor_neutral_below_min_resolved():
    stats = {"resolved_total": 19, "by_horizon": {}}
    assert track_factor(stats, CFG) == 1.0


def test_track_factor_clamps_high_hit_rate_to_1_2():
    stats = {
        "resolved_total": 30,
        "by_horizon": {
            "30": {"n": 15, "hits": 12, "hit_rate": 0.8},
            "120": {"n": 15, "hits": 12, "hit_rate": 0.8},
        },
    }
    assert track_factor(stats, CFG) == 1.2


def test_track_factor_clamps_low_hit_rate_to_0_5():
    stats = {
        "resolved_total": 30,
        "by_horizon": {
            "30": {"n": 15, "hits": 3, "hit_rate": 0.2},
            "120": {"n": 15, "hits": 3, "hit_rate": 0.2},
        },
    }
    assert track_factor(stats, CFG) == 0.5
