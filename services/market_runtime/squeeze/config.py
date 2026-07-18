from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SqueezeConfig:
    """Every tunable of the squeeze engine. No magic numbers elsewhere."""

    version: str = "v2.0"
    # cadence / lifecycle
    poll_seconds: int = 90
    heartbeat_ttl_seconds: int = 300
    max_backoff_seconds: int = 360
    stale_after_polls: int = 2
    # dynamics
    window_minutes: float = 15.0
    history_maxlen: int = 40
    # combination
    structural_weight: float = 0.5
    dynamic_weight: float = 0.5
    # dynamic component ceilings (sum = 100)
    wall_build_max_points: float = 20.0
    flow_accel_max_points: float = 30.0
    spot_kinetics_max_points: float = 25.0
    iv_lift_max_points: float = 25.0
    # dynamics scaling
    wall_build_tanh_gain: float = 4.0
    spot_velocity_unit_pct_per_min: float = 0.15
    iv_lift_unit_pp: float = 0.5
    positive_gex_damp: float = 0.35
    # phase machine
    build_enter_score: float = 25.0
    peak_enter_score: float = 55.0
    fade_drop_points: float = 15.0
    none_exit_score: float = 15.0
    min_rising_polls: int = 2
    min_dwell_polls: int = 2
    peak_flat_eps: float = 3.0
    # track record
    horizons_minutes: tuple[int, ...] = (30, 120)
    hit_thresholds_pct: tuple[float, ...] = (0.2, 0.5)
    min_resolved_for_track: int = 20

    def weights_json(self) -> str:
        return json.dumps(asdict(self), default=list, sort_keys=True)
