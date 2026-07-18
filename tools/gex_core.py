"""Pure GEX math shared by tools/gamma_exposure.py CLI and services/market_runtime/squeeze."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm


def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    return float(norm.pdf(d1) / (S * sigma * sqrtT))


def gex_per_one_percent(gamma, contracts, spot: float):
    """Dollar gamma exposure for a one-percent underlying move."""
    value = gamma * contracts * 100.0 * float(spot) ** 2 * 0.01
    return float(value) if np.isscalar(value) else value


def price_consistency(
    trusted_spot: float,
    option_spot: float,
    max_divergence_pct: float = 5.0,
) -> dict:
    trusted = float(trusted_spot)
    option = float(option_spot)
    if not (np.isfinite(trusted) and trusted > 0 and np.isfinite(option) and option > 0):
        return {"consistent": False, "divergence_pct": float("inf")}
    divergence = abs(option - trusted) / trusted * 100.0
    return {
        "consistent": bool(divergence <= float(max_divergence_pct)),
        "divergence_pct": float(divergence),
    }


def max_pain(call_strikes: np.ndarray, call_oi: np.ndarray, put_strikes: np.ndarray, put_oi: np.ndarray, strikes: list[float]) -> float | None:
    if not strikes:
        return None
    strike_arr = np.array(strikes)
    pains = []
    for K in strike_arr:
        call_value = float(np.sum(np.maximum(0.0, K - call_strikes) * call_oi))
        put_value = float(np.sum(np.maximum(0.0, put_strikes - K) * put_oi))
        pains.append(call_value + put_value)
    return float(strike_arr[np.argmin(pains)])


def zero_gamma_flip(net_by_strike, spot: float):
    """Strike where cumulative net GEX crosses zero, nearest to spot (linear interp).

    Replaces cum.abs().idxmin(), which picked the near-zero low-strike tail
    (e.g. APLD flip=10 with spot 31.15). A crossing is only counted where the
    series demonstrably flips sign between two nonzero values -- an isolated
    cum==0.0 touch flanked by the SAME sign on both sides (e.g. a leading run
    of zero-contribution strikes with no OI/volume) is not a genuine flip.
    """
    cum = net_by_strike.sort_index().cumsum()
    strikes = cum.index.to_numpy(dtype=float)
    vals = cum.to_numpy(dtype=float)

    nonzero = [(i, 1.0 if v > 0 else -1.0) for i, v in enumerate(vals) if v != 0.0]

    crossings: list[float] = []
    for (i_a, s_a), (i_b, s_b) in zip(nonzero, nonzero[1:]):
        if s_a == s_b:
            continue
        if i_b == i_a + 1:
            a, b = vals[i_a], vals[i_b]
            crossing = strikes[i_a] + (strikes[i_b] - strikes[i_a]) * (0.0 - a) / (b - a)
        else:
            # One or more exact-zero strikes sit between i_a and i_b; the
            # cumulative sum is genuinely zero starting at the first of them.
            crossing = strikes[i_a + 1]
        crossings.append(float(crossing))

    if not crossings:
        return None
    return float(min(crossings, key=lambda k: abs(k - spot)))


def compute_squeeze_score(
    spot: float,
    call_wall: float | None,
    put_wall: float | None,
    flip: float | None,
    near_net: float,
    net_dealer: float,
    otm_call_weight: float,
    otm_put_weight: float,
    total_weight: float,
    by_strike: list[dict],
    expected_move_pct: float | None,
    expected_move_low: float | None,
    expected_move_high: float | None,
) -> dict:
    """Compute a bullish/bearish/neutral squeeze score from gamma exposure.

    Returns a dict with squeeze_score (-100..100), squeeze_label, and the
    components that drove the score for transparency.

    WARNING: This is a hand-tuned heuristic with arbitrary thresholds. It has
    not been validated against historical data and should be treated as
    experimental.
    """
    total_weight = max(total_weight, 1.0)
    call_wall_gex = 0.0
    put_wall_gex = 0.0
    for s in by_strike:
        if call_wall is not None and abs(s["strike"] - call_wall) < 1e-9:
            call_wall_gex = abs(s.get("call_gex", 0.0))
        if put_wall is not None and abs(s["strike"] - put_wall) < 1e-9:
            put_wall_gex = abs(s.get("put_gex", 0.0))

    # Dynamic Volatility-scaled proximity based on Expected Move
    em_pct = expected_move_pct if (expected_move_pct is not None and expected_move_pct > 0.1) else 5.0

    # 1. Call wall proximity (0 to +30)
    # Positive when spot is near the call wall: close from below (breakout) or
    # just above from support. Tapers to zero outside ±em_pct.
    call_wall_dist_pct = ((call_wall - spot) / spot * 100) if call_wall is not None else 999.0
    if -em_pct <= call_wall_dist_pct <= em_pct:
        call_prox_score = 30.0 * (1 - abs(call_wall_dist_pct) / em_pct)
    else:
        call_prox_score = 0.0

    # 2. Put wall proximity (0 to -30)
    # Negative when spot is near the put wall: close from below (support broken)
    # or close from above (break risk). Tapers to zero outside ±em_pct.
    put_wall_dist_pct = ((put_wall - spot) / spot * 100) if put_wall is not None else 999.0
    if -em_pct <= put_wall_dist_pct <= em_pct:
        put_prox_score = -30.0 * (1 - abs(put_wall_dist_pct) / em_pct)
    else:
        put_prox_score = 0.0

    # 3/4. OTM concentration, using OI if available, else volume.
    call_conc = otm_call_weight / total_weight
    put_conc = otm_put_weight / total_weight
    call_conc_score = min(15.0, call_conc * 100)
    put_conc_score = -min(15.0, put_conc * 100)

    # 5. Wall strength asymmetry (-10 to +10)
    if call_wall_gex > 0 and put_wall_gex > 0:
        wall_ratio = call_wall_gex / put_wall_gex
    elif call_wall_gex > 0:
        wall_ratio = float("inf")
    elif put_wall_gex > 0:
        wall_ratio = 0.0
    else:
        wall_ratio = 1.0  # neither wall carries measurable gamma; treat as balanced
    if wall_ratio > 2:
        wall_asym_score = 10.0
    elif wall_ratio < 0.5:
        wall_asym_score = -10.0
    else:
        wall_asym_score = 0.0

    # 6. Expected move reach (-10 to +10). NOTE: expected_move_low/high are always
    # spot*(1-move_pct)/spot*(1+move_pct), so spot's *position* in that band is always
    # the exact midpoint by construction — scoring that position is a tautology that
    # always nets to zero. Instead score whether the wall driving the live directional
    # read (call wall for a bullish setup, put wall for a bearish one) sits inside the
    # current expiry's 1-SD expected move — i.e. whether it's statistically reachable —
    # tapering to 0 as it sits further outside the band.
    em_score = 0.0
    if expected_move_low is not None and expected_move_high is not None:
        if call_wall is not None and call_prox_score > 0:
            if call_wall <= expected_move_high:
                em_score = 10.0
            else:
                overshoot_pct = (call_wall - expected_move_high) / spot * 100
                em_score = max(0.0, 10.0 - overshoot_pct * 4)
        elif put_wall is not None and put_prox_score < 0:
            if put_wall >= expected_move_low:
                em_score = -10.0
            else:
                overshoot_pct = (expected_move_low - put_wall) / spot * 100
                em_score = min(0.0, -10.0 + overshoot_pct * 4)

    # 7. Flip distance: if spot is close to the flip, regime is unstable.
    flip_score = 0.0
    if flip is not None:
        dist_flip_pct = abs((flip - spot) / spot * 100)
        if dist_flip_pct <= 3:
            flip_score = 5.0 if (spot > flip and call_prox_score > 0) else (-5.0 if (spot < flip and put_prox_score < 0) else 0.0)

    # 8. Regime multiplier: negative near-spot GEX is the fuel. It does not
    # have a directional sign on its own; direction comes from the wall,
    # concentration, and expected-move components above. Positive GEX means
    # pinning and is suppressed to neutral.
    directional_net = call_prox_score + put_prox_score + call_conc_score + put_conc_score + wall_asym_score + em_score + flip_score
    direction = 0.0
    if directional_net > 0:
        direction = 1.0
    elif directional_net < 0:
        direction = -1.0

    if near_net < 0 and direction != 0:
        # Fuel is the share of negative near-spot GEX relative to the total dealer book.
        negative_fuel = min(1.0, abs(near_net) / max(1.0, abs(net_dealer)))
        regime_score = 20.0 * direction * negative_fuel
        call_prox_score *= negative_fuel
        put_prox_score *= negative_fuel
        call_conc_score *= negative_fuel
        put_conc_score *= negative_fuel
        wall_asym_score *= negative_fuel
        em_score *= negative_fuel
        flip_score *= negative_fuel
    else:
        regime_score = 0.0
        # Positive gamma (or no net) means no squeeze: zero the directional components.
        call_prox_score = put_prox_score = call_conc_score = put_conc_score = wall_asym_score = em_score = flip_score = 0.0

    score = regime_score + call_prox_score + put_prox_score + call_conc_score + put_conc_score + wall_asym_score + em_score + flip_score
    score = max(-100.0, min(100.0, score))

    if score >= 20:
        label = "bullish_squeeze"
    elif score <= -20:
        label = "bearish_squeeze"
    else:
        label = "neutral"

    return {
        "squeeze_score": round(score, 1),
        "squeeze_label": label,
        "squeeze_components": {
            "regime_score": regime_score,
            "call_prox_score": call_prox_score,
            "put_prox_score": put_prox_score,
            "call_conc_score": call_conc_score,
            "put_conc_score": put_conc_score,
            "wall_asym_score": wall_asym_score,
            "em_score": em_score,
            "flip_score": flip_score,
        },
        "call_wall_gex": call_wall_gex,
        "put_wall_gex": put_wall_gex,
    }
