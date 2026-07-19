"""Vendor-independent data loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

import pandas as pd

from quantmodel.config import get_cache_root
from quantmodel.data.quality import validate_security_bars
from quantmodel.data.schema import ensure_schema, from_ohlcv
from quantmodel.data.synthetic import generate_synthetic_universe
from quantmodel.hashing import sha256_file, sha256_text
from quantmodel.types import QualityIssue


class DataVendor(Protocol):
    def load(self) -> dict[str, Any]:
        """Return dict with bars, earnings, metadata, issues."""
        ...


def load_market_data(config: Mapping[str, Any], *, run_id: str = "load") -> dict[str, Any]:
    vendor_name = config["data"]["vendor"]
    if vendor_name == "synthetic":
        vendor: DataVendor = SyntheticVendor(config)
    elif vendor_name == "lse_cache":
        vendor = LseCacheVendor(config)
    elif vendor_name == "local_cache":
        vendor = LocalCacheVendor(config)
    else:
        raise ValueError(
            f"Vendor {vendor_name!r} not implemented yet. "
            "Use synthetic | lse_cache | local_cache."
        )
    payload = vendor.load()
    bars: pd.DataFrame = payload["bars"]
    issues: list[QualityIssue] = list(payload.get("issues", []))

    clean_parts: list[pd.DataFrame] = []
    for sid, grp in bars.groupby("permanent_security_id", sort=False):
        clean, qi = validate_security_bars(grp, run_id=run_id)
        issues.extend(qi)
        if not clean.empty:
            clean_parts.append(clean)
    clean_bars = (
        pd.concat(clean_parts, ignore_index=True) if clean_parts else ensure_schema(pd.DataFrame())
    )
    clean_bars = ensure_schema(clean_bars)

    # Date filters
    start = config["data"].get("start_date")
    end = config["data"].get("end_date")
    if start:
        clean_bars = clean_bars[clean_bars["date"] >= pd.Timestamp(start)]
    if end:
        clean_bars = clean_bars[clean_bars["date"] <= pd.Timestamp(end)]

    meta = dict(payload.get("metadata", {}))
    meta.setdefault("survivorship_bias", config["data"].get("survivorship_bias", True))
    meta.setdefault(
        "data_manifest_hash",
        sha256_text(str(sorted(clean_bars["symbol"].unique())) + str(len(clean_bars))),
    )
    meta["n_bars"] = int(len(clean_bars))
    meta["n_securities"] = int(clean_bars["permanent_security_id"].nunique()) if len(clean_bars) else 0

    return {
        "bars": clean_bars.reset_index(drop=True),
        "earnings": payload.get("earnings", pd.DataFrame()),
        "metadata": meta,
        "issues": issues,
    }


class SyntheticVendor:
    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config

    def load(self) -> dict[str, Any]:
        d = self.config["data"]
        payload = generate_synthetic_universe(
            start=d.get("start_date") or "2018-01-01",
            end=d.get("end_date") or "2024-12-31",
            seed=int(self.config["run"].get("seed", 42)),
        )
        return {
            "bars": payload["bars"],
            "earnings": payload["earnings"],
            "metadata": payload["metadata"],
            "issues": [],
        }


class LseCacheVendor:
    """Load OHLCV from monorepo data_cache/lse/<interval>/*.parquet."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config

    def load(self) -> dict[str, Any]:
        cache_root = get_cache_root(self.config)
        interval = self.config["data"].get("lse_interval", "1d")
        lse_dir = cache_root / "lse" / interval
        if not lse_dir.exists():
            # try cache_root itself if path already points at lse
            alt = cache_root / interval
            lse_dir = alt if alt.exists() else lse_dir
        if not lse_dir.exists():
            raise FileNotFoundError(
                f"LSE cache not found at {lse_dir}. "
                "Run tools/lse_history.py snapshot or use vendor=synthetic."
            )

        manifest_path = cache_root / "lse" / "MANIFEST.json"
        file_hashes: dict[str, str] = {}
        frames: list[pd.DataFrame] = []
        for path in sorted(lse_dir.glob("*.parquet")):
            symbol = path.stem.upper()
            try:
                raw = pd.read_parquet(path)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Failed reading {path}: {exc}") from exc
            fr = from_ohlcv(
                raw,
                symbol=symbol,
                permanent_security_id=f"LSE_{symbol}",
                exchange="US",
                security_type="common_stock" if symbol not in {"SPY", "QQQ", "HYG", "LQD", "XLP"} else "etf",
                sector="UNKNOWN",
            )
            frames.append(fr)
            file_hashes[symbol] = sha256_file(path)

        if not frames:
            raise FileNotFoundError(f"No parquet files in {lse_dir}")

        bars = pd.concat(frames, ignore_index=True)
        meta = {
            "vendor": "lse_cache",
            "path": str(lse_dir),
            "manifest_path": str(manifest_path) if manifest_path.exists() else None,
            "file_hashes": file_hashes,
            "survivorship_bias": True,
            "symbols": sorted(bars["symbol"].unique().tolist()),
            "data_manifest_hash": sha256_text(json.dumps(file_hashes, sort_keys=True)),
            "adjustment_convention": self.config["data"].get(
                "adjustment_convention", "vendor_single_series_as_adjusted"
            ),
            "limitations": [
                "survivorship_bias",
                "no_delisted_history",
                "no_pit_sector",
                "no_earnings_calendar",
                "limited_history",
            ],
        }
        if manifest_path.exists():
            meta["vendor_manifest"] = json.loads(manifest_path.read_text(encoding="utf-8")).get(
                "generated_utc"
            )
        return {"bars": bars, "earnings": pd.DataFrame(), "metadata": meta, "issues": []}


class LocalCacheVendor:
    """Load from data_cache/1d or data_cache/yahoo style folders."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config

    def load(self) -> dict[str, Any]:
        cache_root = get_cache_root(self.config)
        candidates = [cache_root / "1d", cache_root / "yahoo", cache_root]
        frames: list[pd.DataFrame] = []
        file_hashes: dict[str, str] = {}
        used: Path | None = None
        for folder in candidates:
            if not folder.exists():
                continue
            paths = list(folder.glob("*.parquet"))
            if not paths:
                continue
            used = folder
            for path in sorted(paths):
                symbol = path.stem.upper()
                raw = pd.read_parquet(path)
                fr = from_ohlcv(raw, symbol=symbol, permanent_security_id=f"LOC_{symbol}")
                frames.append(fr)
                file_hashes[symbol] = sha256_file(path)
            break
        if not frames or used is None:
            raise FileNotFoundError(f"No local cache parquet under {cache_root}")
        bars = pd.concat(frames, ignore_index=True)
        meta = {
            "vendor": "local_cache",
            "path": str(used),
            "file_hashes": file_hashes,
            "survivorship_bias": True,
            "symbols": sorted(bars["symbol"].unique().tolist()),
            "data_manifest_hash": sha256_text(json.dumps(file_hashes, sort_keys=True)),
            "limitations": ["survivorship_bias", "no_delisted_history"],
        }
        return {"bars": bars, "earnings": pd.DataFrame(), "metadata": meta, "issues": []}
