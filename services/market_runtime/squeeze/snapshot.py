from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class SqueezeSnapshot:
    """One poll of the chain, reduced to what the engine + replay need.

    ``payload`` carries the full gamma dict for UI passthrough and is NOT
    serialized (replay does not need it).
    """

    ts: float
    spot: float
    structural_score: float
    structural_components: dict[str, float]
    call_wall: float | None
    put_wall: float | None
    call_wall_gex: float
    put_wall_gex: float
    flip: float | None
    near_net: float
    net_dealer: float
    abs_book: float
    otm_call_volume: float
    otm_put_volume: float
    expected_move_pct: float | None
    n_contracts: int
    degraded: bool
    payload: dict = field(default_factory=dict)

    @classmethod
    def from_gamma_result(cls, result: dict, ts: float, degraded: bool) -> "SqueezeSnapshot":
        by_strike = result.get("by_strike") or []
        abs_book = float(
            sum(abs(s.get("call_gex", 0.0)) + abs(s.get("put_gex", 0.0)) for s in by_strike)
        )
        return cls(
            ts=float(ts),
            spot=float(result["spot"]),
            structural_score=float(result.get("squeeze_score") or 0.0),
            structural_components=dict(result.get("squeeze_components") or {}),
            call_wall=result.get("call_wall"),
            put_wall=result.get("put_wall"),
            call_wall_gex=float(result.get("call_wall_gex") or 0.0),
            put_wall_gex=float(result.get("put_wall_gex") or 0.0),
            flip=result.get("approx_flip_strike"),
            near_net=float(result.get("near_spot_dealer_gex") or 0.0),
            net_dealer=float(result.get("net_dealer_gex") or 0.0),
            abs_book=abs_book,
            otm_call_volume=float(result.get("otm_call_volume") or 0.0),
            otm_put_volume=float(result.get("otm_put_volume") or 0.0),
            expected_move_pct=result.get("expected_move_pct"),
            n_contracts=int(result.get("n_contracts") or 0),
            degraded=bool(degraded),
            payload=result,
        )

    def to_json(self) -> str:
        d = asdict(self)
        d.pop("payload", None)
        return json.dumps(d, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "SqueezeSnapshot":
        d = json.loads(s)
        d["payload"] = {}
        return cls(**d)
