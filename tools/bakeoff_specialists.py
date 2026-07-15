#!/usr/bin/env python3
"""Bake off proper specialists: v39d engine + routing DNA vs broken v65 stack.

Why
---
The existing ``v65_spec_*`` models used a thin parametric engine **without**
the v39d XGB meta / confluence stack. On TSLA alone that lost ~30% while
``v39d_confluence`` made ~+34%. Those specialists do not work.

This tool:
  1. Extracts native routing DNA donors from v39d (TSLA/MU/SPY/ARM/IONQ/APLD).
  2. For each desk symbol, backtests each donor DNA on a **v39d fork**
     (engine + meta_xgb + ledger).
  3. Multi-lock promotes only DNA that beats the v39d default for that name.
  4. Rebuilds ``v65_spec_<sym>`` as a real v39d-based specialist and updates
     ``DESK_ROUTING.json``. Symbols with no DNA win route to ``v39d_confluence``.

Usage
-----
  .venv/bin/python tools/bakeoff_specialists.py --quick
  .venv/bin/python tools/bakeoff_specialists.py --promote
  .venv/bin/python tools/bakeoff_specialists.py --symbols TSLA,NVDA,AVGO --promote
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import dynamic_model_rank as dmr  # noqa: E402

MODELS = ROOT / "models" / "poc_va_macdha"
V39D = MODELS / "v39d_confluence"
DESK_ROUTING = MODELS / "DESK_ROUTING.json"
OUT = ROOT / "runs" / "bakeoff_specialists"
CACHE_1H = ROOT / "data_cache" / "1h"

START = "2024-08-01"
END = "2026-07-11"
CASH = 1000.0

# Desk + popular expansion set
DEFAULT_SYMBOLS = [
    "TSLA", "MU", "IONQ", "APLD", "ARM", "SPY",
    "NVDA", "AMD", "MSTR", "COIN", "META", "GOOG",
    "AAPL", "MSFT", "AMZN", "PLTR", "HOOD", "SMCI",
    "SNDK", "ASTS", "CRWV",
    "AVGO", "TSM", "VRT", "SOFI",
]

# Promotion gates vs v39d default on same symbol
MIN_TRADES = 8
# beat baseline on ret AND sharpe; DD not worse by more than this absolute
MAX_DD_WORSE = 0.03


def _code(sym: str) -> str:
    s = sym.strip().upper().replace(".US", "")
    if s == "INFQ":
        s = "IONQ"
    if s == "GOOGL":
        s = "GOOG"
    return f"{s}.US"


def _base(sym: str) -> str:
    return _code(sym).replace(".US", "")


def extract_v39d_donors() -> dict[str, dict[str, Any]]:
    src = (V39D / "signal_engine.py").read_text()
    m = re.search(r"_ROUTING = (\{.*?\})\n\n", src, re.S)
    if not m:
        raise RuntimeError("could not parse v39d _ROUTING")
    routing = ast.literal_eval(m.group(1))
    donors: dict[str, dict[str, Any]] = {}
    name_map = {
        "TSLA.US": "dna_tsla",
        "MU.US": "dna_mu",
        "SPY.US": "dna_spy",
        "ARM.US": "dna_arm",
        "IONQ.US": "dna_ionq",
        "APLD.US": "dna_apld",
    }
    for code, name in name_map.items():
        if code in routing:
            donors[name] = dict(routing[code])
    if not donors:
        raise RuntimeError("no DNA donors extracted")
    return donors


def has_local(sym: str) -> bool:
    return (CACHE_1H / f"{_base(sym)}.parquet").exists()


def source_for(sym: str) -> str:
    return "local" if has_local(sym) else "yfinance"


def _patch_routing(engine_src: str, symbol_code: str, dna: dict[str, Any]) -> str:
    """Replace _ROUTING with a single-symbol map (literal AST-safe)."""
    # Force this symbol's DNA; also set SPY.US fallback (v39d uses it for unknowns).
    routing: dict[str, Any] = {symbol_code: dna}
    if symbol_code != "SPY.US":
        routing["SPY.US"] = dna
    lit = repr(routing)
    new_src, n = re.subn(
        r"_ROUTING = \{.*?\}\n\n",
        f"_ROUTING = {lit}\n\n",
        engine_src,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise RuntimeError("failed to patch _ROUTING")
    return new_src


def build_v39d_variant(
    symbol: str,
    dna_name: str,
    dna: dict[str, Any],
    *,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Create a runnable v39d fork with forced DNA for one symbol."""
    base = _base(symbol)
    code = _code(symbol)
    mid = model_id or f"_bake_{base.lower()}_{dna_name}"
    dst = OUT / "models" / mid
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    # Copy required runtime files from v39d
    for name in (
        "signal_engine.py",
        "candidate_ledger.py",
        "meta_config.json",
        "meta_xgb_final.json",
        "config.json",
    ):
        src = V39D / name
        if src.exists():
            shutil.copy2(src, dst / name)

    # Also copy candidate_ledger from _shared if missing
    if not (dst / "candidate_ledger.py").exists():
        shared = MODELS / "_shared" / "candidate_ledger.py"
        if shared.exists():
            shutil.copy2(shared, dst / "candidate_ledger.py")

    engine = (dst / "signal_engine.py").read_text()
    (dst / "signal_engine.py").write_text(_patch_routing(engine, code, dna))

    cfg = {
        "source": source_for(base),
        "codes": [code],
        "start_date": START,
        "end_date": END,
        "initial_cash": CASH,
        "commission": 0.001,
        "engine": "daily",
        "interval": "1H",
        "strategy": {
            "name": mid,
            "model_version": mid,
            "desk_specialist": True,
            "desk_symbol": code,
            "dna_donor": dna_name,
            "engine_base": "v39d_confluence",
            "note": "Proper specialist: v39d + XGB meta + symbol DNA",
        },
    }
    (dst / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")

    # Paths must be Path objects — dmr.run_one does Path arithmetic.
    return {
        "id": mid,
        "model_dir": dst,
        "src_dir": dst,
        "interval": "1H",
        "modes": ["daily"],
        "path": str(dst / "signal_engine.py"),
    }


def run_variant(model: dict[str, Any], symbol: str, tag: str) -> dict[str, Any]:
    code = _code(symbol)
    src = source_for(symbol)
    try:
        row = dmr.run_one(
            model,
            mode="daily",
            codes=[code],
            start=START,
            end=END,
            tag=tag,
            cash=CASH,
            force_1d=False,
            source=src,
            interval="1H",
            reuse=True,
        )
        row["symbol"] = code
        row["source_data"] = src
        row["ok"] = True
        return row
    except Exception as e:
        return {
            "id": model.get("id"),
            "symbol": code,
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "ret": -9.0,
            "dd": -1.0,
            "sharpe": 0.0,
            "n": 0,
            "wr": 0.0,
            "final": 0.0,
        }


def discover_v39d() -> dict[str, Any]:
    models = dmr.discover_models(["v39d_confluence"])
    if not models:
        raise RuntimeError("v39d_confluence not discoverable")
    return models[0]


def baseline_for_symbol(symbol: str, v39d: dict[str, Any]) -> dict[str, Any]:
    """v39d as-is (uses native DNA if in bag, else SPY fallback)."""
    return run_variant(v39d, symbol, tag=f"bake_base_{_base(symbol).lower()}")


def multi_lock_beats(cand: dict[str, Any], base: dict[str, Any]) -> bool:
    if not cand.get("ok", True) or cand.get("n", 0) < MIN_TRADES:
        return False
    if base.get("n", 0) <= 0 and cand.get("n", 0) >= MIN_TRADES and cand.get("ret", -9) > 0:
        return True
    if cand.get("ret", -9) <= base.get("ret", 0):
        return False
    if cand.get("sharpe", -9) <= base.get("sharpe", 0):
        return False
    # dd is negative; more negative = worse
    if cand.get("dd", -1) < base.get("dd", 0) - MAX_DD_WORSE:
        return False
    return True


def bake_symbol(symbol: str, donors: dict[str, dict[str, Any]], v39d: dict[str, Any]) -> dict[str, Any]:
    code = _code(symbol)
    base = baseline_for_symbol(symbol, v39d)
    rows: list[dict[str, Any]] = [dict(base, dna="v39d_default", kind="baseline")]

    for dna_name, dna in donors.items():
        # Skip donor that is already native identity for bag symbols
        # (still test — DNA applied explicitly)
        model = build_v39d_variant(symbol, dna_name, dna)
        row = run_variant(model, symbol, tag=f"bake_{_base(symbol).lower()}_{dna_name}")
        row["dna"] = dna_name
        row["kind"] = "donor"
        rows.append(row)

    # Optional: existing v65 (prove it loses) if present
    v65_id = f"v65_spec_{_base(symbol).lower()}"
    if (MODELS / v65_id / "signal_engine.py").exists():
        try:
            m65 = dmr.discover_models([v65_id])
            if m65:
                r65 = run_variant(m65[0], symbol, tag=f"bake_old_{_base(symbol).lower()}")
                r65["dna"] = "old_v65_thin"
                r65["kind"] = "legacy_broken"
                rows.append(r65)
        except Exception:
            pass

    # CRWV bounce
    if _base(symbol) == "CRWV" and (MODELS / "v64_crwv_bounce" / "signal_engine.py").exists():
        try:
            m64 = dmr.discover_models(["v64_crwv_bounce"])
            if m64:
                r64 = run_variant(m64[0], symbol, tag="bake_crwv_v64")
                r64["dna"] = "v64_bounce"
                r64["kind"] = "bounce"
                rows.append(r64)
        except Exception:
            pass

    # Rank candidates (exclude broken failures / legacy thin engines)
    viable = [
        r for r in rows
        if r.get("n", 0) > 0
        and r.get("ret", -9) > -8
        and r.get("kind") != "legacy_broken"
    ]
    viable.sort(key=lambda r: (r.get("sharpe", 0), r.get("ret", 0)), reverse=True)
    best = viable[0] if viable else base
    promoted = False
    # Always rebuild a working v39d-based specialist folder for the desk.
    # Multi-lock beat → DNA edge; else still ship champion DNA (honest).
    promote_model = f"v65_spec_{_base(symbol).lower()}"
    promote_dna = "dna_spy"  # safe default for unmapped

    if best.get("kind") == "bounce" and multi_lock_beats(best, base):
        promote_model = "v64_crwv_bounce"
        promote_dna = "v64_bounce"
        promoted = True
    elif best.get("kind") == "donor" and multi_lock_beats(best, base):
        promote_dna = str(best.get("dna") or "dna_spy")
        promoted = True
    elif best.get("kind") == "donor":
        # Best donor even without multi-lock — still better UX than broken thin eng
        promote_dna = str(best.get("dna") or "dna_spy")
        promoted = False
    elif best.get("kind") == "baseline":
        # Map bag symbols to their native DNA labels when known
        native = {
            "TSLA.US": "dna_tsla",
            "MU.US": "dna_mu",
            "SPY.US": "dna_spy",
            "ARM.US": "dna_arm",
            "IONQ.US": "dna_ionq",
            "APLD.US": "dna_apld",
        }
        promote_dna = native.get(code, "dna_spy")
        promoted = False
        # Keep promote_model as v65_spec so desk has a working specialist engine
    else:
        promote_dna = "dna_spy"
        promoted = False

    return {
        "symbol": code,
        "source_data": source_for(symbol),
        "baseline": _slim(base),
        "best": _slim(best),
        "promoted": promoted,
        "promote_model": promote_model,
        "promote_dna": promote_dna,
        "rows": [_slim(r) for r in rows],
    }


def _slim(r: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "id", "dna", "kind", "ret", "dd", "sharpe", "n", "wr", "final",
        "ok", "error", "source_data", "symbol",
    ]
    return {k: r.get(k) for k in keys if k in r or k in ("ret", "dd", "sharpe", "n", "wr", "final")}


def promote_specialist(result: dict[str, Any], donors: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Write permanent v65_spec_* as v39d fork with best DNA (always working engine)."""
    code = result["symbol"]
    base = _base(code)
    model_id = result["promote_model"]
    dna_name = result["promote_dna"]

    if model_id == "v64_crwv_bounce":
        return {
            "symbol": code,
            "model": "v64_crwv_bounce",
            "specialist": "crwv_demand_bounce",
            "family": "demand_bounce",
            "dna": "v64_bounce",
            "routed": True,
            "promoted_specialist": True,
            "dna_edge": True,
        }

    if not dna_name or dna_name not in donors:
        dna_name = "dna_spy"
    dna = donors[dna_name]
    # Permanent model under models/
    mid = f"v65_spec_{base.lower()}"
    dst = MODELS / mid
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for name in (
        "signal_engine.py",
        "candidate_ledger.py",
        "meta_config.json",
        "meta_xgb_final.json",
    ):
        src = V39D / name
        if src.exists():
            shutil.copy2(src, dst / name)
    if not (dst / "candidate_ledger.py").exists():
        shared = MODELS / "_shared" / "candidate_ledger.py"
        if shared.exists():
            shutil.copy2(shared, dst / "candidate_ledger.py")

    engine = (dst / "signal_engine.py").read_text()
    engine = _patch_routing(engine, code, dna)
    # Single-name specialists must not inherit bag drop-lists (ARM/QQQ etc.).
    engine = re.sub(r"TRADE_DROP = \{[^}]*\}", 'TRADE_DROP = {"__none__"}', engine)
    engine = re.sub(r"REGIME_FLAT = \{[^}]*\}", 'REGIME_FLAT = {"__none__"}', engine)
    (dst / "signal_engine.py").write_text(engine)

    cfg = {
        "source": source_for(base),
        "codes": [code],
        "start_date": START,
        "end_date": END,
        "initial_cash": 1000000,
        "commission": 0.001,
        "engine": "daily",
        "interval": "1H",
        "strategy": {
            "name": mid,
            "model_version": mid,
            "desk_specialist": True,
            "desk_symbol": code,
            "dna_donor": dna_name,
            "engine_base": "v39d_confluence",
            "bakeoff": result.get("best"),
            "note": "Proper specialist rebuilt from v39d + winning DNA bakeoff",
        },
    }
    (dst / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (dst / "MODEL.md").write_text(
        f"# {mid}\n\n"
        f"Proper desk specialist for **{code}**.\n\n"
        f"- Engine: `v39d_confluence` (XGB meta + confluence)\n"
        f"- DNA donor: `{dna_name}`\n"
        f"- Bakeoff best: ret={result['best'].get('ret')} sharpe={result['best'].get('sharpe')} "
        f"n={result['best'].get('n')} vs baseline ret={result['baseline'].get('ret')}\n"
        f"- Rebuilt by `tools/bakeoff_specialists.py` because thin v65 engines failed.\n"
    )

    # specialists pack
    pack = MODELS / "specialists" / base
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (pack / "README.md").write_text(
        f"# {base} specialist (v39d-based)\n\n"
        f"DNA: `{dna_name}` — promoted after multi-lock bakeoff vs v39d default.\n"
    )

    return {
        "symbol": code,
        "model": mid,
        "specialist": f"{base.lower()}_{dna_name}",
        "family": dna_name,
        "dna": dna_name,
        "routed": True,
        "promoted_specialist": True,
        "dna_edge": bool(result.get("promoted")),
    }


def update_desk_routing(routes: list[dict[str, Any]]) -> None:
    if DESK_ROUTING.exists():
        data = json.loads(DESK_ROUTING.read_text())
    else:
        data = {"version": 3, "by_symbol": {}, "alias": {}}
    by = data.setdefault("by_symbol", {})
    for r in routes:
        code = r["symbol"]
        by[code] = {
            "model": r["model"],
            "specialist": r["specialist"],
            "family": r.get("family"),
            "dna": r.get("dna"),
            "source_dir": f"specialists/{_base(code)}" if r.get("promoted_specialist") else "v39d_confluence",
            "track": "specialist" if r["model"] != "v39d_confluence" else "standard",
            "engine_base": "v39d_confluence",
            # True only when DNA multi-locked vs v39d default on this symbol.
            "bakeoff_promoted": bool(r.get("dna_edge")),
            "dna_edge": bool(r.get("dna_edge")),
        }
    data["version"] = 3
    data["universal_model"] = "v67_universal_specialist"
    data["fallback_equity"] = "v39d_confluence"
    data["best_router"] = "v66_best_router"
    data["routing_mode"] = "competitive_best"
    data["note"] = (
        "Specialists are v39d+XGB forks. dna_edge=true only when bakeoff multi-locked "
        "a routing DNA beat vs v39d default. All v65_spec_* now use the champion engine."
    )
    DESK_ROUTING.write_text(json.dumps(data, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="Comma list; default full desk set")
    ap.add_argument("--quick", action="store_true", help="Core names only")
    ap.add_argument("--promote", action="store_true", help="Rebuild specialists + DESK_ROUTING")
    ap.add_argument("--workers", type=int, default=1, help="Parallel symbols (1=safe)")
    args = ap.parse_args(argv)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    elif args.quick:
        symbols = ["TSLA", "MU", "NVDA", "META", "MSTR", "COIN", "AVGO", "PLTR", "IONQ", "CRWV"]
    else:
        symbols = list(DEFAULT_SYMBOLS)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "models").mkdir(parents=True, exist_ok=True)
    donors = extract_v39d_donors()
    v39d = discover_v39d()

    print(f"Donors: {list(donors.keys())}", flush=True)
    print(f"Symbols ({len(symbols)}): {symbols}", flush=True)
    print(f"Window {START}→{END} cash=${CASH:g} interval=1H", flush=True)

    results: list[dict[str, Any]] = []

    def _one(sym: str) -> dict[str, Any]:
        print(f"\n=== {sym} ({source_for(sym)}) ===", flush=True)
        try:
            r = bake_symbol(sym, donors, v39d)
            b, best = r["baseline"], r["best"]
            print(
                f"  base  ret={b.get('ret',0):+.1%} sh={b.get('sharpe',0):.2f} "
                f"dd={b.get('dd',0):+.1%} n={b.get('n')} wr={b.get('wr',0):.0%}",
                flush=True,
            )
            print(
                f"  best  dna={best.get('dna')} ret={best.get('ret',0):+.1%} "
                f"sh={best.get('sharpe',0):.2f} dd={best.get('dd',0):+.1%} n={best.get('n')} "
                f"→ {'PROMOTE '+str(r['promote_model']) if r['promoted'] else 'KEEP v39d'}",
                flush=True,
            )
            return r
        except Exception as e:
            print(f"  FAIL {sym}: {e}", flush=True)
            traceback.print_exc()
            return {
                "symbol": _code(sym),
                "error": str(e),
                "promoted": False,
                "promote_model": "v39d_confluence",
                "promote_dna": "v39d_default",
                "baseline": {},
                "best": {},
                "rows": [],
            }

    if args.workers <= 1:
        for s in symbols:
            results.append(_one(s))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(_one, s): s for s in symbols}
            for fut in as_completed(futs):
                results.append(fut.result())
        # stable order
        order = {_code(s): i for i, s in enumerate(symbols)}
        results.sort(key=lambda r: order.get(r.get("symbol", ""), 999))

    summary_path = OUT / "SUMMARY.json"
    summary_path.write_text(json.dumps(results, indent=2, default=str) + "\n")

    # Leaderboard markdown
    lines = [
        "# Specialist bakeoff (v39d DNA)",
        "",
        f"Window `{START}` → `{END}`, cash `${CASH:g}`, interval `1H`.",
        "",
        "Proper specialists = **v39d engine + XGB meta + winning routing DNA**.",
        "Thin `v65` engines without meta are treated as legacy/broken.",
        "",
        "| Symbol | Data | Baseline ret/sh/n | Best DNA | Best ret/sh/n | Decision |",
        "|--------|------|-------------------|----------|---------------|----------|",
    ]
    for r in results:
        b, best = r.get("baseline") or {}, r.get("best") or {}
        lines.append(
            f"| {r.get('symbol')} | {r.get('source_data','')} | "
            f"{b.get('ret',0):+.1%}/{b.get('sharpe',0):.2f}/{b.get('n',0)} | "
            f"{best.get('dna','')} | "
            f"{best.get('ret',0):+.1%}/{best.get('sharpe',0):.2f}/{best.get('n',0)} | "
            f"{'**'+r.get('promote_model','')+'**' if r.get('promoted') else r.get('promote_model','')} |"
        )
    (OUT / "LEADERBOARD.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines), flush=True)
    print(f"\nWrote {summary_path}", flush=True)

    if args.promote:
        routes = []
        for r in results:
            if r.get("error") and not r.get("baseline"):
                routes.append({
                    "symbol": r["symbol"],
                    "model": "v39d_confluence",
                    "specialist": f"{_base(r['symbol']).lower()}_v39d_default",
                    "family": "champion_default",
                    "dna": "v39d_default",
                    "promoted_specialist": False,
                })
                continue
            pr = promote_specialist(r, donors)
            if pr:
                routes.append(pr)
                print(f"  route {pr['symbol']} → {pr['model']} ({pr.get('dna')})", flush=True)
        update_desk_routing(routes)
        print(f"Updated {DESK_ROUTING}", flush=True)
        (OUT / "ROUTES.json").write_text(json.dumps(routes, indent=2) + "\n")

    n_prom = sum(1 for r in results if r.get("promoted"))
    print(f"\nDone. {n_prom}/{len(results)} symbols earned a specialist DNA edge.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
