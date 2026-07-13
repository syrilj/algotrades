#!/usr/bin/env python3
"""Feedback loop: Arete overlay variants on v39b base.

Runs v39b_live_adapt and v40_arete_pro variants with different Arete
weightings, then writes a leaderboard and a JSON state file.

Usage:
    .venv/bin/python tools/feedback_loop_arete.py --cash 1000 --workers 1
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dynamic_model_rank as dmr

ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"

# Match the v39b WINNER bag plus Arete context tickers.
EQUITY_WINNER_BAG = [
    "TSLA.US",
    "MU.US",
    "SPY.US",
    "IONQ.US",
    "APLD.US",
    "XLP.US",
    "QQQ.US",
]

# Optional extra context tickers (Arete overlays will use them if present).
ARETE_CONTEXT = [
    "SMH.US",
    "SOXL.US",
    "VXX.US",
    "IWM.US",
]

CODES = EQUITY_WINNER_BAG
TAG = "winners_bag"

START = "2024-08-01"
END = "2026-07-11"

OUT = ROOT / "runs" / "feedback_loop_arete"

# Promotion gates: a variant must pass absolute thresholds AND beat the
# baseline on a multi-lock set of metrics before it is allowed to replace
# v39b as the live champion.
PROMOTION_GATES = {
    "min_n": 10,
    "min_ret": 0.0,
    "max_abs_dd": 0.25,
    "min_sharpe": 1.0,
    "min_wr": 0.55,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_signal_engine(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "signal_engine.py", dst_dir / "signal_engine.py")


def _make_variant_model(
    v40_dir: Path,
    variant_id: str,
    hunt_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Create a temp src_dir with a patched hunt_config for one variant."""
    tmp = Path(tempfile.mkdtemp(prefix=f"v40_arete_{variant_id}_", dir=OUT))
    _copy_signal_engine(v40_dir, tmp)

    base_hunt = json.loads((v40_dir / "hunt_config.json").read_text())
    base_hunt.update(hunt_overrides)
    (tmp / "hunt_config.json").write_text(json.dumps(base_hunt, indent=2))

    return {
        "id": variant_id,
        "src_dir": tmp,
        "model_dir": v40_dir,
        "interval": "1H",
        "has_hunt": True,
    }


def _run_model(model: dict[str, Any], cash: float, tag: str) -> dict[str, Any]:
    return dmr.run_one(
        model,
        mode="daily",
        codes=CODES,
        start=START,
        end=END,
        tag=tag or TAG,
        force_1d=False,
        reuse=True,
        cash=cash,
    )


def _fmt(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"{row['id']:36} FAIL {row['error'][:80]}"
    return (
        f"{row['id']:36} ret={row['ret']*100:7.1f}% "
        f"dd={abs(row['dd'])*100:6.1f}% "
        f"sharpe={row['sharpe']:5.2f} "
        f"n={row['n']:3d} wr={row['wr']*100:4.0f}% "
        f"final=${row['final_at_cash']:>10,.2f}"
    )


def passes_promotion_gates(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    """Multi-lock promotion: absolute thresholds + beat baseline on risk-adjusted axes.

    A variant must:
      - have enough trades and acceptable absolute risk/reward
      - beat the baseline on total return, Sharpe, and not be worse on drawdown
    """
    if candidate.get("error") or baseline.get("error"):
        return False
    if int(candidate.get("n", 0)) < PROMOTION_GATES["min_n"]:
        return False
    if float(candidate.get("ret", 0.0)) < PROMOTION_GATES["min_ret"]:
        return False
    if abs(float(candidate.get("dd", 0.0))) > PROMOTION_GATES["max_abs_dd"]:
        return False
    if float(candidate.get("sharpe", 0.0)) < PROMOTION_GATES["min_sharpe"]:
        return False
    if float(candidate.get("wr", 0.0)) < PROMOTION_GATES["min_wr"]:
        return False

    # Multi-lock: candidate must be strictly better than baseline where it counts
    # and not materially worse on drawdown.
    ret_ok = float(candidate["ret"]) > float(baseline["ret"])
    sharpe_ok = float(candidate["sharpe"]) > float(baseline["sharpe"])
    dd_ok = abs(float(candidate["dd"])) <= abs(float(baseline["dd"])) + 0.02
    return ret_ok and sharpe_ok and dd_ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cash", type=float, default=1000.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--quick", action="store_true", help="Run only v39b baseline and v40 full variant")
    args = parser.parse_args()

    cash = args.cash
    OUT.mkdir(parents=True, exist_ok=True)

    v40_dir = MODELS_ROOT / "v40_arete_pro"
    if not v40_dir.exists():
        raise FileNotFoundError(f"v40 model not found: {v40_dir}")

    # Discover v39b baseline.
    v39b_models = dmr.discover_models(only=["v39b_live_adapt"])
    if not v39b_models:
        raise FileNotFoundError("v39b_live_adapt not found")
    v39b = v39b_models[0]

    # Define Arete overlay variants.
    if args.quick:
        variants = [
            _make_variant_model(v40_dir, "v40_arete_pro", {}),
        ]
    else:
        variants = [
            _make_variant_model(v40_dir, "v40_arete_pro", {}),
            _make_variant_model(v40_dir, "v40_ma_only", {
                "enable_fib": False,
                "enable_sox": False,
                "enable_vix": False,
                "enable_rs": False,
                "enable_vol": False,
            }),
            _make_variant_model(v40_dir, "v40_ma_fib", {
                "enable_sox": False,
                "enable_vix": False,
                "enable_rs": False,
                "enable_vol": False,
            }),
            _make_variant_model(v40_dir, "v40_no_sox", {
                "enable_sox": False,
            }),
            _make_variant_model(v40_dir, "v40_no_vix", {
                "enable_vix": False,
            }),
            _make_variant_model(v40_dir, "v40_no_rs", {
                "enable_rs": False,
            }),
            _make_variant_model(v40_dir, "v40_no_vol", {
                "enable_vol": False,
            }),
        ]

    print(f"[arete-feedback] cash=${cash:,.0f} codes={len(CODES)}", flush=True)
    rows: list[dict[str, Any]] = []

    # Baseline v39b.
    print("[arete-feedback] baseline v39b_live_adapt", flush=True)
    rows.append(_run_model(v39b, cash, TAG))
    print(f"  {_fmt(rows[-1])}", flush=True)

    # Variants.
    for m in variants:
        print(f"[arete-feedback] variant {m['id']}", flush=True)
        r = _run_model(m, cash, TAG)
        print(f"  {_fmt(r)}", flush=True)
        rows.append(r)

    # Rank by risk-adjusted score (ret/dd) with small-n penalty.
    ranked = []
    for r in rows:
        if r.get("error") or r.get("n", 0) == 0:
            score = -9.0
        else:
            ret = float(r["ret"])
            dd = max(abs(float(r["dd"])), 0.02)
            sh = float(r["sharpe"])
            n = int(r["n"])
            n_pen = 0.0 if n >= 10 else 0.25
            score = (ret / dd) + 0.15 * min(sh, 3.0) - n_pen
        r["score"] = score
        ranked.append(r)

    ranked.sort(key=lambda x: x["score"], reverse=True)

    baseline_result = next((r for r in ranked if r["id"] == v39b["id"]), ranked[0] if ranked else {})
    promoted = [r for r in ranked if passes_promotion_gates(r, baseline_result)]
    promoted_best = promoted[0] if promoted else None

    state = {
        "timestamp": _now(),
        "cash": cash,
        "codes": CODES,
        "start": START,
        "end": END,
        "ranking": ranked,
        "best": ranked[0]["id"] if ranked else None,
        "promoted": [r["id"] for r in promoted],
        "promoted_best": promoted_best["id"] if promoted_best else None,
        "promotion_gates": PROMOTION_GATES,
    }

    (OUT / "STATE.json").write_text(json.dumps(state, indent=2, default=str))

    lines = ["# Arete feedback loop leaderboard\n", f"- cash: ${cash:,.0f}\n", f"- period: {START} to {END}\n", f"- promoted: {len(promoted)} variant(s)\n", ""]
    lines.append("| model | ret | dd | sharpe | n | wr | final | score | promoted |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in ranked:
        is_promoted = any(r["id"] == p["id"] for p in promoted)
        promo = "YES" if is_promoted else ""
        if r.get("error"):
            lines.append(f"| {r['id']} | FAIL | {r.get('error','')[:40]} | | | | | | |")
        else:
            lines.append(
                f"| {r['id']} | {r['ret']*100:6.1f}% | {abs(r['dd'])*100:5.1f}% | "
                f"{r['sharpe']:4.2f} | {r['n']} | {r['wr']*100:3.0f}% | "
                f"${r['final_at_cash']:,.2f} | {r['score']:6.2f} | {promo} |"
            )
    (OUT / "LEADERBOARD.md").write_text("\n".join(lines))

    print(f"\n[arete-feedback] best: {state['best']}", flush=True)
    print(f"[arete-feedback] promoted: {state['promoted']}", flush=True)
    print(f"[arete-feedback] promoted_best: {state['promoted_best']}", flush=True)
    print(f"[arete-feedback] leaderboard: {OUT / 'LEADERBOARD.md'}", flush=True)


if __name__ == "__main__":
    main()
