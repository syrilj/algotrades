"""Pure non-identity blend helpers for Trump-window beat attempt.

All operations are causal when inputs are lagged/point-in-time teacher targets
and risk scores already computed without look-ahead.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def agree_boost(
    primary: pd.Series,
    secondary: pd.Series,
    *,
    boost: float = 1.20,
    entry_thresh: float = 0.5,
    max_scale: float = 1.35,
) -> pd.Series:
    """Scale primary up when secondary also long (disagreement → no boost)."""
    p = primary.astype(float).fillna(0.0)
    s = secondary.reindex(p.index).fillna(0.0).astype(float)
    agree = (p > entry_thresh) & (s > entry_thresh)
    mult = pd.Series(1.0, index=p.index, dtype=float)
    mult = mult.where(~agree, float(boost))
    out = (p * mult).clip(upper=float(max_scale))
    # Preserve flat zeros exactly
    out = out.where(p.abs() > 1e-12, 0.0)
    return out.astype(float)


def risk_on_scale(
    primary: pd.Series,
    risk_score: pd.Series,
    *,
    max_boost: float = 0.25,
    max_scale: float = 1.35,
    risk_floor: float = 0.0,
) -> pd.Series:
    """Size *up* when risk is calm; never above max_scale. Elevated → ~1.0×.

    mult = 1 + max_boost * (1 - risk_score), clipped to [1, 1+max_boost].
    Optional risk_floor shrinks only when risk is extremely high (usually 0).
    """
    p = primary.astype(float).fillna(0.0)
    r = risk_score.reindex(p.index).ffill().fillna(0.0).clip(0.0, 1.0)
    mult = 1.0 + float(max_boost) * (1.0 - r)
    if risk_floor > 0:
        # soft shrink only near full risk
        mult = mult * (1.0 - float(risk_floor) * r)
    mult = mult.clip(lower=1.0 - float(risk_floor), upper=1.0 + float(max_boost))
    out = (p * mult).clip(upper=float(max_scale))
    out = out.where(p.abs() > 1e-12, 0.0)
    return out.astype(float)


def union_calm(
    primary: pd.Series,
    secondary: pd.Series,
    risk_score: pd.Series,
    *,
    calm_threshold: float = 0.35,
    secondary_scale: float = 0.85,
    max_scale: float = 1.25,
    entry_thresh: float = 0.5,
) -> pd.Series:
    """Keep primary; when calm, fill gaps with scaled secondary longs.

    Non-identity: secondary-only bars can become non-zero under calm risk.
    """
    p = primary.astype(float).fillna(0.0)
    s = secondary.reindex(p.index).fillna(0.0).astype(float)
    r = risk_score.reindex(p.index).ffill().fillna(0.0).clip(0.0, 1.0)
    calm = r <= float(calm_threshold)
    primary_flat = p <= entry_thresh
    fill = calm & primary_flat & (s > entry_thresh)
    out = p.copy()
    out = out.where(~fill, s * float(secondary_scale))
    # When both long and calm, mild boost toward max of the two
    both = calm & (p > entry_thresh) & (s > entry_thresh)
    out = out.where(~both, np.maximum(p, s) * 1.05)
    return out.clip(upper=float(max_scale)).astype(float)


def pick_leader(
    primary: pd.Series,
    secondary: pd.Series,
    close: pd.Series,
    *,
    lookback: int = 40,
    forward_proxy: int = 1,
) -> pd.Series:
    """Causal rolling-return leader pick between two teacher target series.

    For each bar t, score each teacher by the sum of lagged bar returns during
    bars where the teacher was long over the prior `lookback` bars (using only
    returns through t-1). Pick the teacher with higher score; ties → primary.
    """
    p = primary.astype(float).fillna(0.0)
    s = secondary.reindex(p.index).fillna(0.0).astype(float)
    px = close.reindex(p.index).astype(float)
    # lagged one-bar return (causal)
    ret = px.pct_change().shift(1).fillna(0.0)

    p_long = (p > 0.5).astype(float)
    s_long = (s > 0.5).astype(float)
    p_pnl = (ret * p_long).rolling(lookback, min_periods=max(5, lookback // 3)).sum()
    s_pnl = (ret * s_long).rolling(lookback, min_periods=max(5, lookback // 3)).sum()
    # lag the scores one more bar so the decision at t uses performance through t-1 only
    p_score = p_pnl.shift(1)
    s_score = s_pnl.shift(1)
    use_sec = (s_score > p_score).fillna(False)
    out = p.where(~use_sec, s)
    return out.astype(float)


def agree_boost_calm(
    primary: pd.Series,
    secondary: pd.Series,
    risk_score: pd.Series,
    *,
    boost: float = 1.20,
    calm_threshold: float = 0.40,
    elevated_threshold: float = 0.55,
    elevated_mult: float = 0.85,
    entry_thresh: float = 0.5,
    max_scale: float = 1.30,
) -> pd.Series:
    """Boost only when teachers agree *and* risk is calm; mild cut when elevated.

    Designed to lift return without letting portfolio DD run away.
    """
    p = primary.astype(float).fillna(0.0)
    s = secondary.reindex(p.index).fillna(0.0).astype(float)
    r = risk_score.reindex(p.index).ffill().fillna(0.0).clip(0.0, 1.0)
    agree = (p > entry_thresh) & (s > entry_thresh)
    calm = r <= float(calm_threshold)
    elevated = r >= float(elevated_threshold)
    mult = pd.Series(1.0, index=p.index, dtype=float)
    mult = mult.where(~(agree & calm), float(boost))
    mult = mult.where(~elevated, float(elevated_mult))
    out = (p * mult).clip(upper=float(max_scale))
    out = out.where(p.abs() > 1e-12, 0.0)
    return out.astype(float)


def leader_risk_on(
    primary: pd.Series,
    secondary: pd.Series,
    close: pd.Series,
    risk_score: pd.Series,
    *,
    lookback: int = 40,
    max_boost: float = 0.12,
    elevated_threshold: float = 0.55,
    elevated_mult: float = 0.90,
    max_scale: float = 1.25,
    symbol_scale: float = 1.0,
    symbol_cap: float | None = None,
) -> pd.Series:
    """Pick causal teacher leader, then mild risk-on / elevated cut.

    Optional per-symbol ``symbol_scale`` / ``symbol_cap`` let high-beta names
    be trimmed without a global position cap that crushes all sizes.
    """
    leader = pick_leader(primary, secondary, close, lookback=lookback)
    r = risk_score.reindex(leader.index).ffill().fillna(0.0).clip(0.0, 1.0)
    mult = 1.0 + float(max_boost) * (1.0 - r)
    mult = mult.where(r < float(elevated_threshold), float(elevated_mult))
    out = (leader.astype(float) * mult.astype(float)).clip(upper=float(max_scale))
    out = out * float(symbol_scale)
    if symbol_cap is not None and float(symbol_cap) > 0:
        out = out.clip(upper=float(symbol_cap))
    out = out.where(leader.abs() > 1e-12, 0.0)
    return out.astype(float)


def high_beta_guard(
    primary: pd.Series,
    risk_score: pd.Series,
    *,
    is_high_beta: bool,
    secondary: pd.Series | None = None,
    boost: float = 1.08,
    calm_threshold: float = 0.40,
    elevated_threshold: float = 0.50,
    high_beta_base: float = 0.92,
    high_beta_elevated: float = 0.55,
    core_elevated: float = 0.90,
    max_scale: float = 1.20,
    position_cap: float = 0.50,
    entry_thresh: float = 0.5,
) -> pd.Series:
    """Mild agree-boost on calm core names; hard-cut high-beta into elevated risk.

    Hypothesis: Trump-window portfolio DD is concentrated in high-beta names
    (e.g. IONQ) at the trough; reducing those sizes preserves MU/TSLA alpha
    while improving max DD enough to multi-lock with a small calm boost.
    """
    p = primary.astype(float).fillna(0.0)
    r = risk_score.reindex(p.index).ffill().fillna(0.0).clip(0.0, 1.0)
    mult = pd.Series(1.0, index=p.index, dtype=float)
    calm = r <= float(calm_threshold)
    elevated = r >= float(elevated_threshold)

    if secondary is not None:
        s = secondary.reindex(p.index).fillna(0.0).astype(float)
        agree = (p > entry_thresh) & (s > entry_thresh)
        if is_high_beta:
            # tiny agree boost only when calm
            mult = mult.where(~(agree & calm), float(min(boost, 1.05)))
        else:
            mult = mult.where(~(agree & calm), float(boost))

    if is_high_beta:
        mult = mult * float(high_beta_base)
        mult = mult.where(~elevated, float(high_beta_elevated))
    else:
        mult = mult.where(~elevated, float(core_elevated))

    out = (p * mult).clip(upper=float(max_scale))
    if position_cap is not None and position_cap > 0:
        out = out.clip(upper=float(position_cap))
    out = out.where(p.abs() > 1e-12, 0.0)
    return out.astype(float)


def inv_vol_scale(
    primary: pd.Series,
    close: pd.Series,
    *,
    lookback: int = 20,
    target_vol: float = 0.015,
    vol_floor: float = 0.004,
    min_mult: float = 0.45,
    max_mult: float = 1.25,
    position_cap: float = 0.55,
) -> pd.Series:
    """Inverse-vol scale using lagged returns (causal). High-vol names shrink."""
    p = primary.astype(float).fillna(0.0)
    px = close.reindex(p.index).astype(float)
    ret = px.pct_change().shift(1)
    vol = ret.rolling(int(lookback), min_periods=max(5, int(lookback) // 2)).std()
    vol = vol.clip(lower=float(vol_floor)).fillna(float(target_vol))
    mult = (float(target_vol) / vol).clip(float(min_mult), float(max_mult))
    out = (p * mult.astype(float)).clip(upper=float(position_cap))
    return out.where(p.abs() > 1e-12, 0.0).astype(float)


def name_dd_cut(
    primary: pd.Series,
    close: pd.Series,
    *,
    soft: float = -0.04,
    hard: float = -0.12,
    min_mult: float = 0.35,
    position_cap: float = 0.55,
) -> pd.Series:
    """Cut size as the *symbol* falls from its causal running peak."""
    p = primary.astype(float).fillna(0.0)
    px = close.reindex(p.index).astype(float)
    peak = px.cummax()
    dd = (px / peak.replace(0.0, np.nan) - 1.0).fillna(0.0)
    # dd ≤ 0; map soft→1, hard→min_mult
    soft = float(soft)
    hard = float(hard)
    if hard >= soft:
        hard = soft - 0.05
    x = (dd - soft) / (hard - soft)
    stress = x.clip(0.0, 1.0).fillna(0.0)
    mult = 1.0 - stress * (1.0 - float(min_mult))
    out = (p * mult.astype(float)).clip(upper=float(position_cap))
    return out.where(p.abs() > 1e-12, 0.0).astype(float)


def multi_lock_blend(
    primary: pd.Series,
    close: pd.Series,
    *,
    secondary: pd.Series | None = None,
    risk_score: pd.Series | None = None,
    boost: float = 1.06,
    entry_thresh: float = 0.5,
    lookback: int = 20,
    target_vol: float = 0.014,
    vol_floor: float = 0.004,
    min_mult: float = 0.50,
    max_mult: float = 1.15,
    dd_soft: float = -0.05,
    dd_hard: float = -0.14,
    dd_min_mult: float = 0.40,
    position_cap: float = 0.42,
    calm_threshold: float = 0.45,
    use_inv_vol: bool = True,
    use_name_dd: bool = True,
    use_agree: bool = True,
) -> pd.Series:
    """Compose mild agree-boost + inv-vol + name-DD cut + hard position cap.

    Goal: lift return slightly while capping single-name blow-ups that set
    portfolio max DD on the Trump window.
    """
    p = primary.astype(float).fillna(0.0)
    out = p.copy()
    if use_agree and secondary is not None:
        s = secondary.reindex(p.index).fillna(0.0).astype(float)
        agree = (p > entry_thresh) & (s > entry_thresh)
        if risk_score is not None:
            r = risk_score.reindex(p.index).ffill().fillna(0.0)
            calm = r <= float(calm_threshold)
            agree = agree & calm
        mult = pd.Series(1.0, index=p.index)
        mult = mult.where(~agree, float(boost))
        out = out * mult
    if use_inv_vol and close is not None:
        # Apply inv-vol relative to current out magnitudes
        scaled = inv_vol_scale(
            out,
            close,
            lookback=lookback,
            target_vol=target_vol,
            vol_floor=vol_floor,
            min_mult=min_mult,
            max_mult=max_mult,
            position_cap=1e9,  # cap later
        )
        # Preserve zeros
        out = scaled
    if use_name_dd and close is not None:
        out = name_dd_cut(
            out,
            close,
            soft=dd_soft,
            hard=dd_hard,
            min_mult=dd_min_mult,
            position_cap=1e9,
        )
    out = out.clip(upper=float(position_cap))
    return out.where(p.abs() > 1e-12, 0.0).astype(float)


def blend_signals(
    mode: str,
    primary: pd.Series,
    secondary: pd.Series | None = None,
    risk_score: pd.Series | None = None,
    close: pd.Series | None = None,
    params: Mapping | None = None,
    code: str | None = None,
) -> pd.Series:
    """Dispatch blend mode."""
    params = dict(params or {})
    mode = str(mode).lower()
    if mode == "agree_boost":
        if secondary is None:
            return primary.astype(float)
        return agree_boost(
            primary,
            secondary,
            boost=float(params.get("boost", 1.20)),
            entry_thresh=float(params.get("entry_thresh", 0.5)),
            max_scale=float(params.get("max_scale", 1.35)),
        )
    if mode == "agree_boost_calm":
        if secondary is None or risk_score is None:
            return primary.astype(float)
        return agree_boost_calm(
            primary,
            secondary,
            risk_score,
            boost=float(params.get("boost", 1.20)),
            calm_threshold=float(params.get("calm_threshold", 0.40)),
            elevated_threshold=float(params.get("elevated_threshold", 0.55)),
            elevated_mult=float(params.get("elevated_mult", 0.85)),
            entry_thresh=float(params.get("entry_thresh", 0.5)),
            max_scale=float(params.get("max_scale", 1.30)),
        )
    if mode == "leader_risk_on":
        if secondary is None or close is None or risk_score is None:
            return primary.astype(float)
        scales = dict(params.get("symbol_scales") or {})
        caps = dict(params.get("symbol_caps") or {})
        code_key = str(code) if code else ""
        return leader_risk_on(
            primary,
            secondary,
            close,
            risk_score,
            lookback=int(params.get("lookback", 40)),
            max_boost=float(params.get("max_boost", 0.12)),
            elevated_threshold=float(params.get("elevated_threshold", 0.55)),
            elevated_mult=float(params.get("elevated_mult", 0.90)),
            max_scale=float(params.get("max_scale", 1.25)),
            symbol_scale=float(scales.get(code_key, params.get("default_symbol_scale", 1.0))),
            symbol_cap=(
                float(caps[code_key])
                if code_key in caps
                else (
                    float(params["default_symbol_cap"])
                    if params.get("default_symbol_cap") is not None
                    else None
                )
            ),
        )
    if mode == "high_beta_guard":
        if risk_score is None:
            return primary.astype(float)
        high_beta = set(params.get("high_beta_codes") or ["IONQ.US", "APLD.US", "TSLA.US"])
        return high_beta_guard(
            primary,
            risk_score,
            is_high_beta=(str(code) in high_beta) if code else False,
            secondary=secondary,
            boost=float(params.get("boost", 1.08)),
            calm_threshold=float(params.get("calm_threshold", 0.40)),
            elevated_threshold=float(params.get("elevated_threshold", 0.50)),
            high_beta_base=float(params.get("high_beta_base", 0.92)),
            high_beta_elevated=float(params.get("high_beta_elevated", 0.55)),
            core_elevated=float(params.get("core_elevated", 0.90)),
            max_scale=float(params.get("max_scale", 1.20)),
            position_cap=float(params.get("position_cap", 0.50)),
            entry_thresh=float(params.get("entry_thresh", 0.5)),
        )
    if mode == "risk_on_scale":
        if risk_score is None:
            return primary.astype(float)
        return risk_on_scale(
            primary,
            risk_score,
            max_boost=float(params.get("max_boost", 0.25)),
            max_scale=float(params.get("max_scale", 1.35)),
            risk_floor=float(params.get("risk_floor", 0.0)),
        )
    if mode == "union_calm":
        if secondary is None or risk_score is None:
            return primary.astype(float)
        return union_calm(
            primary,
            secondary,
            risk_score,
            calm_threshold=float(params.get("calm_threshold", 0.35)),
            secondary_scale=float(params.get("secondary_scale", 0.85)),
            max_scale=float(params.get("max_scale", 1.25)),
            entry_thresh=float(params.get("entry_thresh", 0.5)),
        )
    if mode == "pick_leader":
        if secondary is None or close is None:
            return primary.astype(float)
        return pick_leader(
            primary,
            secondary,
            close,
            lookback=int(params.get("lookback", 40)),
        )
    if mode == "agree_risk_on":
        # Composition: agree boost then mild risk-on scale
        mid = primary
        if secondary is not None:
            mid = agree_boost(
                primary,
                secondary,
                boost=float(params.get("boost", 1.15)),
                max_scale=float(params.get("max_scale", 1.40)),
            )
        if risk_score is not None:
            mid = risk_on_scale(
                mid,
                risk_score,
                max_boost=float(params.get("max_boost", 0.15)),
                max_scale=float(params.get("max_scale", 1.40)),
            )
        return mid.astype(float)
    if mode == "inv_vol":
        if close is None:
            return primary.astype(float)
        return inv_vol_scale(
            primary,
            close,
            lookback=int(params.get("lookback", 20)),
            target_vol=float(params.get("target_vol", 0.015)),
            vol_floor=float(params.get("vol_floor", 0.004)),
            min_mult=float(params.get("min_mult", 0.45)),
            max_mult=float(params.get("max_mult", 1.25)),
            position_cap=float(params.get("position_cap", 0.55)),
        )
    if mode == "name_dd_cut":
        if close is None:
            return primary.astype(float)
        mid = primary
        if secondary is not None and float(params.get("boost", 1.0)) > 1.0:
            mid = agree_boost(
                primary,
                secondary,
                boost=float(params.get("boost", 1.06)),
                max_scale=float(params.get("max_scale", 1.20)),
            )
        return name_dd_cut(
            mid,
            close,
            soft=float(params.get("dd_soft", -0.04)),
            hard=float(params.get("dd_hard", -0.12)),
            min_mult=float(params.get("dd_min_mult", 0.35)),
            position_cap=float(params.get("position_cap", 0.55)),
        )
    if mode in ("multi_lock", "multi_lock_blend", "mlock"):
        if close is None:
            return primary.astype(float)
        return multi_lock_blend(
            primary,
            close,
            secondary=secondary,
            risk_score=risk_score,
            boost=float(params.get("boost", 1.06)),
            entry_thresh=float(params.get("entry_thresh", 0.5)),
            lookback=int(params.get("lookback", 20)),
            target_vol=float(params.get("target_vol", 0.014)),
            vol_floor=float(params.get("vol_floor", 0.004)),
            min_mult=float(params.get("min_mult", 0.50)),
            max_mult=float(params.get("max_mult", 1.15)),
            dd_soft=float(params.get("dd_soft", -0.05)),
            dd_hard=float(params.get("dd_hard", -0.14)),
            dd_min_mult=float(params.get("dd_min_mult", 0.40)),
            position_cap=float(params.get("position_cap", 0.42)),
            calm_threshold=float(params.get("calm_threshold", 0.45)),
            use_inv_vol=bool(params.get("use_inv_vol", True)),
            use_name_dd=bool(params.get("use_name_dd", True)),
            use_agree=bool(params.get("use_agree", True)),
        )
    if mode == "cap_boost":
        # Mild agree boost + hard single-name cap (no inv-vol / name-dd)
        mid = primary.astype(float)
        if secondary is not None:
            mid = agree_boost(
                mid,
                secondary,
                boost=float(params.get("boost", 1.08)),
                max_scale=float(params.get("max_scale", 1.20)),
            )
        cap = float(params.get("position_cap", 0.40))
        mid = mid.clip(upper=cap)
        return mid.where(primary.astype(float).abs() > 1e-12, 0.0).astype(float)
    return primary.astype(float)
