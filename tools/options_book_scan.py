#!/usr/bin/env python3
"""Multi-symbol options book scan — structure + vol package + high-level read.

Fast path for the Options desk: compare several names side-by-side without
running full live_plan for every ticker. Research + structure proposal only;
never sets OPTIONS_ATTACK alone.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from options_picker import PREFERRED, propose, _norm_symbol  # noqa: E402

DEFAULT_BOOK = ["MSTR", "TSLA", "SKHY", "IONQ"]


def _jsonable(obj: Any) -> Any:
    """Recursively convert NaN/Inf and numpy scalars to strict JSON values."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, tuple):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if hasattr(obj, "dtype"):  # numpy scalar
        if obj.dtype.kind in "iub":  # integer / unsigned / boolean
            return int(obj)
        if obj.dtype.kind == "f":  # float
            v = float(obj)
            return None if math.isnan(v) or math.isinf(v) else v
    return obj


def _vol_package(symbol: str) -> dict:
    try:
        from vol_package_score import score_symbol

        return score_symbol(symbol)
    except Exception as e:
        return {"ok": False, "error": str(e), "recommended": None, "warnings": [], "features": {}}


def _flow_summary(symbol: str) -> dict:
    try:
        from options_unusual_flow import scan_symbol

        raw = scan_symbol(symbol, max_expiries=4, max_dte=45, top_n=8)
    except Exception as e:
        return {"ok": False, "error": str(e), "n_flagged": 0, "calls": 0, "puts": 0, "bias": "neutral"}

    if not isinstance(raw, dict):
        return {"ok": False, "error": "bad_flow_payload", "n_flagged": 0, "calls": 0, "puts": 0, "bias": "neutral"}
    flags = raw.get("flags") or raw.get("unusual") or []
    calls = sum(1 for f in flags if str(f.get("right", "")).upper() in ("C", "CALL"))
    puts = sum(1 for f in flags if str(f.get("right", "")).upper() in ("P", "PUT"))
    premium = sum(float(f.get("premium") or 0) for f in flags)
    bias = "neutral"
    if calls > puts * 1.5:
        bias = "bullish"
    elif puts > calls * 1.5:
        bias = "bearish"
    elif calls > puts:
        bias = "lean_bull"
    elif puts > calls:
        bias = "lean_bear"
    return {
        "ok": bool(raw.get("ok", True)),
        "n_flagged": len(flags),
        "calls": calls,
        "puts": puts,
        "premium": round(premium, 0),
        "bias": bias,
        "top": flags[:3] if flags else [],
        "asof_utc": raw.get("asof_utc"),
        "error": raw.get("error"),
    }


def _confidence_read(structure: dict, vol: dict, flow: dict) -> dict:
    """Heuristic high-level desk read — not a calibrated probability."""
    score = 0.0
    reasons: list[str] = []
    action = structure.get("action")
    if action == "buy":
        score += 0.35
        reasons.append("affordable defined-risk structure fits budget")
        max_loss = float(structure.get("max_loss_1_contract") or 0)
        budget = float(structure.get("budget") or 1)
        if budget > 0 and max_loss / budget <= 0.7:
            score += 0.1
            reasons.append("structure uses ≤70% of risk budget")
        ld = abs(float(structure.get("long_delta") or 0))
        if 0.28 <= ld <= 0.55:
            score += 0.1
            reasons.append(f"long delta in tradeable band ({ld:.2f})")
    elif action == "skip":
        score -= 0.15
        reasons.append(structure.get("reason") or "no affordable structure")
    else:
        score -= 0.2
        reasons.append(structure.get("error") or "structure unavailable")

    rec = (vol or {}).get("recommended") or {}
    vol_action = str(rec.get("action") or "stand_aside")
    if vol_action == "consider":
        score += 0.15
        reasons.append(f"vol package consider: {rec.get('template')}")
    elif vol_action == "avoid":
        score -= 0.1
        reasons.append(f"vol package avoid: {rec.get('template')}")

    for w in (vol or {}).get("warnings") or []:
        sev = str(w.get("severity") or "")
        if sev == "danger":
            score -= 0.2
            reasons.append(w.get("message") or w.get("code") or "vol danger")
        elif sev == "watch":
            score -= 0.05
            reasons.append(w.get("message") or w.get("code") or "vol watch")

    bias = (flow or {}).get("bias") or "neutral"
    if bias in ("bullish", "lean_bull") and action == "buy":
        score += 0.15
        reasons.append(f"flow bias {bias} supports long structure")
    elif bias in ("bearish", "lean_bear"):
        score -= 0.1
        reasons.append(f"flow bias {bias} — caution on long calls")

    # clamp
    score = max(0.0, min(1.0, score))
    if score >= 0.7:
        label = "HIGH"
        stance = "structure_ok_if_mode_attack"
    elif score >= 0.45:
        label = "MEDIUM"
        stance = "proposal_only"
    elif score >= 0.25:
        label = "LOW"
        stance = "stand_aside_bias"
    else:
        label = "AVOID"
        stance = "stand_aside"

    return {
        "score": round(score, 3),
        "label": label,
        "stance": stance,
        "reasons": reasons[:6],
    }


def _bounce_model_read(symbol: str, input_symbol: str) -> dict:
    """Optional v80 bounce certainty model (never raises)."""
    try:
        from bounce_predict import predict_symbol

        # Keep INFQ as stock unless the input already requested alias handling.
        apply_alias = False
        targets = {"TSLA": 397.5, "MSTR": 102.0, "SKHY": 180.0, "INFQ": 10.0, "IONQ": 40.0}
        tgt = targets.get(symbol) or targets.get(input_symbol)
        pred = predict_symbol(
            input_symbol if input_symbol else symbol,
            target_price=tgt,
            apply_desk_alias=apply_alias,
            enrich_live=False,
        )
        return {
            "ok": bool(pred.get("ok")),
            "direction": pred.get("direction"),
            "p_bounce": pred.get("p_bounce"),
            "p_target_hit": pred.get("p_target_hit"),
            "confidence_state": pred.get("confidence_state"),
            "abstain": pred.get("abstain"),
            "model_version": pred.get("model_version"),
            "symbol_resolution": pred.get("symbol_resolution"),
            "error": pred.get("error"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _scan_one(symbol: str, account: float, risk_pct: float) -> dict:
    # Preserve input for INFQ stock path; do not force IONQ alias for bounce model.
    input_sym = (symbol or "").upper().replace(".US", "")
    sym = _norm_symbol(symbol)
    structure = propose(sym, account=account, max_risk_pct=risk_pct)
    vol = _vol_package(sym)
    flow = _flow_summary(sym)
    conf = _confidence_read(structure, vol if isinstance(vol, dict) else {}, flow)
    bounce = _bounce_model_read(sym, input_sym)
    return {
        "symbol": sym,
        "input_symbol": input_sym,
        "structure": structure,
        "vol_package": {
            "ok": bool((vol or {}).get("ok", False)),
            "recommended": (vol or {}).get("recommended"),
            "warnings": (vol or {}).get("warnings") or [],
            "features": {
                k: (vol or {}).get("features", {}).get(k)
                for k in (
                    "atm_iv",
                    "rv_har_ann",
                    "iv_rv_spread",
                    "put_call_vol_ratio",
                    "spot_ret_5d",
                    "data_quality",
                )
            }
            if isinstance((vol or {}).get("features"), dict)
            else {},
            "error": (vol or {}).get("error"),
        },
        "unusual_flow": flow,
        "confidence_read": conf,
        "bounce_model": bounce,
        "preferred": sym in PREFERRED,
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


def scan_book(
    symbols: list[str] | None = None,
    account: float = 1000.0,
    risk_pct: float = 0.18,
    workers: int = 4,
) -> dict:
    raw_book = [_norm_symbol(s) for s in (symbols or DEFAULT_BOOK) if s]
    seen: set[str] = set()
    book: list[str] = []
    for s in raw_book:
        if s in seen:
            continue
        seen.add(s)
        book.append(s)
    if not book:
        book = list(DEFAULT_BOOK)

    rows: list[dict] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(book)))) as pool:
        futs = {pool.submit(_scan_one, s, account, risk_pct): s for s in book}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                rows.append(fut.result())
            except Exception as e:
                errors.append(f"{sym}: {e}")
                rows.append(
                    {
                        "symbol": sym,
                        "error": str(e),
                        "confidence_read": {
                            "score": 0.0,
                            "label": "AVOID",
                            "stance": "stand_aside",
                            "reasons": [str(e)],
                        },
                    }
                )

    # rank: HIGH score first, buy structures first
    def row_key(r: dict) -> tuple:
        conf = r.get("confidence_read") or {}
        st = (r.get("structure") or {}).get("action")
        return (
            0 if st == "buy" else 1,
            -float(conf.get("score") or 0),
            r.get("symbol") or "",
        )

    rows.sort(key=row_key)
    top = rows[0] if rows else None
    return {
        "ok": True,
        "account": account,
        "risk_pct": risk_pct,
        "book": book,
        "rows": rows,
        "best": top.get("symbol") if top else None,
        "n": len(rows),
        "errors": errors,
        "note": (
            "High-confidence read is a desk heuristic combining structure fit, "
            "vol package, and chain-proxy flow. It does not set OPTIONS_ATTACK; "
            "confirm on Live with equity/options risk mode."
        ),
        "asof_utc": datetime.now(timezone.utc).isoformat(),
    }


def main():
    ap = argparse.ArgumentParser(description="Multi-symbol options book scan")
    ap.add_argument(
        "--symbols",
        default=",".join(DEFAULT_BOOK),
        help="Comma-separated symbols (default MSTR,TSLA,SKHY,IONQ)",
    )
    ap.add_argument("--account", type=float, default=1000.0)
    ap.add_argument("--risk-pct", type=float, default=0.18)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    out = scan_book(
        symbols=symbols,
        account=args.account,
        risk_pct=args.risk_pct,
        workers=args.workers,
    )
    if args.json:
        print(json.dumps(_jsonable(out), indent=2, default=str))
    else:
        print(f"OPTIONS BOOK  n={out['n']}  best={out.get('best')}  account=${args.account:.0f}")
        for r in out["rows"]:
            conf = r.get("confidence_read") or {}
            st = r.get("structure") or {}
            print(
                f"  {r.get('symbol'):5s}  conf={conf.get('label','?'):6s} "
                f"({conf.get('score', 0):.2f})  "
                f"struct={st.get('action', '—')} "
                f"{st.get('structure') or st.get('reason') or st.get('error') or ''}"
            )
            if st.get("action") == "buy":
                print(
                    f"         exp={st.get('expiry')}  "
                    f"{st.get('long_strike')}/{st.get('short_strike')}  "
                    f"max_loss=${st.get('max_loss_1_contract')}"
                )


if __name__ == "__main__":
    main()
