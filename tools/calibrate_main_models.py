#!/usr/bin/env python3
"""Build honest live-confidence calibrators for the desk's main equity models.

Policy (no force / no fake confidence)
--------------------------------------
1. Fit isotonic maps from point-in-time (raw_probability → win label).
2. Promote to ``runs/calibration/active/<model>.json`` only when sequential OOS
   Brier **and** log-loss improve vs raw, n_oof ≥ 30, and ECE is not worse than
   raw by more than 1pp (absolute ECE ≤ 0.08 still preferred).
3. Portfolio gates use the model's own reconciled metrics as both baseline and
   candidate (delta 0): calibration remaps probability bands for live ENTER;
   it does not rewrite the historical portfolio path.

Sources
-------
- v39d / v39b: candidate ledgers (adj_proba + realized_r)
- v71 / v72: pair full-window trades with engine ``last_confidence`` at entry
- v50: pair trades with |signal weight| / signal_scale as conf proxy
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from evolve.calibration import (  # noqa: E402
    build_calibration_artifact,
    load_candidate_files,
    write_artifact,
)

MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
OUT_CAND = ROOT / "runs" / "calibration" / "candidates"
OUT_ACTIVE = ROOT / "runs" / "calibration" / "active"
DATA_1H = ROOT / "data_cache" / "1h"
DATA_LOCAL = ROOT / "data_cache" / "local"

def _metrics_from_results(model: str) -> tuple[float, float]:
    p = MODELS_ROOT / model / "results.json"
    if not p.exists():
        return 1.0, -0.20
    try:
        d = json.loads(p.read_text())
        port = d.get("portfolio") if isinstance(d.get("portfolio"), dict) else d
        sh = float(port.get("sharpe") or 1.0)
        dd = float(port.get("max_drawdown") or -0.20)
        return sh, dd
    except Exception:
        return 1.0, -0.20


def _discover_paths(model: str, name: str) -> list[str]:
    """Find candidates.csv or trades.csv under dynamic_rank runs for model."""
    root = ROOT / "runs" / "poc_va_dynamic_rank" / "runs" / model
    if not root.exists():
        return []
    hits = sorted(root.rglob(name), key=lambda p: p.stat().st_mtime, reverse=True)
    # Prefer larger / fuller files
    scored: list[tuple[int, str]] = []
    for h in hits[:40]:
        try:
            n = sum(1 for _ in h.open())
        except Exception:
            n = 0
        scored.append((n, str(h.relative_to(ROOT))))
    scored.sort(reverse=True)
    # Dedup near-identical sizes keep top 3 distinct paths
    out: list[str] = []
    for _, rel in scored:
        if rel not in out:
            out.append(rel)
        if len(out) >= 3:
            break
    return out


def build_main_model_registry() -> dict[str, dict[str, Any]]:
    """All desk-relevant models: standards + any with local evidence."""
    models: dict[str, dict[str, Any]] = {}

    # Core standards always attempted.
    core = [
        "v39d_confluence",
        "v39b_live_adapt",
        "v63_spy_prune",
        "v50_high_win_rate",
        "v71_live_confidence",
        "v72_dual_sleeve",
    ]
    for mid in core:
        sh, dd = _metrics_from_results(mid)
        ledgers = _discover_paths(mid, "candidates.csv")
        trades = _discover_paths(mid, "trades.csv")
        if ledgers:
            models[mid] = {"kind": "ledger", "ledgers": ledgers, "sharpe": sh, "dd": dd}
        elif trades:
            models[mid] = {
                "kind": "engine_trades",
                "trades": trades,
                "sharpe": sh,
                "dd": dd,
                "conf_from_weight": False,
            }
        else:
            # Still list for report as missing-evidence
            models[mid] = {
                "kind": "missing",
                "sharpe": sh,
                "dd": dd,
            }

    # Specialists with their own ledgers (small n → may inherit DNA if fail)
    for d in sorted((ROOT / "runs" / "poc_va_dynamic_rank" / "runs").glob("v65_spec_*")):
        mid = d.name
        ledgers = _discover_paths(mid, "candidates.csv")
        if not ledgers:
            continue
        sh, dd = _metrics_from_results(mid)
        models[mid] = {"kind": "ledger", "ledgers": ledgers, "sharpe": sh, "dd": dd}

    return models


# Built at import for CLI defaults; rebuild on main() for freshness.
MAIN_MODELS: dict[str, dict[str, Any]] = build_main_model_registry()


def _load_engine(model: str) -> Any:
    path = MODELS_ROOT / model / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(path)
    name = f"cal_eng_{model}_{id(path)}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _load_bars(code: str) -> pd.DataFrame | None:
    sym = code.replace(".US", "").upper()
    candidates = [
        DATA_1H / f"{sym}.parquet",
        DATA_LOCAL / "1h" / f"{sym}.parquet",
        DATA_LOCAL / f"{sym}.parquet",
        ROOT / "data_cache" / "yahoo" / "1h" / f"{sym}.parquet",
    ]
    for p in candidates:
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[-1] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={c: str(c).lower() for c in df.columns})
        need = {"open", "high", "low", "close", "volume"}
        if not need.issubset(set(df.columns)):
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            for col in ("date", "timestamp", "datetime"):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
                    df = df.set_index(col)
                    break
        if not isinstance(df.index, pd.DatetimeIndex):
            continue
        # Engines in this repo use tz-naive bar indices. Keep naive UTC wall time
        # so reindex/asof joins inside wrappers do not zero out every signal.
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        return df.sort_index()[["open", "high", "low", "close", "volume"]].astype(float)
    return None


def _pair_round_trips(trades: pd.DataFrame) -> pd.DataFrame:
    """Pair buy→sell per code into entry/exit rows with return_pct."""
    t = trades.copy()
    t["timestamp"] = pd.to_datetime(t["timestamp"], utc=True, errors="coerce")
    t = t.dropna(subset=["timestamp"]).sort_values(["code", "timestamp"])
    rows: list[dict[str, Any]] = []
    open_buy: dict[str, dict[str, Any]] = {}
    for _, r in t.iterrows():
        code = str(r["code"])
        side = str(r["side"]).lower()
        if side == "buy":
            open_buy[code] = r.to_dict()
        elif side == "sell" and code in open_buy:
            b = open_buy.pop(code)
            ret = r.get("return_pct")
            try:
                ret_f = float(ret) if ret is not None and ret == ret else np.nan
            except (TypeError, ValueError):
                ret_f = np.nan
            if not np.isfinite(ret_f):
                try:
                    ret_f = (float(r["price"]) - float(b["price"])) / float(b["price"])
                except Exception:
                    continue
            # trades often store return_pct in percent points (0.92 = 0.92%)
            if abs(ret_f) > 1.5:
                ret_f = ret_f / 100.0
            rows.append(
                {
                    "entry_ts": b["timestamp"],
                    "exit_ts": r["timestamp"],
                    "code": code,
                    "realized_r": ret_f,
                    "entry_px": float(b["price"]),
                    "exit_px": float(r["price"]),
                }
            )
    return pd.DataFrame(rows)


def _engine_conf_at_entries(
    model: str,
    trips: pd.DataFrame,
    *,
    conf_from_weight: bool = False,
) -> pd.DataFrame:
    """Replay engine once per symbol; asof-join confidence onto entry times."""
    if trips.empty:
        return trips
    eng = _load_engine(model)
    out_rows: list[dict[str, Any]] = []
    for code, g in trips.groupby("code"):
        bars = _load_bars(str(code))
        if bars is None or bars.empty:
            continue
        data_map = {str(code): bars, str(code).replace(".US", ""): bars}
        try:
            sigs = eng.generate(data_map)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] {model} generate({code}) failed: {exc}")
            continue
        conf_s: pd.Series | None = None
        raw_conf = getattr(eng, "last_confidence", None)
        if isinstance(raw_conf, dict) and raw_conf:
            cand = raw_conf.get(str(code))
            if cand is None:
                cand = raw_conf.get(str(code).replace(".US", ""))
            if cand is None:
                cand = next(iter(raw_conf.values()), None)
            if cand is not None:
                conf_s = pd.Series(cand).astype(float)
        if conf_s is None and conf_from_weight and isinstance(sigs, dict):
            sig = sigs.get(str(code))
            if sig is None and sigs:
                sig = next(iter(sigs.values()))
            if sig is not None:
                scale = 0.225
                try:
                    hunt = json.loads((MODELS_ROOT / model / "hunt_config.json").read_text())
                    scale = float(hunt.get("signal_scale") or scale)
                except Exception:
                    pass
                conf_s = (pd.Series(sig).astype(float).clip(lower=0.0) / max(scale, 1e-6)).clip(0.0, 1.0)
        if conf_s is None or conf_s.empty:
            continue
        if not isinstance(conf_s.index, pd.DatetimeIndex):
            continue
        if conf_s.index.tz is not None:
            conf_s.index = conf_s.index.tz_convert("UTC").tz_localize(None)
        conf_s = conf_s.sort_index()
        for _, row in g.iterrows():
            ts = pd.Timestamp(row["entry_ts"])
            if ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            # asof: last bar at or before entry (midnight trade date → EOD bar)
            hist = conf_s.loc[: ts + pd.Timedelta(hours=16)]
            if len(hist) == 0:
                continue
            p = float(hist.iloc[-1])
            if not np.isfinite(p):
                continue
            # Entry conf 0 with a real trade → nearby same-day max (bar timing skew)
            if p <= 0:
                day = conf_s.loc[ts.normalize() : ts.normalize() + pd.Timedelta(days=1)]
                day_pos = day[day > 0]
                if len(day_pos) == 0:
                    continue
                p = float(day_pos.max())
            exit_ts = pd.Timestamp(row["exit_ts"])
            if exit_ts.tzinfo is not None:
                exit_ts = exit_ts.tz_convert("UTC").tz_localize(None)
            out_rows.append(
                {
                    "entry_ts": ts,
                    "exit_ts": exit_ts,
                    "code": str(code),
                    "raw_probability": float(np.clip(p, 0.0, 1.0)),
                    "realized_r": float(row["realized_r"]),
                    "label": 1.0 if float(row["realized_r"]) > 0 else 0.0,
                }
            )
    return pd.DataFrame(out_rows)


def _frame_from_ledgers(paths: list[str]) -> pd.DataFrame:
    existing = [ROOT / p for p in paths if (ROOT / p).exists()]
    if not existing:
        raise FileNotFoundError(f"no ledgers found among {paths}")
    return load_candidate_files(existing)


def _frame_from_trades(model: str, trade_paths: list[str], conf_from_weight: bool) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for rel in trade_paths:
        p = ROOT / rel
        if not p.exists():
            continue
        trips = _pair_round_trips(pd.read_csv(p))
        if trips.empty:
            continue
        frames.append(trips)
    if not frames:
        raise FileNotFoundError(f"{model}: no trade CSVs found")
    trips = pd.concat(frames, ignore_index=True)
    trips = trips.drop_duplicates(subset=["entry_ts", "code", "realized_r"])
    ledger = _engine_conf_at_entries(model, trips, conf_from_weight=conf_from_weight)
    if ledger.empty:
        raise RuntimeError(f"{model}: engine replay produced 0 confidence-aligned trades")
    # Match ledger schema used by load_candidate_files: UTC-aware timestamps.
    for col in ("entry_ts", "exit_ts"):
        ledger[col] = pd.to_datetime(ledger[col], utc=True, errors="coerce")
    # purge_training_rows uses exit_ts; fill missing exits with entry.
    ledger["exit_ts"] = ledger["exit_ts"].fillna(ledger["entry_ts"])
    ledger = ledger.dropna(subset=["entry_ts", "raw_probability", "realized_r"])
    return ledger.reset_index(drop=True)


def justified_promotion(artifact: dict[str, Any]) -> tuple[bool, list[str]]:
    """Strict-but-fair activate decision: only if reliability improves."""
    metrics = artifact.get("metrics") or {}
    raw = metrics.get("raw_oof") or {}
    cal = metrics.get("calibrated_oof") or {}
    reasons: list[str] = []
    n = int((artifact.get("dataset") or {}).get("n_oof") or 0)
    brier_ok = float(cal.get("brier", 1)) <= float(raw.get("brier", 0))
    log_ok = float(cal.get("log_loss", 9)) <= float(raw.get("log_loss", 0))
    raw_ece = float(raw.get("ece", 1))
    cal_ece = float(cal.get("ece", 1))
    # Absolute target preferred; relative "not worse" allowed so sparse high-WR
    # sets aren't forced to fail a 0.05 ECE wall that raw also fails.
    ece_ok = cal_ece <= 0.08 or cal_ece <= raw_ece + 0.01
    action = artifact.get("action_band") or {}
    n_act = int(action.get("n") or 0)
    p05 = action.get("bootstrap_p05_mean_realized_r")
    action_ok = True
    if n_act >= 12:
        action_ok = p05 is not None and float(p05) > 0
    if n < 30:
        reasons.append(f"oos_n={n}<30")
    if not brier_ok:
        reasons.append(f"brier not improved ({cal.get('brier'):.4f} > {raw.get('brier'):.4f})")
    if not log_ok:
        reasons.append(
            f"log_loss not improved ({cal.get('log_loss'):.4f} > {raw.get('log_loss'):.4f})"
        )
    if not ece_ok:
        reasons.append(f"ece worse ({cal_ece:.3f} vs raw {raw_ece:.3f})")
    if n_act < 12:
        reasons.append(f"ENTER band thin (n={n_act}); expectancy not required")
    elif not action_ok:
        reasons.append(f"ENTER band expectancy not >0 (n={n_act}, p05={p05})")
    ok = bool(n >= 30 and brier_ok and log_ok and ece_ok and action_ok)
    return ok, reasons


def tune_thresholds_oof(
    frame: pd.DataFrame,
    *,
    n_splits: int = 5,
    embargo_hours: int = 1,
) -> dict[str, Any]:
    """Pick ENTER/WATCH on sequential OOF raw probs by expectancy (no isotonic).

    Sweep enter ∈ [0.45, 0.75], require n≥8 trades in band, maximize mean realized R
    with bootstrap p05 > 0. Watch is enter - 0.10 (floored at 0.40).
    """
    from evolve.calibration import _folds, bootstrap_mean_lower

    folds = _folds(frame, n_splits=n_splits, embargo=timedelta(hours=embargo_hours))
    if not folds:
        return {"enter": 0.60, "watch": 0.50, "ok": False, "reason": "no folds"}
    oof_parts = []
    for _train, test in folds:
        oof_parts.append(test[["raw_probability", "label", "realized_r"]].copy())
    oof = pd.concat(oof_parts, ignore_index=True)
    best: dict[str, Any] | None = None
    for enter in np.arange(0.45, 0.76, 0.025):
        band = oof[oof["raw_probability"] >= enter]
        n = int(len(band))
        if n < 8:
            continue
        mean_r = float(band["realized_r"].mean())
        p05 = bootstrap_mean_lower(band["realized_r"], seed=11)
        wr = float((band["realized_r"] > 0).mean())
        if p05 is None or p05 <= 0:
            continue
        # Score: mean R with light sample bonus
        score = mean_r + 0.002 * min(n, 40)
        row = {
            "enter": round(float(enter), 3),
            "watch": round(max(0.40, float(enter) - 0.10), 3),
            "n": n,
            "mean_r": mean_r,
            "p05": p05,
            "wr": wr,
            "score": score,
        }
        if best is None or score > best["score"]:
            best = row
    if best is None:
        return {
            "enter": 0.60,
            "watch": 0.50,
            "ok": False,
            "reason": "no enter threshold with p05>0 and n>=8",
            "oof_n": int(len(oof)),
        }
    best["ok"] = True
    best["oof_n"] = int(len(oof))
    best["reason"] = "max mean_R with bootstrap p05>0"
    return best


def build_identity_artifact(
    frame: pd.DataFrame,
    *,
    model: str,
    sharpe: float,
    dd: float,
    thresholds: dict[str, float],
    isotonic_artifact: dict[str, Any],
    threshold_meta: dict[str, Any],
) -> dict[str, Any]:
    """Build a candidate-only ordinal-score artifact.

    An identity transform does not calibrate a score into a probability, so it
    must never satisfy active runtime probability-calibration gates.
    """
    from evolve.calibration import calibration_metrics

    ordered = frame.sort_values("entry_ts").reset_index(drop=True)
    # Use same OOF slices as isotonic report for apples-to-apples metrics.
    raw_oof = (isotonic_artifact.get("metrics") or {}).get("raw_oof") or calibration_metrics(
        ordered["label"], ordered["raw_probability"]
    )
    enter = float(thresholds["enter"])
    watch = float(thresholds["watch"])
    band = ordered[ordered["raw_probability"] >= enter]
    from evolve.calibration import bootstrap_mean_lower

    p05 = bootstrap_mean_lower(band["realized_r"], seed=7) if len(band) >= 2 else None
    return {
        "schema_version": "confidence-calibration-v1",
        "status": "candidate",
        "model": model,
        "source": "local",
        "interval": "1H",
        "raw_probability": "engine_or_ledger",
        "label": "realized_r > 0",
        "calibration_type": "identity",
        "probability_semantics": "uncalibrated_ordinal_score_not_probability",
        "calibrated_probability_available": False,
        "runtime_eligible": False,
        "calibrator": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
        "thresholds": {"watch": watch, "enter": enter},
        "threshold_selection": threshold_meta,
        "dataset": {
            "n_rows": int(len(ordered)),
            "n_oof": int(isotonic_artifact.get("dataset", {}).get("n_oof") or len(ordered)),
            "start": ordered["entry_ts"].min().isoformat(),
            "end": ordered["entry_ts"].max().isoformat(),
            "folds": int(isotonic_artifact.get("dataset", {}).get("folds") or 0),
            "embargo_hours": 1,
        },
        "metrics": {
            "raw_oof": raw_oof,
            "calibrated_oof": raw_oof,  # identity: identical
            "raw_final_holdout": (isotonic_artifact.get("metrics") or {}).get("raw_final_holdout"),
            "final_holdout": (isotonic_artifact.get("metrics") or {}).get("raw_final_holdout"),
            "isotonic_rejected": {
                "brier": (isotonic_artifact.get("metrics") or {}).get("calibrated_oof", {}).get("brier"),
                "log_loss": (isotonic_artifact.get("metrics") or {}).get("calibrated_oof", {}).get("log_loss"),
                "ece": (isotonic_artifact.get("metrics") or {}).get("calibrated_oof", {}).get("ece"),
                "reason": "isotonic OOS reliability worse than raw — not activated",
            },
        },
        "action_band": {
            "n": int(len(band)),
            "mean_realized_r": float(band["realized_r"].mean()) if len(band) else None,
            "bootstrap_p05_mean_realized_r": p05,
            "enter": enter,
        },
        "promotion": {
            "all_calibration_gates_pass": False,
            "all_promotion_gates_pass": False,
            "justified_activate": False,
            "calibration_type": "identity",
            "justification": (
                "Isotonic OOS reliability gates failed. Identity preserves the raw "
                "ordinal score but is not probability calibration; retain only as "
                "research evidence and do not activate."
            ),
            "portfolio": {
                "candidate_sharpe": sharpe,
                "candidate_dd": dd,
                "baseline_sharpe": sharpe,
                "baseline_dd": dd,
                "sharpe_delta": 0.0,
                "drawdown_delta": 0.0,
                "inputs_present": True,
                "sharpe_gate": True,
                "drawdown_gate": True,
            },
        },
    }


def calibrate_one(model: str, cfg: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    print(f"\n=== {model} ({cfg['kind']}) ===")
    if cfg["kind"] == "missing":
        print("  no candidates.csv or trades.csv evidence — cannot calibrate honestly")
        return {
            "model": model,
            "activated": False,
            "justified": False,
            "mode": "missing_evidence",
            "error": "no ledger or trades evidence",
        }
    if cfg["kind"] == "ledger":
        frame = _frame_from_ledgers(list(cfg["ledgers"]))
    else:
        frame = _frame_from_trades(
            model,
            list(cfg["trades"]),
            conf_from_weight=bool(cfg.get("conf_from_weight")),
        )
    print(f"  rows={len(frame)}  label_rate={frame['label'].mean():.3f}  "
          f"p_mean={frame['raw_probability'].mean():.3f}")

    sh = float(cfg["sharpe"])
    dd = float(cfg["dd"])
    artifact = build_calibration_artifact(
        frame,
        model=model,
        source="local",
        interval="1H",
        n_splits=5,
        embargo_hours=1,
        candidate_sharpe=sh,
        candidate_dd=dd,
        baseline_sharpe=sh,
        baseline_dd=dd,
    )
    ok, reasons = justified_promotion(artifact)
    raw = artifact["metrics"]["raw_oof"]
    cal = artifact["metrics"]["calibrated_oof"]
    print(
        f"  OOF n={artifact['dataset']['n_oof']}  "
        f"brier {raw['brier']:.4f}→{cal['brier']:.4f}  "
        f"logloss {raw['log_loss']:.4f}→{cal['log_loss']:.4f}  "
        f"ece {raw['ece']:.3f}→{cal['ece']:.3f}"
    )
    print(f"  isotonic action_band n={artifact['action_band']['n']}  "
          f"mean_R={artifact['action_band']['mean_realized_r']}  "
          f"p05={artifact['action_band']['bootstrap_p05_mean_realized_r']}")
    print(f"  isotonic_justified={ok}  reasons={reasons or ['ok']}")

    cand_path = OUT_CAND / f"{model}.json"
    mode = "isotonic" if ok else "ordinal_identity_candidate"
    thr_meta = tune_thresholds_oof(frame)
    print(f"  threshold_tune: {thr_meta}")

    if not dry_run:
        write_artifact(artifact, cand_path, activate=False)
        active_path = OUT_ACTIVE / f"{model}.json"
        if ok:
            artifact["promotion"]["all_calibration_gates_pass"] = True
            artifact["promotion"]["all_promotion_gates_pass"] = True
            artifact["promotion"]["justified_activate"] = True
            artifact["promotion"]["calibration_type"] = "isotonic"
            artifact["promotion"]["justification"] = (
                "OOS Brier and log-loss improve vs raw; ECE not worse; "
                "portfolio delta 0 (calibrator remaps live bands only)"
            )
            # Prefer expectancy-tuned thresholds when available.
            if thr_meta.get("ok"):
                artifact["thresholds"] = {
                    "watch": thr_meta["watch"],
                    "enter": thr_meta["enter"],
                }
                artifact["threshold_selection"] = thr_meta
            write_artifact(artifact, active_path, activate=True, force=False)
            print(f"  ACTIVE (isotonic) → {active_path}")
        else:
            # Identity may preserve an ordinal score for threshold research,
            # but it cannot be activated as probability calibration.
            oof_n = int(thr_meta.get("oof_n") or 0)
            # Discrimination check: if raw conf is constant, thresholding is fake.
            p_std = float(frame["raw_probability"].std() or 0.0)
            p_nunique = int(frame["raw_probability"].nunique())
            # High-WR sleeves can clear with n_oof≥20 when ENTER band is real.
            min_oof = 20 if float(frame["label"].mean()) >= 0.75 else 30
            can_identity = (
                thr_meta.get("ok")
                and oof_n >= min_oof
                and p_std >= 0.02
                and p_nunique >= 3
                and int(thr_meta.get("n") or 0) >= 8
                and float(thr_meta.get("p05") or 0) > 0
            )
            if can_identity:
                identity = build_identity_artifact(
                    frame,
                    model=model,
                    sharpe=sh,
                    dd=dd,
                    thresholds={"enter": thr_meta["enter"], "watch": thr_meta["watch"]},
                    isotonic_artifact=artifact,
                    threshold_meta=thr_meta,
                )
                write_artifact(identity, OUT_CAND / f"{model}_identity.json", activate=False)
                mode = "ordinal_identity_candidate"
                print(
                    f"  CANDIDATE ONLY (uncalibrated ordinal score; "
                    f"research enter={thr_meta['enter']})  "
                    f"[isotonic rejected: {reasons[0] if reasons else 'n/a'}]"
                )
                reasons.append("identity_is_ordinal_not_probability_calibration")
                ok = False
            else:
                mode = "none"
                why = thr_meta.get("reason")
                if p_std < 0.02 or p_nunique < 5:
                    why = f"no confidence discrimination (std={p_std:.3f}, nunique={p_nunique})"
                elif oof_n < min_oof:
                    why = f"oof_n={oof_n}<{min_oof}"
                print(
                    f"  NOT ACTIVE → candidate only {cand_path} "
                    f"(isotonic hurts; identity blocked: {why})"
                )
    return {
        "model": model,
        "n": int(len(frame)),
        "n_oof": int(artifact["dataset"]["n_oof"]),
        "activated": bool(ok and not dry_run),
        "mode": mode,
        "justified": ok,
        "reasons": reasons,
        "thresholds": thr_meta if thr_meta.get("ok") else artifact.get("thresholds"),
        "brier_raw": raw["brier"],
        "brier_cal": cal["brier"],
        "log_loss_raw": raw["log_loss"],
        "log_loss_cal": cal["log_loss"],
        "ece_raw": raw["ece"],
        "ece_cal": cal["ece"],
        "action_n": artifact["action_band"]["n"],
        "action_p05": artifact["action_band"]["bootstrap_p05_mean_realized_r"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Calibrate main desk models honestly")
    ap.add_argument(
        "--models",
        default="",
        help="Comma list of models (default: all discoverable mains)",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--core-only",
        action="store_true",
        help="Only standard bag models (skip per-specialist ledgers)",
    )
    args = ap.parse_args(argv)
    registry = build_main_model_registry()
    if args.core_only:
        core = {
            "v39d_confluence",
            "v39b_live_adapt",
            "v63_spy_prune",
            "v50_high_win_rate",
            "v71_live_confidence",
            "v72_dual_sleeve",
        }
        registry = {k: v for k, v in registry.items() if k in core}
    if args.models.strip():
        wanted = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        wanted = list(registry.keys())
    summary: list[dict[str, Any]] = []
    for model in wanted:
        cfg = registry.get(model)
        if not cfg:
            print(f"skip unknown model {model}")
            continue
        try:
            summary.append(calibrate_one(model, cfg, dry_run=args.dry_run))
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {model}: {exc}")
            summary.append({"model": model, "error": str(exc), "activated": False, "justified": False})

    report_path = ROOT / "runs" / "calibration" / "MAIN_MODELS_REPORT.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "main-model-calibration-v2",
        "policy": (
            "no silent identity fallback at runtime; activate only with OOS evidence; "
            "isotonic only if Brier+logloss improve; identity maps remain candidate-only "
            "ordinal-score research artifacts; specialists without own map inherit v39d DNA"
        ),
        "models": summary,
        "active_dir": str(OUT_ACTIVE),
    }
    if not args.dry_run:
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nReport → {report_path}")
    print("\n=== SUMMARY ===")
    for row in summary:
        if row.get("error"):
            print(f"  {row['model']}: ERROR {row['error']}")
        else:
            flag = "ACTIVE" if row.get("activated") else ("JUSTIFIED" if row.get("justified") else "HOLD")
            br = row.get("brier_raw")
            bc = row.get("brier_cal")
            brier_s = f"{br:.4f}→{bc:.4f}" if br is not None and bc is not None else "n/a"
            print(
                f"  {row['model']}: {flag} mode={row.get('mode')}  "
                f"brier {brier_s}  n_oof={row.get('n_oof')}"
            )
    print(
        "\nRuntime: load_active_calibrator fails closed when no active artifact. "
        "v65_spec_* inherit v39d_confluence DNA map (documented alias, not invented)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
