from services.market_runtime.squeeze import SqueezeConfig, SqueezeEngine, SqueezeSnapshot


def snap(ts, structural=0.0, spot=100.0, degraded=False, n_contracts=250):
    return SqueezeSnapshot(
        ts=ts, spot=spot, structural_score=structural, structural_components={},
        call_wall=102.0, put_wall=95.0, call_wall_gex=1e9, put_wall_gex=1e9,
        flip=98.0, near_net=-5e9, net_dealer=-6e9, abs_book=4e9,
        otm_call_volume=0.0, otm_put_volume=0.0, expected_move_pct=4.0,
        n_contracts=n_contracts, degraded=degraded,
    )


def run(engine, seq):
    return [engine.step(s) for s in seq]


def test_flat_zero_stays_none():
    eng = SqueezeEngine()
    results = run(eng, [snap(i * 90, structural=0.0) for i in range(5)])
    assert all(r.phase == "none" for r in results)
    assert all(not r.alerts for r in results)


def test_build_requires_rising_polls_then_alerts_once():
    eng = SqueezeEngine()
    seq = [snap(0, 40), snap(90, 52), snap(180, 60)]
    # scores: 20, 26, 30 (0.5 weight, dynamics ~0) -> rising; building on 3rd poll
    results = run(eng, seq)
    assert results[0].phase == "none"
    assert results[-1].phase == "building"
    assert results[-1].direction == "bull"
    enters = [a for r in results for a in r.alerts if a["transition"] == "enter_building"]
    assert len(enters) == 1


def test_one_poll_spike_does_not_build():
    eng = SqueezeEngine()
    results = run(eng, [snap(0, 0), snap(90, 60), snap(180, 0)])
    assert all(r.phase == "none" for r in results)


def test_full_lifecycle_build_peak_fade_none():
    eng = SqueezeEngine()
    seq = [snap(0, 40), snap(90, 52), snap(180, 80), snap(270, 118), snap(360, 119),
           snap(450, 118), snap(540, 80), snap(630, 20)]
    # peaking gets its min-dwell polls before the fade; final poll drops |score| < 15
    results = run(eng, seq)
    phases = [r.phase for r in results]
    assert "building" in phases and "peaking" in phases and "fading" in phases
    assert phases[-1] == "none"
    transitions = [a["transition"] for r in results for a in r.alerts]
    assert transitions == ["enter_building", "enter_peaking", "enter_fading"]


def test_bearish_direction():
    eng = SqueezeEngine()
    results = run(eng, [snap(0, -40), snap(90, -52), snap(180, -60)])
    assert results[-1].phase == "building" and results[-1].direction == "bear"


def test_confidence_degraded_and_unproven():
    eng = SqueezeEngine()
    r = eng.step(snap(0, 40, degraded=True, n_contracts=250))
    assert r.confidence_parts["quality"] <= 0.5
    r2 = SqueezeEngine().step(snap(0, 40), track_factor=1.0)
    assert 0 <= r2.confidence <= 100


def test_score_is_weighted_combination():
    eng = SqueezeEngine()
    r = eng.step(snap(0, structural=50.0))
    assert abs(r.structural - 50.0) < 1e-9
    assert abs(r.score - (0.5 * 50.0 + 0.5 * r.dynamic)) < 1e-6
