#!/usr/bin/env python3
"""Score predefined vol trade packages from IV–RV / surface features.

Research-only: auto_trade is always false. Deterministic rule scores so the
desk can show relative-value context beside directional options_picker.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from features_vrp import build_features  # noqa: E402

# Half-spread + hedge friction proxy in vol points (e.g. 1.5 vol pts)
DEFAULT_COST_PROXY = 0.015
# Require IV–RV beyond cost before "consider"
EDGE_BUFFER = 0.005


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


def _action(score: float, edge: float) -> str:
    if math.isnan(edge) or edge <= 0:
        return "stand_aside"
    if score >= 0.55 and edge > EDGE_BUFFER:
        return "consider"
    if score < 0.25:
        return "avoid"
    return "stand_aside"


def score_packages(
    features: Dict[str, Any],
    *,
    cost_proxy: float = DEFAULT_COST_PROXY,
) -> List[Dict[str, Any]]:
    """Return scored templates from a features_vrp row."""
    iv_rv = _f(features.get("iv_rv_spread"))
    term = _f(features.get("term_slope"))
    skew = _f(features.get("skew_25d"))
    rv = _f(features.get("rv_har_ann"))
    quality = str(features.get("data_quality") or "degraded")

    packages: List[Dict[str, Any]] = []

    # 1) Long vol when IV cheap vs HAR-RV (negative spread after costs)
    #    Short vol when IV rich (positive spread after costs)
    # Convention: iv_rv_spread = atm_iv - rv_har  → positive = expensive IV
    if not math.isnan(iv_rv):
        long_edge = (-iv_rv) - cost_proxy  # want IV < RV
        short_edge = iv_rv - cost_proxy  # want IV > RV
        long_score = max(0.0, min(1.0, 0.5 + (-iv_rv) * 5.0))
        short_score = max(0.0, min(1.0, 0.5 + iv_rv * 5.0))
        packages.append(
            {
                "template": "delta_neutral_long_vol",
                "score": round(long_score, 4),
                "edge_after_cost_proxy": round(long_edge, 4),
                "action": _action(long_score, long_edge),
                "reasons": [
                    f"iv_rv_spread={iv_rv:.4f} (atm_iv - har_rv)",
                    f"long_vol_edge≈{-iv_rv:.4f} - cost {cost_proxy}",
                ],
            }
        )
        packages.append(
            {
                "template": "delta_neutral_short_vol",
                "score": round(short_score, 4),
                "edge_after_cost_proxy": round(short_edge, 4),
                "action": _action(short_score, short_edge),
                "reasons": [
                    f"iv_rv_spread={iv_rv:.4f}",
                    f"short_vol_edge≈{iv_rv:.4f} - cost {cost_proxy}",
                    "short premium blocked on $1k books — research only",
                ],
            }
        )
    else:
        packages.append(
            {
                "template": "delta_neutral_long_vol",
                "score": 0.0,
                "edge_after_cost_proxy": float("nan"),
                "action": "stand_aside",
                "reasons": ["missing iv_rv_spread"],
            }
        )

    # 2) Calendar: prefer long further / short near when contango (positive slope)
    if not math.isnan(term):
        # Positive term slope → sell near / buy far calendar carry (simplified)
        cal_edge = abs(term) - cost_proxy * 0.5
        cal_score = max(0.0, min(1.0, 0.5 + abs(term) * 8.0))
        packages.append(
            {
                "template": "calendar_roll_down",
                "score": round(cal_score, 4),
                "edge_after_cost_proxy": round(cal_edge if abs(term) > cost_proxy * 0.5 else -abs(cost_proxy), 4),
                "action": _action(cal_score, term - cost_proxy * 0.5 if term > 0 else -term - cost_proxy * 0.5),
                "reasons": [
                    f"term_slope_per_30d={term:.4f}",
                    "positive slope → contango calendar research template",
                ],
            }
        )

    # 3) Skew / put-wing richness (positive skew_proxy = put IV > call IV at wings)
    if not math.isnan(skew):
        # Rich put wing → consider put-spread credit / RR — research only
        skew_edge = abs(skew) - cost_proxy
        skew_score = max(0.0, min(1.0, 0.45 + abs(skew) * 4.0))
        packages.append(
            {
                "template": "skew_risk_reversal",
                "score": round(skew_score, 4),
                "edge_after_cost_proxy": round(skew_edge, 4),
                "action": _action(skew_score, skew_edge),
                "reasons": [
                    f"skew_proxy={skew:.4f} (otm put IV - otm call IV)",
                    "structure mapping deferred to Phase 2",
                ],
            }
        )

    # Degrade all to stand_aside if data quality is bad
    if quality == "degraded":
        for p in packages:
            p["action"] = "stand_aside"
            p["reasons"] = list(p.get("reasons") or []) + ["data_quality=degraded"]
            p["score"] = min(float(p.get("score") or 0), 0.35)

    # High RV regime caution for short vol
    if not math.isnan(rv) and rv > 0.35:
        for p in packages:
            if p["template"] == "delta_neutral_short_vol":
                p["action"] = "avoid"
                p["reasons"] = list(p.get("reasons") or []) + [f"elevated_rv_har={rv:.2f}"]

    return packages


def build_warnings(features: Dict[str, Any], packages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Human-readable desk warnings from live chain flow + price action.

    Severity: info | watch | danger
    """
    warnings: List[Dict[str, str]] = []
    quality = str(features.get("data_quality") or "degraded")
    iv_rv = _f(features.get("iv_rv_spread"))
    term = _f(features.get("term_slope"))
    skew = _f(features.get("skew_25d"))
    rv = _f(features.get("rv_har_ann"))
    atm = _f(features.get("atm_iv"))
    pc_vol = _f(features.get("put_call_vol_ratio"))
    pc_oi = _f(features.get("put_call_oi_ratio"))
    put_vol = _f(features.get("put_volume"))
    call_vol = _f(features.get("call_volume"))
    ret_5d = _f(features.get("spot_ret_5d"))
    ret_1d = _f(features.get("spot_ret_1d"))

    if quality == "degraded":
        warnings.append({
            "severity": "watch",
            "code": "degraded_data",
            "message": "Chain/surface data degraded — treat all package scores as low confidence.",
        })

    # Puts stacking while stock climbs → dump risk
    climbing = (not math.isnan(ret_5d) and ret_5d >= 0.02) or (not math.isnan(ret_1d) and ret_1d >= 0.01)
    puts_heavy_vol = (not math.isnan(pc_vol) and pc_vol >= 1.25) or (
        not math.isnan(put_vol) and not math.isnan(call_vol) and put_vol > call_vol * 1.25 and put_vol > 0
    )
    puts_heavy_oi = not math.isnan(pc_oi) and pc_oi >= 1.35
    if climbing and (puts_heavy_vol or puts_heavy_oi):
        bits = []
        if not math.isnan(ret_5d):
            bits.append(f"spot +{ret_5d*100:.1f}% over ~5 sessions")
        elif not math.isnan(ret_1d):
            bits.append(f"spot +{ret_1d*100:.1f}% today")
        if puts_heavy_vol and not math.isnan(pc_vol):
            bits.append(f"put/call volume {pc_vol:.2f}x")
        if puts_heavy_oi and not math.isnan(pc_oi):
            bits.append(f"put/call OI {pc_oi:.2f}x")
        warnings.append({
            "severity": "danger",
            "code": "puts_stacking_on_climb",
            "message": "Puts stacking while stock climbs — dump / hedge risk. " + "; ".join(bits),
        })
    elif puts_heavy_vol and not climbing:
        msg = "Heavy put volume vs calls"
        if not math.isnan(pc_vol):
            msg += f" (P/C vol {pc_vol:.2f}x)"
        msg += " — downside demand elevated."
        warnings.append({"severity": "watch", "code": "put_volume_heavy", "message": msg})

    # Calls stacking into strength can be chase risk or squeeze fuel
    calls_heavy = not math.isnan(pc_vol) and pc_vol > 0 and pc_vol <= 0.65
    if calls_heavy and climbing:
        warnings.append({
            "severity": "info",
            "code": "calls_stacking_on_climb",
            "message": f"Calls dominating volume (P/C {pc_vol:.2f}x) into a climb — chase / squeeze dynamics, not a free ride.",
        })

    # Stock climbing into rich IV
    if climbing and not math.isnan(iv_rv) and iv_rv >= 0.04:
        warnings.append({
            "severity": "watch",
            "code": "rich_iv_on_climb",
            "message": f"IV rich vs realized (+{iv_rv*100:.1f} vol pts) while price is up — long premium can get crushed if the move stalls.",
        })

    # Stock dumping with cheap IV
    dumping = (not math.isnan(ret_5d) and ret_5d <= -0.03) or (not math.isnan(ret_1d) and ret_1d <= -0.015)
    if dumping and not math.isnan(iv_rv) and iv_rv <= -0.03:
        warnings.append({
            "severity": "info",
            "code": "cheap_iv_on_dump",
            "message": f"IV cheap vs realized ({iv_rv*100:.1f} pts) into weakness — vol may reprice higher if selling continues.",
        })

    if not math.isnan(skew) and skew >= 0.06:
        warnings.append({
            "severity": "watch",
            "code": "put_wing_rich",
            "message": f"Put wing rich vs calls (skew {skew*100:.1f} vol pts) — tail hedge demand is elevated.",
        })

    if not math.isnan(term) and term <= -0.03:
        warnings.append({
            "severity": "watch",
            "code": "backwardation",
            "message": f"Near-term IV elevated vs next (term slope {term*100:.1f} pts/30d) — event/fear premium in front month.",
        })

    if not math.isnan(rv) and rv >= 0.40:
        warnings.append({
            "severity": "watch",
            "code": "elevated_realized_vol",
            "message": f"Realized vol hot (HAR ~{rv*100:.0f}%) — size down; short-vol templates avoided.",
        })

    if not math.isnan(atm) and not math.isnan(rv) and not math.isnan(iv_rv):
        if abs(iv_rv) < 0.01:
            warnings.append({
                "severity": "info",
                "code": "iv_rv_aligned",
                "message": f"ATM IV (~{atm*100:.0f}%) roughly matches realized (~{rv*100:.0f}%) — no fat IV–RV edge after costs.",
            })

    # Sort danger first
    order = {"danger": 0, "watch": 1, "info": 2}
    warnings.sort(key=lambda w: order.get(w.get("severity", "info"), 9))
    return warnings


def pick_recommended(packages: List[Dict[str, Any]]) -> Dict[str, Any]:
    consider = [p for p in packages if p.get("action") == "consider"]
    if not consider:
        return {
            "template": "stand_aside",
            "action": "stand_aside",
            "score": 0.0,
            "edge_after_cost_proxy": 0.0,
            "reasons": ["no package cleared cost proxy / quality gates"],
        }
    best = max(consider, key=lambda p: (float(p.get("edge_after_cost_proxy") or -1e9), float(p.get("score") or 0)))
    # Never recommend short vol as primary for desk default capital
    if best.get("template") == "delta_neutral_short_vol":
        alt = [p for p in consider if p.get("template") != "delta_neutral_short_vol"]
        if alt:
            best = max(alt, key=lambda p: float(p.get("edge_after_cost_proxy") or -1e9))
        else:
            return {
                "template": "stand_aside",
                "action": "stand_aside",
                "score": 0.0,
                "edge_after_cost_proxy": 0.0,
                "reasons": ["only short-vol cleared; blocked for default desk capital"],
            }
    return {
        "template": best["template"],
        "action": best["action"],
        "score": best.get("score"),
        "edge_after_cost_proxy": best.get("edge_after_cost_proxy"),
        "reasons": best.get("reasons") or [],
    }


def score_symbol(
    symbol: str,
    *,
    surface: Optional[Dict[str, Any]] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    fetch_surface: bool = True,
    cost_proxy: float = DEFAULT_COST_PROXY,
    max_risk_pct: float = 0.18,
) -> Dict[str, Any]:
    feats = build_features(
        symbol,
        surface=surface,
        cache_dir=cache_dir,
        fetch_surface=fetch_surface,
    )
    packages = score_packages(feats, cost_proxy=cost_proxy)
    rec = pick_recommended(packages)
    warnings = build_warnings(feats, packages)
    return {
        "ok": True,
        "symbol": feats.get("symbol") or symbol.upper().replace(".US", ""),
        "features": feats,
        "packages": packages,
        "recommended": rec,
        "warnings": warnings,
        "guardrails": {
            "max_risk_pct": max_risk_pct,
            "cost_proxy_vol": cost_proxy,
            "research_only": True,
            "auto_trade": False,
            "does_not_set_options_attack": True,
        },
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: Optional[list] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Vol package scorer (research)")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--no-surface", action="store_true")
    p.add_argument("--cache-dir", default=None)
    p.add_argument("--cost-proxy", type=float, default=DEFAULT_COST_PROXY)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        out = score_symbol(
            args.symbol,
            cache_dir=args.cache_dir,
            fetch_surface=not args.no_surface,
            cost_proxy=args.cost_proxy,
        )
    except Exception as e:
        print(json.dumps(_jsonable({"ok": False, "error": str(e)}), default=str))
        return 1
    print(json.dumps(_jsonable(out), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
