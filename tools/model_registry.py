"""Model registry + ranking for poc_va_macdha variants."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = ROOT / "models" / "poc_va_macdha"
RANKER_ROOT = ROOT / "runs" / "symbol_ranker"
RANKER_MAX_AGE_DAYS = 7
# Fallback if WINNER.json missing; live default prefers WINNER via equity_default_model().
DEFAULT_MODEL = "v39b_live_adapt"
# Options stack default = OOS champion (see OPTIONS_WINNER.json / runs/poc_va_oos_rank/).
OPTIONS_DEFAULT_MODEL = "v32_soft_react_opts"
OPTIONS_WINNER_PATH = MODELS_ROOT / "OPTIONS_WINNER.json"
EQUITY_WINNER_PATH = MODELS_ROOT / "WINNER.json"
DESK_ROUTING_PATH = MODELS_ROOT / "DESK_ROUTING.json"

# Trade timeframes used by ranking, confidence, and desk auto-routing.
HORIZONS: tuple[str, ...] = ("day", "swing", "position")
DEFAULT_HORIZON = "swing"

# Model affinity per horizon (how well each DNA fits hold period).
# day = intraday/1H, swing = multi-day/1D, position = weeks–months.
_MODEL_HORIZON_AFFINITY: dict[str, dict[str, float]] = {
    "v71_live_confidence": {"day": 0.95, "swing": 0.72, "position": 0.40},
    "v72_dual_sleeve": {"day": 0.92, "swing": 0.88, "position": 0.55},
    "v50_high_win_rate": {"day": 0.55, "swing": 0.95, "position": 0.75},
    "v39d_confluence": {"day": 0.85, "swing": 0.92, "position": 0.78},
    "v39b_live_adapt": {"day": 0.82, "swing": 0.88, "position": 0.72},
    "v63_spy_prune": {"day": 0.70, "swing": 0.80, "position": 0.70},
    "v45_ultimate_rsi": {"day": 0.50, "swing": 0.90, "position": 0.65},
    "v60_microstructure": {"day": 0.90, "swing": 0.55, "position": 0.30},
    "v61_institutional_flow": {"day": 0.88, "swing": 0.60, "position": 0.35},
    "v48_regime_barbell": {"day": 0.65, "swing": 0.85, "position": 0.80},
    "v49_precision_trend": {"day": 0.60, "swing": 0.88, "position": 0.82},
}

# Prefix affinities (specialists lean swing; routers inherit child mix).
_PREFIX_HORIZON_AFFINITY: tuple[tuple[str, dict[str, float]], ...] = (
    ("v65_spec_", {"day": 0.70, "swing": 0.92, "position": 0.70}),
    ("v64_", {"day": 0.65, "swing": 0.90, "position": 0.65}),
    ("v67_universal", {"day": 0.68, "swing": 0.85, "position": 0.68}),
    ("v66_best", {"day": 0.80, "swing": 0.85, "position": 0.70}),
    ("v70_self", {"day": 0.80, "swing": 0.85, "position": 0.70}),
)

_DEFAULT_HORIZON_AFFINITY: dict[str, float] = {
    "day": 0.70,
    "swing": 0.75,
    "position": 0.60,
}


def normalize_horizon(horizon: str | None) -> str:
    """Map aliases to day | swing | position."""
    raw = str(horizon or DEFAULT_HORIZON).strip().lower()
    aliases = {
        "intraday": "day",
        "daytrade": "day",
        "day_trade": "day",
        "scalp": "day",
        "1h": "day",
        "hourly": "day",
        "short": "day",
        "swing": "swing",
        "multiday": "swing",
        "multi_day": "swing",
        "week": "swing",
        "weekly": "swing",
        "1d": "swing",
        "daily": "swing",
        "position": "position",
        "invest": "position",
        "long": "position",
        "long_term": "position",
        "longterm": "position",
        "buy_hold": "position",
        "buyandhold": "position",
    }
    h = aliases.get(raw, raw)
    return h if h in HORIZONS else DEFAULT_HORIZON


def model_horizon_affinity(model: str, horizon: str | None = None) -> float:
    """Return 0–1 affinity of ``model`` to a trade horizon."""
    h = normalize_horizon(horizon)
    mid = str(model or "")
    if mid in _MODEL_HORIZON_AFFINITY:
        return float(_MODEL_HORIZON_AFFINITY[mid].get(h, _DEFAULT_HORIZON_AFFINITY[h]))
    for prefix, aff in _PREFIX_HORIZON_AFFINITY:
        if mid.startswith(prefix):
            return float(aff.get(h, _DEFAULT_HORIZON_AFFINITY[h]))
    return float(_DEFAULT_HORIZON_AFFINITY[h])


def horizon_confidence_thresholds(horizon: str | None = None) -> dict[str, float]:
    """Default watch/enter thresholds by horizon (calibrated probability).

    Day is slightly more responsive (short hold, more signals).
    Position demands higher conviction (capital tied longer).
    """
    h = normalize_horizon(horizon)
    if h == "day":
        return {"watch": 0.48, "enter": 0.56}
    if h == "position":
        return {"watch": 0.55, "enter": 0.65}
    return {"watch": 0.50, "enter": 0.60}


def equity_default_model() -> str:
    """Current equity WINNER for desk/auto; falls back to DEFAULT_MODEL."""
    try:
        if EQUITY_WINNER_PATH.exists():
            d = json.loads(EQUITY_WINNER_PATH.read_text())
            w = d.get("winner")
            if w and (MODELS_ROOT / w / "signal_engine.py").exists():
                return str(w)
    except Exception:
        pass
    return DEFAULT_MODEL


def _normalize_symbol_code(symbol: str) -> str:
    code = str(symbol or "").strip().upper()
    if not code:
        return ""
    if code.endswith(".US"):
        return code
    return f"{code}.US"


def load_desk_routing() -> dict[str, Any]:
    """Load DESK_ROUTING.json (symbol → specialist model)."""
    if not DESK_ROUTING_PATH.exists():
        return {"by_symbol": {}, "alias": {}}
    try:
        data = json.loads(DESK_ROUTING_PATH.read_text())
    except Exception:
        return {"by_symbol": {}, "alias": {}}
    return data if isinstance(data, dict) else {"by_symbol": {}, "alias": {}}


def resolve_desk_symbol(symbol: str) -> str:
    """Normalize aliases (INFQ→IONQ, GOOGL→GOOG) to CODE.US form."""
    raw = str(symbol or "").strip().upper()
    if not raw:
        return ""
    routing = load_desk_routing()
    alias = routing.get("alias") or {}
    if raw in alias:
        raw = str(alias[raw]).upper()
    elif f"{raw}.US" in alias:
        raw = str(alias[f"{raw}.US"]).upper()
    return _normalize_symbol_code(raw.replace(".US", "") if raw.endswith(".US") else raw)


def desk_specialist_for_symbol(symbol: str) -> dict[str, Any] | None:
    """Return routed desk specialist model for a symbol, or None.

    Used by recommend_model / analysis / live_plan so TSLA→v65_spec_tsla,
    CRWV→v64_crwv_bounce, INFQ→IONQ specialist, etc.
    """
    code = resolve_desk_symbol(symbol)
    if not code:
        return None
    routing = load_desk_routing()
    by_sym = routing.get("by_symbol") or {}
    row = by_sym.get(code)
    if not isinstance(row, dict):
        return None
    model = str(row.get("model") or "")
    if not model or not (MODELS_ROOT / model / "signal_engine.py").exists():
        return None
    return {
        "model": model,
        "code": code,
        "specialist": row.get("specialist"),
        "family": row.get("family"),
        "source_dir": row.get("source_dir"),
        "reason": (
            f"desk specialist for {code}"
            + (f" ({row.get('specialist')})" if row.get("specialist") else "")
        ),
        "source": "desk_specialist",
        "track": "specialist",
        "kind": engine_kind(model),
    }


def standard_equity_model() -> str:
    """Track B — normal bag models for symbols without a specialist.

    Prefers DESK_ROUTING.fallback_equity (v39d_confluence) when that engine
    exists, else WINNER.json / DEFAULT_MODEL.
    """
    routing = load_desk_routing()
    for key in ("fallback_equity", "fallback_equity_alt"):
        cand = routing.get(key)
        if cand and (MODELS_ROOT / str(cand) / "signal_engine.py").exists():
            return str(cand)
    return equity_default_model()


def equity_model_for_symbol(
    symbol: str | None = None,
    *,
    horizon: str | None = None,
) -> str:
    """Best-model router for a symbol (specialist vs standard competition).

    Delegates to ``route_best_model`` so analysis / live always get the winner
    of specialist DNA vs bag champions (v39d etc.), not a hard-coded track.
    """
    if symbol:
        hit = route_best_model(symbol, horizon=horizon)
        if hit and hit.get("model"):
            return str(hit["model"])
    return standard_equity_model()


# Standard bag models always considered by the best-model router.
_STANDARD_CANDIDATES: tuple[str, ...] = (
    "v39d_confluence",
    "v39b_live_adapt",
    "v63_spy_prune",
    "v50_high_win_rate",
    "v71_live_confidence",
    "v72_dual_sleeve",
)

# Horizon-aware base priors for standards (before evidence blend).
_STANDARD_PRIORS: dict[str, float] = {
    "v39d_confluence": 0.74,
    "v39b_live_adapt": 0.68,
    "v72_dual_sleeve": 0.72,
    "v71_live_confidence": 0.70,
    "v50_high_win_rate": 0.69,
    "v63_spy_prune": 0.66,
}


def _router_confidence(
    best: dict[str, Any],
    runner_up: dict[str, Any] | None,
    *,
    horizon: str,
    ranker_relative: bool = False,
) -> dict[str, Any]:
    """How much we trust the router pick (not trade ENTER confidence)."""
    score = float(best.get("final_score") or 0.0)
    gap = score - float(runner_up.get("final_score") or 0.0) if runner_up else score
    has_hist = best.get("hist_score") is not None
    has_ranker = best.get("ranker_score") is not None
    evidence_n = sum(1 for flag in (has_hist, has_ranker) if flag)
    # Base from score level + margin + evidence depth.
    conf = 0.35 + 0.35 * min(max(score, 0.0), 1.0) + 0.20 * min(max(gap, 0.0) / 0.12, 1.0)
    conf += 0.05 * evidence_n
    conf *= 0.55 + 0.45 * model_horizon_affinity(str(best.get("model") or ""), horizon)
    if ranker_relative and has_ranker:
        # Ranker only said "best of a weak set" — discount trust.
        conf *= 0.85
    if not has_hist and not has_ranker:
        conf *= 0.80  # prior-only pick
    conf = max(0.05, min(0.98, conf))
    band = "high" if conf >= 0.70 else "medium" if conf >= 0.50 else "low"
    return {
        "value": round(conf, 4),
        "band": band,
        "score_gap": round(gap, 4),
        "evidence_depth": evidence_n,
        "horizon": horizon,
        "note": (
            "router trust for model selection — not trade ENTER probability"
        ),
    }


def route_best_model(
    symbol: str,
    *,
    desk_only: bool = True,
    horizon: str | None = None,
) -> dict[str, Any]:
    """Compete specialist vs standard models; return the best for ``symbol``.

    This is the legitimate router: specialists are *candidates*, not automatic
    winners. Generics (v39d etc.) can win when evidence favors them.

    Score = blend of:
      - prior (specialist DNA prior, standard champion prior)
      - historical per-symbol card score when present
      - fresh symbol_ranker score when present
      - horizon affinity (day / swing / position)
    """
    h = normalize_horizon(horizon)
    code = resolve_desk_symbol(symbol) or _normalize_symbol_code(symbol)
    desk = set(list_desk_engines()) if desk_only else None

    def _allowed(model: str) -> bool:
        if not (MODELS_ROOT / model / "signal_engine.py").exists():
            return False
        if desk is not None and model not in desk and not is_desk_engine(model):
            return False
        return True

    # Build candidate set: specialist (if any) + standards + ranker top.
    candidates: dict[str, dict[str, Any]] = {}

    def _add(model: str, *, prior: float, kind: str, meta: dict[str, Any] | None = None) -> None:
        if not model or model in candidates or not _allowed(model):
            return
        candidates[model] = {
            "model": model,
            "prior": float(prior),
            "kind": kind,
            "meta": meta or {},
            "hist_score": None,
            "ranker_score": None,
            "horizon_affinity": model_horizon_affinity(model, h),
            "final_score": float(prior),
            "evidence": [],
        }

    spec = desk_specialist_for_symbol(code) if code else None
    if spec:
        # v39d-based specialists: high prior only when bakeoff multi-locked DNA edge.
        # Otherwise near champion so bag models can still win on evidence.
        mid = str(spec["model"])
        routing = load_desk_routing()
        row = (routing.get("by_symbol") or {}).get(code) or {}
        dna_edge = bool(row.get("bakeoff_promoted") or row.get("dna_edge"))
        if mid == "v39d_confluence":
            prior_s = 0.74
        elif mid.startswith("v65_spec_") or mid.startswith("v64_"):
            prior_s = 0.80 if dna_edge else 0.73
        else:
            prior_s = 0.76
        _add(
            mid,
            prior=prior_s,
            kind="specialist",
            meta={
                "specialist": spec.get("specialist"),
                "family": spec.get("family") or row.get("family"),
                "code": spec.get("code"),
                "dna": row.get("dna"),
                "dna_edge": dna_edge,
            },
        )
        if mid in candidates:
            candidates[mid]["evidence"].append(
                f"desk specialist prior {prior_s:.2f}"
                + (" (dna edge)" if dna_edge else " (v39d-based)")
            )
        elif (MODELS_ROOT / mid / "signal_engine.py").exists():
            candidates[mid] = {
                "model": mid,
                "prior": prior_s,
                "kind": "specialist",
                "meta": {
                    "specialist": spec.get("specialist"),
                    "family": spec.get("family"),
                    "code": spec.get("code"),
                },
                "hist_score": None,
                "ranker_score": None,
                "horizon_affinity": model_horizon_affinity(mid, h),
                "final_score": prior_s,
                "evidence": [f"desk specialist prior {prior_s:.2f} (force-added)"],
            }
    else:
        # Unmapped symbol → universal family-DNA engine as a *candidate*
        # (not auto-win). Prior is softer than named specialists.
        uni = "v67_universal_specialist"
        fam_meta: dict[str, Any] = {}
        prior_u = 0.58
        try:
            from specialist_factory import classify_symbol  # type: ignore

            info = classify_symbol(code or "")
            fam_meta = {
                "specialist": info.get("specialist"),
                "family": info.get("family"),
                "code": info.get("code") or code,
            }
            prior_u = float(info.get("prior") or 0.55)
        except Exception:
            fam_meta = {"family": "default_equity", "code": code}
        _add(uni, prior=prior_u, kind="specialist", meta=fam_meta)
        if uni in candidates:
            candidates[uni]["evidence"].append(
                f"universal family DNA prior {prior_u:.2f}"
                + (f" ({fam_meta.get('family')})" if fam_meta.get("family") else "")
            )

    for m in _STANDARD_CANDIDATES:
        prior = float(_STANDARD_PRIORS.get(m, 0.66))
        if m == standard_equity_model():
            prior = max(prior, 0.74)
        # Day book: lift high-WR / dual-sleeve; position book: lift confluence / high WR.
        if h == "day" and m in ("v71_live_confidence", "v72_dual_sleeve"):
            prior = max(prior, 0.73)
        if h == "position" and m in ("v39d_confluence", "v50_high_win_rate"):
            prior = max(prior, 0.73)
        if h == "swing" and m == "v50_high_win_rate":
            prior = max(prior, 0.71)
        _add(m, prior=prior, kind="standard")
        if m in candidates:
            candidates[m]["evidence"].append(f"standard prior {candidates[m]['prior']:.2f}")

    # Historical per-symbol metrics from model cards.
    for card in all_model_cards(engines_only=True):
        model = str(card.get("model") or "")
        if not model or not _allowed(model):
            continue
        row = (card.get("per_symbol") or {}).get(code) if code else None
        if not isinstance(row, dict):
            continue
        wr = row.get("win_rate")
        sh = row.get("sharpe")
        if wr is None and sh is None:
            continue
        hist = score_metrics(
            _safe_float(wr),
            _safe_float(sh),
            _safe_float(row.get("profit_factor"), 1.0),
            _safe_float(row.get("max_drawdown")),
        )
        if model not in candidates:
            _add(model, prior=0.55, kind="historical")
        if model in candidates:
            candidates[model]["hist_score"] = hist
            candidates[model]["evidence"].append(f"hist score {hist:.3f}")
            if row.get("win_rate") is not None:
                candidates[model]["win_rate"] = row.get("win_rate")
            if row.get("sharpe") is not None:
                candidates[model]["sharpe"] = row.get("sharpe")

    # Fresh symbol ranker (strong evidence when present; relative ok if all weak).
    ranker = ranker_best_model(code, desk_only=desk_only, horizon=h) if code else None
    ranker_relative = bool(ranker and ranker.get("relative_only"))
    if ranker and ranker.get("model"):
        rm = str(ranker["model"])
        rscore = float(ranker.get("score") or 0.0)
        # Absolute positive scores map to [0,1]; relative (all-negative) still
        # contributes but is capped lower so priors/hist can override weak wins.
        if rscore > 0:
            r_norm = max(0.0, min(rscore / 2.0, 1.0)) if rscore > 1.0 else max(0.0, min(rscore, 1.0))
        else:
            # Softmap negative utility into (0.25, 0.55] so best-of-weak still votes.
            r_norm = max(0.25, min(0.55, 0.55 + rscore * 0.15))
        if ranker_relative:
            r_norm *= 0.85
        if rm not in candidates:
            _add(rm, prior=0.60, kind="ranker")
        if rm in candidates:
            candidates[rm]["ranker_score"] = r_norm
            tag = "relative" if ranker_relative else "absolute"
            candidates[rm]["evidence"].append(f"symbol_ranker({tag}/{h}) {r_norm:.3f}")
            candidates[rm]["win_rate"] = ranker.get("win_rate")
            candidates[rm]["sharpe"] = ranker.get("sharpe")

    if not candidates:
        std = standard_equity_model()
        return {
            "model": std,
            "reason": f"no candidates; standard {std}",
            "source": "best_router",
            "track": "standard",
            "code": code or None,
            "score": None,
            "horizon": h,
            "router_confidence": {
                "value": 0.2,
                "band": "low",
                "score_gap": 0.0,
                "evidence_depth": 0,
                "horizon": h,
                "note": "no candidates",
            },
            "candidates": [],
            "kind": engine_kind(std),
        }

    # Final blend with horizon affinity.
    scored_rows: list[dict[str, Any]] = []
    for model, c in candidates.items():
        prior = float(c["prior"])
        hist = c.get("hist_score")
        ranker_s = c.get("ranker_score")
        aff = float(c.get("horizon_affinity") or model_horizon_affinity(model, h))
        if hist is not None and ranker_s is not None:
            base = 0.25 * prior + 0.35 * float(hist) + 0.40 * float(ranker_s)
        elif hist is not None:
            base = 0.40 * prior + 0.60 * float(hist)
        elif ranker_s is not None:
            base = 0.35 * prior + 0.65 * float(ranker_s)
        else:
            base = prior
        # Horizon affinity reweights: strong mismatch cannot win on prior alone.
        final = base * (0.55 + 0.45 * aff)
        # Tiny tie-break: prefer specialist DNA when essentially tied.
        if c["kind"] == "specialist":
            final += 0.01
        c["horizon_affinity"] = round(aff, 4)
        c["final_score"] = round(final, 4)
        scored_rows.append(c)

    scored_rows.sort(key=lambda r: r["final_score"], reverse=True)
    best = scored_rows[0]
    runner_up = scored_rows[1] if len(scored_rows) > 1 else None
    rconf = _router_confidence(best, runner_up, horizon=h, ranker_relative=ranker_relative)
    reason = (
        f"best_router[{h}]: {best['model']} score={best['final_score']:.3f} "
        f"({best['kind']}"
        + (f", beats {runner_up['model']} {runner_up['final_score']:.3f}" if runner_up else "")
        + f", aff={best.get('horizon_affinity', 0):.2f}"
        + f", router_conf={rconf['value']:.2f}/{rconf['band']}"
        + ")"
    )
    if best.get("evidence"):
        reason += " | " + "; ".join(best["evidence"][:3])

    return {
        "model": best["model"],
        "reason": reason,
        "source": "best_router",
        "track": "specialist" if best["kind"] == "specialist" else "standard",
        "kind": engine_kind(best["model"]),
        "code": code or None,
        "score": best["final_score"],
        "horizon": h,
        "horizon_affinity": best.get("horizon_affinity"),
        "router_confidence": rconf,
        "win_rate": best.get("win_rate"),
        "sharpe": best.get("sharpe"),
        "specialist": (best.get("meta") or {}).get("specialist"),
        "family": (best.get("meta") or {}).get("family"),
        "candidates": [
            {
                "model": r["model"],
                "kind": r["kind"],
                "prior": r["prior"],
                "hist_score": r.get("hist_score"),
                "ranker_score": r.get("ranker_score"),
                "horizon_affinity": r.get("horizon_affinity"),
                "final_score": r["final_score"],
            }
            for r in scored_rows[:8]
        ],
    }

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


def engine_kind(model: str) -> str:
    """Classify engine for desk routing: equity | options | other.

    Equity engines either expose classic desk helpers (_resample_ohlcv + profile)
    or implement SignalEngine.generate (trade_desk falls back to helpers and
    uses generate() for the live long/flat decision). Options wrappers load an
    equity child via equity_engine / _equity_engine_path or carry ``opts`` in
    the version id.
    """
    path = MODELS_ROOT / model / "signal_engine.py"
    if not path.exists():
        return "other"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "other"

    has_resample = "def _resample_ohlcv" in text
    has_profile = (
        "def _prior_session_profile" in text or "_prior_session_profile" in text
    )
    has_classic_desk = has_resample and has_profile
    has_generate = "class SignalEngine" in text and "def generate" in text
    is_opts_id = "opts" in model
    is_opts_wrapper = (
        ("equity_engine" in text or "_equity_engine_path" in text)
        and not has_classic_desk
    )

    if is_opts_id or is_opts_wrapper:
        return "options"
    if has_classic_desk or has_generate:
        return "equity"
    return "other"


def is_desk_engine(model: str) -> bool:
    """True when Analyze/Live can run this model (classic helpers or generate)."""
    return engine_kind(model) == "equity"


# Featured recent research models surfaced near the top of desk pickers.
FEATURED_DESK_MODELS: tuple[str, ...] = (
    # Meta-router (picks best child per symbol)
    "v66_best_router",
    "v70_self_evolving_router",
    # Universal family-DNA specialist (any symbol)
    "v67_universal_specialist",
    # Track B — standard bag champions + live sleeves
    "v72_dual_sleeve",
    "v71_live_confidence",
    "v39d_confluence",
    "v39b_live_adapt",
    "v63_spy_prune",
    "v50_high_win_rate",
    # Track A — multi + core specialists
    "v65_desk_specialists",
    "v65_spec_tsla",
    "v65_spec_mu",
    "v65_spec_ionq",
    "v65_spec_mstr",
    "v65_spec_coin",
    "v65_spec_meta",
    "v65_spec_goog",
    "v65_spec_nvda",
    "v65_spec_apld",
    "v64_crwv_bounce",
    # Research / alt sleeves
    "v51_vpa_reflexivity",
    "v60_microstructure",
    "v61_institutional_flow",
    "v48_regime_barbell",
    "v49_precision_trend",
    "v45_ultimate_rsi",
    "v41_ensemble_feedback",
)


def list_featured_desk_engines() -> list[str]:
    """Featured equity engines that currently exist and are desk-runnable."""
    desk = set(list_desk_engines())
    return [m for m in FEATURED_DESK_MODELS if m in desk]


def list_desk_engines() -> list[str]:
    """Equity engines safe for --model auto on the trade desk."""
    return [m for m in list_engine_models() if is_desk_engine(m)]


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


def _live_factor(live_n: int, live_avg_R: float | None) -> float:
    """Bounded nudge from live paper-trading outcomes; never dominates the backtest score."""
    if live_n < 10 or live_avg_R is None:
        return 1.0  # not enough live evidence to move the rank
    r = max(-0.6, min(0.6, float(live_avg_R)))
    return 1.0 + 0.25 * r  # bounded [0.85, 1.15]


def _live_stats_by_model() -> dict[str, dict[str, Any]]:
    """Aggregate paper_ledger.compute_stats() per-(model,symbol) buckets up to per-model.

    Import-safe: returns {} (no live data) if the ledger file is missing/corrupt
    or paper_ledger fails to import, so ranking never breaks without it.
    """
    try:
        import paper_ledger as pl

        stats = pl.compute_stats()
    except Exception:
        return {}

    agg: dict[str, dict[str, Any]] = {}
    for row in stats.get("rows") or []:
        model = str(row.get("model") or "")
        if not model:
            continue
        a = agg.setdefault(model, {"n": 0, "wins": 0, "sum_R": 0.0, "total_pnl": 0.0})
        a["n"] += int(row.get("n") or 0)
        a["wins"] += int(row.get("wins") or 0)
        a["sum_R"] += _safe_float(row.get("sum_R"))
        a["total_pnl"] += _safe_float(row.get("total_pnl"))

    out: dict[str, dict[str, Any]] = {}
    for model, a in agg.items():
        n = a["n"]
        out[model] = {
            "live_n": n,
            # Trade-weighted (sum / n), not a naive mean of per-symbol bucket
            # averages -- symbols with more closed trades count proportionally more.
            "live_wr": (a["wins"] / n) if n else None,
            "live_avg_R": (a["sum_R"] / n) if n else None,
            "live_pnl": round(a["total_pnl"], 4) if n else None,
        }
    return out


def rank_models(engines_only: bool = False) -> list[dict[str, Any]]:
    """Overall ranking by portfolio metrics, blended with live paper-trading outcomes.

    Live results can only nudge the rank (bounded ±15%, see `_live_factor`) and are
    gated on >=10 closed trades before they influence anything; `score` (pure
    backtest) is kept unchanged alongside the new `blended_score` used for sorting.
    """
    live_by_model = _live_stats_by_model()
    ranked = []
    for card in all_model_cards(engines_only=engines_only):
        port = card.get("portfolio") or {}
        if not port:
            continue
        wr = _safe_float(port.get("win_rate"))
        sh = _safe_float(port.get("sharpe"))
        pf = _safe_float(port.get("profit_factor"), 1.0)
        dd = _safe_float(port.get("max_drawdown"))
        score = round(score_metrics(wr, sh, pf, dd), 4)

        live = live_by_model.get(card["model"]) or {}
        live_n = int(live.get("live_n") or 0)
        live_wr = live.get("live_wr")
        live_avg_R = live.get("live_avg_R")
        live_pnl = live.get("live_pnl")
        if live_n == 0:
            live_status = "none"
        elif live_n < 10:
            live_status = "provisional"
        elif live_avg_R is not None and live_avg_R > 0:
            live_status = "confirming"
        else:
            live_status = "degrading"
        blended_score = round(score * _live_factor(live_n, live_avg_R), 4)

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
                "score": score,
                "source": card.get("source"),
                "live_n": live_n,
                "live_wr": live_wr,
                "live_avg_R": live_avg_R,
                "live_pnl": live_pnl,
                "live_status": live_status,
                "blended_score": blended_score,
            }
        )
    ranked.sort(key=lambda r: r["blended_score"], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def rank_models_for_symbol(symbol: str, engines_only: bool = False) -> list[dict[str, Any]]:
    """Rank models by historical performance on one symbol.

    Desk specialist for the symbol is pinned to rank #1 when present so analysis
    surfaces the routed specialist even before a bag backtest score exists.
    """
    code = resolve_desk_symbol(symbol) or _normalize_symbol_code(symbol)
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

    # Pin desk specialist to the front for analysis / auto.
    desk = desk_specialist_for_symbol(code)
    if desk:
        pinned = {
            "model": desk["model"],
            "has_engine": True,
            "code": code,
            "win_rate": None,
            "sharpe": None,
            "profit_factor": None,
            "max_drawdown": None,
            "total_return": None,
            "trade_count": None,
            "score": 1.0,  # display pin; not a backtest claim
            "source": "desk_specialist",
            "specialist": desk.get("specialist"),
            "family": desk.get("family"),
            "routed": True,
        }
        ranked = [r for r in ranked if r.get("model") != desk["model"]]
        ranked.insert(0, pinned)

    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def load_symbol_ranker(
    symbol: str,
    *,
    horizon: str | None = None,
) -> dict[str, Any] | None:
    """Read RANKER artifact for a symbol (horizon-specific when present).

    Lookup order for horizon H:
      1. runs/symbol_ranker/<SYM>/RANKER_<H>.json
      2. runs/symbol_ranker/<SYM>/RANKER.json  (legacy / swing default)
    """
    sym = str(symbol).strip().upper().replace(".US", "")
    h = normalize_horizon(horizon)
    candidates = [
        RANKER_ROOT / sym / f"RANKER_{h}.json",
        RANKER_ROOT / sym / "RANKER.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            data.setdefault("horizon", h if path.name != "RANKER.json" else data.get("horizon") or "swing")
            return data
    return None


def ranker_best_model(
    symbol: str,
    *,
    desk_only: bool = True,
    horizon: str | None = None,
) -> dict[str, Any] | None:
    """Fresh (≤7d) RANKER top desk-eligible row, or None.

    Prefers absolute positive-score winners. If every score is ≤0 (common on
    single-name 1D windows), falls back to the *relative* best among ok rows
    with RESEARCH/CLAIM sample size — marked ``relative_only=True`` so the
    router can discount trust.
    """
    from datetime import datetime, timezone

    h = normalize_horizon(horizon)
    art = load_symbol_ranker(symbol, horizon=h)
    if not art:
        return None
    asof = art.get("asof")
    if not asof:
        return None
    try:
        dt = datetime.fromisoformat(str(asof).replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400.0
    except Exception:
        return None
    if age_days > RANKER_MAX_AGE_DAYS:
        return None

    eligible: list[dict[str, Any]] = []
    for row in art.get("rows") or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "ok":
            continue
        if row.get("claim_level") not in ("RESEARCH", "CLAIM", "THIN"):
            continue
        if desk_only and not row.get("desk_runnable"):
            continue
        # Skip error-only / empty trade shells.
        n = int(row.get("trade_count") or 0)
        if n <= 0 and float(row.get("reliability") or 0) <= 0:
            continue
        eligible.append(row)

    if not eligible:
        return None

    # Prefer absolute positive scores first.
    positive = [
        r
        for r in eligible
        if float(r.get("score") or 0) > 0 and r.get("claim_level") in ("RESEARCH", "CLAIM")
    ]
    if positive:
        pool = positive
        relative_only = False
    else:
        # Relative best of a weak set: prefer RESEARCH/CLAIM over THIN so a
        # 8-trade THIN curiosity does not outrank a fuller RESEARCH window.
        solid = [r for r in eligible if r.get("claim_level") in ("RESEARCH", "CLAIM")]
        pool = solid if solid else [r for r in eligible if r.get("claim_level") == "THIN"]
        relative_only = True
    if not pool:
        return None

    champions = set(_STANDARD_CANDIDATES)

    def _rank_key(r: dict[str, Any]) -> tuple:
        claim_rank = 0 if r.get("claim_level") == "CLAIM" else 1 if r.get("claim_level") == "RESEARCH" else 2
        champ = 0 if r.get("model") in champions else 1
        return (
            claim_rank,
            champ,
            -float(r.get("score") or -999),
            -float(r.get("reliability") or 0),
            -(int(r.get("trade_count") or 0)),
        )

    pool.sort(key=_rank_key)
    row = pool[0]
    return {
        "model": row["model"],
        "score": float(row.get("score") or 0),
        "win_rate": row.get("win_rate"),
        "sharpe": row.get("sharpe"),
        "code": art.get("code") or f"{str(symbol).upper().replace('.US', '')}.US",
        "asof": str(asof),
        "claim_level": row.get("claim_level"),
        "horizon": art.get("horizon") or h,
        "relative_only": relative_only,
        "reliability": row.get("reliability"),
        "trade_count": row.get("trade_count"),
    }


def recommend_model(
    symbol: str | None = None,
    *,
    desk_only: bool = True,
    horizon: str | None = None,
) -> dict[str, Any]:
    """Pick best runnable model overall, or best for a symbol.

    Per-symbol: uses ``route_best_model`` (competitive router — specialist DNA
    vs v39d/generics). Overall (no symbol): standard equity champion.
    """
    desk = set(list_desk_engines()) if desk_only else None
    h = normalize_horizon(horizon)

    def _ok(row: dict[str, Any]) -> bool:
        if not row.get("has_engine"):
            return False
        if desk is not None and row["model"] not in desk:
            return False
        return True

    if symbol:
        routed = route_best_model(symbol, desk_only=desk_only, horizon=h)
        # Prefer returning the child model (what analysis should run), not the
        # meta engine id — callers want the actual signal DNA.
        return routed

    # No symbol → standard bag champion (or best portfolio engine).
    standard = standard_equity_model()
    if (desk is None or standard in desk or is_desk_engine(standard)) and (
        MODELS_ROOT / standard / "signal_engine.py"
    ).exists():
        return {
            "model": standard,
            "reason": f"standard equity model {standard}",
            "score": None,
            "win_rate": None,
            "sharpe": None,
            "kind": engine_kind(standard),
            "source": "standard",
            "track": "standard",
        }

    overall = rank_models(engines_only=True)
    for top in overall:
        if _ok(top):
            return {
                "model": top["model"],
                "reason": "best portfolio score among engines",
                "score": top["score"],
                "win_rate": top["win_rate"],
                "sharpe": top["sharpe"],
                "kind": engine_kind(top["model"]),
                "source": "portfolio_rank",
                "track": "standard",
                "horizon": h,
            }
    fallback = equity_default_model()
    if desk is not None and fallback not in desk:
        fallback = next(iter(desk), DEFAULT_MODEL) if desk else DEFAULT_MODEL
    return {
        "model": fallback,
        "reason": "fallback default",
        "score": None,
        "win_rate": None,
        "sharpe": None,
        "kind": engine_kind(fallback),
        "source": "fallback",
        "track": "standard",
        "horizon": h,
    }


def select_model_for_confidence(
    symbol: str,
    *,
    horizon: str | None = None,
    desk_only: bool = True,
    max_probe: int = 4,
    probe_fn: Any | None = None,
) -> dict[str, Any]:
    """Pick the model expected to yield the highest live confidence for a symbol.

    1. Route horizon-aware candidates via ``route_best_model``.
    2. Optionally probe top-N models for live raw probability / setup_ok.
    3. Return the max-confidence model with a full audit trail.

    ``probe_fn(symbol, model) -> dict`` should match live_plan.try_model_confidence
    shape (ok, raw_probability, setup_ok, ...). When omitted, uses router scores
    only (fast path for scans).
    """
    h = normalize_horizon(horizon)
    routed = route_best_model(symbol, desk_only=desk_only, horizon=h)
    cands = [str(routed.get("model") or "")]
    for row in routed.get("candidates") or []:
        mid = str(row.get("model") or "")
        if mid and mid not in cands:
            cands.append(mid)
    cands = [m for m in cands if m][: max(1, int(max_probe))]

    probes: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None

    for mid in cands:
        aff = model_horizon_affinity(mid, h)
        row_base = next(
            (r for r in (routed.get("candidates") or []) if r.get("model") == mid),
            {"final_score": routed.get("score"), "model": mid},
        )
        probe: dict[str, Any] = {
            "model": mid,
            "horizon_affinity": aff,
            "router_score": row_base.get("final_score"),
            "probed": False,
        }
        if probe_fn is not None:
            try:
                info = probe_fn(symbol, mid) or {}
            except Exception as exc:  # noqa: BLE001
                info = {"ok": False, "error": str(exc)}
            probe["probed"] = True
            probe["ok"] = bool(info.get("ok"))
            probe["raw_probability"] = info.get("raw_probability")
            probe["setup_ok"] = info.get("setup_ok")
            probe["action_hint"] = info.get("action_hint")
            probe["error"] = info.get("error")
            raw = info.get("raw_probability")
            try:
                raw_f = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                raw_f = None
            if info.get("ok") and raw_f is not None:
                # Confidence score for ranking: calibrated-ish raw × affinity, setup boost.
                conf_score = raw_f * (0.60 + 0.40 * aff)
                if info.get("setup_ok"):
                    conf_score += 0.04
            else:
                conf_score = float(row_base.get("final_score") or 0.0) * 0.5 * aff
        else:
            conf_score = float(row_base.get("final_score") or 0.0) * (0.55 + 0.45 * aff)
            probe["ok"] = True
        probe["confidence_score"] = round(conf_score, 4)
        probes.append(probe)
        if best is None or conf_score > float(best.get("confidence_score") or -1):
            best = probe

    winner_model = (best or {}).get("model") or routed.get("model")
    winner_probe = best or {"model": winner_model, "confidence_score": 0.0}
    # Reuse router_confidence as floor; lift when probe found high raw+setup.
    rconf = dict(routed.get("router_confidence") or {})
    raw_w = winner_probe.get("raw_probability")
    try:
        raw_w_f = float(raw_w) if raw_w is not None else None
    except (TypeError, ValueError):
        raw_w_f = None
    if raw_w_f is not None and winner_probe.get("setup_ok"):
        lifted = max(float(rconf.get("value") or 0.0), min(0.95, 0.40 + 0.55 * raw_w_f))
        rconf["value"] = round(lifted, 4)
        rconf["band"] = "high" if lifted >= 0.70 else "medium" if lifted >= 0.50 else "low"
        rconf["source"] = "live_probe"
    else:
        rconf.setdefault("source", "router")

    return {
        "model": winner_model,
        "reason": (
            f"confidence_ranker[{h}]: {winner_model} "
            f"conf_score={winner_probe.get('confidence_score')} "
            f"raw={raw_w} setup_ok={winner_probe.get('setup_ok')}"
        ),
        "source": "confidence_ranker",
        "horizon": h,
        "router": routed,
        "router_confidence": rconf,
        "probes": probes,
        "score": winner_probe.get("confidence_score"),
        "raw_probability": raw_w,
        "setup_ok": winner_probe.get("setup_ok"),
        "kind": engine_kind(str(winner_model)),
        "track": routed.get("track"),
        "code": routed.get("code"),
        "specialist": routed.get("specialist"),
        "family": routed.get("family"),
        "candidates": routed.get("candidates") or [],
    }


def options_default_model() -> str:
    """OOS-elected options default; falls back to OPTIONS_DEFAULT_MODEL constant."""
    try:
        if OPTIONS_WINNER_PATH.exists():
            d = json.loads(OPTIONS_WINNER_PATH.read_text())
            w = d.get("winner") or d.get("champion_oos", {}).get("model_dir")
            if w and (MODELS_ROOT / w / "signal_engine.py").exists():
                return str(w)
    except Exception:
        pass
    return OPTIONS_DEFAULT_MODEL


def options_winner_card() -> dict:
    """Full OPTIONS_WINNER.json for API / desk."""
    if OPTIONS_WINNER_PATH.exists():
        return json.loads(OPTIONS_WINNER_PATH.read_text())
    return {"winner": OPTIONS_DEFAULT_MODEL, "note": "OPTIONS_WINNER.json missing"}
