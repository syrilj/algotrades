"""Causal, cost-aware online expert routing for completed-bar strategies.

The router deliberately adapts only *which frozen expert may open the next
episode* and the entry risk multiplier.  It never mutates an expert model and
never changes authority midway through an open episode.  Counterfactual expert
utility is updated only after the corresponding next-open return is observable.

The exponential update is Fixed-Share-inspired.  Deterministic selection,
episode locking, and the risk overlay are practical trading constraints, so the
formal regret result for the original aggregate prediction rule is not claimed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


EPS = 1e-12


@dataclass(frozen=True)
class RouterConfig:
    """Frozen online-update and execution policy."""

    eta: float = 0.16
    share: float = 0.02
    utility_bound: float = 0.03
    one_way_cost: float = 0.001
    context_blend: float = 0.65
    warmup_updates: int = 40
    min_bucket_updates: int = 8
    entry_margin_over_cash: float = 0.02
    fallback_expert: int = 0
    stress_size: float = 0.70
    high_vol_size: float = 0.85
    stress_high_vol_size: float = 0.60
    max_weight: float = 0.50
    active_epsilon: float = 1e-9
    drift_primary_weight: float = 0.20
    min_context_quality: float = 2.0 / 3.0

    def validate(self, n_experts: int) -> None:
        if n_experts < 1:
            raise ValueError("at least one non-cash expert is required")
        if not 0.0 < self.eta <= 2.0:
            raise ValueError("eta must be in (0, 2]")
        if not 0.0 <= self.share < 1.0:
            raise ValueError("share must be in [0, 1)")
        if self.utility_bound <= 0.0:
            raise ValueError("utility_bound must be positive")
        if not 0 <= self.fallback_expert < n_experts:
            raise ValueError("fallback_expert is out of range")
        if not 0.0 < self.max_weight <= 1.0:
            raise ValueError("max_weight must be in (0, 1]")
        if not 0.0 <= self.min_context_quality <= 1.0:
            raise ValueError("min_context_quality must be in [0, 1]")
        bounded = {
            "share": self.share,
            "context_blend": self.context_blend,
            "entry_margin_over_cash": self.entry_margin_over_cash,
            "stress_size": self.stress_size,
            "high_vol_size": self.high_vol_size,
            "stress_high_vol_size": self.stress_high_vol_size,
            "drift_primary_weight": self.drift_primary_weight,
        }
        if any(not np.isfinite(value) or not 0.0 <= value <= 1.0 for value in bounded.values()):
            raise ValueError("router fractions must be finite values in [0, 1]")
        if not np.isfinite(self.one_way_cost) or self.one_way_cost < 0.0:
            raise ValueError("one_way_cost must be finite and non-negative")
        if self.warmup_updates < 0 or self.min_bucket_updates < 0:
            raise ValueError("update warmups must be non-negative")
        if not np.isfinite(self.active_epsilon) or self.active_epsilon <= 0.0:
            raise ValueError("active_epsilon must be finite and positive")


def _normalise(weights: np.ndarray) -> np.ndarray:
    values = np.asarray(weights, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values = np.maximum(values, EPS)
    return values / float(values.sum())


def fixed_share_update(
    weights: np.ndarray,
    utility: np.ndarray,
    *,
    eta: float,
    share: float,
    utility_bound: float,
) -> np.ndarray:
    """Update expert weights from bounded, already-matured net utility."""
    current = _normalise(weights)
    bounded = np.clip(np.asarray(utility, dtype=float), -utility_bound, utility_bound)
    loss = (utility_bound - bounded) / (2.0 * utility_bound)
    posterior = current * np.exp(-float(eta) * loss)
    posterior = _normalise(posterior)
    k = len(posterior)
    return _normalise((1.0 - float(share)) * posterior + float(share) / k)


def counterfactual_net_utility(
    decision_targets: np.ndarray,
    previous_targets: np.ndarray,
    open_return: float,
    *,
    one_way_cost: float,
) -> np.ndarray:
    """Realized target return less entry/resize/exit turnover cost."""
    current = np.asarray(decision_targets, dtype=float)
    previous = np.asarray(previous_targets, dtype=float)
    if current.shape != previous.shape:
        raise ValueError("current and previous targets must have the same shape")
    if not np.isfinite(open_return) or not np.isfinite(one_way_cost) or one_way_cost < 0.0:
        raise ValueError("return and cost must be finite; cost must be non-negative")
    return current * float(open_return) - float(one_way_cost) * np.abs(current - previous)


def _as_naive_index(index: pd.Index) -> pd.DatetimeIndex:
    result = pd.DatetimeIndex(pd.to_datetime(index))
    if result.tz is not None:
        result = result.tz_convert("America/New_York").tz_localize(None)
    return result


def _clean_close(frame: pd.DataFrame | None) -> pd.Series | None:
    if frame is None or frame.empty or "close" not in frame.columns:
        return None
    close = frame["close"].astype(float).copy()
    close.index = _as_naive_index(close.index)
    return close.sort_index()[~close.sort_index().index.duplicated(keep="last")]


def _align_intraday_close(
    frame: pd.DataFrame | None,
    index: pd.Index,
    *,
    tolerance: str | pd.Timedelta | None = "36h",
) -> pd.Series:
    close = _clean_close(frame)
    if close is None:
        return pd.Series(np.nan, index=index, dtype=float)
    return _align_known_series(close, index, tolerance=tolerance)


def _align_prior_daily_close(frame: pd.DataFrame | None, index: pd.Index) -> pd.Series:
    """Align the most recent *previous-session* close to intraday bars.

    Daily cache rows are midnight-labelled even though the close is available
    only after that session.  Shifting one observation before backward-asof
    prevents the same day's close from leaking into that day's intraday bars.
    """
    close = _clean_close(frame)
    target = _as_naive_index(index)
    if close is None:
        return pd.Series(np.nan, index=index, dtype=float)
    prior = close.shift(1).dropna()
    if prior.empty:
        return pd.Series(np.nan, index=index, dtype=float)
    left = pd.DataFrame({"ts": target, "_order": np.arange(len(target))}).sort_values("ts")
    right = prior.rename("value").reset_index()
    right.columns = ["ts", "value"]
    joined = pd.merge_asof(left, right.sort_values("ts"), on="ts", direction="backward")
    joined = joined.sort_values("_order")
    return pd.Series(joined["value"].to_numpy(dtype=float), index=index)


def _prior_daily_close(frame: pd.DataFrame | None) -> pd.Series | None:
    """Return the daily close that is knowable at each midnight-labelled row."""
    close = _clean_close(frame)
    if close is None:
        return None
    prior = close.shift(1)
    return prior if prior.notna().any() else None


def _align_known_series(
    series: pd.Series | None,
    index: pd.Index,
    *,
    tolerance: str | pd.Timedelta | None = "4d",
) -> pd.Series:
    """Backward-align an already publication-lagged series to target bars."""
    if series is None or series.empty:
        return pd.Series(np.nan, index=index, dtype=float)
    known = series.astype(float).copy()
    known.index = _as_naive_index(known.index)
    known = known.sort_index()
    known = known[~known.index.duplicated(keep="last")].dropna()
    if known.empty:
        return pd.Series(np.nan, index=index, dtype=float)
    target = _as_naive_index(index)
    left = pd.DataFrame({"ts": target, "_order": np.arange(len(target))}).sort_values("ts")
    right = known.rename("value").reset_index()
    right.columns = ["ts", "value"]
    max_age = pd.Timedelta(tolerance) if tolerance is not None else None
    joined = pd.merge_asof(
        left,
        right.sort_values("ts"),
        on="ts",
        direction="backward",
        tolerance=max_age,
    )
    joined = joined.sort_values("_order")
    return pd.Series(joined["value"].to_numpy(dtype=float), index=index)


def build_causal_context(
    frame: pd.DataFrame,
    *,
    spy: pd.DataFrame | None = None,
    vix_daily: pd.DataFrame | None = None,
    hyg_daily: pd.DataFrame | None = None,
    lqd_daily: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return prefix-invariant market context known at each bar close.

    The compact bucket intentionally avoids a high-dimensional regime model on
    the repository's short two-year hourly history.  Missing optional sources
    are explicit in ``context_quality`` and never replaced with target prices.
    """
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {missing}")
    data = frame.sort_index()
    index = data.index
    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)
    previous = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous).abs(), (low - previous).abs()], axis=1
    ).max(axis=1)
    atr_pct = true_range.ewm(alpha=1.0 / 14.0, adjust=False).mean() / close.replace(0.0, np.nan)
    atr_baseline = atr_pct.shift(1).expanding(min_periods=40).median()
    high_vol = (atr_pct > 1.15 * atr_baseline).fillna(False)

    slow = close.ewm(span=200, adjust=False).mean()
    trend = (close >= slow).fillna(False)

    spy_close = _align_intraday_close(spy, index)
    spy_slow = spy_close.ewm(span=200, adjust=False, min_periods=40).mean()
    spy_drawdown = spy_close / spy_close.rolling(100, min_periods=20).max() - 1.0
    spy_available = spy_close.notna() & spy_slow.notna() & spy_drawdown.notna()
    spy_stress = ((spy_close < spy_slow) & (spy_drawdown < -0.03)).fillna(False)

    # Compute daily-horizon features on the daily clock *before* expanding them
    # onto hourly bars.  Doing pct_change(5) after forward filling would make a
    # purported five-session measure a five-bar measure.
    vix_known_daily = _prior_daily_close(vix_daily)
    vix = _align_known_series(vix_known_daily, index)
    if vix_known_daily is None:
        vix_z = pd.Series(np.nan, index=index, dtype=float)
        vix_change = pd.Series(np.nan, index=index, dtype=float)
    else:
        vix_mean_daily = vix_known_daily.shift(1).expanding(min_periods=20).mean()
        vix_std_daily = (
            vix_known_daily.shift(1).expanding(min_periods=20).std().replace(0.0, np.nan)
        )
        vix_z = _align_known_series((vix_known_daily - vix_mean_daily) / vix_std_daily, index)
        vix_change = _align_known_series(vix_known_daily.pct_change(5, fill_method=None), index)
    vix_stress = ((vix_z > 1.0) | (vix_change > 0.15)).fillna(False)

    hyg_known_daily = _prior_daily_close(hyg_daily)
    lqd_known_daily = _prior_daily_close(lqd_daily)
    hyg = _align_known_series(hyg_known_daily, index)
    lqd = _align_known_series(lqd_known_daily, index)
    if hyg_known_daily is None or lqd_known_daily is None:
        credit_change = pd.Series(np.nan, index=index, dtype=float)
    else:
        daily_credit_ratio = hyg_known_daily / lqd_known_daily.replace(0.0, np.nan)
        credit_change = _align_known_series(
            daily_credit_ratio.pct_change(5, fill_method=None), index
        )
    credit_stress = (credit_change < -0.01).fillna(False)

    stress = (spy_stress | vix_stress | credit_stress).astype(bool)
    bucket = (
        trend.astype(int)
        + 2 * high_vol.astype(int)
        + 4 * stress.astype(int)
    ).astype(int)

    quality_parts = pd.concat(
        [
            spy_available.astype(float).rename("spy"),
            vix.notna().astype(float).rename("vix"),
            credit_change.notna().astype(float).rename("credit"),
            atr_baseline.notna().astype(float).rename("target_features"),
        ],
        axis=1,
    )
    quality = quality_parts.mean(axis=1)
    return pd.DataFrame(
        {
            "context_bucket": bucket,
            "trend": trend.astype(bool),
            "high_vol": high_vol.astype(bool),
            "stress": stress.astype(bool),
            "atr_pct": atr_pct.fillna(0.0),
            "spy_drawdown": spy_drawdown,
            "vix_level_prior_close": vix,
            "vix_z": vix_z,
            "vix_change_5d": vix_change,
            "credit_change_5d": credit_change,
            "context_quality": quality,
        },
        index=index,
    )


def _entry_scale(stress: bool, high_vol: bool, config: RouterConfig) -> float:
    if stress and high_vol:
        return config.stress_high_vol_size
    if stress:
        return config.stress_size
    if high_vol:
        return config.high_vol_size
    return 1.0


def route_experts(
    opens: pd.Series,
    expert_signals: Mapping[str, pd.Series],
    context: pd.DataFrame,
    *,
    config: RouterConfig | None = None,
    prior: Sequence[float] | None = None,
    context_priors: Mapping[int, Sequence[float]] | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """Causally route frozen experts and return target plus diagnostics.

    Signals at bar ``t`` execute at the next open.  At iteration ``i`` the
    newest mature counterfactual is therefore signal ``i-2`` evaluated over
    ``open[i-1] -> open[i]``.  No current/future return enters selection.
    """
    if not expert_signals:
        raise ValueError("expert_signals cannot be empty")
    if "CASH" in expert_signals:
        raise ValueError("CASH is a reserved expert name")
    cfg = config or RouterConfig()
    names = list(expert_signals)
    n_experts = len(names)
    cfg.validate(n_experts)
    index = opens.index
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError("opens index must be strictly increasing and unique")
    if not np.isfinite(opens.astype(float).to_numpy()).all():
        raise ValueError("opens must be finite")
    if not context.index.equals(index):
        context = context.reindex(index)

    matrix = np.column_stack(
        [
            expert_signals[name]
            .reindex(index)
            .fillna(0.0)
            .astype(float)
            .clip(-cfg.max_weight, cfg.max_weight)
            .to_numpy()
            for name in names
        ]
    )
    # CASH is a real expert with zero utility and zero target.
    matrix = np.column_stack([matrix, np.zeros(len(index), dtype=float)])
    all_names = [*names, "CASH"]
    k = len(all_names)

    if prior is None:
        base_prior = np.array([0.62, *([0.33 / max(n_experts - 1, 1)] * (n_experts - 1)), 0.05])
    else:
        base_prior = np.asarray(prior, dtype=float)
        if len(base_prior) == n_experts:
            base_prior = np.r_[base_prior, 0.05]
    if len(base_prior) != k:
        raise ValueError(f"prior must contain {k} values including CASH")
    if not np.isfinite(base_prior).all() or np.any(base_prior < 0.0) or float(base_prior.sum()) <= 0.0:
        raise ValueError("prior must contain finite non-negative mass")
    base_prior = _normalise(base_prior)

    global_weights = base_prior.copy()
    bucket_weights: dict[int, np.ndarray] = {}
    bucket_updates: dict[int, int] = {}
    supplied_context_priors = context_priors or {}

    output = np.zeros(len(index), dtype=float)
    selected = np.full(len(index), -1, dtype=int)
    confidence = np.zeros(len(index), dtype=float)
    support_margin = np.zeros(len(index), dtype=float)
    cash_weight = np.zeros(len(index), dtype=float)
    evidence = np.zeros(len(index), dtype=int)
    drift = np.zeros(len(index), dtype=bool)
    weight_history = np.zeros((len(index), k), dtype=float)

    active_expert: int | None = None
    locked_scale = 1.0
    total_updates = 0
    open_values = opens.astype(float).to_numpy()
    buckets = context["context_bucket"].fillna(0).astype(int).to_numpy()
    stresses = context.get("stress", pd.Series(False, index=index)).fillna(False).astype(bool).to_numpy()
    high_vols = context.get("high_vol", pd.Series(False, index=index)).fillna(False).astype(bool).to_numpy()
    context_quality = (
        context.get("context_quality", pd.Series(1.0, index=index))
        .fillna(0.0)
        .astype(float)
        .clip(0.0, 1.0)
        .to_numpy()
    )
    low_quality_abstain = np.zeros(len(index), dtype=bool)

    for i in range(len(index)):
        if i >= 2 and np.isfinite(open_values[i]) and np.isfinite(open_values[i - 1]) and open_values[i - 1] > 0:
            decision_targets = matrix[i - 2]
            previous_targets = matrix[i - 3] if i >= 3 else np.zeros(k, dtype=float)
            # A flat target following an active target is an observable exit
            # and must pay turnover cost even though its gross return is zero.
            has_position_or_turnover = np.any(
                (np.abs(decision_targets[:-1]) > cfg.active_epsilon)
                | (np.abs(previous_targets[:-1]) > cfg.active_epsilon)
            )
            if has_position_or_turnover:
                open_return = open_values[i] / open_values[i - 1] - 1.0
                utility = counterfactual_net_utility(
                    decision_targets,
                    previous_targets,
                    open_return,
                    one_way_cost=cfg.one_way_cost,
                )
                utility[-1] = 0.0
                global_weights = fixed_share_update(
                    global_weights,
                    utility,
                    eta=cfg.eta,
                    share=cfg.share,
                    utility_bound=cfg.utility_bound,
                )
                reward_bucket = int(buckets[i - 2])
                if reward_bucket not in bucket_weights:
                    seed = supplied_context_priors.get(reward_bucket, base_prior)
                    bucket_weights[reward_bucket] = _normalise(np.asarray(seed, dtype=float))
                    bucket_updates[reward_bucket] = 0
                bucket_weights[reward_bucket] = fixed_share_update(
                    bucket_weights[reward_bucket],
                    utility,
                    eta=cfg.eta,
                    share=cfg.share,
                    utility_bound=cfg.utility_bound,
                )
                bucket_updates[reward_bucket] += 1
                total_updates += 1

        bucket = int(buckets[i])
        if bucket not in bucket_weights:
            seed = supplied_context_priors.get(bucket, base_prior)
            seed_array = np.asarray(seed, dtype=float)
            if len(seed_array) != k:
                raise ValueError(f"context prior {bucket} must contain {k} values")
            bucket_weights[bucket] = _normalise(seed_array)
            bucket_updates[bucket] = 0
        local_weights = bucket_weights[bucket]
        log_score = (
            (1.0 - cfg.context_blend) * np.log(np.maximum(global_weights, EPS))
            + cfg.context_blend * np.log(np.maximum(local_weights, EPS))
        )
        combined = _normalise(np.exp(log_score - np.max(log_score)))
        weight_history[i] = combined
        evidence[i] = bucket_updates[bucket]
        drift[i] = bool(total_updates >= cfg.warmup_updates and global_weights[cfg.fallback_expert] < cfg.drift_primary_weight)

        exited_this_bar = False
        if active_expert is not None:
            current_target = float(matrix[i, active_expert])
            if abs(current_target) <= cfg.active_epsilon:
                active_expert = None
                locked_scale = 1.0
                exited_this_bar = True
            else:
                # A newly observed risk shock may only de-risk the open
                # episode. Clearing stress never sizes the episode back up.
                locked_scale = min(
                    locked_scale,
                    float(_entry_scale(bool(stresses[i]), bool(high_vols[i]), cfg)),
                )
                output[i] = float(np.clip(current_target * locked_scale, -cfg.max_weight, cfg.max_weight))
                selected[i] = active_expert

        if active_expert is None and not exited_this_bar:
            eligible = np.flatnonzero(np.abs(matrix[i, :n_experts]) > cfg.active_epsilon)
            if context_quality[i] < cfg.min_context_quality:
                choice = k - 1
                low_quality_abstain[i] = bool(len(eligible))
            elif total_updates < cfg.warmup_updates or bucket_updates[bucket] < cfg.min_bucket_updates:
                fallback = cfg.fallback_expert
                choice = fallback if fallback in eligible else k - 1
            elif len(eligible):
                best = int(eligible[np.argmax(combined[eligible])])
                choice = best if combined[best] - combined[-1] >= cfg.entry_margin_over_cash else k - 1
            else:
                choice = k - 1

            if choice < n_experts:
                active_expert = choice
                locked_scale = float(np.clip(_entry_scale(bool(stresses[i]), bool(high_vols[i]), cfg), 0.0, 1.0))
                output[i] = float(np.clip(matrix[i, choice] * locked_scale, -cfg.max_weight, cfg.max_weight))
                selected[i] = choice

        cash_weight[i] = float(combined[-1])
        if selected[i] >= 0:
            chosen = int(selected[i])
            alternatives = np.delete(combined, chosen)
            best_alternative = float(np.max(alternatives)) if len(alternatives) else 0.0
            confidence[i] = float(combined[chosen])
            support_margin[i] = float(combined[chosen] - best_alternative)

    diagnostics = pd.DataFrame(index=index)
    diagnostics["selected_expert"] = selected
    diagnostics["selected_name"] = [all_names[j] if j >= 0 else "CASH" for j in selected]
    diagnostics["ordinal_confidence"] = confidence
    diagnostics["selected_weight"] = confidence
    diagnostics["selected_support_margin"] = support_margin
    diagnostics["cash_weight"] = cash_weight
    diagnostics["context_updates"] = evidence
    diagnostics["drift_warning"] = drift
    diagnostics["context_bucket"] = buckets
    diagnostics["context_quality"] = context_quality
    diagnostics["low_quality_entry_abstain"] = low_quality_abstain
    for j, name in enumerate(all_names):
        diagnostics[f"weight_{name}"] = weight_history[:, j]
    return pd.Series(output, index=index, dtype=float), diagnostics
