#!/usr/bin/env python3
"""Matched-horizon IV–RV feature join for options/vol research.

Joins:
  - HAR-RV from local daily bars (rv_har)
  - Live (or injected) surface ATM IV / term / skew (options_surface)

Writes optional parquet for SPY/QQQ research bags.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from options_surface import fetch_live_surface  # noqa: E402
from rv_har import har_for_symbol  # noqa: E402

DEFAULT_OUT = ROOT / "runs" / "options_vrp_v1" / "features"


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



def _f(x: Any) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return float("nan")
        return v
    except Exception:
        return float("nan")


def build_features(
    symbol: str,
    *,
    surface: Optional[Dict[str, Any]] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    fetch_surface: bool = True,
) -> Dict[str, Any]:
    """Return a single feature row for `symbol`."""
    sym = symbol.upper().replace(".US", "")
    reasons: List[str] = []
    quality = "ok"

    try:
        har = har_for_symbol(sym, cache_dir=cache_dir)
    except Exception as e:
        har = {
            "ok": False,
            "symbol": sym,
            "error": str(e),
            "rv_har_ann": float("nan"),
            "rv_5d_ann": float("nan"),
            "rv_21d_ann": float("nan"),
            "spot": float("nan"),
        }
        reasons.append(f"har_failed:{e}")
        quality = "degraded"

    if surface is None and fetch_surface:
        try:
            surface = fetch_live_surface(sym)
        except Exception as e:
            surface = {
                "ok": False,
                "data_quality": "degraded",
                "error": str(e),
                "atm_iv": float("nan"),
                "term_slope": float("nan"),
                "skew_25d": float("nan"),
            }
            reasons.append(f"surface_failed:{e}")
            quality = "degraded"
    elif surface is None:
        surface = {
            "ok": False,
            "data_quality": "degraded",
            "error": "surface not provided",
            "atm_iv": float("nan"),
            "term_slope": float("nan"),
            "skew_25d": float("nan"),
        }
        reasons.append("surface_skipped")
        quality = "partial" if quality == "ok" else quality

    atm_iv = _f(surface.get("atm_iv"))
    rv = _f(har.get("rv_har_ann"))
    rv_5 = _f(har.get("rv_5d_ann"))
    rv_21 = _f(har.get("rv_21d_ann"))
    iv_rv = atm_iv - rv if not (math.isnan(atm_iv) or math.isnan(rv)) else float("nan")

    sq = str(surface.get("data_quality") or "degraded")
    if sq == "degraded" or not surface.get("ok"):
        # Missing surface alone is partial (HAR may still be good); hard only if HAR also failed.
        if quality == "ok":
            quality = "partial"
        if surface.get("error") and surface.get("error") not in reasons:
            reasons.append(str(surface["error"]))
    elif sq == "partial" and quality == "ok":
        quality = "partial"

    spot = _f(surface.get("spot"))
    if math.isnan(spot):
        spot = _f(har.get("spot"))

    row: Dict[str, Any] = {
        "ok": quality != "degraded" or not math.isnan(rv),
        "symbol": sym,
        "asof": har.get("asof"),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "spot": spot,
        "rv_har_ann": rv,
        "rv_5d_ann": rv_5,
        "rv_21d_ann": rv_21,
        "atm_iv": atm_iv,
        "iv_rv_spread": iv_rv,
        "term_slope": _f(surface.get("term_slope")),
        "skew_25d": _f(surface.get("skew_25d")),
        "near_dte": surface.get("near_dte"),
        "next_dte": surface.get("next_dte"),
        "call_volume": _f(surface.get("call_volume")) if surface.get("call_volume") is not None else 0.0,
        "put_volume": _f(surface.get("put_volume")) if surface.get("put_volume") is not None else 0.0,
        "call_oi": _f(surface.get("call_oi")) if surface.get("call_oi") is not None else 0.0,
        "put_oi": _f(surface.get("put_oi")) if surface.get("put_oi") is not None else 0.0,
        "put_call_vol_ratio": _f(surface.get("put_call_vol_ratio")),
        "put_call_oi_ratio": _f(surface.get("put_call_oi_ratio")),
        "spot_ret_1d": _f(surface.get("spot_ret_1d")),
        "spot_ret_5d": _f(surface.get("spot_ret_5d")),
        "data_quality": quality,
        "reasons": reasons,
        "surface_ok": bool(surface.get("ok")),
        "har_n_bars": har.get("n_bars"),
    }
    return row


def build_bag(
    symbols: Sequence[str] = ("SPY", "QQQ"),
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    return [build_features(s, **kwargs) for s in symbols]


def write_features(
    rows: Sequence[Dict[str, Any]],
    out_dir: Union[str, Path] = DEFAULT_OUT,
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(list(rows))
    path = out / "features_latest.parquet"
    df.to_parquet(path, index=False)
    meta = {
        "n": len(df),
        "symbols": df["symbol"].tolist() if "symbol" in df.columns else [],
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "path": str(path),
    }
    (out / "STATE.json").write_text(json.dumps(meta, indent=2))
    return path


def main(argv: Optional[list] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="IV–RV feature matrix")
    p.add_argument("--symbols", default="SPY,QQQ")
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--no-surface", action="store_true", help="HAR only (offline)")
    p.add_argument("--write", action="store_true")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    rows = build_bag(
        syms,
        cache_dir=args.cache_dir,
        fetch_surface=not args.no_surface,
    )
    path = None
    if args.write:
        path = write_features(rows, out_dir=args.out_dir)
    payload = {
        "ok": True,
        "rows": rows,
        "written": str(path) if path else None,
    }
    print(json.dumps(_jsonable(payload), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
