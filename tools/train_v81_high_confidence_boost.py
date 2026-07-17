#!/usr/bin/env python3
"""Train-only selection and locked-holdout verification for v81.

The variant menu is deliberately small and fixed in this file.  Target-weight
floors are selected on the registered train window only.  The winning rule is
written to the model and then evaluated once on the locked holdout.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402
from evolve.farm import EQUITY_WINNER_BAG  # noqa: E402


MODELS = ROOT / "models" / "poc_va_macdha"
TARGET = MODELS / "v81_high_confidence_boost"
OUT = ROOT / "runs" / "v81_high_confidence_boost"
TRAIN = ("2024-08-01", "2025-08-01")
HOLDOUT = ("2025-08-01", "2026-07-11")
FULL = ("2024-08-01", "2026-07-11")

# Pre-registered before candidate evaluation.  A 30% floor is nearly an
# ablation; 50% is the existing per-symbol hard cap.
TARGET_WEIGHTS = [0.30, 0.35, 0.40, 0.45, 0.50]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wilson_interval(wins: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    """Two-sided Wilson interval; default z gives an approximate 95% interval."""
    if n <= 0:
        return None
    p = float(wins) / float(n)
    den = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / den
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / den
    return [center - half, center + half]


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "tag", "start", "end", "cash", "ret", "dd", "sharpe", "n", "wr", "final", "path", "error")
    return {k: row.get(k) for k in keys if k in row}


def _fmt(row: dict[str, Any]) -> str:
    if row.get("error"):
        return f"FAIL {row['error']}"
    return (
        f"ret={float(row.get('ret') or 0)*100:7.1f}% "
        f"dd={float(row.get('dd') or 0)*100:6.1f}% "
        f"sh={float(row.get('sharpe') or 0):5.2f} "
        f"n={int(row.get('n') or 0):3d} wr={float(row.get('wr') or 0)*100:5.1f}%"
    )


def _discover_one(model_id: str) -> dict[str, Any]:
    found = dmr.discover_models([model_id])
    if not found:
        raise FileNotFoundError(f"model not discoverable: {model_id}")
    return found[0]


def _run(model_id: str, window: tuple[str, str], tag: str, cash: float, *, reuse: bool) -> dict[str, Any]:
    return dmr.run_one(
        _discover_one(model_id),
        mode="daily",
        codes=EQUITY_WINNER_BAG,
        start=window[0],
        end=window[1],
        tag=tag,
        cash=cash,
        force_1d=False,
        source="local",
        interval="1H",
        reuse=reuse,
    )


def _hunt_for(target_weight: float, variant_id: str) -> dict[str, Any]:
    return {
        "base_model": "v72_dual_sleeve",
        "precision_model": "v70_high_confidence_wr",
        "precision_target_weight": float(target_weight),
        "max_weight": 0.50,
        "high_confidence_target": 0.90,
        "allow_precision_orphans": False,
        "selection_rule": "train_only_then_locked_holdout",
        "train_window_end": TRAIN[1],
        "variant_id": variant_id,
        "hypothesis": (
            "Raise an already-active v72 target only when the v70 hard-quality "
            "sleeve agrees; retain v72 exits and breadth."
        ),
    }


def _materialize(target_weight: float) -> str:
    suffix = int(round(target_weight * 100))
    model_id = f"v81hc_t{suffix:02d}"
    dest = MODELS / model_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TARGET, dest)
    hunt = _hunt_for(target_weight, f"target_{suffix:02d}")
    (dest / "hunt_config.json").write_text(json.dumps(hunt, indent=2) + "\n")
    cfg_path = dest / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg.setdefault("strategy", {})["name"] = model_id
    cfg["strategy"]["model_version"] = model_id
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return model_id


def _cleanup(model_ids: list[str]) -> None:
    for model_id in model_ids:
        path = MODELS / model_id
        if path.exists() and model_id.startswith("v81hc_t"):
            shutil.rmtree(path, ignore_errors=True)


def _train_score(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    if row.get("error"):
        return -1e9
    if int(row.get("n") or 0) < max(40, int(baseline.get("n") or 0) - 5):
        return -1e8
    ret_delta = float(row.get("ret") or 0) - float(baseline.get("ret") or 0)
    sh_delta = float(row.get("sharpe") or 0) - float(baseline.get("sharpe") or 0)
    dd_excess = max(
        0.0,
        abs(float(row.get("dd") or 0)) - abs(float(baseline.get("dd") or 0)) - 0.015,
    )
    return ret_delta + 0.20 * sh_delta - 1.50 * dd_excess


def _promotion(
    candidate_full: dict[str, Any],
    candidate_holdout: dict[str, Any],
    base_full: dict[str, Any],
    base_holdout: dict[str, Any],
    precision_holdout: dict[str, Any],
) -> tuple[bool, list[str]]:
    checks = {
        "holdout_return_beats_v72": float(candidate_holdout.get("ret") or 0) > float(base_holdout.get("ret") or 0),
        "holdout_sharpe_beats_v72": float(candidate_holdout.get("sharpe") or 0) > float(base_holdout.get("sharpe") or 0),
        "holdout_dd_within_2pp": abs(float(candidate_holdout.get("dd") or -1)) <= abs(float(base_holdout.get("dd") or 0)) + 0.02,
        "holdout_n_at_least_80": int(candidate_holdout.get("n") or 0) >= 80,
        "full_return_beats_v72": float(candidate_full.get("ret") or 0) > float(base_full.get("ret") or 0),
        "precision_holdout_wr_at_least_90pct": float(precision_holdout.get("wr") or 0) >= 0.90,
        "precision_holdout_n_at_least_10": int(precision_holdout.get("n") or 0) >= 10,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return not failed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and verify v81 high-confidence boost")
    parser.add_argument("--cash", type=float, default=1000.0)
    parser.add_argument("--keep-scratch", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "updated_at": _now(),
        "protocol": {
            "train": list(TRAIN),
            "holdout": list(HOLDOUT),
            "full": list(FULL),
            "target_weights": TARGET_WEIGHTS,
            "bag": EQUITY_WINNER_BAG,
            "source": "local",
            "interval": "1H",
            "cash": args.cash,
            "holdout_retune_forbidden": True,
        },
        "promoted": False,
    }
    (OUT / "STATE.json").write_text(json.dumps(state, indent=2) + "\n")

    print("=== frozen baselines ===", flush=True)
    base_train = _run("v72_dual_sleeve", TRAIN, "v81_base_train", args.cash, reuse=True)
    base_holdout = _run("v72_dual_sleeve", HOLDOUT, "v81_base_holdout", args.cash, reuse=True)
    base_full = _run("v72_dual_sleeve", FULL, "v81_base_full", args.cash, reuse=True)
    precision_holdout = _run("v70_high_confidence_wr", HOLDOUT, "v81_precision_holdout", args.cash, reuse=True)
    for name, row in (
        ("v72 train", base_train),
        ("v72 holdout", base_holdout),
        ("v72 full", base_full),
        ("v70 holdout", precision_holdout),
    ):
        print(f"  {name:15} {_fmt(row)}", flush=True)

    aliases: list[str] = []
    train_rows: list[dict[str, Any]] = []
    try:
        print("\n=== train-only target sweep ===", flush=True)
        for target_weight in TARGET_WEIGHTS:
            model_id = _materialize(target_weight)
            aliases.append(model_id)
            row = _run(model_id, TRAIN, "v81_train_select", args.cash, reuse=False)
            row["precision_target_weight"] = target_weight
            row["train_score"] = _train_score(row, base_train)
            train_rows.append(row)
            print(
                f"  target={target_weight:.2f} {_fmt(row)} score={row['train_score']:+.4f}",
                flush=True,
            )

        viable = [r for r in train_rows if not r.get("error")]
        if not viable:
            raise RuntimeError("all v81 train variants failed")
        best = max(viable, key=lambda r: float(r.get("train_score") or -1e9))
        selected_weight = float(best["precision_target_weight"])
        selected_variant = f"target_{int(round(selected_weight * 100)):02d}"
        frozen_hunt = _hunt_for(selected_weight, selected_variant)
        (TARGET / "hunt_config.json").write_text(json.dumps(frozen_hunt, indent=2) + "\n")
        print(f"\nFROZEN train winner: {selected_variant} target={selected_weight:.2f}", flush=True)
    finally:
        if not args.keep_scratch:
            _cleanup(aliases)

    print("\n=== locked holdout (one evaluation) ===", flush=True)
    candidate_holdout = _run("v81_high_confidence_boost", HOLDOUT, "v81_locked_holdout", args.cash, reuse=False)
    print(f"  v81 holdout   {_fmt(candidate_holdout)}", flush=True)

    print("\n=== full-window reconciliation ===", flush=True)
    candidate_full = _run("v81_high_confidence_boost", FULL, "v81_full_reconcile", args.cash, reuse=False)
    print(f"  v81 full      {_fmt(candidate_full)}", flush=True)

    promoted, failed = _promotion(
        candidate_full,
        candidate_holdout,
        base_full,
        base_holdout,
        precision_holdout,
    )
    state.update(
        {
            "updated_at": _now(),
            "selected": {
                "variant_id": selected_variant,
                "precision_target_weight": selected_weight,
                "train_score": float(best["train_score"]),
            },
            "train_rows": [_clean(r) | {"precision_target_weight": r["precision_target_weight"], "train_score": r["train_score"]} for r in train_rows],
            "baselines": {
                "v72_train": _clean(base_train),
                "v72_holdout": _clean(base_holdout),
                "v72_full": _clean(base_full),
                "v70_precision_holdout": _clean(precision_holdout),
            },
            "candidate": {
                "holdout": _clean(candidate_holdout),
                "full": _clean(candidate_full),
            },
            "promoted": promoted,
            "promotion_failed": failed,
            "confidence_note": (
                "v70 precision subset reached 90.9% holdout WR at n=11; this is thin "
                "evidence and not a guaranteed 90% probability."
            ),
        }
    )
    (OUT / "STATE.json").write_text(json.dumps(state, indent=2) + "\n")

    results = {
        "status": "promoted" if promoted else "research_only",
        "research_only": not promoted,
        "portfolio": {
            "total_return": candidate_full.get("ret"),
            "max_drawdown": candidate_full.get("dd"),
            "sharpe": candidate_full.get("sharpe"),
            "trade_count": candidate_full.get("n"),
            "win_rate": candidate_full.get("wr"),
            "final_value": candidate_full.get("final"),
        },
        "holdout": _clean(candidate_holdout),
        "precision_subset_holdout": _clean(precision_holdout),
        "selected_variant": state["selected"],
        "promoted": promoted,
        "promotion_failed": failed,
        "confidence_kind": "empirical_precision_subset_target_thin",
        "confidence_warning": (
            "0.90 marks v70-qualified episodes. Holdout evidence is 10 wins in "
            "11 trades and is too thin to guarantee a calibrated 90% probability."
        ),
        "precision_holdout_wilson_95": _wilson_interval(
            int(round(float(precision_holdout.get("wr") or 0) * int(precision_holdout.get("n") or 0))),
            int(precision_holdout.get("n") or 0),
        ),
    }
    (TARGET / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    lines = [
        "# v81 high-confidence boost",
        "",
        f"**Promoted:** {'yes' if promoted else 'no — research only'}",
        "",
        f"Frozen train winner: `{selected_variant}` (`precision_target_weight={selected_weight:.2f}`).",
        "",
        "| model | window | return | max DD | Sharpe | trades | win rate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for model, window, row in (
        ("v81", "holdout", candidate_holdout),
        ("v72", "holdout", base_holdout),
        ("v81", "full", candidate_full),
        ("v72", "full", base_full),
        ("v70 precision", "holdout", precision_holdout),
    ):
        lines.append(
            f"| {model} | {window} | {float(row.get('ret') or 0)*100:.1f}% | "
            f"{float(row.get('dd') or 0)*100:.1f}% | {float(row.get('sharpe') or 0):.2f} | "
            f"{int(row.get('n') or 0)} | {float(row.get('wr') or 0)*100:.1f}% |"
        )
    lines.extend(
        [
            "",
            "The precision subset targets 90% confidence and achieved 90.9% holdout win rate,",
            "but its holdout sample is only 11 trades. It remains thin evidence.",
            "",
            f"Failed promotion gates: `{failed}`" if failed else "All promotion gates passed.",
        ]
    )
    (OUT / "LEADERBOARD.md").write_text("\n".join(lines) + "\n")

    print(f"\nPROMOTED={promoted} failed={failed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
