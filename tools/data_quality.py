#!/usr/bin/env python3
"""Fail-closed validation for versioned OHLCV snapshot manifests."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("open", "high", "low", "close", "volume")


def validate_frame(frame: pd.DataFrame, *, symbol: str = "unknown") -> list[str]:
    errors: list[str] = []
    columns = {str(column).lower(): column for column in frame.columns}
    missing = [name for name in REQUIRED if name not in columns]
    if missing:
        return [f"{symbol}:missing_columns:{','.join(missing)}"]
    if frame.empty:
        return [f"{symbol}:empty"]
    index = pd.to_datetime(frame.index, errors="coerce")
    if index.isna().any():
        errors.append(f"{symbol}:invalid_timestamp")
    if not index.is_monotonic_increasing:
        errors.append(f"{symbol}:non_monotonic_index")
    if index.duplicated().any():
        errors.append(f"{symbol}:duplicate_timestamps")

    values = frame[[columns[name] for name in REQUIRED]].astype(float)
    if not np.isfinite(values.to_numpy()).all():
        errors.append(f"{symbol}:non_finite_ohlcv")
    open_ = values[columns["open"]]
    high = values[columns["high"]]
    low = values[columns["low"]]
    close = values[columns["close"]]
    volume = values[columns["volume"]]
    if ((open_ <= 0) | (high <= 0) | (low <= 0) | (close <= 0)).any():
        errors.append(f"{symbol}:non_positive_price")
    if (volume < 0).any():
        errors.append(f"{symbol}:negative_volume")
    row_scale = pd.concat([open_.abs(), high.abs(), low.abs(), close.abs()], axis=1).max(axis=1)
    tolerance = row_scale * 1e-8 + 1e-10
    if (high + tolerance < pd.concat([open_, close, low], axis=1).max(axis=1)).any():
        errors.append(f"{symbol}:high_inconsistent")
    if (low - tolerance > pd.concat([open_, close, high], axis=1).min(axis=1)).any():
        errors.append(f"{symbol}:low_inconsistent")
    return errors


def validate_manifest(
    manifest_path: str | Path = ROOT / "data_cache" / "MANIFEST.json",
    *,
    verify_checksums: bool = True,
    max_age_days: float | None = 7.0,
) -> dict[str, Any]:
    path = Path(manifest_path)
    errors: list[str] = []
    warnings: list[str] = []
    entries_report: list[dict[str, Any]] = []
    if not path.exists():
        return {"ok": False, "errors": ["manifest_missing"], "entries": []}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"manifest_invalid:{exc}"], "entries": []}
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        return {"ok": False, "errors": ["manifest_entries_missing"], "entries": []}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        symbol = str(entry.get("symbol") or "")
        interval = str(entry.get("interval") or "")
        key = (symbol, interval.lower())
        row_errors: list[str] = []
        if not symbol or not interval:
            row_errors.append("identity_missing")
        if key in seen:
            row_errors.append("duplicate_manifest_entry")
        seen.add(key)
        raw_path = Path(str(entry.get("path") or ""))
        file_path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        if not file_path.exists():
            row_errors.append("file_missing")
        else:
            if verify_checksums:
                digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
                if digest != str(entry.get("sha256") or ""):
                    row_errors.append("checksum_mismatch")
            try:
                frame = pd.read_parquet(file_path)
                row_errors.extend(validate_frame(frame, symbol=f"{symbol}/{interval}"))
                declared_rows = entry.get("rows")
                if declared_rows is not None and int(declared_rows) != len(frame):
                    row_errors.append("row_count_mismatch")
                if len(frame) < 50:
                    warnings.append(f"{symbol}/{interval}:thin_history:{len(frame)}")
                if max_age_days is not None and len(frame):
                    latest = pd.Timestamp(frame.index.max())
                    if latest.tzinfo is not None:
                        latest = latest.tz_convert("UTC").tz_localize(None)
                    age_days = (pd.Timestamp(now) - latest).total_seconds() / 86400.0
                    if math.isfinite(age_days) and age_days > max_age_days:
                        warnings.append(f"{symbol}/{interval}:stale:{age_days:.1f}d")
            except Exception as exc:  # noqa: BLE001
                row_errors.append(f"read_failed:{exc}")
        if row_errors:
            errors.extend(f"{symbol or 'unknown'}/{interval or 'unknown'}:{item}" for item in row_errors)
        entries_report.append(
            {"symbol": symbol, "interval": interval, "path": str(file_path), "errors": row_errors}
        )
    return {
        "schema_version": "ohlcv-data-quality-v1",
        "ok": not errors,
        "manifest": str(path),
        "generated_utc": manifest.get("generated_utc"),
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
        "errors": errors,
        "warnings": warnings,
        "entries": entries_report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an OHLCV data snapshot")
    parser.add_argument("--manifest", default=str(ROOT / "data_cache" / "MANIFEST.json"))
    parser.add_argument("--no-checksum", action="store_true")
    parser.add_argument("--max-age-days", type=float, default=7.0)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = validate_manifest(
        args.manifest,
        verify_checksums=not args.no_checksum,
        max_age_days=args.max_age_days,
    )
    text = json.dumps(report, indent=2, default=str) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(output)
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
