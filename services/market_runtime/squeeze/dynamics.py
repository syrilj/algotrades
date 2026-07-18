from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .config import SqueezeConfig
from .snapshot import SqueezeSnapshot


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class FlowBaseline:
    """Welford online mean/variance of this session's per-window OTM flow totals."""

    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2

    def z(self, x: float) -> float:
        if self.n < 3:
            return 0.0
        std = math.sqrt(self.m2 / self.n)
        if std == 0.0:
            return 0.0
        return (x - self.mean) / std


def compute_dynamics(
    history: Sequence[SqueezeSnapshot],
    baseline: FlowBaseline,
    cfg: SqueezeConfig,
) -> dict[str, float]:
    """Inter-poll dynamic components over a rolling ``cfg.window_minutes`` window.

    ``history[-1]`` is the newest snapshot; the reference is the oldest snapshot
    still within the window of it. Mutates ``baseline`` with this window's total
    OTM flow.
    """
    keys = (
        "wall_build_score",
        "flow_accel_score",
        "spot_kinetics_score",
        "iv_lift_score",
        "dynamic_score",
    )
    if len(history) < 2:
        return {k: 0.0 for k in keys}

    newest = history[-1]
    window_s = cfg.window_minutes * 60.0
    ref = newest
    for s in history:
        if newest.ts - s.ts <= window_s:
            ref = s
            break
    dt_min = max((newest.ts - ref.ts) / 60.0, 1.0)

    # 1. wall build/erode rate
    rel = (
        (newest.call_wall_gex - ref.call_wall_gex)
        - (newest.put_wall_gex - ref.put_wall_gex)
    ) / max(newest.abs_book, 1.0)
    rate = rel * (cfg.window_minutes / dt_min)
    wall_build = cfg.wall_build_max_points * math.tanh(cfg.wall_build_tanh_gain * rate)

    # 2. flow acceleration
    dcall = max(newest.otm_call_volume - ref.otm_call_volume, 0.0)
    dput = max(newest.otm_put_volume - ref.otm_put_volume, 0.0)
    total = dcall + dput
    imbalance = (dcall - dput) / max(total, 1.0)
    if baseline.n < 3:
        magnitude = 0.5
    else:
        magnitude = _clamp(baseline.z(total) / 2.0, 0.0, 1.0)
    flow_accel = cfg.flow_accel_max_points * imbalance * magnitude
    baseline.update(total)

    # 3. spot kinetics
    vel = (newest.spot - ref.spot) / ref.spot * 100.0 / dt_min
    wall = newest.call_wall if vel > 0 else newest.put_wall
    if wall is None:
        proximity = 0.0
    else:
        dist_pct = abs(wall - newest.spot) / newest.spot * 100.0
        ep = newest.expected_move_pct
        em = ep if (ep is not None and ep > 0.1) else 5.0
        proximity = max(0.0, 1.0 - dist_pct / em)
    spot_kinetics = (
        cfg.spot_kinetics_max_points
        * math.tanh(vel / cfg.spot_velocity_unit_pct_per_min)
        * proximity
    )

    # 4. IV lift (confirmation only when the other components have a subtotal)
    subtotal = wall_build + flow_accel + spot_kinetics
    if (
        subtotal == 0.0
        or newest.expected_move_pct is None
        or ref.expected_move_pct is None
    ):
        iv_lift = 0.0
    else:
        d_em = newest.expected_move_pct - ref.expected_move_pct
        iv_lift = (
            cfg.iv_lift_max_points
            * math.tanh(d_em / cfg.iv_lift_unit_pp)
            * (1.0 if subtotal > 0 else -1.0)
        )

    # regime damp: positive near-spot GEX suppresses squeeze dynamics
    if newest.near_net >= 0:
        damp = cfg.positive_gex_damp
    else:
        damp = min(1.0, abs(newest.near_net) / max(abs(newest.net_dealer), 1.0))
    wall_build *= damp
    flow_accel *= damp
    spot_kinetics *= damp
    iv_lift *= damp

    dynamic_score = _clamp(
        wall_build + flow_accel + spot_kinetics + iv_lift, -100.0, 100.0
    )

    return {
        "wall_build_score": wall_build,
        "flow_accel_score": flow_accel,
        "spot_kinetics_score": spot_kinetics,
        "iv_lift_score": iv_lift,
        "dynamic_score": dynamic_score,
    }
