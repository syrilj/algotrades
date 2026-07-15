"""Content-addressed backtest cache.

Key = hash(engine sources + configs + data provenance + env versions + codes + window + mode + cash + cost model).
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import shutil
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_ROOT = ROOT / "runs" / "evolve_cache"
COST_MODEL_VERSION = "v1_commission_0.001"
DATA_CACHE = ROOT / "data_cache"
DATA_MANIFEST = DATA_CACHE / "MANIFEST.json"

VERSION_PACKAGES = (
    "backtest",
    "vibe-trading-ai",
    "lse-data",
    "xgboost",
    "mlflow",
    "scikit-learn",
    "pandas",
    "numpy",
)


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return "unknown"


def env_versions() -> dict[str, str]:
    """Snapshot of runtime versions that affect backtest outputs."""
    return {
        "python": platform.python_version(),
        **{name: _version(name) for name in VERSION_PACKAGES},
    }


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
        "DEPENDENCIES.json",
    )
    parts: list[str] = [model["id"]]
    for name in names:
        p = src / name
        if not p.exists() and model_dir != src:
            p = model_dir / name
        if p.exists() and p.is_file():
            parts.append(f"{name}:{_file_digest(p)}")
    manifest = src / "DEPENDENCIES.json"
    if not manifest.exists() and model_dir != src:
        manifest = model_dir / "DEPENDENCIES.json"
    if manifest.exists():
        try:
            for item in json.loads(manifest.read_text()).get("files", []):
                if not isinstance(item, dict) or not isinstance(item.get("source"), str):
                    continue
                dep = (src / item["source"]).resolve()
                if dep.is_file():
                    parts.append(f"dep:{item.get('target', dep.name)}:{_file_digest(dep)}")
        except Exception:
            parts.append("dependencies:invalid")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def data_bundle_hash(
    source: str,
    interval: str,
    codes: Iterable[str],
    start: str,
    end: str,
) -> dict[str, Any]:
    """Hash the data bundle that will be fed into the engine.

    For local/bridge data we use the snapshot MANIFEST.json and SHA-256 of
    the individual parquet files. For remote sources (e.g. yfinance) we fall
    back to source + interval + window, which is weaker but still deterministic
    for a fixed cache key.
    """
    symbols = {c.lstrip("^").replace(".US", "") for c in codes}
    if source == "local" and DATA_MANIFEST.exists():
        try:
            manifest = json.loads(DATA_MANIFEST.read_text())
            # Select entries for this interval/window and requested symbols
            entries = [
                e
                for e in manifest.get("entries", [])
                if e.get("interval", "").lower() == interval.lower()
                and e.get("symbol", "").lstrip("^").split(".")[0] in symbols
            ]
            shas = sorted(e.get("sha256", "") for e in entries)
            return {
                "source": source,
                "interval": interval,
                "start": start,
                "end": end,
                "manifest_version": manifest.get("generated_utc", ""),
                "package_version": manifest.get("package_version", ""),
                "sha256_digest": hashlib.sha256("|".join(shas).encode()).hexdigest()[:20],
                "n_files": len(entries),
            }
        except Exception:
            pass
    return {
        "source": source,
        "interval": interval,
        "start": start,
        "end": end,
        "sha256_digest": "",
    }


def cache_key(
    model: dict[str, Any],
    *,
    mode: str,
    codes: Iterable[str],
    start: str,
    end: str,
    cash: float,
    interval: str = "1D",
    source: str = "yfinance",
    extra: dict[str, Any] | None = None,
) -> str:
    payload = {
        "engine": engine_bundle_hash(model),
        "data": data_bundle_hash(source, interval, codes, start, end),
        "env": env_versions(),
        "mode": mode,
        "codes": list(codes),
        "start": start,
        "end": end,
        "cash": float(cash),
        "interval": interval,
        "source": source,
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
