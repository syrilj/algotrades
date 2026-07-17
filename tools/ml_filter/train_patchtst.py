#!/usr/bin/env python3
"""Train-only selection and holdout evaluation of PatchTST trade filter in PyTorch."""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ml_filter.patchtst_model import PatchTSTClassifier

# Load PyTorch packages
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

CANDIDATES_PATH = ROOT / "runs" / "v88_xgb_filter" / "candidates.csv"
DAILY_CACHE_1H = ROOT / "data_cache" / "1h"
BUNDLE_DIR = ROOT / "models" / "poc_va_macdha" / "v88_xgb_filter"
REPORT_PATH = ROOT / "runs" / "v88_xgb_filter" / "PATCHTST_TRAIN_REPORT.json"

LOOKBACK = 96  # Sequence length (4 trading days)
N_FOLDS = 4
MIN_TRAIN_ROWS = 60
MIN_ACCEPTED_FOR_THRESHOLD = 20
THRESHOLD_GRID = [round(x, 2) for x in np.arange(0.40, 0.76, 0.05)]

# Hyperparameters
PARAMS = {
    "d_model": 32,
    "n_heads": 4,
    "num_layers": 2,
    "dropout": 0.1,
    "lr": 0.001,
    "weight_decay": 1e-4,
    "epochs": 100,
    "batch_size": 16
}

class TimeSeriesDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32).unsqueeze(1)
        
    def __len__(self):
        return len(self.X)
        
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

def walk_forward_folds(n: int, n_folds: int = N_FOLDS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-window folds: train [0:cut), val [cut:next)."""
    if n < (n_folds + 1) * 10:
        n_folds = max(2, n // 20)
    edges = np.linspace(0, n, n_folds + 2, dtype=int)
    folds = []
    for k in range(1, n_folds + 1):
        train_idx = np.arange(0, edges[k])
        val_idx = np.arange(edges[k], edges[k + 1])
        if len(train_idx) >= 10 and len(val_idx) >= 5:
            folds.append((train_idx, val_idx))
    return folds

def load_candidate_sequences(candidates_df):
    """Load preceding 96 bars for each candidate entry."""
    X_list = []
    y_list = []
    valid_rows = []
    
    # Cache parquet dataframes to avoid reading multiple times
    cache = {}
    
    for idx, row in candidates_df.iterrows():
        symbol = str(row["symbol"]).replace(".US", "")
        entry_ts = pd.Timestamp(row["entry_ts"])
        
        if symbol not in cache:
            parquet_path = DAILY_CACHE_1H / f"{symbol}.parquet"
            if not parquet_path.exists():
                continue
            df = pd.read_parquet(parquet_path).sort_index()
            df.index = pd.to_datetime(df.index)
            df.columns = [c.lower() for c in df.columns]
            cache[symbol] = df
            
        df = cache[symbol]
        
        # Locate entry bar index
        locs = df.index.get_indexer([entry_ts], method='pad')
        if len(locs) == 0 or locs[0] < LOOKBACK - 1:
            continue
            
        loc = locs[0]
        seq = df.iloc[loc - LOOKBACK + 1: loc + 1][["open", "high", "low", "close", "volume"]].copy()
        if len(seq) < LOOKBACK:
            continue
            
        # Normalize sequence: scale prices relative to the final close price of the window
        ref_close = seq["close"].iloc[-1]
        seq["open"] /= ref_close
        seq["high"] /= ref_close
        seq["low"] /= ref_close
        seq["close"] /= ref_close
        
        # Normalize volume by mean volume
        vol_mean = seq["volume"].mean()
        if vol_mean > 0:
            seq["volume"] /= vol_mean
            
        X_list.append(seq.values)
        y_list.append(row["label"])
        valid_rows.append(row)
        
    return np.array(X_list), np.array(y_list), pd.DataFrame(valid_rows)

def train_model(X_train, y_train, X_val, y_val):
    """Train PyTorch model with early stopping on validation loss."""
    train_dataset = TimeSeriesDataset(X_train, y_train)
    val_dataset = TimeSeriesDataset(X_val, y_val)
    
    train_loader = DataLoader(train_dataset, batch_size=PARAMS["batch_size"], shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=PARAMS["batch_size"], shuffle=False)
    
    model = PatchTSTClassifier(
        seq_len=LOOKBACK,
        num_channels=5,
        patch_len=8,
        stride=8,
        d_model=PARAMS["d_model"],
        n_heads=PARAMS["n_heads"],
        num_layers=PARAMS["num_layers"],
        dropout=PARAMS["dropout"]
    )
    
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=PARAMS["lr"], weight_decay=PARAMS["weight_decay"])
    
    best_val_loss = float('inf')
    best_state = None
    
    for epoch in range(PARAMS["epochs"]):
        model.train()
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            preds = model(batch_x)
            loss = criterion(preds, batch_y)
            loss.backward()
            optimizer.step()
            
        # Eval
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                preds = model(batch_x)
                loss = criterion(preds, batch_y)
                val_loss += loss.item() * len(batch_x)
        val_loss /= len(val_dataset)
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu() for k, v in model.state_dict().items()}
            
    model.load_state_dict(best_state)
    return model

def select_threshold(pooled_df):
    best = None
    for threshold in THRESHOLD_GRID:
        accepted = pooled_df[pooled_df["p_win"] >= threshold]
        if len(accepted) < MIN_ACCEPTED_FOR_THRESHOLD:
            continue
        mean_r = float(accepted["realized_return"].mean())
        row = {
            "threshold": threshold,
            "accepted_n": int(len(accepted)),
            "accepted_mean_r": mean_r,
            "accepted_wr": float(accepted["label"].mean()),
        }
        if best is None or mean_r > best["accepted_mean_r"]:
            best = row
    if best is None:
        best = {"threshold": 0.5, "accepted_n": 0, "accepted_mean_r": None, "accepted_wr": None,
                "note": "no threshold met the minimum accepted count; defaulted to 0.5"}
    return best

def run_walk_forward(X, y, val_table):
    """Run walk-forward cross validation."""
    folds = walk_forward_folds(len(X))
    fold_stats = []
    pooled = []
    
    for i, (train_idx, val_idx) in enumerate(folds):
        model = train_model(X[train_idx], y[train_idx], X[val_idx], y[val_idx])
        model.eval()
        
        # Predict on validation set
        with torch.no_grad():
            preds = model(torch.tensor(X[val_idx], dtype=torch.float32)).numpy().flatten()
            
        val_frame = val_table.iloc[val_idx][["entry_ts", "realized_return", "label"]].copy()
        val_frame["p_win"] = preds
        pooled.append(val_frame)
        
        base_rate = float(y[val_idx].mean())
        fold_stats.append({
            "fold": i,
            "train_n": int(len(train_idx)),
            "val_n": int(len(val_idx)),
            "val_base_rate": base_rate,
        })
        
    pooled_frame = pd.concat(pooled, ignore_index=True) if pooled else pd.DataFrame()
    return fold_stats, pooled_frame

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward PatchTST trade filter")
    parser.add_argument("--candidates", default=str(CANDIDATES_PATH))
    parser.add_argument("--bundle-dir", default=str(BUNDLE_DIR))
    parser.add_argument("--report", default=str(REPORT_PATH))
    args = parser.parse_args(argv)
    
    table = pd.read_csv(args.candidates)
    table = table.sort_values("entry_ts").reset_index(drop=True)
    
    # Filter candidates to only those with valid preceding OHLCV history
    print("Loading raw time-series inputs for candidates...")
    X, y, filtered_table = load_candidate_sequences(table)
    
    train = filtered_table[filtered_table["window"] == "train"].reset_index(drop=True)
    holdout = filtered_table[filtered_table["window"] == "holdout"].reset_index(drop=True)
    
    train_idx = filtered_table[filtered_table["window"] == "train"].index
    holdout_idx = filtered_table[filtered_table["window"] == "holdout"].index
    
    X_train, y_train = X[train_idx], y[train_idx]
    X_holdout, y_holdout = X[holdout_idx], y[holdout_idx]
    
    report = {
        "schema_version": "patchtst-filter-train-v1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "candidates": str(args.candidates),
        "rows": {"train": int(len(train)), "holdout": int(len(holdout))},
        "params": PARAMS,
    }
    
    if len(train) < MIN_TRAIN_ROWS:
        print(f"Error: insufficient training rows ({len(train)} < {MIN_TRAIN_ROWS})")
        return 1
        
    print("Running walk-forward cross validation on train candidates...")
    fold_stats, pooled = run_walk_forward(X_train, y_train, train)
    report["walk_forward"] = fold_stats
    
    # Select best validation threshold
    threshold_info = select_threshold(pooled)
    report["threshold_selection"] = threshold_info
    threshold = float(threshold_info["threshold"])
    print(f"Optimal threshold chosen: {threshold} with stats: {threshold_info}")
    
    # Train final model on all training data
    print("Training final PatchTST model on all train data...")
    # Use training data for final fit; we evaluate loss on train to avoid validation parameter bias
    final_model = train_model(X_train, y_train, X_train, y_train)
    
    # Save final model
    bundle_dir = Path(args.bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    torch.save(final_model.state_dict(), str(bundle_dir / "patchtst_model.pt"))
    
    # Save model metadata
    meta = {
        "schema_version": "patchtst-filter-meta-v1",
        "trained_at_utc": report["asof_utc"],
        "seq_len": LOOKBACK,
        "threshold": threshold,
        "train_rows": int(len(train)),
        "params": PARAMS
    }
    (bundle_dir / "patchtst_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    
    # Holdout evaluation
    print("Running holdout evaluation...")
    final_model.eval()
    with torch.no_grad():
        preds_holdout = final_model(torch.tensor(X_holdout, dtype=torch.float32)).numpy().flatten()
        
    accepted_mask = preds_holdout >= threshold
    
    baseline = {
        "n": int(len(holdout)),
        "wr": float(holdout["label"].mean()),
        "mean_r": float(holdout["realized_return"].mean()),
        "sum_r": float(holdout["realized_return"].sum()),
    }
    accepted = holdout[accepted_mask]
    filtered = {
        "n": int(len(accepted)),
        "wr": float(accepted["label"].mean()) if len(accepted) else None,
        "mean_r": float(accepted["realized_return"].mean()) if len(accepted) else None,
        "sum_r": float(accepted["realized_return"].sum()) if len(accepted) else None,
    }
    
    improves = (
        filtered["mean_r"] is not None
        and filtered["n"] >= 20
        and filtered["mean_r"] > baseline["mean_r"]
        and filtered["wr"] > baseline["wr"]
    )
    
    one_shot = {
        "threshold": threshold,
        "baseline_all_candidates": baseline,
        "filter_accepted": filtered,
        "improves_over_baseline": bool(improves),
    }
    report["one_shot_holdout"] = one_shot
    
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\n=== HOLDOUT REPORT ===")
    print(json.dumps(one_shot, indent=2))
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
