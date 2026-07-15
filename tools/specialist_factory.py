#!/usr/bin/env python3
"""Universal desk specialist factory.

Honest framing
--------------
Desk ``v65_spec_*`` models are **not** separate trained agents per ticker.
They share one parametric stack (VA + HTF HA + swing VWAP + VPA gates) and
differ only by **family DNA** — a small set of gate / TF knobs.

This factory:
  1. Defines reusable **family DNA** templates (megacap, semi, crypto, etc.).
  2. Classifies any symbol into a family (static map → vol heuristic).
  3. Mints permanent ``v65_spec_<sym>`` packs when you want a dedicated folder.
  4. Powers ``v67_universal_specialist`` which applies family DNA live for *any*
     stock without hand-writing a specialist.

Accuracy note
-------------
- Confidence / hit_prob are **structure + live signal** heuristics, not
  calibrated P(win).
- Family DNA is a prior recipe, not proof of edge on that name.
- Always compete vs bag champions (``route_best_model`` / ``v39d_confluence``).
- Prefer minting only names you actually trade; use universal for the rest.

Usage
-----
  .venv/bin/python tools/specialist_factory.py list-families
  .venv/bin/python tools/specialist_factory.py classify AVGO
  .venv/bin/python tools/specialist_factory.py mint AVGO --route
  .venv/bin/python tools/specialist_factory.py mint-batch NVDA AMD SMCI --route
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "poc_va_macdha"
DESK_ROUTING = MODELS / "DESK_ROUTING.json"
SPEC_DIR = MODELS / "specialists"
UNIVERSAL = MODELS / "v67_universal_specialist"
ENGINE_TEMPLATE = MODELS / "v65_spec_tsla" / "signal_engine.py"

# ---------------------------------------------------------------------------
# Family DNA — the only real differentiation across specialists
# ---------------------------------------------------------------------------
# Each family is a gate recipe that historically matches a *style* of name.
# Do not invent a new family for every ticker; map into these.

_BASE_GATES: dict[str, Any] = {
    "value_area_pct": 0.7,
    "profile_rows": 25,
    "profile_lookback": 20,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "macd_htf": "4h",
    "signal_tf": "2h",
    "require_htf_green": True,
    "require_vwap_uptrend": False,
    "require_above_vwap": False,
    "require_volume_expand": False,
    "require_vol_confirm": False,
    "block_red_flag": True,
    "block_dump": True,
    "require_sqz_release": False,
    "require_mom_pos": False,
    "require_mom_pos_inc": False,
    "allow_healthy_pull_entry": False,
    "exit_on_poc_break": False,
    "exit_on_val_break": False,
    "exit_below_vwap": False,
    "exit_on_sqz_neg": False,
    "soft_confidence": False,
    "swing_period": 50,
    "vol_look": 5,
    "vol_sma": 20,
    "min_confidence": 0.6,
}

FAMILY_DNA: dict[str, dict[str, Any]] = {
    "megacap_quality": {
        "label": "Large-cap quality (AAPL/MSFT/META style)",
        "why": "VWAP trend + HTF green; fewer VPA hard blocks",
        "prior": 0.62,
        "gates": {
            "require_vwap_uptrend": True,
            "require_above_vwap": True,
            "block_red_flag": False,
            "block_dump": False,
            "exit_below_vwap": True,
        },
    },
    "megacap_beta": {
        "label": "Large-cap high beta (TSLA style)",
        "why": "Vol confirm + red-flag/dump blocks; shorter vol look",
        "prior": 0.64,
        "gates": {
            "profile_lookback": 30,
            "require_vol_confirm": True,
            "block_red_flag": True,
            "block_dump": True,
            "vol_look": 3,
        },
    },
    "semi_memory": {
        "label": "Semi / memory cycle (MU/AMD/SNDK)",
        "why": "Simple red-flag/dump block; standard 2H/4H",
        "prior": 0.63,
        "gates": {
            "block_red_flag": True,
            "block_dump": True,
        },
    },
    "semi_leader": {
        "label": "Semi leader (NVDA style)",
        "why": "Vol confirm + dump block; leader momentum bias",
        "prior": 0.64,
        "gates": {
            "require_vol_confirm": True,
            "block_red_flag": True,
            "block_dump": True,
            "vol_look": 3,
        },
    },
    "semi_spec_4h": {
        "label": "Speculative semi 4H (ARM)",
        "why": "4H signal / 1D HTF; above VWAP + mom",
        "prior": 0.60,
        "gates": {
            "macd_htf": "1D",
            "signal_tf": "4h",
            "require_above_vwap": True,
            "require_mom_pos": True,
            "block_dump": False,
            "exit_below_vwap": True,
        },
        "interval": "4H",
    },
    "crypto_beta": {
        "label": "Crypto-beta equities (MSTR/COIN)",
        "why": "Vol confirm + healthy-pull allowed; dump block",
        "prior": 0.61,
        "gates": {
            "require_vol_confirm": True,
            "allow_healthy_pull_entry": True,
            "block_red_flag": True,
            "block_dump": True,
            "vol_look": 3,
        },
    },
    "ai_infra_beta": {
        "label": "AI infra high beta (APLD/SMCI)",
        "why": "Full stack: vol confirm + dump/red-flag + mom soft",
        "prior": 0.60,
        "gates": {
            "require_vol_confirm": True,
            "block_red_flag": True,
            "block_dump": True,
            "require_mom_pos": True,
            "vol_look": 3,
        },
    },
    "spec_high_vol": {
        "label": "High-vol speculative (ASTS/IONQ style)",
        "why": "4H bars; above VWAP + mom; exit below VWAP",
        "prior": 0.58,
        "gates": {
            "macd_htf": "1D",
            "signal_tf": "4h",
            "require_above_vwap": True,
            "require_mom_pos": True,
            "block_dump": False,
            "exit_below_vwap": True,
        },
        "interval": "4H",
    },
    "quantum_spec": {
        "label": "Quantum / pure speculative (IONQ)",
        "why": "Same as high-vol 4H stack",
        "prior": 0.58,
        "gates": {
            "macd_htf": "1D",
            "signal_tf": "4h",
            "require_above_vwap": True,
            "require_mom_pos": True,
            "block_dump": False,
            "exit_below_vwap": True,
        },
        "interval": "4H",
    },
    "software_beta": {
        "label": "Software growth beta (PLTR)",
        "why": "Soft trend: HTF + above VWAP; light dump block",
        "prior": 0.60,
        "gates": {
            "require_above_vwap": True,
            "block_red_flag": True,
            "block_dump": False,
            "exit_below_vwap": True,
        },
    },
    "fintech_beta": {
        "label": "Fintech beta (HOOD)",
        "why": "Vol confirm + dump block",
        "prior": 0.59,
        "gates": {
            "require_vol_confirm": True,
            "block_red_flag": True,
            "block_dump": True,
        },
    },
    "demand_bounce": {
        "label": "Demand bounce (CRWV-like)",
        "why": "Prefer dedicated v64 when mapped; else high-vol recipe",
        "prior": 0.57,
        "gates": {
            "require_vol_confirm": True,
            "require_above_vwap": True,
            "block_red_flag": True,
            "block_dump": True,
            "allow_healthy_pull_entry": True,
            "vol_look": 3,
        },
    },
    "index_trend": {
        "label": "Index / broad ETF (SPY/QQQ)",
        "why": "VWAP trend like megacap quality",
        "prior": 0.61,
        "gates": {
            "require_vwap_uptrend": True,
            "require_above_vwap": True,
            "block_red_flag": False,
            "block_dump": False,
            "exit_below_vwap": True,
        },
    },
    "default_equity": {
        "label": "Default equity (unknown name)",
        "why": "Balanced gates — compete with v39d; do not over-claim edge",
        "prior": 0.55,
        "gates": {
            "require_htf_green": True,
            "block_red_flag": True,
            "block_dump": True,
            "require_above_vwap": False,
        },
    },
}

# Explicit symbol → family (extends DESK_ROUTING families).
_SYMBOL_FAMILY: dict[str, str] = {
    "TSLA": "megacap_beta",
    "META": "megacap_quality",
    "GOOG": "megacap_quality",
    "GOOGL": "megacap_quality",
    "AAPL": "megacap_quality",
    "MSFT": "megacap_quality",
    "AMZN": "megacap_quality",
    "MU": "semi_memory",
    "AMD": "semi_memory",
    "SNDK": "semi_memory",
    "AVGO": "semi_leader",
    "NVDA": "semi_leader",
    "TSM": "semi_leader",
    "ARM": "semi_spec_4h",
    "MSTR": "crypto_beta",
    "COIN": "crypto_beta",
    "MARA": "crypto_beta",
    "RIOT": "crypto_beta",
    "APLD": "ai_infra_beta",
    "SMCI": "ai_infra_beta",
    "VRT": "ai_infra_beta",
    "CRWV": "demand_bounce",
    "IONQ": "quantum_spec",
    "RGTI": "quantum_spec",
    "QBTS": "quantum_spec",
    "ASTS": "spec_high_vol",
    "PLTR": "software_beta",
    "SNOW": "software_beta",
    "CRM": "software_beta",
    "HOOD": "fintech_beta",
    "SOFI": "fintech_beta",
    "SPY": "index_trend",
    "QQQ": "index_trend",
    "IWM": "index_trend",
    "DIA": "index_trend",
}

_ALIAS = {
    "INFQ": "IONQ",
    "GOOGL": "GOOG",
    "BRK.B": "BRK-B",
    "BRK/B": "BRK-B",
}


def normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    if s.endswith(".US"):
        s = s[:-3]
    s = s.replace(" ", "")
    return _ALIAS.get(s, s)


def code_us(symbol: str) -> str:
    base = normalize_symbol(symbol)
    return f"{base}.US" if base else ""


def list_families() -> list[dict[str, Any]]:
    out = []
    for fam, meta in FAMILY_DNA.items():
        out.append(
            {
                "family": fam,
                "label": meta["label"],
                "why": meta["why"],
                "prior": meta.get("prior", 0.55),
                "interval": meta.get("interval", "1H"),
                "gate_overrides": meta.get("gates", {}),
            }
        )
    return out


def resolve_gates(family: str) -> dict[str, Any]:
    meta = FAMILY_DNA.get(family) or FAMILY_DNA["default_equity"]
    gates = dict(_BASE_GATES)
    gates.update(meta.get("gates") or {})
    return gates


def classify_symbol(
    symbol: str,
    *,
    vol_ann: float | None = None,
    avg_dollar_vol: float | None = None,
) -> dict[str, Any]:
    """Map a symbol to family DNA.

    Priority:
      1. explicit map
      2. DESK_ROUTING family if present
      3. vol / liquidity heuristics
      4. default_equity
    """
    base = normalize_symbol(symbol)
    code = code_us(base)

    # 1) static map
    if base in _SYMBOL_FAMILY:
        fam = _SYMBOL_FAMILY[base]
        return _pack(base, code, fam, source="symbol_map")

    # 2) DESK_ROUTING
    try:
        data = json.loads(DESK_ROUTING.read_text()) if DESK_ROUTING.exists() else {}
        row = (data.get("by_symbol") or {}).get(code)
        if isinstance(row, dict) and row.get("family"):
            fam = str(row["family"])
            if fam not in FAMILY_DNA:
                fam = "default_equity"
            return _pack(
                base,
                code,
                fam,
                source="desk_routing",
                model=row.get("model"),
                specialist=row.get("specialist"),
            )
    except Exception:
        pass

    # 3) heuristics from optional stats (caller can pass yfinance-derived)
    if vol_ann is not None:
        if vol_ann >= 0.90:
            return _pack(base, code, "spec_high_vol", source="vol_heuristic", vol_ann=vol_ann)
        if vol_ann >= 0.55:
            return _pack(base, code, "megacap_beta", source="vol_heuristic", vol_ann=vol_ann)
        if vol_ann <= 0.28:
            return _pack(base, code, "megacap_quality", source="vol_heuristic", vol_ann=vol_ann)

    if avg_dollar_vol is not None and avg_dollar_vol < 5e7:
        return _pack(base, code, "spec_high_vol", source="liquidity_heuristic", avg_dollar_vol=avg_dollar_vol)

    # 4) ticker-shape heuristics
    if base.endswith("Q") and len(base) <= 5:  # rough speculative suffix bias
        pass
    if re.fullmatch(r"[A-Z]{1,5}", base or ""):
        # unknown liquid-looking ticker → default
        return _pack(base, code, "default_equity", source="default")

    return _pack(base, code, "default_equity", source="default")


def _pack(
    base: str,
    code: str,
    family: str,
    *,
    source: str,
    model: str | None = None,
    specialist: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    meta = FAMILY_DNA.get(family) or FAMILY_DNA["default_equity"]
    gates = resolve_gates(family)
    spec_name = specialist or f"{base.lower()}_{family}"
    return {
        "symbol": base,
        "code": code,
        "family": family,
        "label": meta["label"],
        "why": meta["why"],
        "prior": float(meta.get("prior", 0.55)),
        "interval": meta.get("interval", "1H"),
        "gates": gates,
        "specialist": spec_name,
        "model": model or "v67_universal_specialist",
        "source": source,
        "accurate": False,  # explicit: recipe, not proven edge
        "note": (
            "Family DNA recipe only — not a calibrated probability or "
            "guaranteed specialist edge. Compete with bag champions."
        ),
        **extra,
    }


def estimate_stats(symbol: str) -> dict[str, float | None]:
    """Best-effort vol / dollar-volume from yfinance (optional)."""
    base = normalize_symbol(symbol)
    try:
        import yfinance as yf
        import numpy as np

        h = yf.Ticker(base).history(period="6mo", interval="1d")
        if h is None or h.empty:
            return {"vol_ann": None, "avg_dollar_vol": None}
        h.columns = [str(c).lower() for c in h.columns]
        rets = h["close"].pct_change().dropna()
        vol_ann = float(rets.std() * (252 ** 0.5)) if len(rets) > 5 else None
        dv = (h["close"] * h["volume"]).tail(20).mean()
        avg_dv = float(dv) if np.isfinite(dv) else None
        return {"vol_ann": vol_ann, "avg_dollar_vol": avg_dv}
    except Exception:
        return {"vol_ann": None, "avg_dollar_vol": None}


def classify_with_market(symbol: str) -> dict[str, Any]:
    """Classify using live market stats when available."""
    base = normalize_symbol(symbol)
    if base in _SYMBOL_FAMILY:
        return classify_symbol(base)
    stats = estimate_stats(base)
    return classify_symbol(base, vol_ann=stats.get("vol_ann"), avg_dollar_vol=stats.get("avg_dollar_vol"))


def build_config(symbol: str, family: str | None = None) -> dict[str, Any]:
    info = classify_with_market(symbol) if family is None else classify_symbol(symbol)
    if family is not None:
        info = _pack(
            normalize_symbol(symbol),
            code_us(symbol),
            family,
            source="forced_family",
        )
    base = info["symbol"]
    code = info["code"]
    fam = info["family"]
    gates = info["gates"]
    model_id = f"v65_spec_{base.lower()}"
    return {
        "source": "yfinance",
        "codes": [code],
        "start_date": "2024-08-01",
        "end_date": "2026-07-14",
        "initial_cash": 1000000,
        "commission": 0.001,
        "engine": "daily",
        "interval": info.get("interval") or "1H",
        "strategy": {
            "specialist": info["specialist"],
            "family": fam,
            "why": info["why"],
            **gates,
            "model_version": model_id,
            "name": model_id,
            "desk_specialist": True,
            "desk_symbol": code,
            "factory_generated": True,
            "accuracy_note": info["note"],
        },
    }


def mint_specialist(
    symbol: str,
    *,
    family: str | None = None,
    route: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Create specialists/<SYM> + v65_spec_<sym> packs from family DNA."""
    base = normalize_symbol(symbol)
    if not base:
        raise ValueError("empty symbol")
    if not ENGINE_TEMPLATE.exists():
        raise FileNotFoundError(f"engine template missing: {ENGINE_TEMPLATE}")

    cfg = build_config(base, family=family)
    fam = cfg["strategy"]["family"]
    model_id = cfg["strategy"]["name"]
    code = cfg["codes"][0]

    # specialists/<SYM>/
    pack = SPEC_DIR / base
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    engine_dst = pack / "signal_engine.py"
    if force or not engine_dst.exists():
        shutil.copy2(ENGINE_TEMPLATE, engine_dst)
    readme = pack / "README.md"
    if force or not readme.exists():
        readme.write_text(
            f"# {base} specialist\n\n"
            f"- Family: `{fam}`\n"
            f"- Model: `{model_id}`\n"
            f"- Generated by `tools/specialist_factory.py`\n"
            f"- **Not** a proven edge — family DNA recipe only.\n"
            f"- Compete with bag champions via `route_best_model`.\n"
        )

    # runnable model folder
    model_dir = MODELS / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    if force or not (model_dir / "signal_engine.py").exists():
        shutil.copy2(ENGINE_TEMPLATE, model_dir / "signal_engine.py")
    (model_dir / "MODEL.md").write_text(
        f"# {model_id}\n\n"
        f"Factory-minted specialist for **{code}**.\n\n"
        f"- Family DNA: `{fam}`\n"
        f"- Source: `tools/specialist_factory.py`\n"
        f"- Accuracy: recipe prior only; validate before promoting.\n"
    )

    routed = False
    if route:
        routed = _route_symbol(code, model_id, cfg["strategy"]["specialist"], fam)

    return {
        "symbol": base,
        "code": code,
        "family": fam,
        "model": model_id,
        "specialist_dir": str(pack.relative_to(ROOT)),
        "model_dir": str(model_dir.relative_to(ROOT)),
        "routed": routed,
        "config": cfg,
    }


def _route_symbol(code: str, model: str, specialist: str, family: str) -> bool:
    data: dict[str, Any]
    if DESK_ROUTING.exists():
        data = json.loads(DESK_ROUTING.read_text())
    else:
        data = {"version": 2, "by_symbol": {}}
    by = data.setdefault("by_symbol", {})
    by[code] = {
        "model": model,
        "specialist": specialist,
        "family": family,
        "source_dir": f"specialists/{code.replace('.US', '')}",
        "track": "specialist",
        "factory_generated": True,
    }
    data.setdefault("universal_model", "v67_universal_specialist")
    data.setdefault("routing_mode", "competitive_best")
    DESK_ROUTING.write_text(json.dumps(data, indent=2) + "\n")
    return True


def ensure_universal_model() -> Path:
    """Ensure v67_universal_specialist exists with config."""
    UNIVERSAL.mkdir(parents=True, exist_ok=True)
    if ENGINE_TEMPLATE.exists() and not (UNIVERSAL / "signal_engine.py").exists():
        shutil.copy2(ENGINE_TEMPLATE, UNIVERSAL / "signal_engine.py")
    cfg = {
        "source": "yfinance",
        "codes": [],
        "start_date": "2024-08-01",
        "end_date": "2026-07-14",
        "initial_cash": 1000000,
        "commission": 0.001,
        "engine": "daily",
        "interval": "1H",
        "strategy": {
            "name": "v67_universal_specialist",
            "model_version": "v67_universal_specialist",
            "desk_specialist": True,
            "universal": True,
            "why": "Applies family DNA from specialist_factory for any symbol",
            "accuracy_note": "Recipe only — competes with bag champions",
        },
    }
    (UNIVERSAL / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (UNIVERSAL / "MODEL.md").write_text(
        "# v67_universal_specialist\n\n"
        "One engine for **any** equity symbol.\n\n"
        "At `generate()` time it classifies each code into a **family DNA** "
        "template (see `tools/specialist_factory.py`) and runs the parametric "
        "VA/VWAP/VPA stack with those gates.\n\n"
        "## Honesty\n"
        "- Not a unique ML model per stock.\n"
        "- Not calibrated confidence.\n"
        "- Use as a **candidate** against `v39d_confluence` / `v39b_live_adapt`.\n"
        "- Mint permanent `v65_spec_*` only for names you trade heavily.\n"
    )
    return UNIVERSAL


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Desk specialist factory")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-families", help="List family DNA templates")

    c = sub.add_parser("classify", help="Classify a symbol into family DNA")
    c.add_argument("symbol")
    c.add_argument("--no-market", action="store_true", help="Skip yfinance vol heuristic")

    m = sub.add_parser("mint", help="Mint permanent specialist pack")
    m.add_argument("symbol")
    m.add_argument("--family", default=None, help="Force family id")
    m.add_argument("--route", action="store_true", help="Write DESK_ROUTING entry")
    m.add_argument("--force", action="store_true", help="Overwrite engine/README")

    b = sub.add_parser("mint-batch", help="Mint many symbols")
    b.add_argument("symbols", nargs="+")
    b.add_argument("--route", action="store_true")
    b.add_argument("--force", action="store_true")

    sub.add_parser("ensure-universal", help="Create/refresh v67_universal_specialist")

    args = p.parse_args(argv)

    if args.cmd == "list-families":
        print(json.dumps(list_families(), indent=2))
        return 0

    if args.cmd == "classify":
        info = (
            classify_symbol(args.symbol)
            if args.no_market
            else classify_with_market(args.symbol)
        )
        # drop bulky gates for terminal unless useful
        print(json.dumps(info, indent=2, default=str))
        return 0

    if args.cmd == "mint":
        out = mint_specialist(
            args.symbol, family=args.family, route=args.route, force=args.force
        )
        print(json.dumps({k: v for k, v in out.items() if k != "config"}, indent=2))
        return 0

    if args.cmd == "mint-batch":
        rows = []
        for s in args.symbols:
            rows.append(
                mint_specialist(s, route=args.route, force=args.force)
            )
        print(json.dumps(
            [{k: v for k, v in r.items() if k != "config"} for r in rows],
            indent=2,
        ))
        return 0

    if args.cmd == "ensure-universal":
        path = ensure_universal_model()
        print(json.dumps({"ok": True, "path": str(path.relative_to(ROOT))}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_main())
