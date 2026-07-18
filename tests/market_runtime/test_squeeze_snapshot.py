import json

from services.market_runtime.squeeze import SqueezeConfig, SqueezeSnapshot

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
}


def test_config_defaults_and_weights_json():
    cfg = SqueezeConfig()
    assert cfg.poll_seconds == 90
    assert cfg.structural_weight == 0.5
    w = json.loads(cfg.weights_json())
    assert w["structural_weight"] == 0.5
    assert w["version"] == cfg.version


def test_snapshot_from_gamma_result():
    snap = SqueezeSnapshot.from_gamma_result(GAMMA_RESULT, ts=1000.0, degraded=False)
    assert snap.spot == 100.0
    assert snap.structural_score == 30.0
    assert snap.abs_book == 4e9  # sum |call_gex| + |put_gex| across strikes
    assert snap.degraded is False
    assert snap.payload["by_strike"]


def test_snapshot_json_roundtrip_drops_payload():
    snap = SqueezeSnapshot.from_gamma_result(GAMMA_RESULT, ts=1000.0, degraded=True)
    back = SqueezeSnapshot.from_json(snap.to_json())
    assert back.spot == snap.spot and back.otm_call_volume == snap.otm_call_volume
    assert back.payload == {}  # payload intentionally not serialized


def test_snapshot_handles_missing_optionals():
    r = dict(GAMMA_RESULT, expected_move_pct=None, approx_flip_strike=None)
    snap = SqueezeSnapshot.from_gamma_result(r, ts=1.0, degraded=False)
    assert snap.expected_move_pct is None and snap.flip is None
