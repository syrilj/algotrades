#!/usr/bin/env python3
"""Snapshot yfinance data for the evolve_direction_v1 universe.

CLI:
  .venv/bin/python tools/snapshot_data.py snapshot
  .venv/bin/python tools/snapshot_data.py verify
  .venv/bin/python tools/snapshot_data.py use-bridge 1h

Reads/writes under data_cache/ and manages ~/.vibe-trading/data-bridge/config.yaml.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_CACHE = ROOT / "data_cache"
BRIDGE_DIR = Path.home() / ".vibe-trading" / "data-bridge"
BRIDGE_PATH = BRIDGE_DIR / "config.yaml"

CORE_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US"]
GATE_ETFS = ["QQQ.US", "XLP.US", "HYG.US", "LQD.US"]
CANDIDATES = ["ARM.US", "COIN.US", "RKLB.US", "NVDA.US", "PLTR.US", "MSTR.US"]
SECTORS = ["XLK.US", "XLF.US", "XLE.US", "XLV.US", "XLY.US", "XLI.US", "XLU.US", "XLB.US", "XLC.US"]
INDICES = ["^VIX", "^TNX"]

UNIVERSE_1H = CORE_BAG + GATE_ETFS + CANDIDATES
UNIVERSE_1D = CORE_BAG + GATE_ETFS + CANDIDATES + SECTORS + INDICES

INTERVAL_START = {
    "1h": "2024-07-01",
    "1d": "2018-01-01",
}

END_DATE = "2026-07-13"


def _ensure_env() -> None:
    os.environ.setdefault("VIBE_TRADING_DATA_CACHE", "1")
    os.environ.setdefault("VIBE_TRADING_DATA_CACHE_ROOT", str(DATA_CACHE))


def _yf_ticker(symbol: str) -> str:
    return symbol.replace(".US", "")


def _download_one(symbol: str, interval: str, start: str, end: str) -> pd.DataFrame | None:
    import yfinance as yf

    ticker = _yf_ticker(symbol)
    kwargs = {
        "progress": False,
        "auto_adjust": True,
        "threads": False,
    }
    if interval == "1h":
        # 1h history is limited to ~730 days; yfinance with start/end rejects
        # long ranges. Use the 2y period and crop below.
        kwargs["period"] = "2y"
        kwargs["interval"] = "1h"
    else:
        kwargs["start"] = start
        kwargs["end"] = end
        kwargs["interval"] = interval
    try:
        df = yf.download(ticker, **kwargs)
    except Exception as exc:
        print(f"[snapshot] {symbol} {interval} download failed: {exc}", flush=True)
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    need = {"open", "high", "low", "close"}
    if not need.issubset(set(df.columns)):
        print(f"[snapshot] {symbol} {interval} missing OHLC columns: {list(df.columns)}")
        return None
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df = df[["open", "high", "low", "close", "volume"]].astype(float).dropna()
    if df.empty:
        return None
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    end_ts = pd.Timestamp(end)
    df = df[df.index <= end_ts]
    return df


def _snapshot_interval(interval: str, symbols: list[str]) -> list[dict[str, Any]]:
    _ensure_env()
    DATA_CACHE.mkdir(parents=True, exist_ok=True)
    out_dir = DATA_CACHE / interval
    out_dir.mkdir(parents=True, exist_ok=True)

    start = INTERVAL_START[interval]
    end = END_DATE
    entries: list[dict[str, Any]] = []

    for symbol in symbols:
        df = _download_one(symbol, interval, start, end)
        if df is None:
            print(f"[snapshot] {symbol} {interval} skipped", flush=True)
            continue
        path = out_dir / f"{_yf_ticker(symbol).replace('^', '')}.parquet"
        df.to_parquet(path)
        rows = len(df)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(
            {
                "symbol": symbol,
                "interval": interval,
                "path": str(path.relative_to(ROOT)),
                "start": df.index.min().strftime("%Y-%m-%d %H:%M:%S"),
                "end": df.index.max().strftime("%Y-%m-%d %H:%M:%S"),
                "rows": rows,
                "sha256": sha,
            }
        )
        print(f"[snapshot] {symbol} {interval} rows={rows} {path}", flush=True)

    return entries


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("vibe-trading-ai")
    except Exception:
        return "unknown"


def _write_manifest(entries: list[dict[str, Any]]) -> Path:
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": _package_version(),
        "entries": entries,
    }
    path = DATA_CACHE / "MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path


def _write_bridge_config(interval: str, entries: list[dict[str, Any]]) -> Path:
    sources = []
    for e in entries:
        if e["interval"] != interval:
            continue
        path = ROOT / e["path"]
        sources.append(
            {
                "symbol": e["symbol"],
                "type": "parquet",
                "path": str(path),
            }
        )
    config = {"sources": sources}
    import yaml

    path = DATA_CACHE / f"bridge_config_{interval}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def use_bridge(interval: str) -> Path:
    """Copy bridge_config_<interval>.yaml into the live bridge path."""
    _ensure_env()
    if not BRIDGE_DIR.exists():
        BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    if BRIDGE_PATH.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BRIDGE_PATH.with_suffix(f".yaml.bak-{stamp}")
        shutil.copy2(BRIDGE_PATH, backup)
    src = DATA_CACHE / f"bridge_config_{interval}.yaml"
    if not src.exists():
        raise FileNotFoundError(f"bridge config not found: {src}")
    shutil.copy2(src, BRIDGE_PATH)
    return BRIDGE_PATH


def run_snapshot() -> dict[str, Any]:
    _ensure_env()
    DATA_CACHE.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    entries.extend(_snapshot_interval("1h", UNIVERSE_1H))
    entries.extend(_snapshot_interval("1d", UNIVERSE_1D))
    for e in entries:
        _write_bridge_config(e["interval"], [e])
    # Re-write full bridge configs per interval
    for interval in ("1h", "1d"):
        _write_bridge_config(interval, [e for e in entries if e["interval"] == interval])
    manifest_path = _write_manifest(entries)
    print(f"[snapshot] wrote manifest {manifest_path}", flush=True)
    return {"ok": True, "manifest": str(manifest_path), "entries": len(entries)}


def run_verify() -> dict[str, Any]:
    manifest_path = DATA_CACHE / "MANIFEST.json"
    if not manifest_path.exists():
        return {"ok": False, "error": "missing MANIFEST.json"}
    manifest = json.loads(manifest_path.read_text())
    errors = []
    for e in manifest.get("entries", []):
        path = ROOT / e["path"]
        if not path.exists():
            errors.append(f"missing {e['path']}")
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha != e["sha256"]:
            errors.append(f"sha256 mismatch {e['path']}")
    for interval in ("1h", "1d"):
        bridge = DATA_CACHE / f"bridge_config_{interval}.yaml"
        if not bridge.exists():
            errors.append(f"missing bridge config {bridge}")
    return {"ok": len(errors) == 0, "errors": errors, "entries": len(manifest.get("entries", []))}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Snapshot market data for evolve_direction_v1")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="Fetch 1h and 1d data and write manifest")
    sub.add_parser("verify", help="Check manifest and bridge configs")
    use = sub.add_parser("use-bridge", help="Copy bridge config to live bridge")
    use.add_argument("interval", choices=["1h", "1d"])
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "snapshot":
        res = run_snapshot()
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    if args.cmd == "verify":
        res = run_verify()
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    if args.cmd == "use-bridge":
        try:
            path = use_bridge(args.interval)
            print(f"[snapshot] active bridge -> {path}")
            return 0
        except Exception as exc:
            print(f"[snapshot] use-bridge failed: {exc}")
            return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
