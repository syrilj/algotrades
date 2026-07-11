"""Walk-forward meta-label XGBoost on REAL v13 engine-exit candidates.

Primary side stays v13 rules. This trains a secondary P(win) filter + size map.
Threshold is tuned on validation slice only (never on test).

Called by: CLI `python runs/poc_va_meta_xgb/train_meta_xgb.py`
Reads: artifacts/candidates.csv (from build_candidates.py)
Writes: artifacts/meta_xgb_report.json, fold boosters; on edge ships
        models/poc_va_macdha/v15_meta_xgb/; else NO_EDGE.md
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
ART = RUN / "artifacts"
MODEL_DIR = ROOT / "models" / "poc_va_macdha" / "v15_meta_xgb"
ART.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEAT_COLS = [
    "dist_poc",
    "dist_val",
    "dist_vwap",
    "ha_green",
    "above_vwap",
    "vol_expand",
    "macd_hist",
    "block_red_flag_on",
    "htf_green",
    "atr_pct",
    "conf",
    "spy_htf_green",
    "sym_TSLA",
    "sym_ARM",
    "sym_MU",
    "sym_SPY",
    "sym_IONQ",
    "sym_APLD",
]
LR = 0.04
MAX_DEPTH = 4
SUBSAMPLE = 0.8
REG_LAMBDA = 1.5
MIN_TRAIN = 60
MIN_TEST = 15
MIN_FOLDS_FOR_EDGE = 2
THR_GRID = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]


def _half_year_key(ts) -> str:
    t = pd.Timestamp(ts)
    return f"{t.year}H{(t.month - 1) // 6 + 1}"


def _fold_keys(df: pd.DataFrame) -> pd.Series:
    """Prefer half-year expanding folds when calendar years are too few."""
    hy = df["entry_ts"].map(_half_year_key)
    if hy.nunique() >= 3:
        return hy
    return df["year"].astype(str)


def _metrics(y: np.ndarray, pnl: np.ndarray, mask: np.ndarray) -> dict:
    if mask.sum() == 0:
        return {"n": 0, "hit_rate": float("nan"), "exp": float("nan")}
    yy = y[mask]
    pp = pnl[mask]
    return {"n": int(mask.sum()), "hit_rate": float(yy.mean()), "exp": float(pp.mean())}


def _tune_threshold(
    proba: np.ndarray, y: np.ndarray, pnl: np.ndarray
) -> tuple[float, dict]:
    best_thr = 0.55
    best = {"exp": -9.0, "hit_rate": 0.0, "n": 0}
    for thr in THR_GRID:
        m = proba >= thr
        met = _metrics(y, pnl, m)
        if met["n"] < max(5, int(0.15 * len(y))):
            continue
        if met["exp"] > best["exp"]:
            best = met
            best_thr = thr
    return best_thr, best


def walk_forward(df: pd.DataFrame) -> dict:
    df = df.sort_values("entry_ts").reset_index(drop=True)
    df = df.copy()
    df["fold_key"] = _fold_keys(df)
    keys = sorted(df["fold_key"].unique())
    folds = []
    imps = []
    models_saved = []

    for i, test_key in enumerate(keys):
        if i == 0:
            continue
        train = df[df["fold_key"] < test_key]
        test = df[df["fold_key"] == test_key]
        if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
            continue
        split = int(len(train) * 0.8)
        if split < 30 or len(train) - split < 10:
            continue
        Xtr = train[FEAT_COLS].iloc[:split].fillna(0.0)
        ytr = train["y"].iloc[:split].astype(int)
        Xva = train[FEAT_COLS].iloc[split:].fillna(0.0)
        yva = train["y"].iloc[split:].astype(int)
        pva = train["pnl"].iloc[split:].to_numpy()
        Xte = test[FEAT_COLS].fillna(0.0)
        yte = test["y"].astype(int).to_numpy()
        pte = test["pnl"].to_numpy()

        model = XGBClassifier(
            n_estimators=250,
            learning_rate=LR,
            max_depth=MAX_DEPTH,
            subsample=SUBSAMPLE,
            colsample_bytree=0.8,
            reg_lambda=REG_LAMBDA,
            min_child_weight=5,
            objective="binary:logistic",
            eval_metric="logloss",
            early_stopping_rounds=25,
            n_jobs=2,
        )
        model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
        va_proba = model.predict_proba(Xva)[:, 1]
        thr, va_met = _tune_threshold(va_proba, yva.to_numpy(), pva)
        te_proba = model.predict_proba(Xte)[:, 1]
        taken = te_proba >= thr

        base = _metrics(yte, pte, np.ones(len(yte), dtype=bool))
        filt = _metrics(yte, pte, taken)
        lift_hit = (
            filt["hit_rate"] - base["hit_rate"]
            if filt["n"] and base["n"]
            else float("nan")
        )
        lift_exp = (
            filt["exp"] - base["exp"] if filt["n"] and base["n"] else float("nan")
        )
        gain = pd.Series(model.feature_importances_, index=FEAT_COLS)
        imps.append(gain)
        fold = {
            "test_fold": str(test_key),
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "n_taken": int(taken.sum()),
            "threshold": thr,
            "val_tune": va_met,
            "base_hit_rate": base["hit_rate"],
            "filt_hit_rate": filt["hit_rate"],
            "base_exp": base["exp"],
            "filt_exp": filt["exp"],
            "lift_hit": lift_hit,
            "lift_exp": lift_exp,
            "best_iteration": int(getattr(model, "best_iteration", -1) or -1),
        }
        folds.append(fold)
        safe = str(test_key).replace("/", "_")
        booster_path = ART / f"meta_xgb_{safe}.json"
        model.save_model(booster_path)
        models_saved.append(str(booster_path))
        print(
            f"fold {test_key}: thr={thr} taken={fold['n_taken']}/{fold['n_test']} "
            f"lift_hit={lift_hit:.4f} lift_exp={lift_exp:.6f}"
        )

    if not folds:
        return {"folds": [], "edge": False, "reason": "insufficient_year_folds"}

    avg_lift_hit = float(np.nanmean([f["lift_hit"] for f in folds]))
    avg_lift_exp = float(np.nanmean([f["lift_exp"] for f in folds]))
    avg_filt_hit = float(np.nanmean([f["filt_hit_rate"] for f in folds]))
    avg_base_hit = float(np.nanmean([f["base_hit_rate"] for f in folds]))
    avg_filt_exp = float(np.nanmean([f["filt_exp"] for f in folds]))
    avg_base_exp = float(np.nanmean([f["base_exp"] for f in folds]))
    pos_exp_folds = sum(1 for f in folds if (f.get("lift_exp") or 0) > 0)
    # Edge needs multi-fold confirmation — single lucky OOS fold is not enough
    edge = bool(
        len(folds) >= MIN_FOLDS_FOR_EDGE
        and avg_lift_exp > 0
        and avg_lift_hit > 0.02
        and avg_filt_exp > 0
        and pos_exp_folds >= max(2, (len(folds) + 1) // 2)
    )
    avg_imp = pd.concat(imps, axis=1).mean(axis=1).sort_values(ascending=False)

    last_key = max(f["test_fold"] for f in folds)
    thr_final = float(np.median([f["threshold"] for f in folds]))
    train_all = df[df["fold_key"] < last_key]
    final_path: Path | None
    if len(train_all) >= MIN_TRAIN:
        split = int(len(train_all) * 0.85)
        final = XGBClassifier(
            n_estimators=250,
            learning_rate=LR,
            max_depth=MAX_DEPTH,
            subsample=SUBSAMPLE,
            colsample_bytree=0.8,
            reg_lambda=REG_LAMBDA,
            min_child_weight=5,
            objective="binary:logistic",
            eval_metric="logloss",
            early_stopping_rounds=25,
            n_jobs=2,
        )
        final.fit(
            train_all[FEAT_COLS].iloc[:split].fillna(0.0),
            train_all["y"].iloc[:split].astype(int),
            eval_set=[
                (
                    train_all[FEAT_COLS].iloc[split:].fillna(0.0),
                    train_all["y"].iloc[split:].astype(int),
                )
            ],
            verbose=False,
        )
        final_path = ART / "meta_xgb_final.json"
        final.save_model(final_path)
        models_saved.append(str(final_path))
    else:
        final_path = Path(models_saved[-1]) if models_saved else None

    return {
        "folds": folds,
        "avg_lift_hit": avg_lift_hit,
        "avg_lift_exp": avg_lift_exp,
        "avg_base_hit_rate": avg_base_hit,
        "avg_filt_hit_rate": avg_filt_hit,
        "avg_base_exp": avg_base_exp,
        "avg_filt_exp": avg_filt_exp,
        "pos_exp_folds": pos_exp_folds,
        "n_folds": len(folds),
        "feature_importance_gain": avg_imp.round(4).to_dict(),
        "edge": edge,
        "threshold": thr_final,
        "feat_cols": FEAT_COLS,
        "models": models_saved,
        "final_model": str(final_path) if final_path else None,
        "params": {
            "learning_rate": LR,
            "max_depth": MAX_DEPTH,
            "subsample": SUBSAMPLE,
            "reg_lambda": REG_LAMBDA,
            "label": "engine_exit_pnl_after_cost",
            "fold_scheme": "expanding_half_year_or_year",
        },
    }


def _ship_or_no_edge(report: dict) -> None:
    (ART / "meta_xgb_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    if report.get("edge") and report.get("final_model"):
        dest = MODEL_DIR / "meta_xgb_final.json"
        shutil.copy(report["final_model"], dest)
        cfg = {
            "feat_cols": report["feat_cols"],
            "threshold": report["threshold"],
            "size_map": {"low": 0.25, "mid": 0.5, "high": 1.0},
            "size_breaks": [0.55, 0.65],
            "params": report["params"],
            "oos": {
                "avg_lift_hit": report["avg_lift_hit"],
                "avg_lift_exp": report["avg_lift_exp"],
                "avg_filt_hit_rate": report["avg_filt_hit_rate"],
                "avg_filt_exp": report["avg_filt_exp"],
                "n_folds": report.get("n_folds"),
                "pos_exp_folds": report.get("pos_exp_folds"),
            },
        }
        (MODEL_DIR / "meta_config.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8"
        )
        (ART / "meta_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        no_edge = MODEL_DIR / "NO_EDGE.md"
        if no_edge.exists():
            no_edge.unlink()
        print("SHIP edge=true →", dest)
    else:
        for stale in ("meta_xgb_final.json", "meta_config.json", "signal_engine.py"):
            p = MODEL_DIR / stale
            if p.exists():
                p.unlink()
        no_edge = MODEL_DIR / "NO_EDGE.md"
        lines = [
            "# v15_meta_xgb — NO_EDGE",
            "",
            "True meta-labeler on v13 specialist candidates did **not** clear the OOS bar.",
            "",
            "## Decision rule",
            "- ≥2 expanding half-year (or year) OOS folds",
            "- avg OOS expectancy lift > 0",
            "- filt hit-rate lift > +2pp",
            "- filt expectancy > 0",
            "- majority of folds have positive expectancy lift",
            "",
            "## OOS results",
            f"- n_candidates: {report.get('n_candidates')}",
            f"- n_folds: {report.get('n_folds')}",
            f"- pos_exp_folds: {report.get('pos_exp_folds')}",
            f"- avg_base_hit_rate: {report.get('avg_base_hit_rate')}",
            f"- avg_filt_hit_rate: {report.get('avg_filt_hit_rate')}",
            f"- avg_lift_hit: {report.get('avg_lift_hit')}",
            f"- avg_base_exp: {report.get('avg_base_exp')}",
            f"- avg_filt_exp: {report.get('avg_filt_exp')}",
            f"- avg_lift_exp: {report.get('avg_lift_exp')}",
            f"- edge: {report.get('edge')}",
            f"- reason: {report.get('reason', 'metrics')}",
            "",
            "## Folds",
            "```json",
            json.dumps(report.get("folds", []), indent=2, default=str),
            "```",
            "",
            "## Recommendation",
            "Do **not** promote `v15_meta_xgb`. Leave WINNER unchanged.",
            "Next: Phase A longer OOS / Phase C better volume-profile data before more ML.",
            "",
            "## Re-run",
            "```bash",
            ".venv/bin/python runs/poc_va_meta_xgb/build_candidates.py",
            ".venv/bin/python runs/poc_va_meta_xgb/train_meta_xgb.py",
            "```",
            "",
        ]
        no_edge.write_text("\n".join(lines), encoding="utf-8")
        print("NO_EDGE wrote", no_edge)


def main() -> None:
    cand_path = ART / "candidates.csv"
    if not cand_path.exists():
        from build_candidates import main as build_main

        build_main()
    df = pd.read_csv(cand_path, parse_dates=["entry_ts", "exit_ts"])
    for c in FEAT_COLS:
        if c not in df.columns:
            df[c] = 0.0
    print(
        "candidates",
        len(df),
        "hit",
        float(df["y"].mean()),
        "exp",
        float(df["pnl"].mean()),
    )
    report = walk_forward(df)
    report["n_candidates"] = int(len(df))
    report["baseline_hit"] = float(df["y"].mean())
    report["baseline_exp"] = float(df["pnl"].mean())
    _ship_or_no_edge(report)
    print(
        "done edge=",
        report.get("edge"),
        "lift_hit=",
        report.get("avg_lift_hit"),
        "lift_exp=",
        report.get("avg_lift_exp"),
    )


if __name__ == "__main__":
    main()
