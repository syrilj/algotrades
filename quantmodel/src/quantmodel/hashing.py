"""Deterministic hashing helpers for configs, data manifests, and runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def hash_config(config: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(dict(config)))


def hash_mapping(obj: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(dict(obj)))


def git_info(repo_root: Path | None = None) -> tuple[str, bool]:
    """Return (commit_hash_or_unknown, dirty_flag)."""
    cwd = str(repo_root) if repo_root else None
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", True
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        dirty = bool(status.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        dirty = True
    return commit, dirty
