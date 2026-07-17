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

import hashlib
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
_BUNDLE_REQUIRED = ("signal_engine.py", "config.json")
_EVIDENCE_BASENAMES = {
    "results.json",
    "state.json",
    "audit.json",
    "metrics.json",
    "promotion_evidence.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bundle_files(model_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in model_dir.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )


def _bundle_integrity(model_dir: Path) -> dict[str, Any]:
    """Create a deterministic, per-file checksum snapshot of a model bundle."""
    if not model_dir.is_dir():
        raise ValueError(f"model_dir does not exist or is not a directory: {model_dir}")
    missing = [name for name in _BUNDLE_REQUIRED if not (model_dir / name).is_file()]
    if missing:
        raise ValueError(f"model bundle missing required files: {', '.join(missing)}")
    records = [
        {"path": str(path.relative_to(model_dir)), "sha256": _sha256(path)}
        for path in _bundle_files(model_dir)
    ]
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return {
        "model_dir": str(model_dir.resolve()),
        "files": records,
        "bundle_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _artifact_record(value: Any, *, kind: str) -> dict[str, str]:
    raw = value.get("artifact") if isinstance(value, dict) else value
    raw = raw or (value.get("path") if isinstance(value, dict) else None)
    if not raw:
        raise ValueError(f"{kind} artifact path is empty")
    path = Path(str(raw))
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{kind} artifact does not exist: {path}")
    try:
        stored_path = str(path.relative_to(ROOT))
    except ValueError:
        stored_path = str(path)
    return {"artifact": stored_path, "sha256": _sha256(path), "kind": kind}


def _snapshot_integrity(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Snapshot nomination-time bytes; missing bundles remain unapprovable."""
    raw_dir = candidate.get("model_dir")
    if not raw_dir:
        return None
    model_dir = Path(str(raw_dir)).expanduser()
    if not model_dir.is_absolute():
        model_dir = ROOT / model_dir
    if not model_dir.is_dir():
        return None

    bundle = _bundle_integrity(model_dir.resolve())
    evidence_values = list(candidate.get("evidence") or [])
    if not evidence_values:
        evidence_values = [
            path for path in _bundle_files(model_dir)
            if path.name.lower() in _EVIDENCE_BASENAMES
        ]
    evidence = [_artifact_record(value, kind="promotion_evidence") for value in evidence_values]
    calibration_value = candidate.get("calibration_artifact")
    calibration = (
        _artifact_record(calibration_value, kind="calibration")
        if calibration_value else None
    )
    return {"bundle": bundle, "evidence": evidence, "calibration": calibration}


def _resolve_artifact(record: dict[str, Any]) -> Path:
    path = Path(str(record.get("artifact") or ""))
    return path if path.is_absolute() else ROOT / path


def _validate_integrity(
    entry: dict[str, Any], *, model_dir: Path | None = None
) -> dict[str, Any]:
    """Fail closed unless bundle, promotion evidence, and calibration are pinned."""
    integrity = entry.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("candidate has no nomination-time integrity snapshot")
    expected_bundle = integrity.get("bundle") or {}
    source = model_dir or Path(str(expected_bundle.get("model_dir") or ""))
    actual = _bundle_integrity(source.resolve())
    expected_files = expected_bundle.get("files") or []
    if actual["files"] != expected_files or actual[
        "bundle_sha256"
    ] != expected_bundle.get("bundle_sha256"):
        raise ValueError("model bundle bytes changed after nomination")

    evidence = integrity.get("evidence") or []
    if not evidence:
        raise ValueError("candidate has no hash-pinned promotion evidence")
    for record in evidence:
        path = _resolve_artifact(record)
        if not path.is_file() or _sha256(path) != record.get("sha256"):
            raise ValueError(f"promotion evidence missing or hash mismatch: {path}")

    calibration = integrity.get("calibration")
    if not isinstance(calibration, dict):
        raise ValueError("candidate has no hash-pinned calibration artifact")
    calibration_path = _resolve_artifact(calibration)
    if not calibration_path.is_file() or _sha256(calibration_path) != calibration.get(
        "sha256"
    ):
        raise ValueError(
            f"calibration artifact missing or hash mismatch: {calibration_path}"
        )
    try:
        calibration_payload = json.loads(calibration_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("calibration artifact must be valid JSON") from exc
    if (
        calibration_payload.get("probability_calibrated") is not True
        or calibration_payload.get("cross_fitted") is not True
        or calibration_payload.get("status") not in {"active", "passed", "approved"}
    ):
        raise ValueError(
            "calibration artifact is not an approved cross-fitted probability calibrator"
        )
    return integrity


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
    integrity = _snapshot_integrity(candidate)
    entry = {
        "id": cid,
        "ts": _now(),
        "campaign": candidate.get("campaign"),
        "family": candidate.get("family") or DEFAULT_FAMILY,
        "model_dir": str(model_dir) if model_dir is not None else None,
        "metrics": dict(candidate.get("metrics") or {}),
        "gates": dict(candidate.get("gates") or {}),
        "data_contract": dict(candidate.get("data_contract") or {}),
        "integrity": integrity,
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
      2) atomically rewrites DEPLOYMENT_MANIFEST.json and the WINNER.json
         compatibility mirror, preserving rollback lineage
      3) _record_promotion_finding(...) logs a durable finding
      4) marks the queue entry status="approved"

    MUST NOT be called by nominate(), winner_health(), or compare_to_winners().
    """
    entries = _load_queue()
    entry = next((e for e in entries if e.get("id") == entry_id), None)
    if entry is None:
        raise KeyError(f"no queue entry with id {entry_id!r}")
    if entry.get("status") != "pending":
        raise ValueError(
            f"candidate {entry_id!r} is {entry.get('status')!r}; only pending candidates may be approved"
        )
    if (entry.get("gates") or {}).get("passed") is not True:
        raise ValueError("candidate promotion gates did not pass")
    data_contract = entry.get("data_contract") or {}
    if (
        not isinstance(data_contract, dict)
        or not data_contract.get("source")
        or not data_contract.get("interval")
    ):
        raise ValueError("candidate is missing source/interval data-contract metadata")
    _validate_integrity(entry)

    fam = family or entry.get("family") or DEFAULT_FAMILY

    from evolve import mutations  # local import -- keep automated import surface small

    mut = {"id": entry["id"], "model_dir": entry.get("model_dir")}
    dest = mutations.promote_mutation_to_models(
        mut, family=fam, version_name=version_name
    )
    version = Path(dest).name
    _validate_integrity(entry, model_dir=Path(dest))

    _update_deployment_control_plane(fam, version, Path(dest), entry)
    _record_promotion_finding(fam, version, entry)

    entry["status"] = "approved"
    entry["approved_at"] = _now()
    entry["promoted_version"] = version
    entry["promoted_path"] = str(dest)
    _write_queue(entries)
    return entry


def _winner_payload(family: str, version: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Build legacy WINNER metadata; deployment manifest remains authoritative."""
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

    return new_winner


def _deployed_artifact_record(
    record: dict[str, Any], *, source_dir: Path, dest_dir: Path
) -> dict[str, Any]:
    """Rewrite source-bundle artifact paths to their permanent destination."""
    source_path = _resolve_artifact(record).resolve()
    try:
        relative = source_path.relative_to(source_dir.resolve())
        deployed = dest_dir.resolve() / relative
    except ValueError:
        deployed = source_path
    if not deployed.is_file() or _sha256(deployed) != record.get("sha256"):
        raise ValueError(f"deployed artifact missing or hash mismatch: {deployed}")
    try:
        artifact = str(deployed.relative_to(ROOT))
    except ValueError:
        artifact = str(deployed)
    return {**record, "artifact": artifact}


def _manifest_payload(
    family: str, version: str, dest: Path, entry: dict[str, Any]
) -> dict[str, Any]:
    manifest_path = ROOT / "models" / family / "DEPLOYMENT_MANIFEST.json"
    try:
        current = json.loads(manifest_path.read_text())
        if not isinstance(current, dict):
            current = {}
    except (OSError, json.JSONDecodeError):
        current = {}

    integrity = entry["integrity"]
    source_dir = Path(str(integrity["bundle"]["model_dir"]))
    file_hashes = {
        row["path"]: row["sha256"] for row in integrity["bundle"]["files"]
    }
    evidence = [
        _deployed_artifact_record(row, source_dir=source_dir, dest_dir=dest)
        for row in integrity["evidence"]
    ]
    calibration = _deployed_artifact_record(
        integrity["calibration"], source_dir=source_dir, dest_dir=dest
    )

    prior = str((current.get("active") or {}).get("equity_model") or "")
    existing_fallbacks = list((current.get("fallbacks") or {}).get("equity") or [])
    fallbacks: list[str] = []
    for model in (prior, current.get("rollback_model"), *existing_fallbacks):
        if model and model != version and model not in fallbacks:
            fallbacks.append(str(model))
    bundle: dict[str, Any] = {
        "path": str(dest.resolve().relative_to(ROOT)),
        "bundle_sha256": integrity["bundle"]["bundle_sha256"],
        "signal_engine_sha256": file_hashes["signal_engine.py"],
        "config_sha256": file_hashes["config.json"],
    }
    if "results.json" in file_hashes:
        bundle["results_sha256"] = file_hashes["results.json"]
    return {
        "schema_version": 1,
        "authority": "live_equity_deployment",
        "family": family,
        "updated_at": _now(),
        "updated_by": "manual approve via promotion_queue.approve()",
        "promoted_from": entry.get("id"),
        "active": {"equity_model": version, "bundle": bundle},
        "fallbacks": {"equity": fallbacks, "policy": "ordered_fail_closed"},
        "rollback_model": prior or (fallbacks[0] if fallbacks else None),
        "calibration": {
            **calibration,
            "status": "active_probability_calibrated",
            "probability_calibrated": True,
            "cross_fitted": True,
            "semantics": "cross_fitted_probability_calibrator",
        },
        "execution_readiness": {
            "model_routing": "ready",
            "probability_sized_execution": "ready",
        },
        "promotion_evidence": evidence,
        "data_contract": dict(entry["data_contract"]),
        "compatibility": {
            "winner_metadata": f"models/{family}/WINNER.json",
            "desk_routing": f"models/{family}/DESK_ROUTING.json",
        },
    }


def _atomic_write_control_plane(payloads: dict[Path, dict[str, Any]]) -> None:
    """Commit manifest + compatibility mirror together, rolling back on error."""
    previous: dict[Path, bytes | None] = {}
    staged: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path, payload in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            previous[path] = path.read_bytes() if path.exists() else None
            tmp = path.with_name(f".{path.name}.pending")
            tmp.write_text(json.dumps(payload, indent=2) + "\n")
            staged[path] = tmp
        for path, tmp in staged.items():
            tmp.replace(path)
            replaced.append(path)
    except Exception:
        for path in reversed(replaced):
            old = previous[path]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                restore = path.with_name(f".{path.name}.rollback")
                restore.write_bytes(old)
                restore.replace(path)
        raise
    finally:
        for tmp in staged.values():
            tmp.unlink(missing_ok=True)


def _update_deployment_control_plane(
    family: str, version: str, dest: Path, entry: dict[str, Any]
) -> tuple[Path, Path]:
    """Atomically update the live authority and WINNER compatibility mirror."""
    manifest_path = ROOT / "models" / family / "DEPLOYMENT_MANIFEST.json"
    winner_path = ROOT / "models" / family / "WINNER.json"
    # The authoritative manifest is replaced last, making it the commit point.
    # Readers never observe a new live deployment before its compatibility
    # metadata exists; any failure rolls both paths back.
    payloads = {
        winner_path: _winner_payload(family, version, entry),
        manifest_path: _manifest_payload(family, version, dest, entry),
    }
    _atomic_write_control_plane(payloads)
    return manifest_path, winner_path


def _update_winner(family: str, version: str, entry: dict[str, Any]) -> Path:
    """Compatibility-only helper for tests/tools; approve uses atomic pair update."""
    winner_path = ROOT / "models" / family / "WINNER.json"
    _atomic_write_control_plane({winner_path: _winner_payload(family, version, entry)})
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Promotion Queue CLI")
    parser.add_argument("--json", action="store_true", help="Always output JSON")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # list
    subparsers.add_parser("list")

    # approve
    app_p = subparsers.add_parser("approve")
    app_p.add_argument("id")
    app_p.add_argument("--family", default=None)
    app_p.add_argument("--version-name", default=None)

    # reject
    rej_p = subparsers.add_parser("reject")
    rej_p.add_argument("id")
    rej_p.add_argument("--reason", default="")

    # winner-health
    wh_p = subparsers.add_parser("winner-health")
    wh_p.add_argument("--n", type=int, default=20)

    # nominate-test (dev-only)
    subparsers.add_parser("nominate-test")

    args = parser.parse_args()

    if args.cmd == "list":
        q = _load_queue()
        wh = winner_health()
        out = {"queue": q, "winner_health": wh}
        print(json.dumps(out, indent=2))
    elif args.cmd == "approve":
        res = approve(args.id, family=args.family, version_name=args.version_name)
        print(json.dumps({"ok": True, "entry": res}))
    elif args.cmd == "reject":
        res = reject(args.id, reason=args.reason)
        print(json.dumps({"ok": True, "entry": res}))
    elif args.cmd == "winner-health":
        res = winner_health(trailing_n=args.n)
        print(json.dumps(res, indent=2))
    elif args.cmd == "nominate-test":
        test_candidate = {
            "id": f"test_candidate_{int(datetime.now(timezone.utc).timestamp())}",
            "campaign": "test_campaign",
            "family": DEFAULT_FAMILY,
            "model_dir": None,
            "metrics": {"utility": 0.85, "sharpe": 1.95, "ret": 0.45, "dd": -0.15, "n": 35},
            "gates": {"passed": True, "claim_level": "CLAIM"},
        }
        res = nominate(test_candidate)
        print(json.dumps({"ok": True, "entry": res}))
