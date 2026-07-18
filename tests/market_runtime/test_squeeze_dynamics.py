from services.market_runtime.squeeze import SqueezeConfig, SqueezeSnapshot
from services.market_runtime.squeeze.dynamics import FlowBaseline, compute_dynamics

CFG = SqueezeConfig()


def snap(ts, spot=100.0, cw_gex=1e9, pw_gex=1e9, ocv=0.0, opv=0.0, em=4.0,
         near=-5e9, net=-6e9):
    return SqueezeSnapshot(
        ts=ts, spot=spot, structural_score=0.0, structural_components={},
        call_wall=102.0, put_wall=95.0, call_wall_gex=cw_gex, put_wall_gex=pw_gex,
        flip=98.0, near_net=near, net_dealer=net, abs_book=4e9,
        otm_call_volume=ocv, otm_put_volume=opv, expected_move_pct=em,
        n_contracts=200, degraded=False,
    )


def test_short_history_is_all_zero():
    out = compute_dynamics([snap(0)], FlowBaseline(), CFG)
    assert out["dynamic_score"] == 0.0
    assert all(v == 0.0 for v in out.values())


def test_call_wall_building_is_bullish():
    hist = [snap(0, cw_gex=1e9), snap(300, cw_gex=2e9)]
    out = compute_dynamics(hist, FlowBaseline(), CFG)
    assert out["wall_build_score"] > 0


def test_call_flow_burst_is_bullish_and_baseline_updates():
    base = FlowBaseline()
    hist = [snap(0, ocv=0, opv=0), snap(300, ocv=5000, opv=500)]
    out = compute_dynamics(hist, base, CFG)
    assert out["flow_accel_score"] > 0
    assert base.n == 1


def test_spot_rising_toward_call_wall_is_bullish():
    hist = [snap(0, spot=100.0), snap(300, spot=101.0)]
    out = compute_dynamics(hist, FlowBaseline(), CFG)
    assert out["spot_kinetics_score"] > 0


def test_iv_lift_amplifies_direction_and_zero_without_subtotal():
    hist = [snap(0, spot=100.0, em=4.0), snap(300, spot=101.0, em=4.6)]
    out = compute_dynamics(hist, FlowBaseline(), CFG)
    assert out["iv_lift_score"] > 0
    flat = [snap(0), snap(300)]
    assert compute_dynamics(flat, FlowBaseline(), CFG)["iv_lift_score"] == 0.0


def test_positive_gex_damps_dynamics():
    bull = [snap(0, spot=100.0), snap(300, spot=101.0)]
    hot = compute_dynamics(bull, FlowBaseline(), CFG)
    damped_hist = [snap(0, spot=100.0, near=5e9), snap(300, spot=101.0, near=5e9)]
    damped = compute_dynamics(damped_hist, FlowBaseline(), CFG)
    assert 0 < damped["spot_kinetics_score"] < hot["spot_kinetics_score"]


def test_dynamic_score_bounded():
    hist = [snap(0, spot=100, cw_gex=0, ocv=0),
            snap(60, spot=110, cw_gex=9e9, ocv=1e6)]
    out = compute_dynamics(hist, FlowBaseline(), CFG)
    assert -100.0 <= out["dynamic_score"] <= 100.0
