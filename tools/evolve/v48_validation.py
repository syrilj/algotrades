"""Data-contract, causal-invariance, and snapshot helpers for v48 research."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_OHLCV = ("open", "high", "low", "close", "volume")


def validate_data_contract(
    data_map: Mapping[str, pd.DataFrame], *, expected_symbols: list[str] | None = None
) -> dict[str, object]:
    """Fail closed on malformed OHLCV or an incomplete requested universe."""
    if expected_symbols is not None:
        missing = sorted(set(expected_symbols) - set(data_map))
        if missing:
            raise ValueError(f"missing expected symbols: {missing}")
    summaries: dict[str, object] = {}
    for code, raw in data_map.items():
        missing = [column for column in REQUIRED_OHLCV if column not in raw.columns]
        if missing:
            raise ValueError(f"{code}: missing OHLCV columns {missing}")
        frame = raw.loc[:, REQUIRED_OHLCV].copy()
        frame.index = pd.to_datetime(frame.index)
        if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
            raise ValueError(f"{code}: timestamps must be sorted and unique")
        if frame.isna().any().any():
            raise ValueError(f"{code}: OHLCV contains null values")
        if (frame["volume"] < 0).any():
            raise ValueError(f"{code}: negative volume")
        if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
            raise ValueError(f"{code}: invalid high")
        if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
            raise ValueError(f"{code}: invalid low")
        summaries[code] = {
            "rows": int(len(frame)),
            "start": str(frame.index.min()),
            "end": str(frame.index.max()),
            "timezone": str(getattr(frame.index, "tz", None) or "naive"),
        }
    return {"symbols": summaries, "count": len(summaries), "pricing": "adjusted_local_ohlcv"}


def _equal(left: pd.Series, right: pd.Series, context: str) -> None:
    left = left.astype(float).fillna(0.0)
    right = right.reindex(left.index).astype(float).fillna(0.0)
    if not np.allclose(left.to_numpy(), right.to_numpy(), rtol=0.0, atol=1e-12):
        raise AssertionError(f"causal invariance failed: {context}")


def assert_prefix_invariance(
    engine_factory: Callable[[], object], data_map: Mapping[str, pd.DataFrame], cut: int
) -> None:
    full = engine_factory().generate(dict(data_map))
    prefix = {code: frame.iloc[:cut].copy() for code, frame in data_map.items()}
    partial = engine_factory().generate(prefix)
    for code in prefix:
        _equal(partial[code], full[code].iloc[:cut], f"prefix:{code}")


def assert_future_perturbation_invariance(
    engine_factory: Callable[[], object], data_map: Mapping[str, pd.DataFrame], cut: int
) -> None:
    baseline = engine_factory().generate(dict(data_map))
    altered: dict[str, pd.DataFrame] = {}
    for code, raw in data_map.items():
        frame = raw.copy().astype({column: float for column in REQUIRED_OHLCV if column in raw})
        if cut < len(frame):
            future = frame.iloc[cut:].copy()
            # Preserve valid OHLC relationships while making the future clearly different.
            future.loc[:, ["open", "high", "low", "close"]] *= 1.37
            future.loc[:, "volume"] *= 1.91
            frame.iloc[cut:] = future
        altered[code] = frame
    perturbed = engine_factory().generate(altered)
    for code in data_map:
        _equal(perturbed[code].iloc[:cut], baseline[code].iloc[:cut], f"future:{code}")


def assert_symbol_order_invariance(
    engine_factory: Callable[[], object], data_map: Mapping[str, pd.DataFrame]
) -> None:
    baseline = engine_factory().generate(dict(data_map))
    reordered = engine_factory().generate(dict(reversed(list(data_map.items()))))
    for code in data_map:
        _equal(baseline[code], reordered[code], f"symbol_order:{code}")


def assert_repeatability(engine_factory: Callable[[], object], data_map: Mapping[str, pd.DataFrame]) -> None:
    first = engine_factory().generate(dict(data_map))
    second = engine_factory().generate(dict(data_map))
    for code in data_map:
        _equal(first[code], second[code], f"repeat:{code}")


def run_causal_invariance_suite(
    engine_factory: Callable[[], object], data_map: Mapping[str, pd.DataFrame]
) -> dict[str, bool]:
    if not data_map:
        raise ValueError("empty data map")
    validate_data_contract(data_map)
    cut = min(len(frame) for frame in data_map.values()) // 2
    if cut < 30:
        raise ValueError("need at least 60 bars for the causal suite")
    assert_prefix_invariance(engine_factory, data_map, cut)
    assert_future_perturbation_invariance(engine_factory, data_map, cut)
    assert_symbol_order_invariance(engine_factory, data_map)
    assert_repeatability(engine_factory, data_map)
    return {"prefix": True, "future_perturbation": True, "symbol_order": True, "repeatability": True}


def load_signal_engine(model_dir: Path):
    path = Path(model_dir) / "signal_engine.py"
    spec = importlib.util.spec_from_file_location(f"v48_engine_{path.parent.name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.SignalEngine


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependency_hashes(model_dir: Path) -> dict[str, str]:
    model_dir = Path(model_dir)
    result: dict[str, str] = {}
    for name in ("signal_engine.py", "config.json", "DEPENDENCIES.json"):
        path = model_dir / name
        if path.exists():
            result[name] = sha256(path)
    manifest = model_dir / "DEPENDENCIES.json"
    if manifest.exists():
        for item in json.loads(manifest.read_text()).get("files", []):
            if isinstance(item, dict) and isinstance(item.get("source"), str):
                path = (model_dir / item["source"]).resolve()
                if path.is_file():
                    result[str(item.get("target", path.name))] = sha256(path)
    return result


def build_frozen_manifest(
    *, model_dir: Path, policy: str, data_contract: dict[str, object], trial_count: int, seed: int = 42
) -> dict[str, object]:
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except Exception:
        git_commit, dirty = "unknown", True
    return {
        "model": Path(model_dir).name,
        "policy": policy,
        "teacher_hashes": dependency_hashes(Path(model_dir)),
        "data_contract": data_contract,
        "trial_count": int(trial_count),
        "seed": int(seed),
        "git_commit": git_commit,
        "dirty_worktree": dirty,
        "frozen": True,
    }
