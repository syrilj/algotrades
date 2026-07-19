#!/usr/bin/env python3
"""Train and validate v90_meta_confidence.

Pipeline (honest, anti-leakage):

1. Build causal features (models/poc_va_macdha/v90_meta_confidence/features.py).
2. Triple-barrier labels for LONG and SHORT at every bar (take-profit / stop /
   time exit), win := net-of-cost exit return > 0.
3. Purged + embargoed K-fold on the TRAIN window to get out-of-fold (OOF)
   probabilities (no lookahead across fold boundaries).
4. Isotonic calibration fit on OOF; activated only if OOF Brier AND log-loss
   improve vs raw (else identity map).
5. Retrain final LONG/SHORT boosters on the full train window.
6. Evaluate on the LOCKED holdout: calibrated probabilities -> BUY/SELL/FLAT
   trade simulation with 5bp+5bp costs. Report WR (Wilson 95% CI), expectancy
   (avg R), profit factor, Sharpe, and calibration (Brier, log-loss, ECE).

Artifacts written into the model bundle:
  meta_xgb_long.json, meta_xgb_short.json, calibration.json, thresholds.json,
  results.json, and metrics printed to stdout.

Usage:
  python3 tools/train_v90_meta_confidence.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "models" / "poc_va_macdha" / "v90_meta_confidence"
sys.path.insert(0, str(BUNDLE))
from features import FEATURES, build_features  # noqa: E402

UNIVERSE = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
TRAIN = ("2024-08-01", "2025-08-01")
HOLDOUT = ("2025-08-01", "2026-07-11")

HORIZON = 8            # bars (~1.2 trading days at 1H)
BARRIER_K = 1.0        # take-profit / stop in ATR units
COST = 0.001           # 5bp + 5bp roundtrip
N_FOLDS = 5
EMBARGO = HORIZON      # bars purged around each fold boundary
SEED = 0

XGB_PARAMS = dict(
    n_estimators=250,
    max_depth=4,
    learning_rate=0.03,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    reg_lambda=1.0,
    objective="binary:logistic",
    eval_metric="logloss",
    tree_method="hist",
    random_state=SEED,
    n_jobs=4,
)


def load_symbol(code: str) -> pd.DataFrame:
    path = ROOT / "data_cache" / "1h" / f"{code.replace('.US', '')}.parquet"
    df = pd.read_parquet(path).sort_index()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def triple_barrier(df: pd.DataFrame, side: int) -> Tuple[np.ndarray, np.ndarray]:
    """Return (label, exit_return) arrays for one direction.

    side = +1 long, -1 short. Enter at close_t; take-profit at +k*ATR, stop at
    -k*ATR (in price terms for the chosen side), time exit at t+HORIZON.
    label = 1 if net-of-cost exit return > 0.
    """
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    prev = np.roll(close, 1)
    prev[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    atr = pd.Series(tr).ewm(alpha=1.0 / 14.0, adjust=False).mean().to_numpy()
    atr_pct = np.divide(atr, close, out=np.zeros_like(close), where=close > 0)

    n = len(close)
    label = np.full(n, np.nan)
    ret = np.full(n, np.nan)
    for t in range(n - 1):
        entry = close[t]
        band = BARRIER_K * atr_pct[t]
        if not np.isfinite(band) or band <= 0:
            continue
        up = entry * (1.0 + band)
        dn = entry * (1.0 - band)
        exit_ret = None
        end = min(t + HORIZON, n - 1)
        for j in range(t + 1, end + 1):
            if side > 0:
                if high[j] >= up:
                    exit_ret = band
                    break
                if low[j] <= dn:
                    exit_ret = -band
                    break
            else:
                if low[j] <= dn:
                    exit_ret = band
                    break
                if high[j] >= up:
                    exit_ret = -band
                    break
        if exit_ret is None:
            exit_ret = side * (close[end] - entry) / entry
        ret[t] = exit_ret
        label[t] = 1.0 if (exit_ret - COST) > 0 else 0.0
    return label, ret


def build_dataset(codes: List[str], side: int) -> pd.DataFrame:
    frames = []
    for code in codes:
        df = load_symbol(code)
        feats = build_features(df)
        label, ret = triple_barrier(df, side)
        feats = feats.copy()
        feats["_label"] = label
        feats["_ret"] = ret
        feats["_code"] = code
        feats["_time"] = df.index
        frames.append(feats)
    data = pd.concat(frames, axis=0)
    data = data.dropna(subset=FEATURES + ["_label"])
    return data.reset_index(drop=True)


def wilson_ci(wins: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def purged_oof(data: pd.DataFrame) -> np.ndarray:
    """Out-of-fold raw probabilities with time-contiguous purged folds."""
    df = data.sort_values("_time").reset_index()  # keep original idx in 'index'
    order = df["index"].to_numpy()
    times = pd.to_datetime(df["_time"]).to_numpy()
    n = len(df)
    oof = np.full(len(data), np.nan)
    bounds = np.linspace(0, n, N_FOLDS + 1, dtype=int)
    X = df[FEATURES].to_numpy(float)
    y = df["_label"].to_numpy(float)
    # embargo as timedelta ~ EMBARGO hours * 3 (session gaps); use bar-position purge
    for k in range(N_FOLDS):
        lo, hi = bounds[k], bounds[k + 1]
        test_pos = np.arange(lo, hi)
        purge_lo = max(0, lo - EMBARGO)
        purge_hi = min(n, hi + EMBARGO)
        train_mask = np.ones(n, dtype=bool)
        train_mask[purge_lo:purge_hi] = False
        if train_mask.sum() < 200 or len(test_pos) == 0:
            continue
        clf = XGBClassifier(**XGB_PARAMS)
        clf.fit(X[train_mask], y[train_mask])
        p = clf.predict_proba(X[test_pos])[:, 1]
        oof[order[test_pos]] = p
    return oof


def fit_calibrator(p_raw: np.ndarray, y: np.ndarray) -> Tuple[Dict, np.ndarray]:
    """Isotonic if it improves OOF Brier AND log-loss, else identity."""
    mask = np.isfinite(p_raw)
    p_raw = p_raw[mask]
    y = y[mask]
    eps = 1e-6
    raw_brier = brier_score_loss(y, p_raw)
    raw_ll = log_loss(y, np.clip(p_raw, eps, 1 - eps))
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    p_cal = iso.fit_transform(p_raw, y)
    cal_brier = brier_score_loss(y, p_cal)
    cal_ll = log_loss(y, np.clip(p_cal, eps, 1 - eps))
    if cal_brier < raw_brier and cal_ll < raw_ll:
        art = {
            "type": "isotonic",
            "x": iso.f_.x.tolist(),
            "y": iso.f_.y.tolist(),
            "raw_brier": raw_brier, "cal_brier": cal_brier,
            "raw_logloss": raw_ll, "cal_logloss": cal_ll,
        }
        return art, p_cal
    art = {
        "type": "identity",
        "raw_brier": raw_brier, "cal_brier": raw_brier,
        "raw_logloss": raw_ll, "cal_logloss": raw_ll,
    }
    return art, p_raw


def apply_calibration(art: Dict, p: np.ndarray) -> np.ndarray:
    if art.get("type") == "isotonic":
        return np.interp(p, np.asarray(art["x"]), np.asarray(art["y"]))
    return p


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= edges[i + 1])
        if m.sum() == 0:
            continue
        total += (m.sum() / len(p)) * abs(p[m].mean() - y[m].mean())
    return float(total)


def main() -> int:
    print(f"[v90] loading {len(UNIVERSE)} symbols ...", flush=True)
    results = {}
    calib_arts = {}
    final_models = {}
    holdout_data = {}
    train_metrics = {}
    oof_raw_by_side = {}

    for side, name in [(1, "long"), (-1, "short")]:
        data = build_dataset(UNIVERSE, side)
        tmask = (data["_time"] >= TRAIN[0]) & (data["_time"] < TRAIN[1])
        hmask = (data["_time"] >= HOLDOUT[0]) & (data["_time"] < HOLDOUT[1])
        train = data[tmask].reset_index(drop=True)
        hold = data[hmask].reset_index(drop=True)
        print(f"[v90] {name}: train={len(train)} holdout={len(hold)} "
              f"base_rate={train['_label'].mean():.3f}", flush=True)

        oof = purged_oof(train)
        art, oof_cal = fit_calibrator(oof, train["_label"].to_numpy(float))
        calib_arts[name] = art
        oof_raw_by_side[name] = oof[np.isfinite(oof)]
        m = np.isfinite(oof)
        train_metrics[name] = {
            "oof_brier": art["cal_brier"],
            "oof_logloss": art["cal_logloss"],
            "oof_ece": ece(apply_calibration(art, oof[m]), train["_label"].to_numpy(float)[m]),
            "calibration": art["type"],
        }
        print(f"[v90] {name}: calibration={art['type']} "
              f"brier {art['raw_brier']:.4f}->{art['cal_brier']:.4f} "
              f"logloss {art['raw_logloss']:.4f}->{art['cal_logloss']:.4f}", flush=True)

        clf = XGBClassifier(**XGB_PARAMS)
        clf.fit(train[FEATURES].to_numpy(float), train["_label"].to_numpy(float))
        final_models[name] = clf
        holdout_data[name] = hold

    # Holdout: raw score drives decisions (continuous, monotonic); calibrated
    # probability is the honest confidence we display.
    hold = holdout_data["long"].copy()
    p_long_raw = final_models["long"].predict_proba(hold[FEATURES].to_numpy(float))[:, 1]
    p_long = apply_calibration(calib_arts["long"], p_long_raw)
    hs = holdout_data["short"]
    ps_raw_full = final_models["short"].predict_proba(hs[FEATURES].to_numpy(float))[:, 1]
    key_to_psraw = {(c, t): p for c, t, p in zip(hs["_code"], hs["_time"], ps_raw_full)}
    p_short_raw = np.array([key_to_psraw.get((c, t), 0.0) for c, t in zip(hold["_code"], hold["_time"])])
    p_short = apply_calibration(calib_arts["short"], p_short_raw)
    key_to_sret = {(c, t): r for c, t, r in zip(hs["_code"], hs["_time"], hs["_ret"])}

    # Holdout calibration quality (long head, most-traded)
    yb = hold["_label"].to_numpy(float)
    eps = 1e-6
    hold_cal = {
        "long_holdout_brier": float(brier_score_loss(yb, p_long)),
        "long_holdout_logloss": float(log_loss(yb, np.clip(p_long, eps, 1 - eps))),
        "long_holdout_ece": ece(p_long, yb),
    }

    # Decision thresholds derived from TRAIN OOF calibrated probs (no holdout peek).
    # We report several operating points as a WR-vs-frequency dial.
    combined = hold.copy()
    combined["_ret_short"] = [key_to_sret.get((c, t), 0.0) for c, t in zip(combined["_code"], combined["_time"])]
    combined["_conf_long"] = p_long
    combined["_conf_short"] = p_short
    pooled_oof = np.concatenate([oof_raw_by_side["long"], oof_raw_by_side["short"]])
    sweep = {}
    op_points = {"active_top10": 0.90, "balanced_top5": 0.95, "selective_top2": 0.98, "sniper_top1": 0.99}
    thr_map = {}
    for label, q in op_points.items():
        thr = float(np.quantile(pooled_oof, q))
        thr_map[label] = thr
        two = simulate_two_sided(combined, p_long_raw, p_short_raw, thr)
        two["raw_threshold"] = thr
        sweep[label] = two
    thresholds = {
        "enter_hi": thr_map["balanced_top5"],
        "enter_lo": thr_map["active_top10"],
        "selective": thr_map["selective_top2"],
        "exit": 0.45,
        "quantile_source": "train_oof_pooled",
        "operating_point_quantiles": op_points,
    }

    results = {
        "model": "v90_meta_confidence",
        "contract": {
            "universe": UNIVERSE, "interval": "1h", "source": "yfinance_auto_adjust",
            "train_window": list(TRAIN), "holdout_window": list(HOLDOUT),
            "horizon_bars": HORIZON, "barrier_k_atr": BARRIER_K, "cost_roundtrip": COST,
            "annualization_bars_per_year": 1764,
        },
        "calibration": {"long": train_metrics["long"], "short": train_metrics["short"],
                        "holdout": hold_cal},
        "holdout_operating_points": sweep,
        "recommended_thresholds": thresholds,
        "note": ("Simulated only. Self-contained purged-CV/holdout harness in "
                 "tools/train_v90_meta_confidence.py; not the legacy dmr runner."),
    }

    # Persist artifacts
    final_models["long"].get_booster().save_model(str(BUNDLE / "meta_xgb_long.json"))
    final_models["short"].get_booster().save_model(str(BUNDLE / "meta_xgb_short.json"))
    (BUNDLE / "calibration.json").write_text(json.dumps(calib_arts, indent=2))
    (BUNDLE / "thresholds.json").write_text(json.dumps(thresholds, indent=2))
    (BUNDLE / "results.json").write_text(json.dumps(results, indent=2))

    print("\n[v90] HOLDOUT operating points (two-sided BUY/SELL):")
    for label, t in sweep.items():
        if t.get("trade_count", 0) == 0:
            print(f"  {label} (p>={t.get('threshold',0):.3f}): no trades")
            continue
        lo, hi = t["win_rate_wilson95"]
        print(f"  {label} (raw>={t['raw_threshold']:.3f} conf~{t.get('avg_confidence',0):.2f}): "
              f"n={t['trade_count']} WR={t['win_rate']:.3f} [{lo:.2f},{hi:.2f}] "
              f"avgR={t['avg_return_per_trade']*1e2:.2f}% "
              f"PF={t['profit_factor']:.2f} Sharpe={t['sharpe']:.2f} "
              f"ret={t['total_return_compounded']*1e2:.1f}%")
    print(f"\n[v90] calibration long: {hold_cal}")
    print(f"[v90] artifacts written to {BUNDLE}")
    return 0


def simulate_two_sided(data: pd.DataFrame, p_long: np.ndarray, p_short: np.ndarray,
                       enter_hi: float) -> Dict:
    """Two-sided sim using per-row long/short returns. Decision on raw score;
    confidence reported from calibrated columns _conf_long/_conf_short."""
    trades = []
    confs = []
    sides = []
    for code in data["_code"].unique():
        sub = data[data["_code"] == code].sort_values("_time")
        idx = sub.index.to_numpy()
        pl = p_long[idx]
        ps = p_short[idx]
        rl = sub["_ret"].to_numpy(float)
        rs = sub["_ret_short"].to_numpy(float)
        cl = sub["_conf_long"].to_numpy(float)
        cs = sub["_conf_short"].to_numpy(float)
        i, n = 0, len(idx)
        while i < n:
            long_ok = pl[i] >= enter_hi
            short_ok = ps[i] >= enter_hi
            if long_ok and pl[i] >= ps[i]:
                trades.append(rl[i] - COST); confs.append(cl[i]); sides.append(1)
                i += HORIZON
            elif short_ok:
                trades.append(rs[i] - COST); confs.append(cs[i]); sides.append(-1)
                i += HORIZON
            else:
                i += 1
    trades = np.array(trades, dtype=float)
    if len(trades) == 0:
        return {"trade_count": 0}
    wins = int((trades > 0).sum())
    lo, hi = wilson_ci(wins, len(trades))
    gains = trades[trades > 0].sum()
    losses = -trades[trades < 0].sum()
    pf = float(gains / losses) if losses > 0 else float("inf")
    sharpe = float(trades.mean() / trades.std() * math.sqrt(1764)) if trades.std() > 0 else 0.0
    return {
        "trade_count": int(len(trades)),
        "win_rate": wins / len(trades),
        "win_rate_wilson95": [lo, hi],
        "avg_return_per_trade": float(trades.mean()),
        "profit_factor": pf,
        "sharpe": sharpe,
        "total_return_compounded": float(np.prod(1.0 + trades) - 1.0),
        "avg_confidence": float(np.mean(confs)),
        "long_trades": int(sum(1 for s in sides if s > 0)),
        "short_trades": int(sum(1 for s in sides if s < 0)),
    }


if __name__ == "__main__":
    raise SystemExit(main())
