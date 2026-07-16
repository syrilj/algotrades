#!/usr/bin/env python3
"""HAR-RV (Corsi-style) realized-volatility baselines from OHLCV bars.

Contract: pure functions over a price series → annualized RV estimates.
No network I/O. Used by features_vrp and vol_package_score.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data_cache" / "1d"

# US equity trading days for annualization of daily RV
_ANN_DAYS = 252.0


def _jsonable(obj):
    """Convert NaN/Inf to None for strict JSON (desk parse safety)."""
    import math
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj



def log_returns(close: pd.Series) -> pd.Series:
    c = pd.to_numeric(close, errors="coerce").astype(float)
    return np.log(c / c.shift(1)).replace([np.inf, -np.inf], np.nan)


def realized_var(returns: pd.Series, window: int) -> pd.Series:
    """Rolling sum of squared returns (variance units, not annualized)."""
    r = returns.astype(float)
    return (r * r).rolling(window, min_periods=max(2, window // 2)).sum()


def har_components(close: pd.Series) -> pd.DataFrame:
    """Daily / weekly / monthly RV components (annualized vol units).

    RV_d  ≈ sqrt(sum r^2 over 1d) * sqrt(252)
    RV_w  ≈ sqrt(sum r^2 over 5d / 5) * sqrt(252)
    RV_m  ≈ sqrt(sum r^2 over 21d / 21) * sqrt(252)

    HAR forecast uses the three levels as a persistence stack.
    """
    r = log_returns(close)
    out = pd.DataFrame(index=close.index)
    # 1-day realized vol (noisy)
    out["rv_1d"] = (r * r).clip(lower=0).pow(0.5) * np.sqrt(_ANN_DAYS)
    out["rv_5d"] = realized_var(r, 5).div(5.0).clip(lower=0).pow(0.5) * np.sqrt(_ANN_DAYS)
    out["rv_21d"] = realized_var(r, 21).div(21.0).clip(lower=0).pow(0.5) * np.sqrt(_ANN_DAYS)
    # Simple HAR blend (equal weight of d/w/m when available)
    out["rv_har"] = out[["rv_1d", "rv_5d", "rv_21d"]].mean(axis=1, skipna=True)
    return out


def latest_har(close: pd.Series) -> Dict[str, float]:
    """Point estimate from the last valid bar."""
    comps = har_components(close)
    row = comps.dropna(how="all").iloc[-1] if len(comps.dropna(how="all")) else None
    if row is None:
        return {
            "rv_1d_ann": float("nan"),
            "rv_5d_ann": float("nan"),
            "rv_21d_ann": float("nan"),
            "rv_har_ann": float("nan"),
            "n_bars": int(len(close)),
        }
    return {
        "rv_1d_ann": float(row["rv_1d"]) if pd.notna(row["rv_1d"]) else float("nan"),
        "rv_5d_ann": float(row["rv_5d"]) if pd.notna(row["rv_5d"]) else float("nan"),
        "rv_21d_ann": float(row["rv_21d"]) if pd.notna(row["rv_21d"]) else float("nan"),
        "rv_har_ann": float(row["rv_har"]) if pd.notna(row["rv_har"]) else float("nan"),
        "n_bars": int(len(close)),
    }


def load_close(
    symbol: str,
    cache_dir: Optional[Union[str, Path]] = None,
) -> pd.Series:
    """Load close from data_cache/1d/<SYM>.parquet (strip .US)."""
    sym = symbol.upper().replace(".US", "")
    base = Path(cache_dir) if cache_dir else DEFAULT_CACHE
    path = base / f"{sym}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"missing bars: {path}")
    df = pd.read_parquet(path)
    if "close" not in df.columns:
        raise ValueError(f"{path} has no close column")
    s = df["close"].astype(float)
    s.index = pd.to_datetime(df.index)
    s = s.sort_index()
    return s


def har_for_symbol(
    symbol: str,
    cache_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    close = load_close(symbol, cache_dir=cache_dir)
    out = latest_har(close)
    out["symbol"] = symbol.upper().replace(".US", "")
    out["asof"] = close.index[-1].isoformat() if len(close) else None
    out["spot"] = float(close.iloc[-1]) if len(close) else float("nan")
    return out


def main(argv: Optional[list] = None) -> int:
    import argparse
    import json

    p = argparse.ArgumentParser(description="HAR-RV from local daily bars")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        row = har_for_symbol(args.symbol, cache_dir=args.cache_dir)
    except Exception as e:
        print(json.dumps(_jsonable({"ok": False, "error": str(e)}), default=str))
        return 1
    row["ok"] = True
    print(json.dumps(_jsonable(row), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
