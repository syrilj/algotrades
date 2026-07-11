"""Walk-forward XGBoost filter research for poc_va rule candidates.

LSE guidance applied:
- tabular XGB for alpha (lr 0.05, max_depth 4, subsample 0.8, early stopping)
- walk-forward OOS only (no random CV)
- feature importance as SHAP-proxy (gain)

Writes: runs/poc_va_xgb/artifacts/xgb_report.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

TICKERS = {
    "SPY.US": "SPY",
    "QQQ.US": "QQQ",
    "AAPL.US": "AAPL",
    "MU.US": "MU",
    "TSLA.US": "TSLA",
}
START, END = "2018-01-01", "2026-07-11"
HORIZON = 5
COST = 0.002
TRAIN_YEARS = 3


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def features(df: pd.DataFrame) -> pd.DataFrame:
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    ret1 = c.pct_change()
    atr = (h - l).ewm(span=14, adjust=False).mean()
    macd = (_ema(c, 12) - _ema(c, 26)) / _ema(h - l, 26).replace(0, np.nan) * 100
    signal = _ema(macd, 9)
    hist = macd - signal
    ha_close = (macd + signal + hist + macd.shift(1).fillna(macd)) / 4.0
    ha_open = ((macd.shift(1) + signal.shift(1)) / 2.0).fillna(macd)
    ha_green = ha_close > ha_open
    vol_sma = v.rolling(20).mean()
    tp = (h + l + c) / 3.0
    vwap = (tp * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    above_vwap = c >= vwap
    poc = c.rolling(20).median()
    above_poc = c >= poc
    mom = c / c.shift(10) - 1.0
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + up / down.replace(0, np.nan)))
    out = pd.DataFrame(
        {
            "ret1": ret1,
            "atr_pct": atr / c,
            "macd_hist": hist,
            "ha_green": ha_green.astype(float),
            "above_vwap": above_vwap.astype(float),
            "above_poc": above_poc.astype(float),
            "vol_expand": (v / vol_sma).replace([np.inf, -np.inf], np.nan),
            "mom10": mom,
            "rsi": rsi,
            "dist_vwap": (c - vwap) / atr.replace(0, np.nan),
            "dist_poc": (c - poc) / atr.replace(0, np.nan),
        },
        index=df.index,
    )
    out["candidate"] = (
        out["ha_green"].eq(1.0)
        & out["above_vwap"].eq(1.0)
        & out["above_poc"].eq(1.0)
        & (out["vol_expand"] >= 1.0)
        & (out["macd_hist"] > 0)
    ).astype(int)
    fwd = c.shift(-HORIZON) / c - 1.0
    out["y"] = (fwd > COST).astype(float)
    out["fwd"] = fwd
    return out


def walk_forward(X: pd.DataFrame, y: pd.Series, fwd: pd.Series) -> dict:
    years = sorted(X.index.year.unique())
    folds = []
    importances = []
    for train_end in years:
        test_year = train_end + 1
        if test_year not in years:
            continue
        train_mask = (X.index.year >= test_year - TRAIN_YEARS) & (X.index.year <= train_end)
        test_mask = X.index.year == test_year
        Xtr, ytr = X.loc[train_mask], y.loc[train_mask]
        Xte, yte, fte = X.loc[test_mask], y.loc[test_mask], fwd.loc[test_mask]
        if len(Xtr) < 80 or len(Xte) < 20:
            continue
        model = XGBClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            min_child_weight=5,
            objective="binary:logistic",
            eval_metric="logloss",
            early_stopping_rounds=20,
            n_jobs=2,
        )
        split = int(len(Xtr) * 0.8)
        model.fit(
            Xtr.iloc[:split],
            ytr.iloc[:split],
            eval_set=[(Xtr.iloc[split:], ytr.iloc[split:])],
            verbose=False,
        )
        proba = model.predict_proba(Xte)[:, 1]
        thr = 0.55
        take = proba >= thr
        base_hits = float(yte.mean()) if len(yte) else 0.0
        filt_hits = float(yte[take].mean()) if take.any() else float("nan")
        base_exp = float(fte.mean()) if len(fte) else 0.0
        filt_exp = float(fte[take].mean()) if take.any() else float("nan")
        folds.append(
            {
                "test_year": int(test_year),
                "n_test": int(len(Xte)),
                "n_taken": int(take.sum()),
                "base_hit_rate": base_hits,
                "filt_hit_rate": filt_hits,
                "base_exp": base_exp,
                "filt_exp": filt_exp,
                "lift_hit": (filt_hits - base_hits) if take.any() else None,
                "lift_exp": (filt_exp - base_exp) if take.any() else None,
            }
        )
        importances.append(dict(zip(X.columns, model.feature_importances_.tolist())))
    if not folds:
        return {"folds": [], "edge": False}
    avg_lift_hit = np.nanmean([f["lift_hit"] for f in folds if f["lift_hit"] is not None])
    avg_lift_exp = np.nanmean([f["lift_exp"] for f in folds if f["lift_exp"] is not None])
    avg_filt_hit = np.nanmean(
        [f["filt_hit_rate"] for f in folds if f["filt_hit_rate"] == f["filt_hit_rate"]]
    )
    avg_imp = pd.DataFrame(importances).mean().sort_values(ascending=False)
    edge = bool(avg_lift_exp > 0.001 and avg_filt_hit > 0.52)
    return {
        "folds": folds,
        "avg_lift_hit": float(avg_lift_hit) if avg_lift_hit == avg_lift_hit else None,
        "avg_lift_exp": float(avg_lift_exp) if avg_lift_exp == avg_lift_exp else None,
        "avg_filt_hit_rate": float(avg_filt_hit) if avg_filt_hit == avg_filt_hit else None,
        "feature_importance_gain": avg_imp.round(4).to_dict(),
        "edge": edge,
        "params": {
            "learning_rate": 0.05,
            "max_depth": 4,
            "subsample": 0.8,
            "horizon": HORIZON,
            "threshold": 0.55,
        },
    }


def main() -> None:
    rows = []
    for code, ysym in TICKERS.items():
        raw = yf.download(ysym, start=START, end=END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        if raw.empty:
            continue
        feat = features(raw).dropna()
        cand = feat[feat["candidate"] == 1].copy()
        if len(cand) < 50:
            continue
        feat_cols = [
            "ret1",
            "atr_pct",
            "macd_hist",
            "ha_green",
            "above_vwap",
            "above_poc",
            "vol_expand",
            "mom10",
            "rsi",
            "dist_vwap",
            "dist_poc",
        ]
        report = walk_forward(cand[feat_cols], cand["y"], cand["fwd"])
        report["code"] = code
        report["n_candidates"] = int(len(cand))
        rows.append(report)
        print(
            code,
            "edge=",
            report["edge"],
            "filt_hit=",
            report.get("avg_filt_hit_rate"),
            "lift_exp=",
            report.get("avg_lift_exp"),
            "top=",
            list(report.get("feature_importance_gain", {}).keys())[:3],
        )

    summary = {
        "symbols": rows,
        "any_edge": any(r.get("edge") for r in rows),
        "best": max(rows, key=lambda r: (r.get("avg_lift_exp") or -9)) if rows else None,
    }
    out = ART / "xgb_report.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("wrote", out, "any_edge=", summary["any_edge"])


if __name__ == "__main__":
    main()
