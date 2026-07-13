"""Direction edge report — hit@k, MFE/MAE, and regime-sliced expectancy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from backtest.metrics import calc_bars_per_year
from tools.evolve import regime_gate

ROOT = Path(__file__).resolve().parents[1]


def _pair_trades(trades_csv: Path) -> pd.DataFrame:
    """Convert two-row-per-trade CSV into one-row-per-trade."""
    df = pd.read_csv(trades_csv)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "entry_time", "exit_time", "symbol", "direction",
                "entry_price", "exit_price", "size", "pnl", "pnl_pct",
                "holding_days", "exit_reason",
            ]
        )
    rows = []
    df = df.reset_index(drop=True)
    for i in range(0, len(df) - 1, 2):
        entry = df.iloc[i]
        exit_ = df.iloc[i + 1]
        entry_side = str(entry.get("side", "buy")).lower()
        direction = 1 if entry_side == "buy" else -1
        rows.append(
            {
                "entry_time": pd.to_datetime(entry["timestamp"]),
                "exit_time": pd.to_datetime(exit_["timestamp"]),
                "symbol": entry.get("code", ""),
                "direction": direction,
                "entry_price": float(entry["price"]),
                "exit_price": float(exit_["price"]),
                "size": float(entry["qty"]),
                "pnl": float(exit_["pnl"]),
                "pnl_pct": float(exit_["return_pct"]),
                "holding_days": int(exit_["holding_days"]) if exit_["holding_days"] else 0,
                "exit_reason": str(exit_.get("reason", "")),
            }
        )
    return pd.DataFrame(rows)


def _load_bars(run_dir: Path) -> dict[str, pd.DataFrame]:
    """Load OHLCV bars from run_dir artifacts."""
    bars = {}
    art = run_dir / "artifacts"
    for p in art.glob("ohlcv_*.csv"):
        symbol = p.stem.replace("ohlcv_", "")
        df = pd.read_csv(p, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        bars[symbol] = df[["open", "high", "low", "close", "volume"]].astype(float)
    return bars


def _initial_cash(run_dir: Path) -> float:
    cfg = run_dir / "config.json"
    if cfg.exists():
        try:
            return float(json.loads(cfg.read_text()).get("initial_cash", 1_000_000))
        except Exception:
            pass
    return 1_000_000.0


def _hit_rate(
    trades: pd.DataFrame, bars: dict[str, pd.DataFrame], k: int
) -> dict[str, Any]:
    """hit@k and binomial statistics."""
    hits = []
    for _, t in trades.iterrows():
        symbol = t["symbol"]
        if symbol not in bars:
            continue
        close = bars[symbol]["close"].sort_index()
        # For 1H trades.csv has only date; for 1D exact. Use first bar on/after entry date.
        idx = close.index.searchsorted(t["entry_time"])
        if idx >= len(close):
            continue
        if idx + k >= len(close):
            continue
        close_k = close.iloc[idx + k]
        hit = float((close_k - t["entry_price"]) * t["direction"]) > 0
        hits.append(hit)
    n = len(hits)
    if n == 0:
        return {"rate": 0.0, "n": 0, "p_value": 1.0, "ci_low": 0.0, "ci_high": 0.0}
    k_hits = sum(hits)
    rate = k_hits / n
    # Wilson 95% CI
    z = 1.959963984540054
    denom = 1.0 + z * z / n
    center = (rate + z * z / (2 * n)) / denom
    margin = (
        z
        * np.sqrt((rate * (1 - rate) + z * z / (4 * n)) / n)
        / denom
    )
    ci_low = max(0.0, center - margin)
    ci_high = min(1.0, center + margin)
    # one-sided binomial test vs 0.5
    try:
        p_value = float(stats.binomtest(k=k_hits, n=n, p=0.5, alternative="greater").pvalue)
    except Exception:
        p_value = 1.0
    return {
        "rate": rate,
        "n": n,
        "p_value": p_value,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def _mfe_mae(trades: pd.DataFrame, bars: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Median MFE and MAE within holding period, in dollars and percent."""
    mfe_list = []
    mae_list = []
    for _, t in trades.iterrows():
        symbol = t["symbol"]
        if symbol not in bars:
            continue
        df = bars[symbol]
        # Slice bars in [entry_date, exit_date] (best-effort for 1H date-only timestamps)
        mask = (df.index.date >= t["entry_time"].date()) & (df.index.date <= t["exit_time"].date())
        slice_ = df[mask]
        if slice_.empty:
            continue
        high = float(slice_["high"].max())
        low = float(slice_["low"].min())
        entry = float(t["entry_price"])
        direction = int(t["direction"])
        if direction == 1:
            mfe = max(0.0, high - entry)
            mae = max(0.0, entry - low)
        else:
            mfe = max(0.0, entry - low)
            mae = max(0.0, high - entry)
        mfe_list.append(mfe)
        mae_list.append(mae)
    if not mfe_list:
        return {"mfe_median": 0.0, "mae_median": 0.0, "mfe_mae_ratio": 0.0}
    mfe_m = float(np.median(mfe_list))
    mae_m = float(np.median(mae_list))
    return {
        "mfe_median": mfe_m,
        "mae_median": mae_m,
        "mfe_mae_ratio": mfe_m / mae_m if mae_m > 1e-12 else 0.0,
    }


def _regime_slices(
    trades: pd.DataFrame, initial_cash: float, regime_parquet: Path | None
) -> dict[str, Any]:
    """Expectancy, win rate, and approximate DD per regime label."""
    if trades.empty:
        return {}
    labels = []
    for _, t in trades.iterrows():
        labels.append(regime_gate.regime_label_at(t["entry_time"], regime_parquet))
    trades = trades.copy()
    trades["regime"] = labels
    slices = {}
    for label, group in trades.groupby("regime"):
        pnls = group["pnl"].astype(float)
        group_sorted = group.sort_values("entry_time")
        eq = 1.0 + (group_sorted["pnl"].astype(float).cumsum() / max(initial_cash, 1.0))
        peak = eq.cummax()
        dd = (eq - peak) / peak.replace(0, 1)
        slices[str(label)] = {
            "n": int(len(pnls)),
            "expectancy": float(pnls.mean()),
            "win_rate": float((pnls > 0).mean()),
            "ret": float(eq.iloc[-1] - 1.0),
            "max_drawdown": float(dd.min()),
        }
    return slices


def _bars_per_day(run_dir: Path) -> float:
    cfg = run_dir / "config.json"
    if cfg.exists():
        try:
            interval = json.loads(cfg.read_text()).get("interval", "1D")
            return calc_bars_per_year(interval, "yfinance") / 252.0
        except Exception:
            pass
    return 1.0


def build_direction_report(
    trades_csv: str | Path,
    bars: dict[str, pd.DataFrame],
    ks: tuple[int, ...] = (3, 5, 10),
    regime_parquet: Path | str | None = None,
) -> dict[str, Any]:
    """Build DIRECTION report dict from trades CSV and OHLCV bars."""
    trades_csv = Path(trades_csv)
    run_dir = trades_csv.parent.parent
    trades = _pair_trades(trades_csv)
    initial_cash = _initial_cash(run_dir)
    bpd = _bars_per_day(run_dir)

    if regime_parquet is None:
        regime_parquet = ROOT / "models" / "_shared" / "regime" / "regime_daily.parquet"
    else:
        regime_parquet = Path(regime_parquet)

    hit_rates = {f"hit_{k}d": _hit_rate(trades, bars, max(1, int(k * bpd))) for k in ks}
    mfe_mae = _mfe_mae(trades, bars)
    slices = _regime_slices(trades, initial_cash, regime_parquet)

    return {
        "n_trades": int(len(trades)),
        "expectancy": float(trades["pnl"].mean()) if not trades.empty else 0.0,
        "win_rate": float((trades["pnl"] > 0).mean()) if not trades.empty else 0.0,
        "hit": hit_rates,
        "mfe_mae": mfe_mae,
        "regime_slices": slices,
    }


def _md_report(report: dict[str, Any]) -> str:
    lines = ["# Direction Report\n", f"Trades: {report['n_trades']}  "]
    lines.append(f"Expectancy: ${report['expectancy']:.2f}")
    lines.append(f"Win rate: {report['win_rate']:.2%}\n")
    lines.append("## Hit rates")
    for k, v in report["hit"].items():
        lines.append(f"- {k}: {v['rate']:.2%} (n={v['n']}, p={v['p_value']:.4f}, CI={v['ci_low']:.2%}-{v['ci_high']:.2%})")
    lines.append("\n## MFE/MAE")
    m = report["mfe_mae"]
    lines.append(f"- MFE median: ${m['mfe_median']:.2f}")
    lines.append(f"- MAE median: ${m['mae_median']:.2f}")
    lines.append(f"- MFE/MAE ratio: {m['mfe_mae_ratio']:.2f}")
    lines.append("\n## Regime slices")
    for label, v in report.get("regime_slices", {}).items():
        lines.append(
            f"- {label}: n={v['n']}, exp=${v['expectancy']:.2f}, wr={v['win_rate']:.2%}, "
            f"ret={v['ret']:.2%}, dd={v['max_drawdown']:.2%}"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build direction report")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--regime-parquet", type=Path, default=None)
    args = parser.parse_args()

    run_dir = args.run_dir
    trades_csv = run_dir / "artifacts" / "trades.csv"
    if not trades_csv.exists():
        raise FileNotFoundError(f"no trades.csv in {run_dir / 'artifacts'}")
    bars = _load_bars(run_dir)
    report = build_direction_report(trades_csv, bars, regime_parquet=args.regime_parquet)

    out = args.out or (run_dir / "DIRECTION.json")
    out.write_text(json.dumps(report, indent=2, default=float))
    md_path = out.with_suffix(".md")
    md_path.write_text(_md_report(report))
    print(out)


if __name__ == "__main__":
    main()
