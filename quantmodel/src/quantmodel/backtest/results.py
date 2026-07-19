"""Serialize backtest results to artifact directory."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from quantmodel.backtest.state import BacktestState
from quantmodel.hashing import canonical_json
from quantmodel.types import ExperimentManifest


def state_to_frames(state: BacktestState) -> dict[str, pd.DataFrame]:
    daily = pd.DataFrame([asdict(d) for d in state.daily])
    fills = pd.DataFrame([asdict(f) for f in state.fills])
    orders = pd.DataFrame([asdict(o) for o in state.orders + state.pending_orders])
    signals = pd.DataFrame(state.signals) if state.signals else pd.DataFrame()
    # normalize enums
    for df in (fills, orders):
        if not df.empty:
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].map(lambda x: x.value if hasattr(x, "value") else x)
    equity = (
        daily[["date", "equity"]].copy()
        if not daily.empty
        else pd.DataFrame(columns=["date", "equity"])
    )
    return {
        "daily_portfolio": daily,
        "fills": fills,
        "orders": orders,
        "signals": signals,
        "equity_curve": equity,
    }


def write_artifacts(
    out_dir: Path,
    *,
    state: BacktestState,
    config: Mapping[str, Any],
    manifest: ExperimentManifest,
    metrics: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = state_to_frames(state)

    # config
    import yaml

    cfg_out = {k: v for k, v in config.items() if k != "_meta"}
    (out_dir / "config.yaml").write_text(yaml.safe_dump(cfg_out, sort_keys=False), encoding="utf-8")

    man = asdict(manifest)
    man["created_at_utc"] = manifest.created_at_utc.isoformat()
    man["data_metadata"] = dict(metadata)
    (out_dir / "manifest.json").write_text(canonical_json(man) + "\n", encoding="utf-8")
    (out_dir / "metrics.json").write_text(canonical_json(dict(metrics)) + "\n", encoding="utf-8")

    for name, df in frames.items():
        if name == "equity_curve":
            df.to_csv(out_dir / "equity_curve.csv", index=False)
        else:
            path = out_dir / f"{name}.parquet"
            try:
                df.to_parquet(path, index=False)
            except Exception:
                df.to_csv(out_dir / f"{name}.csv", index=False)

    # trades from fills pair simplification
    trades = frames["fills"]
    if not trades.empty:
        trades.to_csv(out_dir / "trades.csv", index=False)

    # kill switch events
    (out_dir / "kill_switch_events.json").write_text(
        canonical_json(state.kill_switch.events) + "\n", encoding="utf-8"
    )
    return out_dir
