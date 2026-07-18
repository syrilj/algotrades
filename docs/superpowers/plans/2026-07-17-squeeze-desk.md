# Squeeze Desk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real-time gamma squeeze engine (structural + dynamic scoring, phase state machine, live track record) in `services/market_runtime/squeeze/`, surfaced on a rebuilt Squeeze Desk UI at `/live?mode=gamma` (deep-linked from `/gamma`).

**Architecture:** Extract pure GEX math into `tools/gex_core.py`. New `squeeze` package: pure `SqueezeEngine` (snapshot in → score/phase/confidence/alerts out), SQLite `SqueezeStore`, `Evaluator` for alert outcomes, threaded `SqueezeWatcher` + `SqueezeManager` polling LSE every 90s with heartbeat TTL. Three FastAPI endpoints. Next.js thin proxy + new `SqueezeDesk` React component tree replacing `GammaExposureDesk` in gamma mode.

**Tech Stack:** Python 3.11+ (FastAPI, pandas, numpy, sqlite3, threading), Next.js 15 / React 19 / Tailwind (existing trade-desk), sucrase-node assert tests for TS lib.

**Spec:** `docs/superpowers/specs/2026-07-17-squeeze-desk-design.md` — read it first.

## Global Constraints

- Poll cadence 90s; heartbeat POST every 60s; watcher TTL 300s without heartbeat; dynamics window 15 min.
- Score = clamp(0.5·structural + 0.5·dynamic, −100, +100). Weights recorded on every snapshot row.
- Phase thresholds: BUILDING enter |score| ≥ 25 rising ≥ 2 polls; PEAKING ≥ 55 + momentum flat; FADING on 15-pt drop from session peak; NONE at |score| < 15. Hysteresis: min dwell 2 polls before any transition out.
- Hit thresholds: 30 min ≥ 0.2%; 2 h ≥ 0.5% (signed, in alert direction).
- Confidence always carries evidence count; track-record factor neutral (1.0) until ≥ 20 resolved alerts.
- SQLite per symbol: `data_cache/squeeze/{SYMBOL}.sqlite`. `data_cache/` is repo-local, gitignored (verify; add ignore if missing).
- All thresholds/weights live ONLY in `SqueezeConfig` — no magic numbers elsewhere.
- UI: institutional terminal rules from repo `CLAUDE.md`. Action-color law: bull → `--td-action-buy-breakout` (building) / `--td-action-buy-now` (peaking); bear → `--td-action-avoid`; fading → `--td-action-wait`; none → `--td-muted`. No gradients, no glow, tabular nums, honest empty states.
- Python tests: `pytest` from repo root (pythonpath already includes `tools` and `services`). TS tests: sucrase-node files registered in `apps/trade-desk/package.json` `test` script.
- Keep `tests/test_gamma_flip.py` passing: `gamma_exposure._zero_gamma_flip` must keep working after extraction (alias imports).
- Commit after every task with a conventional message ending in the Claude co-author trailer.

---

### Task 1: Extract pure GEX math into `tools/gex_core.py`

**Files:**
- Create: `tools/gex_core.py`
- Modify: `tools/gamma_exposure.py` (delete moved bodies, import + alias)
- Test: `tests/test_gex_core.py`

**Interfaces:**
- Consumes: current private helpers in `tools/gamma_exposure.py`: `_bs_gamma` (line ~100), `_gex_per_one_percent` (~108), `_price_consistency` (~114), `_max_pain` (~130), `_zero_gamma_flip` (~171), `_compute_squeeze_score` (~204).
- Produces (public, exact same signatures/bodies, underscore dropped):
  - `bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float`
  - `gex_per_one_percent(gamma, contracts, spot: float)`
  - `price_consistency(spot: float, option_spot: float, max_divergence_pct: float = 3.0) -> dict`
  - `max_pain(call_strikes, call_oi, put_strikes, put_oi, strikes) -> float | None`
  - `zero_gamma_flip(net_by_strike, spot: float) -> float | None`
  - `compute_squeeze_score(spot, call_wall, put_wall, flip, near_net, net_dealer, otm_call_weight, otm_put_weight, total_weight, by_strike, expected_move_pct, expected_move_low, expected_move_high) -> dict` — returns `{"squeeze_score", "squeeze_label", "squeeze_components", "call_wall_gex", "put_wall_gex"}` exactly as today.

- [ ] **Step 1: Write failing tests** — `tests/test_gex_core.py`:

```python
import numpy as np
import pandas as pd

from gex_core import (
    bs_gamma,
    compute_squeeze_score,
    max_pain,
    price_consistency,
    zero_gamma_flip,
)


def _score(**over):
    """Baseline bullish-squeeze inputs; override per test."""
    kw = dict(
        spot=100.0,
        call_wall=103.0,
        put_wall=90.0,
        flip=98.0,
        near_net=-5e9,
        net_dealer=-6e9,
        otm_call_weight=400.0,
        otm_put_weight=100.0,
        total_weight=1000.0,
        by_strike=[
            {"strike": 103.0, "call_gex": -3e9, "put_gex": 0.0},
            {"strike": 90.0, "call_gex": 0.0, "put_gex": -1e9},
        ],
        expected_move_pct=4.0,
        expected_move_low=96.0,
        expected_move_high=104.0,
    )
    kw.update(over)
    return compute_squeeze_score(**kw)


def test_bullish_setup_scores_bullish():
    out = _score()
    assert out["squeeze_score"] >= 20
    assert out["squeeze_label"] == "bullish_squeeze"


def test_positive_gex_is_neutral():
    out = _score(near_net=5e9, net_dealer=6e9)
    assert out["squeeze_label"] == "neutral"
    assert all(v == 0.0 for k, v in out["squeeze_components"].items() if k != "regime_score")


def test_bearish_mirror_scores_bearish():
    out = _score(
        call_wall=110.0,
        put_wall=97.0,
        otm_call_weight=100.0,
        otm_put_weight=400.0,
        by_strike=[
            {"strike": 110.0, "call_gex": -1e9, "put_gex": 0.0},
            {"strike": 97.0, "call_gex": 0.0, "put_gex": -3e9},
        ],
    )
    assert out["squeeze_score"] <= -20
    assert out["squeeze_label"] == "bearish_squeeze"


def test_flip_crossing_near_spot():
    net = pd.Series([1.0, 2.0, -4.0, 1.5], index=[10.0, 20.0, 30.0, 40.0])
    assert abs(zero_gamma_flip(net, spot=31.0) - 27.5) < 1e-9


def test_bs_gamma_atm_positive_and_degenerate_zero():
    assert bs_gamma(100, 100, 30 / 365, 0.0, 0.5) > 0
    assert bs_gamma(100, 100, 0.0, 0.0, 0.5) == 0.0


def test_price_consistency_flags_divergence():
    assert price_consistency(100.0, 100.5)["consistent"] is True
    assert price_consistency(100.0, 110.0)["consistent"] is False


def test_max_pain_prefers_middle_strike():
    strikes = [90.0, 100.0, 110.0]
    mp = max_pain(
        np.array([90.0, 100.0]), np.array([100.0, 100.0]),
        np.array([110.0, 100.0]), np.array([100.0, 100.0]),
        strikes,
    )
    assert mp in strikes
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_gex_core.py -v` → FAIL (`ModuleNotFoundError: gex_core`).
- [ ] **Step 3: Implement** — create `tools/gex_core.py` with module docstring ("Pure GEX math shared by tools/gamma_exposure.py CLI and services/market_runtime/squeeze."), then MOVE (cut, don't copy) the six function bodies from `gamma_exposure.py` verbatim, renamed without underscore. Imports needed: `numpy as np`, `pandas as pd`, `from scipy.stats import norm`. In `gamma_exposure.py` delete the moved bodies and add:

```python
from gex_core import (
    bs_gamma as _bs_gamma,
    compute_squeeze_score as _compute_squeeze_score,
    gex_per_one_percent as _gex_per_one_percent,
    max_pain as _max_pain,
    price_consistency as _price_consistency,
    zero_gamma_flip as _zero_gamma_flip,
)
```

(Aliases keep every internal call site and `tests/test_gamma_flip.py` working unchanged.)
- [ ] **Step 4: Verify** — `pytest tests/test_gex_core.py tests/test_gamma_flip.py -v` → all PASS. Also `python -c "import sys; sys.path.insert(0,'tools'); import gamma_exposure"` → no error.
- [ ] **Step 5: Commit** — `git add tools/gex_core.py tools/gamma_exposure.py tests/test_gex_core.py && git commit -m "refactor: extract pure GEX math into tools/gex_core"`

---

### Task 2: `squeeze` package — config + snapshot

**Files:**
- Create: `services/market_runtime/squeeze/__init__.py`, `services/market_runtime/squeeze/config.py`, `services/market_runtime/squeeze/snapshot.py`
- Test: `tests/market_runtime/test_squeeze_snapshot.py`

**Interfaces:**
- Produces:
  - `SqueezeConfig` frozen dataclass (fields + defaults below) with `.weights_json() -> str`.
  - `SqueezeSnapshot` dataclass; `SqueezeSnapshot.from_gamma_result(result: dict, ts: float, degraded: bool) -> SqueezeSnapshot`; `snap.to_json() -> str`; `SqueezeSnapshot.from_json(s: str) -> SqueezeSnapshot`.
- `__init__.py` re-exports: `SqueezeConfig`, `SqueezeSnapshot` (and later `SqueezeEngine`, `SqueezeStore`, `SqueezeManager`).

- [ ] **Step 1: Failing tests** — `tests/market_runtime/test_squeeze_snapshot.py`:

```python
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
```

- [ ] **Step 2: Verify failure** — `pytest tests/market_runtime/test_squeeze_snapshot.py -v` → FAIL.
- [ ] **Step 3: Implement**:

`config.py`:

```python
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
```

`snapshot.py`:

```python
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
```

`__init__.py`:

```python
from .config import SqueezeConfig
from .snapshot import SqueezeSnapshot

__all__ = ["SqueezeConfig", "SqueezeSnapshot"]
```

- [ ] **Step 4: Verify** — `pytest tests/market_runtime/test_squeeze_snapshot.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat: squeeze package config + snapshot`

---

### Task 3: Engine dynamics (`compute_dynamics`)

**Files:**
- Create: `services/market_runtime/squeeze/dynamics.py`
- Test: `tests/market_runtime/test_squeeze_dynamics.py`

**Interfaces:**
- Consumes: `SqueezeSnapshot`, `SqueezeConfig`.
- Produces:
  - `@dataclass FlowBaseline: n: int = 0; mean: float = 0.0; m2: float = 0.0` with `.update(x: float) -> None` and `.z(x: float) -> float` (Welford; `z` returns 0.0 when `n < 3` or std == 0).
  - `compute_dynamics(history: Sequence[SqueezeSnapshot], baseline: FlowBaseline, cfg: SqueezeConfig) -> dict[str, float]` — keys exactly: `wall_build_score`, `flow_accel_score`, `spot_kinetics_score`, `iv_lift_score`, `dynamic_score`. Also mutates `baseline` with this window's total flow. `history[-1]` is the newest snapshot; the reference is the oldest snapshot within `cfg.window_minutes` of it.

Semantics (implement exactly):
- `len(history) < 2` → all zeros.
- `ref` = oldest snap with `newest.ts - snap.ts <= window_minutes * 60`; `dt_min = max((newest.ts - ref.ts) / 60, 1.0)`.
- **wall_build**: `rel = ((newest.call_wall_gex - ref.call_wall_gex) - (newest.put_wall_gex - ref.put_wall_gex)) / max(newest.abs_book, 1.0)`; `rate = rel * (cfg.window_minutes / dt_min)`; `score = cfg.wall_build_max_points * tanh(cfg.wall_build_tanh_gain * rate)`.
- **flow_accel**: `dcall = max(newest.otm_call_volume - ref.otm_call_volume, 0)`; `dput = max(newest.otm_put_volume - ref.otm_put_volume, 0)`; `total = dcall + dput`; `imbalance = (dcall - dput) / max(total, 1.0)`; `magnitude = clamp(baseline.z(total) / 2, 0, 1)` but `0.5` when `baseline.n < 3`; `score = cfg.flow_accel_max_points * imbalance * magnitude`; then `baseline.update(total)`.
- **spot_kinetics**: `vel = (newest.spot - ref.spot) / ref.spot * 100 / dt_min` (%/min). Relevant wall: call wall if `vel > 0` else put wall; `dist_pct = abs(wall - spot) / spot * 100` (missing wall → proximity 0); `em = expected_move_pct if > 0.1 else 5.0`; `proximity = max(0, 1 - dist_pct / em)`; `score = cfg.spot_kinetics_max_points * tanh(vel / cfg.spot_velocity_unit_pct_per_min) * proximity`.
- **iv_lift**: `subtotal = wall_build_score + flow_accel_score + spot_kinetics_score`; if `subtotal == 0` or either `expected_move_pct` is None → 0; else `d_em = newest.expected_move_pct - ref.expected_move_pct`; `score = cfg.iv_lift_max_points * tanh(d_em / cfg.iv_lift_unit_pp) * (1 if subtotal > 0 else -1)`.
- **regime damp**: if `newest.near_net >= 0`, multiply every component by `cfg.positive_gex_damp`; else multiply by `min(1.0, abs(newest.near_net) / max(abs(newest.net_dealer), 1.0))`.
- `dynamic_score = clamp(sum of 4, -100, 100)`.

- [ ] **Step 1: Failing tests** — `tests/market_runtime/test_squeeze_dynamics.py`:

```python
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
```

- [ ] **Step 2: Verify failure** — `pytest tests/market_runtime/test_squeeze_dynamics.py -v` → FAIL.
- [ ] **Step 3: Implement `dynamics.py`** exactly per the semantics block above (single `compute_dynamics` function + `FlowBaseline`; use `math.tanh`; write a `_clamp` helper locally).
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `feat: squeeze dynamic components (wall build, flow accel, kinetics, IV lift)`

---

### Task 4: Engine — phase machine, confidence, alerts, `SqueezeEngine.step`

**Files:**
- Create: `services/market_runtime/squeeze/engine.py`
- Modify: `services/market_runtime/squeeze/__init__.py` (export `SqueezeEngine`, `StepResult`)
- Test: `tests/market_runtime/test_squeeze_engine.py`

**Interfaces:**
- Consumes: `SqueezeSnapshot`, `compute_dynamics`, `FlowBaseline`, `SqueezeConfig`.
- Produces:

```python
@dataclass
class StepResult:
    ts: float
    score: float
    structural: float
    dynamic: float
    components: dict[str, float]      # structural_components + dynamic components merged
    phase: str                        # "none" | "building" | "peaking" | "fading"
    direction: str                    # "bull" | "bear" | "none"
    phase_seconds: float
    confidence: float                 # 0..100
    confidence_parts: dict[str, float]
    alerts: list[dict]                # 0..n transition alerts

class SqueezeEngine:
    def __init__(self, cfg: SqueezeConfig | None = None) -> None
    def step(self, snap: SqueezeSnapshot, track_factor: float = 1.0,
             chain_age_minutes: float = 0.0) -> StepResult
    def reset(self) -> None
```

Phase machine rules (implement exactly; direction = sign of score):
- Track `rising_polls`: +1 when |score| increased vs previous poll *in the current direction*, reset on direction flip or decrease.
- Track `session_peak_abs`: max |score| since phase left "none"; reset when phase returns to "none".
- `none → building`: |score| ≥ `build_enter_score` AND `rising_polls ≥ min_rising_polls`.
- `building → peaking`: |score| ≥ `peak_enter_score` AND |score − prev_score| ≤ `peak_flat_eps`.
- `building|peaking → fading`: |score| ≤ `session_peak_abs − fade_drop_points`.
- `fading → none`: |score| < `none_exit_score`.
- Direction flip while in any phase (sign of score crosses zero with |score| ≥ `build_enter_score` rising): emit `enter_fading` for old direction then treat as fresh `none` state next poll.
- No transition out of a phase before `min_dwell_polls` polls in it (except `fading → none`).
- Alerts emitted on transitions INTO building, peaking, fading; dict: `{"ts", "direction", "transition" ("enter_building"|"enter_peaking"|"enter_fading"), "score", "spot", "confidence", "components"}`.

Confidence (0–100): `100 * freshness * quality * agreement * track` where
- `freshness = clip(1 - chain_age_minutes / 30, 0.3, 1.0)`
- `quality = clip(n_contracts / 200, 0.3, 1.0) * (0.5 if degraded else 1.0)`
- `agreement = 1.0` if structural and dynamic same sign and both nonzero; `0.75` if exactly one is zero; `0.5` if opposite signs
- `track = track_factor` (caller supplies; 1.0 when unproven), clipped to `[0.5, 1.2]`
- final clipped to `[0, 100]`, `confidence_parts = {"freshness", "quality", "agreement", "track"}`.

- [ ] **Step 1: Failing tests** — `tests/market_runtime/test_squeeze_engine.py` (build sequences by monkeypatching structural score directly on snapshots; dynamics naturally ~0 for flat inputs, so drive score via `structural_score` and spot moves):

```python
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
```

- [ ] **Step 2: Verify failure** — FAIL (`ImportError: SqueezeEngine`).
- [ ] **Step 3: Implement `engine.py`** per the interface + rules blocks. The engine holds `self._history: deque(maxlen=cfg.history_maxlen)`, `self._baseline = FlowBaseline()`, and mutable phase fields; `step()` appends snapshot, calls `compute_dynamics`, computes score, applies phase rules, computes confidence, returns `StepResult`. Export in `__init__.py`.
- [ ] **Step 4: Verify** — `pytest tests/market_runtime/test_squeeze_engine.py -v` → PASS. Re-run task 2–3 tests too.
- [ ] **Step 5: Commit** — `feat: squeeze engine phase machine + confidence + alerts`

---

### Task 5: `SqueezeStore` (SQLite)

**Files:**
- Create: `services/market_runtime/squeeze/store.py`
- Modify: `services/market_runtime/squeeze/__init__.py` (export)
- Test: `tests/market_runtime/test_squeeze_store.py`

**Interfaces:**
- Produces `class SqueezeStore` (thread-safe via `threading.Lock`, one `sqlite3` connection, `check_same_thread=False`, WAL):

```python
class SqueezeStore:
    def __init__(self, symbol: str, root: Path | str | None = None) -> None
        # db path: (root or REPO_ROOT/"data_cache"/"squeeze")/f"{symbol.upper()}.sqlite"
    def append(self, snap: SqueezeSnapshot, step: StepResult, weights_json: str) -> None
    def insert_alert(self, alert: dict) -> int          # returns alert id
    def alerts_without_outcome(self, horizon_min: int) -> list[dict]  # includes "id"
    def insert_outcome(self, alert_id: int, horizon_min: int,
                       realized_ret_pct: float, hit: bool, resolved_ts: float) -> None
    def spot_at_or_after(self, ts: float, not_after: float | None = None) -> tuple[float, float] | None
    def last_spot_of_day(self, day_start_ts: float, day_end_ts: float) -> tuple[float, float] | None
    def timeline(self, since_ts: float) -> list[dict]   # {"ts","score","phase","direction","spot"}
    def snapshots_between(self, t0: float, t1: float) -> list[SqueezeSnapshot]  # from snap_json
    def alerts_since(self, since_ts: float) -> list[dict]  # joined with outcomes
    def stats(self) -> dict
    def close(self) -> None
```

`stats()` returns exactly:

```python
{
  "alerts_total": int, "resolved_total": int,
  "by_horizon": {"30": {"n": int, "hits": int, "hit_rate": float | None},
                  "120": {...}},
  "by_direction": {"bull": {"n": int, "hits": int, "hit_rate": float | None},
                    "bear": {...}},
  "avg_favorable_pct": float | None,   # mean of realized_ret_pct where hit
  "worst_adverse_pct": float | None,   # min of realized_ret_pct
}
```

DDL (run in `__init__`):

```sql
CREATE TABLE IF NOT EXISTS snapshots(
  ts REAL PRIMARY KEY, spot REAL NOT NULL, score REAL NOT NULL,
  structural REAL NOT NULL, dynamic REAL NOT NULL, phase TEXT NOT NULL,
  direction TEXT NOT NULL, confidence REAL NOT NULL, components TEXT NOT NULL,
  weights TEXT NOT NULL, degraded INTEGER NOT NULL, n_contracts INTEGER NOT NULL,
  snap_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, direction TEXT NOT NULL,
  transition TEXT NOT NULL, score REAL NOT NULL, spot REAL NOT NULL,
  confidence REAL NOT NULL, components TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes(
  alert_id INTEGER NOT NULL, horizon_min INTEGER NOT NULL,
  realized_ret_pct REAL NOT NULL, hit INTEGER NOT NULL, resolved_ts REAL NOT NULL,
  PRIMARY KEY(alert_id, horizon_min));
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
```

- [ ] **Step 1: Failing tests** — `tests/market_runtime/test_squeeze_store.py` using `tmp_path` as root: append two snapshots + steps, insert bull alert, assert `alerts_without_outcome(30)` returns it, insert outcome (hit, +0.5), assert it disappears and `stats()["by_horizon"]["30"]["hit_rate"] == 1.0`; `spot_at_or_after` picks first ts ≥ target and respects `not_after`; `timeline` ordered ascending; `snapshots_between` reconstructs `SqueezeSnapshot` with empty payload; re-open same path → data persisted. Write ~8 focused test functions with real asserts (no placeholders).
- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement `store.py`.** REPO_ROOT = `Path(__file__).resolve().parents[3]`. All writes under `with self._lock:`; `conn.execute("PRAGMA journal_mode=WAL")`. `stats()` via SQL aggregates.
- [ ] **Step 4: Verify** — PASS. Confirm `data_cache/` is gitignored: `git check-ignore data_cache/squeeze/X.sqlite || echo ADD-IGNORE` — if ADD-IGNORE, append `data_cache/` to `.gitignore` in this commit.
- [ ] **Step 5: Commit** — `feat: squeeze sqlite store (snapshots, alerts, outcomes)`

---

### Task 6: Evaluator (alert outcome resolution)

**Files:**
- Create: `services/market_runtime/squeeze/evaluator.py`
- Test: `tests/market_runtime/test_squeeze_evaluator.py`

**Interfaces:**
- Consumes: `SqueezeStore`, `SqueezeConfig`.
- Produces:

```python
def resolve_pending(store: SqueezeStore, cfg: SqueezeConfig, now_ts: float,
                    backfill_fn: Callable[[float], float | None] | None = None) -> int
```

Rules (exact):
- For each `(horizon, threshold)` in `zip(cfg.horizons_minutes, cfg.hit_thresholds_pct)`, for each alert from `store.alerts_without_outcome(horizon)` with `transition != "enter_fading"` (fading alerts are informational, never scored):
  - `deadline = alert["ts"] + horizon * 60`. If `now_ts < deadline`: skip.
  - Resolution price, in order: (1) `store.spot_at_or_after(deadline, not_after=deadline + 2 * cfg.poll_seconds)`; (2) `backfill_fn(deadline)` if provided and non-None; (3) if the session ended (no snapshot within 30 min after deadline AND `now_ts > deadline + 3600`): `store.last_spot_of_day(...)` for the alert's UTC day; else skip (stay pending).
  - `sign = +1 if alert["direction"] == "bull" else -1`; `ret_pct = sign * (price / alert["spot"] - 1) * 100`; `hit = ret_pct >= threshold`.
  - `store.insert_outcome(alert_id, horizon, ret_pct, hit, now_ts)`; count it.
- Return number of outcomes inserted.
- Also produce `track_factor(stats: dict, cfg: SqueezeConfig) -> float`: `1.0` if `stats["resolved_total"] < cfg.min_resolved_for_track`; else overall hit-rate `h` across horizons → `clamp(2 * h, 0.5, 1.2)`.

- [ ] **Step 1: Failing tests** — seed a store in `tmp_path` with an `enter_building` bull alert at ts=1000 spot=100, snapshots at ts 1000..(1000+40*90) with spot ramping 100→101: resolve at `now=1000+31*60` → 30 m outcome hit (ret ≥ 0.2). Bear alert with rising spot → miss with negative ret. No spot after deadline and no backfill → stays pending (returns 0 for it). With `backfill_fn=lambda ts: 102.0` → resolves. `enter_fading` alerts never resolve. `track_factor`: below-min stats → 1.0; 30 resolved / 24 hits → `min(1.2, 2*0.8)` = 1.2; 30 resolved / 6 hits → 0.5.
- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement `evaluator.py`** per rules.
- [ ] **Step 4: Verify** — PASS.
- [ ] **Step 5: Commit** — `feat: squeeze alert evaluator + track factor`

---

### Task 7: Watcher thread + manager

**Files:**
- Create: `services/market_runtime/squeeze/watcher.py`
- Modify: `services/market_runtime/squeeze/__init__.py` (export `SqueezeManager`)
- Test: `tests/market_runtime/test_squeeze_watcher.py`

**Interfaces:**
- Consumes: everything above.
- Produces:

```python
class SqueezeWatcher(threading.Thread):
    def __init__(self, symbol: str, cfg: SqueezeConfig,
                 fetch_fn: Callable[[str], tuple[dict, bool]],  # -> (gamma_result, degraded)
                 store_root: Path | str | None = None,
                 clock: Callable[[], float] = time.time,
                 tick_wait: float | None = None) -> None  # tick_wait overrides poll sleep in tests
    def heartbeat(self) -> None
    def request_stop(self) -> None
    def state(self) -> dict          # full API payload, see below
    daemon = True

class SqueezeManager:
    def __init__(self, cfg: SqueezeConfig | None = None,
                 fetch_fn: Callable[[str], tuple[dict, bool]] | None = None,
                 store_root: Path | str | None = None) -> None
    def watch(self, symbol: str) -> dict      # start if absent, heartbeat, return state()
    def state(self, symbol: str) -> dict | None
    def ledger(self, symbol: str) -> dict | None   # {"alerts": [...], "stats": {...}}
    def stop_all(self) -> None

def default_fetch(symbol: str) -> tuple[dict, bool]:
    """Imports tools.gamma_exposure.compute_gamma_exposure; degraded = result source != 'lse'."""
```

Watcher loop (each iteration): if `clock() - last_heartbeat > cfg.heartbeat_ttl_seconds` → stop. Try `fetch_fn`; on success: build `SqueezeSnapshot`, `track = track_factor(store.stats(), cfg)`, `res = engine.step(snap, track_factor=track, chain_age_minutes=...)`, `store.append`, insert alerts, `resolve_pending(store, cfg, now)`, reset failure count/backoff. On exception: increment `consecutive_failures`, double backoff up to `cfg.max_backoff_seconds`; a `RuntimeError` containing "differs from trusted spot" increments `rejected_snapshots` instead of failures. Sleep `poll_seconds` (or backoff) using an `threading.Event.wait` so `request_stop()` is immediate; `tick_wait` overrides for tests.

`state()` payload (exact keys):

```python
{
  "symbol", "phase", "direction", "phase_seconds", "score", "structural", "dynamic",
  "confidence", "confidence_parts", "components",
  "spot", "call_wall", "put_wall", "flip", "regime",
  "net_dealer_gex", "near_spot_dealer_gex", "expected_move_pct",
  "by_strike",                       # passthrough from last payload
  "feed": "lse" | "degraded",
  "stale": bool,                     # clock() - last_success_ts > stale_after_polls * poll_seconds
  "last_poll_ts", "poll_age_seconds", "consecutive_failures", "rejected_snapshots",
  "watch_expires_in",                # seconds until TTL stop
  "timeline",                        # store.timeline(session start = last 8h)
  "ledger_stats",                    # store.stats()
  "alerts_today",                    # store.alerts_since(last 24h)
  "error": str | None,               # last fetch error message
  "asof",                            # iso utc of last success
}
```

Before first successful poll, `state()` returns the same shape with `score=0, phase="none", spot=None, by_strike=[], error=<last error or None>`.

- [ ] **Step 1: Failing tests** — with a scripted `fetch_fn` returning the Task 2 `GAMMA_RESULT` fixture (import it or redefine): watcher with `tick_wait=0.01`, `cfg = SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=2)`; assert after ~5 ticks state has `score` set, `feed == "lse"`, snapshots persisted (store row count > 1); TTL expiry: stop heartbeating, thread dies within 2s (`join(timeout=5)`, `not is_alive()`). Failure path: fetch raises → `consecutive_failures` grows, state carries `error`, thread alive. Divergence path: raise `RuntimeError("... differs from trusted spot ...")` → `rejected_snapshots == 1`, `consecutive_failures == 0`. Manager: `watch()` twice → one thread; `state("UNKNOWN") is None`; `stop_all()` joins.
- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement `watcher.py`.** `default_fetch` does `sys.path` bootstrap mirroring `api.py` (ROOT, ROOT/tools) then `from gamma_exposure import compute_gamma_exposure`; call with `(symbol, spot_source="auto", source="auto")`; `degraded = str(result.get("source") or "") != "lse"`; raise on `result.get("error")`.
- [ ] **Step 4: Verify** — PASS; also rerun the whole `tests/market_runtime/` suite.
- [ ] **Step 5: Commit** — `feat: squeeze watcher thread + manager with heartbeat TTL`

---

### Task 8: FastAPI endpoints

**Files:**
- Modify: `services/market_runtime/api.py` (add `squeeze_manager` param + 3 endpoints), `services/market_runtime/server.py` (construct manager, pass in)
- Test: `tests/market_runtime/test_squeeze_api.py`

**Interfaces:**
- Consumes: `SqueezeManager` from Task 7; existing `_validated_identifier`, `_SYMBOL_RE`, auth middleware (token via `X-API-Key` — already global, nothing to add).
- Produces endpoints:
  - `POST /squeeze/watch` body `{"symbol": "TSLA"}` → 200 `manager.watch(symbol)` payload; 400 invalid symbol; 503 `{"detail": "squeeze manager not configured"}` when manager is None.
  - `GET /squeeze/state/{symbol}` → 200 state; 404 `{"detail": "not watched"}` when `manager.state()` is None; 503 when unconfigured.
  - `GET /squeeze/ledger/{symbol}` → 200 `manager.ledger(symbol)`; 404 / 503 same as state.
- `create_app(supervisor=None, vault_client=None, squeeze_manager=None)`; `app.state.squeeze_manager = squeeze_manager`; lifespan shutdown calls `squeeze_manager.stop_all()` when set.
- `server.py`: `squeeze_manager = SqueezeManager()` (default fetch) and pass to `create_app`.

- [ ] **Step 1: Failing tests** — `tests/market_runtime/test_squeeze_api.py` mirroring `test_api.py` style: build `create_app(squeeze_manager=SqueezeManager(cfg=SqueezeConfig(poll_seconds=1, heartbeat_ttl_seconds=60), fetch_fn=fake, store_root=tmp))` with `TestClient`; assert watch→200 with `symbol` key; state 200 after watch; `GET /squeeze/state/NOPE` → 404; bad symbol `POST {"symbol": "$$$"}` → 400; `create_app()` (no manager) → 503 on all three.
- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement** endpoints + server wiring.
- [ ] **Step 4: Verify** — PASS incl. existing `test_api.py` + `test_runtime_auth.py`.
- [ ] **Step 5: Commit** — `feat: /squeeze API endpoints on market-runtime`

---

### Task 9: Replay harness

**Files:**
- Create: `services/market_runtime/squeeze/replay.py` (also `__main__` runnable)
- Test: `tests/market_runtime/test_squeeze_replay.py`

**Interfaces:**
- Consumes: `SqueezeStore.snapshots_between`, `SqueezeEngine`.
- Produces:

```python
def replay(symbol: str, t0: float, t1: float, store_root=None,
           cfg: SqueezeConfig | None = None) -> dict
# {"symbol", "n_snapshots", "transitions": [{"ts","transition","direction","score"}],
#  "final_phase", "score_series": [{"ts","score","stored_score","drift"}],
#  "max_abs_drift": float}
def main(argv: list[str] | None = None) -> int   # --symbol required, --date YYYY-MM-DD,
                                                 # --from/--to unix ts override, --db-root
```

`replay` reconstructs snapshots from `snap_json`, runs a FRESH engine over them (track_factor=1.0), records transitions, and compares recomputed scores to stored ones (`drift = recomputed - stored`) — nonzero drift means the engine changed since capture; that is the point (regression signal). `main` prints a JSON report and returns 0.

- [ ] **Step 1: Failing tests** — seed store via engine+store loop over 10 synthetic ramping snapshots (reuse the Task 4 `snap()` idea inline); `replay()` returns `n_snapshots == 10`, transitions non-empty, `max_abs_drift == 0.0` (same engine version). `main(["--symbol","TSLA","--db-root",str(tmp)])` returns 0 and prints valid JSON (capsys).
- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement** + `if __name__ == "__main__": raise SystemExit(main())`.
- [ ] **Step 4: Verify** — PASS; then run the FULL python suite: `pytest tests/ -q` → all green.
- [ ] **Step 5: Commit** — `feat: squeeze replay harness (model regression tool)`

---

### Task 10: Next.js proxy route

**Files:**
- Create: `apps/trade-desk/src/app/api/squeeze/[...path]/route.ts`
- Modify: `apps/trade-desk/src/lib/backendUrl.ts` (add helper), `apps/trade-desk/src/lib/backendUrl.test.ts` (extend)

**Interfaces:**
- Consumes: `marketRuntimeEndpointUrl` from `backendUrl.ts`; `MARKET_RUNTIME_URL`, `MARKET_RUNTIME_API_TOKEN` env.
- Produces:
  - `squeezeEndpointUrl(pathParts: string[], env?: EnvLike): string | null` in `backendUrl.ts` — returns `null` unless every part matches `/^[A-Za-z0-9.^-]{1,24}$/` and `pathParts[0]` is one of `watch|state|ledger`; joins onto `marketRuntimeEndpointUrl("squeeze/...")`, falling back to `http://localhost:8000/squeeze/...` when `MARKET_RUNTIME_URL` unset.
  - Route handlers `GET` and `POST` forwarding method, JSON body (POST), and `X-API-Key` (when token set), with `cache: "no-store"`, 10 s `AbortSignal.timeout`; upstream non-JSON or network error → 502 `{"detail": "..."}`; invalid path → 404.

- [ ] **Step 1: Failing test** — extend `backendUrl.test.ts` with `squeezeEndpointUrl` checks: fallback URL when env empty; uses `MARKET_RUNTIME_URL` when set; rejects `["state", "../evil"]` and `["nope", "TSLA"]` with null. Run: `cd apps/trade-desk && npx sucrase-node src/lib/backendUrl.test.ts` → FAIL.
- [ ] **Step 2: Implement helper + route.** Route (complete):

```ts
import { NextResponse } from "next/server";

import { squeezeEndpointUrl } from "@/lib/backendUrl";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function forward(req: Request, pathParts: string[], method: "GET" | "POST") {
  const url = squeezeEndpointUrl(pathParts);
  if (!url) {
    return NextResponse.json({ detail: "unknown squeeze path" }, { status: 404 });
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = process.env.MARKET_RUNTIME_API_TOKEN?.trim();
  if (token) headers["X-API-Key"] = token;
  try {
    const res = await fetch(url, {
      method,
      headers,
      body: method === "POST" ? await req.text() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    const text = await res.text();
    try {
      return NextResponse.json(JSON.parse(text), { status: res.status });
    } catch {
      return NextResponse.json(
        { detail: `runtime returned non-JSON (${res.status})` },
        { status: 502 },
      );
    }
  } catch (e) {
    return NextResponse.json(
      { detail: e instanceof Error ? e.message : String(e) },
      { status: 502 },
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: Request, ctx: Ctx) {
  return forward(req, (await ctx.params).path ?? [], "GET");
}

export async function POST(req: Request, ctx: Ctx) {
  return forward(req, (await ctx.params).path ?? [], "POST");
}
```

- [ ] **Step 3: Verify** — `npx sucrase-node src/lib/backendUrl.test.ts` PASS; `npm run typecheck` in `apps/trade-desk` clean.
- [ ] **Step 4: Commit** — `feat: /api/squeeze proxy to market-runtime`

---

### Task 11: TS lib — squeeze types + helpers

**Files:**
- Create: `apps/trade-desk/src/lib/squeeze.ts`, `apps/trade-desk/src/lib/squeeze.test.ts`
- Modify: `apps/trade-desk/package.json` (append `&& sucrase-node src/lib/squeeze.test.ts` to `test` script)

**Interfaces:**
- Produces (exact exports; UI in Task 12 imports these — keep names):

```ts
export type SqueezePhase = "none" | "building" | "peaking" | "fading";
export type SqueezeDirection = "bull" | "bear" | "none";

export interface SqueezeTimelinePoint { ts: number; score: number; phase: SqueezePhase; direction: SqueezeDirection; spot: number; }
export interface SqueezeLedgerStats { alerts_total: number; resolved_total: number; by_horizon: Record<string, { n: number; hits: number; hit_rate: number | null }>; by_direction: Record<string, { n: number; hits: number; hit_rate: number | null }>; avg_favorable_pct: number | null; worst_adverse_pct: number | null; }
export interface SqueezeAlertRow { id: number; ts: number; direction: SqueezeDirection; transition: string; score: number; spot: number; confidence: number; outcomes?: Record<string, { realized_ret_pct: number; hit: boolean }>; }
export interface SqueezeState { symbol: string; phase: SqueezePhase; direction: SqueezeDirection; phase_seconds: number; score: number; structural: number; dynamic: number; confidence: number; confidence_parts: Record<string, number>; components: Record<string, number>; spot: number | null; call_wall: number | null; put_wall: number | null; flip: number | null; regime: string | null; net_dealer_gex: number | null; near_spot_dealer_gex: number | null; expected_move_pct: number | null; by_strike: { strike: number; net_gex: number; call_gex: number; put_gex: number }[]; feed: "lse" | "degraded"; stale: boolean; last_poll_ts: number | null; poll_age_seconds: number | null; consecutive_failures: number; rejected_snapshots: number; watch_expires_in: number | null; timeline: SqueezeTimelinePoint[]; ledger_stats: SqueezeLedgerStats | null; alerts_today: SqueezeAlertRow[]; error: string | null; asof: string | null; }

export function phaseColorVar(phase: SqueezePhase, direction: SqueezeDirection): string;
// bull+building -> "var(--td-action-buy-breakout)"; bull+peaking -> "var(--td-action-buy-now)";
// bear building|peaking -> "var(--td-action-avoid)"; any fading -> "var(--td-action-wait)";
// none -> "var(--td-muted)"
export function phaseHeadline(phase: SqueezePhase, direction: SqueezeDirection, phaseSeconds: number): string;
// "BULLISH SQUEEZE — BUILDING · 24 MIN"; "NO SQUEEZE" for none; "BEARISH SQUEEZE — FADING · 8 MIN"
export function squeezeNarrative(s: SqueezeState): string;
// Operator English, <=160 chars, from strongest components: e.g.
// "Pressure building into the 32 call wall. Fuel: -$1.8B near-spot GEX. Flow accelerating in OTM calls."
// none-phase: "No squeeze pressure. Dealers pinned / balanced book." Degraded: append " (EOD OI data)".
export function formatGexDollars(v: number | null | undefined): string; // -1.8e9 -> "-$1.8B"; 2.5e6 -> "+$2.5M"; null -> "—"
export function formatAgeSeconds(sec: number | null | undefined): string; // 14 -> "14s"; 200 -> "3m20s"; null -> "—"
export function confidenceEvidenceTag(stats: SqueezeLedgerStats | null, minResolved?: number): string;
// resolved < 20 -> "unproven · n=7"; else "hit 63% · n=41" (overall resolved hit rate)
```

- [ ] **Step 1: Failing tests** — `squeeze.test.ts` in the repo's assert style (copy the `check()` harness from `format.test.ts`): cover every helper: color mapping table (all 4×3 combos that matter), headline strings exact, `formatGexDollars(-1.8e9) === "-$1.8B"`, `formatGexDollars(0) === "$0"`, age formats, evidence tag both branches, narrative for a bull-building state mentions "call wall" and for degraded appends "(EOD OI data)". Register in package.json, run `npm test` → FAIL.
- [ ] **Step 2: Implement `squeeze.ts`.** Keep helpers pure; no React.
- [ ] **Step 3: Verify** — `npm test` (all suites) + `npm run typecheck` → PASS.
- [ ] **Step 4: Commit** — `feat: squeeze lib types + display helpers`

---

### Task 12: Squeeze Desk UI

**Files:**
- Create: `apps/trade-desk/src/components/gamma/squeeze/SqueezeDesk.tsx` (container + polling), `SqueezeMeter.tsx`, `SessionTimeline.tsx`, `StrikeLadder.tsx`, `ComponentBars.tsx`, `TrackRecord.tsx`
- Modify: `apps/trade-desk/src/app/live/page.tsx:90` — replace `<GammaExposureDesk showHeader={false} />` with `<SqueezeDesk />` (import swap). `GammaExposureDesk.tsx` and `GammaScene.tsx` stay in the repo, unrendered.

**Interfaces:**
- Consumes: everything from `@/lib/squeeze` (Task 11 names), `Chip`/`Stat`/`EmptyState` from `@/components/ui`, CSS vars from `globals.css` (`--td-*`), fetch endpoints `/api/squeeze/state/{sym}` (GET), `/api/squeeze/watch` (POST), `/api/squeeze/ledger/{sym}` (GET).
- Produces: `export function SqueezeDesk({ initialSymbol }: { initialSymbol?: string })`.

Container behavior (`SqueezeDesk.tsx`):
- Symbol state seeded from `?symbol=` query (same pattern as `GammaExposureDesk.tsx:317`), default `"TSLA"`.
- On symbol set + every 60 s: `POST /api/squeeze/watch {symbol}` (heartbeat). Every 20 s: `GET /api/squeeze/state/{symbol}` → `setState`. Both paused when `document.hidden` (visibilitychange listener). 404 from state → show "starting watcher…" pending panel. Fetch errors → inline error banner naming the failure, keep last good state rendered with `STALE` badge.
- Layout (single column, `max-w-[1200px]`, dense):
  1. Command bar: symbol input (uppercase, submit on Enter), feed badge (`LSE LIVE` with pulsing dot when `!stale && feed==="lse"`; `DEGRADED — EOD OI` amber when degraded; `STALE` gray when stale), poll age (`formatAgeSeconds`), rejected-snapshot count when > 0.
  2. Hero: `SqueezeMeter` (left, 2/3) + confidence block (right, 1/3): confidence number (Source Serif, tabular), `confidenceEvidenceTag`, narrative line (`squeezeNarrative`).
  3. `SessionTimeline` full width.
  4. Grid: `StrikeLadder` (left 1/2) + `ComponentBars` (right 1/2).
  5. `TrackRecord` full width.
  - Honest empty state before first data: EmptyState explaining the watcher is warming up and what will appear.

`SqueezeMeter.tsx` — props `{ score, phase, direction, phaseSeconds }`. Horizontal SVG gauge: track −100..+100 with center tick at 0, zone shading beyond ±25 and ±55 (hairline opacity fills), needle line at `score` with 200ms CSS transition (`transition: transform 200ms ease`), score numeral (Source Serif, 48px, tabular) and `phaseHeadline` beneath in `phaseColorVar` color. No gradients.

`SessionTimeline.tsx` — props `{ timeline, alerts }`. SVG area/line of score vs time (last 8 h), y −100..+100 with zero line, background bands where phase ≠ none tinted by `phaseColorVar` at 12% opacity, alert markers as vertical ticks with direction color. Empty → EmptyState "Timeline builds as the watcher polls."

`StrikeLadder.tsx` — props `{ byStrike, spot, callWall, putWall, flip, components }`. Vertical ladder (strikes descending), for the 21 strikes nearest spot: horizontal bar per strike — `call_gex` rightward in `--td-action-buy-breakout`, `put_gex` leftward in `--td-action-avoid`, width scaled to max |gex| in view, 1px hairline rows, strike labels mono. Spot: full-width line in `--td-ink` with price tag; walls: highlighted rows with `▲ building` / `▼ eroding` arrow when `components.wall_build_score` is > +2 / < −2 (call wall) and mirrored for put wall; flip: dashed hairline. All tabular nums.

`ComponentBars.tsx` — props `{ components, structural, dynamic }`. Two grouped lists (STRUCTURAL / DYNAMIC) of signed horizontal bars centered at 0 (max |15|..|30| scale per component ceiling), label left (mono, uppercase, `--td-muted`), value right, bar in buy-breakout for positive / avoid for negative at 80% opacity. Include every key present in `components`.

`TrackRecord.tsx` — props `{ stats, alerts }`. Left card: hit-rate per horizon (`30m`, `2h`) with n, `avg_favorable_pct`, `worst_adverse_pct`, evidence tag; right: dense mono table of `alerts_today` (time ET, direction chip, transition, score, spot, outcome cell per horizon: `✓ +0.4%` in buy-now color / `✗ -0.3%` in avoid / `· pending` muted). Empty → "No resolved alerts yet — the ledger builds while you watch."

- [ ] **Step 1: Build components** in the order Meter → Timeline → Ladder → Bars → TrackRecord → Desk container (each compiles standalone; no new deps — use existing framer-motion only if already imported patterns exist, otherwise plain CSS transitions).
- [ ] **Step 2: Wire `live/page.tsx`** import swap.
- [ ] **Step 3: Verify** — `npm run typecheck && npm run lint && npm test` all clean; `npm run build` succeeds.
- [ ] **Step 4: Visual smoke** — `npm run dev` + mock: run uvicorn locally with a fake manager is overkill; instead temporarily hit `/live?mode=gamma` and confirm pending/empty states render correctly without backend (honest failure states are part of the spec). If `LSE_API_KEY` present locally, watch a real symbol and confirm meter/timeline/ladder populate.
- [ ] **Step 5: Commit** — `feat: Squeeze Desk UI (meter, timeline, strike ladder, attribution, track record)`

---

### Task 13: Options desk deep-link chip

**Files:**
- Modify: `apps/trade-desk/src/components/options/OptionsDesk.tsx` (header area)

- [ ] **Step 1:** Add one `Chip`-style `<Link href={\`/gamma?symbol=\${symbol}\`}>` labeled `SQUEEZE DESK →` near the desk's existing header controls, colored `var(--td-accent, --td-action-breakout-watch)` consistent with existing chips (inspect neighboring chips and match their exact classes).
- [ ] **Step 2:** `npm run typecheck && npm run lint` clean.
- [ ] **Step 3: Commit** — `feat: options desk deep-link to squeeze desk`

---

### Task 14: Full verification + docs touch

- [ ] **Step 1:** `pytest tests/ -q` → all pass (note count).
- [ ] **Step 2:** `cd apps/trade-desk && npm test && npm run typecheck && npm run lint && npm run build` → all pass.
- [ ] **Step 3:** Boot smoke: `MARKET_RUNTIME_ENV=development .venv/bin/python -m uvicorn services.market_runtime.server:app --port 8000` starts; `curl -s localhost:8000/health` ok; `curl -s -X POST localhost:8000/squeeze/watch -H 'Content-Type: application/json' -d '{"symbol":"TSLA"}'` returns a state JSON (degraded without key is fine, or 503-free error payload with `error` set). Kill server.
- [ ] **Step 4:** Append one line to `models/poc_va_gex/MODEL.md` versions table: `| squeeze_v2 | Live squeeze engine + Squeeze Desk (services/market_runtime/squeeze) | live |`. Do NOT touch README (recruiter-clean rule) beyond nothing.
- [ ] **Step 5: Commit** — `chore: squeeze desk verification + model index entry`
