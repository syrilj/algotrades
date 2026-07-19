"""High-level backtest engine."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
import sys
import uuid

import pandas as pd

from quantmodel.backtest.event_loop import run_day
from quantmodel.backtest.results import write_artifacts
from quantmodel.backtest.state import BacktestState
from quantmodel.config import PACKAGE_ROOT, load_config
from quantmodel.data.loader import load_market_data
from quantmodel.data.quality import write_quality_issues
from quantmodel.hashing import git_info, hash_config
from quantmodel.logging import setup_logging
from quantmodel.strategy.signals import (
    attach_benchmark_regime,
    compute_entry_signals,
    compute_features,
)
from quantmodel.types import DeploymentStatus, ExperimentManifest
from quantmodel.validation.metrics import compute_metrics
from quantmodel.validation.promotion_gate import evaluate_promotion


def run_backtest(
    config: Mapping[str, Any] | str | Path,
    *,
    artifacts_root: Optional[Path] = None,
    experiment_number: int = 0,
    notes: str = "",
) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        config = load_config(config)

    run_name = config["run"]["name"]
    seed = int(config["run"]["seed"])
    logger = setup_logging()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"__{run_name}__{uuid.uuid4().hex[:6]}"
    logger.info("Starting run %s", run_id)

    data = load_market_data(config, run_id=run_id)
    bars: pd.DataFrame = data["bars"]
    earnings: pd.DataFrame = data["earnings"]
    metadata: dict[str, Any] = data["metadata"]
    issues = data["issues"]

    if bars.empty:
        raise RuntimeError("No bars loaded — cannot backtest")

    feat = compute_features(bars, config)
    feat = attach_benchmark_regime(feat, config)
    feat = compute_entry_signals(feat, config, earnings)

    # Require enough history for indicators
    min_hist = int(config["data"].get("min_history_days", 252))
    dates = sorted(feat["date"].dropna().unique())
    # start after min history from first date
    if dates:
        start_idx = min(min_hist, max(0, len(dates) - 2))
        trade_dates = dates[start_idx:]
    else:
        trade_dates = []

    state = BacktestState(cash=float(config["run"]["initial_equity"]))
    state.peak_equity = state.cash
    state.kill_switch.peak_equity = state.cash
    state.kill_switch.shadow_equity = state.cash
    state.kill_switch.shadow_peak = state.cash

    for i, dt in enumerate(trade_dates):
        day_bars = feat[feat["date"] == dt]
        # next session for pending
        nxt = trade_dates[i + 1].date() if i + 1 < len(trade_dates) else None
        if nxt is None and len(trade_dates):
            from quantmodel.data.calendar import next_session

            nxt = next_session(pd.Timestamp(dt).date())
        run_day(
            state,
            asof=pd.Timestamp(dt),
            day_bars=day_bars,
            signal_rows=feat,
            config=config,
            next_session_date=nxt,
        )

    metrics = compute_metrics(state, config, benchmark_symbol=str(config["data"]["benchmark"]))
    promo = evaluate_promotion(metrics, config, metadata)
    metrics["promotion"] = promo

    commit, dirty = git_info(PACKAGE_ROOT.parent)
    manifest = ExperimentManifest(
        run_id=run_id,
        run_name=run_name,
        created_at_utc=datetime.now(timezone.utc),
        git_commit=commit,
        git_dirty_flag=dirty,
        python_version=sys.version.split()[0],
        dependency_lock_hash="n/a",
        config_hash=config.get("_meta", {}).get("config_hash")
        or hash_config({k: v for k, v in config.items() if k != "_meta"}),
        data_manifest_hash=str(metadata.get("data_manifest_hash", "")),
        random_seed=seed,
        experiment_number=experiment_number,
        notes=notes,
        deployment_status=promo.get("deployment_status", DeploymentStatus.RESEARCH_ONLY.value),
        extra={"data_limitations": metadata.get("limitations", [])},
    )

    art_root = artifacts_root or (PACKAGE_ROOT / config.get("artifacts", {}).get("root", "artifacts/runs"))
    out_dir = Path(art_root) / run_id
    write_artifacts(
        out_dir,
        state=state,
        config=config,
        manifest=manifest,
        metrics=metrics,
        metadata=metadata,
    )
    if issues:
        write_quality_issues(issues, out_dir / "data_quality_issues.csv")

    logger.info(
        "Completed %s equity=%.2f status=%s",
        run_id,
        state.daily[-1].equity if state.daily else state.cash,
        manifest.deployment_status,
    )
    return {
        "run_id": run_id,
        "artifact_dir": str(out_dir),
        "metrics": metrics,
        "manifest": manifest,
        "state": state,
        "metadata": metadata,
    }
