"""Smoke tests for tools/evolve/loop_core.py with a fake backtest runner."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.evolve import loop_core


ROOT = Path(__file__).resolve().parents[2]


def _fake_run_one(model, *, mode, codes, start, end, tag, **kwargs):
    """Create a synthetic run_dir with trades/equity and return a dmr-style dict."""
    import re
    mid = model["id"]
    cash = kwargs.get("cash", 1_000_000)
    cash_tag = f"c{int(cash)}"
    run_dir = loop_core.DMR_OUT / "runs" / mid / f"{tag}__{mode}__{cash_tag}"
    if run_dir.exists():
        import shutil
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "code").mkdir()
    (run_dir / "signal_engine.py").write_text("# stub")

    cfg = {
        "source": "local",
        "codes": codes,
        "start_date": start,
        "end_date": end,
        "initial_cash": cash,
        "commission": 0.001,
        "engine": mode,
        "interval": kwargs.get("interval", "1H"),
        "slippage_us": kwargs.get("extra_cfg", {}).get("slippage_us", 0.001),
    }
    (run_dir / "config.json").write_text(json.dumps(cfg))

    art = run_dir / "artifacts"
    art.mkdir()

    # Generate a tiny trade list inside the OOS window
    days = pd.date_range(start, end)
    entries = days[-9:][::3]  # last 3 entries within the run window
    rows = []
    for entry in entries:
        exit_ = entry + pd.Timedelta(days=2)
        if exit_ > pd.Timestamp(end):
            continue
        rows.append({
            "timestamp": str(entry.date()), "code": codes[0], "side": "buy", "price": 100,
            "qty": 1, "reason": "signal", "pnl": 0, "holding_days": 0, "return_pct": 0,
        })
        rows.append({
            "timestamp": str(exit_.date()), "code": codes[0], "side": "sell", "price": 101,
            "qty": 1, "reason": "stop", "pnl": 1, "holding_days": 2, "return_pct": 0.01,
        })
    pd.DataFrame(rows).to_csv(art / "trades.csv", index=False)

    equity = pd.Series(1 + np.cumsum(np.random.normal(0.001, 0.01, len(days))), index=days)
    eq_df = pd.DataFrame({
        "ret": equity.pct_change().fillna(0),
        "equity": equity,
        "drawdown": 0.0,
        "benchmark_equity": 1.0,
        "active_ret": equity.pct_change().fillna(0),
    }, index=days)
    eq_df.index.name = "timestamp"
    eq_df.to_csv(art / "equity.csv")

    return {"path": str(run_dir.relative_to(ROOT)), "pnl": 3.0, "ret": 0.03, "n": 3}


def test_run_candidate_smoke(tmp_path: Path):
    # Point data cache to a temp dir
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({"codes": ["TSLA.US"], "interval": "1H"}))
    (model_dir / "signal_engine.py").write_text("# stub")
    model = loop_core._build_model(model_dir)

    # Use a tiny fold set
    fold_set = [
        {"name": "F1", "train_start": "2025-01-01", "train_end": "2025-01-15", "gap_days": 0, "oos_start": "2025-01-16", "oos_end": "2025-01-31", "warmup_start": "2025-01-01"},
        {"name": "F2", "train_start": "2025-01-01", "train_end": "2025-02-15", "gap_days": 0, "oos_start": "2025-02-16", "oos_end": "2025-02-28", "warmup_start": "2025-02-01"},
    ]

    candidate = loop_core.run_candidate(
        model,
        codes=["TSLA.US"],
        cash=1_000_000,
        campaign_id="test",
        gen=0,
        variant_id="stub",
        run_fn=_fake_run_one,
        fold_set=fold_set,
        probe_slippage=False,
    )
    assert candidate["fitness"] is not None
    assert candidate["direction_report"]["n_trades"] > 0
    assert (Path(candidate["run_dir"]) / "DIRECTION.json").exists()
