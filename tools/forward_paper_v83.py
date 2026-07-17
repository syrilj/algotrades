#!/usr/bin/env python3
"""Forward paper-trading harness for poc_va_macdha models.

Pulls the latest 1H bars from yfinance, runs the selected signal engine, and
reconciles target weights against open paper positions logged to paper_ledger.
Dry-run by default; pass --execute to append events.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.institutional_flow.features import compute_features  # noqa: E402
from tools.paper_ledger import close_trade, mark_positions, open_trade, replay_positions  # noqa: E402

EQUITY_WINNER_BAG = ["TSLA.US", "MU.US", "SPY.US", "IONQ.US", "APLD.US", "XLP.US", "QQQ.US"]
DEFAULT_MODEL = "v84_macro_sleeve"
DEFAULT_CASH = 1000.0
DEFAULT_ATR_MULT = 1.5
MIN_BARS = 50


def _load_engine(model_id: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        f"{model_id}_forward_engine",
        ROOT / "models" / "poc_va_macdha" / model_id / "signal_engine.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod.SignalEngine()


def _fetch_bars(code: str, lookback_days: int) -> pd.DataFrame | None:
    ticker = code.replace(".US", "")
    try:
        df = yf.download(ticker, period=f"{lookback_days}d", interval="1h", progress=False, auto_adjust=True)
    except Exception as exc:
        print(f"[{code}] yfinance error: {exc}", file=sys.stderr)
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=lambda c: c.lower().split(" ")[0])
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            return None
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def _latest_atr_pct(df: pd.DataFrame) -> float:
    try:
        feats = compute_features(df)
        return float(feats["atr_pct"].iloc[-1])
    except Exception:
        return 0.0


def _symbol(code: str) -> str:
    return code.replace(".US", "")


def _confidence(engine: Any, code: str) -> float | None:
    raw = engine.last_confidence.get(code)
    if isinstance(raw, pd.Series) and not raw.empty:
        return float(raw.iloc[-1])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Forward paper-trading harness for poc_va_macdha models")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="model directory name under models/poc_va_macdha")
    ap.add_argument("--execute", action="store_true", help="append events to paper_ledger")
    ap.add_argument("--cash", type=float, default=DEFAULT_CASH)
    ap.add_argument("--symbols", default=",".join(EQUITY_WINNER_BAG))
    ap.add_argument("--atr-mult", type=float, default=DEFAULT_ATR_MULT)
    ap.add_argument("--lookback-days", type=int, default=60)
    args = ap.parse_args()

    model_id = args.model
    codes = [c.strip() for c in args.symbols.split(",") if c.strip()]
    engine = _load_engine(model_id)
    positions = replay_positions()
    open_by_symbol = {
        _symbol(p["symbol"]): p
        for p in positions.values()
        if p.get("status") == "open" and p.get("model") == model_id
    }

    data_map: dict[str, pd.DataFrame] = {}
    atr_map: dict[str, float] = {}
    for code in codes:
        df = _fetch_bars(code, args.lookback_days)
        if df is None or len(df) < MIN_BARS:
            continue
        data_map[code] = df
        atr_map[code] = _latest_atr_pct(df)

    if not data_map:
        print(json.dumps({"ok": False, "error": "no data fetched"}))
        return 1

    signals = engine.generate(data_map)
    actions: list[dict[str, Any]] = []

    for code, sig in signals.items():
        if sig is None or sig.empty or code not in data_map:
            continue
        last_weight = float(sig.iloc[-1])
        df = data_map[code]
        last_price = float(df["close"].iloc[-1])
        sym = _symbol(code)
        atr = last_price * atr_map.get(code, 0.0)
        pos = open_by_symbol.get(sym)

        if last_weight <= 0.0:
            if pos is not None:
                if args.execute:
                    close_trade(pos["id"], last_price, reason="signal_flat")
                actions.append({"action": "close", "id": pos["id"], "code": code, "exit": last_price, "reason": "signal_flat"})
            continue

        target_notional = args.cash * last_weight
        shares = int(target_notional / last_price) if last_price > 0 else 0
        if shares <= 0:
            continue
        stop = last_price - args.atr_mult * atr

        if pos is None:
            if args.execute:
                p = open_trade(
                    symbol=code,
                    side="long",
                    shares=shares,
                    entry=last_price,
                    stop=stop,
                    model=model_id,
                    account=args.cash,
                    confidence=_confidence(engine, code),
                    reason=f"{model_id} forward signal",
                    source="forward_paper",
                    notes=f"weight={last_weight:.4f}",
                )
                actions.append({"action": "open", "id": p["id"], "code": code, "shares": shares, "entry": last_price, "stop": stop})
            else:
                actions.append({"action": "open_dry", "code": code, "shares": shares, "entry": last_price, "stop": stop})

    mark_positions()
    latest_weights = {code: float(s.iloc[-1]) for code, s in signals.items() if s is not None and not s.empty}
    snapshot = {"ok": True, "model": model_id, "dry_run": not args.execute, "latest_weights": latest_weights, "actions": actions, "asof": datetime.now(timezone.utc).isoformat()}
    print(json.dumps(snapshot, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
