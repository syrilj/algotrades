#!/usr/bin/env python3
"""Per-symbol model ranker — multi-window return-forward backtests → RANKER.json."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
OUT = ROOT / "runs" / "symbol_ranker"
CASH = 10_000.0
STALE_DAYS = 7
EXCLUDE = {
    "specialists",
    "v23_moonshot_1y",
    "v35_mixed_dte",
    "v22_opts_hunt",
    "v28_feedback",
    "v3_sqz",
    "v4_voldiv",
    "v5_combo",
    "v6_softconf",
}
OPTIONS_BAG = {"IONQ", "AVGO", "HOOD", "MU", "TSLA", "GME", "COIN", "RKLB"}
COPY_NAMES = (
    "signal_engine.py",
    "_base_engine.py",
    "GENOME.json",
    "hunt_config.json",
    "meta_config.json",
    "meta_xgb_final.json",
    "vpa.py",
    "vwap_peg.py",
    "vwap_dna.json",
    "ROUTING.json",
    "RISK_POLICY.json",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sym(symbol: str) -> tuple[str, str]:
    s = str(symbol).strip().upper().replace(".US", "")
    return s, f"{s}.US"


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def _sanitize_nan(obj: Any) -> Any:
    """Replace NaN/±Infinity with None so downstream JSON.parse is safe."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _print_json(obj: Any) -> int:
    print(json.dumps(_sanitize_nan(obj), default=str))
    return 0


def window_specs(
    today: date | None = None,
    *,
    horizon: str = "swing",
) -> dict[str, dict[str, str]]:
    """Multi-window backtest ranges, interval-tuned per trade horizon.

    - day: 1H bars, shorter lookbacks (intraday / swing-day DNA)
    - swing: 1D bars, ~6m recent / prior (default)
    - position: 1D bars, longer full window emphasis
    """
    today = today or date.today()
    end = today.isoformat()
    h = str(horizon or "swing").strip().lower()
    if h in ("intraday", "daytrade", "day_trade", "1h", "hourly", "short"):
        h = "day"
    elif h in ("long", "long_term", "longterm", "invest", "buy_hold"):
        h = "position"
    elif h not in ("day", "swing", "position"):
        h = "swing"

    if h == "day":
        recent_start = (today - timedelta(days=90)).isoformat()
        prior_start = (today - timedelta(days=180)).isoformat()
        full_start = (today - timedelta(days=365)).isoformat()
        interval = "1H"
        return {
            "full": {"start": full_start, "end": end, "interval": interval},
            "recent": {"start": recent_start, "end": end, "interval": interval},
            "prior": {"start": prior_start, "end": recent_start, "interval": interval},
        }
    if h == "position":
        recent_start = (today - timedelta(days=270)).isoformat()
        prior_start = (today - timedelta(days=540)).isoformat()
        return {
            "full": {"start": "2024-01-01", "end": end, "interval": "1D"},
            "recent": {"start": recent_start, "end": end, "interval": "1D"},
            "prior": {"start": prior_start, "end": recent_start, "interval": "1D"},
        }
    # swing (default)
    recent_start = (today - timedelta(days=182)).isoformat()
    prior_start = (today - timedelta(days=364)).isoformat()
    return {
        "full": {"start": "2024-08-01", "end": end, "interval": "1D"},
        "recent": {"start": recent_start, "end": end, "interval": "1D"},
        "prior": {"start": prior_start, "end": recent_start, "interval": "1D"},
    }


def _winner_doc() -> dict[str, Any]:
    path = MODELS_ROOT / "WINNER.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


# Always-probe champions so ranker evidence covers live sleeves, not only priors.
_ALWAYS_RANK: tuple[str, ...] = (
    "v72_dual_sleeve",
    "v71_live_confidence",
    "v39d_confluence",
    "v39b_live_adapt",
    "v50_high_win_rate",
    "v63_spy_prune",
)


def equity_candidates(max_models: int = 8, *, horizon: str = "swing") -> list[str]:
    import model_registry as mr

    ordered: list[str] = []
    w = _winner_doc()
    for key in ("winner", "previous_winner"):
        mid = w.get(key)
        if mid and mid not in ordered and mid not in EXCLUDE:
            ordered.append(str(mid))
    if mr.DEFAULT_MODEL not in ordered and mr.DEFAULT_MODEL not in EXCLUDE:
        ordered.append(mr.DEFAULT_MODEL)
    # Horizon-priority champions first.
    try:
        h = mr.normalize_horizon(horizon)
    except Exception:
        h = "swing"
    ranked_always = sorted(
        _ALWAYS_RANK,
        key=lambda m: mr.model_horizon_affinity(m, h),
        reverse=True,
    )
    for mid in ranked_always:
        if mid not in ordered and mid not in EXCLUDE and (MODELS_ROOT / mid / "signal_engine.py").exists():
            ordered.append(mid)
    desk = set(mr.list_desk_engines())
    for row in mr.rank_models(engines_only=True):
        mid = row.get("model")
        if not mid or mid in EXCLUDE or mid in ordered:
            continue
        if mid not in desk and mid not in (w.get("winner"), w.get("previous_winner")):
            continue
        ordered.append(str(mid))
        if len(ordered) >= max_models:
            break
    for mid in mr.list_desk_engines():
        if len(ordered) >= max_models:
            break
        if mid in EXCLUDE or mid in ordered:
            continue
        ordered.append(mid)
    return ordered[:max_models]


def options_candidates() -> list[str]:
    import model_registry as mr

    ordered: list[str] = []
    try:
        ow_path = MODELS_ROOT / "OPTIONS_WINNER.json"
        if ow_path.exists():
            ow = json.loads(ow_path.read_text())
            if isinstance(ow, dict) and ow.get("winner"):
                ordered.append(str(ow["winner"]))
    except Exception:
        pass
    try:
        ordered.append(mr.options_default_model())
    except Exception:
        ordered.append(getattr(mr, "OPTIONS_DEFAULT_MODEL", "v32_soft_react_opts"))
    for mid in ("v34_bag6_opts", "v32_soft_react_opts"):
        if mid not in ordered:
            ordered.append(mid)
    seen: list[str] = []
    engines = set(mr.list_engine_models())
    for mid in ordered:
        if mid in seen or mid in EXCLUDE or mid not in engines:
            continue
        seen.append(mid)
    return seen


def _copy_model_code(model_id: str, run_code: Path) -> None:
    run_code.mkdir(parents=True, exist_ok=True)
    model_dir = MODELS_ROOT / model_id
    for name in COPY_NAMES:
        p = model_dir / name
        if p.exists():
            shutil.copy2(p, run_code / name)


def _read_metrics(metrics_path: Path) -> dict[str, Any]:
    row = next(csv.DictReader(open(metrics_path)))
    pf_raw = row.get("profit_factor")
    if pf_raw in (None, ""):
        pf_raw = row.get("profit_loss_ratio")
    return {
        "total_return": _f(row.get("total_return")),
        "sharpe": _f(row.get("sharpe")),
        "calmar": _f(row.get("calmar")),
        "max_drawdown": _f(row.get("max_drawdown")),
        "win_rate": _f(row.get("win_rate")),
        "profit_factor": _f(pf_raw, 1.0),
        "profit_loss_ratio": _f(row.get("profit_loss_ratio"), 1.0),
        "trade_count": int(_f(row.get("trade_count"))),
        "final_value": _f(row.get("final_value")),
    }


def run_backtest(
    model: str,
    symbol_code: str,
    window: str,
    spec: dict[str, str],
    engine_mode: str,
    cash: float,
    reuse: bool = True,
) -> dict[str, Any]:
    sym = symbol_code.replace(".US", "")
    end = spec["end"]
    run_dir = OUT / sym / f"{model}__{window}__{end}"
    metrics_path = run_dir / "artifacts" / "metrics.csv"
    rel = str(run_dir.relative_to(ROOT))

    if reuse and metrics_path.exists():
        try:
            m = _read_metrics(metrics_path)
            return {"status": "ok", "reused": True, "run_dir": rel, **m}
        except Exception:
            pass

    if not (MODELS_ROOT / model / "signal_engine.py").exists():
        return {
            "status": "error",
            "reused": False,
            "run_dir": rel,
            "error": f"missing signal_engine for {model}",
        }

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_code = run_dir / "code"
    _copy_model_code(model, run_code)

    commission = 0.001
    model_cfg = MODELS_ROOT / model / "config.json"
    if model_cfg.exists():
        try:
            mc = json.loads(model_cfg.read_text())
            if mc.get("commission") is not None:
                commission = float(mc["commission"])
        except Exception:
            pass

    mode = "options" if engine_mode == "options" else "daily"
    max_contracts = max(1, int(500 * (cash / 1_000_000)))
    if cash <= 25_000:
        max_contracts = max(1, min(max_contracts, 20))

    code = symbol_code if symbol_code.endswith(".US") else f"{sym}.US"
    cfg = {
        "source": "yfinance",
        "codes": [code],
        "start_date": spec["start"],
        "end_date": spec["end"],
        "initial_cash": cash,
        "commission": commission,
        "engine": mode,
        "interval": spec.get("interval", "1D"),
        "options_config": {
            "risk_free_rate": 0.05,
            "contract_multiplier": 100,
            "exercise_style": "american",
        },
        "strategy": {
            "model_version": model,
            "rank_tag": f"{window}_{sym}",
            "mode": mode,
            "cash": cash,
        },
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))

    hunt_path = run_code / "hunt_config.json"
    if mode == "options":
        if hunt_path.exists():
            try:
                hc = json.loads(hunt_path.read_text())
            except Exception:
                hc = {}
        else:
            hc = {
                "risk_pct": 0.10,
                "dte_days": 21,
                "otm_pct": 0.0,
                "halt_dd": 0.30,
                "flatten_dd": 0.45,
            }
        hc["initial_cash"] = cash
        hc["contract_multiplier"] = int(hc.get("contract_multiplier") or 100)
        hc["max_contracts"] = min(int(hc.get("max_contracts") or 500), max_contracts)
        if cash <= 25_000 and float(hc.get("risk_pct") or 0.1) < 0.15:
            hc["risk_pct"] = max(float(hc.get("risk_pct") or 0.1), 0.20)
        hunt_path.write_text(json.dumps(hc, indent=2))

    try:
        from backtest.runner import main as bt_main
        import contextlib
        from io import StringIO

        try:
            # runner may print metrics JSON to stdout — keep CLI --json clean
            with contextlib.redirect_stdout(StringIO()):
                try:
                    bt_main(run_dir.resolve())
                except SystemExit as se:
                    raise RuntimeError(f"backtest SystemExit: {se}") from se
        except RuntimeError:
            raise
        m = _read_metrics(metrics_path)
        art = run_dir / "artifacts"
        for p in art.glob("ohlcv_*.csv"):
            p.unlink(missing_ok=True)
        return {"status": "ok", "reused": False, "run_dir": rel, **m}
    except Exception as e:  # noqa: BLE001
        err = str(e).split("\n")[0][:200]
        return {"status": "error", "reused": False, "run_dir": rel, "error": err}


def window_utility(m: dict[str, Any] | None) -> float:
    if not m or m.get("status") != "ok":
        return -0.5
    n = int(m.get("trade_count") or 0)
    dd = abs(_f(m.get("max_drawdown")))
    if dd >= 0.25:
        return -1.0
    reliability = min(1.0, n / 40.0)
    return reliability * (
        _f(m.get("total_return"))
        + 0.35 * min(_f(m.get("sharpe")), 3.0)
        + 0.15 * _f(m.get("calmar"))
        + 0.05 * _f(m.get("win_rate"))
        - 0.55 * max(0.0, dd - 0.15)
    )


# --- Confidence layer: conservative, evidence-gated (anti-false-signal) ---

Z_ONE_SIDED_90 = 1.645
MIN_TRADES_FULL = 12  # below this the read is capped hard (THIN evidence)
TRUST_MIN_TRADES = 20  # a TRUST verdict needs at least this many full-window trades
CONF_THIN_CAP = 0.35
DD_HARD_GATE = 0.25
DD_SOFT_KNEE = 0.15
OPTIONS_CONF_CAP = 0.55  # synthetic BS pricing can never earn a trusted read


def _norm_horizon(horizon: str | None) -> str:
    h = str(horizon or "swing").strip().lower()
    if h in ("intraday", "daytrade", "day_trade", "1h", "hourly", "short"):
        return "day"
    if h in ("long", "long_term", "longterm", "invest", "buy_hold"):
        return "position"
    return h if h in ("day", "swing", "position") else "swing"


def wilson_lower_bound(wins: float, n: int, z: float = Z_ONE_SIDED_90) -> float:
    """Conservative lower bound of a win rate given the sample size."""
    if n <= 0:
        return 0.0
    p = max(0.0, min(1.0, wins / n))
    z2 = z * z
    centre = p + z2 / (2 * n)
    spread = z * math.sqrt((p * (1.0 - p) + z2 / (4 * n)) / n)
    return max(0.0, (centre - spread) / (1.0 + z2 / n))


def breakeven_win_rate(profit_loss_ratio: float) -> float:
    """Win rate needed to break even given the avg win / avg loss ratio."""
    plr = min(10.0, max(0.1, _f(profit_loss_ratio, 1.0) or 1.0))
    return 1.0 / (1.0 + plr)


def row_confidence(row: dict[str, Any], *, options_track: bool = False) -> dict[str, Any]:
    """Evidence-gated confidence in [0,1] for one engine on one symbol.

    Gates are multiplicative so a single disqualifier (no statistical edge,
    blow-up drawdown, thin sample) zeroes or caps the read instead of being
    averaged away by strong-looking headline metrics.
    """
    reasons: list[str] = []
    parts: dict[str, Any] = {}
    wm = row.get("window_metrics") or {}
    full = wm.get("full") or {}
    if row.get("status") != "ok" or full.get("status") != "ok":
        return {"confidence": 0.0, "parts": {}, "reasons": ["no_valid_full_window"]}

    n = int(_f(full.get("trade_count")))
    if n <= 0:
        return {"confidence": 0.0, "parts": {"n_full": 0}, "reasons": ["no_trades"]}
    wr = _f(full.get("win_rate"))
    lb = wilson_lower_bound(wr * n, n)
    plr = _f(full.get("profit_loss_ratio"), 0.0) or _f(full.get("profit_factor"), 1.0)
    be = breakeven_win_rate(plr)
    margin = lb - be
    # Full credit only when the *lower bound* clears breakeven by 10 points.
    edge = max(0.0, min(1.0, margin / 0.10))
    parts.update(
        {
            "n_full": n,
            "win_rate": round(wr, 4),
            "wilson_lb": round(lb, 4),
            "breakeven_wr": round(be, 4),
            "edge_margin": round(margin, 4),
            "edge": round(edge, 4),
        }
    )
    if margin <= 0:
        reasons.append("win_rate_lb_below_breakeven")

    sample = math.sqrt(n / (n + 20.0))
    parts["sample"] = round(sample, 4)

    oos = max(0.0, min(1.0, _f(row.get("oos_consistency"))))
    consistency = 0.5 + 0.5 * oos
    recent = wm.get("recent") or {}
    if recent.get("status") == "ok" and _f(recent.get("total_return")) < 0:
        consistency *= 0.7
        reasons.append("recent_window_negative")
    parts["consistency"] = round(consistency, 4)

    dd = abs(_f(full.get("max_drawdown")))
    if dd >= DD_HARD_GATE:
        return {"confidence": 0.0, "parts": parts, "reasons": reasons + ["drawdown_gate"]}
    dd_factor = max(0.5, 1.0 - max(0.0, dd - DD_SOFT_KNEE) * 3.0)
    parts["dd_factor"] = round(dd_factor, 4)

    conf = edge * sample * consistency * dd_factor

    live = row.get("live")
    if isinstance(live, dict) and int(live.get("n") or 0) >= 5:
        adj = max(-0.10, min(0.10, 0.2 * _f(live.get("avg_R"))))
        conf += adj
        parts["live_adj"] = round(adj, 4)
        if adj < 0:
            reasons.append("live_underperformance")

    if n < MIN_TRADES_FULL and conf > CONF_THIN_CAP:
        conf = CONF_THIN_CAP
        reasons.append("thin_sample_capped")
    if options_track and conf > OPTIONS_CONF_CAP:
        conf = OPTIONS_CONF_CAP
        reasons.append("synthetic_options_pricing_capped")

    return {"confidence": round(max(0.0, min(1.0, conf)), 4), "parts": parts, "reasons": reasons}


def _apply_confidence(rows: list[dict[str, Any]], *, options_track: bool = False) -> None:
    for row in rows:
        res = row_confidence(row, options_track=options_track)
        row["confidence"] = res["confidence"]
        row["confidence_parts"] = res["parts"]
        row["confidence_reasons"] = res["reasons"]


def confidence_read(art: dict[str, Any], *, horizon: str = "swing") -> dict[str, Any]:
    """Symbol-level highest-confidence engine read with honest abstain.

    A verdict is only TRUST when the top engine's evidence-gated confidence
    clears the horizon enter threshold on a non-thin sample; otherwise the
    read degrades to WATCH or STAND_ASIDE with named reasons.
    """
    h = _norm_horizon(horizon)
    try:
        import model_registry as mr

        thresholds = mr.horizon_confidence_thresholds(h)
    except Exception:
        thresholds = {"watch": 0.50, "enter": 0.60}
    reasons: list[str] = []
    read: dict[str, Any] = {
        "schema": 1,
        "symbol": art.get("symbol"),
        "horizon": h,
        "asof": art.get("asof"),
        "verdict": "STAND_ASIDE",
        "model": None,
        "confidence": 0.0,
        "thresholds": {k: round(float(v), 4) for k, v in thresholds.items()},
        "runner_up": None,
        "gap": None,
        "reasons": reasons,
    }
    if art.get("stale"):
        reasons.append("ranker_stale_refresh_required")
        return read
    rows = [
        r
        for r in (art.get("rows") or [])
        if r.get("status") == "ok" and r.get("desk_runnable")
    ]
    if not rows:
        reasons.append("no_desk_runnable_evidence")
        return read
    ranked = sorted(
        rows,
        key=lambda r: (-_f(r.get("confidence")), -_f(r.get("score")), r.get("model") or ""),
    )
    best = ranked[0]
    conf = _f(best.get("confidence"))
    read["model"] = best.get("model")
    read["confidence"] = conf
    reasons.extend(str(x) for x in (best.get("confidence_reasons") or []))
    if len(ranked) > 1:
        second = ranked[1]
        read["runner_up"] = {
            "model": second.get("model"),
            "confidence": _f(second.get("confidence")),
        }
        read["gap"] = round(conf - _f(second.get("confidence")), 4)

    verdict = "STAND_ASIDE"
    if conf >= float(thresholds.get("enter", 0.60)):
        verdict = "TRUST"
    elif conf >= float(thresholds.get("watch", 0.50)):
        verdict = "WATCH"
    n_full = int(_f((best.get("confidence_parts") or {}).get("n_full")))
    if verdict == "TRUST" and n_full < TRUST_MIN_TRADES:
        verdict = "WATCH"
        reasons.append("sample_below_trust_floor")
    if verdict == "STAND_ASIDE" and not reasons:
        reasons.append("confidence_below_watch_threshold")
    read["verdict"] = verdict
    return read


def composite_score(utils: dict[str, float], *, quick: bool) -> tuple[float, float]:
    if quick:
        u = utils.get("full", -0.5)
        return u - 0.10, (1.0 if u > 0 else 0.0)
    u_full = utils.get("full", -0.5)
    u_recent = utils.get("recent", -0.5)
    u_prior = utils.get("prior", -0.5)
    try:
        pstdev = statistics.pstdev([u_full, u_recent, u_prior])
    except statistics.StatisticsError:
        pstdev = 0.0
    score = 0.50 * u_full + 0.25 * u_recent + 0.25 * u_prior - 0.25 * pstdev
    run_keys = [k for k in ("full", "recent", "prior") if k in utils]
    pos = sum(1 for k in run_keys if utils.get(k, -0.5) > 0)
    oos = pos / len(run_keys) if run_keys else 0.0
    return score, oos


def claim_level(
    n_full: int, portfolio: dict[str, Any] | None, *, options_track: bool
) -> tuple[str, dict[str, Any]]:
    import findings as findings_mod

    pb = findings_mod.check_pass_bar(portfolio)
    if n_full < 12:
        level = "THIN"
    elif n_full < 40:
        level = "RESEARCH"
    else:
        level = "CLAIM" if pb.get("passed") else "RESEARCH"
    if options_track and level == "CLAIM":
        level = "RESEARCH"
    return level, {"passed": bool(pb.get("passed")), "reasons": list(pb.get("reasons") or [])}


def _hist_evidence(model: str, code: str) -> dict[str, Any] | None:
    import model_registry as mr

    code_u = code.upper()
    sym_u = code_u.replace(".US", "")
    for card in mr.all_model_cards(engines_only=False):
        if card.get("model") != model:
            continue
        per = card.get("per_symbol") or {}
        row = per.get(code_u) or per.get(sym_u) or per.get(f"{sym_u}.US")
        if not isinstance(row, dict):
            continue
        out: dict[str, Any] = {"source": card.get("source") or "TRAINING_LEADERBOARD"}
        if row.get("win_rate") is not None:
            out["win_rate"] = _f(row.get("win_rate"))
        if row.get("sharpe") is not None:
            out["sharpe"] = _f(row.get("sharpe"))
        if row.get("trade_count") is not None:
            out["trade_count"] = int(_f(row.get("trade_count")))
        return out
    return None


def enrich_live(rows: list[dict[str, Any]], symbol: str) -> None:
    try:
        import paper_ledger as pl

        stats = pl.compute_stats(symbol=symbol)
    except Exception:
        for r in rows:
            r.setdefault("live", None)
            r.setdefault("live_blend_applied", False)
        return

    by_key = {(r["model"], r["symbol"]): r for r in stats.get("rows") or []}
    sym, _ = _sym(symbol)
    for row in rows:
        live = by_key.get((row.get("model"), sym))
        if live:
            row["live"] = {
                "n": int(live.get("n") or 0),
                "wins": int(live.get("wins") or 0),
                "live_wr": float(live.get("live_wr") or 0),
                "total_pnl": float(live.get("total_pnl") or 0),
                "avg_R": float(live.get("avg_R") or 0),
            }
        else:
            row["live"] = None
        row["live_blend_applied"] = False
        live_s = row.get("live")
        if live_s and int(live_s.get("n") or 0) >= 5:
            adj = max(-0.15, min(0.15, 0.25 * float(live_s.get("avg_R") or 0)))
            row["score"] = float(row.get("score") or 0) + adj
            row["live_blend_applied"] = True


def _atomic_write(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_sanitize_nan(obj), indent=2, default=str))
    os.replace(tmp, path)


def _pending_metrics() -> dict[str, Any]:
    return {"status": "pending"}


def _assemble_row(
    model: str,
    *,
    window_metrics: dict[str, dict[str, Any]],
    utils: dict[str, float],
    quick: bool,
    options_track: bool,
    code: str,
) -> dict[str, Any]:
    import model_registry as mr

    score, oos = composite_score(utils, quick=quick)
    full = window_metrics.get("full") or {}
    n_full = int(full.get("trade_count") or 0) if full.get("status") == "ok" else 0
    portfolio = None
    if full.get("status") == "ok":
        portfolio = {
            "total_return": full.get("total_return"),
            "sharpe": full.get("sharpe"),
            "calmar": full.get("calmar"),
            "max_drawdown": full.get("max_drawdown"),
            "win_rate": full.get("win_rate"),
            "profit_factor": full.get("profit_factor") or full.get("profit_loss_ratio") or 1.0,
            "trade_count": n_full,
        }
    level, pb = claim_level(n_full, portfolio, options_track=options_track)

    recent = window_metrics.get("recent") or {}
    prior = window_metrics.get("prior") or {}
    if quick:
        proj = _f(full.get("total_return")) * 0.25 if full.get("status") == "ok" else 0.0
    else:
        rets = []
        if recent.get("status") == "ok":
            rets.append(_f(recent.get("total_return")))
        if prior.get("status") == "ok":
            rets.append(_f(prior.get("total_return")))
        proj = (sum(rets) / len(rets)) if rets else (
            _f(full.get("total_return")) * 0.25 if full.get("status") == "ok" else 0.0
        )

    reliability = min(1.0, n_full / 40.0) if full.get("status") == "ok" else 0.0
    statuses = [wm.get("status") for wm in window_metrics.values()]
    if any(s == "error" for s in statuses) and not any(s == "ok" for s in statuses):
        row_status = "error"
        err = next((wm.get("error") for wm in window_metrics.values() if wm.get("error")), None)
    elif any(s == "pending" for s in statuses):
        row_status = "pending"
        err = None
    else:
        row_status = "ok" if any(s == "ok" for s in statuses) else "error"
        err = None

    row: dict[str, Any] = {
        "model": model,
        "engine_kind": mr.engine_kind(model),
        "desk_runnable": model in set(mr.list_desk_engines()),
        "rank": 0,
        "score": score,
        "utility": {k: utils.get(k) for k in ("full", "recent", "prior") if k in utils},
        "oos_consistency": oos,
        "reliability": reliability,
        "window_metrics": window_metrics,
        "claim_level": level,
        "pass_bar": pb,
        "proj_6mo_return": proj,
        "hist_evidence": _hist_evidence(model, code),
        "live": None,
        "live_blend_applied": False,
        "status": row_status,
        "error": err,
    }
    if full.get("status") == "ok":
        row.update(
            {
                "total_return": full.get("total_return"),
                "max_drawdown": full.get("max_drawdown"),
                "sharpe": full.get("sharpe"),
                "win_rate": full.get("win_rate"),
                "trade_count": full.get("trade_count"),
            }
        )
    if options_track:
        row["pricing"] = "synthetic_bs"
    return row


def _rank_sort(rows: list[dict[str, Any]]) -> None:
    # Confidence first: an unproven high-score row must not outrank proven
    # evidence. Score remains the tie-break within a confidence tier.
    rows.sort(
        key=lambda r: (
            0 if r.get("status") == "ok" else 1,
            -float(r.get("confidence") or 0.0),
            -float(r.get("score") or -999),
            r.get("model") or "",
        )
    )
    for i, r in enumerate(rows, 1):
        r["rank"] = i


def _artifact_path(sym: str, horizon: str = "swing") -> Path:
    h = str(horizon or "swing").strip().lower()
    if h in ("intraday", "daytrade", "1h", "hourly", "short"):
        h = "day"
    elif h in ("long", "long_term", "longterm", "invest"):
        h = "position"
    elif h not in ("day", "swing", "position"):
        h = "swing"
    if h == "swing":
        # Legacy path stays the default so existing consumers keep working.
        return OUT / sym / "RANKER.json"
    return OUT / sym / f"RANKER_{h}.json"


def load_artifact(symbol: str, *, horizon: str = "swing") -> dict[str, Any] | None:
    sym, _ = _sym(symbol)
    path = _artifact_path(sym, horizon)
    if not path.exists() and horizon != "swing":
        # Fall back to legacy RANKER.json.
        path = OUT / sym / "RANKER.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _age_days(asof: str | None) -> float | None:
    if not asof:
        return None
    try:
        dt = datetime.fromisoformat(asof.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400.0
    except Exception:
        return None


def _prune(sym: str, artifact: dict[str, Any]) -> None:
    keep: set[str] = set()
    for track in ("rows", "options_rows"):
        for row in artifact.get(track) or []:
            for wm in (row.get("window_metrics") or {}).values():
                rd = wm.get("run_dir")
                if rd:
                    keep.add(Path(rd).name)
    base = OUT / sym
    if not base.exists():
        return
    for child in base.iterdir():
        if child.name.startswith("RANKER") or child.name.endswith(".tmp"):
            continue
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child, ignore_errors=True)


def build_ranker(
    symbol: str,
    *,
    quick: bool = False,
    refresh: bool = False,
    max_seconds: float = 240.0,
    kind: str = "equity",
    max_models: int = 8,
    cash: float = CASH,
    models: list[str] | None = None,
    horizon: str = "swing",
) -> dict[str, Any]:
    sym, code = _sym(symbol)
    h = str(horizon or "swing").strip().lower()
    if h in ("intraday", "daytrade", "1h", "hourly", "short"):
        h = "day"
    elif h in ("long", "long_term", "longterm", "invest"):
        h = "position"
    elif h not in ("day", "swing", "position"):
        h = "swing"
    specs = window_specs(horizon=h)
    windows_run = ("full",) if quick else ("full", "recent", "prior")

    eq = models if models else equity_candidates(max_models, horizon=h)
    do_opts = kind in ("options", "both") or (kind == "equity" and sym in OPTIONS_BAG)
    if kind == "options":
        eq = []
        do_opts = True
    opts = options_candidates() if do_opts else []

    eq_wm: dict[str, dict[str, dict[str, Any]]] = {
        m: {w: _pending_metrics() for w in windows_run} for m in eq
    }
    opt_wm: dict[str, dict[str, dict[str, Any]]] = {
        m: {w: _pending_metrics() for w in windows_run} for m in opts
    }
    errors: list[str] = []
    t0 = time.monotonic()
    budget_hit = False

    def assemble(status: str) -> dict[str, Any]:
        rows = []
        for m in eq:
            utils = {}
            for w in windows_run:
                wm = eq_wm[m].get(w) or {}
                if wm.get("status") == "pending":
                    utils[w] = -0.5
                else:
                    utils[w] = window_utility(wm)
            rows.append(
                _assemble_row(
                    m,
                    window_metrics=eq_wm[m],
                    utils=utils,
                    quick=quick,
                    options_track=False,
                    code=code,
                )
            )
        opt_rows = []
        for m in opts:
            utils = {}
            for w in windows_run:
                wm = opt_wm[m].get(w) or {}
                if wm.get("status") == "pending":
                    utils[w] = -0.5
                else:
                    utils[w] = window_utility(wm)
            opt_rows.append(
                _assemble_row(
                    m,
                    window_metrics=opt_wm[m],
                    utils=utils,
                    quick=quick,
                    options_track=True,
                    code=code,
                )
            )
        enrich_live(rows, sym)
        enrich_live(opt_rows, sym)
        _apply_confidence(rows)
        _apply_confidence(opt_rows, options_track=True)
        _rank_sort(rows)
        _rank_sort(opt_rows)
        art = {
            "schema": 3,
            "symbol": sym,
            "code": code,
            "horizon": h,
            "asof": _utc_now(),
            "cash": cash,
            "status": status,
            "budget_seconds": max_seconds,
            "elapsed_seconds": round(time.monotonic() - t0, 2),
            "windows": {k: specs[k] for k in ("full", "recent", "prior")},
            "rows": rows,
            "options_rows": opt_rows,
            "errors": errors,
        }
        art["read"] = confidence_read(art, horizon=h)
        return art

    path = _artifact_path(sym, h)

    for window in windows_run:
        if budget_hit:
            break
        for model in eq:
            if time.monotonic() - t0 > max_seconds:
                budget_hit = True
                break
            res = run_backtest(
                model, code, window, specs[window], "daily", cash, reuse=not refresh
            )
            eq_wm[model][window] = res
            if res.get("status") == "error":
                errors.append(f"{model}/{window}: {res.get('error')}")
            _atomic_write(path, assemble("partial"))
        for model in opts:
            if budget_hit or time.monotonic() - t0 > max_seconds:
                budget_hit = True
                break
            res = run_backtest(
                model, code, window, specs[window], "options", cash, reuse=not refresh
            )
            opt_wm[model][window] = res
            if res.get("status") == "error":
                errors.append(f"{model}/{window}/opts: {res.get('error')}")
            _atomic_write(path, assemble("partial"))

    pending_left = any(
        wm.get("status") == "pending"
        for store in (eq_wm, opt_wm)
        for m in store.values()
        for wm in m.values()
    )
    final_status = "partial" if (budget_hit or pending_left) else "complete"
    art = assemble(final_status)
    _atomic_write(path, art)
    _prune(sym, art)
    return art


def show_payload(symbol: str, *, horizon: str = "swing") -> dict[str, Any]:
    sym, code = _sym(symbol)
    art = load_artifact(sym, horizon=horizon)
    if not art:
        out = {
            "exists": False,
            "symbol": sym,
            "code": code,
            "horizon": horizon,
            "stale": True,
            "rows": [],
            "options_rows": [],
            "schema": 3,
            "asof": _utc_now(),
            "cash": CASH,
            "status": "partial",
            "windows": window_specs(horizon=horizon),
        }
        out["read"] = confidence_read(out, horizon=horizon)
        return out
    rows = list(art.get("rows") or [])
    opt_rows = list(art.get("options_rows") or [])
    enrich_live(rows, sym)
    enrich_live(opt_rows, sym)
    _apply_confidence(rows)
    _apply_confidence(opt_rows, options_track=True)
    _rank_sort(rows)
    _rank_sort(opt_rows)
    art["rows"] = rows
    art["options_rows"] = opt_rows
    age = _age_days(art.get("asof"))
    art["exists"] = True
    art["age_days"] = age
    art["stale"] = age is None or age > STALE_DAYS
    art["read"] = confidence_read(art, horizon=horizon)
    return art


def cmd_rank(ns: argparse.Namespace) -> int:
    sym, _ = _sym(ns.symbol)
    horizon = getattr(ns, "horizon", "swing") or "swing"
    if not ns.refresh:
        art = load_artifact(sym, horizon=horizon)
        age = _age_days(art.get("asof")) if art else None
        if art and art.get("status") == "complete" and age is not None and age <= STALE_DAYS:
            return _print_json(show_payload(sym, horizon=horizon))

    models = None
    if ns.models:
        models = [m.strip() for m in ns.models.split(",") if m.strip()]
    art = build_ranker(
        ns.symbol,
        quick=bool(ns.quick),
        refresh=bool(ns.refresh),
        max_seconds=float(ns.max_seconds),
        kind=ns.kind,
        max_models=int(ns.max_models),
        cash=float(ns.cash),
        models=models,
        horizon=horizon,
    )
    out = show_payload(sym, horizon=horizon)
    out.update({k: art[k] for k in art if k not in ("exists", "stale", "age_days")})
    out["exists"] = True
    age = _age_days(out.get("asof"))
    out["age_days"] = age
    out["stale"] = age is None or age > STALE_DAYS
    return _print_json(out)


def cmd_show(ns: argparse.Namespace) -> int:
    horizon = getattr(ns, "horizon", "swing") or "swing"
    return _print_json(show_payload(ns.symbol, horizon=horizon))


def cmd_read(ns: argparse.Namespace) -> int:
    horizon = getattr(ns, "horizon", "swing") or "swing"
    art = show_payload(ns.symbol, horizon=horizon)
    return _print_json(art.get("read") or confidence_read(art, horizon=horizon))


def cmd_best(ns: argparse.Namespace) -> int:
    import model_registry as mr

    horizon = getattr(ns, "horizon", "swing") or "swing"
    hit = None
    if hasattr(mr, "ranker_best_model"):
        hit = mr.ranker_best_model(ns.symbol, desk_only=True, horizon=horizon)
    if not hit:
        art = show_payload(ns.symbol, horizon=horizon)
        for row in art.get("rows") or []:
            if (
                row.get("status") == "ok"
                and row.get("claim_level") in ("RESEARCH", "CLAIM", "THIN")
                and row.get("desk_runnable")
            ):
                hit = {
                    "model": row["model"],
                    "score": row["score"],
                    "confidence": row.get("confidence"),
                    "code": art.get("code"),
                    "asof": art.get("asof"),
                    "win_rate": row.get("win_rate"),
                    "sharpe": row.get("sharpe"),
                    "horizon": horizon,
                    "relative_only": float(row.get("score") or 0) <= 0,
                }
                break
    return _print_json({"ok": True, "best": hit, "exists": hit is not None, "horizon": horizon})


def main(argv: list[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    want_json = "--json" in raw
    raw = [a for a in raw if a != "--json"]

    ap = argparse.ArgumentParser(description="Per-symbol model ranker")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rank")
    r.add_argument("symbol")
    r.add_argument("--quick", action="store_true")
    r.add_argument("--refresh", action="store_true")
    r.add_argument("--max-seconds", type=float, default=240.0)
    r.add_argument("--kind", choices=["equity", "options", "both"], default="equity")
    r.add_argument("--max-models", type=int, default=8)
    r.add_argument("--models", default=None)
    r.add_argument("--cash", type=float, default=CASH)
    r.add_argument(
        "--horizon",
        choices=["day", "swing", "position"],
        default="swing",
        help="Trade timeframe: day (1H), swing (1D default), position (longer 1D)",
    )
    r.set_defaults(func=cmd_rank)

    s = sub.add_parser("show")
    s.add_argument("symbol")
    s.add_argument("--horizon", choices=["day", "swing", "position"], default="swing")
    s.set_defaults(func=cmd_show)

    rd = sub.add_parser("read", help="Highest-confidence engine read (abstains when weak)")
    rd.add_argument("symbol")
    rd.add_argument("--horizon", choices=["day", "swing", "position"], default="swing")
    rd.set_defaults(func=cmd_read)

    b = sub.add_parser("best")
    b.add_argument("symbol")
    b.add_argument("--horizon", choices=["day", "swing", "position"], default="swing")
    b.set_defaults(func=cmd_best)

    ns = ap.parse_args(raw)
    ns.json = True if want_json else bool(getattr(ns, "json", False))
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
