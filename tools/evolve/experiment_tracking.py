"""Thin MLflow adapter for the poc_va_macdha research program.

Uses a local file store under `runs/mlruns` and the `poc_va_macdha` experiment.
Each attempted backtest is one run; failures are still logged with `error` tags.
Run IDs are meant to be linked from `trials.jsonl`/`findings.jsonl`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MLRUNS_DIR = ROOT / "runs" / "mlruns"
EXPERIMENT_NAME = "poc_va_macdha"

_enabled: bool | None = None


def _is_enabled() -> bool:
    global _enabled
    if _enabled is None:
        # Allow MLFLOW_DISABLE to short-circuit for CI / debugging
        _enabled = os.environ.get("MLFLOW_DISABLE", "").lower() not in ("1", "true", "yes")
    return _enabled


def _init() -> Any:
    import mlflow

    mlflow.set_tracking_uri(f"file://{MLRUNS_DIR}")
    exp = mlflow.set_experiment(EXPERIMENT_NAME)
    return exp


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except Exception:
        return str(value)


def _coerce_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except Exception:
        return None


def _metric_dict(row: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in ("ret", "dd", "sharpe", "n", "wr", "final", "pnl", "score", "score_gain", "score_risk", "score_risk_adj"):
        v = _coerce_float(row.get(key))
        if v is not None:
            out[key] = v
    out["reused"] = 1.0 if row.get("reused") or row.get("from_cache") else 0.0
    return out


def log_run_from_row(model: dict[str, Any] | None, row: dict[str, Any]) -> str | None:
    """Convenience wrapper that pulls run metadata from a DMR-style row."""
    return log_run(
        model,
        mode=str(row.get("mode", "")),
        codes=list(row.get("codes") or []),
        start=str(row.get("start", "")),
        end=str(row.get("end", "")),
        cash=float(row.get("cash", 0) or 0),
        source=str(row.get("source", "")),
        interval=str(row.get("interval", "")),
        tag=str(row.get("tag", "")),
        cache_key=str(row.get("cache_key", "")),
        row=row,
    )


def log_run(
    model: dict[str, Any] | None,
    *,
    mode: str,
    codes: list[str],
    start: str,
    end: str,
    cash: float,
    source: str,
    interval: str,
    tag: str,
    cache_key: str,
    row: dict[str, Any],
    run_name: str | None = None,
) -> str | None:
    """Log one backtest attempt to MLflow. Returns the run_id or None if disabled."""
    if not _is_enabled():
        return None
    try:
        import mlflow

        exp = _init()
        model_id = (model or {}).get("id", "unknown")
        with mlflow.start_run(run_name=run_name or f"{model_id}__{mode}__{tag}") as run:
            mlflow.set_tag("model_id", model_id)
            mlflow.set_tag("mode", mode)
            mlflow.set_tag("tag", tag)
            mlflow.set_tag("source", source)
            mlflow.set_tag("cache_key", cache_key)
            mlflow.set_tag("experiment_phase", "research")
            mlflow.set_tag("generated_utc", datetime.now(timezone.utc).isoformat())
            if row.get("error"):
                mlflow.set_tag("status", "failed")
                mlflow.set_tag("error", str(row["error"])[:250])
            else:
                mlflow.set_tag("status", "ok")

            mlflow.log_param("model_id", model_id)
            mlflow.log_param("mode", mode)
            mlflow.log_param("codes", _safe_json(codes))
            mlflow.log_param("start", start)
            mlflow.log_param("end", end)
            mlflow.log_param("cash", cash)
            mlflow.log_param("source", source)
            mlflow.log_param("interval", interval)
            mlflow.log_param("tag", tag)
            mlflow.log_param("cache_key", cache_key)
            mlflow.log_param("data_hash", _safe_json(row.get("data_hash")))
            mlflow.log_param("env", _safe_json(row.get("env_versions")))

            for name, value in _metric_dict(row).items():
                mlflow.log_metric(name, value)

            return run.info.run_id
    except Exception as exc:
        # MLflow must never break the research loop
        print(f"[mlflow] warning: {exc}", flush=True)
        return None
