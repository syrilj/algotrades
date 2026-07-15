#!/usr/bin/env python3
"""Paper trade ledger — append-only events, replay-derived positions, live marks."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = ROOT / "runs" / "paper_ledger"
LEDGER_PATH = LEDGER_DIR / "ledger.jsonl"
MARKS_PATH = LEDGER_DIR / "MARKS.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _sym(symbol: str) -> tuple[str, str]:
    s = str(symbol).strip().upper().replace(".US", "")
    return s, f"{s}.US"


def _print_json(obj: Any) -> int:
    print(json.dumps(obj, default=str))
    return 0


def _err(msg: str) -> int:
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def load_events() -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in LEDGER_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_event(row: dict[str, Any]) -> dict[str, Any]:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    payload.setdefault("ts", _utc_now())
    with LEDGER_PATH.open("a") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


def replay_positions(events: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    events = events if events is not None else load_events()
    pos: dict[str, dict[str, Any]] = {}
    for ev in events:
        eid = ev.get("id")
        if not eid:
            continue
        kind = ev.get("event")
        if kind == "open":
            pos[eid] = {
                "id": eid,
                "symbol": ev.get("symbol"),
                "code": ev.get("code"),
                "side": ev.get("side", "long"),
                "shares": int(ev.get("shares") or 0),
                "entry": float(ev.get("entry") or 0),
                "stop": float(ev.get("stop") or 0),
                "trail_arm": ev.get("trail_arm"),
                "model": ev.get("model"),
                "model_reason": ev.get("model_reason"),
                "opened_at": ev.get("ts"),
                "account": ev.get("account"),
                "risk_pct": ev.get("risk_pct"),
                "dollar_risk": float(ev.get("dollar_risk") or 0),
                "action_at_entry": ev.get("action_at_entry"),
                "confidence": ev.get("confidence"),
                "override": bool(ev.get("override")),
                "source": ev.get("source"),
                "notes": ev.get("notes", ""),
                "status": "open",
                "mark": None,
                "mark_ts": None,
                "unrealized_pnl": None,
                "unrealized_r": None,
                "stop_hit": False,
                "trail_hit": False,
                "exit": None,
                "exit_reason": None,
                "pnl": None,
                "r_multiple": None,
                "closed_at": None,
                "holding_days": None,
            }
        elif kind == "close" and eid in pos:
            p = pos[eid]
            p["status"] = "closed"
            p["exit"] = float(ev.get("exit") or 0)
            p["exit_reason"] = ev.get("exit_reason") or "manual"
            p["pnl"] = float(ev.get("pnl") or 0)
            p["r_multiple"] = float(ev.get("r_multiple") or 0)
            p["closed_at"] = ev.get("ts")
            p["holding_days"] = ev.get("holding_days")
        elif kind == "cancel" and eid in pos:
            p = pos[eid]
            p["status"] = "cancelled"
            p["exit_reason"] = ev.get("reason") or "cancel"
            p["closed_at"] = ev.get("ts")
    return pos


def open_trade(
    symbol: str,
    side: str,
    shares: int,
    entry: float,
    stop: float,
    model: str,
    *,
    trail_arm: float | None = None,
    account: float | None = None,
    risk_pct: float | None = None,
    dollar_risk: float | None = None,
    action: str | None = None,
    confidence: float | None = None,
    override: bool = False,
    reason: str | None = None,
    source: str = "cli",
    notes: str = "",
) -> dict[str, Any]:
    sym, code = _sym(symbol)
    side_l = str(side).lower().strip()
    if side_l not in ("long", "short"):
        raise ValueError("side must be long or short")
    shares_i = int(shares)
    if shares_i <= 0:
        raise ValueError("shares must be > 0")
    entry_f = float(entry)
    stop_f = float(stop)
    if not (entry_f > 0 and stop_f > 0):
        raise ValueError("entry and stop must be > 0")
    if not all(x == x and abs(x) != float("inf") for x in (entry_f, stop_f)):
        raise ValueError("entry/stop must be finite")

    try:
        import model_registry as mr

        if model not in set(mr.list_engine_models()):
            print(f"warn: model {model!r} not in list_engine_models()", file=sys.stderr)
    except Exception:
        pass

    dr = float(dollar_risk) if dollar_risk is not None else abs(entry_f - stop_f) * shares_i
    ts = _utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tid = f"t_{stamp}_{sym}_{secrets.token_hex(2)}"

    append_event(
        {
            "event": "open",
            "id": tid,
            "ts": ts,
            "symbol": sym,
            "code": code,
            "side": side_l,
            "shares": shares_i,
            "entry": entry_f,
            "stop": stop_f,
            "trail_arm": float(trail_arm) if trail_arm is not None else None,
            "model": model,
            "model_reason": reason or "",
            "account": float(account) if account is not None else None,
            "risk_pct": float(risk_pct) if risk_pct is not None else None,
            "dollar_risk": float(dr),
            "action_at_entry": action,
            "confidence": float(confidence) if confidence is not None else None,
            "override": bool(override),
            "source": source,
            "notes": notes or "",
        }
    )
    return replay_positions()[tid]


def last_prices(symbols: list[str]) -> dict[str, dict[str, Any]]:
    import yfinance as yf

    out: dict[str, dict[str, Any]] = {}
    ts = _utc_now()
    for raw in symbols:
        sym, _ = _sym(raw)
        try:
            t = yf.Ticker(sym)
            price = None
            try:
                fi = getattr(t, "fast_info", None)
                if fi is not None:
                    price = getattr(fi, "last_price", None)
                    if price is None and hasattr(fi, "get"):
                        price = fi.get("last_price")
            except Exception:
                price = None
            if price is None or not (float(price) > 0):
                hist = yf.download(
                    sym, period="5d", interval="1d", progress=False, auto_adjust=True
                )
                if hist is not None and len(hist) > 0:
                    col = "Close" if "Close" in hist.columns else hist.columns[-1]
                    price = float(hist[col].iloc[-1])
                    out[sym] = {"price": price, "ts": ts, "source": "download"}
                else:
                    out[sym] = {"error": "no price"}
            else:
                out[sym] = {"price": float(price), "ts": ts, "source": "fast_info"}
        except Exception as e:  # noqa: BLE001
            out[sym] = {"error": str(e).split("\n")[0][:160]}
    return out


def mark_positions(ids: list[str] | None = None) -> dict[str, Any]:
    positions = replay_positions()
    open_ids = [
        pid
        for pid, p in positions.items()
        if p.get("status") == "open" and (ids is None or pid in ids)
    ]
    symbols = sorted(
        {positions[pid]["symbol"] for pid in open_ids if positions[pid].get("symbol")}
    )
    prices = last_prices(symbols) if symbols else {}
    marked: list[dict[str, Any]] = []
    for pid in open_ids:
        p = positions[pid]
        sym = p["symbol"]
        info = prices.get(sym) or {}
        if "error" in info or info.get("price") is None:
            p["mark"] = None
            p["mark_ts"] = None
            p["unrealized_pnl"] = None
            p["unrealized_r"] = None
            marked.append(p)
            continue
        mark = float(info["price"])
        direction = 1.0 if p["side"] == "long" else -1.0
        pnl = (mark - float(p["entry"])) * int(p["shares"]) * direction
        dr = float(p.get("dollar_risk") or 0) or 1e-9
        stop = float(p["stop"])
        trail = p.get("trail_arm")
        stop_hit = (p["side"] == "long" and mark <= stop) or (
            p["side"] == "short" and mark >= stop
        )
        trail_hit = False
        if trail is not None:
            tarm = float(trail)
            trail_hit = (p["side"] == "long" and mark >= tarm) or (
                p["side"] == "short" and mark <= tarm
            )
        p["mark"] = mark
        p["mark_ts"] = info.get("ts") or _utc_now()
        p["unrealized_pnl"] = round(pnl, 4)
        p["unrealized_r"] = round(pnl / dr, 4)
        p["stop_hit"] = bool(stop_hit)
        p["trail_hit"] = bool(trail_hit)
        marked.append(p)

    snap = {"asof": _utc_now(), "prices": prices, "positions": marked}
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MARKS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, indent=2, default=str))
    tmp.replace(MARKS_PATH)
    return {"positions": marked, "prices": prices, "asof": snap["asof"]}


def close_trade(tid: str, exit_price: float, reason: str = "manual") -> dict[str, Any]:
    positions = replay_positions()
    p = positions.get(tid)
    if not p:
        raise ValueError(f"unknown id {tid}")
    if p.get("status") != "open":
        raise ValueError(f"position {tid} is {p.get('status')}, not open")
    exit_f = float(exit_price)
    if not (exit_f > 0 and exit_f == exit_f and abs(exit_f) != float("inf")):
        raise ValueError("exit must be finite and > 0")

    direction = 1.0 if p["side"] == "long" else -1.0
    pnl = (exit_f - float(p["entry"])) * int(p["shares"]) * direction
    dr = float(p.get("dollar_risk") or 0) or 1e-9
    r_mult = pnl / dr
    opened = _parse_ts(p.get("opened_at"))
    now = datetime.now(timezone.utc)
    holding = None
    if opened is not None:
        holding = round(
            (now - opened.astimezone(timezone.utc)).total_seconds() / 86400.0, 4
        )

    ts = _utc_now()
    append_event(
        {
            "event": "close",
            "id": tid,
            "ts": ts,
            "exit": exit_f,
            "exit_reason": reason or "manual",
            "pnl": round(pnl, 4),
            "r_multiple": round(r_mult, 4),
            "holding_days": holding,
        }
    )

    try:
        import findings as findings_mod

        findings_mod.append_finding(
            {
                "family": "live_paper",
                "version": p.get("model"),
                "status": "pass" if pnl > 0 else "fail",
                "kind": "paper_trade",
                "summary": (
                    f"{p['symbol']} {p['side']} {r_mult:+.2f}R (${pnl:.2f})"
                    + (f" in {holding}d" if holding is not None else "")
                ),
                "source": "paper_ledger",
                "evidence": [f"runs/paper_ledger/ledger.jsonl#{tid}"],
                "metrics": {
                    "symbol": p["symbol"],
                    "side": p["side"],
                    "entry": p["entry"],
                    "exit": exit_f,
                    "shares": p["shares"],
                    "pnl": round(pnl, 4),
                    "r_multiple": round(r_mult, 4),
                    "holding_days": holding,
                },
                "failure_class": None,
                "next_action": None,
            }
        )
    except Exception as e:  # noqa: BLE001
        print(f"warn: findings append failed: {e}", file=sys.stderr)

    # Feed live adapt (desk size mult for next plans)
    try:
        import live_adapt as live_adapt_mod

        live_adapt_mod.record_outcome(
            pnl=float(pnl),
            symbol=str(p.get("symbol") or ""),
            model=str(p.get("model") or ""),
            r_multiple=float(r_mult),
            tags={"exit_reason": reason or "manual", "trade_id": tid},
        )
    except Exception as e:  # noqa: BLE001
        print(f"warn: live_adapt record failed: {e}", file=sys.stderr)

    return replay_positions()[tid]


def cancel_trade(tid: str, reason: str = "cancel") -> dict[str, Any]:
    positions = replay_positions()
    p = positions.get(tid)
    if not p:
        raise ValueError(f"unknown id {tid}")
    if p.get("status") != "open":
        raise ValueError(f"position {tid} is {p.get('status')}, not open")
    append_event(
        {"event": "cancel", "id": tid, "ts": _utc_now(), "reason": reason or "cancel"}
    )
    return replay_positions()[tid]


def update_trade(
    tid: str,
    *,
    shares: int | None = None,
    entry: float | None = None,
    stop: float | None = None,
    trail_arm: float | None = None,
    account: float | None = None,
    risk_pct: float | None = None,
    dollar_risk: float | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    events = load_events()
    found = False
    for ev in events:
        if ev.get("id") == tid and ev.get("event") == "open":
            found = True
            if shares is not None:
                ev["shares"] = int(shares)
            if entry is not None:
                ev["entry"] = float(entry)
            if stop is not None:
                ev["stop"] = float(stop)
            if trail_arm is not None:
                ev["trail_arm"] = float(trail_arm)
            if account is not None:
                ev["account"] = float(account)
            if risk_pct is not None:
                ev["risk_pct"] = float(risk_pct)
            if dollar_risk is not None:
                ev["dollar_risk"] = float(dollar_risk)
            elif (shares is not None or entry is not None or stop is not None):
                e = ev.get("entry", 0.0)
                s = ev.get("stop", 0.0)
                sh = ev.get("shares", 0)
                ev["dollar_risk"] = abs(e - s) * sh
            if notes is not None:
                ev["notes"] = notes
            break
    
    if not found:
        raise ValueError(f"open trade with id {tid} not found")
        
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev, separators=(",", ":")) + "\n")
            
    return replay_positions()[tid]


def delete_trade(tid: str) -> None:
    events = load_events()
    new_events = [ev for ev in events if ev.get("id") != tid]
    if len(new_events) == len(events):
        raise ValueError(f"trade with id {tid} not found")
    
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("w") as f:
        for ev in new_events:
            f.write(json.dumps(ev, separators=(",", ":")) + "\n")



def compute_stats(
    symbol: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Aggregate closed-trade stats. Import-safe (no yfinance)."""
    positions = replay_positions()
    closed = [p for p in positions.values() if p.get("status") == "closed"]
    if symbol:
        sym, _ = _sym(symbol)
        closed = [p for p in closed if p.get("symbol") == sym]
    if model:
        closed = [p for p in closed if p.get("model") == model]

    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for p in closed:
        key = (str(p.get("model") or ""), str(p.get("symbol") or ""))
        b = buckets.setdefault(
            key,
            {
                "model": key[0],
                "symbol": key[1],
                "n": 0,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "sum_R": 0.0,
                "last_close_ts": None,
            },
        )
        b["n"] += 1
        pnl = float(p.get("pnl") or 0)
        r = float(p.get("r_multiple") or 0)
        b["total_pnl"] += pnl
        b["sum_R"] += r
        if pnl > 0:
            b["wins"] += 1
        else:
            b["losses"] += 1
        cts = p.get("closed_at")
        if cts and (b["last_close_ts"] is None or str(cts) > str(b["last_close_ts"])):
            b["last_close_ts"] = cts

    rows = []
    for b in buckets.values():
        n = b["n"]
        rows.append(
            {
                **b,
                "live_wr": (b["wins"] / n) if n else 0.0,
                "avg_R": (b["sum_R"] / n) if n else 0.0,
                "total_pnl": round(b["total_pnl"], 4),
                "sum_R": round(b["sum_R"], 4),
            }
        )
    rows.sort(key=lambda r: (-r["n"], r["model"], r["symbol"]))

    n_all = len(closed)
    wins_all = sum(1 for p in closed if float(p.get("pnl") or 0) > 0)
    total_pnl = sum(float(p.get("pnl") or 0) for p in closed)
    sum_r = sum(float(p.get("r_multiple") or 0) for p in closed)
    overall = {
        "n": n_all,
        "wins": wins_all,
        "losses": n_all - wins_all,
        "live_wr": (wins_all / n_all) if n_all else 0.0,
        "total_pnl": round(total_pnl, 4),
        "avg_R": (sum_r / n_all) if n_all else 0.0,
        "sum_R": round(sum_r, 4),
    }
    return {"rows": rows, "overall": overall, "asof": _utc_now()}


def cmd_open(ns: argparse.Namespace) -> int:
    try:
        pos = open_trade(
            ns.symbol,
            ns.side,
            ns.shares,
            ns.entry,
            ns.stop,
            ns.model,
            trail_arm=ns.trail_arm,
            account=ns.account,
            risk_pct=ns.risk_pct,
            dollar_risk=ns.dollar_risk,
            action=ns.action,
            confidence=ns.confidence,
            override=bool(ns.override),
            reason=ns.reason,
            source=ns.source or "cli",
        )
    except Exception as e:  # noqa: BLE001
        return _err(str(e))
    if ns.json:
        return _print_json({"ok": True, "position": pos})
    print(pos["id"], pos["symbol"], pos["side"], pos["shares"])
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    positions = list(replay_positions().values())
    status = (ns.status or "all").lower()
    if status != "all":
        positions = [p for p in positions if p.get("status") == status]
    positions.sort(key=lambda p: str(p.get("opened_at") or ""), reverse=True)
    if ns.json:
        return _print_json({"ok": True, "positions": positions, "asof": _utc_now()})
    for p in positions:
        print(p["id"], p["status"], p["symbol"], p["model"], p.get("pnl"))
    return 0


def cmd_mark(ns: argparse.Namespace) -> int:
    ids = None
    if ns.ids:
        ids = [x.strip() for x in ns.ids.split(",") if x.strip()]
    try:
        out = mark_positions(ids)
    except Exception as e:  # noqa: BLE001
        return _err(str(e))
    if ns.json:
        return _print_json({"ok": True, **out})
    for p in out["positions"]:
        print(p["id"], p.get("mark"), p.get("unrealized_pnl"), p.get("stop_hit"))
    return 0


def cmd_close(ns: argparse.Namespace) -> int:
    try:
        pos = close_trade(ns.id, ns.exit, reason=ns.reason or "manual")
    except Exception as e:  # noqa: BLE001
        return _err(str(e))
    if ns.json:
        return _print_json({"ok": True, "position": pos})
    print(pos["id"], pos["pnl"], pos["r_multiple"])
    return 0


def cmd_cancel(ns: argparse.Namespace) -> int:
    try:
        pos = cancel_trade(ns.id, reason=ns.reason or "cancel")
    except Exception as e:  # noqa: BLE001
        return _err(str(e))
    if ns.json:
        return _print_json({"ok": True, "position": pos})
    print(pos["id"], pos["status"])
    return 0


def cmd_update(ns: argparse.Namespace) -> int:
    try:
        pos = update_trade(
            ns.id,
            shares=ns.shares,
            entry=ns.entry,
            stop=ns.stop,
            trail_arm=ns.trail_arm,
            account=ns.account,
            risk_pct=ns.risk_pct,
            dollar_risk=ns.dollar_risk,
            notes=ns.notes,
        )
    except Exception as e:  # noqa: BLE001
        return _err(str(e))
    if ns.json:
        return _print_json({"ok": True, "position": pos})
    print(pos["id"], pos["symbol"], pos["shares"])
    return 0


def cmd_delete(ns: argparse.Namespace) -> int:
    try:
        delete_trade(ns.id)
    except Exception as e:  # noqa: BLE001
        return _err(str(e))
    if ns.json:
        return _print_json({"ok": True})
    print(f"deleted {ns.id}")
    return 0



def cmd_stats(ns: argparse.Namespace) -> int:
    out = compute_stats(symbol=ns.symbol, model=ns.model)
    if ns.json:
        return _print_json(out)
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    # runPythonScript appends --json at the end; accept anywhere.
    want_json = "--json" in raw
    raw = [a for a in raw if a != "--json"]

    ap = argparse.ArgumentParser(description="Paper trade ledger")
    ap.add_argument("--json", action="store_true", help="Print one JSON object to stdout")
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("open")
    o.add_argument("--symbol", required=True)
    o.add_argument("--side", required=True, choices=["long", "short"])
    o.add_argument("--shares", type=int, required=True)
    o.add_argument("--entry", type=float, required=True)
    o.add_argument("--stop", type=float, required=True)
    o.add_argument("--model", required=True)
    o.add_argument("--trail-arm", type=float, default=None)
    o.add_argument("--account", type=float, default=None)
    o.add_argument("--risk-pct", type=float, default=None)
    o.add_argument("--dollar-risk", type=float, default=None)
    o.add_argument("--action", default=None)
    o.add_argument("--confidence", type=float, default=None)
    o.add_argument("--override", action="store_true")
    o.add_argument("--reason", default=None)
    o.add_argument("--source", default="cli")
    o.set_defaults(func=cmd_open)

    l = sub.add_parser("list")
    l.add_argument(
        "--status", choices=["open", "closed", "all", "cancelled"], default="all"
    )
    l.set_defaults(func=cmd_list)

    m = sub.add_parser("mark")
    m.add_argument("--ids", default=None, help="Comma-separated position ids")
    m.set_defaults(func=cmd_mark)

    c = sub.add_parser("close")
    c.add_argument("--id", required=True)
    c.add_argument("--exit", type=float, required=True)
    c.add_argument("--reason", default="manual")
    c.set_defaults(func=cmd_close)

    k = sub.add_parser("cancel")
    k.add_argument("--id", required=True)
    k.add_argument("--reason", default="cancel")
    k.set_defaults(func=cmd_cancel)

    u = sub.add_parser("update")
    u.add_argument("--id", required=True)
    u.add_argument("--shares", type=int, default=None)
    u.add_argument("--entry", type=float, default=None)
    u.add_argument("--stop", type=float, default=None)
    u.add_argument("--trail-arm", type=float, default=None)
    u.add_argument("--account", type=float, default=None)
    u.add_argument("--risk-pct", type=float, default=None)
    u.add_argument("--dollar-risk", type=float, default=None)
    u.add_argument("--notes", default=None)
    u.set_defaults(func=cmd_update)

    d = sub.add_parser("delete")
    d.add_argument("--id", required=True)
    d.set_defaults(func=cmd_delete)

    s = sub.add_parser("stats")
    s.add_argument("--symbol", default=None)
    s.add_argument("--model", default=None)
    s.set_defaults(func=cmd_stats)


    ns = ap.parse_args(raw)
    ns.json = bool(want_json or ns.json)
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
