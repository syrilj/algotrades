#!/usr/bin/env python3
"""Resumable, bounded autonomous research loop for equity strategies.

This controller deliberately does not use final-lockbox performance as a
reward.  It evolves candidates on the rolling validation folds, freezes the
best research bundle after each cycle, remembers mutation outcomes, and can
optionally perform one terminal qualification after all learning has stopped.

It is "self-healing" operationally: state is checkpointed atomically, stale
locks are recovered, failed cycles are retried within a budget, and a stopped
run can be resumed.  It cannot guarantee a market edge or turn historical
profit into a valid live claim.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.evolve import folds  # noqa: E402
from tools.evolve.loop_core import (  # noqa: E402
    _build_model,
    run_campaign,
    run_candidate,
    run_lockbox_and_audit,
)
from tools.evolve.v72_search import run_v72_campaign  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f".{path.name}.pending")
    pending.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    pending.replace(path)


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else dict(default or {})
    except (OSError, json.JSONDecodeError):
        return dict(default or {})


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class RunLock:
    """Single-writer lock with stale-process recovery."""

    def __init__(self, path: Path):
        self.path = path
        self.owned = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                old_pid = int(self.path.read_text().strip())
            except (OSError, ValueError):
                old_pid = -1
            if _pid_alive(old_pid):
                raise RuntimeError(f"feedback loop already running with pid {old_pid}")
            self.path.unlink(missing_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RuntimeError("feedback loop lock was acquired concurrently") from exc
        with os.fdopen(fd, "w") as handle:
            handle.write(str(os.getpid()))
        self.owned = True

    def release(self) -> None:
        if self.owned:
            self.path.unlink(missing_ok=True)
            self.owned = False

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


@dataclass(frozen=True)
class LoopConfig:
    base_model: str = "v39b_live_adapt"
    search_mode: str = "direction"
    cash: float = 1_000.0
    generations_per_cycle: int = 1
    max_variants_per_generation: int = 8
    max_cycles: int = 10
    max_runtime_hours: float = 8.0
    max_consecutive_failures: int = 3
    min_free_gb: float = 5.0
    max_load_per_cpu: float = 0.0
    retry_cooldown_seconds: float = 5.0
    validate_data_every: int = 1
    qualify_final: bool = False

    def validate(self) -> None:
        if self.search_mode not in {"direction", "v72_sleeve"}:
            raise ValueError("search_mode must be direction or v72_sleeve")
        if self.cash <= 0:
            raise ValueError("cash must be positive")
        if (
            self.generations_per_cycle < 1
            or self.max_variants_per_generation < 1
            or self.max_cycles < 1
        ):
            raise ValueError("generation and cycle budgets must be >= 1")
        if self.max_runtime_hours <= 0:
            raise ValueError("max_runtime_hours must be positive")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be >= 1")
        if self.min_free_gb < 0 or self.max_load_per_cpu < 0:
            raise ValueError("resource thresholds cannot be negative")
        if self.retry_cooldown_seconds < 0 or self.retry_cooldown_seconds > 60:
            raise ValueError("retry cooldown must be between 0 and 60 seconds")
        if self.validate_data_every < 1:
            raise ValueError("validate_data_every must be >= 1")


CampaignRunner = Callable[..., list[dict[str, Any]]]
QualityRunner = Callable[[Path], dict[str, Any]]


class SelfHealingLoop:
    def __init__(
        self,
        config: LoopConfig,
        run_dir: Path,
        *,
        campaign_runner: CampaignRunner | None = None,
        quality_runner: QualityRunner | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        config.validate()
        self.config = config
        self.run_dir = run_dir.resolve()
        self.state_path = self.run_dir / "STATE.json"
        self.stop_path = self.run_dir / "STOP"
        self.lock_path = self.run_dir / "RUN.lock"
        self.memory_path = self.run_dir / "MODEL_MEMORY.json"
        self.campaign_runner = campaign_runner or (
            run_v72_campaign if config.search_mode == "v72_sleeve" else run_campaign
        )
        self.quality_runner = quality_runner or self._run_data_quality
        self.sleep_fn = sleep_fn
        self._stop_requested = False
        self._last_best_candidate: dict[str, Any] | None = None

    def _initial_state(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": "initialized",
            "started_at": _now(),
            "updated_at": _now(),
            "pid": None,
            "config": asdict(self.config),
            "cycles_completed": 0,
            "consecutive_failures": 0,
            "best_validation_score": None,
            "best_candidate": None,
            "edge_candidate": None,
            "current_parent_dir": str(
                ROOT / "models" / "poc_va_macdha" / self.config.base_model
            ),
            "history": [],
            "data_quality": None,
            "qualification": None,
            "stop_reason": None,
            "honesty": {
                "learning_signal": "rolling_selection_validation_only",
                "method": "failure-guided evolutionary_search_not_online_RL",
                "lockbox_used_for_learning": False,
                "auto_deploy": False,
                "edge_guaranteed": False,
                "edge_definition": (
                    "beats_frozen_champion_by_gate_on_rolling_validation_with_"
                    "adequate_confidence_and_no_failure_tags"
                ),
            },
        }

    def load_state(self) -> dict[str, Any]:
        state = _read_json(self.state_path)
        if not state:
            state = self._initial_state()
        return state

    def _save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _now()
        _atomic_json(self.state_path, state)

    def request_stop(self, *_args: object) -> None:
        self._stop_requested = True

    def _resource_problem(self, started_monotonic: float) -> str | None:
        elapsed_hours = (time.monotonic() - started_monotonic) / 3600.0
        if elapsed_hours >= self.config.max_runtime_hours:
            return "max_runtime_reached"
        free_gb = shutil.disk_usage(self.run_dir).free / (1024**3)
        if free_gb < self.config.min_free_gb:
            return f"free_disk_below_limit:{free_gb:.2f}GB"
        if self.config.max_load_per_cpu > 0 and hasattr(os, "getloadavg"):
            load = os.getloadavg()[0] / max(1, os.cpu_count() or 1)
            if load > self.config.max_load_per_cpu:
                return f"load_per_cpu_above_limit:{load:.3f}"
        return None

    def _run_data_quality(self, output_path: Path) -> dict[str, Any]:
        python = ROOT / ".venv" / "bin" / "python"
        if not python.exists():
            python = Path(sys.executable)
        cmd = [
            str(python),
            str(ROOT / "tools" / "data_quality.py"),
            "--output",
            str(output_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown failure").strip()
            raise RuntimeError(f"data quality failed: {detail[-1000:]}")
        payload = _read_json(output_path)
        return {"ok": True, "path": str(output_path), "report": payload}

    @staticmethod
    def _candidate_score(candidate: dict[str, Any]) -> float:
        value = candidate.get("rank_score")
        if value is None:
            value = candidate.get("fitness")
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")

    @staticmethod
    def _summary(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": candidate.get("id"),
            "parent": candidate.get("parent"),
            "model_dir": candidate.get("model_dir"),
            "score": SelfHealingLoop._candidate_score(candidate),
            "fitness": candidate.get("fitness"),
            "rank": candidate.get("rank"),
            "rank_confidence": candidate.get("rank_confidence"),
            "failure_profile": candidate.get("failure_profile"),
            "codes": candidate.get("codes"),
            "extra_cfg": candidate.get("extra_cfg", {}),
            "evaluation_role": candidate.get("evaluation_role"),
            "hunt": candidate.get("hunt"),
            "hunt_signature": candidate.get("hunt_signature"),
            "behavior_hash": candidate.get("behavior_hash"),
            "no_op": candidate.get("no_op"),
            "champion_score": candidate.get("champion_score"),
            "score_delta_vs_champion": candidate.get("score_delta_vs_champion"),
            "beat_champion": candidate.get("beat_champion"),
            "changes": candidate.get("changes", []),
        }

    def _freeze_candidate(self, candidate: dict[str, Any], cycle: int) -> Path:
        """Materialize the selected research parent without touching models/."""
        source = Path(str(candidate["model_dir"])).resolve()
        if not source.is_dir() or not (source / "signal_engine.py").is_file():
            raise RuntimeError(f"candidate bundle is incomplete: {source}")
        dest = self.run_dir / "parents" / f"cycle_{cycle:04d}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)

        config_path = dest / "config.json"
        config = _read_json(config_path)
        config["codes"] = list(candidate.get("codes") or config.get("codes") or [])
        config["interval"] = candidate.get("interval") or config.get("interval") or "1H"
        strategy = config.get("strategy")
        if not isinstance(strategy, dict):
            strategy = {}
        strategy.update(
            {
                "research_parent": candidate.get("id"),
                "research_cycle": cycle,
                "promotion_eligible": False,
            }
        )
        config["strategy"] = strategy
        for key, value in (candidate.get("extra_cfg") or {}).items():
            config[key] = value
        _atomic_json(config_path, config)
        _atomic_json(dest / "RESEARCH_LINEAGE.json", self._summary(candidate))
        return dest

    def _qualify_once(
        self, state: dict[str, Any], frozen_parent: Path
    ) -> dict[str, Any]:
        ledger_path = self.run_dir / "LOCKBOX_LEDGER.json"
        ledger = _read_json(ledger_path, {"uses": []})
        uses = ledger.get("uses") if isinstance(ledger.get("uses"), list) else []
        window_id = str(folds.LOCKBOX["window_id"])
        if any(row.get("window_id") == window_id for row in uses if isinstance(row, dict)):
            return {
                "status": "SKIPPED_ALREADY_USED",
                "window_id": window_id,
                "note": "This controller never reuses a terminal lockbox.",
            }

        model = _build_model(frozen_parent)
        candidate = run_candidate(
            model,
            cash=self.config.cash,
            campaign_id=f"self_healing_terminal_{int(time.time())}",
            gen=int(state["cycles_completed"]),
            variant_id=frozen_parent.name,
            parent=str((state.get("best_candidate") or {}).get("id") or ""),
            fold_set=folds.VALIDATION_FOLDS_1H,
        )
        candidate, audit_path = run_lockbox_and_audit(candidate, model)
        paired_control: dict[str, Any] | None = None
        if self.config.search_mode == "v72_sleeve":
            control_dir = ROOT / "models" / "poc_va_macdha" / self.config.base_model
            control = run_candidate(
                _build_model(control_dir),
                cash=self.config.cash,
                campaign_id=f"self_healing_paired_control_{int(time.time())}",
                gen=int(state["cycles_completed"]),
                variant_id=f"{self.config.base_model}_frozen_control",
                parent=self.config.base_model,
                fold_set=[folds.LOCKBOX],
            )
            challenger_metrics = dict((candidate.get("lockbox") or {}).get("fold_metrics") or {})
            control_metrics = dict((control.get("fold_metrics") or {}).get("LOCKBOX") or {})
            return_delta = float(challenger_metrics.get("ret") or 0.0) - float(
                control_metrics.get("ret") or 0.0
            )
            sharpe_delta = float(challenger_metrics.get("sharpe") or 0.0) - float(
                control_metrics.get("sharpe") or 0.0
            )
            challenger_dd = abs(float(challenger_metrics.get("dd") or 0.0))
            control_dd = abs(float(control_metrics.get("dd") or 0.0))
            paired_pass = bool(
                return_delta >= 0.02
                and sharpe_delta > 0.0
                and challenger_dd <= control_dd
            )
            paired_control = {
                "status": "PASS" if paired_pass else "FAIL",
                "ok": paired_pass,
                "policy": {
                    "return_delta_min": 0.02,
                    "sharpe_delta_min_exclusive": 0.0,
                    "drawdown_must_not_worsen": True,
                },
                "challenger": challenger_metrics,
                "control": control_metrics,
                "return_delta": return_delta,
                "sharpe_delta": sharpe_delta,
                "fed_back_into_learning": False,
            }
            evidence = candidate.get("promotion_evidence")
            if not isinstance(evidence, dict):
                evidence = {}
            evidence["paired_frozen_champion"] = paired_control
            candidate["promotion_evidence"] = evidence
            candidate["may_auto_promote"] = bool(
                candidate.get("may_auto_promote", False) and paired_pass
            )
        record = {
            "used_at": _now(),
            "window_id": window_id,
            "candidate_id": candidate["id"],
            "candidate_dir": str(frozen_parent),
            "lockbox": candidate.get("lockbox"),
            "promotion_gate": candidate.get("promotion_gate"),
            "paired_control": paired_control,
            "may_auto_promote": bool(candidate.get("may_auto_promote", False)),
            "audit_path": str(audit_path),
            "fed_back_into_learning": False,
            "auto_deployed": False,
        }
        uses.append(record)
        _atomic_json(ledger_path, {"uses": uses})
        return {"status": "COMPLETED", **record}

    def run(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        started_monotonic = time.monotonic()
        previous_handlers: dict[int, Any] = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, self.request_stop)

        try:
            with RunLock(self.lock_path):
                state = self.load_state()
                state["status"] = "running"
                state["pid"] = os.getpid()
                state["config"] = asdict(self.config)
                state["stop_reason"] = None
                self._save(state)

                parent_dir = Path(str(state["current_parent_dir"])).resolve()
                if not (parent_dir / "signal_engine.py").is_file():
                    state["status"] = "failed"
                    state["pid"] = None
                    state["stop_reason"] = f"base_model_incomplete:{parent_dir}"
                    self._save(state)
                    return state

                while int(state["cycles_completed"]) < self.config.max_cycles:
                    if self._stop_requested or self.stop_path.exists():
                        state["status"] = "stopped"
                        state["stop_reason"] = "stop_requested"
                        break
                    problem = self._resource_problem(started_monotonic)
                    if problem:
                        state["status"] = (
                            "complete" if problem == "max_runtime_reached" else "paused_resource"
                        )
                        state["stop_reason"] = problem
                        break

                    cycle = int(state["cycles_completed"]) + 1
                    cycle_record: dict[str, Any] = {
                        "cycle": cycle,
                        "started_at": _now(),
                        "parent_dir": str(parent_dir),
                        "status": "running",
                    }
                    state["history"].append(cycle_record)
                    self._save(state)

                    try:
                        if (cycle - 1) % self.config.validate_data_every == 0:
                            quality_path = self.run_dir / "quality" / f"cycle_{cycle:04d}.json"
                            quality = self.quality_runner(quality_path)
                            if quality.get("ok") is not True:
                                raise RuntimeError("data-quality runner did not return ok=true")
                            state["data_quality"] = quality

                        results = self.campaign_runner(
                            parent_dir,
                            generations=self.config.generations_per_cycle,
                            cash=self.config.cash,
                            campaign_id=f"self_healing_c{cycle:04d}",
                            memory_path=self.memory_path,
                            qualify_generation_best=False,
                            max_variants_per_generation=self.config.max_variants_per_generation,
                        )
                        usable = [
                            row for row in results
                            if self._candidate_score(row) != float("-inf")
                        ]
                        if not usable:
                            raise RuntimeError("campaign produced no usable candidates")
                        edge_candidates = [row for row in usable if row.get("beat_champion") is True]
                        best = max(edge_candidates or usable, key=self._candidate_score)
                        frozen = self._freeze_candidate(best, cycle)
                        summary = self._summary(best)
                        summary["frozen_model_dir"] = str(frozen)
                        score = float(summary["score"])
                        previous_best = state.get("best_validation_score")
                        improved = previous_best is None or score > float(previous_best)
                        edge_found = bool(summary.get("beat_champion"))
                        if improved or edge_found:
                            state["best_validation_score"] = score
                            state["best_candidate"] = summary
                        if edge_found:
                            state["edge_candidate"] = summary
                        state["current_parent_dir"] = str(frozen)
                        parent_dir = frozen
                        self._last_best_candidate = best
                        state["cycles_completed"] = cycle
                        state["consecutive_failures"] = 0
                        cycle_record.update(
                            {
                                "status": "completed",
                                "finished_at": _now(),
                                "n_candidates": len(results),
                                "best": summary,
                                "global_best_improved": improved,
                                "edge_found": edge_found,
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 - recovery boundary
                        failures = int(state.get("consecutive_failures") or 0) + 1
                        state["consecutive_failures"] = failures
                        cycle_record.update(
                            {
                                "status": "failed",
                                "finished_at": _now(),
                                "error": f"{type(exc).__name__}: {exc}"[:2000],
                            }
                        )
                        self._save(state)
                        if failures >= self.config.max_consecutive_failures:
                            state["status"] = "failed"
                            state["stop_reason"] = "consecutive_failure_budget_exhausted"
                            break
                        if self.config.retry_cooldown_seconds:
                            self.sleep_fn(self.config.retry_cooldown_seconds)
                        continue

                    self._save(state)
                    if state.get("edge_candidate"):
                        state["status"] = "complete"
                        state["stop_reason"] = "edge_candidate_found"
                        break

                if state["status"] == "running":
                    state["status"] = "complete"
                    state["stop_reason"] = (
                        "edge_candidate_found"
                        if state.get("edge_candidate")
                        else "max_cycles_reached"
                    )

                if (
                    self.config.qualify_final
                    and state["status"] == "complete"
                    and state.get("best_candidate")
                ):
                    state["status"] = "qualifying"
                    self._save(state)
                    frozen = Path(state["best_candidate"]["frozen_model_dir"])
                    try:
                        state["qualification"] = self._qualify_once(state, frozen)
                        state["status"] = "complete"
                    except Exception as exc:  # noqa: BLE001 - fail closed at final gate
                        state["qualification"] = {
                            "status": "FAILED",
                            "error": f"{type(exc).__name__}: {exc}"[:2000],
                            "fed_back_into_learning": False,
                            "auto_deployed": False,
                        }
                        state["status"] = "failed"
                        state["stop_reason"] = "terminal_qualification_failed"

                state["pid"] = None
                self._save(state)
                return state
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)


def _config_from_args(args: argparse.Namespace) -> LoopConfig:
    return LoopConfig(
        base_model=args.base,
        search_mode=args.search_mode,
        cash=args.cash,
        generations_per_cycle=args.generations_per_cycle,
        max_variants_per_generation=args.max_variants_per_generation,
        max_cycles=args.max_cycles,
        max_runtime_hours=args.max_runtime_hours,
        max_consecutive_failures=args.max_consecutive_failures,
        min_free_gb=args.min_free_gb,
        max_load_per_cpu=args.max_load_per_cpu,
        retry_cooldown_seconds=args.retry_cooldown_seconds,
        validate_data_every=args.validate_data_every,
        qualify_final=args.qualify_final,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bounded, resumable self-healing model research loop"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="start or resume the research loop")
    run.add_argument("--run-dir", default="runs/self_healing_feedback")
    run.add_argument("--base", default="v39b_live_adapt")
    run.add_argument(
        "--search-mode",
        choices=("direction", "v72_sleeve"),
        default="direction",
    )
    run.add_argument("--cash", type=float, default=1_000.0)
    run.add_argument("--generations-per-cycle", type=int, default=1)
    run.add_argument("--max-variants-per-generation", type=int, default=8)
    run.add_argument("--max-cycles", type=int, default=10)
    run.add_argument("--max-runtime-hours", type=float, default=8.0)
    run.add_argument("--max-consecutive-failures", type=int, default=3)
    run.add_argument("--min-free-gb", type=float, default=5.0)
    run.add_argument("--max-load-per-cpu", type=float, default=0.0)
    run.add_argument("--retry-cooldown-seconds", type=float, default=5.0)
    run.add_argument("--validate-data-every", type=int, default=1)
    run.add_argument(
        "--qualify-final",
        action="store_true",
        help="after learning stops, consume this run's terminal lockbox once",
    )

    status = sub.add_parser("status", help="show checkpoint state")
    status.add_argument("--run-dir", default="runs/self_healing_feedback")
    stop = sub.add_parser("stop", help="request a graceful stop after the active candidate")
    stop.add_argument("--run-dir", default="runs/self_healing_feedback")
    clear = sub.add_parser("clear-stop", help="remove a prior graceful-stop request")
    clear.add_argument("--run-dir", default="runs/self_healing_feedback")
    return parser


def _resolve_run_dir(value: str) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    allowed = (ROOT / "runs").resolve()
    if resolved == allowed or not resolved.is_relative_to(allowed):
        raise ValueError(f"run directory must be a child of {allowed}")
    return resolved


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = _resolve_run_dir(args.run_dir)
    if args.command == "status":
        print(json.dumps(_read_json(run_dir / "STATE.json"), indent=2))
        return 0
    if args.command == "stop":
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "STOP").write_text(_now() + "\n")
        print(f"stop requested: {run_dir / 'STOP'}")
        return 0
    if args.command == "clear-stop":
        (run_dir / "STOP").unlink(missing_ok=True)
        print(f"stop request cleared: {run_dir / 'STOP'}")
        return 0

    loop = SelfHealingLoop(_config_from_args(args), run_dir)
    state = loop.run()
    print(json.dumps({
        "status": state.get("status"),
        "cycles_completed": state.get("cycles_completed"),
        "best_validation_score": state.get("best_validation_score"),
        "best_candidate": state.get("best_candidate"),
        "stop_reason": state.get("stop_reason"),
        "state_path": str(loop.state_path),
    }, indent=2))
    return 0 if state.get("status") in {"complete", "stopped", "paused_resource"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
