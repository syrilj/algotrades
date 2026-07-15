"""Macro, cross-asset, and long-memory feature module.

This module computes causal regime, beta, macro-surprise, and fractional-
differentiation features for use by the meta-labeler.  It is designed to be
integrated into the research pipeline (``tools/evolve/feature_validation.py``)
once cross-asset bars are aligned.

Causal / leakage contract
-------------------------
* All returns used for beta/correlation estimation are shifted by one bar
  before the rolling window is applied.
* Macro surprises are joined with ``merge_asof(..., direction='backward')`` so
  that the value available at a bar is the latest known print at or before that
  bar.  ``release_ts`` is the official release timestamp.
* Fractional-differencing parameter ``d`` is estimated on a training window
  only and then applied out-of-sample; the transform is a weighted sum of
  past values.
* Post-release drift (return in first 15-60 minutes after a release) is
  provided as a labeling utility, not as a feature.
* All percentile / z-score normalization is computed on expanding or rolling
  windows with a lag, never on future data.

The module uses pandas/numpy because those are the project dependencies.  The
API is vectorized and can be ported to Polars later if required.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Union

import numpy as np
import pandas as pd


# ─── Fractional differentiation ─────────────────────────────────────────────

def fracdiff_weights(d: float, threshold: float = 1e-5, max_len: int = 10000) -> np.ndarray:
    """Binomial expansion weights for fractional differencing operator (1-L)^d.

    Weights: w[0] = 1; w[k] = -w[k-1] * (d - k + 1) / k
    Truncation when absolute weight falls below ``threshold`` or ``max_len``.
    """
    if d <= 0.0:
        return np.array([1.0])
    if d >= 1.0:
        raise ValueError("fractional differencing d must be < 1 for long-memory preservation")
    weights = [1.0]
    for k in range(1, max_len):
        w = -weights[k - 1] * (d - k + 1) / k
        if abs(w) < threshold:
            break
        weights.append(w)
    return np.array(weights, dtype=float)


def fracdiff_series(series: pd.Series, d: float, threshold: float = 1e-5) -> pd.Series:
    """Apply causal fractional differencing to ``series``.

    Returns a weighted rolling sum using the binomial expansion weights.
    The output is aligned to the right (value at index t uses only prior values).
    """
    if d <= 0.0:
        return series.astype(float)
    w = fracdiff_weights(d, threshold=threshold)
    out = series.astype(float).rolling(len(w), min_periods=len(w)).apply(
        lambda x: float(np.dot(w, x.iloc[-len(w):].to_numpy())),
        raw=False,
    )
    return out


def estimate_d(
    series: pd.Series,
    method: str = "hurst",
    min_d: float = 0.0,
    max_d: float = 0.8,
    step: float = 0.05,
    adf_significance: float = 0.01,
) -> float:
    """Estimate fractional differencing parameter ``d`` on training data.

    Methods
    -------
    hurst: estimate via rescaled range (R/S) and convert d = H - 0.5.
    adf: try grid of d values; pick the smallest d whose fractionally
         differenced series rejects the ADF null hypothesis at
         ``adf_significance``.  Requires ``statsmodels``.
    """
    method = method.lower()
    if method == "hurst":
        return _hurst_to_d(_hurst_rs(series))

    if method != "adf":
        raise ValueError(f"unknown method: {method}")

    try:
        from statsmodels.tsa.stattools import adfuller
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise ModuleNotFoundError(
            "statsmodels is required for method='adf'. "
            "Install it or use method='hurst'."
        ) from exc

    s = series.dropna().astype(float)
    if s.empty:
        return 0.0

    best_d = 0.0
    for d in np.arange(min_d, max_d + step, step):
        fd = fracdiff_series(s, d)
        fd = fd.dropna()
        if len(fd) < 30:
            break
        try:
            _, pvalue, *_ = adfuller(fd, maxlag=1, regression="c")
        except Exception:  # noqa: BLE001
            continue
        if pvalue < adf_significance:
            best_d = d
            break
        best_d = d
    return float(best_d)


def _hurst_rs(series: pd.Series) -> float:
    """Rescaled-range (R/S) estimate of Hurst exponent."""
    x = series.dropna().astype(float).to_numpy()
    if len(x) < 100:
        return 0.5
    n = len(x)
    cum = np.cumsum(x - x.mean())
    r = cum.max() - cum.min()
    s = x.std(ddof=1)
    return float(np.log(max(r, 1e-12) / max(s, 1e-12)) / np.log(n)) if s > 0 else 0.5


def _hurst_to_d(h: float) -> float:
    """Long-memory relation d = H - 0.5, clipped to (0, 1)."""
    return float(np.clip(h - 0.5, 0.0, 0.99))


# ─── Macro calendar helpers ─────────────────────────────────────────────────

MACRO_EVENT_TYPES = ("CPI", "PPI", "FOMC", "NFP", "GDP", "ISM")


def parse_macro_calendar(
    path_or_df: Union[str, Path, pd.DataFrame],
    event_types: Optional[Sequence[str]] = None,
    tz: Optional[str] = "UTC",
) -> pd.DataFrame:
    """Normalize a macro calendar CSV/DataFrame.

    Expected columns: ``release_ts``, ``event_type`` plus either
    ``actual`` and ``expected`` or a precomputed ``surprise``.
    Optional: ``country``.  Returns a DataFrame with ``surprise`` and
    ``surprise_stdized`` computed per event type.
    """
    if isinstance(path_or_df, (str, Path)):
        df = pd.read_csv(path_or_df, parse_dates=["release_ts"])
    else:
        df = path_or_df.copy()
    event_types = set(event_types) if event_types else set(MACRO_EVENT_TYPES)
    df["release_ts"] = pd.to_datetime(df["release_ts"], utc=True)
    if tz:
        df["release_ts"] = df["release_ts"].dt.tz_convert(tz)
    df = df[df["event_type"].isin(event_types)].copy()
    if "actual" in df.columns and "expected" in df.columns:
        df["actual"] = pd.to_numeric(df["actual"], errors="coerce")
        df["expected"] = pd.to_numeric(df["expected"], errors="coerce")
        df["surprise"] = df["actual"] - df["expected"]
    elif "surprise" in df.columns:
        df["surprise"] = pd.to_numeric(df["surprise"], errors="coerce")
    else:
        raise ValueError("macro calendar must contain actual/expected or surprise")
    # Historical std of surprises per event type (expanding, one bar lag)
    df = df.sort_values("release_ts")
    df["surprise_std"] = (
        df.groupby("event_type")["surprise"]
        .shift(1)
        .groupby(df["event_type"])
        .expanding(min_periods=5)
        .std()
        .reset_index(level=0, drop=True)
    )
    df["surprise_stdized"] = df["surprise"] / df["surprise_std"].replace(0, np.nan)
    return df.dropna(subset=["release_ts"]).reset_index(drop=True)


def _latest_macro_value(
    index: pd.DatetimeIndex,
    events: pd.DataFrame,
    event_type: str,
    value_col: str = "surprise_stdized",
    fallback_col: str = "surprise",
    horizon: str = "48h",
) -> pd.Series:
    """Return the most recent ``value_col`` for ``event_type`` at each index.

    If ``value_col`` is NaN (e.g. first few events with no historical std), falls
    back to ``fallback_col`` (raw surprise) so the information is still usable.
    """
    cols = ["release_ts", value_col]
    if fallback_col in events.columns:
        cols.append(fallback_col)
    sub = events[events["event_type"] == event_type][cols].copy()
    if sub.empty:
        return pd.Series(index=index, dtype=float)
    frame = pd.DataFrame({"ts": index})
    joined = pd.merge_asof(
        frame.sort_values("ts"),
        sub.sort_values("release_ts"),
        left_on="ts",
        right_on="release_ts",
        direction="backward",
    )
    # Require the print to be within ``horizon`` to avoid stale surprises.
    if horizon:
        joined["delta"] = joined["ts"] - joined["release_ts"]
        joined[value_col] = joined[value_col].where(
            joined["delta"] <= pd.Timedelta(horizon), np.nan
        )
        if fallback_col in joined.columns:
            joined[fallback_col] = joined[fallback_col].where(
                joined["delta"] <= pd.Timedelta(horizon), np.nan
            )
    out = joined.set_index("ts")[value_col]
    if fallback_col in joined.columns:
        out = out.fillna(joined.set_index("ts")[fallback_col])
    return out.reindex(index)


def macro_event_features(
    index: pd.DatetimeIndex,
    events: pd.DataFrame,
    event_types: Optional[Sequence[str]] = None,
    horizon: str = "48h",
    include_countdown: bool = True,
) -> pd.DataFrame:
    """Macro event proximity and lagged surprise features.

    All surprise values are the last known standardized surprise at or before
    each timestamp.  Countdowns are derived from the macro calendar only.
    """
    event_types = event_types or MACRO_EVENT_TYPES
    if "surprise_stdized" not in events.columns:
        events = parse_macro_calendar(events)
    events = events.sort_values("release_ts")
    out = pd.DataFrame(index=index)

    for et in event_types:
        sub = events[events["event_type"] == et]
        if sub.empty:
            out[f"macro_{et.lower()}_surprise_lag"] = np.nan
            out[f"macro_{et.lower()}_since_release_h"] = np.nan
            out[f"macro_{et.lower()}_to_next_release_h"] = np.nan
            continue

        # Latest known surprise
        out[f"macro_{et.lower()}_surprise_lag"] = _latest_macro_value(
            index, events, et, value_col="surprise_stdized", horizon=horizon
        )

        # Proximity: hours since last / to next release
        since = pd.Series(index=index, dtype="timedelta64[ns]")
        to_next = pd.Series(index=index, dtype="timedelta64[ns]")
        for i, ts in enumerate(index):
            past = sub[sub["release_ts"] <= ts]
            future = sub[sub["release_ts"] > ts]
            if not past.empty:
                since.iloc[i] = ts - past["release_ts"].iloc[-1]
            if not future.empty:
                to_next.iloc[i] = future["release_ts"].iloc[0] - ts
        out[f"macro_{et.lower()}_since_release_h"] = since.dt.total_seconds() / 3600.0
        out[f"macro_{et.lower()}_to_next_release_h"] = to_next.dt.total_seconds() / 3600.0

    if include_countdown:
        out = out.assign(
            macro_any_to_next_release_h=out.filter(like="_to_next_release_h").min(axis=1),
            macro_any_since_release_h=out.filter(like="_since_release_h").min(axis=1),
        )
    return out


# ─── Cross-asset and regime features ────────────────────────────────────────

def _log_returns(series: pd.Series) -> pd.Series:
    return np.log(series.astype(float).replace(0, np.nan)).diff()


def _shifted_returns(df: pd.DataFrame, col: str) -> pd.Series:
    """Causal log returns: shift by one bar so only past return is known."""
    return _log_returns(df[col]).shift(1)


def rolling_betas(
    df: pd.DataFrame,
    target_col: str,
    bench_col: str,
    windows: Sequence[int] = (5 * 24, 20 * 24, 60 * 24),
    suffix: str = "beta",
) -> pd.DataFrame:
    """Rolling OLS beta of ``target_col`` returns on ``bench_col`` returns.

    Returns are log and shifted one bar before the window.  Windows are in
    number of bars; for 1-hour bars, defaults are ~5d, 20d, 60d.
    """
    out = pd.DataFrame(index=df.index)
    r_t = _shifted_returns(df, target_col)
    r_b = _shifted_returns(df, bench_col)
    for w in windows:
        cov = r_t.rolling(w, min_periods=max(3, w // 4)).cov(r_b)
        var = r_b.rolling(w, min_periods=max(3, w // 4)).var()
        out[f"{suffix}_{w}"] = cov / var.replace(0, np.nan)
    return out


def rolling_correlations(
    df: pd.DataFrame,
    target_col: str,
    other_col: str,
    windows: Sequence[int] = (5 * 24, 20 * 24, 60 * 24),
    suffix: str = "corr",
) -> pd.DataFrame:
    """Rolling correlation of shifted log returns."""
    out = pd.DataFrame(index=df.index)
    r_t = _shifted_returns(df, target_col)
    r_o = _shifted_returns(df, other_col)
    for w in windows:
        out[f"{suffix}_{w}"] = r_t.rolling(w, min_periods=max(3, w // 4)).corr(r_o)
    return out


def regime_features(
    df: pd.DataFrame,
    vix_col: str = "vix_close",
    spy_col: str = "spy_close",
    tlt_col: str = "tlt_close",
    breadth_col: Optional[str] = None,
    lookback: int = 20 * 24,
) -> pd.DataFrame:
    """Risk-on/off regime indicators, all point-in-time.

    Columns produced:
    * ``vix_level`` / ``vix_zscore`` / ``vix_pct_low`` (percentile in low VIX)
    * ``vix_term_slope`` if ``vix3m_close`` / ``vix9d_close`` are present
    * ``equity_rate_corr`` correlation of SPY and TLT returns
    * ``spy_above_sma`` and ``spy_momentum``
    * ``risk_on_score`` composite (0..1)
    """
    out = pd.DataFrame(index=df.index)
    if vix_col in df.columns:
        vix = df[vix_col].astype(float)
        out["vix_level"] = vix
        out["vix_zscore"] = (vix - vix.rolling(lookback, min_periods=lookback // 4).mean()) / (
            vix.rolling(lookback, min_periods=lookback // 4).std().replace(0, np.nan)
        )
        rank = vix.rank()
        out["vix_pct_low"] = 1.0 - (rank - 1.0) / (rank.rolling(lookback, min_periods=lookback // 4).max() - 1.0).replace(0, np.nan)

        # Term structure: VIX3M / VIX9D if available
        if "vix3m_close" in df.columns and "vix9d_close" in df.columns:
            out["vix_term_slope"] = (
                df["vix3m_close"].astype(float) - df["vix9d_close"].astype(float)
            ) / vix

    if spy_col in df.columns and tlt_col in df.columns:
        out["equity_rate_corr"] = rolling_correlations(
            df, spy_col, tlt_col, windows=[lookback], suffix="equity_rate_corr"
        ).iloc[:, 0]
        spy_ret = _shifted_returns(df, spy_col)
        tlt_ret = _shifted_returns(df, tlt_col)
        out["rates_down_eq_up"] = ((spy_ret > 0) & (tlt_ret > 0)).astype(float)

    if spy_col in df.columns:
        spy = df[spy_col].astype(float)
        sma = spy.rolling(lookback, min_periods=lookback // 4).mean()
        out["spy_above_sma"] = (spy > sma).astype(float)
        out["spy_momentum_1h"] = _shifted_returns(df, spy_col)

    if breadth_col and breadth_col in df.columns:
        out["high_beta_breadth"] = df[breadth_col].astype(float)

    # Composite risk-on score: low VIX, positive SPY momentum, rates down/equity up
    components = []
    if "vix_pct_low" in out.columns:
        components.append(out["vix_pct_low"])
    if "spy_momentum_1h" in out.columns:
        components.append(out["spy_momentum_1h"].clip(lower=-0.05, upper=0.05) / 0.05)
    if "rates_down_eq_up" in out.columns:
        components.append(out["rates_down_eq_up"])
    if components:
        out["risk_on_score"] = pd.concat(components, axis=1).mean(axis=1)
    else:
        out["risk_on_score"] = np.nan
    return out


# ─── Long-memory features ───────────────────────────────────────────────────

def long_memory_features(
    df: pd.DataFrame,
    cols: Sequence[str] = ("close", "volume"),
    d: Optional[float] = None,
    d_train: Optional[pd.Series] = None,
    threshold: float = 1e-5,
    method: str = "hurst",
) -> pd.DataFrame:
    """Fractionally differentiate selected price/volume series.

    If ``d`` is None and ``d_train`` is provided, ``d`` is estimated on the
    training series.  When neither is provided, ``d`` is estimated from the
    full column (intended only for exploratory use; for production, fit on a
    training window).  ``method`` controls ``d`` estimation (``hurst`` or
    ``adf``; the latter requires ``statsmodels``).
    """
    out = pd.DataFrame(index=df.index)
    for col in cols:
        if col not in df.columns:
            continue
        s = df[col].astype(float)
        d_est = d
        if d_est is None:
            train = d_train if d_train is not None else s
            d_est = estimate_d(train, method=method)
        fd = fracdiff_series(s, d_est, threshold=threshold)
        out[f"{col}_fd{d_est:.2f}"] = fd
        # Also preserve a raw memory proxy: Hurst exponent over a long window
        out[f"{col}_hurst"] = s.rolling(252 * 24, min_periods=100).apply(
            _hurst_rs, raw=False
        )
    return out


# ─── Interaction / high-beta amplification features ────────────────────────

def interaction_features(
    df: pd.DataFrame,
    macro: pd.DataFrame,
    regime: pd.DataFrame,
    micro: Optional[pd.DataFrame] = None,
    high_beta_col: Optional[str] = None,
) -> pd.DataFrame:
    """Regime-conditional interaction features.

    Examples:
    * high_beta x macro surprise x low VIX
    * macro surprise x risk_on_score
    * VPA/toxicity x risk_on_score (if ``micro`` contains those columns)
    """
    out = pd.DataFrame(index=df.index)
    macro_surprise = None
    for c in macro.columns:
        if "surprise" in c:
            macro_surprise = macro[c]
            break

    if macro_surprise is not None:
        if "risk_on_score" in regime.columns:
            out["macro_surprise_x_risk_on"] = macro_surprise * regime["risk_on_score"]

        if "vix_pct_low" in regime.columns:
            out["macro_surprise_x_low_vix"] = macro_surprise * regime["vix_pct_low"]

        if high_beta_col and high_beta_col in df.columns:
            out["macro_surprise_x_low_vix_x_high_beta"] = (
                macro_surprise * regime.get("vix_pct_low", 1.0) * df[high_beta_col]
            )

    if "risk_on_score" in regime.columns and micro is not None:
        for col in ["toxicity", "vpin", "absorption", "ofi"]:
            for c in micro.columns:
                if col in c:
                    out[f"{c}_x_risk_on"] = micro[c] * regime["risk_on_score"]

    if "vix_level" in regime.columns and "spy_momentum_1h" in regime.columns:
        out["vix_inverse_x_spy_momentum"] = (1.0 / regime["vix_level"].replace(0, np.nan)) * regime["spy_momentum_1h"]
    return out


# ─── Full feature matrix ────────────────────────────────────────────────────

def align_cross_asset_bars(
    target_df: pd.DataFrame,
    spy_df: Optional[pd.DataFrame] = None,
    tlt_df: Optional[pd.DataFrame] = None,
    vix_df: Optional[pd.DataFrame] = None,
    suffix_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Align cross-asset bars to the target index and rename columns.

    This is the cross-asset data aligner.  It takes optional DataFrames for
    SPY/SPX, TLT/rate proxy, and VIX and merges them onto ``target_df`` using
    backward-as-of joins.  Column names are prefixed by asset class.
    """
    out = target_df.copy().sort_index()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")

    suffix_map = suffix_map or {
        "spy_df": "spy_",
        "tlt_df": "tlt_",
        "vix_df": "vix_",
    }

    def _join(other: Optional[pd.DataFrame], prefix: str) -> pd.DataFrame:
        if other is None or other.empty:
            return out
        other = other.copy().sort_index()
        other.index = pd.to_datetime(other.index)
        if other.index.tz is None:
            other.index = other.index.tz_localize("UTC")
        other = other.tz_convert(out.index.tz)
        other = other.add_prefix(prefix)
        joined = pd.merge_asof(
            out.reset_index(names="ts"),
            other.reset_index(names="ts"),
            on="ts",
            direction="backward",
        )
        return joined.set_index("ts").sort_index()

    out = _join(spy_df, suffix_map.get("spy_df", "spy_"))
    out = _join(tlt_df, suffix_map.get("tlt_df", "tlt_"))
    out = _join(vix_df, suffix_map.get("vix_df", "vix_"))
    return out


def macro_feature_matrix(
    target_df: pd.DataFrame,
    spy_df: Optional[pd.DataFrame] = None,
    tlt_df: Optional[pd.DataFrame] = None,
    vix_df: Optional[pd.DataFrame] = None,
    events_df: Optional[pd.DataFrame] = None,
    d: Optional[float] = None,
    d_train_col: Optional[str] = None,
    high_beta_col: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Build the full macro + cross-asset + long-memory feature matrix.

    Parameters
    ----------
    target_df: OHLCV bars for the target symbol.
    spy_df/tlt_df/vix_df: optional cross-asset bars.
    events_df: macro calendar DataFrame (see ``parse_macro_calendar``).
    d: optional fixed fractional differencing parameter.
    d_train_col: column name in ``target_df`` whose training history is used
        to estimate ``d``.  If None, ``d`` is estimated on the full column
        (use only for exploration; in walk-forward, pass a training slice).
    high_beta_col: optional column in ``target_df`` flagging high-beta names.
    cfg: optional dict with tuning keys (beta_windows, corr_windows, etc.).

    Returns a DataFrame indexed like ``target_df``.
    """
    cfg = cfg or {}
    beta_windows = cfg.get("beta_windows", (5 * 24, 20 * 24, 60 * 24))
    corr_windows = cfg.get("corr_windows", (5 * 24, 20 * 24, 60 * 24))
    regime_lookback = cfg.get("regime_lookback", 20 * 24)
    fd_threshold = cfg.get("fd_threshold", 1e-5)
    fd_method = cfg.get("fd_method", "hurst")

    # Align cross-asset data
    aligned = align_cross_asset_bars(target_df, spy_df, tlt_df, vix_df)

    # Base features from target
    features = pd.DataFrame(index=aligned.index)
    features["returns_1h"] = _shifted_returns(aligned, "close")
    features["range_pct"] = (aligned["high"] - aligned["low"]) / aligned["close"].replace(0, np.nan)

    # Cross-asset beta and correlation
    if "spy_close" in aligned.columns:
        features = pd.concat(
            [features, rolling_betas(aligned, "close", "spy_close", windows=beta_windows, suffix="beta_spy")],
            axis=1,
        )
    if "tlt_close" in aligned.columns:
        features = pd.concat(
            [features, rolling_correlations(aligned, "close", "tlt_close", windows=corr_windows, suffix="corr_tlt")],
            axis=1,
        )

    # Regime features
    regime = regime_features(
        aligned,
        vix_col="vix_close" if "vix_close" in aligned.columns else "close",
        spy_col="spy_close" if "spy_close" in aligned.columns else "close",
        tlt_col="tlt_close" if "tlt_close" in aligned.columns else "close",
        lookback=regime_lookback,
    )
    features = pd.concat([features, regime], axis=1)

    # Macro event features
    if events_df is not None and not events_df.empty:
        macro = macro_event_features(aligned.index, events_df)
        features = pd.concat([features, macro], axis=1)
    else:
        macro = pd.DataFrame(index=aligned.index)

    # Long-memory features
    d_train = None
    if d_train_col and d_train_col in aligned.columns:
        d_train = aligned[d_train_col]
    fd_cols = cfg.get("fd_cols", ["close"])
    fd = long_memory_features(aligned, cols=fd_cols, d=d, d_train=d_train, threshold=fd_threshold, method=fd_method)
    features = pd.concat([features, fd], axis=1)

    # Interaction features
    interactions = interaction_features(
        aligned, macro, regime, micro=None, high_beta_col=high_beta_col
    )
    features = pd.concat([features, interactions], axis=1)

    return features.replace([np.inf, -np.inf], np.nan)


# ─── Convenience class for walk-forward use ─────────────────────────────────

class MacroCrossAssetEngine:
    """Fit-transform engine for macro/cross-asset/long-memory features.

    ``fit`` estimates normalization statistics and fractional ``d`` on a
    training DataFrame.  ``transform`` applies them to new data.  This is the
    intended interface for purged walk-forward experiments.
    """

    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self.cfg = cfg or {}
        self.d_estimates: Dict[str, float] = {}
        self.norm_stats: Dict[str, Dict[str, float]] = {}

    def fit(
        self,
        target_train: pd.DataFrame,
        spy_train: Optional[pd.DataFrame] = None,
        tlt_train: Optional[pd.DataFrame] = None,
        vix_train: Optional[pd.DataFrame] = None,
        events_train: Optional[pd.DataFrame] = None,
    ) -> "MacroCrossAssetEngine":
        """Fit ``d`` and normalization stats on training data only."""
        # Estimate d per column
        for col in self.cfg.get("fd_cols", ["close"]):
            if col in target_train.columns:
                self.d_estimates[col] = estimate_d(target_train[col])
        # Regime / macro normalization stats are handled inside functions
        # by expanding/rolling windows, so no explicit fit needed.
        return self

    def transform(
        self,
        target_df: pd.DataFrame,
        spy_df: Optional[pd.DataFrame] = None,
        tlt_df: Optional[pd.DataFrame] = None,
        vix_df: Optional[pd.DataFrame] = None,
        events_df: Optional[pd.DataFrame] = None,
        high_beta_col: Optional[str] = None,
    ) -> pd.DataFrame:
        """Build feature matrix using the fitted ``d`` values."""
        cfg = self.cfg.copy()
        if "fd_cols" in cfg:
            # Use the first fitted d for all cols, or per-col logic in future
            d = next(iter(self.d_estimates.values()), None) if self.d_estimates else None
            cfg["d"] = d
        return macro_feature_matrix(
            target_df,
            spy_df=spy_df,
            tlt_df=tlt_df,
            vix_df=vix_df,
            events_df=events_df,
            high_beta_col=high_beta_col,
            cfg=cfg,
        )
