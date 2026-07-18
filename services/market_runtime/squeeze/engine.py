"""Squeeze engine: phase state machine, confidence, and transition alerts.

The engine is stateful across polls. ``step`` takes one :class:`SqueezeSnapshot`,
combines the structural score with the fresh dynamic score, drives a hysteretic
phase machine (none -> building -> peaking -> fading -> none), computes a
multiplicative confidence, and emits alerts on transitions INTO an active phase.
All thresholds/weights come from :class:`SqueezeConfig` (no magic numbers here).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .config import SqueezeConfig
from .dynamics import FlowBaseline, compute_dynamics
from .snapshot import SqueezeSnapshot


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sign_dir(score: float) -> str:
    if score > 0:
        return "bull"
    if score < 0:
        return "bear"
    return "none"


@dataclass
class StepResult:
    ts: float
    score: float
    structural: float
    dynamic: float
    components: dict[str, float]  # structural_components + dynamic components merged
    phase: str  # "none" | "building" | "peaking" | "fading"
    direction: str  # "bull" | "bear" | "none"
    phase_seconds: float
    confidence: float  # 0..100
    confidence_parts: dict[str, float]
    alerts: list[dict] = field(default_factory=list)


class SqueezeEngine:
    """Stateful deterministic squeeze engine (prev_state + snapshot -> state)."""

    def __init__(self, cfg: SqueezeConfig | None = None) -> None:
        self.cfg = cfg or SqueezeConfig()
        self._history: deque[SqueezeSnapshot] = deque(maxlen=self.cfg.history_maxlen)
        self._baseline = FlowBaseline()
        self._phase = "none"
        self._phase_direction = "none"
        self._prev_score: float | None = None
        self._rising_polls = 0
        self._session_peak_abs = 0.0
        self._polls_in_phase = 0
        self._phase_entered_ts: float | None = None

    def reset(self) -> None:
        self._history.clear()
        self._baseline = FlowBaseline()
        self._phase = "none"
        self._phase_direction = "none"
        self._prev_score = None
        self._rising_polls = 0
        self._session_peak_abs = 0.0
        self._polls_in_phase = 0
        self._phase_entered_ts = None

    def step(
        self,
        snap: SqueezeSnapshot,
        track_factor: float = 1.0,
        chain_age_minutes: float = 0.0,
    ) -> StepResult:
        cfg = self.cfg
        self._history.append(snap)
        dyn = compute_dynamics(self._history, self._baseline, cfg)
        dynamic = dyn["dynamic_score"]
        structural = float(snap.structural_score)
        score = _clamp(
            cfg.structural_weight * structural + cfg.dynamic_weight * dynamic,
            -100.0,
            100.0,
        )
        direction = _sign_dir(score)
        abs_score = abs(score)

        # rising_polls: consecutive polls where |score| grows in the same direction.
        if self._prev_score is None:
            rising = False
        else:
            prev_dir = _sign_dir(self._prev_score)
            rising = (
                direction != "none"
                and direction == prev_dir
                and abs_score > abs(self._prev_score)
            )
        self._rising_polls = self._rising_polls + 1 if rising else 0

        # dwell counter for the phase we are currently in (entry poll counts as 1).
        self._polls_in_phase += 1
        if self._phase_entered_ts is None:
            self._phase_entered_ts = snap.ts

        components: dict[str, float] = dict(snap.structural_components or {})
        components.update(dyn)

        confidence, confidence_parts = self._confidence(
            snap, structural, dynamic, track_factor, chain_age_minutes
        )

        alerts: list[dict] = []

        def emit(transition: str, alert_dir: str) -> None:
            alerts.append(
                {
                    "ts": snap.ts,
                    "direction": alert_dir,
                    "transition": transition,
                    "score": score,
                    "spot": snap.spot,
                    "confidence": confidence,
                    "components": dict(components),
                }
            )

        def enter(new_phase: str) -> None:
            self._phase = new_phase
            self._phase_direction = direction
            self._phase_entered_ts = snap.ts
            self._polls_in_phase = 1

        def to_none() -> None:
            self._phase = "none"
            self._phase_direction = "none"
            self._session_peak_abs = 0.0
            self._phase_entered_ts = snap.ts
            self._polls_in_phase = 1

        dwell_ok = self._polls_in_phase >= cfg.min_dwell_polls

        if self._phase == "none":
            if (
                abs_score >= cfg.build_enter_score
                and self._rising_polls >= cfg.min_rising_polls
            ):
                enter("building")
                emit("enter_building", direction)
        else:
            hard_flip = (
                self._phase_direction in ("bull", "bear")
                and direction in ("bull", "bear")
                and direction != self._phase_direction
                and abs_score >= cfg.build_enter_score
                and rising
            )
            if hard_flip:
                # Old squeeze is over: close it with an enter_fading alert for the
                # old direction, then reset to a fresh none state.
                emit("enter_fading", self._phase_direction)
                to_none()
            elif self._phase == "building":
                if dwell_ok and abs_score <= self._session_peak_abs - cfg.fade_drop_points:
                    enter("fading")
                    emit("enter_fading", direction)
                elif (
                    dwell_ok
                    and abs_score >= cfg.peak_enter_score
                    and abs(score - self._prev_score) <= cfg.peak_flat_eps
                ):
                    enter("peaking")
                    emit("enter_peaking", direction)
            elif self._phase == "peaking":
                if dwell_ok and abs_score <= self._session_peak_abs - cfg.fade_drop_points:
                    enter("fading")
                    emit("enter_fading", direction)
            elif self._phase == "fading":
                # fading -> none is exempt from the min-dwell rule.
                if abs_score < cfg.none_exit_score:
                    to_none()

        # session_peak_abs = max |score| since phase left "none"; 0 while in none.
        if self._phase != "none":
            self._session_peak_abs = max(self._session_peak_abs, abs_score)
        else:
            self._session_peak_abs = 0.0

        phase_seconds = float(snap.ts - self._phase_entered_ts)
        self._prev_score = score

        return StepResult(
            ts=float(snap.ts),
            score=score,
            structural=structural,
            dynamic=dynamic,
            components=components,
            phase=self._phase,
            direction=direction,
            phase_seconds=phase_seconds,
            confidence=confidence,
            confidence_parts=confidence_parts,
            alerts=alerts,
        )

    def _confidence(
        self,
        snap: SqueezeSnapshot,
        structural: float,
        dynamic: float,
        track_factor: float,
        chain_age_minutes: float,
    ) -> tuple[float, dict[str, float]]:
        cfg = self.cfg  # noqa: F841 - kept for symmetry / future tunables
        freshness = _clamp(1.0 - chain_age_minutes / 30.0, 0.3, 1.0)
        quality = _clamp(snap.n_contracts / 200.0, 0.3, 1.0) * (
            0.5 if snap.degraded else 1.0
        )
        prod = structural * dynamic
        if prod > 0:
            agreement = 1.0
        elif prod < 0:
            agreement = 0.5
        else:
            agreement = 0.75
        track = _clamp(track_factor, 0.5, 1.2)
        confidence = _clamp(100.0 * freshness * quality * agreement * track, 0.0, 100.0)
        parts = {
            "freshness": freshness,
            "quality": quality,
            "agreement": agreement,
            "track": track,
        }
        return confidence, parts
