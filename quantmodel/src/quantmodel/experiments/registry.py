"""Append-only experiment registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantmodel.config import PACKAGE_ROOT
from quantmodel.hashing import canonical_json

DEFAULT_REGISTRY = PACKAGE_ROOT / "artifacts" / "experiment_registry.jsonl"


def next_experiment_number(path: Path = DEFAULT_REGISTRY) -> int:
    if not path.exists():
        return 1
    n = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n + 1


def append_experiment(record: dict[str, Any], path: Path = DEFAULT_REGISTRY) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    num = next_experiment_number(path)
    record = dict(record)
    record["experiment_number"] = num
    with path.open("a", encoding="utf-8") as f:
        f.write(canonical_json(record) + "\n")
    return num


def load_registry(path: Path = DEFAULT_REGISTRY) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def trial_count(path: Path = DEFAULT_REGISTRY) -> int:
    return len(load_registry(path))
