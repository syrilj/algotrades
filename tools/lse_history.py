#!/usr/bin/env python3
"""LSE historical candle snapshot/backfill for the local data cache.

CLI:
  .venv/bin/python tools/lse_history.py snapshot --intervals 1h 1d
  .venv/bin/python tools/lse_history.py use-bridge 1h
  .venv/bin/python tools/lse_history.py verify

Requires LSE_API_KEY (or lse-data default env lookup).
Writes under data_cache/lse/<interval>/<symbol>.parquet and produces
bridge_config_lse_<interval>.yaml for source=local backtests.
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
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_CACHE = ROOT / "data_cache" / "lse"
BRIDGE_DIR = Path.home() / ".vibe-trading" / "data-bridge"
BRIDGE_PATH = BRIDGE_DIR / "config.yaml"

END_DATE = "2026-07-13"
START_1H = "2024-07-01"
START_1D = "2020-01-01"

# Same US equity universe used by snapshot_data.py; LSE coverage supports the same tickers
LSE_SYMBOLS = [
    "TSLA.US",
    "MU.US",
    "SPY.US",
    "IONQ.US",
    "APLD.US",
    "QQQ.US",
    "XLP.US",
    "HYG.US",
    "LQD.US",
    "ARM.US",
    "COIN.US",
    "RKLB.US",
    "NVDA.US",
    "PLTR.US",
    "MSTR.US",
]


def _lse_symbol(sym: str) -> str:
    s = sym.strip().upper().replace(".US", "")
    # FX convention if a 6-letter alphabetic string is passed
    if len(s) == 6 and s.isalpha() and "/" not in s:
        s = f"{s[:3]}/{s[3:]}"
    return s


def _lse_candles_to_df(candles: list[dict]) -> Any:
    import pandas as pd

    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df.rename(
        columns={
            k: v
            for k, v in {
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }.items()
            if k in df.columns
        }
    )
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = 0.0
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def _ensure_services() -> None:
    services = str(ROOT / "services")
    if services not in sys.path:
        sys.path.insert(0, services)


def _lse_adapter() -> Any:
    _ensure_services()
    from market_runtime import LSEAdapter

    key = os.environ.get("LSE_API_KEY")
    return LSEAdapter(api_key=key)


def _fetch_candles(
    adapter: Any,
    symbol: str,
    interval: str,
    start: str,
    end: str,
    limit: int = 5000,
) -> Any:
    """Fetch LSE candles and return a normalized OHLCV DataFrame.

    Candles are paginated when the API limit is hit; the `start` parameter is
    advanced to the last returned timestamp until the window is fully covered.
    """
    end_ts = pd.Timestamp(end)
    start_ts = pd.Timestamp(start)
    dfs: list[Any] = []
    while start_ts < end_ts:
        try:
            candles = adapter.client.candles(
                _lse_symbol(symbol),
                timeframe=interval,
                start=start_ts.isoformat(),
                end=end_ts.isoformat(),
                limit=limit,
                order="asc",
            )
        except Exception as exc:
            print(f"[lse_history] {symbol} {interval} fetch failed: {exc}", flush=True)
            break
        df = _lse_candles_to_df(candles)
        if df.empty:
            break
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)
        df = df[df.index <= end_ts]
        if df.empty:
            break
        dfs.append(df)
        # Advance start to the next bar after the latest returned timestamp
        last_ts = df.index.max()
        if last_ts >= end_ts:
            break
        if len(df) < limit:
            break
        if interval == "1h":
            start_ts = last_ts + pd.Timedelta(hours=1)
        elif interval == "1d":
            start_ts = last_ts + pd.Timedelta(days=1)
        else:
            start_ts = last_ts + pd.Timedelta(minutes=1)
    if not dfs:
        return None
    combined = pd.concat(dfs)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    combined.index.name = "date"
    return combined


def _snapshot_interval(
    adapter: Any,
    interval: str,
    symbols: list[str],
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    DATA_CACHE.mkdir(parents=True, exist_ok=True)
    out_dir = DATA_CACHE / interval
    out_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    for symbol in symbols:
        df = _fetch_candles(adapter, symbol, interval, start, end)
        if df is None:
            print(f"[lse_history] {symbol} {interval} skipped", flush=True)
            continue
        name = symbol.replace(".US", "").replace("^", "")
        path = out_dir / f"{name}.parquet"
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
        print(f"[lse_history] {symbol} {interval} rows={rows} {path}", flush=True)
    return entries


def _write_bridge_config(interval: str, entries: list[dict[str, Any]]) -> Path:
    import yaml

    sources = []
    for e in entries:
        if e["interval"] != interval:
            continue
        path = ROOT / e["path"]
        sources.append({"symbol": e["symbol"], "type": "parquet", "path": str(path)})
    config = {"sources": sources}
    path = DATA_CACHE / f"bridge_config_lse_{interval}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def _write_manifest(entries: list[dict[str, Any]]) -> Path:
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    path = DATA_CACHE / "MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path


def run_snapshot(intervals: list[str] | None = None) -> dict[str, Any]:
    intervals = intervals or ["1h", "1d"]
    adapter = _lse_adapter()
    entries: list[dict[str, Any]] = []
    for interval in intervals:
        start = START_1H if interval == "1h" else START_1D
        entries.extend(_snapshot_interval(adapter, interval, LSE_SYMBOLS, start, END_DATE))
    for interval in intervals:
        _write_bridge_config(interval, entries)
    manifest_path = _write_manifest(entries)
    print(f"[lse_history] wrote manifest {manifest_path}", flush=True)
    return {"ok": True, "manifest": str(manifest_path), "entries": len(entries)}


def run_backfill(intervals: list[str] | None = None) -> dict[str, Any]:
    """Alias for snapshot; LSE candles(start,end,limit) already returns the full window."""
    return run_snapshot(intervals)


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
    return {"ok": len(errors) == 0, "errors": errors, "entries": len(manifest.get("entries", []))}


def use_bridge(interval: str) -> Path:
    if not BRIDGE_DIR.exists():
        BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    if BRIDGE_PATH.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BRIDGE_PATH.with_suffix(f".yaml.bak-{stamp}")
        shutil.copy2(BRIDGE_PATH, backup)
    src = DATA_CACHE / f"bridge_config_lse_{interval}.yaml"
    if not src.exists():
        raise FileNotFoundError(f"bridge config not found: {src}")
    shutil.copy2(src, BRIDGE_PATH)
    return BRIDGE_PATH


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="LSE historical snapshot/backfill")
    sub = p.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="Fetch LSE candles and write manifest")
    snap.add_argument("--intervals", nargs="+", choices=["1h", "1d"], default=["1h", "1d"])
    sub.add_parser("backfill", help="Backfill LSE candles (same as snapshot)")
    sub.add_parser("verify", help="Check LSE manifest and files")
    use = sub.add_parser("use-bridge", help="Copy LSE bridge config to live bridge")
    use.add_argument("interval", choices=["1h", "1d"])
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "snapshot":
        run_snapshot(args.intervals)
    elif args.cmd == "backfill":
        run_backfill(args.intervals)
    elif args.cmd == "verify":
        print(run_verify(), flush=True)
    elif args.cmd == "use-bridge":
        print(use_bridge(args.interval), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
