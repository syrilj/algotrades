#!/usr/bin/env python3
"""Batch ablations for v32 soft-react options vs v28 baseline."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from backtest.runner import main as bt_main

ROOT = Path(__file__).resolve().parents[1]
ENG = ROOT / "models" / "poc_va_macdha" / "v32_soft_react_opts" / "signal_engine.py"
CFG_BASE = ROOT / "models" / "poc_va_macdha" / "v32_soft_react_opts" / "config.json"
OUT = ROOT / "runs" / "poc_va_v32_ablations"

COMMON = {
    "risk_pct": 0.10,
    "dte_days": 14,
    "dte_high_vol": 10,
    "otm_pct": 0.0,
    "halt_dd": 0.28,
    "flatten_dd": 0.42,
    "use_conf_tier": True,
    "use_narrative": True,
    "narrative_mode": "surgical",
    "loss_cooloff_days": 10,
    "initial_cash": 1_000_000,
    "contract_multiplier": 100,
    "max_contracts": 500,
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 55,
    "profile_lookback": 20,
    "profile_rows": 25,
    "value_area_pct": 0.70,
    "min_target_room_pct": 0.004,
    "stmacd_revt": 100.0,
    "vol_surge_ref": 1.35,
    "vol_regime_high": 0.75,
}

# name -> overrides (need_structure False = pure v28-like with optional adaptive dte only)
VARIANTS = {
    "v28_like_plain": {
        "need_structure": False,
        "use_soft_structure": False,
        "use_soft_ob": False,
        "use_os_boost": False,
        "use_soft_vol": False,
        "use_adaptive_dte": False,
        "exit_on_cloud_bear": False,
    },
    "adaptive_dte_only": {
        "need_structure": True,  # only for rv_pct
        "use_soft_structure": False,
        "use_soft_ob": False,
        "use_os_boost": False,
        "use_soft_vol": False,
        "use_adaptive_dte": True,
        "exit_on_cloud_bear": False,
        "struct_good_mult": 1.0,
        "struct_weak_mult": 1.0,
    },
    "soft_struct": {
        "need_structure": True,
        "use_soft_structure": True,
        "use_soft_ob": False,
        "use_os_boost": False,
        "use_soft_vol": False,
        "use_adaptive_dte": False,
        "exit_on_cloud_bear": False,
        "struct_good_mult": 1.15,
        "struct_weak_mult": 0.55,
    },
    "soft_struct_strong": {
        "need_structure": True,
        "use_soft_structure": True,
        "use_soft_ob": False,
        "use_os_boost": False,
        "use_soft_vol": False,
        "use_adaptive_dte": False,
        "exit_on_cloud_bear": False,
        "struct_good_mult": 1.25,
        "struct_weak_mult": 0.70,
    },
    "soft_ob": {
        "need_structure": True,
        "use_soft_structure": False,
        "use_soft_ob": True,
        "use_os_boost": False,
        "use_soft_vol": False,
        "use_adaptive_dte": False,
        "exit_on_cloud_bear": False,
        "struct_good_mult": 1.0,
        "struct_weak_mult": 1.0,
        "ob_chase_mult": 0.40,
    },
    "soft_struct_ob_os_dte": {
        "need_structure": True,
        "use_soft_structure": True,
        "use_soft_ob": True,
        "use_os_boost": True,
        "use_soft_vol": False,
        "use_adaptive_dte": True,
        "exit_on_cloud_bear": False,
        "struct_good_mult": 1.15,
        "struct_weak_mult": 0.55,
        "ob_chase_mult": 0.40,
        "os_boost_mult": 1.12,
    },
    "soft_full_exit_cloud": {
        "need_structure": True,
        "use_soft_structure": True,
        "use_soft_ob": True,
        "use_os_boost": True,
        "use_soft_vol": True,
        "use_adaptive_dte": True,
        "exit_on_cloud_bear": True,
        "struct_good_mult": 1.20,
        "struct_weak_mult": 0.60,
        "ob_chase_mult": 0.35,
        "os_boost_mult": 1.15,
    },
    "os_boost_only": {
        "need_structure": True,
        "use_soft_structure": False,
        "use_soft_ob": False,
        "use_os_boost": True,
        "use_soft_vol": False,
        "use_adaptive_dte": False,
        "exit_on_cloud_bear": False,
        "struct_good_mult": 1.0,
        "struct_weak_mult": 1.0,
        "os_boost_mult": 1.20,
    },
    "exit_cloud_only": {
        "need_structure": True,
        "use_soft_structure": False,
        "use_soft_ob": False,
        "use_os_boost": False,
        "use_soft_vol": False,
        "use_adaptive_dte": False,
        "exit_on_cloud_bear": True,
        "struct_good_mult": 1.0,
        "struct_weak_mult": 1.0,
    },
    "soft_vol_only": {
        "need_structure": True,
        "use_soft_structure": False,
        "use_soft_ob": False,
        "use_os_boost": False,
        "use_soft_vol": True,
        "use_adaptive_dte": False,
        "exit_on_cloud_bear": False,
        "struct_good_mult": 1.0,
        "struct_weak_mult": 1.0,
    },
}


def run_one(name: str, overrides: dict) -> dict:
    run_dir = OUT / name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "code").mkdir(parents=True)
    shutil.copy2(ENG, run_dir / "code" / "signal_engine.py")
    cfg = json.loads(CFG_BASE.read_text())
    cfg["strategy"] = {**cfg.get("strategy", {}), "ablation": name}
    (run_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    hc = {**COMMON, **overrides}
    (run_dir / "hunt_config.json").write_text(json.dumps(hc, indent=2))
    # also put hunt next to code for loader parents[1]
    shutil.copy2(run_dir / "hunt_config.json", run_dir / "code" / "hunt_config.json")
    print(f"\n=== RUN {name} ===", flush=True)
    bt_main(run_dir.resolve())
    metrics_path = run_dir / "artifacts" / "metrics.csv"
    card = run_dir / "run_card.json"
    if card.exists():
        m = json.loads(card.read_text()).get("metrics", {})
    else:
        # parse csv header
        lines = metrics_path.read_text().strip().splitlines()
        keys = lines[0].split(",")
        vals = lines[1].split(",")
        m = {k: float(v) if k != "trade_count" else int(float(v)) for k, v in zip(keys, vals)}
    row = {
        "id": name,
        "total_return": m.get("total_return"),
        "max_drawdown": m.get("max_drawdown"),
        "sharpe": m.get("sharpe"),
        "trade_count": m.get("trade_count"),
        "win_rate": m.get("win_rate"),
        "profit_loss_ratio": m.get("profit_loss_ratio"),
        "final_value": m.get("final_value"),
    }
    print(json.dumps(row, indent=2), flush=True)
    return row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = {
        "id": "v28_baseline",
        "total_return": 1.040993,
        "max_drawdown": -0.111673,
        "sharpe": 1.4003,
        "trade_count": 30,
        "win_rate": 0.8,
        "profit_loss_ratio": 2.3731,
        "final_value": 2040992.82,
    }
    rows = [baseline]
    for name, ov in VARIANTS.items():
        try:
            rows.append(run_one(name, ov))
        except Exception as e:  # noqa: BLE001
            rows.append({"id": name, "error": str(e)})
            print(f"FAIL {name}: {e}", flush=True)

    # rank by (sharpe, total_return) beating baseline first
    def score(r):
        if r.get("error") or r.get("sharpe") is None:
            return (-999, -999)
        return (float(r["sharpe"]), float(r["total_return"]))

    ranked = sorted(rows, key=score, reverse=True)
    beats = [
        r
        for r in rows
        if not r.get("error")
        and r["id"] != "v28_baseline"
        and r.get("sharpe") is not None
        and (
            float(r["sharpe"]) > baseline["sharpe"]
            or (
                float(r["sharpe"]) >= baseline["sharpe"] - 0.02
                and float(r["total_return"]) > baseline["total_return"]
            )
        )
        and float(r.get("total_return", -1)) >= 0.90
    ]
    summary = {
        "baseline": baseline,
        "results": rows,
        "ranked_by_sharpe_then_ret": ranked,
        "beats_v28": beats,
        "best": ranked[0] if ranked else None,
    }
    (OUT / "ABLATION_SUMMARY.json").write_text(json.dumps(summary, indent=2))
    print("\n===== SUMMARY =====")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT / 'ABLATION_SUMMARY.json'}")


if __name__ == "__main__":
    main()
