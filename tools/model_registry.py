"""Model registry + ranking for poc_va_macdha variants."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
# Keep aligned with WINNER.json: v15 beats v14 on Sharpe/PF/DD (risk-adj), not raw return.
DEFAULT_MODEL = "v15_meta_xgb"

# Process-local card cache — scan/watch call rank_models_for_symbol per symbol.
_CARD_CACHE: dict[str, Any] = {"mtime_key": None, "cards": None}


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if v != v:  # NaN
            return default
        return v
    except (TypeError, ValueError):
        return default


def score_metrics(wr: float, sharpe: float, pf: float, max_dd: float = 0.0) -> float:
    """Composite used for ranking (aligned with WINNER selection spirit)."""
    wr = _safe_float(wr)
    sharpe = _safe_float(sharpe)
    pf = _safe_float(pf, 1.0)
    max_dd = abs(_safe_float(max_dd))
    sharpe_n = max(0.0, min(sharpe / 2.0, 1.0))
    pf_n = max(0.0, min((pf - 0.8) / 1.2, 1.0))
    dd_pen = min(max_dd / 0.6, 1.0) * 0.10
    return 0.55 * wr + 0.30 * sharpe_n + 0.15 * pf_n - dd_pen


def list_engine_models() -> list[str]:
    """Versions that have a runnable signal_engine.py."""
    out = []
    if not MODELS_ROOT.exists():
        return out
    for p in sorted(MODELS_ROOT.glob("v*")):
        if (p / "signal_engine.py").exists():
            out.append(p.name)
    return out


def engine_path(model: str) -> Path:
    p = MODELS_ROOT / model / "signal_engine.py"
    if not p.exists():
        raise FileNotFoundError(f"No engine for model {model}: {p}")
    return p


def _extract_portfolio(d: Any) -> dict | None:
    if isinstance(d, dict):
        if isinstance(d.get("portfolio"), dict) and "sharpe" in d["portfolio"]:
            return d["portfolio"]
        if "sharpe" in d and "win_rate" in d:
            return d
    return None


def _extract_per_symbol(d: Any) -> dict[str, dict]:
    """Normalize various results.json shapes → {CODE: metrics}."""
    out: dict[str, dict] = {}
    if isinstance(d, list):
        for row in d:
            if isinstance(row, dict) and "code" in row:
                out[str(row["code"]).upper()] = row
        return out
    if not isinstance(d, dict):
        return out
    ps = d.get("per_symbol")
    if isinstance(ps, list):
        for row in ps:
            if isinstance(row, dict) and "code" in row:
                out[str(row["code"]).upper()] = row
    elif isinstance(ps, dict):
        for code, row in ps.items():
            if isinstance(row, dict):
                out[str(code).upper()] = row
    specs = d.get("specialists")
    if isinstance(specs, dict):
        for code, row in specs.items():
            if isinstance(row, dict) and "win_rate" in row:
                out.setdefault(str(code).upper(), row)
    return out


def load_version_card(model: str) -> dict[str, Any]:
    """Portfolio + per-symbol metrics for a frozen version folder."""
    folder = MODELS_ROOT / model
    card: dict[str, Any] = {
        "model": model,
        "has_engine": (folder / "signal_engine.py").exists(),
        "portfolio": None,
        "per_symbol": {},
        "source": None,
    }
    results = folder / "results.json"
    if results.exists():
        d = json.loads(results.read_text())
        card["portfolio"] = _extract_portfolio(d)
        card["per_symbol"] = _extract_per_symbol(d)
        card["source"] = "results.json"
    return card


def load_leaderboard_cards() -> list[dict[str, Any]]:
    """Training sweep variants (may not all have engines)."""
    path = MODELS_ROOT / "TRAINING_LEADERBOARD.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text())
    cards = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        variant = row.get("variant") or row.get("model")
        if not variant:
            continue
        port = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else None
        per = {}
        for r in row.get("per_symbol") or []:
            if isinstance(r, dict) and "code" in r:
                per[str(r["code"]).upper()] = r
        cards.append(
            {
                "model": str(variant),
                "has_engine": (MODELS_ROOT / str(variant) / "signal_engine.py").exists(),
                "portfolio": port,
                "per_symbol": per,
                "source": "TRAINING_LEADERBOARD",
                "avg_win_rate": row.get("avg_win_rate"),
                "composite": row.get("composite"),
            }
        )
    return cards


def _leaderboard_mtime_key() -> tuple[Any, ...]:
    """Invalidate cache when leaderboard or any results.json changes."""
    parts: list[Any] = []
    lb = MODELS_ROOT / "TRAINING_LEADERBOARD.json"
    parts.append(lb.stat().st_mtime_ns if lb.exists() else 0)
    if MODELS_ROOT.exists():
        for p in sorted(MODELS_ROOT.glob("v*/results.json")):
            parts.append((p.as_posix(), p.stat().st_mtime_ns))
    return tuple(parts)


def clear_model_card_cache() -> None:
    _CARD_CACHE["mtime_key"] = None
    _CARD_CACHE["cards"] = None


def all_model_cards(engines_only: bool = False) -> list[dict[str, Any]]:
    """Merge frozen version results + leaderboard; prefer folder results for same name."""
    key = _leaderboard_mtime_key()
    if _CARD_CACHE["cards"] is None or _CARD_CACHE["mtime_key"] != key:
        by_name: dict[str, dict[str, Any]] = {}
        for card in load_leaderboard_cards():
            by_name[card["model"]] = card
        for name in list_engine_models():
            card = load_version_card(name)
            if card["portfolio"] or card["per_symbol"]:
                by_name[name] = card
            else:
                by_name.setdefault(name, card)
        for p in sorted(MODELS_ROOT.glob("v*")):
            if not (p / "results.json").exists():
                continue
            if p.name not in by_name:
                by_name[p.name] = load_version_card(p.name)
        _CARD_CACHE["mtime_key"] = key
        _CARD_CACHE["cards"] = list(by_name.values())
    cards = _CARD_CACHE["cards"] or []
    if engines_only:
        return [c for c in cards if c.get("has_engine")]
    return list(cards)


def hist_win_rate(model: str, symbol: str) -> float | None:
    """O(1) cached lookup of historical WR for model+symbol (no full re-rank)."""
    code = symbol.strip().upper()
    if not code.endswith(".US"):
        code = f"{code}.US"
    for card in all_model_cards(engines_only=False):
        if card.get("model") != model:
            continue
        row = (card.get("per_symbol") or {}).get(code)
        if row and row.get("win_rate") is not None:
            return _safe_float(row.get("win_rate"))
    return None


def rank_models(engines_only: bool = False) -> list[dict[str, Any]]:
    """Overall ranking by portfolio metrics."""
    ranked = []
    for card in all_model_cards(engines_only=engines_only):
        port = card.get("portfolio") or {}
        if not port:
            continue
        wr = _safe_float(port.get("win_rate"))
        sh = _safe_float(port.get("sharpe"))
        pf = _safe_float(port.get("profit_factor"), 1.0)
        dd = _safe_float(port.get("max_drawdown"))
        ranked.append(
            {
                "model": card["model"],
                "has_engine": bool(card.get("has_engine")),
                "win_rate": wr,
                "sharpe": sh,
                "profit_factor": pf,
                "max_drawdown": dd,
                "total_return": _safe_float(port.get("total_return")),
                "trade_count": port.get("trade_count"),
                "score": round(score_metrics(wr, sh, pf, dd), 4),
                "source": card.get("source"),
            }
        )
    ranked.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def rank_models_for_symbol(symbol: str, engines_only: bool = False) -> list[dict[str, Any]]:
    """Rank models by historical performance on one symbol."""
    code = symbol.strip().upper()
    if not code.endswith(".US"):
        code = f"{code}.US"
    ranked = []
    for card in all_model_cards(engines_only=engines_only):
        row = (card.get("per_symbol") or {}).get(code)
        if not row:
            continue
        wr = _safe_float(row.get("win_rate"))
        sh = _safe_float(row.get("sharpe"))
        pf = _safe_float(row.get("profit_factor"), 1.0)
        dd = _safe_float(row.get("max_drawdown"))
        ranked.append(
            {
                "model": card["model"],
                "has_engine": bool(card.get("has_engine")),
                "code": code,
                "win_rate": wr,
                "sharpe": sh,
                "profit_factor": pf,
                "max_drawdown": dd,
                "total_return": _safe_float(row.get("total_return")),
                "trade_count": row.get("trade_count"),
                "score": round(score_metrics(wr, sh, pf, dd), 4),
                "source": card.get("source"),
                "specialist": row.get("specialist"),
            }
        )
    ranked.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def recommend_model(symbol: str | None = None) -> dict[str, Any]:
    """Pick best runnable model overall, or best for a symbol."""
    if symbol:
        for row in rank_models_for_symbol(symbol, engines_only=True):
            if row["has_engine"]:
                return {
                    "model": row["model"],
                    "reason": f"best historical score on {row['code']}",
                    "score": row["score"],
                    "win_rate": row["win_rate"],
                    "sharpe": row["sharpe"],
                }
    overall = rank_models(engines_only=True)
    if overall:
        top = overall[0]
        return {
            "model": top["model"],
            "reason": "best portfolio score among engines",
            "score": top["score"],
            "win_rate": top["win_rate"],
            "sharpe": top["sharpe"],
        }
    return {
        "model": DEFAULT_MODEL,
        "reason": "fallback default",
        "score": None,
        "win_rate": None,
        "sharpe": None,
    }
