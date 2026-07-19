"""Data integrity checks and quarantine logging."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quantmodel.types import QualityIssue

ISSUE_CODES = (
    "high_inconsistent",
    "low_inconsistent",
    "negative_volume",
    "non_positive_price",
    "duplicate_bar",
    "out_of_order",
    "non_finite",
    "impossible_return",
)


def validate_security_bars(
    df: pd.DataFrame,
    *,
    run_id: str = "pre",
) -> tuple[pd.DataFrame, list[QualityIssue]]:
    """Return clean frame and list of quarantined issues (rows dropped)."""
    if df.empty:
        return df.copy(), []
    issues: list[QualityIssue] = []
    work = df.copy().sort_values("date")
    keep = pd.Series(True, index=work.index)

    def flag(mask: pd.Series, code: str) -> None:
        nonlocal keep
        if not mask.any():
            return
        for idx in work.index[mask]:
            row = work.loc[idx]
            d = row["date"]
            if hasattr(d, "date"):
                d = d.date() if not isinstance(d, date) else d
            issues.append(
                QualityIssue(
                    run_id=run_id,
                    security_id=str(row["permanent_security_id"]),
                    symbol=str(row["symbol"]),
                    date=d if isinstance(d, date) else None,
                    issue_code=code,
                    raw_values=str(
                        {
                            "o": row["open"],
                            "h": row["high"],
                            "l": row["low"],
                            "c": row["close"],
                            "v": row["volume"],
                        }
                    ),
                    resolution="quarantined",
                )
            )
        keep &= ~mask

    o, h, l, c, v = (
        work["open"].astype(float),
        work["high"].astype(float),
        work["low"].astype(float),
        work["close"].astype(float),
        work["volume"].astype(float),
    )
    flag(~np.isfinite(o) | ~np.isfinite(h) | ~np.isfinite(l) | ~np.isfinite(c) | ~np.isfinite(v), "non_finite")
    flag((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0), "non_positive_price")
    flag(v < 0, "negative_volume")
    flag(h + 1e-12 < pd.concat([o, c, l], axis=1).max(axis=1), "high_inconsistent")
    flag(l - 1e-12 > pd.concat([o, c, h], axis=1).min(axis=1), "low_inconsistent")
    flag(work["date"].duplicated(keep="first"), "duplicate_bar")
    dates = pd.to_datetime(work["date"])
    if not dates.is_monotonic_increasing:
        # mark all after first decrease
        prev = dates.shift(1)
        flag(prev.notna() & (dates < prev), "out_of_order")

    clean = work.loc[keep].copy()
    # impossible returns without corporate action
    if len(clean) > 1:
        rets = clean["close"].pct_change()
        splits = clean["split_factor"].fillna(1.0)
        bad = rets.abs() > 0.5
        # allow if split_factor != 1 on that day
        bad = bad & (splits == 1.0) & rets.notna()
        if bad.any():
            for idx in clean.index[bad]:
                row = clean.loc[idx]
                d = row["date"]
                if hasattr(d, "date"):
                    d = d.date()
                issues.append(
                    QualityIssue(
                        run_id=run_id,
                        security_id=str(row["permanent_security_id"]),
                        symbol=str(row["symbol"]),
                        date=d if isinstance(d, date) else None,
                        issue_code="impossible_return",
                        raw_values=str({"close": row["close"], "ret": float(rets.loc[idx])}),
                        resolution="flagged_kept",
                    )
                )
    return clean.reset_index(drop=True), issues


def write_quality_issues(issues: list[QualityIssue], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(i) for i in issues]
    pd.DataFrame(rows).to_csv(path, index=False)
