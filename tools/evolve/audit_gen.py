"""Audit gate evaluation and reporting for evolve_direction_v1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from backtest.models import TradeRecord
from backtest.validation import walk_forward_analysis

from tools.evolve import auditor, costs, folds, stats as evolve_stats

ROOT = Path(__file__).resolve().parents[2]
PASS_BAR_PATH = ROOT / "models" / "_shared" / "PASS_BAR.json"
AUDIT_GATES_PATH = ROOT / "models" / "_shared" / "AUDIT_GATES.json"


def _pass_bar() -> dict[str, Any]:
    return json.loads(PASS_BAR_PATH.read_text()) if PASS_BAR_PATH.exists() else {}


def _audit_gates() -> dict[str, Any]:
    return json.loads(AUDIT_GATES_PATH.read_text()) if AUDIT_GATES_PATH.exists() else {}


def _pooled_metrics(candidate: dict) -> dict[str, Any]:
    return folds.fold_metrics(
        candidate["trades"], candidate["equity"], candidate["bars_per_year"]
    )


def _pass_bar_ok(m: dict[str, Any]) -> bool:
    bar = _pass_bar()
    gates = bar.get("gates", {})
    return bool(
        m.get("pf", 0.0) >= float(gates.get("profit_factor_min", 1.2))
        and m.get("sharpe", 0.0) >= float(gates.get("sharpe_min", 0.5))
        and m.get("n", 0) >= int(gates.get("min_trades", 40))
        and m.get("expectancy", 0.0) >= float(gates.get("expectancy_after_costs_min", 0.0))
        and abs(m.get("dd", 0.0)) <= float(gates.get("max_drawdown_max_abs", 0.25))
    )


def _trials_stats() -> tuple[int, float]:
    """n_trials and variance of mean Sharpe across trials."""
    trials = ROOT / "models" / "_shared" / "trials.jsonl"
    if not trials.exists():
        return 1, 0.0
    sharps = []
    for line in trials.read_text().strip().splitlines():
        if not line:
            continue
        try:
            row = json.loads(line)
            fm = row.get("fold_metrics", {})
            shs = [float(f.get("sharpe", 0)) for f in fm.values() if isinstance(f, dict)]
            if shs:
                sharps.append(float(np.mean(shs)))
        except Exception:
            continue
    if not sharps:
        return 1, 0.0
    return len(sharps), float(np.var(sharps, ddof=0))


def _returns_stats(equity: pd.Series) -> tuple[float, float]:
    r = equity.pct_change().dropna()
    if len(r) < 4:
        return 0.0, 3.0
    return float(stats.skew(r)), float(stats.kurtosis(r, fisher=False))


def _wf_consistency(equity: pd.Series, trades_records: list[TradeRecord], bars_per_year: int) -> float:
    try:
        res = walk_forward_analysis(equity, trades_records, n_windows=5, bars_per_year=bars_per_year)
        return float(res.get("consistency_rate", 0.0))
    except Exception:
        return 0.0


def _trade_records_from_df(trades: pd.DataFrame) -> list[TradeRecord]:
    records = []
    for _, t in trades.iterrows():
        records.append(
            TradeRecord(
                symbol=str(t["symbol"]),
                direction=int(t["direction"]),
                entry_price=float(t["entry_price"]),
                exit_price=float(t["exit_price"]),
                entry_time=pd.Timestamp(t["entry_time"]),
                exit_time=pd.Timestamp(t["exit_time"]),
                size=float(t["size"]),
                leverage=1.0,
                pnl=float(t["pnl"]),
                pnl_pct=float(t.get("pnl_pct", 0.0)),
                exit_reason=str(t.get("exit_reason", "")),
                holding_bars=int(t.get("holding_days", 0)),
                commission=0.0,
            )
        )
    return records


def _stressor_metrics(trades: pd.DataFrame, equity: pd.Series, bars_per_year: int, cash: float = 1_000_000.0) -> dict[str, Any]:
    """PASS_BAR metrics under SLIPPAGE_STRESS total per-side."""
    if trades.empty or equity.empty:
        return {}
    adj_trades = costs.adjust_trades_for_slippage(trades, costs.SLIPPAGE_STRESS)
    adj_equity = costs.adjust_equity_for_slippage(equity, trades, costs.SLIPPAGE_STRESS, cash=cash)
    return folds.fold_metrics(adj_trades, adj_equity, bars_per_year)


def evaluate_gates(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate all AUDIT_GATES for a candidate."""
    gates = []

    pooled = _pooled_metrics(candidate)
    fold_ms = [candidate["fold_metrics"][f["name"]] for f in folds.FOLDS_1H]
    fold_utilities = [folds.fold_utility(m) for m in fold_ms]
    fold_ns = [m.get("n", 0) for m in fold_ms]

    # 1 pooled PASS_BAR + per-fold DD
    per_fold_dd_ok = all(abs(m.get("dd", 0.0)) <= 0.25 for m in fold_ms)
    gates.append(
        {
            "gate_id": 1,
            "name": "pooled_pass_bar",
            "threshold": "PF>=1.2, Sharpe>=0.5, n>=40, exp>0, |DD|<=0.25 every fold",
            "measured": {
                "pooled": pooled,
                "per_fold_dd_ok": per_fold_dd_ok,
            },
            "passed": _pass_bar_ok(pooled) and per_fold_dd_ok,
            "notes": "",
        }
    )

    # 2 U_f > 0 in >=3/4 folds, n>=8/fold
    positive_folds = sum(1 for u, n in zip(fold_utilities, fold_ns) if u > 0 and n >= 8)
    gates.append(
        {
            "gate_id": 2,
            "name": "fold_utility_positive",
            "threshold": "U_f > 0 in >=3/4 folds, n>=8/fold",
            "measured": {"positive_folds": positive_folds, "fold_utilities": fold_utilities},
            "passed": positive_folds >= 3,
            "notes": "",
        }
    )

    # 3 sign-flip p <= 0.05
    pnls = candidate["trades"]["pnl"].astype(float).tolist() if not candidate["trades"].empty else []
    sf = evolve_stats.signflip_permutation(pnls, n_perm=2000, seed=7)
    gates.append(
        {
            "gate_id": 3,
            "name": "signflip_significant",
            "threshold": "sign-flip p <= 0.05",
            "measured": sf,
            "passed": sf.get("p_value", 1.0) <= 0.05,
            "notes": "",
        }
    )

    # 4 MC DD p >= 0.05
    val = candidate.get("validation", {})
    gates.append(
        {
            "gate_id": 4,
            "name": "mc_dd_path",
            "threshold": "MC DD-path p >= 0.05",
            "measured": {"mc_dd_pvalue": val.get("mc_dd_pvalue", 0.0)},
            "passed": val.get("mc_dd_pvalue", 0.0) >= 0.05,
            "notes": "",
        }
    )

    # 5 bootstrap Sharpe CI low > 0
    gates.append(
        {
            "gate_id": 5,
            "name": "bootstrap_sharpe_positive",
            "threshold": "bootstrap Sharpe 95% CI low > 0",
            "measured": {
                "sharpe_ci_low": val.get("sharpe_ci_low", 0.0),
                "sharpe_ci_high": val.get("sharpe_ci_high", 0.0),
            },
            "passed": val.get("sharpe_ci_low", 0.0) > 0.0,
            "notes": "",
        }
    )

    # 6 DSR >= 0.95
    n_obs = max(0, len(candidate["equity"]) - 1)
    skew, kurt = _returns_stats(candidate["equity"])
    n_trials, var_trials_sr = _trials_stats()
    dsr_res = evolve_stats.deflated_sharpe(
        sr_hat=pooled.get("sharpe", 0.0),
        n_obs=n_obs,
        skew=skew,
        kurt=kurt,
        n_trials=n_trials,
        var_trials_sr=var_trials_sr,
    )
    gates.append(
        {
            "gate_id": 6,
            "name": "deflated_sharpe",
            "threshold": "DSR >= 0.95",
            "measured": dsr_res,
            "passed": dsr_res.get("dsr", 0.0) >= 0.95,
            "notes": "",
        }
    )

    # 7 PASS_BAR at SLIPPAGE_STRESS
    stress = _stressor_metrics(candidate["trades"], candidate["equity"], candidate["bars_per_year"], cash=candidate.get("cash", 1_000_000.0))
    gates.append(
        {
            "gate_id": 7,
            "name": "pass_bar_at_stress_slippage",
            "threshold": f"PASS_BAR at total per-side slippage {costs.SLIPPAGE_STRESS}",
            "measured": stress,
            "passed": _pass_bar_ok(stress),
            "notes": "",
        }
    )

    # 8 slippage perturbation
    perturb = candidate.get("perturb_fitness")
    if perturb and len(perturb) == 3:
        base = candidate["fitness"]
        mean_p = float(np.mean(perturb))
        min_p = float(np.min(perturb))
        passed = mean_p >= 0.6 * base and min_p >= 0.0
    else:
        perturb = []
        mean_p = 0.0
        min_p = 0.0
        passed = False
    gates.append(
        {
            "gate_id": 8,
            "name": "slippage_perturbation",
            "threshold": "slippage +/-20%: mean fitness >=0.6x base, none<0",
            "measured": {"perturb_fitness": perturb, "mean": mean_p, "min": min_p, "base": candidate["fitness"]},
            "passed": passed,
            "notes": "",
        }
    )

    # 9 Track B floor
    tb = candidate.get("track_b", {})
    tb_pooled = tb.get("pooled_metrics", {})
    gates.append(
        {
            "gate_id": 9,
            "name": "track_b_floor",
            "threshold": "Track B pooled ret>0, |DD|<=0.30; DURABLE_CLAIM = full PASS_BAR",
            "measured": tb_pooled,
            "passed": bool(tb_pooled.get("ret", 0.0) > 0 and abs(tb_pooled.get("dd", 0.0)) <= 0.30),
            "notes": "DURABLE_CLAIM requires full PASS_BAR on Track B" if not _pass_bar_ok(tb_pooled) else "",
        }
    )

    # 10 regime slices
    slices = candidate.get("direction_report", {}).get("regime_slices", {})
    if slices:
        positive = sum(1 for v in slices.values() if v.get("expectancy", 0.0) > 0)
        max_dd = max((abs(v.get("max_drawdown", 0.0)) for v in slices.values()), default=0.0)
        passed = positive >= (2 / 3) * len(slices) and max_dd <= 0.25
    else:
        positive = 0
        max_dd = 0.0
        passed = False
    gates.append(
        {
            "gate_id": 10,
            "name": "regime_slices",
            "threshold": "expectancy>0 in >=2/3 regime slices, no slice |DD|>0.25",
            "measured": {"positive_slices": positive, "n_slices": len(slices), "max_slice_dd": max_dd},
            "passed": passed,
            "notes": "",
        }
    )

    # 11 direction hit
    hit = candidate.get("direction_report", {}).get("hit", {}).get("hit_5d", {})
    hit_rate = hit.get("rate", 0.0)
    hit_p = hit.get("p_value", 1.0)
    exp = candidate.get("direction_report", {}).get("expectancy", 0.0)
    gates.append(
        {
            "gate_id": 11,
            "name": "direction_hit",
            "threshold": "hit@5d > 50% with binomial p <= 0.10 and expectancy > 0",
            "measured": {"hit_5d_rate": hit_rate, "hit_5d_pvalue": hit_p, "expectancy": exp},
            "passed": hit_rate > 0.5 and hit_p <= 0.10 and exp > 0,
            "notes": "",
        }
    )

    # 12 auditor source scan + WF
    model_dir = Path(candidate.get("model_dir", candidate.get("run_dir", ".")))
    engine_path = model_dir / "signal_engine.py"
    if not engine_path.exists():
        engine_path = model_dir / "code" / "signal_engine.py"
    findings = auditor.audit_source(engine_path)
    max_sev = max(
        (0 if f.severity == "info" else 1 if f.severity == "warn" else 2 if f.severity == "fail" else 3)
        for f in findings
    ) if findings else 0
    records = _trade_records_from_df(candidate["trades"])
    wf = _wf_consistency(candidate["equity"], records, candidate["bars_per_year"])
    gates.append(
        {
            "gate_id": 12,
            "name": "source_scan_and_wf",
            "threshold": "auditor source scan clean (no fail/block) and walk-forward stitched",
            "measured": {"max_severity": max_sev, "wf_consistency": wf},
            "passed": max_sev < 2 and wf >= 0.5,
            "notes": "",
        }
    )

    # 13 LOCKBOX
    lock = candidate.get("lockbox", {})
    gates.append(
        {
            "gate_id": 13,
            "name": "lockbox_binding",
            "threshold": "LOCKBOX fitness > 0 and binding",
            "measured": lock,
            "passed": lock.get("fitness", 0.0) > 0,
            "notes": "",
        }
    )

    return gates


def write_audit(
    candidate: dict[str, Any],
    gate_results: list[dict[str, Any]] | None,
    out_path: str | Path,
) -> Path:
    """Write audit JSON and Markdown."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if gate_results is None:
        gate_results = evaluate_gates(candidate)

    passed = [g for g in gate_results if g["passed"]]
    failed = [g for g in gate_results if not g["passed"]]
    all_pass = len(failed) == 0

    audit = {
        "ts": pd.Timestamp.now(tz="UTC").isoformat(),
        "candidate": candidate.get("variant_id", candidate.get("id", "unknown")),
        "campaign_id": candidate.get("campaign_id", ""),
        "gen": candidate.get("gen", 0),
        "parent": candidate.get("parent", ""),
        "all_pass": all_pass,
        "gates_passed": len(passed),
        "gates_total": len(gate_results),
        "fitness": candidate.get("fitness", 0.0),
        "gate_results": gate_results,
    }
    out_path.write_text(json.dumps(audit, indent=2, default=str))

    md = out_path.with_suffix(".md")
    lines = [
        f"# Audit: {audit['candidate']}",
        "",
        f"Campaign: {audit['campaign_id']} | Gen: {audit['gen']} | Parent: {audit['parent']}",
        f"Fitness: {audit['fitness']:.4f} | Gates passed: {audit['gates_passed']}/{audit['gates_total']}",
        f"**All gates passed:** {all_pass}",
        "",
        "| Gate | Name | Threshold | Measured | Passed |",
        "|------|------|-----------|----------|--------|",
    ]
    for g in gate_results:
        lines.append(
            f"| {g['gate_id']} | {g['name']} | {g['threshold']} | {g['measured']} | {'YES' if g['passed'] else 'NO'} |"
        )
    md.write_text("\n".join(lines))
    return out_path
