#!/usr/bin/env python3
"""Persistent live adaptation state for desk / paper / future IB hooks.

Stores streak multipliers from closed paper (or live) trades so engines and
trade_desk can scale size without reloading a full SignalEngine instance.

State file: runs/live_adapt/STATE.json
IB ticket template: runs/live_adapt/LAST_TICKET.json (written by export_ib_ticket)

Usage:
  .venv/bin/python tools/live_adapt.py snapshot --json
  .venv/bin/python tools/live_adapt.py record --model v39b_live_adapt --symbol IONQ --pnl 85 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "runs" / "live_adapt"
STATE_PATH = STATE_DIR / "STATE.json"
TICKET_PATH = STATE_DIR / "LAST_TICKET.json"
HISTORY_MAX = 80


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def default_state() -> dict[str, Any]:
    return {
        "asof": _utc(),
        "global": {"streak_mult": 1.0, "consec": 0, "n": 0, "wins": 0, "losses": 0},
        "by_model": {},
        "by_symbol": {},
        "history": [],
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return default_state()
    try:
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return default_state()
        d.setdefault("global", default_state()["global"])
        d.setdefault("by_model", {})
        d.setdefault("by_symbol", {})
        d.setdefault("history", [])
        return d
    except Exception:
        return default_state()


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["asof"] = _utc()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _bucket_update(bucket: dict[str, Any], won: bool, after_win: float = 1.09, after_loss: float = 0.73) -> dict[str, Any]:
    """Same spirit as v39b _live_streak_update — stack then mean-revert toward 1."""
    sm = float(bucket.get("streak_mult") or 1.0)
    consec = int(bucket.get("consec") or 0)
    if won:
        consec = consec + 1 if consec > 0 else 1
        boost = after_win * (1.0 + 0.04 * min(consec, 4))
        sm = min(1.45, sm * 0.35 + boost * 0.65)
        bucket["wins"] = int(bucket.get("wins") or 0) + 1
    else:
        consec = consec - 1 if consec < 0 else -1
        cut = after_loss * (1.0 - 0.05 * min(abs(consec), 4))
        sm = max(0.45, sm * 0.40 + cut * 0.60)
        bucket["losses"] = int(bucket.get("losses") or 0) + 1
    sm = 0.85 * sm + 0.15 * 1.0
    bucket["streak_mult"] = _clip(sm, 0.45, 1.45)
    bucket["consec"] = consec
    bucket["n"] = int(bucket.get("n") or 0) + 1
    return bucket


def record_outcome(
    *,
    pnl: float,
    symbol: str = "",
    model: str = "",
    r_multiple: float | None = None,
    tags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a closed trade outcome; updates global / model / symbol streaks."""
    state = load_state()
    won = float(pnl) >= 0.0
    sym = str(symbol or "").upper().replace(".US", "")
    mid = str(model or "unknown")
    empty = {"streak_mult": 1.0, "consec": 0, "n": 0, "wins": 0, "losses": 0}

    g = _bucket_update(dict(state.get("global") or empty), won)
    state["global"] = g

    by_m = dict(state.get("by_model") or {})
    by_m[mid] = _bucket_update(dict(by_m.get(mid) or empty), won)
    state["by_model"] = by_m

    by_s = dict(state.get("by_symbol") or {})
    if sym:
        by_s[sym] = _bucket_update(dict(by_s.get(sym) or empty), won)
        state["by_symbol"] = by_s

    hist = list(state.get("history") or [])
    hist.append(
        {
            "ts": _utc(),
            "symbol": sym,
            "model": mid,
            "pnl": float(pnl),
            "r_multiple": r_multiple,
            "won": won,
            "tags": tags or {},
            "streak_mult": g["streak_mult"],
        }
    )
    state["history"] = hist[-HISTORY_MAX:]
    save_state(state)
    return {
        "ok": True,
        "won": won,
        "global": state["global"],
        "model_bucket": by_m.get(mid),
        "symbol_bucket": by_s.get(sym) if sym else None,
        "asof": state["asof"],
        "size_mult": size_mult_for(mid, sym or None),
    }


def size_mult_for(model: str | None = None, symbol: str | None = None) -> float:
    """Combined size mult for desk sizing (model × soft symbol × global)."""
    state = load_state()
    g = float((state.get("global") or {}).get("streak_mult") or 1.0)
    m = 1.0
    if model:
        m = float((state.get("by_model") or {}).get(model, {}).get("streak_mult") or 1.0)
    s = 1.0
    if symbol:
        sym = str(symbol).upper().replace(".US", "")
        s = float((state.get("by_symbol") or {}).get(sym, {}).get("streak_mult") or 1.0)
    # blend: model heaviest, then symbol, light global
    blended = 0.55 * m + 0.30 * s + 0.15 * g
    return _clip(blended, 0.45, 1.45)


def snapshot() -> dict[str, Any]:
    state = load_state()
    recent = list(state.get("history") or [])[-12:]
    wr = None
    if recent:
        wr = sum(1 for h in recent if h.get("won")) / len(recent)
    return {
        "ok": True,
        "asof": state.get("asof"),
        "global": state.get("global"),
        "by_model": state.get("by_model"),
        "by_symbol": state.get("by_symbol"),
        "recent_n": len(recent),
        "recent_wr": wr,
        "size_mult_default": size_mult_for(),
        "path": str(STATE_PATH.relative_to(ROOT)),
    }


def export_ib_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Write a flat IB-ready order ticket (human + bot readable). Does not place orders."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "asof": _utc(),
        "broker": "ibkr_ready",
        "note": "Manual / future IB bridge — desk does not auto-send orders.",
        "ticket": ticket,
        "adapt": {
            "size_mult": size_mult_for(ticket.get("model"), ticket.get("symbol")),
            "snapshot": snapshot(),
        },
    }
    tmp = TICKET_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(TICKET_PATH)
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live adapt state for desk / paper / IB hooks")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="Show adapt state")
    p_snap.add_argument("--json", action="store_true")

    p_rec = sub.add_parser("record", help="Record closed trade outcome")
    p_rec.add_argument("--model", default="")
    p_rec.add_argument("--symbol", default="")
    p_rec.add_argument("--pnl", type=float, required=True)
    p_rec.add_argument("--r", type=float, default=None)
    p_rec.add_argument("--json", action="store_true")

    p_mult = sub.add_parser("mult", help="Size mult for model/symbol")
    p_mult.add_argument("--model", default="")
    p_mult.add_argument("--symbol", default="")
    p_mult.add_argument("--json", action="store_true")

    p_ib = sub.add_parser("ib-ticket", help="Write LAST_TICKET.json from stdin JSON or flags")
    p_ib.add_argument("--symbol", default="")
    p_ib.add_argument("--side", default="BUY")
    p_ib.add_argument("--qty", type=float, default=0)
    p_ib.add_argument("--entry", type=float, default=0)
    p_ib.add_argument("--stop", type=float, default=0)
    p_ib.add_argument("--model", default="")
    p_ib.add_argument("--vehicle", default="equity")
    p_ib.add_argument("--json", action="store_true")

    ns = ap.parse_args(argv)
    if ns.cmd == "snapshot":
        out = snapshot()
        print(json.dumps(out, indent=2 if ns.json else None))
        return 0
    if ns.cmd == "record":
        out = record_outcome(pnl=ns.pnl, symbol=ns.symbol, model=ns.model, r_multiple=ns.r)
        print(json.dumps(out, indent=2 if ns.json else None))
        return 0
    if ns.cmd == "mult":
        m = size_mult_for(ns.model or None, ns.symbol or None)
        print(json.dumps({"size_mult": m, "model": ns.model, "symbol": ns.symbol}))
        return 0
    if ns.cmd == "ib-ticket":
        ticket = {
            "symbol": ns.symbol.upper().replace(".US", ""),
            "side": ns.side.upper(),
            "qty": ns.qty,
            "order_type": "LMT" if ns.entry else "MKT",
            "limit": ns.entry or None,
            "stop": ns.stop or None,
            "tif": "DAY",
            "model": ns.model,
            "vehicle": ns.vehicle,
        }
        out = export_ib_ticket(ticket)
        print(json.dumps(out, indent=2 if ns.json else None, default=str))
        return 0
    return 1


if __name__ == "__main__":
    # fix double-count bug in first draft of record_outcome - rewrite cleanly
    sys.exit(main())
