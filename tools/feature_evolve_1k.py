#!/usr/bin/env python3
"""Multi-model evaluate → feature mine → Sharpe-reward → meta-MLP → $1k growth test.

Pipeline (live-trading oriented):
  1) Rank contender models on a $1k-realistic options bag (cheap premium names)
  2) Mine features (price / momentum / vol / volume / structure DNA) with IC + stability
  3) Reward models by max(0, Sharpe) softmax weights  → ensemble vote prior
  4) Train a small sklearn MLP meta-labeler on walk-forward folds (no torch required)
  5) Emit report + META_ENSEMBLE.json for live routing (best return×Sharpe recipe)

Usage:
  .venv/bin/python tools/feature_evolve_1k.py
  .venv/bin/python tools/feature_evolve_1k.py --cash 1000 --quick
  .venv/bin/python tools/feature_evolve_1k.py --skip-bt   # feature+MLP only
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "poc_va_feature_evolve_1k"
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"

# $1k-realistic underlyings (ATM debit often fits 1 contract; skip MU mega-premium)
BAG_1K = ["IONQ.US", "HOOD.US", "APLD.US", "SOFI.US", "PLTR.US"]
# Secondary liquid bag for stress (still options DNA)
BAG_GROWTH = ["IONQ.US", "HOOD.US", "AVGO.US", "TSLA.US", "NVDA.US"]

CONTENDERS = [
    "v32_soft_react_opts",
    "v31_selective_nodes_opts",
    "v30_feedback_pro",
    "v28_feedback_opts",
    "v29_coldstart_opts",
    "v26_opts_evolve",
    "v22_opts_live",
    "v20b_macro_light",  # equity control
    "v23_devin_overlay",
    "v15_meta_xgb",
]

WINDOW = ("2024-08-01", "2026-07-11")
WINDOW_LATE = ("2025-07-01", "2026-07-11")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Feature engineering (LSE lesson + our structure DNA) ─────────────────────


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1 / n, adjust=False).mean()
    rd = dn.ewm(alpha=1 / n, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time features only (shifted for prediction of next return)."""
    o = df.copy()
    o.index = pd.to_datetime(o.index)
    if getattr(o.index, "tz", None) is not None:
        o.index = o.index.tz_localize(None)
    c = o["close"].astype(float)
    h = o["high"].astype(float) if "high" in o else c
    l = o["low"].astype(float) if "low" in o else c
    v = o["volume"].astype(float) if "volume" in o else pd.Series(1.0, index=o.index)

    f = pd.DataFrame(index=o.index)
    # Price / returns
    f["ret_1d"] = c.pct_change(1)
    f["ret_5d"] = c.pct_change(5)
    f["ret_20d"] = c.pct_change(20)
    sma20 = c.rolling(20, min_periods=10).mean()
    sma50 = c.rolling(50, min_periods=20).mean()
    sma200 = c.rolling(200, min_periods=50).mean()
    f["dist_sma20"] = (c - sma20) / sma20
    f["dist_sma50"] = (c - sma50) / sma50
    f["dist_sma200"] = (c - sma200) / sma200
    f["gap"] = (o.get("open", c) - c.shift(1)) / c.shift(1)
    f["range"] = (h - l) / c.replace(0, np.nan)
    f["body"] = (c - o.get("open", c)).abs() / (h - l).replace(0, np.nan)

    # Momentum
    f["rsi_14"] = _rsi(c, 14)
    macd = _ema(c, 12) - _ema(c, 26)
    f["macd"] = macd
    f["macd_hist"] = macd - _ema(macd, 9)
    f["roc_10"] = c.pct_change(10)

    # Volatility
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    f["atr_14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    f["atr_pct"] = f["atr_14"] / c
    logret = np.log(c / c.shift(1))
    f["hvol_20"] = logret.rolling(20, min_periods=10).std() * np.sqrt(252)
    bb_mid = sma20
    bb_std = c.rolling(20, min_periods=10).std()
    f["bb_width"] = (2 * bb_std * 2) / bb_mid  # 2σ bands width / mid

    # Volume
    vol_sma = v.rolling(20, min_periods=10).mean()
    f["rvol"] = v / vol_sma.replace(0, np.nan)
    sign = np.sign(c.diff()).fillna(0.0)
    f["obv_slope"] = (sign * v).rolling(10, min_periods=5).sum() / vol_sma.replace(0, np.nan)
    tp = (h + l + c) / 3.0
    vwap = (tp * v).rolling(20, min_periods=10).sum() / v.rolling(20, min_periods=10).sum()
    f["vwap_dist"] = (c - vwap) / vwap

    # Structure DNA (lightweight cloud + room proxy)
    ef, em, es = _ema(c, 8), _ema(c, 21), _ema(c, 55)
    f["cloud_bull"] = ((ef > em) & (em > es) & (c >= em)).astype(float)
    f["cloud_bear"] = ((ef < em) & (em < es) & (c <= em)).astype(float)
    # Prior 20d high as "resistance room"
    high20 = h.rolling(20, min_periods=10).max().shift(1)
    f["room_pct"] = (high20 - c) / c

    # Target: next-day return (for IC / meta labels)
    f["fwd_ret_1d"] = c.pct_change(1).shift(-1)
    f["fwd_up"] = (f["fwd_ret_1d"] > 0).astype(int)

    # Point-in-time: all predictors known at close of day t for predicting t+1
    # (fwd_* are targets; features themselves use only past via rolling/pct_change)
    return f


def feature_diagnostics(frames: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """IC + stability across symbols and early/late halves."""
    feat_cols = [
        c
        for c in next(iter(frames.values())).columns
        if c not in ("fwd_ret_1d", "fwd_up")
    ]
    rows: list[dict[str, Any]] = []
    for col in feat_cols:
        ics: list[float] = []
        half_ics: list[float] = []
        for _sym, f in frames.items():
            sub = f[[col, "fwd_ret_1d"]].dropna()
            if len(sub) < 40:
                continue
            ic = float(sub[col].corr(sub["fwd_ret_1d"]))
            if math.isfinite(ic):
                ics.append(ic)
            mid = len(sub) // 2
            for chunk in (sub.iloc[:mid], sub.iloc[mid:]):
                if len(chunk) < 25:
                    continue
                hic = float(chunk[col].corr(chunk["fwd_ret_1d"]))
                if math.isfinite(hic):
                    half_ics.append(hic)
        if not ics:
            continue
        mean_ic = float(np.mean(ics))
        # Stability: fraction of half-windows with same sign as mean_ic
        if half_ics and abs(mean_ic) > 1e-9:
            same = sum(1 for x in half_ics if x * mean_ic > 0) / len(half_ics)
        else:
            same = 0.0
        # Redundancy proxy filled later
        rows.append(
            {
                "feature": col,
                "mean_ic": mean_ic,
                "abs_ic": abs(mean_ic),
                "ic_std": float(np.std(ics)) if len(ics) > 1 else 0.0,
                "n_symbols": len(ics),
                "stability": same,
                "score": abs(mean_ic) * (0.5 + 0.5 * same),
            }
        )
    rows.sort(key=lambda r: r["score"], reverse=True)

    # Independence: drop highly correlated with higher-ranked peer
    if frames:
        sample = next(iter(frames.values()))
        keep: list[dict] = []
        kept_names: list[str] = []
        for r in rows:
            col = r["feature"]
            redundant = False
            for k in kept_names:
                pair = sample[[col, k]].dropna()
                if len(pair) < 30:
                    continue
                corr = abs(float(pair[col].corr(pair[k])))
                if corr > 0.92:
                    redundant = True
                    r["redundant_with"] = k
                    r["corr_with_peer"] = corr
                    break
            r["selected"] = not redundant and r["score"] >= 0.01
            if r["selected"]:
                keep.append(r)
                kept_names.append(col)
            else:
                if "redundant_with" not in r:
                    r["selected"] = r["score"] >= 0.015  # allow weak if not redundant
                    if r["selected"]:
                        keep.append(r)
                        kept_names.append(col)
        # Mark selected on full list
        sel_set = {x["feature"] for x in keep if x.get("selected")}
        for r in rows:
            if r["feature"] in sel_set:
                r["selected"] = True
    return rows


# ── Meta MLP (walk-forward) ──────────────────────────────────────────────────


def train_meta_mlp(
    frames: dict[str, pd.DataFrame],
    selected_feats: list[str],
    n_splits: int = 4,
) -> dict[str, Any]:
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, roc_auc_score

    parts = []
    for sym, f in frames.items():
        cols = selected_feats + ["fwd_up", "fwd_ret_1d"]
        sub = f[cols].dropna().copy()
        sub["symbol"] = sym
        parts.append(sub)
    if not parts:
        return {"error": "no data"}
    data = pd.concat(parts).sort_index()
    if len(data) < 120:
        return {"error": f"too few rows ({len(data)})"}

    X_all = data[selected_feats].to_numpy(float)
    y_all = data["fwd_up"].to_numpy(int)
    rets = data["fwd_ret_1d"].to_numpy(float)
    n = len(data)
    fold_size = n // (n_splits + 1)
    fold_metrics = []
    oos_pred = np.full(n, np.nan)
    oos_proba = np.full(n, np.nan)

    for k in range(n_splits):
        train_end = fold_size * (k + 1)
        test_end = fold_size * (k + 2) if k < n_splits - 1 else n
        if train_end < 80 or test_end - train_end < 20:
            continue
        X_tr, y_tr = X_all[:train_end], y_all[:train_end]
        X_te, y_te = X_all[train_end:test_end], y_all[train_end:test_end]
        r_te = rets[train_end:test_end]
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)
        clf = MLPClassifier(
            hidden_layer_sizes=(32, 16),
            activation="relu",
            solver="adam",
            max_iter=400,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42 + k,
            learning_rate_init=0.001,
        )
        clf.fit(X_tr_s, y_tr)
        proba = clf.predict_proba(X_te_s)[:, 1]
        pred = (proba >= 0.55).astype(int)
        oos_pred[train_end:test_end] = pred
        oos_proba[train_end:test_end] = proba
        acc = float(accuracy_score(y_te, pred))
        try:
            auc = float(roc_auc_score(y_te, proba))
        except ValueError:
            auc = float("nan")
        # Long-only when proba high: strategy return
        strat = np.where(proba >= 0.55, r_te, 0.0)
        sharpe = float(np.mean(strat) / (np.std(strat) + 1e-12) * np.sqrt(252))
        fold_metrics.append(
            {
                "fold": k,
                "train_end": int(train_end),
                "test_n": int(test_end - train_end),
                "accuracy": acc,
                "auc": auc,
                "sharpe_long_filter": sharpe,
                "coverage": float(pred.mean()),
            }
        )

    mask = np.isfinite(oos_proba)
    if mask.sum() > 30:
        strat = np.where(oos_proba[mask] >= 0.55, rets[mask], 0.0)
        overall_sh = float(np.mean(strat) / (np.std(strat) + 1e-12) * np.sqrt(252))
        bh = rets[mask]
        bh_sh = float(np.mean(bh) / (np.std(bh) + 1e-12) * np.sqrt(252))
    else:
        overall_sh = bh_sh = float("nan")

    # Fit final model on all but last 15% for live artifact
    cut = int(n * 0.85)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X_all[:cut])
    final = MLPClassifier(
        hidden_layer_sizes=(32, 16),
        activation="relu",
        max_iter=500,
        early_stopping=True,
        validation_fraction=0.12,
        random_state=7,
    )
    final.fit(Xs, y_all[:cut])

    return {
        "selected_features": selected_feats,
        "n_rows": n,
        "folds": fold_metrics,
        "oos_sharpe_long_filter": overall_sh,
        "buy_hold_sharpe": bh_sh,
        "mean_fold_acc": float(np.nanmean([m["accuracy"] for m in fold_metrics])) if fold_metrics else None,
        "mean_fold_auc": float(np.nanmean([m["auc"] for m in fold_metrics])) if fold_metrics else None,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "mlp": {
            "hidden_layer_sizes": [32, 16],
            "n_features": len(selected_feats),
            "classes": final.classes_.tolist(),
            "note": "Weights not exported as raw arrays (sklearn); retrain live or use XGB meta path. "
            "Feature list + thresholds are the portable live contract.",
        },
        "live_rule": {
            "enter_if_proba_ge": 0.55,
            "size_mult_if_proba_ge_0_65": 1.15,
            "size_mult_if_proba_lt_0_50": 0.0,
            "fallback_if_mlp_unavailable": "use_reward_weights_only",
        },
    }


# ── Model ranking @ $1k ──────────────────────────────────────────────────────


def rank_models_1k(cash: float, quick: bool, reuse: bool) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "tools"))
    from dynamic_model_rank import discover_models, run_one  # noqa: WPS433

    only = CONTENDERS
    models = discover_models(only)
    by_id = {m["id"]: m for m in models}
    models = [by_id[i] for i in only if i in by_id]

    screen_rows = []
    for m in models:
        mode = "options" if any(
            h in m["id"].lower()
            for h in (
                "opts",
                "feedback",
                "soft_react",
                "coldstart",
                "selective",
                "flip",
                "vpa",
            )
        ) or m.get("has_hunt") else "daily"
        if "macro" in m["id"] or "meta_xgb" in m["id"] or "devin" in m["id"]:
            mode = "daily"
        screen_rows.append(
            run_one(
                m,
                mode=mode,
                codes=BAG_1K,
                start=WINDOW[0],
                end=WINDOW[1],
                tag="bag_1k",
                force_1d=True,
                reuse=reuse,
                cash=cash,
            )
        )

    ok = [r for r in screen_rows if not r.get("error") and r.get("n", 0) > 0]
    # Primary sort: Sharpe (live quality), then return, then low DD
    ok.sort(
        key=lambda r: (
            float(r.get("sharpe") or 0.0),
            float(r.get("ret") or 0.0),
            -abs(float(r.get("dd") or 0.0)),
        ),
        reverse=True,
    )
    fail = [r for r in screen_rows if r.get("error") or r.get("n", 0) == 0]

    # Late window stress on top 4
    deep: dict[str, list] = {}
    top = ok[: (3 if quick else 5)]
    for r in top:
        mid = r["id"]
        m = by_id[mid]
        mode = r["mode"]
        deep[mid] = [
            run_one(
                m,
                mode=mode,
                codes=BAG_1K,
                start=WINDOW_LATE[0],
                end=WINDOW_LATE[1],
                tag="bag_1k_late",
                force_1d=True,
                reuse=reuse,
                cash=cash,
            )
        ]
        if not quick and mode == "options":
            deep[mid].append(
                run_one(
                    m,
                    mode=mode,
                    codes=BAG_GROWTH,
                    start=WINDOW[0],
                    end=WINDOW[1],
                    tag="bag_growth",
                    force_1d=True,
                    reuse=reuse,
                    cash=cash,
                )
            )

    return {
        "cash": cash,
        "bag": BAG_1K,
        "window": WINDOW,
        "screen": ok + fail,
        "deep": deep,
        "by_sharpe": [r["id"] for r in ok],
    }


def reward_weights(screen: list[dict[str, Any]], temperature: float = 0.35) -> dict[str, float]:
    """Softmax over max(0, sharpe) — reward models that grow capital with risk control."""
    scored = []
    for r in screen:
        if r.get("error") or r.get("n", 0) == 0:
            continue
        sh = float(r.get("sharpe") or 0.0)
        ret = float(r.get("ret") or 0.0)
        # Reward only positive risk-adj; slight return bonus
        utility = max(sh, 0.0) + 0.15 * max(ret, 0.0)
        scored.append((r["id"], utility, sh, ret))
    if not scored:
        return {}
    utils = np.array([u for _, u, _, _ in scored], dtype=float)
    # temperature: lower = more peaky on best
    exp = np.exp((utils - utils.max()) / max(temperature, 1e-3))
    w = exp / exp.sum()
    return {
        scored[i][0]: {
            "weight": float(w[i]),
            "utility": float(scored[i][1]),
            "sharpe": float(scored[i][2]),
            "ret": float(scored[i][3]),
        }
        for i in range(len(scored))
    }


def load_ohlcv_yf(codes: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    for code in codes:
        t = code.replace(".US", "")
        raw = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0].lower() for c in raw.columns]
        else:
            raw.columns = [str(c).lower() for c in raw.columns]
        need = ["open", "high", "low", "close", "volume"]
        if not all(c in raw.columns for c in need):
            # yfinance sometimes Title Case
            rename = {c: c.lower() for c in raw.columns}
            raw = raw.rename(columns=rename)
        if "close" not in raw.columns:
            continue
        for c in need:
            if c not in raw.columns:
                raw[c] = raw["close"] if c != "volume" else 1.0
        out[code] = raw[need].dropna(subset=["close"])
    return out


def write_report(state: dict[str, Any]) -> Path:
    lines = [
        "# Feature Evolve @ $1k — Multi-Model → Meta-MLP",
        "",
        f"Generated: `{state['updated_at']}`",
        f"Account: **${state['cash']:,.0f}** · bag: `{', '.join(state.get('bag', []))}`",
        "",
        "## 1) Model ranking (Sharpe-first for live)",
        "",
        "| Rank | Model | Mode | Sharpe | Ret% | $ PnL | MaxDD% | n | WR% | Reward w |",
        "|------|-------|------|--------|------|-------|--------|---|-----|----------|",
    ]
    rewards = state.get("rewards") or {}
    for i, r in enumerate(state.get("screen") or [], 1):
        if r.get("error") or r.get("n", 0) == 0:
            lines.append(f"| {i} | `{r['id']}` | {r.get('mode','')} | FAIL | — | — | — | 0 | — | 0 |")
            continue
        w = rewards.get(r["id"], {}).get("weight", 0.0)
        lines.append(
            f"| {i} | `{r['id']}` | {r.get('mode')} | {r.get('sharpe',0):.2f} | "
            f"{100*r.get('ret',0):.1f}% | ${r.get('pnl') or 0:+,.0f} | "
            f"{100*r.get('dd',0):.1f}% | {r.get('n',0)} | {100*r.get('wr',0):.0f}% | {w:.3f} |"
        )
    lines += [
        "",
        "## 2) Best features (IC × stability, de-correlated)",
        "",
        "| Feature | mean IC | stability | score | selected |",
        "|---------|---------|-----------|-------|----------|",
    ]
    for f in (state.get("features") or [])[:25]:
        lines.append(
            f"| `{f['feature']}` | {f['mean_ic']:+.4f} | {f['stability']:.0%} | "
            f"{f['score']:.4f} | {'✓' if f.get('selected') else ''} |"
        )

    meta = state.get("meta_mlp") or {}
    lines += [
        "",
        "## 3) Meta-MLP (walk-forward long filter)",
        "",
        f"- Features: `{', '.join(meta.get('selected_features') or [])}`",
        f"- OOS Sharpe (long when p≥0.55): **{meta.get('oos_sharpe_long_filter')}**",
        f"- Buy & hold Sharpe (same bars): {meta.get('buy_hold_sharpe')}",
        f"- Mean fold accuracy: {meta.get('mean_fold_acc')}",
        f"- Mean fold AUC: {meta.get('mean_fold_auc')}",
        "",
        "## 4) Live recipe (what to run)",
        "",
    ]
    recipe = state.get("live_recipe") or {}
    for k, v in recipe.items():
        lines.append(f"- **{k}**: `{v}`")
    lines += [
        "",
        "## 5) Feedback loop",
        "",
        "Winners (high reward weight + positive Sharpe) keep their DNA:",
        "",
    ]
    for mid, info in sorted(rewards.items(), key=lambda x: -x[1]["weight"])[:5]:
        lines.append(
            f"- `{mid}`: weight={info['weight']:.3f} sharpe={info['sharpe']:.2f} ret={100*info['ret']:.1f}%"
        )
    lines += [
        "",
        "Losers (weight≈0 or negative Sharpe) are demoted — do not blend hard filters from them "
        "(historical fail mode: v29/v30 hard stacks).",
        "",
        "Feature feedback: keep selected features with stability ≥50% and |IC| competitive; "
        "drop redundant pairs (corr>0.92).",
        "",
        f"Artifacts: `{OUT.relative_to(ROOT)}`",
        "",
    ]
    path = OUT / "EVOLVE_REPORT.md"
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Feature evolve + $1k multi-model Sharpe loop")
    ap.add_argument("--cash", type=float, default=1000.0)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--skip-bt", action="store_true", help="Skip model backtests (features+MLP only)")
    ap.add_argument("--no-reuse", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "tools"))
    # Isolate backtests under this run folder
    import dynamic_model_rank as dmr  # type: ignore  # noqa: WPS433

    dmr.OUT = OUT / "bt"
    dmr.CASH = float(args.cash)
    (OUT / "bt").mkdir(parents=True, exist_ok=True)

    state: dict[str, Any] = {
        "updated_at": _now(),
        "cash": float(args.cash),
        "bag": BAG_1K,
        "window": WINDOW,
    }

    if not args.skip_bt:
        print(f"======== RANK MODELS @ ${args.cash:,.0f} (Sharpe-first) ========", flush=True)
        rank = rank_models_1k(float(args.cash), args.quick, reuse=not args.no_reuse)
        state["screen"] = rank["screen"]
        state["deep"] = rank["deep"]
        state["rewards"] = reward_weights(rank["screen"])
        print("\n-- Reward weights (softmax Sharpe) --", flush=True)
        for mid, info in sorted(state["rewards"].items(), key=lambda x: -x[1]["weight"]):
            print(
                f"  {mid:28} w={info['weight']:.3f}  sh={info['sharpe']:.2f}  ret={100*info['ret']:.1f}%",
                flush=True,
            )
    else:
        state["screen"] = []
        state["rewards"] = {}

    print("\n======== FEATURE MINE (LSE toolkit + structure DNA) ========", flush=True)
    ohlcv = load_ohlcv_yf(BAG_1K, WINDOW[0], WINDOW[1])
    frames = {sym: build_features(df) for sym, df in ohlcv.items()}
    feats = feature_diagnostics(frames)
    state["features"] = feats
    selected = [f["feature"] for f in feats if f.get("selected")][:12]
    if not selected:
        selected = [f["feature"] for f in feats[:8]]
    print(f"Selected features ({len(selected)}): {selected}", flush=True)
    for f in feats[:12]:
        mark = "✓" if f.get("selected") else " "
        print(
            f"  {mark} {f['feature']:16} IC={f['mean_ic']:+.4f} stab={f['stability']:.0%} score={f['score']:.4f}",
            flush=True,
        )

    print("\n======== META-MLP (walk-forward) ========", flush=True)
    meta = train_meta_mlp(frames, selected)
    state["meta_mlp"] = meta
    if meta.get("error"):
        print(f"  MLP skip: {meta['error']}", flush=True)
    else:
        print(
            f"  OOS Sharpe filter={meta.get('oos_sharpe_long_filter')}  "
            f"BH={meta.get('buy_hold_sharpe')}  acc={meta.get('mean_fold_acc')}",
            flush=True,
        )

    # Live recipe: pick best model by reward weight among options modes, + feature gates
    best_model = None
    if state.get("rewards"):
        best_model = max(state["rewards"].items(), key=lambda x: x[1]["weight"])[0]
    elif state.get("screen"):
        ok = [r for r in state["screen"] if not r.get("error") and r.get("n", 0) > 0]
        if ok:
            best_model = ok[0]["id"]

    top_feats = selected[:6]
    state["live_recipe"] = {
        "primary_engine": best_model or "v32_soft_react_opts",
        "account_cash": float(args.cash),
        "universe_1k": BAG_1K,
        "objective": "max Sharpe then total return (grow $1k without blowing DD)",
        "reward_weights": {k: v["weight"] for k, v in (state.get("rewards") or {}).items()},
        "feature_gates_soft": top_feats,
        "meta_mlp_threshold": 0.55,
        "options_structure": "prefer debit calls/spreads; max 1 contract; risk_pct≈0.20; DTE 14",
        "do_not_use": [
            "hard entry kills from v29/v31 selective nodes",
            "MU ATM weeklies on $1k",
            "naked short premium",
        ],
        "rationale": (
            "Primary = highest Sharpe reward weight on $1k bag. "
            "Soft-size with structure DNA + MLP proba; never hard-block winners. "
            "Features selected by IC×stability, not vanity win-rate."
        ),
    }

    # Persist
    (OUT / "META_ENSEMBLE.json").write_text(json.dumps(state, indent=2, default=str))
    # Compact live config for trade desk / future engine
    live = {
        "version": "v36_sharpe_meta",
        "parent": best_model or "v32_soft_react_opts",
        "cash": float(args.cash),
        "codes": BAG_1K,
        "reward_weights": state["live_recipe"]["reward_weights"],
        "features": top_feats,
        "meta": {
            "threshold": 0.55,
            "boost_threshold": 0.65,
            "boost_mult": 1.15,
            "oos_sharpe": meta.get("oos_sharpe_long_filter"),
        },
        "hunt_overrides": {
            "initial_cash": float(args.cash),
            "max_contracts": 1,
            "risk_pct": 0.20,
            "dte_days": 14,
            "use_soft_structure": True,
            "struct_good_mult": 1.15,
            "struct_weak_mult": 0.55,
            "use_narrative": True,
            "narrative_mode": "surgical",
            "loss_cooloff_days": 10,
        },
        "updated_at": _now(),
    }
    live_path = MODELS_ROOT / "v36_sharpe_meta"
    live_path.mkdir(parents=True, exist_ok=True)
    (live_path / "LIVE_RECIPE.json").write_text(json.dumps(live, indent=2))
    (live_path / "HYPOTHESIS.md").write_text(
        f"""# v36_sharpe_meta

**Goal:** Grow a **${args.cash:,.0f}** account with the best **live Sharpe** recipe.

## Loop
1. Re-evaluate contender models on $1k options bag  
2. Mine features (IC × stability, de-correlated)  
3. Softmax-reward models by Sharpe (+ light return bonus)  
4. Walk-forward MLP meta filter on selected features  
5. Primary engine = highest reward weight; soft-size only  

## Parent
`{best_model or "v32_soft_react_opts"}`

## Selected features
{chr(10).join("- `" + f + "`" for f in top_feats)}

## Do not
- Hard-block entries (v29/v31 fail mode)
- Trade MU ATM on $1k
- Optimize for win-rate vanity

See `runs/poc_va_feature_evolve_1k/EVOLVE_REPORT.md` and `META_ENSEMBLE.json`.
"""
    )

    report = write_report(state)
    print(f"\nReport → {report}", flush=True)
    print(f"State  → {OUT / 'META_ENSEMBLE.json'}", flush=True)
    print(f"Live   → {live_path / 'LIVE_RECIPE.json'}", flush=True)
    if best_model:
        print(f"\n>>> LIVE PRIMARY: {best_model} (reward-weighted @ ${args.cash:,.0f})", flush=True)
    return 0


if __name__ == "__main__":
    # Allow `import dynamic_model_rank` from tools/
    sys.path.insert(0, str(ROOT / "tools"))
    raise SystemExit(main())
