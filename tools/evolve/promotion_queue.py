"""Promotion queue backend + winner decay check.

SAFETY CONTRACT (the most important thing in this module)
---------------------------------------------------------
The evolve / scheduler loops may ONLY call ``nominate()`` and ``winner_health()``.

  * ``nominate()``      -- appends a *pending* candidate to the queue file.
                           It NEVER writes ``WINNER.json`` and NEVER calls
                           ``approve()``.
  * ``winner_health()`` -- read-only decay check. Writes nothing at all.
  * ``approve()``       -- the ONLY function that overwrites ``WINNER.json``.
                           It is invoked EXCLUSIVELY by a human-triggered API
                           route (a future task). No automated code path in this
                           repo -- not ``nominate``, not ``winner_health``, not
                           the ``finalize.compare_to_winners`` wiring -- may ever
                           call ``approve()``.

Silently swapping the live trading model on backtest metrics alone would be a
serious safety failure, so promotion is a two-step human gate: the pipeline
NOMINATES; a human APPROVES.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import paper_ledger  # noqa: E402  (tools/paper_ledger.py -- compute_stats)
from evolve.finalize import load_winner  # noqa: E402

QUEUE_PATH = ROOT / "models" / "_shared" / "promotion_queue.json"
PASS_BAR_PATH = ROOT / "models" / "_shared" / "PASS_BAR.json"

# PASS_BAR.json has no win-rate floor (win_rate is explicitly listed under
# ``vanity_not_sufficient``). Per the task brief we fall back to a documented
# 0.40 live win-rate floor for the decay check.
DEFAULT_WINRATE_FLOOR = 0.40

DEFAULT_FAMILY = "poc_va_macdha"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Queue file helpers
# --------------------------------------------------------------------------- #
def _load_queue() -> list[dict[str, Any]]:
    if not QUEUE_PATH.exists():
        return []
    try:
        data = json.loads(QUEUE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):  # tolerate {"entries": [...]} wrappers
        data = data.get("entries") or []
    return list(data) if isinstance(data, list) else []


def _write_queue(entries: list[dict[str, Any]]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(QUEUE_PATH)


def _winrate_floor() -> float:
    """Live win-rate floor for winner_health.

    PASS_BAR.json does not define a win-rate floor today, so this probes a few
    plausible keys and otherwise returns the documented 0.40 default.
    """
    try:
        bar = json.loads(PASS_BAR_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return DEFAULT_WINRATE_FLOOR
    gates = bar.get("gates") or {}
    for key in ("win_rate_min", "win_rate_floor", "live_win_rate_min", "wr_min"):
        for holder in (gates, bar):
            if key in holder:
                try:
                    return float(holder[key])
                except (TypeError, ValueError):
                    pass
    return DEFAULT_WINRATE_FLOOR


# --------------------------------------------------------------------------- #
# Public API -- automated callers may use nominate() and winner_health() ONLY
# --------------------------------------------------------------------------- #
def nominate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Append a *pending* promotion candidate to the queue. Dedupes by id.

    NEVER touches ``WINNER.json`` and NEVER calls ``approve()``. Safe for the
    evolve/scheduler loops to call automatically.
    """
    cid = str(candidate.get("id") or "").strip()
    if not cid:
        raise ValueError("candidate must have a non-empty 'id'")

    entries = _load_queue()
    for existing in entries:
        if existing.get("id") == cid:
            return existing  # dedupe -- already queued, do not add again

    model_dir = candidate.get("model_dir")
    entry = {
        "id": cid,
        "ts": _now(),
        "campaign": candidate.get("campaign"),
        "family": candidate.get("family") or DEFAULT_FAMILY,
        "model_dir": str(model_dir) if model_dir is not None else None,
        "metrics": dict(candidate.get("metrics") or {}),
        "gates": dict(candidate.get("gates") or {}),
        "status": "pending",
    }
    entries.append(entry)
    _write_queue(entries)
    return entry


def reject(entry_id: str, reason: str = "") -> dict[str, Any]:
    """Mark a queued candidate as rejected. Never promotes."""
    entries = _load_queue()
    for entry in entries:
        if entry.get("id") == entry_id:
            entry["status"] = "rejected"
            entry["rejected_at"] = _now()
            entry["reject_reason"] = reason
            _write_queue(entries)
            return entry
    raise KeyError(f"no queue entry with id {entry_id!r}")


def winner_health(trailing_n: int = 20) -> dict[str, Any]:
    """Read-only decay check for the current frozen WINNER.

    Uses ``paper_ledger.compute_stats(model=<winner id>)`` as the live-stats
    source and compares its win rate against the win-rate floor. Writes NOTHING.

    Note on ``trailing_n``: ``compute_stats`` has no last-N parameter -- it
    aggregates every closed trade for the model -- so ``trailing_n`` is reported
    as the requested recency window but the win rate reflects the model's full
    closed history. It is echoed in the result for callers / future refinement.
    """
    winner = load_winner().get("winner")
    stats = paper_ledger.compute_stats(model=winner)
    overall = stats.get("overall") or {}
    live_n = int(overall.get("n") or 0)
    live_wr = float(overall.get("live_wr") or 0.0)
    threshold = _winrate_floor()
    degraded = live_n > 0 and live_wr < threshold
    return {
        "winner": winner,
        "live_n": live_n,
        "live_wr": live_wr,
        "threshold": threshold,
        "trailing_n": trailing_n,
        "degraded": bool(degraded),
        "asof": stats.get("asof"),
    }


# --------------------------------------------------------------------------- #
# HUMAN-ONLY promotion path -- invoked solely by the API route (a human click).
# Nothing in this repo's automated code may call approve().
# --------------------------------------------------------------------------- #
def approve(
    entry_id: str,
    *,
    family: str | None = None,
    version_name: str | None = None,
) -> dict[str, Any]:
    """HUMAN-ONLY. Promote a queued candidate to WINNER.

    Steps:
      1) mutations.promote_mutation_to_models(...) copies the bundle into models/
      2) _update_winner(...) rewrites WINNER.json, moving the old winner into
         ``previous_winner`` lineage
      3) _record_promotion_finding(...) logs a durable finding
      4) marks the queue entry status="approved"

    MUST NOT be called by nominate(), winner_health(), or compare_to_winners().
    """
    entries = _load_queue()
    entry = next((e for e in entries if e.get("id") == entry_id), None)
    if entry is None:
        raise KeyError(f"no queue entry with id {entry_id!r}")
    if entry.get("status") == "approved":
        return entry  # idempotent

    fam = family or entry.get("family") or DEFAULT_FAMILY

    from evolve import mutations  # local import -- keep automated import surface small

    mut = {"id": entry["id"], "model_dir": entry.get("model_dir")}
    dest = mutations.promote_mutation_to_models(
        mut, family=fam, version_name=version_name
    )
    version = Path(dest).name

    _update_winner(fam, version, entry)
    _record_promotion_finding(fam, version, entry)

    entry["status"] = "approved"
    entry["approved_at"] = _now()
    entry["promoted_version"] = version
    entry["promoted_path"] = str(dest)
    _write_queue(entries)
    return entry


def _update_winner(family: str, version: str, entry: dict[str, Any]) -> Path:
    """Rewrite models/<family>/WINNER.json, preserving lineage.

    Called ONLY from approve(). Moves the outgoing winner id into
    ``previous_winner``.
    """
    winner_path = ROOT / "models" / family / "WINNER.json"
    current: dict[str, Any] = {}
    if winner_path.exists():
        try:
            current = json.loads(winner_path.read_text())
        except (json.JSONDecodeError, OSError):
            current = {}

    prior = current.get("winner")
    new_winner: dict[str, Any] = {
        "winner": version,
        "selection_rule": "manual approve via promotion_queue.approve()",
        "updated_at": _now(),
        "portfolio": dict(entry.get("metrics") or {}),
        "previous_winner": prior,
        "promoted_from": entry.get("id"),
        "pass_bar": bool((entry.get("gates") or {}).get("passed", False)),
    }
    # Keep older lineage so history is not lost.
    supersedes: list[str] = []
    if prior:
        supersedes.append(prior)
    for older in current.get("also_supersedes") or []:
        if older and older not in supersedes:
            supersedes.append(older)
    if supersedes:
        new_winner["also_supersedes"] = supersedes

    winner_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = winner_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(new_winner, indent=2))
    tmp.replace(winner_path)
    return winner_path


def _record_promotion_finding(
    family: str, version: str, entry: dict[str, Any]
) -> None:
    """Append a durable promotion finding. Never raises (best-effort)."""
    try:
        import findings as findings_mod

        findings_mod.append_finding(
            {
                "family": family,
                "version": version,
                "status": "working",
                "kind": "promotion",
                "summary": (
                    f"manual approve: {entry.get('id')} -> WINNER "
                    f"({family}/{version})"
                ),
                "source": "promotion_queue",
                "evidence": [f"models/_shared/promotion_queue.json#{entry.get('id')}"],
                "metrics": dict(entry.get("metrics") or {}),
                "failure_class": None,
                "next_action": None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - findings must not block a human approve
        print(f"warn: promotion finding append failed: {exc}", file=sys.stderr)
