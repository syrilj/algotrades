#!/usr/bin/env python3
"""Cost & slippage stress harness for the promoted v72 book (P0-2).

Re-runs the locked train/holdout windows from
``models/poc_va_macdha/DEPLOYMENT_MANIFEST.json``'s ``data_contract`` under
stressed execution costs and writes ``runs/v72_dual_sleeve/STRESS.json``.

Cost model background (verified against the promotion path):
  ``tools/dynamic_model_rank.py`` routes ``source="local"`` US-equity runs to
  ``backtest.engines.global_equity.GlobalEquityEngine(market="us")``, whose US
  branch charges **zero commission** and a flat ``slippage_us`` (default
  0.0005 = 5 bps) per side. The ``commission`` key in each model's
  config.json is *not* consumed on that path — so "2x commission" stress must
  be applied explicitly. This module adds the smallest clean extension:

  ``StressedGlobalEquityEngine`` honors two new config keys:
    - ``stress_commission_per_side``: notional rate charged on every fill
      (entry and exit). Default 0.0 — existing results unchanged.
    - ``slippage_bps``: per-symbol map of *additional* per-side slippage in
      basis points on top of the engine's base ``slippage_us``; a
      ``"default"`` key covers unmapped symbols. Default {} — existing
      results unchanged.

Scenario definitions live in
``models/poc_va_macdha/v72_dual_sleeve/stress_config.json``.

Pass bar (docs/ML_PROD_READINESS_PLAN.md P0-2): holdout return stays positive
and holdout Sharpe >= 1.0 under stress.

Offline & read-only with respect to locked evidence: this tool never touches
``runs/v72_dual_sleeve/{STATE,COMPARE}.json``, the calibration artifacts, or
the deployment manifest. It only *reads* the manifest's data contract and
writes new run dirs under ``runs/`` plus ``runs/v72_dual_sleeve/STRESS.json``.

Usage:
  .venv/bin/python tools/stress_backtest.py                # run all scenarios
  .venv/bin/python tools/stress_backtest.py --scenario commission_2x
  .venv/bin/python tools/stress_backtest.py --include-baseline
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# The runner validates run dirs against allowed roots; make the repo's runs/
# tree explicitly allowed regardless of the caller's cwd.
os.environ.setdefault("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(ROOT / "runs"))

# Importing dynamic_model_rank applies its runner patches (source="local" →
# GlobalEquityEngine + yfinance-calendar annualization), which is exactly the
# environment the v72 promotion numbers were produced under.
import dynamic_model_rank as _dmr  # noqa: E402,F401  (imported for side effects)
import backtest.runner as _runner  # noqa: E402
from backtest.engines.global_equity import GlobalEquityEngine  # noqa: E402

MANIFEST_PATH = ROOT / "models" / "poc_va_macdha" / "DEPLOYMENT_MANIFEST.json"
STRESS_CONFIG_PATH = ROOT / "models" / "poc_va_macdha" / "v72_dual_sleeve" / "stress_config.json"
STRESS_OUT_PATH = ROOT / "runs" / "v72_dual_sleeve" / "STRESS.json"
RUNS_DIR = ROOT / "runs" / "v72_stress"

# P0-2 pass bar from the plan doc.
PASS_BAR = {"holdout_return_gt": 0.0, "holdout_sharpe_gte": 1.0}


class StressedGlobalEquityEngine(GlobalEquityEngine):
    """GlobalEquityEngine plus explicit per-side commission and slippage stress.

    With ``stress_commission_per_side == 0`` and an empty ``slippage_bps`` map
    this class is behaviorally identical to ``GlobalEquityEngine`` — covered
    by tests so the stress path can never silently change baseline results.
    """

    def __init__(self, config: dict, market: str = "us") -> None:
        super().__init__(config, market)
        self.stress_commission_per_side: float = float(config.get("stress_commission_per_side", 0.0) or 0.0)
        raw_map = config.get("slippage_bps") or {}
        self.slippage_bps: dict[str, float] = {
            str(k): float(v) for k, v in raw_map.items() if v is not None
        }

    def _extra_slippage_rate(self, symbol: str) -> float:
        """Per-side extra slippage rate for ``symbol`` (bps → fraction)."""
        if not self.slippage_bps:
            return 0.0
        key = str(symbol or "")
        if key in self.slippage_bps:
            bps = self.slippage_bps[key]
        else:
            bare = key.replace(".US", "")
            if bare in self.slippage_bps:
                bps = self.slippage_bps[bare]
            else:
                bps = self.slippage_bps.get("default", 0.0)
        return float(bps) / 10_000.0

    def calc_commission(self, size: float, price: float, direction: int, is_open: bool) -> float:
        base = super().calc_commission(size, price, direction, is_open)
        return base + size * price * self.stress_commission_per_side

    def apply_slippage(self, price: float, direction: int) -> float:
        # Combine base + extra into one rate so entry and exit each pay a
        # single well-defined haircut (not compounding two multiplications).
        base_rate = self.slippage_hk if self.market == "hk" else self.slippage_us
        extra = self._extra_slippage_rate(getattr(self, "_active_symbol", ""))
        return price * (1 + direction * (base_rate + extra))


_prev_create_market_engine = None


def install_stress_engine() -> None:
    """Route configs carrying stress keys to ``StressedGlobalEquityEngine``.

    Mirrors dynamic_model_rank's own runner patch; configs without stress
    keys keep the exact engine they had before.
    """
    global _prev_create_market_engine
    if _prev_create_market_engine is not None:
        return  # already installed
    _prev_create_market_engine = _runner._create_market_engine

    def _create(source: str, config: dict, codes: list[str]):
        has_stress = bool(config.get("slippage_bps")) or bool(config.get("stress_commission_per_side"))
        if has_stress and codes:
            markets = {_runner._detect_market(c) for c in codes}
            if len(markets) == 1 and markets & {"us_equity", "hk_equity"}:
                market = _runner._detect_submarket(codes)
                return StressedGlobalEquityEngine(config, market=market)
        return _prev_create_market_engine(source, config, codes)

    _runner._create_market_engine = _create


# ---------------------------------------------------------------------------
# Config plumbing.
# ---------------------------------------------------------------------------


def load_manifest_contract(manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = manifest.get("data_contract") or {}
    bundle_path = ((manifest.get("active") or {}).get("bundle") or {}).get("path")
    required = ("train_window", "locked_holdout_window", "universe", "interval", "source", "cash")
    missing = [k for k in required if k not in contract]
    if missing or not bundle_path:
        raise ValueError(f"data_contract incomplete (missing {missing}) or bundle path absent")
    return {
        "bundle_path": str(bundle_path),
        "source": str(contract["source"]),
        "interval": str(contract["interval"]),
        "cash": float(contract["cash"]),
        "universe": list(contract["universe"]),
        "windows": {
            "train": tuple(contract["train_window"]),
            "holdout": tuple(contract["locked_holdout_window"]),
        },
    }


def load_stress_scenarios(config_path: Path = STRESS_CONFIG_PATH) -> list[dict[str, Any]]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(f"no scenarios in {config_path}")
    return scenarios


def build_run_config(
    contract: dict[str, Any],
    window: tuple[str, str],
    scenario: dict[str, Any] | None,
) -> dict[str, Any]:
    """Backtest config.json for one (window, scenario) cell.

    ``scenario is None`` builds the unstressed baseline (no stress keys at
    all, so the engine routing and costs are exactly the promotion path's).
    """
    cfg: dict[str, Any] = {
        "source": contract["source"],
        "codes": list(contract["universe"]),
        "start_date": str(window[0]),
        "end_date": str(window[1]),
        "initial_cash": contract["cash"],
        "commission": 0.001,  # informational; not consumed on the US path
        "engine": "daily",
        "interval": contract["interval"],
        "strategy": {"model_version": "v72_dual_sleeve", "mode": "stress"},
    }
    if scenario is not None:
        cfg["stress_commission_per_side"] = float(scenario.get("stress_commission_per_side", 0.0) or 0.0)
        cfg["slippage_bps"] = dict(scenario.get("slippage_bps") or {})
        cfg["strategy"]["stress_scenario"] = scenario.get("id")
    return cfg


def _copy_engine_code(bundle_dir: Path, run_code: Path) -> None:
    run_code.mkdir(parents=True, exist_ok=True)
    for name in ("signal_engine.py", "hunt_config.json"):
        src = bundle_dir / name
        if src.exists():
            shutil.copy2(src, run_code / name)


def run_cell(
    contract: dict[str, Any],
    window_name: str,
    scenario: dict[str, Any] | None,
    *,
    runs_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    """Execute one backtest cell and return its metrics row."""
    from backtest.runner import main as bt_main

    scenario_id = scenario.get("id") if scenario else "baseline"
    window = contract["windows"][window_name]
    run_dir = runs_dir / f"{scenario_id}__{window_name}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    _copy_engine_code(ROOT / contract["bundle_path"], run_dir / "code")
    cfg = build_run_config(contract, window, scenario)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    print(f"[stress] RUN {scenario_id:28} {window_name:8} {window[0]}→{window[1]}", flush=True)
    try:
        bt_main(run_dir.resolve())
    except SystemExit as se:  # runner exits on engine/data errors
        return {"scenario": scenario_id, "window": window_name, "error": f"backtest SystemExit: {se}"}

    metrics_path = run_dir / "artifacts" / "metrics.csv"
    if not metrics_path.exists():
        return {"scenario": scenario_id, "window": window_name, "error": "metrics.csv missing"}
    with metrics_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    # Large OHLCV dumps are reproducible from data_cache; drop them.
    for p in (run_dir / "artifacts").glob("ohlcv_*.csv"):
        p.unlink(missing_ok=True)
    return {
        "scenario": scenario_id,
        "window": window_name,
        "start": window[0],
        "end": window[1],
        "ret": float(row["total_return"]),
        "dd": float(row["max_drawdown"]),
        "sharpe": float(row["sharpe"]),
        "n": int(float(row["trade_count"])),
        "wr": float(row["win_rate"]),
        "final": float(row["final_value"]),
        "run_dir": str(run_dir.relative_to(ROOT)),
        "error": None,
    }


def evaluate_pass_bar(rows: list[dict[str, Any]], pass_bar: dict[str, float] = PASS_BAR) -> dict[str, Any]:
    """P0-2 bar: every *stressed* holdout cell must keep ret > 0 and Sharpe >= bar."""
    verdicts: dict[str, Any] = {}
    all_pass = True
    for row in rows:
        if row.get("window") != "holdout" or row.get("scenario") == "baseline":
            continue
        if row.get("error"):
            verdicts[row["scenario"]] = {"pass": False, "reason": f"run_error: {row['error']}"}
            all_pass = False
            continue
        ret_ok = row["ret"] > pass_bar["holdout_return_gt"]
        sharpe_ok = row["sharpe"] >= pass_bar["holdout_sharpe_gte"]
        ok = ret_ok and sharpe_ok
        verdicts[row["scenario"]] = {
            "pass": ok,
            "holdout_return": row["ret"],
            "holdout_sharpe": row["sharpe"],
            "return_gt_0": ret_ok,
            "sharpe_gte_1": sharpe_ok,
        }
        all_pass = all_pass and ok
    if not verdicts:
        # Fail closed: no stressed holdout evidence means no pass.
        return {"pass": False, "reason": "no_stressed_holdout_runs", "scenarios": {}}
    return {"pass": all_pass, "pass_bar": pass_bar, "scenarios": verdicts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cost & slippage stress harness for v72_dual_sleeve")
    parser.add_argument("--scenario", default=None, help="Run only this scenario id")
    parser.add_argument("--include-baseline", action="store_true", help="Also run an unstressed baseline for reference")
    parser.add_argument("--config", default=str(STRESS_CONFIG_PATH))
    parser.add_argument("--output", default=str(STRESS_OUT_PATH))
    args = parser.parse_args(argv)

    contract = load_manifest_contract()
    scenarios = load_stress_scenarios(Path(args.config))
    if args.scenario:
        scenarios = [s for s in scenarios if s.get("id") == args.scenario]
        if not scenarios:
            print(json.dumps({"error": f"scenario {args.scenario!r} not found"}))
            return 2

    install_stress_engine()

    rows: list[dict[str, Any]] = []
    plan: list[dict[str, Any] | None] = ([None] if args.include_baseline else []) + scenarios
    for scenario in plan:
        for window_name in ("train", "holdout"):
            rows.append(run_cell(contract, window_name, scenario))

    verdict = evaluate_pass_bar(rows)
    report = {
        "schema_version": "cost-stress-v1",
        "asof_utc": datetime.now(timezone.utc).isoformat(),
        "model": "v72_dual_sleeve",
        "data_contract": {
            "source": contract["source"],
            "interval": contract["interval"],
            "cash": contract["cash"],
            "universe": contract["universe"],
            "windows": {k: list(v) for k, v in contract["windows"].items()},
        },
        "cost_model_note": (
            "Baseline promotion path (dynamic_model_rank, source=local, US equities) charges zero "
            "commission and slippage_us=0.0005 (5 bps) per side; the config 'commission' key is not "
            "consumed on that path. Stress adds stress_commission_per_side notional per fill and "
            "slippage_bps per-symbol per-side on top of the 5 bps base."
        ),
        "results": rows,
        "verdict": verdict,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    print(json.dumps({"output": str(out_path), "verdict": verdict}, indent=2))
    return 0 if verdict.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
