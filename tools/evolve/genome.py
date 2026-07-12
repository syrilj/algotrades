"""Learnable genome — the continuous parameters the train loop optimizes.

This is *not* end-to-end RL on raw bars. Primary SIDE stays rules-based.
The genome is secondary control: risk, filters, meta thresholds, options hunt.
Think of it as the weights we update each epoch from utility feedback.
"""
from __future__ import annotations

import copy
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BRAIN = ROOT / "runs" / "evolve_brain" / "BRAIN.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Genome:
    """Continuous knobs the loop can train."""

    # identity
    base_model: str = "v23_devin_overlay"
    track: str = "equity_ohlcv"  # or options_synthetic

    # risk / feedback sizing (secondary)
    risk_pct: float = 0.10
    after_loss_mult: float = 0.70
    after_win_mult: float = 1.10
    halt_dd: float = 0.25
    soft_dd: float = 0.12

    # filters / meta
    vol_z_min: float = 0.0  # 0 = off
    min_confidence: float = 0.55
    meta_p_full: float = 0.55  # size 1.0 if P(up) >=
    meta_p_half: float = 0.45

    # options hunt
    dte_days: float = 21.0
    otm_pct: float = 0.0
    flatten_dd: float = 0.40
    struct_weak_mult: float = 0.55
    struct_good_mult: float = 1.15

    # train hyperparameters (meta-learning rate)
    lr: float = 0.15  # relative step size for mutations
    generation: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Genome":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})

    def clip(self) -> "Genome":
        g = copy.deepcopy(self)
        g.risk_pct = float(min(0.35, max(0.03, g.risk_pct)))
        g.after_loss_mult = float(min(1.0, max(0.25, g.after_loss_mult)))
        g.after_win_mult = float(min(1.5, max(0.8, g.after_win_mult)))
        g.halt_dd = float(min(0.45, max(0.10, g.halt_dd)))
        g.soft_dd = float(min(g.halt_dd - 0.02, max(0.05, g.soft_dd)))
        g.vol_z_min = float(min(3.0, max(0.0, g.vol_z_min)))
        g.min_confidence = float(min(0.85, max(0.35, g.min_confidence)))
        g.meta_p_full = float(min(0.80, max(0.50, g.meta_p_full)))
        g.meta_p_half = float(min(g.meta_p_full - 0.02, max(0.35, g.meta_p_half)))
        g.dte_days = float(min(45, max(7, round(g.dte_days))))
        g.otm_pct = float(min(0.08, max(0.0, g.otm_pct)))
        g.flatten_dd = float(min(0.60, max(g.halt_dd + 0.05, g.flatten_dd)))
        g.struct_weak_mult = float(min(1.0, max(0.25, g.struct_weak_mult)))
        g.struct_good_mult = float(min(1.5, max(0.8, g.struct_good_mult)))
        g.lr = float(min(0.5, max(0.03, g.lr)))
        return g


# which fields are continuous and trainable
TRAINABLE: dict[str, tuple[float, float]] = {
    # name: (noise scale,) — larger steps so equity wrapper actually changes behavior
    "risk_pct": (0.08, 1.0),
    "after_loss_mult": (0.12, 1.0),
    "after_win_mult": (0.10, 1.0),
    "halt_dd": (0.05, 1.0),
    "soft_dd": (0.04, 1.0),
    "vol_z_min": (0.35, 1.0),
    "min_confidence": (0.08, 1.0),
    "meta_p_full": (0.05, 1.0),
    "meta_p_half": (0.05, 1.0),
    "dte_days": (5.0, 1.0),
    "otm_pct": (0.02, 1.0),
    "flatten_dd": (0.06, 1.0),
    "struct_weak_mult": (0.10, 1.0),
    "struct_good_mult": (0.08, 1.0),
}


def mutate_genome(parent: Genome, rng: random.Random | None = None) -> Genome:
    """One training step candidate: gaussian noise on knobs, scaled by lr."""
    rng = rng or random.Random()
    child = copy.deepcopy(parent)
    child.generation = parent.generation + 1
    # pick 2–4 knobs to update (sparse updates like SGD on subset)
    keys = list(TRAINABLE.keys())
    if child.track.startswith("equity"):
        keys = [k for k in keys if k not in ("dte_days", "otm_pct", "struct_weak_mult", "struct_good_mult", "flatten_dd")]
    else:
        keys = [k for k in keys if k not in ("vol_z_min", "min_confidence")]  # hunt-focused

    n_touch = rng.randint(2, min(4, len(keys)))
    for k in rng.sample(keys, n_touch):
        scale, _ = TRAINABLE[k]
        cur = float(getattr(child, k))
        noise = rng.gauss(0.0, scale * child.lr)
        setattr(child, k, cur + noise)
    return child.clip()


def genome_to_hunt(g: Genome) -> dict[str, Any]:
    return {
        "risk_pct": g.risk_pct,
        "dte_days": int(g.dte_days),
        "otm_pct": g.otm_pct,
        "halt_dd": g.halt_dd,
        "flatten_dd": g.flatten_dd,
        "use_soft_structure": True,
        "struct_weak_mult": g.struct_weak_mult,
        "struct_good_mult": g.struct_good_mult,
        "min_size_frac": 0.35,
        "narrative_mode": "surgical",
    }


def genome_to_strategy(g: Genome) -> dict[str, Any]:
    return {
        "mutate": "genome_train",
        "vol_z_min": g.vol_z_min,
        "min_confidence": g.min_confidence,
        "meta_p_full": g.meta_p_full,
        "meta_p_half": g.meta_p_half,
        "after_loss_mult": g.after_loss_mult,
        "after_win_mult": g.after_win_mult,
        "soft_dd": g.soft_dd,
        "halt_dd": g.halt_dd,
        "risk_pct": g.risk_pct,
        "generation": g.generation,
    }


@dataclass
class Brain:
    """Persistent training state — like a model checkpoint."""

    genome: Genome = field(default_factory=Genome)
    best_genome: Genome = field(default_factory=Genome)
    best_utility_oos: float = -999.0
    best_utility_train: float = -999.0
    epoch: int = 0
    accepted: int = 0
    rejected: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    meta_recipe: dict[str, Any] | None = None
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome": self.genome.to_dict(),
            "best_genome": self.best_genome.to_dict(),
            "best_utility_oos": self.best_utility_oos,
            "best_utility_train": self.best_utility_train,
            "epoch": self.epoch,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "history": self.history[-200:],
            "lessons": self.lessons[-50:],
            "meta_recipe": self.meta_recipe,
            "updated_at": self.updated_at,
            "role": "secondary_control_only",
            "forbid": ["replace_primary_side_with_end_to_end_rl"],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Brain":
        g = Genome.from_dict(d.get("genome") or {})
        bg = Genome.from_dict(d.get("best_genome") or d.get("genome") or {})
        return cls(
            genome=g,
            best_genome=bg,
            best_utility_oos=float(d.get("best_utility_oos", -999)),
            best_utility_train=float(d.get("best_utility_train", -999)),
            epoch=int(d.get("epoch", 0)),
            accepted=int(d.get("accepted", 0)),
            rejected=int(d.get("rejected", 0)),
            history=list(d.get("history") or []),
            lessons=list(d.get("lessons") or []),
            meta_recipe=d.get("meta_recipe"),
            updated_at=str(d.get("updated_at") or _now()),
        )


def load_brain(path: Path | None = None) -> Brain:
    p = path or DEFAULT_BRAIN
    if not p.exists():
        return Brain()
    return Brain.from_dict(json.loads(p.read_text()))


def save_brain(brain: Brain, path: Path | None = None) -> Path:
    p = path or DEFAULT_BRAIN
    p.parent.mkdir(parents=True, exist_ok=True)
    brain.updated_at = _now()
    p.write_text(json.dumps(brain.to_dict(), indent=2))
    # also write best genome snapshot
    (p.parent / "BEST_GENOME.json").write_text(
        json.dumps(brain.best_genome.to_dict(), indent=2)
    )
    return p


def learn_lesson(brain: Brain, row: dict[str, Any], accepted: bool) -> str:
    """Derive a short training lesson from an epoch result."""
    ret = float(row.get("ret") or 0)
    dd = abs(float(row.get("dd") or 0))
    n = int(row.get("n") or 0)
    u = float(row.get("utility") or 0)
    if accepted:
        msg = f"epoch accept u={u:.3f} ret={ret:.2%} dd={dd:.2%} n={n} — keep genome knobs"
    else:
        if n < 12:
            msg = f"reject thin n={n} — next mutate toward more trades (lower conf / vol_z)"
        elif dd > 0.25:
            msg = f"reject hard DD {dd:.1%} — next tighten halt_dd / risk_pct"
        elif ret <= 0:
            msg = f"reject flat/neg ret — next ease filters or adjust risk"
        else:
            msg = f"reject u={u:.3f} below best — sample new noise"
    brain.lessons.append(msg)
    return msg
