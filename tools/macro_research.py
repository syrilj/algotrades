#!/usr/bin/env python3
"""v61 macro cross-asset research harness.

Loads a candidate ledger (default: v39d_confluence baseline), builds causal
macro/cross-asset/long-memory features per chronological fold, and tests whether
a small meta-logistic on v39d probability + macro features beats the raw v39d
probability out-of-fold.

Defaults use the available data cache.  LQD is used as a bond/rate proxy because
TLT is not present in the cache; VIX is the daily series.

Example:
  .venv/bin/python tools/macro_research.py --out runs/v61_macro_research
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add project root so imports like `tools/econ_narrative` work
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from evolve.macro_features import MacroCrossAssetEngine, parse_macro_calendar
from evolve.feature_validation import _fit_logistic, _predict
from evolve.calibration import _folds, calibration_metrics, bootstrap_mean_lower


def _load_bars(symbol: str, interval: str = "1h") -> pd.DataFrame:
    """Load OHLCV bars from data_cache."""
    sym = symbol.split(".", 1)[0].upper()
    p = ROOT / "data_cache" / interval / f"{sym}.parquet"
    if not p.exists():
        p = ROOT / "data_cache" / "1d" / f"{sym}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"no cached bars for {symbol} at {p}")
    df = pd.read_parquet(p).sort_index()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    return df


def _generate_macro_events(spy_df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Build a macro calendar from econ_narrative event dates.

    When no real actual/expected CSV is supplied, we use the SPY overnight/intro
    gap at the first bar after the release as a market-implied macro surprise.
    This is a proxy; replace with actual macro prints for real research.
    """
    from econ_narrative import FOMC_DATES, CPI_DATES, NFP_DATES

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    rows = []
    for date in FOMC_DATES:
        ts = pd.Timestamp(date) + pd.Timedelta(hours=14, minutes=30)
        if start_ts <= ts <= end_ts:
            rows.append({"release_ts": ts, "event_type": "FOMC"})
    for date in CPI_DATES:
        ts = pd.Timestamp(date) + pd.Timedelta(hours=9, minutes=30)
        if start_ts <= ts <= end_ts:
            rows.append({"release_ts": ts, "event_type": "CPI"})
    for date in NFP_DATES:
        ts = pd.Timestamp(date) + pd.Timedelta(hours=9, minutes=30)
        if start_ts <= ts <= end_ts:
            rows.append({"release_ts": ts, "event_type": "NFP"})

    events = pd.DataFrame(rows).sort_values("release_ts")
    if events.empty:
        return events

    spy = spy_df.sort_index()
    # open of the first bar after the release
    open_at = spy["open"].reindex(events["release_ts"], method="ffill").to_numpy()
    # close of the bar immediately before the release
    prev_close = spy["close"].shift(1).reindex(events["release_ts"], method="ffill").replace(0, np.nan).to_numpy()
    events["surprise"] = np.divide(open_at - prev_close, prev_close, out=np.full_like(open_at, np.nan, dtype=float), where=prev_close != 0) * 100.0
    events = events.dropna(subset=["surprise"])
    return events.reset_index(drop=True)


def _load_macro_events(path: Path | None, spy_df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if path is None or not path.exists():
        events = _generate_macro_events(spy_df, start, end)
    else:
        events = parse_macro_calendar(path)
    if events.empty:
        raise ValueError("no macro events found")
    return events


# Default macro feature columns used in the meta-selector.  A small set avoids
# overfitting on the candidate counts typically produced by v39d.
DEFAULT_MACRO_COLS = [
    "beta_spy_480",
    "corr_tlt_480",
    "vix_pct_low",
    "risk_on_score",
    "spy_momentum_1h",
    "macro_any_to_next_release_h",
    "macro_any_since_release_h",
    "macro_cpi_surprise_lag",
    "macro_fomc_surprise_lag",
    "macro_nfp_surprise_lag",
    "macro_surprise_x_risk_on",
    "macro_surprise_x_low_vix",
    "macro_surprise_x_low_vix_x_high_beta",
]


def _build_macro_features_for_symbol(
    symbol: str,
    engine: MacroCrossAssetEngine,
    spy_df: pd.DataFrame,
    lqd_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    events_df: pd.DataFrame,
    high_beta: float,
) -> pd.DataFrame:
    """Return macro features for a target symbol."""
    target = _load_bars(symbol)
    target["high_beta"] = float(high_beta)
    features = engine.transform(
        target,
        spy_df=spy_df,
        tlt_df=lqd_df,
        vix_df=vix_df,
        events_df=events_df,
    )
    return features


def _attach_features(
    candidates: pd.DataFrame,
    feature_store: dict[str, pd.DataFrame],
    max_lag: pd.Timedelta = pd.Timedelta(hours=2),
) -> pd.DataFrame:
    """Merge per-symbol macro features onto candidate rows."""
    rows = []
    for code, group in candidates.groupby("code", sort=False):
        sym = str(code).split(".", 1)[0]
        if sym not in feature_store:
            continue
        feats = feature_store[sym].reset_index().rename(columns={feature_store[sym].index.name or "index": "ts"})
        left = group.sort_values("entry_ts").copy()
        left["join_ts"] = pd.to_datetime(left["entry_ts"], utc=True).dt.tz_convert(None)
        joined = pd.merge_asof(
            left,
            feats,
            left_on="join_ts",
            right_on="ts",
            direction="backward",
            tolerance=max_lag,
        )
        rows.append(joined)
    if not rows:
        raise ValueError("no candidates matched macro features")
    return pd.concat(rows, ignore_index=True).sort_values("entry_ts").reset_index(drop=True)


def _evaluate(
    frame: pd.DataFrame,
    baseline_col: str,
    candidate_col: str,
    event_mask: pd.Series | None = None,
) -> dict[str, Any]:
    """Compare baseline and candidate probabilities."""
    full = calibration_metrics(frame["label"], frame[baseline_col])
    cand = calibration_metrics(frame["label"], frame[candidate_col])
    out = {
        "n": len(frame),
        "positive_rate": float(frame["label"].mean()),
        "baseline": {"brier": full["brier"], "log_loss": full["log_loss"], "ece": full["ece"]},
        "candidate": {"brier": cand["brier"], "log_loss": cand["log_loss"], "ece": cand["ece"]},
    }
    for threshold in (0.55, 0.60):
        action = frame[frame[candidate_col] >= threshold]
        action_lower = bootstrap_mean_lower(action["realized_r"]) if len(action) else None
        out[f"action_ret_threshold_{threshold}"] = {
            "n": len(action),
            "mean_ret": float(action["realized_r"].mean()) if len(action) else None,
            "lower_95": action_lower,
        }
    if event_mask is not None:
        event = frame[event_mask]
        non_event = frame[~event_mask]
        if len(event) and len(non_event):
            out["event_period"] = _evaluate(event, baseline_col, candidate_col, event_mask=None)
            out["non_event_period"] = _evaluate(non_event, baseline_col, candidate_col, event_mask=None)
    return out


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=ROOT / "runs/poc_va_dynamic_rank/runs/v39d_confluence/baseline_manifest_v1__daily__c1000/artifacts/candidates.csv")
    parser.add_argument("--macro-csv", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / "runs/v61_macro_research")
    parser.add_argument("--symbols", nargs="+", default=["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"])
    parser.add_argument("--start", default="2024-08-01")
    parser.add_argument("--end", default="2026-07-11")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--macro-cols", nargs="+", default=None)
    parser.add_argument("--use-market-surprise", action="store_true", default=True, help="fallback if --macro-csv missing")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.candidates.exists():
        print(f"Candidate ledger not found: {args.candidates}", file=sys.stderr)
        return 1

    # Load candidate ledger
    cand = pd.read_csv(args.candidates)
    cand["entry_ts"] = pd.to_datetime(cand["timestamp"], utc=True)
    cand["exit_ts"] = pd.to_datetime(cand["exit_timestamp"], utc=True)
    cand["raw_probability"] = pd.to_numeric(cand.get("adj_proba", cand.get("meta_proba")), errors="coerce")
    cand["realized_r"] = pd.to_numeric(cand["return_pct"], errors="coerce")
    cand["label"] = (cand["realized_r"] > 0).astype(float)
    cand = cand.dropna(subset=["entry_ts", "exit_ts", "raw_probability", "realized_r", "code"])
    start_ts = pd.Timestamp(args.start, tz="UTC")
    end_ts = pd.Timestamp(args.end, tz="UTC")
    cand = cand[(cand["entry_ts"] >= start_ts) & (cand["entry_ts"] <= end_ts)]
    if len(cand) < 30:
        print("Too few candidates after filtering", file=sys.stderr)
        return 1

    # Load cross-asset bars
    spy_df = _load_bars("SPY.US")
    lqd_df = _load_bars("LQD.US")
    vix_df = _load_bars("VIX.US", interval="1d")

    # Macro events
    events_df = _load_macro_events(args.macro_csv, spy_df, args.start, args.end)
    if not args.use_market_surprise and (args.macro_csv is None or not args.macro_csv.exists()):
        print("No macro CSV and --use-market-surprise disabled; aborting", file=sys.stderr)
        return 1

    macro_cols = args.macro_cols or DEFAULT_MACRO_COLS
    cfg = {
        "fd_cols": ["close"],
        "beta_windows": (120, 480, 1440),
        "corr_windows": (120, 480, 1440),
        "regime_lookback": 480,
    }

    # Walk-forward OOF evaluation
    folds = _folds(cand, n_splits=args.n_splits, embargo=timedelta(0))
    if not folds:
        print("Insufficient candidates for walk-forward folds", file=sys.stderr)
        return 1

    oof_rows: list[pd.DataFrame] = []
    for fold_i, (train, test) in enumerate(folds, 1):
        train_end = train["entry_ts"].max()
        test_end = test["entry_ts"].max()

        # Build a feature store per symbol for this fold.
        feature_store: dict[str, pd.DataFrame] = {}
        for symbol in args.symbols:
            target = _load_bars(symbol)
            target = target[(target.index >= args.start) & (target.index <= args.end)]
            target["high_beta"] = 1.0 if symbol.split(".", 1)[0] in {
                "TSLA", "MU", "IONQ", "APLD", "HOOD", "NVDA", "COIN", "MSTR", "PLTR", "RKLB", "GME"
            } else 0.0

            engine = MacroCrossAssetEngine(cfg=cfg)
            train_end_naive = train_end.tz_convert(None) if train_end.tz else train_end
            train_target = target[target.index <= train_end_naive]
            if len(train_target) < 50:
                continue
            engine.fit(train_target)

            features = engine.transform(
                target,
                spy_df=spy_df,
                tlt_df=lqd_df,
                vix_df=vix_df,
                events_df=events_df,
                high_beta_col="high_beta",
            )
            # Convert back to tz-naive wall-clock so candidate merge_asof works
            if features.index.tz is not None:
                features.index = features.index.tz_convert(None)
            # Keep only candidate-relevant columns and clean infinites
            keep = [c for c in macro_cols if c in features.columns]
            features = features[keep].replace([np.inf, -np.inf], np.nan)
            features.index.name = "ts"
            feature_store[symbol.split(".", 1)[0]] = features

        # Attach macro features to train and test
        train_merged = _attach_features(train, feature_store)
        test_merged = _attach_features(test, feature_store)

        # Train meta-selector
        selector_cols = [c for c in macro_cols if c in train_merged.columns]
        if not selector_cols:
            print(f"Fold {fold_i}: no macro columns available, skipping", file=sys.stderr)
            continue

        train_model = _fit_logistic(train_merged, ["raw_probability", *selector_cols], l2=0.05)
        test_merged["candidate_probability"] = _predict(test_merged, train_model)
        oof_rows.append(test_merged[["entry_ts", "code", "raw_probability", "candidate_probability", "label", "realized_r", *selector_cols]])

    if not oof_rows:
        print("No OOF predictions produced", file=sys.stderr)
        return 1

    oof = pd.concat(oof_rows, ignore_index=True)
    oof = oof.replace([np.inf, -np.inf], np.nan).dropna(subset=["raw_probability", "candidate_probability", "label", "realized_r"])

    # Event mask: within 24h of any macro release
    event_mask = pd.Series(False, index=oof.index)
    for col in [c for c in oof.columns if c.startswith("macro_") and c.endswith("_since_release_h")]:
        event_mask = event_mask | (oof[col].notna() & (oof[col] <= 24.0))
    for col in [c for c in oof.columns if c.startswith("macro_") and c.endswith("_to_next_release_h")]:
        event_mask = event_mask | (oof[col].notna() & (oof[col] <= 24.0))

    summary = _evaluate(oof, "raw_probability", "candidate_probability", event_mask=event_mask)
    summary["macro_cols_used"] = selector_cols if "selector_cols" in dir() else macro_cols
    summary["n_candidates"] = len(oof)
    summary["n_event"] = int(event_mask.sum())
    summary["n_non_event"] = int((~event_mask).sum())

    print(json.dumps(summary, indent=2, default=str))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    oof.to_parquet(out_dir / "oof_candidates.parquet", index=False)
    print(f"Wrote results to {out_dir}")
    return 0


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    raise SystemExit(_main())
