"""Continuous self-improvement loop — train-like feedback.

Each epoch:
  1. Mutate genome (learned secondary knobs) from current champion
  2. Materialize a temporary engine (base model + hunt/strategy overlays)
  3. Backtest TRAIN window + rolling validation window
  4. Score with validation utility (reward); penalize train/validation gap
  5. Accept only if validation improves
  6. Persist BRAIN.json checkpoint + lessons
  7. Every K epochs: retrain meta MLP features (secondary)

Primary SIDE stays rules (PLAYBOOK). Genome = how much / whether / risk.
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.farm import WINDOWS, bags_for_track, discover, run_one_cached  # noqa: E402
from evolve.gates import apply_gates  # noqa: E402
from evolve.genome import (  # noqa: E402
    DEFAULT_BRAIN,
    Brain,
    Genome,
    genome_to_hunt,
    genome_to_strategy,
    learn_lesson,
    load_brain,
    mutate_genome,
    save_brain,
)
from evolve.report import write_leaderboard, write_state  # noqa: E402
from evolve.scoring import enrich_scores, utility_score  # noqa: E402
from evolve.gates import claim_min_trades, dd_hard_from_bar  # noqa: E402
from evolve.auditor import audit_train_epoch, write_audit  # noqa: E402


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _setup_out(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    dmr.OUT = out / "bt"
    dmr.OUT.mkdir(parents=True, exist_ok=True)


# AST-safe wrapper: composition (no sibling import at top-level — runner sandbox).
# Loads _base_engine.py via importlib inside generate(); scales secondary risk.
_GENOME_WRAPPER = '''\
"""Train-loop wrapper: primary SIDE from base; genome scales secondary risk/filters."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Dict

import pandas as pd


class SignalEngine:
    """Secondary control only — does not invent long/short side."""

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        here = Path(__file__).resolve().parent
        base_path = here / "_base_engine.py"
        spec = importlib.util.spec_from_file_location("_train_base_engine", base_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        raw = mod.SignalEngine().generate(data_map)
        gpath = here / "GENOME.json"
        g = {}
        if gpath.exists():
            g = json.loads(gpath.read_text())
        risk = float(g.get("risk_pct", 0.10) or 0.10)
        min_conf = float(g.get("min_confidence", 0.55) or 0.55)
        # min_confidence 0.35..0.85 → zero weak |signal| up to ~0.35
        thr = max(0.0, (min_conf - 0.35) / 0.50) * 0.35
        scale = max(0.20, min(2.5, risk / 0.10))
        out: Dict[str, pd.Series] = {}
        for code, series in raw.items():
            s = series.astype(float) * scale
            if thr > 0:
                s = s.where(s.abs() >= thr, 0.0)
            out[code] = s
        return out
'''


def materialize_candidate(
    base: dict[str, Any],
    genome: Genome,
    dest: Path,
) -> dict[str, Any]:
    """Copy base engine and stamp genome into hunt/config (secondary knobs)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    src: Path = base["src_dir"]
    model_dir: Path = base["model_dir"]
    for name in (
        "signal_engine.py",
        "hunt_config.json",
        "meta_config.json",
        "meta_xgb_final.json",
        "vpa.py",
        "vwap_peg.py",
        "vwap_dna.json",
        "ROUTING.json",
        "RISK_POLICY.json",
    ):
        p = src / name
        if not p.exists() and model_dir != src:
            p = model_dir / name
        if p.exists():
            shutil.copy2(p, dest / name)

    is_opts = genome.track.startswith("options") or base.get("has_hunt") or "opts" in base["id"]
    cid = f"train_g{genome.generation}_{base['id']}"

    # Equity: wrap base engine so genome min_confidence / vol_z / size mult apply
    eng = dest / "signal_engine.py"
    if eng.exists() and not is_opts:
        shutil.move(str(eng), str(dest / "_base_engine.py"))
        (dest / "signal_engine.py").write_text(_GENOME_WRAPPER)

    cfg: dict[str, Any] = {}
    cfg_path = model_dir / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            cfg = {}
    cfg.setdefault("strategy", {})
    if isinstance(cfg["strategy"], dict):
        cfg["strategy"].update(genome_to_strategy(genome))
        cfg["strategy"]["model_version"] = cid
        cfg["strategy"]["parent"] = base["id"]
    cfg["engine"] = "options" if is_opts else cfg.get("engine", "daily")
    # preserve interval for equity multi-TF
    if not is_opts and not cfg.get("interval"):
        cfg["interval"] = base.get("interval") or "1H"
    (dest / "config.json").write_text(json.dumps(cfg, indent=2))

    if is_opts or (dest / "hunt_config.json").exists():
        hunt_path = dest / "hunt_config.json"
        hc: dict[str, Any] = {}
        if hunt_path.exists():
            try:
                hc = json.loads(hunt_path.read_text())
            except Exception:
                hc = {}
        hc.update(genome_to_hunt(genome))
        hc.setdefault("contract_multiplier", 100)
        hc.setdefault("max_contracts", 5)
        hunt_path.write_text(json.dumps(hc, indent=2))

    # RISK_POLICY overlay for engines that read it
    risk = {
        "feedback": {
            "after_loss_mult": genome.after_loss_mult,
            "after_1_2_wins_mult": genome.after_win_mult,
            "after_3_wins_mult": min(1.25, genome.after_win_mult + 0.1),
            "streak_full_wins": 3,
            "min_feedback_mult": 0.25,
            "max_feedback_mult": 1.25,
        },
        "drawdown": {
            "soft_throttle": genome.soft_dd,
            "halt_new": genome.halt_dd,
            "flatten": min(0.55, genome.halt_dd + 0.15),
        },
        "genome_generation": genome.generation,
    }
    (dest / "RISK_POLICY.json").write_text(json.dumps(risk, indent=2))
    (dest / "GENOME.json").write_text(json.dumps(genome.to_dict(), indent=2))
    (dest / "HYPOTHESIS.md").write_text(
        f"# {cid}\n\nTrain-loop candidate gen {genome.generation} from `{base['id']}`.\n"
        f"Secondary knobs only — primary SIDE unchanged.\n"
    )

    return {
        "id": cid,
        "src_dir": dest,
        "model_dir": dest,
        "modes": ["options"] if is_opts else ["daily"],
        "interval": cfg.get("interval") or base.get("interval") or "1D",
        "has_hunt": (dest / "hunt_config.json").exists(),
        "hunt_path": dest / "hunt_config.json" if (dest / "hunt_config.json").exists() else None,
        "is_mutation": True,
        "parent": base["id"],
        "genome_gen": genome.generation,
    }


def evaluate_model(
    model: dict[str, Any],
    *,
    track: str,
    cash: float,
    train_window: tuple[str, str],
    bag: list[str],
    reuse: bool,
    validation_window: tuple[str, str] | None = None,
    oos_window: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate selection fitness on train + validation.

    ``oos_window`` is retained as a deprecated compatibility alias.  Because
    this window is repeatedly used to accept/reject mutations, it must not be
    represented as an untouched OOS/lockbox result.
    """
    selected_window = validation_window or oos_window
    if selected_window is None:
        raise ValueError("validation_window is required")
    mode = "options" if track.startswith("options") else "daily"
    force_1d = mode == "options"
    train = run_one_cached(
        model,
        mode=mode,
        codes=bag,
        start=train_window[0],
        end=train_window[1],
        tag="train",
        cash=cash,
        reuse=reuse,
        force_1d=force_1d if force_1d else None,
    )
    validation = run_one_cached(
        model,
        mode=mode,
        codes=bag,
        start=selected_window[0],
        end=selected_window[1],
        tag="validation",
        cash=cash,
        reuse=reuse,
        force_1d=force_1d if force_1d else None,
    )
    # Anti-overfit selection heuristic. This remains validation, not a final
    # generalization claim; promotion requires separate lockbox evidence.
    u_tr = float(train.get("utility") or utility_score(train))
    u_validation = float(validation.get("utility") or utility_score(validation))
    gap = max(0.0, u_tr - u_validation)
    objective = u_validation - 0.08 * min(gap, 5.0)
    if validation.get("error") or int(validation.get("n") or 0) == 0:
        objective = -99.0
    elif float(validation.get("ret") or 0) <= 0 and int(validation.get("n") or 0) >= 5:
        objective = min(objective, -1.0)
    return {
        "train": train,
        "validation": validation,
        "oos": validation,  # deprecated artifact compatibility alias
        "evaluation_role": "selection_validation",
        "u_train": u_tr,
        "u_validation": u_validation,
        "u_oos": u_validation,  # legacy Brain schema alias
        "gap": gap,
        "objective": objective,
        "id": model["id"],
    }


def run_train(
    *,
    epochs: int = 10,
    base_model: str | None = None,
    track: str = "equity_ohlcv",
    cash: float = 10_000,
    seed: int = 42,
    reuse: bool = True,
    retrain_meta_every: int = 5,
    brain_path: Path | None = None,
    out_dir: Path | None = None,
    continuous: bool = False,
    max_epochs_continuous: int = 1000,
) -> dict[str, Any]:
    """Run N training epochs (or continuous until max)."""
    brain_path = brain_path or DEFAULT_BRAIN
    out = out_dir or (ROOT / "runs" / f"evolve_train_{_now_tag()}")
    _setup_out(out)
    dmr.CASH = cash

    brain = load_brain(brain_path)
    if base_model:
        brain.genome.base_model = base_model
        brain.best_genome.base_model = base_model
    brain.genome.track = track
    brain.best_genome.track = track

    bag, _core = bags_for_track("options" if track.startswith("options") else "equity")
    # Repeatedly selected-on validation window; never a final lockbox.
    train_w = WINDOWS["early_train"]
    validation_w = WINDOWS["oos"]  # historical window registry key

    found = discover([brain.genome.base_model])
    if not found:
        found = discover(None)
        if track.startswith("options"):
            found = [m for m in found if m.get("has_hunt") or "opts" in m["id"]]
        if not found:
            raise RuntimeError("No base model engines found")
        brain.genome.base_model = found[0]["id"]
    base = found[0]

    rng = random.Random(seed + brain.epoch)
    total = max_epochs_continuous if continuous else epochs
    print(
        f"[train] base={brain.genome.base_model} track={track} epochs={total} "
        f"best_validation_u={brain.best_utility_oos:.3f} brain={brain_path}",
        flush=True,
    )

    # baseline eval if brain empty
    if brain.best_utility_oos <= -900:
        print("[train] evaluating seed champion…", flush=True)
        base_eval = evaluate_model(
            base, track=track, cash=cash, train_window=train_w,
            validation_window=validation_w, bag=bag, reuse=reuse
        )
        brain.best_utility_oos = base_eval["objective"]
        brain.best_utility_train = base_eval["u_train"]
        brain.best_genome = brain.genome.clip()
        brain.history.append(
            {
                "epoch": 0,
                "event": "seed",
                "id": base["id"],
                "objective": base_eval["objective"],
                "u_validation": base_eval["u_validation"],
                "u_oos": base_eval["u_validation"],  # legacy schema
                "u_train": base_eval["u_train"],
            }
        )
        save_brain(brain, brain_path)
        print(f"[train] seed objective={base_eval['objective']:.3f}", flush=True)

    epoch_rows: list[dict[str, Any]] = []

    for step in range(1, total + 1):
        brain.epoch += 1
        cand_g = mutate_genome(brain.genome, rng)
        cand_dir = out / "candidates" / f"ep{brain.epoch:04d}"
        cand = materialize_candidate(base, cand_g, cand_dir)

        print(
            f"[train] epoch {brain.epoch} mut risk={cand_g.risk_pct:.3f} "
            f"halt_dd={cand_g.halt_dd:.3f} vol_z={cand_g.vol_z_min:.2f} dte={cand_g.dte_days:.0f}",
            flush=True,
        )
        # Don't reuse content cache for brand-new candidate paths — still ok if hash unique
        ev = evaluate_model(
            cand,
            track=track,
            cash=cash,
            train_window=train_w,
            validation_window=validation_w,
            bag=bag,
            reuse=False,
        )
        obj = ev["objective"]
        # Independent auditor — block overfit / cheating accepts
        audit = audit_train_epoch(
            candidate_id=cand["id"],
            candidate_dir=cand_dir,
            eval_result=ev,
            data_track=track,
        )
        write_audit(audit, out / "audits")
        better = obj > brain.best_utility_oos + 1e-4
        auditor_blocks = audit.verdict in ("FAIL", "BLOCK")
        accepted = better and not auditor_blocks
        if better and auditor_blocks:
            lesson = (
                f"auditor {audit.verdict} blocked accept (score={audit.score:.0f}): "
                + "; ".join(f.code for f in audit.findings if f.severity in ("fail", "block"))[:120]
            )
            brain.lessons.append(lesson)
        else:
            lesson = learn_lesson(brain, ev["validation"], accepted)

        if accepted:
            brain.accepted += 1
            brain.genome = cand_g
            brain.best_genome = cand_g
            brain.best_utility_oos = obj
            brain.best_utility_train = ev["u_train"]
            # slight lr decay when winning (exploit)
            brain.genome.lr = max(0.05, brain.genome.lr * 0.97)
            print(
                f"[train]  ✓ ACCEPT obj={obj:.3f} audit={audit.verdict}/{audit.score:.0f} — {lesson}",
                flush=True,
            )
            # promote snapshot to brain folder
            prom = brain_path.parent / "champion_engine"
            if prom.exists():
                shutil.rmtree(prom)
            shutil.copytree(cand_dir, prom)
        else:
            brain.rejected += 1
            # increase exploration slightly after rejects
            brain.genome.lr = min(0.4, brain.genome.lr * 1.03)
            why = "auditor" if (better and auditor_blocks) else "objective"
            print(
                f"[train]  ✗ reject obj={obj:.3f} best={brain.best_utility_oos:.3f} "
                f"audit={audit.verdict}/{audit.score:.0f} ({why}) — {lesson}",
                flush=True,
            )

        rec = {
            "epoch": brain.epoch,
            "accepted": accepted,
            "objective": obj,
            "u_validation": ev["u_validation"],
            "u_oos": ev["u_validation"],  # legacy schema
            "u_train": ev["u_train"],
            "gap": ev["gap"],
            "validation_n": ev["validation"].get("n"),
            "validation_ret": ev["validation"].get("ret"),
            "validation_dd": ev["validation"].get("dd"),
            "oos_n": ev["validation"].get("n"),  # legacy schema
            "oos_ret": ev["validation"].get("ret"),
            "oos_dd": ev["validation"].get("dd"),
            "genome": cand_g.to_dict(),
            "lesson": lesson,
            "candidate_id": cand["id"],
            "audit_verdict": audit.verdict,
            "audit_score": audit.score,
            "audit_codes": [f.code for f in audit.findings if f.severity != "info"],
        }
        brain.history.append(rec)
        epoch_rows.append(rec)
        save_brain(brain, brain_path)

        # periodic meta retrain (secondary feature learning)
        if retrain_meta_every > 0 and brain.epoch % retrain_meta_every == 0:
            try:
                from evolve.meta_train import train_meta_recipe

                print("[train] retrain meta MLP (secondary)…", flush=True)
                recipe = train_meta_recipe(
                    bag[:5],
                    start=train_w[0],
                    end=validation_w[1],
                    out_dir=out / "meta",
                )
                if recipe.get("ok"):
                    brain.meta_recipe = {
                        "selected_features": recipe.get("selected_features"),
                        "mlp": recipe.get("mlp"),
                        "size_rule": recipe.get("size_rule"),
                        "epoch": brain.epoch,
                    }
                    # pull thresholds into genome if present
                    thr = (recipe.get("size_rule") or {}).get("thresholds") or {}
                    if "full" in thr:
                        brain.genome.meta_p_full = float(thr["full"])
                    if "half" in thr:
                        brain.genome.meta_p_half = float(thr["half"])
                    save_brain(brain, brain_path)
                    print("[train] meta recipe updated", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[train] meta retrain skipped: {e}", flush=True)

        # early stop if many rejects in a row (local optimum) — lower lr already explores
        if not continuous and step >= epochs:
            break

    # final board
    ranking = []
    for rec in epoch_rows[-20:]:
        ranking.append(
            enrich_scores(
                apply_gates(
                    {
                        "id": rec["candidate_id"],
                        "mode": "options" if track.startswith("options") else "daily",
                        "ret": rec.get("validation_ret") or 0,
                        "dd": rec.get("validation_dd") or 0,
                        "sharpe": 0,
                        "n": rec.get("validation_n") or 0,
                        "wr": 0,
                        "utility": rec.get("u_validation"),
                    }
                ),
                dd_hard=dd_hard_from_bar(),
                claim_min=claim_min_trades(),
            )
        )
    ranking.sort(key=lambda r: float(r.get("utility") or -99), reverse=True)

    state = {
        "phase": "train",
        "track": track,
        "cash": cash,
        "family": "poc_va_macdha",
        "ranking": ranking,
        "brain_path": str(brain_path.relative_to(ROOT)),
        "best_genome": brain.best_genome.to_dict(),
        "best_utility_oos": brain.best_utility_oos,
        "best_utility_validation": brain.best_utility_oos,
        "epoch": brain.epoch,
        "accepted": brain.accepted,
        "rejected": brain.rejected,
        "lessons": brain.lessons[-15:],
        "history_tail": brain.history[-20:],
        "promote": [],
        "run_dir": str(out.relative_to(ROOT)),
        "honesty": {
            "primary_side": "unchanged_rules",
            "trained": "secondary_genome_risk_meta",
            "selection_window": "validation_reused_for_mutation_selection",
            "accept_rule": "validation utility minus soft train/validation gap penalty",
            "promotion_eligible": False,
            "promotion_blocker": "separate untouched lockbox and multi-lock evidence required",
        },
    }
    write_state(out / "STATE.json", state)
    write_leaderboard(out / "LEADERBOARD.md", state)
    (out / "TRAIN_LOG.md").write_text(_train_log_md(brain, epoch_rows))
    save_brain(brain, brain_path)
    print(
        f"[train] done epoch={brain.epoch} best_validation_obj={brain.best_utility_oos:.3f} "
        f"accepted={brain.accepted} rejected={brain.rejected} → {out}",
        flush=True,
    )
    return state


def _train_log_md(brain: Brain, rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Train log (self-feedback)",
        "",
        f"Updated: `{datetime.now(timezone.utc).isoformat()}`",
        f"Best validation objective: **{brain.best_utility_oos:.4f}**",
        f"Epochs: {brain.epoch} · accepted {brain.accepted} · rejected {brain.rejected}",
        "",
        "## Lessons (latest)",
        "",
    ]
    for L in brain.lessons[-20:]:
        lines.append(f"- {L}")
    lines += ["", "## Epochs", "", "| Ep | Acc | Obj | U_validation | U_train | n | Lesson |", "|----|-----|-----|--------------|---------|---|--------|"]
    for r in rows:
        lines.append(
            f"| {r['epoch']} | {'Y' if r['accepted'] else 'n'} | {r['objective']:.3f} | "
            f"{r['u_validation']:.3f} | {r['u_train']:.3f} | {r.get('validation_n')} | {r.get('lesson','')[:48]} |"
        )
    lines += [
        "",
        "## Best genome",
        "",
        "```json",
        json.dumps(brain.best_genome.to_dict(), indent=2),
        "```",
        "",
    ]
    return "\n".join(lines)
