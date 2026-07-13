"""v41_ensemble_feedback: meta-ensemble with multiple feedback modes.

Modes:
  - sgd_binary / sgd_proba: online SGD classifier on forward-return labels.
  - sgd_regression: online SGD regressor on forward returns, scaled to [0,1].
  - perf_weighted: rolling performance-weighted blend of teacher engines.

All modes use only past information. They are iterative feedback loops: the
market provides the outcome, and the meta learner adjusts every bar.
"""

import importlib.util
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Literal-only top-level config (backtest runner AST sandbox compatibility).
_DEFAULT_HUNT = {
    "base_models": ["v39b_live_adapt", "v39d_confluence", "v12_regime_router"],
    "mode": "perf_weighted",
    "forward_bars": 3,
    "target_threshold": 0.0,
    "warmup": 80,
    "learning_rate": 0.02,
    "alpha": 0.0001,
    "loss": "log_loss",
    "feature_deltas": True,
    "feature_extra": True,
    "fallback": "v39b_live_adapt",
    "proba_threshold": 0.5,
    "signal_mode": "binary",
    "return_scale": 100.0,
    "perf_lookback": 60,
    "perf_temperature": 0.5,
    "perf_min_weight": 0.0,
    "perf_forward": 1,
    "perf_metric": "raw_return",
}


def _find_repo_root(anchor: Path) -> Path:
    for p in anchor.resolve().parents:
        if (p / "models" / "poc_va_macdha").exists():
            return p
    raise RuntimeError("Could not find TradingAlgoWork repo root")


def _load_base_engine(repo_root: Path, model_dir_name: str):
    """Import the SignalEngine class from a sibling model directory."""
    path = repo_root / "models" / "poc_va_macdha" / model_dir_name / "signal_engine.py"
    if not path.exists():
        raise FileNotFoundError(f"Base engine {model_dir_name} not found at {path}")
    module_name = f"base_{model_dir_name.replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[arg-type]
    return mod.SignalEngine()


def _softmax(weights: np.ndarray, temperature: float) -> np.ndarray:
    """Numerically stable softmax over the last axis."""
    weights = np.asarray(weights, dtype=float)
    if weights.ndim == 1:
        weights = weights.reshape(1, -1)
    scaled = weights * temperature
    scaled = scaled - np.max(scaled, axis=1, keepdims=True)
    expw = np.exp(scaled)
    s = expw / np.maximum(np.sum(expw, axis=1, keepdims=True), 1e-12)
    if s.shape[0] == 1 and weights.shape[0] == 1:
        return s[0]
    return s


class SignalEngine:
    """Multi-mode meta-ensemble over top swing engines."""

    def __init__(self):
        # Locate hunt config.
        self_dir = Path(__file__).resolve().parent
        hunt_path = self_dir / "hunt_config.json"
        if hunt_path.exists():
            self._hunt = json.loads(hunt_path.read_text(encoding="utf-8"))
        else:
            self._hunt = dict(_DEFAULT_HUNT)

        # Hyperparameters.
        self._base_model_names: List[str] = list(self._hunt.get("base_models", _DEFAULT_HUNT["base_models"]))
        self._mode: str = str(self._hunt.get("mode", _DEFAULT_HUNT["mode"]))
        self._forward_bars: int = int(self._hunt.get("forward_bars", _DEFAULT_HUNT["forward_bars"]))
        self._target_threshold: float = float(self._hunt.get("target_threshold", _DEFAULT_HUNT["target_threshold"]))
        self._warmup: int = int(self._hunt.get("warmup", _DEFAULT_HUNT["warmup"]))
        self._lr: float = float(self._hunt.get("learning_rate", _DEFAULT_HUNT["learning_rate"]))
        self._alpha: float = float(self._hunt.get("alpha", _DEFAULT_HUNT["alpha"]))
        self._loss: str = str(self._hunt.get("loss", _DEFAULT_HUNT["loss"]))
        self._feature_deltas: bool = bool(self._hunt.get("feature_deltas", _DEFAULT_HUNT["feature_deltas"]))
        self._feature_extra: bool = bool(self._hunt.get("feature_extra", _DEFAULT_HUNT["feature_extra"]))
        self._fallback: str = str(self._hunt.get("fallback", _DEFAULT_HUNT["fallback"]))
        self._proba_threshold: float = float(self._hunt.get("proba_threshold", _DEFAULT_HUNT["proba_threshold"]))
        self._signal_mode: str = str(self._hunt.get("signal_mode", _DEFAULT_HUNT["signal_mode"]))
        self._return_scale: float = float(self._hunt.get("return_scale", _DEFAULT_HUNT["return_scale"]))
        self._perf_lookback: int = int(self._hunt.get("perf_lookback", _DEFAULT_HUNT["perf_lookback"]))
        self._perf_temperature: float = float(self._hunt.get("perf_temperature", _DEFAULT_HUNT["perf_temperature"]))
        self._perf_min_weight: float = float(self._hunt.get("perf_min_weight", _DEFAULT_HUNT["perf_min_weight"]))
        self._perf_forward: int = int(self._hunt.get("perf_forward", _DEFAULT_HUNT["perf_forward"]))
        self._perf_metric: str = str(self._hunt.get("perf_metric", _DEFAULT_HUNT["perf_metric"]))

        # Load teacher engines.
        repo_root = _find_repo_root(self_dir)
        self._engines: Dict[str, object] = {}
        self._engine_order: List[str] = []
        for name in self._base_model_names:
            try:
                self._engines[name] = _load_base_engine(repo_root, name)
                self._engine_order.append(name)
            except Exception as exc:
                print(f"[v41] warning: could not load base engine {name}: {exc}")

        # Lazy sklearn imports.
        if self._mode in ("sgd_binary", "sgd_proba"):
            from sklearn.linear_model import SGDClassifier
            self._sgd_classifier = SGDClassifier
        if self._mode == "sgd_regression":
            from sklearn.linear_model import SGDRegressor
            self._sgd_regressor = SGDRegressor

    def _build_features(
        self,
        code: str,
        close: pd.Series,
        volume: pd.Series,
        sigs: Dict[str, pd.Series],
        spy_close: Optional[pd.Series] = None,
        qqq_close: Optional[pd.Series] = None,
        df: Optional[pd.DataFrame] = None,
    ) -> np.ndarray:
        """Build (n_bars, n_features) matrix for one symbol."""
        idx = close.index
        sigs_df = pd.DataFrame({k: v.reindex(idx).fillna(0.0).astype(float) for k, v in sigs.items()})

        parts = [sigs_df]

        if self._feature_deltas:
            deltas = sigs_df.diff(1).fillna(0.0)
            deltas.columns = [f"{c}_delta" for c in deltas.columns]
            parts.append(deltas)

        if self._feature_extra:
            close_ret = close.pct_change(self._forward_bars).fillna(0.0)
            vol_ret = volume.pct_change(self._forward_bars).fillna(0.0)
            extra = pd.DataFrame(
                {
                    "close_ret": close_ret,
                    "vol_ret": vol_ret,
                },
                index=idx,
            )
            if spy_close is not None and not spy_close.empty:
                spy_ret = spy_close.pct_change(self._forward_bars).reindex(idx).fillna(0.0)
                extra["spy_ret"] = spy_ret
            if qqq_close is not None and not qqq_close.empty:
                qqq_ret = qqq_close.pct_change(self._forward_bars).reindex(idx).fillna(0.0)
                extra["qqq_ret"] = qqq_ret

            # richer market features
            close_ret_1 = close.pct_change(1).fillna(0.0)
            extra["volatility"] = close_ret_1.rolling(20, min_periods=1).std().fillna(0.0)
            extra["close_sma20"] = (close / close.rolling(20, min_periods=1).mean() - 1.0).fillna(0.0)
            extra["volume_sma20"] = (volume / volume.rolling(20, min_periods=1).mean() - 1.0).fillna(0.0)
            if df is not None:
                high = df["high"].astype(float)
                low = df["low"].astype(float)
                open_ = df["open"].astype(float)
                extra["open_ret"] = open_.pct_change(self._forward_bars).fillna(0.0)
                extra["high_ret"] = high.pct_change(self._forward_bars).fillna(0.0)
                extra["low_ret"] = low.pct_change(self._forward_bars).fillna(0.0)
                extra["close_to_open"] = (close / open_ - 1.0).fillna(0.0)
                extra["range"] = ((high - low) / close).fillna(0.0)

            # signal-market interactions
            sig_names = list(sigs_df.columns)
            for sig_name in sig_names:
                extra[f"{sig_name}_x_close_ret"] = sigs_df[sig_name] * close_ret
                extra[f"{sig_name}_x_vol"] = sigs_df[sig_name] * extra["volume_sma20"]
            # signal-signal interactions for first few pairs
            for i in range(min(3, len(sig_names))):
                for j in range(i + 1, min(3, len(sig_names))):
                    extra[f"{sig_names[i]}_x_{sig_names[j]}"] = sigs_df[sig_names[i]] * sigs_df[sig_names[j]]

            parts.append(extra)

        X = pd.concat(parts, axis=1).replace([np.inf, -np.inf], 0.0).fillna(0.0).to_numpy(dtype=float)
        return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    def _generate_sgd(self, close: pd.Series, sigs: Dict[str, pd.Series], X: np.ndarray, idx: pd.Index) -> pd.Series:
        """SGD classifier (binary/proba) mode."""
        forward_ret = close.pct_change(self._forward_bars).shift(-self._forward_bars)
        y = (forward_ret > self._target_threshold).astype(int).fillna(0).to_numpy(dtype=int)

        n_bars = len(idx)
        signals = np.zeros(n_bars, dtype=float)
        fb_sig = sigs.get(self._fallback, sigs.get(self._engine_order[0]))
        fb_sig = fb_sig.reindex(idx).fillna(0.0).to_numpy(dtype=float)

        max_warmup = min(self._warmup, n_bars)
        signals[:max_warmup] = fb_sig[:max_warmup]

        from sklearn.linear_model import SGDClassifier

        model = SGDClassifier(
            loss=self._loss,
            penalty="l2",
            alpha=self._alpha,
            learning_rate="constant",
            eta0=self._lr,
            shuffle=False,
            random_state=42,
            max_iter=1,
            tol=None,
            warm_start=False,
        )

        # Causal initial batch: only use labels whose forward horizon is
        # already known (i <= warmup - forward_bars - 1).
        train_end = max(0, max_warmup - self._forward_bars - 1)
        if train_end > 0:
            model.partial_fit(X[:train_end], y[:train_end], classes=[0, 1])

        for t in range(max_warmup, n_bars):
            # Update the model with the latest realized sample (target uses close[t-1]).
            update_idx = t - self._forward_bars - 1
            if update_idx >= 0:
                model.partial_fit(X[update_idx].reshape(1, -1), np.array([y[update_idx]]))

            proba = model.predict_proba(X[t].reshape(1, -1))[0]
            if self._signal_mode == "binary":
                signals[t] = 1.0 if proba[1] > self._proba_threshold else 0.0
            else:
                signals[t] = proba[1]

        return pd.Series(signals, index=idx).clip(0.0, 1.0)

    def _generate_regression(self, close: pd.Series, sigs: Dict[str, pd.Series], X: np.ndarray, idx: pd.Index) -> pd.Series:
        """SGD regressor on forward return, scaled to [0,1]."""
        forward_ret = close.pct_change(self._forward_bars).shift(-self._forward_bars)
        y = np.nan_to_num(forward_ret.to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)

        n_bars = len(idx)
        signals = np.zeros(n_bars, dtype=float)
        fb_sig = sigs.get(self._fallback, sigs.get(self._engine_order[0]))
        fb_sig = fb_sig.reindex(idx).fillna(0.0).to_numpy(dtype=float)

        max_warmup = min(self._warmup, n_bars)
        signals[:max_warmup] = fb_sig[:max_warmup]

        from sklearn.linear_model import SGDRegressor

        model = SGDRegressor(
            loss="squared_error",
            penalty="l2",
            alpha=self._alpha,
            learning_rate="constant",
            eta0=self._lr,
            shuffle=False,
            random_state=42,
            max_iter=1,
            tol=None,
            warm_start=False,
        )

        # Causal initial batch: only use labels whose forward horizon is
        # already known (i <= warmup - forward_bars - 1).
        train_end = max(0, max_warmup - self._forward_bars - 1)
        if train_end > 0:
            model.partial_fit(X[:train_end], y[:train_end])

        for t in range(max_warmup, n_bars):
            # Update the model with the latest realized sample (target uses close[t-1]).
            update_idx = t - self._forward_bars - 1
            if update_idx >= 0:
                model.partial_fit(X[update_idx].reshape(1, -1), np.array([y[update_idx]]))

            pred = float(model.predict(X[t].reshape(1, -1))[0])
            signals[t] = max(0.0, min(1.0, pred * self._return_scale))

        return pd.Series(signals, index=idx).clip(0.0, 1.0)

    def _generate_perf_weighted(
        self, close: pd.Series, sigs: Dict[str, pd.Series], idx: pd.Index
    ) -> pd.Series:
        """Rolling performance-weighted blend of teacher engines.

        Each bar the realized 1-bar (or perf_forward) return of each teacher
        signal is computed, summed over a lookback, and softmaxed into weights.
        The current bar's signal is the weighted average of the teachers' signals.
        """
        n_bars = len(idx)
        n_models = len(self._engine_order)
        sig_array = np.zeros((n_bars, n_models), dtype=float)
        for i, name in enumerate(self._engine_order):
            s = sigs[name].reindex(idx).fillna(0.0).to_numpy(dtype=float)
            sig_array[:, i] = s

        # Single-bar forward return.
        ret = close.pct_change(self._perf_forward).shift(-self._perf_forward).fillna(0.0).to_numpy(dtype=float)
        ret = np.nan_to_num(ret, nan=0.0, posinf=0.0, neginf=0.0)

        # Realized PnL for model i at bar t: signal at t-perf_forward held
        # for perf_forward bars.
        realized = np.zeros((n_bars, n_models), dtype=float)
        for t in range(self._perf_forward, n_bars):
            realized[t] = sig_array[t - self._perf_forward] * ret[t - self._perf_forward]

        signals = np.zeros(n_bars, dtype=float)
        fb_sig = sigs.get(self._fallback, sigs.get(self._engine_order[0]))
        fb_sig = fb_sig.reindex(idx).fillna(0.0).to_numpy(dtype=float)

        max_warmup = min(self._warmup, n_bars)
        signals[:max_warmup] = fb_sig[:max_warmup]

        for t in range(max_warmup, n_bars):
            start = max(0, t - self._perf_lookback)
            window = realized[start:t]
            scores = self._score_perf(window)
            # If all scores are zero (no recent edge), fall back to equal weights.
            if np.all(scores == 0):
                weights = np.ones(n_models, dtype=float) / n_models
            else:
                weights = _softmax(scores, self._perf_temperature)
                weights = np.maximum(weights, self._perf_min_weight)
                weights = weights / np.maximum(np.sum(weights), 1e-12)

            signals[t] = float(np.dot(weights, sig_array[t]))

        return pd.Series(signals, index=idx).clip(0.0, 1.0)

    def _score_perf(self, window: np.ndarray) -> np.ndarray:
        """Convert a (window_len, n_models) realized-return array to per-model scores."""
        n_models = window.shape[1]
        if window.shape[0] < 2:
            return np.zeros(n_models, dtype=float)

        metric = self._perf_metric
        if metric == "raw_return":
            return np.sum(window, axis=0)

        if metric == "sharpe":
            mean = np.mean(window, axis=0)
            std = np.std(window, axis=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                score = np.where(std > 1e-12, mean / std, 0.0)
            return score

        if metric == "sortino":
            mean = np.mean(window, axis=0)
            downside = window.copy()
            downside[downside > 0] = 0.0
            std_down = np.sqrt(np.mean(downside ** 2, axis=0))
            with np.errstate(divide="ignore", invalid="ignore"):
                score = np.where(std_down > 1e-12, mean / std_down, 0.0)
            return score

        if metric == "calmar" or metric == "return_per_dd":
            total = np.sum(window, axis=0)
            cum = np.cumsum(window, axis=0)
            peak = np.maximum.accumulate(cum, axis=0)
            dd = peak - cum
            max_dd = np.max(dd, axis=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                score = np.where(max_dd > 1e-12, total / max_dd, 0.0)
            return score

        return np.sum(window, axis=0)

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """Generate meta-ensemble signals for all symbols in data_map."""
        if not self._engines:
            raise RuntimeError("No base engines loaded")

        base_signals: Dict[str, Dict[str, pd.Series]] = {}
        for name, engine in self._engines.items():
            try:
                base_signals[name] = engine.generate(data_map)
            except Exception as exc:
                print(f"[v41] warning: base engine {name} failed: {exc}")
                base_signals[name] = {}

        if self._fallback not in self._engines:
            self._fallback = self._engine_order[0]

        spy_close = None
        if "SPY.US" in data_map and not data_map["SPY.US"].empty:
            spy_close = data_map["SPY.US"]["close"].astype(float)
        qqq_close = None
        if "QQQ.US" in data_map and not data_map["QQQ.US"].empty:
            qqq_close = data_map["QQQ.US"]["close"].astype(float)

        out: Dict[str, pd.Series] = {}

        for code, df in data_map.items():
            if df is None or df.empty or len(df) < self._warmup + self._forward_bars + 2:
                out[code] = pd.Series(0.0, index=df.index)
                continue

            close = df["close"].astype(float)
            volume = df.get("volume", pd.Series(1.0, index=close.index)).astype(float)
            idx = close.index

            sigs: Dict[str, pd.Series] = {}
            for name in self._engine_order:
                sig = base_signals[name].get(code)
                if sig is None or sig.empty:
                    sig = pd.Series(0.0, index=idx)
                sigs[name] = sig

            if self._mode == "perf_weighted":
                out[code] = self._generate_perf_weighted(close, sigs, idx)
            else:
                X = self._build_features(code, close, volume, sigs, spy_close, qqq_close, df)
                if self._mode == "sgd_regression":
                    out[code] = self._generate_regression(close, sigs, X, idx)
                else:
                    out[code] = self._generate_sgd(close, sigs, X, idx)

        return out
