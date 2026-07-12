"""Content-addressed backtest cache.

Key = hash(engine sources + configs + codes + window + mode + cash + cost model).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_ROOT = ROOT / "runs" / "evolve_cache"
COST_MODEL_VERSION = "v1_commission_0.001"


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def engine_bundle_hash(model: dict[str, Any]) -> str:
    """Hash all runnable source files for a model dict from discover_models."""
    src: Path = model["src_dir"]
    model_dir: Path = model["model_dir"]
    names = (
        "signal_engine.py",
        "hunt_config.json",
        "meta_config.json",
        "meta_xgb_final.json",
        "vpa.py",
        "vwap_peg.py",
        "vwap_dna.json",
        "ROUTING.json",
        "RISK_POLICY.json",
        "config.json",
    )
    parts: list[str] = [model["id"]]
    for name in names:
        p = src / name
        if not p.exists() and model_dir != src:
            p = model_dir / name
        if p.exists() and p.is_file():
            parts.append(f"{name}:{_file_digest(p)}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def cache_key(
    model: dict[str, Any],
    *,
    mode: str,
    codes: Iterable[str],
    start: str,
    end: str,
    cash: float,
    interval: str = "1D",
    extra: dict[str, Any] | None = None,
) -> str:
    payload = {
        "engine": engine_bundle_hash(model),
        "mode": mode,
        "codes": list(codes),
        "start": start,
        "end": end,
        "cash": float(cash),
        "interval": interval,
        "cost_model": COST_MODEL_VERSION,
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def cache_dir(key: str, root: Path | None = None) -> Path:
    base = root or DEFAULT_CACHE_ROOT
    return base / key


def read_cached_metrics(key: str, root: Path | None = None) -> dict[str, Any] | None:
    d = cache_dir(key, root)
    meta = d / "metrics.json"
    if not meta.exists():
        # fall back to metrics.csv path shape
        csv_p = d / "artifacts" / "metrics.csv"
        if not csv_p.exists():
            return None
        import csv

        try:
            row = next(csv.DictReader(csv_p.open()))
            return {
                "ret": float(row["total_return"]),
                "dd": float(row["max_drawdown"]),
                "sharpe": float(row["sharpe"]),
                "n": int(float(row["trade_count"])),
                "wr": float(row["win_rate"]),
                "final": float(row["final_value"]),
                "from_cache": True,
                "cache_key": key,
            }
        except Exception:
            return None
    try:
        data = json.loads(meta.read_text())
        data["from_cache"] = True
        data["cache_key"] = key
        return data
    except Exception:
        return None


def write_cached_metrics(
    key: str,
    metrics: dict[str, Any],
    *,
    run_dir: Path | None = None,
    root: Path | None = None,
) -> Path:
    d = cache_dir(key, root)
    d.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in metrics.items() if k not in ("path",)}
    payload["cache_key"] = key
    (d / "metrics.json").write_text(json.dumps(payload, indent=2, default=str))
    if run_dir and run_dir.exists():
        art = run_dir / "artifacts" / "metrics.csv"
        if art.exists():
            dest = d / "artifacts"
            dest.mkdir(exist_ok=True)
            shutil.copy2(art, dest / "metrics.csv")
    return d
