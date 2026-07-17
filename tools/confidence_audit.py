#!/usr/bin/env python3
"""Historical confidence audit for promoted live equity paths.

Re-runs dual-sleeve / high-WR books on local adjusted data, inventories what
the money path looks at, and calibrates confidence vs outcomes with honest
floors (unreliable when n is thin). Never mutates promotion state.

Usage:
  .venv/bin/python tools/confidence_audit.py --cash 1000
  .venv/bin/python tools/confidence_audit.py --quick --cash 1000  # reuse frozen results.json metrics
  .venv/bin/python tools/confidence_audit.py --out-dir runs/confidence_audit/latest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Locked windows (v71/v72 freeze contract — do not invent look-ahead)
FULL_START = "2024-08-01"
FULL_END = "2026-07-11"
HOLDOUT_START = "2025-08-01"
HOLDOUT_END = "2026-07-11"
TRAIN_END = "2025-08-01"

DEFAULT_CASH = 1000.0
DEFAULT_INTERVAL = "1H"
DEFAULT_SOURCE = "local"
MIN_BUCKET_N = 8  # below this → unreliable for that bucket
MIN_CALIB_N = 20  # overall calibration table floor
MIN_CLAIM_TRADES = 40  # PASS_BAR claim floor

DEFAULT_OUT = ROOT / "runs" / "confidence_audit" / "latest"


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


# ---------------------------------------------------------------------------
# Inventory: what live money path looks at
# ---------------------------------------------------------------------------


def load_desk_routing(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or (ROOT / "models" / "poc_va_macdha" / "DESK_ROUTING.json")
    return json.loads(p.read_text(encoding="utf-8"))


def load_hunt(model_id: str) -> Dict[str, Any]:
    p = ROOT / "models" / "poc_va_macdha" / model_id / "hunt_config.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_pass_bar() -> Dict[str, Any]:
    p = ROOT / "models" / "_shared" / "PASS_BAR.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def build_live_inventory(routing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Document models, gates, confidence sources, data contracts for the money path."""
    routing = routing or load_desk_routing()
    v72_hunt = load_hunt("v72_dual_sleeve")
    v71_hunt = load_hunt("v71_live_confidence")
    v39d_hunt = load_hunt("v39d_confluence")
    pass_bar = load_pass_bar()

    dual = str(routing.get("dual_sleeve_equity") or "v72_dual_sleeve")
    high_wr = str(routing.get("high_wr_equity") or "v71_live_confidence")
    fallback = str(routing.get("fallback_equity") or "v39d_confluence")

    inventory = {
        "schema_version": "confidence-audit-inventory-v1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "money_path": {
            "preferred_combined_book": dual,
            "high_wr_sleeve": high_wr,
            "fallback_equity": fallback,
            "fallback_equity_alt": routing.get("fallback_equity_alt"),
            "routing_mode": routing.get("routing_mode"),
            "note_sleeves": routing.get("note_sleeves"),
        },
        "models_routed": {
            dual: {
                "role": "combined_live_book",
                "sniper": v72_hunt.get("sniper_model", "v71_live_confidence"),
                "core": v72_hunt.get("core_model", "v39d_confluence"),
                "core_scale": v72_hunt.get("core_scale"),
                "both_core_frac": v72_hunt.get("both_core_frac"),
                "max_weight": v72_hunt.get("max_weight"),
                "selection_rule": v72_hunt.get("selection_rule"),
                "train_window_end": v72_hunt.get("train_window_end", TRAIN_END),
                "confidence_source": "engine_last_confidence",
                "merge_rule": "hierarchical_sniper_then_core_no_averaging",
            },
            high_wr: {
                "role": "high_wr_confidence_sleeve",
                "primary": v71_hunt.get("primary") or (v71_hunt.get("base_models") or ["v45_ultimate_rsi"])[0],
                "trend_filter": v71_hunt.get("trend_filter"),
                "quality": v71_hunt.get("quality"),
                "confidence": v71_hunt.get("confidence"),
                "signal_scale": v71_hunt.get("signal_scale"),
                "max_scale_cap": v71_hunt.get("max_scale_cap"),
                "variant_id": v71_hunt.get("variant_id"),
                "selection_rule": v71_hunt.get("selection_rule"),
                "train_window_end": v71_hunt.get("train_window_end", TRAIN_END),
                "confidence_source": "engine_last_confidence",
            },
            fallback: {
                "role": "core_return_champion_fallback",
                "confidence_source": "meta_proba_or_calibrator_when_active",
                "calibrator_path": "runs/calibration/active/v39d_confluence.json",
                "notes": "Specialists (v65_spec_*) inherit v39d DNA; desk competitive_best may pick specialists per symbol.",
            },
        },
        "data_contract": {
            "source": DEFAULT_SOURCE,
            "interval": DEFAULT_INTERVAL,
            "full_window": {"start": FULL_START, "end": FULL_END},
            "holdout_window": {"start": HOLDOUT_START, "end": HOLDOUT_END},
            "train_select_end": TRAIN_END,
            "holdout_retune_forbidden": True,
            "bag": "EQUITY_WINNER_BAG",
        },
        "gates": {
            "pass_bar": pass_bar.get("gates"),
            "claim_levels": pass_bar.get("claim_levels"),
            "live_runtime": {
                "confidence_states": ["ENTER", "WATCH", "ABSTAIN"],
                "missing_calibrator": "ABSTAIN fail-closed",
                "sizing": "bounded_execution_risk hard caps after adapt * confidence_size_limit",
            },
        },
        "explicitly_not_money_path": {
            "options_vol_package_score": {
                "module": "tools/vol_package_score.py",
                "auto_trade": False,
                "research_only": True,
                "reason": "No multi-year package PnL warehouse; live chain warnings are point-in-time only.",
            },
            "gex_live_only": {
                "may_auto_promote": False,
                "reason": "PASS_BAR data track gex_live_only",
            },
        },
        "specialists_note": "DESK_ROUTING.by_symbol maps many tickers to v65_spec_*; dna_edge true only when bakeoff multi-locked. Combined book audit uses EQUITY_WINNER_BAG on dual_sleeve/high_wr, not the full specialist map.",
    }
    return inventory


# ---------------------------------------------------------------------------
# Metrics packing
# ---------------------------------------------------------------------------


REQUIRED_METRIC_KEYS = ("ret", "dd", "sharpe", "n", "wr", "final")


def pack_window_metrics(
    row: Dict[str, Any],
    *,
    window: str,
    start: str,
    end: str,
    cash: float,
) -> Dict[str, Any]:
    """Normalize dmr/results rows into a stable audit metric block."""
    ret = row.get("ret", row.get("total_return"))
    dd = row.get("dd", row.get("max_drawdown"))
    sharpe = row.get("sharpe")
    n = row.get("n", row.get("trade_count"))
    wr = row.get("wr", row.get("win_rate"))
    final = row.get("final", row.get("final_value"))
    out = {
        "window": window,
        "start": start,
        "end": end,
        "cash": float(cash),
        "ret": float(ret) if ret is not None else None,
        "dd": float(dd) if dd is not None else None,
        "sharpe": float(sharpe) if sharpe is not None else None,
        "n": int(n) if n is not None else None,
        "wr": float(wr) if wr is not None else None,
        "final": float(final) if final is not None else None,
        "path": row.get("path"),
        "reused": row.get("reused"),
        "error": row.get("error"),
    }
    missing = [k for k in REQUIRED_METRIC_KEYS if out.get(k) is None]
    out["schema_ok"] = len(missing) == 0
    out["missing_fields"] = missing
    return out


def metrics_from_results_json(model_id: str) -> Dict[str, Dict[str, Any]]:
    """Load frozen full/holdout from models/.../results.json when present."""
    p = ROOT / "models" / "poc_va_macdha" / model_id / "results.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    cash = DEFAULT_CASH
    out: Dict[str, Dict[str, Any]] = {}
    if "portfolio" in raw:
        out["full"] = pack_window_metrics(
            raw["portfolio"],
            window="full",
            start=str(raw.get("start") or FULL_START),
            end=str(raw.get("end") or FULL_END),
            cash=cash,
        )
        out["full"]["source"] = "frozen_results_json"
    if "holdout" in raw:
        out["holdout"] = pack_window_metrics(
            raw["holdout"],
            window="holdout",
            start=str(raw.get("holdout_start") or HOLDOUT_START),
            end=str(raw.get("holdout_end") or HOLDOUT_END),
            cash=cash,
        )
        out["holdout"]["source"] = "frozen_results_json"
    return out


# ---------------------------------------------------------------------------
# Confidence calibration (pure)
# ---------------------------------------------------------------------------


def pair_round_trips(trades: pd.DataFrame) -> pd.DataFrame:
    """Pair buy→sell rows per code into round trips with return_pct."""
    if trades is None or trades.empty:
        return pd.DataFrame(
            columns=["code", "entry_ts", "exit_ts", "return_pct", "win", "notional_frac"]
        )
    df = trades.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values(["code", "timestamp"]).reset_index(drop=True)
    rows: List[Dict[str, Any]] = []
    open_buy: Dict[str, Dict[str, Any]] = {}
    for r in df.itertuples(index=False):
        side = str(getattr(r, "side", "")).lower()
        code = str(getattr(r, "code", ""))
        if side == "buy":
            open_buy[code] = {
                "entry_ts": getattr(r, "timestamp", None),
                "price": float(getattr(r, "price", 0) or 0),
                "qty": float(getattr(r, "qty", 0) or 0),
            }
        elif side == "sell" and code in open_buy:
            b = open_buy.pop(code)
            # backtest trades.csv stores return_pct in percent points (e.g. 15.18 = +15.18%)
            raw_ret = float(getattr(r, "return_pct", 0) or 0)
            ret = raw_ret / 100.0
            notional = abs(b["price"] * b["qty"])
            rows.append(
                {
                    "code": code,
                    "entry_ts": b["entry_ts"],
                    "exit_ts": getattr(r, "timestamp", None),
                    "return_pct": ret,
                    "win": 1.0 if ret > 0 else 0.0,
                    "notional": notional,
                    "qty": b["qty"],
                    "entry_px": b["price"],
                }
            )
    return pd.DataFrame(rows)


def confidence_from_candidates(path: Path) -> pd.DataFrame:
    """Load candidate ledger rows with probability + realized outcome."""
    from evolve.calibration import load_candidate_files

    frame = load_candidate_files([path])
    out = pd.DataFrame(
        {
            "entry_ts": frame["entry_ts"],
            "code": frame["code"],
            "confidence": frame["raw_probability"].astype(float),
            "return_pct": frame["realized_r"].astype(float),
            "win": (frame["realized_r"].astype(float) > 0).astype(float),
            "confidence_kind": "candidate_raw_probability",
        }
    )
    return out


def confidence_from_size_proxy(trips: pd.DataFrame, cash: float) -> pd.DataFrame:
    """Map position notional / cash into [0,1] size proxy labeled honestly."""
    if trips is None or trips.empty:
        return pd.DataFrame(
            columns=["entry_ts", "code", "confidence", "return_pct", "win", "confidence_kind"]
        )
    cash_f = max(float(cash), 1e-9)
    conf = (trips["notional"].astype(float) / cash_f).clip(0.0, 1.0)
    # stretch small scales (v71 base ~0.225) into a usable [0.2, 0.95] band for bucketing
    conf_scaled = (0.2 + 0.75 * (conf / max(float(conf.max() or 0.4), 1e-6))).clip(0.05, 0.99)
    out = trips.copy()
    out["confidence"] = conf_scaled
    out["confidence_kind"] = "position_notional_frac_proxy"
    return out[["entry_ts", "code", "confidence", "return_pct", "win", "confidence_kind"]]


def calibrate_confidence_buckets(
    rows: pd.DataFrame,
    *,
    edges: Sequence[float] = (0.0, 0.40, 0.55, 0.70, 1.0001),
    min_bucket_n: int = MIN_BUCKET_N,
    min_total_n: int = MIN_CALIB_N,
) -> Dict[str, Any]:
    """Bucket confidence vs win rate / expectancy. Honest unreliable labeling."""
    if rows is None or rows.empty or "confidence" not in rows.columns:
        return {
            "n": 0,
            "reliable": False,
            "label": "unreliable",
            "reason": "no_rows",
            "buckets": [],
            "discrimination": None,
        }

    df = rows.dropna(subset=["confidence", "win"]).copy()
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
    df["win"] = pd.to_numeric(df["win"], errors="coerce")
    df["return_pct"] = pd.to_numeric(df.get("return_pct", 0.0), errors="coerce").fillna(0.0)
    df = df[np.isfinite(df["confidence"]) & np.isfinite(df["win"])]
    n = int(len(df))
    if n == 0:
        return {
            "n": 0,
            "reliable": False,
            "label": "unreliable",
            "reason": "no_finite_rows",
            "buckets": [],
            "discrimination": None,
        }

    edge_list = list(edges)
    labels = []
    for i in range(len(edge_list) - 1):
        labels.append(f"[{edge_list[i]:.2f},{edge_list[i+1]:.2f})")
    df["bucket"] = pd.cut(
        df["confidence"],
        bins=edge_list,
        labels=labels,
        include_lowest=True,
        right=False,
    )

    buckets: List[Dict[str, Any]] = []
    for lab in labels:
        sub = df[df["bucket"] == lab]
        bn = int(len(sub))
        if bn == 0:
            buckets.append(
                {
                    "bucket": lab,
                    "n": 0,
                    "win_rate": None,
                    "mean_return": None,
                    "expectancy": None,
                    "mean_confidence": None,
                    "reliable": False,
                    "label": "empty",
                }
            )
            continue
        wr = float(sub["win"].mean())
        mean_ret = float(sub["return_pct"].mean())
        buckets.append(
            {
                "bucket": lab,
                "n": bn,
                "win_rate": wr,
                "mean_return": mean_ret,
                "expectancy": mean_ret,
                "mean_confidence": float(sub["confidence"].mean()),
                "reliable": bn >= min_bucket_n,
                "label": "ok" if bn >= min_bucket_n else "unreliable_thin_n",
            }
        )

    # Discrimination: high conf mean win - low conf mean win (only reliable buckets)
    reliable = [b for b in buckets if b["reliable"] and b["win_rate"] is not None]
    discrimination = None
    inverted = False
    if len(reliable) >= 2:
        discrimination = float(reliable[-1]["win_rate"] - reliable[0]["win_rate"])
        inverted = discrimination < -0.02

    overall_reliable = n >= min_total_n and len(reliable) >= 2 and not inverted
    reason = None
    label = "ok"
    if n < min_total_n:
        label = "unreliable"
        reason = f"n={n} < min_total_n={min_total_n}"
    elif len(reliable) < 2:
        label = "unreliable"
        reason = "fewer_than_two_reliable_buckets"
    elif inverted:
        label = "unreliable_inverted"
        reason = f"high_minus_low_wr={discrimination:.3f} (inverted)"

    return {
        "n": n,
        "reliable": overall_reliable,
        "label": label,
        "reason": reason,
        "min_bucket_n": min_bucket_n,
        "min_total_n": min_total_n,
        "confidence_kind": (
            str(df["confidence_kind"].iloc[0]) if "confidence_kind" in df.columns else "unknown"
        ),
        "buckets": buckets,
        "discrimination": discrimination,
        "inverted": inverted,
        "mean_win_rate": float(df["win"].mean()),
        "mean_return": float(df["return_pct"].mean()),
    }


def capital_guardrail(
    *,
    full_n: Optional[int],
    holdout_n: Optional[int],
    calib: Dict[str, Any],
    vol_auto_trade: bool = False,
) -> Dict[str, Any]:
    """Hard language for real money — never green-light on thin/inverted evidence."""
    reasons: List[str] = []
    may_size = True
    if holdout_n is None or holdout_n < MIN_CLAIM_TRADES:
        may_size = False
        reasons.append(
            f"holdout n={holdout_n} below CLAIM floor {MIN_CLAIM_TRADES} — research sizing only"
        )
    if not calib.get("reliable"):
        may_size = False
        reasons.append(
            f"confidence calibration {calib.get('label')}: {calib.get('reason') or 'failed floors'}"
        )
    if vol_auto_trade:
        may_size = False
        reasons.append("options/vol package auto_trade must remain false")
    if may_size:
        reasons.append("historical floors met for disciplined paper→small live only; hard risk caps still apply")
    return {
        "research_only": not may_size,
        "not_for_naked_size_up": True,  # always — never naked size-up from audit alone
        "may_consider_small_live": may_size,
        "reasons": reasons,
        "auto_promote": False,
    }


# ---------------------------------------------------------------------------
# Historical runs via dmr
# ---------------------------------------------------------------------------


def _equity_bag() -> List[str]:
    from evolve.farm import EQUITY_WINNER_BAG

    return list(EQUITY_WINNER_BAG)


def run_model_window(
    model_id: str,
    *,
    start: str,
    end: str,
    tag: str,
    cash: float,
    source: str = DEFAULT_SOURCE,
    interval: str = DEFAULT_INTERVAL,
    reuse: bool = False,
) -> Dict[str, Any]:
    import tools.dynamic_model_rank as dmr

    models = dmr.discover_models([model_id])
    if not models:
        return {"error": f"model not found: {model_id}", "id": model_id}
    m = models[0]
    codes = _equity_bag()
    row = dmr.run_one(
        m,
        mode="daily",
        codes=codes,
        start=start,
        end=end,
        tag=tag,
        force_1d=False,
        reuse=reuse,
        cash=cash,
        source=source,
        interval=interval,
    )
    packed = pack_window_metrics(
        row,
        window=tag,
        start=start,
        end=end,
        cash=cash,
    )
    packed["id"] = model_id
    packed["codes"] = codes
    packed["source_data"] = source
    packed["interval"] = interval
    packed["raw"] = {k: row.get(k) for k in ("ret", "dd", "sharpe", "n", "wr", "final", "path", "reused", "error")}
    return packed


def find_trades_csv(model_id: str, tag_substr: str) -> Optional[Path]:
    base = ROOT / "runs" / "poc_va_dynamic_rank" / "runs" / model_id
    if not base.exists():
        return None
    matches = sorted(base.glob(f"**/*{tag_substr}*/artifacts/trades.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def find_candidates_csv(model_id: str) -> Optional[Path]:
    base = ROOT / "runs" / "poc_va_dynamic_rank" / "runs" / model_id
    if not base.exists():
        return None
    matches = sorted(base.glob("**/artifacts/candidates.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def build_confidence_series_for_model(
    model_id: str,
    *,
    cash: float,
    prefer_candidates: bool = True,
) -> Tuple[pd.DataFrame, str]:
    """Return rows for calibration + a note on confidence kind used."""
    if prefer_candidates:
        cand = find_candidates_csv(model_id)
        if cand is not None:
            try:
                return confidence_from_candidates(cand), f"candidates:{cand}"
            except Exception as exc:
                note = f"candidates_failed:{exc}"
        else:
            note = "no_candidates"
    else:
        note = "candidates_skipped"

    # Fall back to trade size proxy from latest full-window trades
    for tag in ("audit_full", "v72cmp_full", "v71_verify_full", "v71_sizeup_final_full", "full"):
        tr_path = find_trades_csv(model_id, tag)
        if tr_path is None:
            continue
        trips = pair_round_trips(pd.read_csv(tr_path))
        if trips.empty:
            continue
        return confidence_from_size_proxy(trips, cash), f"size_proxy:{tr_path};{note}"

    return (
        pd.DataFrame(columns=["entry_ts", "code", "confidence", "return_pct", "win", "confidence_kind"]),
        f"empty;{note}",
    )


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def assert_report_schema(report: Dict[str, Any]) -> List[str]:
    """Return list of schema errors (empty = ok)."""
    errs: List[str] = []
    if report.get("schema_version") != "confidence-audit-v1":
        errs.append("bad schema_version")
    inv = report.get("inventory") or {}
    if not inv.get("money_path"):
        errs.append("inventory.money_path missing")
    if not inv.get("models_routed"):
        errs.append("inventory.models_routed missing")
    if not inv.get("data_contract"):
        errs.append("inventory.data_contract missing")
    hist = report.get("historical") or {}
    if not hist:
        errs.append("historical block empty")
    for path_key, block in hist.items():
        if not isinstance(block, dict):
            errs.append(f"historical.{path_key} not a dict")
            continue
        for win in ("full", "holdout"):
            m = block.get(win) or {}
            if not m:
                errs.append(f"historical.{path_key}.{win} missing")
                continue
            # Failed runs must fail the audit (criterion: fail if required metrics missing).
            if m.get("error"):
                errs.append(f"historical.{path_key}.{win} error: {m.get('error')}")
            for k in REQUIRED_METRIC_KEYS:
                if m.get(k) is None:
                    errs.append(f"historical.{path_key}.{win}.{k} missing")
    # Prefer dual_sleeve when present (money path)
    if "dual_sleeve" not in hist and "high_wr" not in hist:
        errs.append("historical must include dual_sleeve or high_wr")
    calib = report.get("confidence_calibration") or {}
    buckets = calib.get("buckets") or []
    if len(buckets) < 2:
        errs.append("confidence_calibration needs >=2 buckets")
    g = report.get("guardrails") or {}
    if g.get("auto_promote") is not False:
        errs.append("guardrails.auto_promote must be false")
    if g.get("not_for_naked_size_up") is not True:
        errs.append("guardrails.not_for_naked_size_up must be true")
    vol = report.get("options_vol_research") or {}
    if vol.get("auto_trade") is not False:
        errs.append("options_vol_research.auto_trade must be false")
    return errs


def check_vol_research_only() -> Dict[str, Any]:
    """Spot-check vol package scorer cannot auto-trade."""
    try:
        from vol_package_score import score_symbol

        out = score_symbol("SPY", fetch_surface=False)
        g = out.get("guardrails") or {}
        return {
            "ok": True,
            "auto_trade": bool(g.get("auto_trade", True)),
            "research_only": bool(g.get("research_only", False)),
            "does_not_set_options_attack": bool(g.get("does_not_set_options_attack", False)),
            "module": "tools/vol_package_score.py",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "auto_trade": False,
            "research_only": True,
            "module": "tools/vol_package_score.py",
        }


def run_audit(
    *,
    cash: float = DEFAULT_CASH,
    quick: bool = False,
    reuse: bool = False,
    out_dir: Optional[Path] = None,
    models: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    out_dir = Path(out_dir or DEFAULT_OUT)
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory = build_live_inventory()
    dual_id = inventory["money_path"]["preferred_combined_book"]
    high_wr_id = inventory["money_path"]["high_wr_sleeve"]
    fallback_id = inventory["money_path"]["fallback_equity"]

    target_models = list(models) if models else [dual_id, high_wr_id]
    historical: Dict[str, Any] = {}

    # Stable tags so dual re-runs with --reuse are consistent evidence (same keys/values).
    full_tag = "conf_audit_full"
    holdout_tag = "conf_audit_holdout"

    for mid in target_models:
        key = "dual_sleeve" if mid == dual_id else ("high_wr" if mid == high_wr_id else mid)
        block: Dict[str, Any] = {"model_id": mid}

        if quick:
            frozen = metrics_from_results_json(mid)
            if frozen.get("full"):
                block["full"] = frozen["full"]
            if frozen.get("holdout"):
                block["holdout"] = frozen["holdout"]
            if not frozen:
                block["error"] = "quick mode but no results.json"
        else:
            try:
                block["full"] = run_model_window(
                    mid,
                    start=FULL_START,
                    end=FULL_END,
                    tag=full_tag,
                    cash=cash,
                    reuse=reuse,
                )
            except Exception as e:
                block["full"] = {"error": str(e), "schema_ok": False, "missing_fields": list(REQUIRED_METRIC_KEYS)}
            try:
                block["holdout"] = run_model_window(
                    mid,
                    start=HOLDOUT_START,
                    end=HOLDOUT_END,
                    tag=holdout_tag,
                    cash=cash,
                    reuse=reuse,
                )
            except Exception as e:
                block["holdout"] = {
                    "error": str(e),
                    "schema_ok": False,
                    "missing_fields": list(REQUIRED_METRIC_KEYS),
                }

        historical[key] = block

    # Confidence calibration: prefer candidate ledger on core (v39d); also size proxy on dual trades
    calib_sources: List[str] = []
    conf_frames: List[pd.DataFrame] = []

    core_rows, core_note = build_confidence_series_for_model(fallback_id, cash=cash, prefer_candidates=True)
    if not core_rows.empty:
        conf_frames.append(core_rows)
        calib_sources.append(core_note)

    # Dual / high-wr size proxy from their trades
    for mid, label in ((dual_id, "dual"), (high_wr_id, "high_wr")):
        rows, note = build_confidence_series_for_model(mid, cash=cash, prefer_candidates=False)
        if not rows.empty:
            conf_frames.append(rows)
            calib_sources.append(f"{label}:{note}")

    if conf_frames:
        conf_all = pd.concat(conf_frames, ignore_index=True)
    else:
        conf_all = pd.DataFrame(columns=["confidence", "win", "return_pct"])

    # Primary table: use core candidates if present else all
    primary = core_rows if not core_rows.empty else conf_all
    calibration = calibrate_confidence_buckets(primary)
    calibration["sources"] = calib_sources
    calibration["primary_model"] = fallback_id if not core_rows.empty else (target_models[0] if target_models else None)

    dual_hold_n = (historical.get("dual_sleeve") or {}).get("holdout", {}).get("n")
    dual_full_n = (historical.get("dual_sleeve") or {}).get("full", {}).get("n")
    high_hold_n = (historical.get("high_wr") or {}).get("holdout", {}).get("n")
    vol_check = check_vol_research_only()
    guardrails = capital_guardrail(
        full_n=dual_full_n,
        holdout_n=dual_hold_n,
        calib=calibration,
        vol_auto_trade=bool(vol_check.get("auto_trade")),
    )
    if high_hold_n is not None and high_hold_n < MIN_CLAIM_TRADES:
        guardrails["reasons"] = list(guardrails.get("reasons") or []) + [
            f"high_wr holdout n={high_hold_n} < CLAIM floor {MIN_CLAIM_TRADES} — do not run high-WR sleeve alone as size-up basis"
        ]

    report: Dict[str, Any] = {
        "schema_version": "confidence-audit-v1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "cash": cash,
        "quick": quick,
        "inventory": inventory,
        "historical": historical,
        "confidence_calibration": calibration,
        "guardrails": guardrails,
        "options_vol_research": {
            "auto_trade": vol_check.get("auto_trade", False),
            "research_only": vol_check.get("research_only", True),
            "does_not_set_options_attack": vol_check.get("does_not_set_options_attack", True),
            "check": vol_check,
            "capital_language": "research_only / not for naked size-up",
        },
        "operator_summary": [],
    }

    # Operator-facing bullets
    summary: List[str] = []
    ds = historical.get("dual_sleeve") or {}
    if ds.get("full") and ds["full"].get("ret") is not None:
        summary.append(
            f"v72 full: ret={ds['full']['ret']:.1%} dd={ds['full']['dd']:.1%} "
            f"sharpe={ds['full']['sharpe']:.2f} n={ds['full']['n']} wr={ds['full']['wr']:.1%}"
        )
    if ds.get("holdout") and ds["holdout"].get("ret") is not None:
        summary.append(
            f"v72 holdout (locked): ret={ds['holdout']['ret']:.1%} dd={ds['holdout']['dd']:.1%} "
            f"sharpe={ds['holdout']['sharpe']:.2f} n={ds['holdout']['n']} wr={ds['holdout']['wr']:.1%}"
        )
    summary.append(
        f"Confidence calibration: {calibration.get('label')} "
        f"(n={calibration.get('n')}, discrimination={calibration.get('discrimination')})"
    )
    if guardrails["research_only"]:
        summary.append("CAPITAL: research_only — do not naked size-up from this audit alone.")
    else:
        summary.append("CAPITAL: floors met for cautious small live only; hard caps still apply; no auto-promote.")
    summary.append("Options/vol package scores remain research_only with auto_trade=false.")
    report["operator_summary"] = summary

    schema_errors = assert_report_schema(report)
    report["schema_errors"] = schema_errors
    report["schema_ok"] = len(schema_errors) == 0

    # Write artifacts
    json_path = out_dir / "AUDIT.json"
    md_path = out_dir / "AUDIT.md"
    json_path.write_text(json.dumps(_jsonable(report), indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["written"] = {"json": str(json_path), "md": str(md_path)}
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Confidence audit — promoted live equity path")
    lines.append("")
    lines.append(f"asof: `{report.get('asof_utc')}`  ")
    lines.append(f"cash: `{report.get('cash')}`  ")
    lines.append(f"schema_ok: `{report.get('schema_ok')}`")
    lines.append("")
    lines.append("## Operator summary")
    for s in report.get("operator_summary") or []:
        lines.append(f"- {s}")
    lines.append("")
    inv = report.get("inventory") or {}
    mp = inv.get("money_path") or {}
    lines.append("## Inventory — what the money path looks at")
    lines.append("")
    lines.append(f"- **Combined book:** `{mp.get('preferred_combined_book')}`")
    lines.append(f"- **High-WR sleeve:** `{mp.get('high_wr_sleeve')}`")
    lines.append(f"- **Fallback equity:** `{mp.get('fallback_equity')}`")
    lines.append(f"- **Routing mode:** `{mp.get('routing_mode')}`")
    dc = inv.get("data_contract") or {}
    lines.append(
        f"- **Data:** source=`{dc.get('source')}` interval=`{dc.get('interval')}` "
        f"full={dc.get('full_window')} holdout={dc.get('holdout_window')} "
        f"(holdout retune forbidden={dc.get('holdout_retune_forbidden')})"
    )
    lines.append("")
    lines.append("### Models routed")
    for mid, meta in (inv.get("models_routed") or {}).items():
        lines.append(f"- **`{mid}`** — role=`{meta.get('role')}` conf=`{meta.get('confidence_source')}`")
        if meta.get("sniper"):
            lines.append(
                f"  - hierarchical: sniper=`{meta.get('sniper')}` core=`{meta.get('core')}` "
                f"both_core_frac={meta.get('both_core_frac')} max_weight={meta.get('max_weight')}"
            )
        if meta.get("trend_filter"):
            lines.append(f"  - trend_filter={meta.get('trend_filter')} quality={meta.get('quality')}")
    lines.append("")
    lines.append("### Explicitly NOT money path")
    for k, v in (inv.get("explicitly_not_money_path") or {}).items():
        lines.append(f"- `{k}`: auto_trade={v.get('auto_trade')} — {v.get('reason')}")
    lines.append("")
    lines.append("## Historical metrics (local data contract)")
    hist = report.get("historical") or {}
    for key, block in hist.items():
        lines.append(f"### {key} (`{block.get('model_id')}`)")
        for win in ("full", "holdout"):
            m = block.get(win) or {}
            if m.get("error"):
                lines.append(f"- **{win}:** ERROR {m.get('error')}")
                continue
            lines.append(
                f"- **{win}** [{m.get('start')} → {m.get('end')}]: "
                f"ret={m.get('ret')} dd={m.get('dd')} sharpe={m.get('sharpe')} "
                f"n={m.get('n')} wr={m.get('wr')} final={m.get('final')} "
                f"(source={m.get('source') or m.get('source_data')})"
            )
        lines.append("")
    lines.append("## Confidence calibration")
    cal = report.get("confidence_calibration") or {}
    lines.append(
        f"label=**{cal.get('label')}** reliable=`{cal.get('reliable')}` n=`{cal.get('n')}` "
        f"kind=`{cal.get('confidence_kind')}` discrimination=`{cal.get('discrimination')}`"
    )
    if cal.get("reason"):
        lines.append(f"reason: {cal.get('reason')}")
    lines.append("")
    lines.append("| bucket | n | win_rate | mean_return | reliable |")
    lines.append("|---|---:|---:|---:|---|")
    for b in cal.get("buckets") or []:
        lines.append(
            f"| {b.get('bucket')} | {b.get('n')} | {b.get('win_rate')} | "
            f"{b.get('mean_return')} | {b.get('reliable')} |"
        )
    lines.append("")
    lines.append("## Guardrails")
    g = report.get("guardrails") or {}
    lines.append(f"- research_only: `{g.get('research_only')}`")
    lines.append(f"- not_for_naked_size_up: `{g.get('not_for_naked_size_up')}`")
    lines.append(f"- may_consider_small_live: `{g.get('may_consider_small_live')}`")
    lines.append(f"- auto_promote: `{g.get('auto_promote')}`")
    for r in g.get("reasons") or []:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Options / vol research check")
    ov = report.get("options_vol_research") or {}
    lines.append(f"- auto_trade: `{ov.get('auto_trade')}`")
    lines.append(f"- research_only: `{ov.get('research_only')}`")
    lines.append(f"- capital_language: {ov.get('capital_language')}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Historical confidence audit for live equity path")
    p.add_argument("--cash", type=float, default=DEFAULT_CASH)
    p.add_argument("--quick", action="store_true", help="Use frozen results.json metrics (no backtest re-run)")
    p.add_argument("--reuse", action="store_true", help="Allow dmr cache reuse when re-running")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--models", default=None, help="Comma list override (default dual_sleeve + high_wr)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    models = [m.strip() for m in args.models.split(",")] if args.models else None
    report = run_audit(
        cash=float(args.cash),
        quick=bool(args.quick),
        reuse=bool(args.reuse),
        out_dir=Path(args.out_dir) if args.out_dir else None,
        models=models,
    )
    print(json.dumps(_jsonable(report), indent=2 if args.json else None))
    return 0 if report.get("schema_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
