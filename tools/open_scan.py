#!/usr/bin/env python3
"""Open-ready market scanner — find plays for the live desk at the open.

Two-phase scan:
  1) Fast VPA+VWAP screen over a broad liquid universe (+ hot sector leaders)
  2) Deep WINNER engine analyze on top candidates (live tape settings)

Writes:
  runs/live_adapt/LAST_OPEN_SCAN.json   — full ranked book
  runs/live_adapt/WATCHLIST.txt         — comma symbols for Watch UI / CLI

Usage:
  .venv/bin/python tools/open_scan.py
  .venv/bin/python tools/open_scan.py --top 12 --account 10000 --json
  .venv/bin/python tools/open_scan.py --fast          # VPA-only (no deep analyze)
  .venv/bin/python tools/open_scan.py --universe full # all DEFAULT_WATCH names
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sanitize_nan(obj: Any) -> Any:
    """Replace NaN/±Infinity with None so downstream JSON.parse is safe."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

OUT_DIR = ROOT / "runs" / "live_adapt"
SCAN_PATH = OUT_DIR / "LAST_OPEN_SCAN.json"
WATCH_PATH = OUT_DIR / "WATCHLIST.txt"

# Liquid core always scanned at open (high participation names)
OPEN_CORE = [
    "SPY", "QQQ", "IWM",
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AVGO", "AMD",
    "MU", "ARM", "TSM", "SMCI", "PLTR", "HOOD", "COIN", "MSTR",
    "IONQ", "APLD", "ANET", "CRWD", "PANW", "ORCL", "AMAT", "KLAC",
    "JPM", "GS", "XOM", "VST", "RKLB", "ASTS",
]


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _uniq(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        u = str(s).strip().upper().replace(".US", "")
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _yahoo_day_movers(n: int = 30) -> list[str]:
    """Pull US day-gainers from Yahoo predefined screener (catches names outside liquid core).

    Soft-fails to [] on network / rate-limit so open scan still runs.
    """
    import json as _json
    import urllib.error
    import urllib.request

    out: list[str] = []
    for scr_id in ("day_gainers", "most_actives"):
        url = (
            "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            f"?formatted=false&lang=en-US&region=US&scrIds={scr_id}&count={max(5, min(n, 50))}"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; TradingAlgoWork/1.0)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                payload = _json.loads(resp.read().decode("utf-8", errors="replace"))
            finance = (payload or {}).get("finance") or {}
            results = finance.get("result") or []
            if not results:
                continue
            quotes = results[0].get("quotes") or []
            for q in quotes:
                sym = str(q.get("symbol") or "").strip().upper()
                # Skip non-common: warrants, preferreds, OTC junk, crypto pairs
                if not sym or any(x in sym for x in ("-", "=", "^", "/")):
                    continue
                if sym.endswith(("W", "U", "R")) and len(sym) > 5:
                    continue
                # Prefer ordinary equities / liquid ETFs
                quote_type = str(q.get("quoteType") or q.get("typeDisp") or "").upper()
                if quote_type and quote_type not in ("EQUITY", "ETF", "STOCK", ""):
                    continue
                out.append(sym)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError):
            continue
    return _uniq(out)[: max(1, n)]


def build_universe(mode: str = "open", top_sectors: int = 8) -> dict[str, Any]:
    """Assemble scan universe for the open.

    Includes liquid core + rotating hot sectors + Yahoo day movers/actives so
    we do not miss names outside the static bag (e.g. small-cap runners).
    """
    from trade_desk import DEFAULT_WATCH, rank_sector_flows, SECTORS

    sector_rows = []
    hot_names: list[str] = []
    try:
        flows = rank_sector_flows()
        sector_rows = [r for r in flows if "error" not in r]
        top = sector_rows[: max(1, top_sectors)]
        for sec in top:
            hot_names.extend(sec.get("members") or [])
            # also pull SECTORS members if rotate uses sector key
            sk = sec.get("sector")
            if sk and sk in SECTORS:
                # more depth per hot sector (was 8)
                hot_names.extend(SECTORS[sk][:12])
    except Exception as e:  # noqa: BLE001
        sector_rows = [{"error": str(e)}]

    day_movers = _yahoo_day_movers(32 if mode == "full" else 24)

    if mode == "full":
        names = list(DEFAULT_WATCH) + hot_names + OPEN_CORE + day_movers
    else:
        # open mode: core + hot sector leaders + day movers (latency-bounded)
        names = OPEN_CORE + hot_names + day_movers
        # sprinkle more liquid beta names from DEFAULT_WATCH
        names.extend([n for n in DEFAULT_WATCH if n not in names][:36])

    symbols = _uniq(names)
    # cap for open latency (deep phase is the bottleneck)
    if mode == "open" and len(symbols) > 100:
        symbols = symbols[:100]
    if mode == "full" and len(symbols) > 160:
        symbols = symbols[:160]

    return {
        "symbols": symbols,
        "sector_flows": sector_rows[:14],
        "hot_sectors": [r.get("sector") for r in sector_rows[:top_sectors] if "error" not in r],
        "day_movers": day_movers,
        "count": len(symbols),
        "mode": mode,
    }


def _vpa_screen(symbols: list[str], workers: int = 8) -> list[dict[str, Any]]:
    """Fast daily VPA pass — filter CALL / constructive bias first."""
    import importlib.util

    v31 = ROOT / "models" / "poc_va_macdha" / "v31_vpa_vwap"
    spec = importlib.util.spec_from_file_location("vpa_mod", v31 / "vpa.py")
    vpa_mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(vpa_mod)
    spec2 = importlib.util.spec_from_file_location("vwap_mod", v31 / "vwap_peg.py")
    vwap_mod = importlib.util.module_from_spec(spec2)
    assert spec2.loader
    spec2.loader.exec_module(vwap_mod)

    from vpa_scan import scan_symbol  # type: ignore
    import json as _json

    dna = {}
    dna_path = v31 / "vwap_dna.json"
    if dna_path.exists():
        dna = _json.loads(dna_path.read_text())

    rows: list[dict[str, Any]] = []

    def one(sym: str) -> dict[str, Any]:
        try:
            return scan_symbol(sym, vpa_mod, vwap_mod, dna, period="6mo")
        except Exception as e:  # noqa: BLE001
            return {"symbol": sym, "ok": False, "error": str(e)[:120]}

    with ThreadPoolExecutor(max_workers=max(2, workers)) as ex:
        futs = {ex.submit(one, s): s for s in symbols}
        for fut in as_completed(futs):
            rows.append(fut.result())

    # Prefer CALL / CALL_SOFT / constructive; demote PUT/FLAT for long-only desk DNA
    def vpa_score(r: dict[str, Any]) -> float:
        if not r.get("ok"):
            return -9.0
        bias = str(r.get("bias") or "")
        base = {
            "CALL": 1.0,
            "CALL_SOFT": 0.72,
            "CALL_WEAK": 0.35,
            "FLAT": 0.15,
            "CONFLICT": 0.05,
            "PUT_SOFT": -0.2,
            "PUT_WEAK": -0.3,
            "PUT": -0.5,
        }.get(bias, 0.0)
        tags = str(r.get("vpa_tag") or "")
        if "stopping_reclaim" in tags or "no_supply" in tags:
            base += 0.25
        if "confirm_up" in tags:
            base += 0.15
        if "no_demand" in tags or "buying_climax" in tags:
            base -= 0.35
        if "dump" in tags:
            base -= 0.40
        vr = float(r.get("vol_ratio") or 1.0)
        if vr >= 1.5:
            base += 0.12
        elif vr < 0.7:
            base -= 0.10
        r["vpa_screen_score"] = round(base, 4)
        return base

    for r in rows:
        vpa_score(r)
    rows.sort(key=lambda x: x.get("vpa_screen_score", -9), reverse=True)
    return rows


def _deep_analyze(
    symbols: list[str],
    account: float,
    risk_pct: float,
    model: str,
    workers: int = 4,
) -> list[dict[str, Any]]:
    """WINNER engine deep pass with live-ish tape settings."""
    from trade_desk import analyze, _plain_plan

    def one(sym: str) -> dict[str, Any]:
        try:
            out = analyze(
                sym,
                account=account,
                risk_pct=risk_pct,
                model=model,
                period="10d",
                interval="5m",
                live=True,
                ranks=False,
            )
            st, sz = out["state"], out["sizing"]
            plan = _plain_plan(st)
            kind = st.get("setup_kind") or "wait"
            kind_mult = {
                "classic_buy": 1.0,
                "breakout_buy": 0.95,
                "breakout_watch": 0.62,
                "pullback_watch": 0.55,
                "wait": 0.28,
                "avoid": 0.12,
                "structural_break": 0.05,
            }.get(kind, 0.30)
            score = float(st.get("hit_probability") or 0.5) * kind_mult * max(float(st.get("sleeve_fraction") or 0.25), 0.2)
            if st.get("vol_surge"):
                score *= 1.18
            elif st.get("vol_dry"):
                score *= 0.72
            if st.get("setup_ok"):
                score *= 1.15
            if st.get("breakout_ready") or st.get("pressing_high"):
                score *= 1.08
            if st.get("lost_200"):
                score *= 0.45
            # live adapt mult already inside sizing
            adapt = float(sz.get("live_adapt_mult") or 1.0)
            score *= 0.85 + 0.15 * adapt
            action = plan.get("action") or "WAIT"
            playable = action in ("BUY NOW", "BUY BREAKOUT", "BREAKOUT WATCH", "PULLBACK ZONE")
            # Near-play: not a hard avoid, has a level map operator can arm alerts on.
            has_level = any(
                st.get(k) is not None
                for k in ("breakout_level", "entry", "ema22", "val", "vah", "stop")
            )
            near_play = (not playable) and kind in (
                "wait", "pullback_watch", "breakout_watch"
            ) and has_level and not bool(st.get("lost_200"))
            if action.startswith("WAIT") and has_level and not bool(st.get("lost_200")):
                near_play = True
            # Soft-upgrade dry-tape waits into near_play so the board isn't 90% AVOID.
            if action.startswith("AVOID") and has_level and not bool(st.get("lost_200")) and float(st.get("confidence") or 0) >= 0.50:
                # Keep action honest, but mark as candidate for alert board.
                near_play = True
            return {
                "symbol": st.get("symbol") or sym,
                "ok": True,
                "model": out.get("model"),
                "action": action,
                "setup_kind": kind,
                "setup_ok": bool(st.get("setup_ok")),
                "playable": playable,
                "near_play": near_play,
                "price": st.get("price"),
                "entry": st.get("entry"),
                "breakout_level": st.get("breakout_level"),
                "stop": st.get("stop"),
                "trail_arm": st.get("trail_arm"),
                "risk_per_share": st.get("risk_per_share"),
                "ema22": st.get("ema22"),
                "ema200": st.get("ema200"),
                "val": st.get("val"),
                "vah": st.get("vah"),
                "confidence": st.get("confidence"),
                "hit_probability": st.get("hit_probability"),
                "rvol": st.get("rvol"),
                "vol_surge": st.get("vol_surge"),
                "vol_dry": st.get("vol_dry"),
                "lost_200": bool(st.get("lost_200")),
                "shares": sz.get("shares"),
                "dollar_risk": sz.get("dollar_risk"),
                "live_adapt_mult": adapt,
                "sleeve": st.get("sleeve_fraction"),
                "missing": (st.get("missing") or [])[:4],
                "do_next": plan.get("do_next"),
                "why": plan.get("why"),
                "score": round(score, 4),
                "asof": st.get("asof"),
            }
        except Exception as e:  # noqa: BLE001
            return {"symbol": sym, "ok": False, "error": str(e)[:160], "score": -1, "playable": False}

    rows: list[dict[str, Any]] = []
    # sequential is safer for yfinance rate limits at open; light pool
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as ex:
        futs = [ex.submit(one, s) for s in symbols]
        for fut in as_completed(futs):
            rows.append(fut.result())
    rows.sort(key=lambda r: (not r.get("playable", False), -float(r.get("score") or -1)))
    return rows


def run_open_scan(
    account: float = 10_000.0,
    risk_pct: float = 0.01,
    model: str = "auto",
    universe: str = "open",
    top: int = 12,
    deep_n: int = 24,
    fast_only: bool = False,
    workers: int = 6,
    quiet: bool = False,
) -> dict[str, Any]:
    t0 = time.time()
    uni = build_universe(mode=universe)
    symbols = uni["symbols"]
    if not quiet:
        hot_sectors = ", ".join(uni.get("hot_sectors") or []) or "—"
        print(f"Open scan universe: {len(symbols)} names  hot sectors: {hot_sectors}", flush=True)

    if not quiet:
        print("Phase 1 — VPA screen…", flush=True)
    vpa_rows = _vpa_screen(symbols, workers=workers)
    # Keep CALL-leaning + flat high vol for deep; drop hard PUTs
    candidates = [
        r for r in vpa_rows
        if r.get("ok") and float(r.get("vpa_screen_score") or -9) >= 0.10
    ]
    if len(candidates) < 8:
        candidates = [r for r in vpa_rows if r.get("ok")][: deep_n]
    else:
        candidates = candidates[:deep_n]
    cand_syms = [r["symbol"] for r in candidates]
    if not quiet:
        print(f"  VPA advanced {len(cand_syms)} → deep: {', '.join(cand_syms[:15])}{'…' if len(cand_syms)>15 else ''}", flush=True)

    deep_rows: list[dict[str, Any]] = []
    if not fast_only:
        if not quiet:
            print(f"Phase 2 — deep analyze (model={model}, live 5m)…", flush=True)
        deep_rows = _deep_analyze(cand_syms, account, risk_pct, model, workers=min(4, workers))
        # merge VPA tags onto deep rows
        vpa_by = {r["symbol"]: r for r in vpa_rows if r.get("ok")}
        for d in deep_rows:
            v = vpa_by.get(d.get("symbol") or "")
            if v:
                d["vpa_bias"] = v.get("bias")
                d["vpa_tag"] = v.get("vpa_tag")
                d["vpa_screen_score"] = v.get("vpa_screen_score")
                # blend scores
                d["score"] = round(float(d.get("score") or 0) + 0.15 * float(v.get("vpa_screen_score") or 0), 4)
        def _rank_key(r: dict[str, Any]) -> tuple:
            a = str(r.get("action") or "")
            if a in ("BUY NOW", "BUY BREAKOUT"):
                tier = 0
            elif a in ("BREAKOUT WATCH", "PULLBACK ZONE"):
                tier = 1
            elif r.get("near_play") or a.startswith("WAIT"):
                tier = 2
            elif a.startswith("AVOID") and not r.get("lost_200") and r.get("near_play"):
                tier = 3
            elif a.startswith("AVOID (structure"):
                tier = 5
            else:
                tier = 4
            return (tier, -float(r.get("score") or -1))

        deep_rows.sort(key=_rank_key)

    plays = [r for r in deep_rows if r.get("ok") and r.get("playable")] if deep_rows else []
    near = [r for r in deep_rows if r.get("ok") and r.get("near_play") and not r.get("playable")] if deep_rows else []
    # Prefer buys → watches → near levels. Do NOT pad top with pure AVOID spam.
    ranked_deep = list(deep_rows) if deep_rows else []
    avoid_only = [
        r for r in ranked_deep
        if r.get("ok") and str(r.get("action", "")).startswith("AVOID") and not r.get("near_play")
    ]
    preferred = plays + near + [
        r for r in ranked_deep
        if r not in plays and r not in near and r not in avoid_only
    ]
    # Only append a few avoids so the book still shows "what not to touch"
    top_plays = (preferred + avoid_only[:3])[: max(1, top)]
    if not top_plays:
        top_plays = candidates[: max(1, top)]

    # Watchlist: playable + near + CALL VPA + day movers (skip broken structure)
    raw_movers = uni.get("day_movers") or []
    day_movers: list[str] = []
    for m in raw_movers:
        if isinstance(m, str) and m.strip():
            day_movers.append(m.strip().upper())
        elif isinstance(m, dict) and m.get("symbol"):
            day_movers.append(str(m["symbol"]).strip().upper())
    watch_syms = _uniq(
        [r.get("symbol") for r in plays if r.get("symbol")]
        + [r.get("symbol") for r in near if r.get("symbol")]
        + [
            r.get("symbol")
            for r in ranked_deep
            if r.get("ok") and not str(r.get("action", "")).startswith("AVOID (structure")
        ]
        + [r["symbol"] for r in candidates if str(r.get("bias", "")).startswith("CALL")]
        + day_movers
    )[:18]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _sanitize_nan(
        {
            "ok": True,
            "asof": _utc(),
            "elapsed_sec": round(time.time() - t0, 1),
            "account": account,
            "risk_pct": risk_pct,
            "model": model,
            "universe": universe,
            "hot_sectors": uni.get("hot_sectors"),
            "day_movers": uni.get("day_movers") or [],
            "scanned": len(symbols),
            "vpa_candidates": len(candidates),
            "deep_n": len(deep_rows),
            "top_plays": top_plays,
            "buys": [r for r in plays if str(r.get("action")) in ("BUY NOW", "BUY BREAKOUT")],
            "watches": [r for r in plays if str(r.get("action")) in ("BREAKOUT WATCH", "PULLBACK ZONE")],
            "near_plays": near,
            "all_deep": deep_rows,
            "vpa_top": vpa_rows[:20],
            "watchlist": watch_syms,
            "operator": {
                "use": "Load watchlist into /watch or: trade_desk.py watch " + ",".join(watch_syms[:12]),
                "model": "auto → specialist when mapped else bag WINNER",
                "how_to_trade": (
                    "BUY NOW / BUY BREAKOUT = size with stop. "
                    "PULLBACK ZONE = alert on VAL / 22 EMA, buy dip not chase. "
                    "BREAKOUT WATCH = alert above level, only with volume surge. "
                    "NEAR = arm alerts from levels; not an entry yet. "
                    "AVOID = ignore unless reclaim 200 EMA on volume."
                ),
                "breakout_watch": (
                    "BREAKOUT WATCH is not a buy. Alert above breakout_level; "
                    "enter only when volume expands through the level (rvol ≥ ~1.3x)."
                ),
                "note": "Long-biased desk DNA; day_movers catch names outside static bag; PUT bias in vpa_top = stand-aside",
            },
        }
    )
    tmp = SCAN_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(SCAN_PATH)
    WATCH_PATH.write_text(",".join(watch_syms), encoding="utf-8")
    return payload


def _fmt_lvl(v: Any) -> str:
    try:
        return f"${float(v):.2f}"
    except (TypeError, ValueError):
        return "—"


def _print_row(r: dict[str, Any], i: int | None = None) -> None:
    prefix = f"  {i:<3} " if i is not None else "    "
    if r.get("error"):
        print(f"{prefix}{r.get('symbol','?'):<6} ERROR {r.get('error')[:40]}")
        return
    sh = int(r.get("shares") or 0)
    rps = r.get("risk_per_share")
    risk = r.get("dollar_risk")
    math_bits = []
    if sh > 0:
        math_bits.append(f"{sh} sh")
    if rps:
        math_bits.append(f"R/sh {_fmt_lvl(rps).lstrip('$')}")
    if risk:
        try:
            math_bits.append(f"${float(risk):.0f} risk")
        except (TypeError, ValueError):
            pass
    conf = r.get("confidence")
    conf_s = f" conf {float(conf):.0%}" if conf is not None else ""
    rvol = r.get("rvol")
    rvol_s = f" rvol {float(rvol):.1f}x" if rvol is not None else ""
    print(
        f"{prefix}{str(r.get('symbol')):<6} {str(r.get('action') or '—'):<18} "
        f"px {_fmt_lvl(r.get('price'))}  stop {_fmt_lvl(r.get('stop'))}"
        f"{conf_s}{rvol_s}"
        + (f"  · {' · '.join(math_bits)}" if math_bits else "")
    )
    levels = []
    if r.get("breakout_level") is not None:
        levels.append(f"break {_fmt_lvl(r.get('breakout_level'))}")
    if r.get("ema22") is not None:
        levels.append(f"22 {_fmt_lvl(r.get('ema22'))}")
    if r.get("val") is not None:
        levels.append(f"VAL {_fmt_lvl(r.get('val'))}")
    if r.get("vah") is not None:
        levels.append(f"VAH {_fmt_lvl(r.get('vah'))}")
    if levels:
        print(f"       levels: {' · '.join(levels)}")
    tip = r.get("do_next") or r.get("why")
    if tip:
        print(f"       → {str(tip)[:100]}")


def _print_human(p: dict[str, Any]) -> None:
    print()
    print("=" * 72)
    print(f"  OPEN SCAN  asof {p.get('asof')}  elapsed {p.get('elapsed_sec')}s")
    print(f"  scanned {p.get('scanned')}  deep {p.get('deep_n')}  model={p.get('model')}")
    print(f"  hot sectors: {', '.join(p.get('hot_sectors') or []) or '—'}")
    print("=" * 72)

    buys = p.get("buys") or []
    watches = p.get("watches") or []
    near = p.get("near_plays") or []
    all_deep = p.get("all_deep") or p.get("top_plays") or []
    avoids = [
        r for r in all_deep
        if r.get("ok") and str(r.get("action", "")).startswith("AVOID") and not r.get("near_play")
    ]

    # Fallback if older payload without buckets
    if not buys and not watches and not near:
        for r in (p.get("top_plays") or []):
            a = str(r.get("action") or "")
            if a in ("BUY NOW", "BUY BREAKOUT"):
                buys.append(r)
            elif a in ("BREAKOUT WATCH", "PULLBACK ZONE"):
                watches.append(r)
            elif r.get("near_play") or a.startswith("WAIT"):
                near.append(r)

    print("\n  ══ BUY NOW / BUY BREAKOUT  (size with stop) ══")
    if not buys:
        print("    None live right now — use WATCH + NEAR alerts at the open.")
    else:
        for i, r in enumerate(buys[:12], 1):
            _print_row(r, i)

    print("\n  ══ WATCH  (arm alerts — not a chase) ══")
    if not watches:
        print("    None classified as breakout/pullback yet.")
    else:
        for i, r in enumerate(watches[:15], 1):
            _print_row(r, i)

    print("\n  ══ NEAR  (levels ready — wait for trigger) ══")
    if not near:
        print("    None — tape is soft / structure weak.")
    else:
        for i, r in enumerate(near[:12], 1):
            _print_row(r, i)

    # Day movers — momentum names outside the deep avoid wall
    movers = p.get("day_movers") or []
    if movers:
        print("\n  ══ DAY MOVERS  (check at open for volume) ══")
        for m in movers[:10]:
            if isinstance(m, str):
                print(f"    {m:<6}  (yahoo gainer — re-check tape at open)")
                continue
            if not isinstance(m, dict):
                continue
            sym = m.get("symbol") or m.get("ticker") or "?"
            chg = m.get("change_pct") or m.get("ret") or m.get("pct")
            try:
                chg_s = f"{float(chg):+.1f}%" if chg is not None else ""
            except (TypeError, ValueError):
                chg_s = ""
            print(f"    {str(sym):<6} {chg_s}  {str(m.get('name') or m.get('note') or '')[:40]}")

    # VPA CALL lean
    vpa_calls = [
        r for r in (p.get("vpa_top") or [])
        if str(r.get("bias", "")).startswith("CALL") or "call" in str(r.get("action", "")).lower()
    ]
    if vpa_calls:
        print("\n  ══ VPA CALL lean  (participation bias) ══")
        for r in vpa_calls[:8]:
            print(
                f"    {str(r.get('symbol')):<6} {str(r.get('bias') or ''):<14} "
                f"{str(r.get('vpa_tag') or r.get('action') or '')[:48]}"
            )

    if avoids:
        print(f"\n  ══ AVOID  ({len(avoids)} names — do not pad the board) ══")
        for r in avoids[:5]:
            why = (r.get("do_next") or r.get("why") or "stand aside")[:70]
            print(f"    {str(r.get('symbol')):<6} {str(r.get('action') or 'AVOID')[:22]:<22} {why}")
        if len(avoids) > 5:
            print(f"    … +{len(avoids) - 5} more skipped (structural break / dry volume)")

    print("\n  HOW TO USE THIS")
    print("    1) BUY NOW / BUY BREAKOUT → enter with listed stop & share count")
    print("    2) PULLBACK ZONE → alert VAL / 22 EMA; buy the dip, not the extension")
    print("    3) BREAKOUT WATCH → alert above break level only with rvol ≥ ~1.3x")
    print("    4) NEAR → arm levels; re-scan after open volume prints")
    print("    5) AVOID → cash; only revisit on 200-EMA reclaim + volume")
    op = (p.get("operator") or {}).get("how_to_trade")
    if op:
        print(f"    {op}")

    print()
    wl = p.get("watchlist") or []
    # Prefer actionable watchlist order: buys + watches + near first
    preferred = _uniq(
        [r.get("symbol") for r in buys]
        + [r.get("symbol") for r in watches]
        + [r.get("symbol") for r in near]
        + wl
    )[:18]
    print(f"  WATCHLIST ({len(preferred)}): {', '.join(str(s) for s in preferred if s)}")
    print(f"  Saved → {SCAN_PATH.relative_to(ROOT)}")
    if preferred:
        print(f"  Watch → .venv/bin/python tools/trade_desk.py watch {','.join(str(s) for s in preferred[:12])} --every 30")
    print()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Open market scanner for live desk")
    ap.add_argument("--account", type=float, default=10_000.0)
    ap.add_argument("--risk-pct", type=float, default=0.01)
    ap.add_argument("--model", type=str, default="auto")
    ap.add_argument("--universe", choices=["open", "full"], default="open")
    ap.add_argument("--top", type=int, default=12, help="How many plays to print / keep")
    ap.add_argument("--deep", type=int, default=24, help="How many VPA candidates get deep analyze")
    ap.add_argument("--fast", action="store_true", help="VPA screen only (skip deep engine)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)

    payload = run_open_scan(
        account=ns.account,
        risk_pct=ns.risk_pct,
        model=ns.model,
        universe=ns.universe,
        top=ns.top,
        deep_n=ns.deep,
        fast_only=ns.fast,
        workers=ns.workers,
        quiet=ns.json,
    )
    if ns.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_human(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
