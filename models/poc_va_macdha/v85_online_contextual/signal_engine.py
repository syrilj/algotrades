"""v85_online_contextual: causal online routing over a frozen expert bundle.

The model does not retrain a predictor on live outcomes.  It keeps the proven
signal generators frozen, evaluates their already-matured next-open utility,
and chooses the expert allowed to own the next flat-to-entry episode.  Market
context may select only at entry; stress may only reduce an open position.

`last_confidence` is posterior expert support, not a probability of profit.
The dependency manifest is verified before any expert is loaded so a mutable
sibling model cannot silently change this strategy.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

import numpy as np
import pandas as pd


CONFIDENCE_KIND = "ordinal_online_expert_support_not_probability"
CONTEXT_ONLY = {"VIX", "^VIX", "HYG.US", "LQD.US"}


class _NullCandidateLedger:
    """Prevent child research labels from being mistaken for v85 executions."""

    def record_entry(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    def record_exit(self, *args: Any, **kwargs: Any) -> None:
        return None

    def flush(self) -> None:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_repo_root(anchor: Path) -> Path:
    for parent in (anchor.resolve(), *anchor.resolve().parents):
        if (parent / "models" / "poc_va_macdha").is_dir() and (parent / "data_cache").is_dir():
            return parent
    raise RuntimeError("TradingAlgoWork repository root not found")


def _load_module(path: Path, label: str, *, exact_name: str | None = None) -> Any:
    name = exact_name or f"v85_{label}_{_sha256(path)[:12]}_{id(path)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {label} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        if sys.modules.get(name) is module:
            sys.modules.pop(name, None)
        raise
    return module


def _load_hunt(model_dir: Path) -> dict[str, Any]:
    path = model_dir / "hunt_config.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("hunt_config.json must contain an object")
    return payload


def _verify_bundle(model_dir: Path) -> tuple[dict[str, Path], str]:
    manifest_path = model_dir / "DEPENDENCIES.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("files")
    if not isinstance(items, list) or not items:
        raise RuntimeError("frozen dependency manifest is empty")

    resolved: dict[str, Path] = {}
    lock_rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError("invalid frozen dependency entry")
        source = item.get("source")
        target = item.get("target")
        expected = item.get("sha256")
        if not all(isinstance(value, str) and value for value in (source, target, expected)):
            raise RuntimeError("dependency source, target, and sha256 are required")
        target_rel = Path(target)
        if target_rel.is_absolute() or ".." in target_rel.parts:
            raise RuntimeError(f"unsafe dependency target: {target}")
        vendored = (model_dir / target_rel).resolve()
        source_path = (model_dir / source).resolve()
        path = vendored if vendored.is_file() else source_path
        if not path.is_file():
            raise RuntimeError(f"frozen dependency is missing: {target}")
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(
                f"frozen dependency hash mismatch for {target}: expected {expected}, got {actual}"
            )
        resolved[target] = path
        lock_rows.append({"target": target, "sha256": actual})

    lock_text = json.dumps(lock_rows, sort_keys=True, separators=(",", ":"))
    return resolved, hashlib.sha256(lock_text.encode("utf-8")).hexdigest()


def _canonical_code(value: str) -> str:
    code = str(value).strip().upper()
    if code in {"VIX", "^VIX"}:
        return code
    if "." not in code:
        return f"{code}.US"
    return code


def _canonicalize_data_map(
    data_map: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    canonical: dict[str, pd.DataFrame] = {}
    aliases: dict[str, str] = {}
    for raw_code, frame in data_map.items():
        code = _canonical_code(raw_code)
        aliases[str(raw_code)] = code
        if frame is None:
            continue
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{raw_code} data must be a DataFrame")
        if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
            raise ValueError(f"{raw_code} timestamps must be increasing and unique")
        existing = canonical.get(code)
        if existing is not None and existing is not frame and not existing.equals(frame):
            raise ValueError(f"conflicting alias frames for {code}")
        canonical[code] = frame
    return canonical, aliases


def _to_daily(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None or frame.empty or "close" not in frame.columns:
        return None
    data = frame.copy()
    data.index = pd.DatetimeIndex(pd.to_datetime(data.index))
    if data.index.tz is not None:
        data.index = data.index.tz_convert("America/New_York").tz_localize(None)
    close = data["close"].astype(float).resample("1D").last().dropna()
    return close.to_frame("close")


def _load_daily_cache(repo_root: Path, symbol: str) -> pd.DataFrame | None:
    path = repo_root / "data_cache" / "1d" / f"{symbol}.parquet"
    if not path.is_file():
        return None
    try:
        return _to_daily(pd.read_parquet(path))
    except Exception:
        return None


class SignalEngine:
    """Frozen dual/core/sniper experts with causal contextual Fixed Share."""

    def __init__(self) -> None:
        self.confidence_kind = CONFIDENCE_KIND
        self.options_policy = "activity_only_observation_no_directional_inference"
        self.state_mode = "deterministic_full_window_replay"
        self.model_dir = Path(__file__).resolve().parent
        self.repo_root = _find_repo_root(self.model_dir)
        self._hunt = _load_hunt(self.model_dir)
        dependencies, self.bundle_hash = _verify_bundle(self.model_dir)

        self._router_module = _load_module(dependencies["adaptive_router.py"], "adaptive_router")
        self._gates = _load_module(
            dependencies["experts/v71_live_confidence/gates.py"], "v71_gates"
        )
        v45_module = _load_module(
            dependencies["experts/v45_ultimate_rsi/signal_engine.py"], "v45"
        )
        self._v45 = v45_module.SignalEngine()

        previous_ledger = sys.modules.get("candidate_ledger")
        try:
            _load_module(
                dependencies["experts/v39d_confluence/candidate_ledger.py"],
                "candidate_ledger",
                exact_name="candidate_ledger",
            )
            core_module = _load_module(
                dependencies["experts/v39d_confluence/signal_engine.py"], "v39d"
            )
            self._core = core_module.SignalEngine()
        finally:
            if previous_ledger is None:
                sys.modules.pop("candidate_ledger", None)
            else:
                sys.modules["candidate_ledger"] = previous_ledger
        self._core._ledger = _NullCandidateLedger()

        router_cfg = dict(self._hunt.get("router") or {})
        self._router_config = self._router_module.RouterConfig(**router_cfg)
        self._prior = list(self._hunt.get("prior") or [0.62, 0.20, 0.13, 0.05])
        self._min_history_bars = int(self._hunt.get("min_history_bars", 800))
        self._dual_cfg = dict(self._hunt.get("dual") or {})
        self._sniper_cfg = dict(self._hunt.get("sniper") or {})

        self.last_confidence: Dict[str, pd.Series] = {}
        self.last_expert: Dict[str, pd.Series] = {}
        self.last_regime: Dict[str, pd.Series] = {}
        self.last_drift: Dict[str, pd.Series] = {}
        self.last_evidence: Dict[str, pd.Series] = {}
        self.last_context_quality: Dict[str, pd.Series] = {}
        self.last_support_margin: Dict[str, pd.Series] = {}
        self.last_readiness_reason: Dict[str, str] = {}

        self._vix_daily = _load_daily_cache(self.repo_root, "VIX")
        self._hyg_daily = _load_daily_cache(self.repo_root, "HYG")
        self._lqd_daily = _load_daily_cache(self.repo_root, "LQD")

    def _sniper_from_v45(
        self,
        data: pd.DataFrame,
        primary: pd.Series,
    ) -> tuple[pd.Series, pd.Series]:
        cfg = self._sniper_cfg
        index = data.index
        trend = self._gates.trend_mask(
            data["close"],
            lookback=int(cfg.get("trend_lookback", 250)),
            direction="above",
        )
        quality = self._gates.quality_score(data).reindex(index).fillna(0)
        quality_ok = quality >= int(cfg.get("min_quality", 1))
        quality_conf = (quality.astype(float) / 3.0).clip(0.0, 1.0)
        rsi_conf = self._gates.rsi_depth_confidence(data).reindex(index)
        confidence = self._gates.blend_confidence(
            quality_conf,
            rsi_conf,
            quality_weight=float(cfg.get("quality_weight", 0.65)),
            rsi_weight=float(cfg.get("rsi_weight", 0.35)),
        )
        return self._gates.apply_entry_only_soft(
            primary.reindex(index).fillna(0.0),
            trend=trend,
            quality_ok=quality_ok,
            confidence=confidence,
            close=data["close"].astype(float),
            base_scale=float(cfg.get("base_scale", 0.225)),
            min_scale_frac=float(cfg.get("min_scale_frac", 1.0)),
            max_scale_frac=float(cfg.get("max_scale_frac", 1.55)),
            max_scale_cap=float(cfg.get("max_scale_cap", 0.40)),
        )

    def _dual_signal(
        self,
        sniper: pd.Series,
        core: pd.Series,
        sniper_confidence: pd.Series,
    ) -> pd.Series:
        cfg = self._dual_cfg
        cap = float(cfg.get("max_weight", 0.50))
        core_scale = float(cfg.get("core_scale", 0.85))
        both_fraction = float(cfg.get("both_core_fraction", 0.35))
        minimum_confidence = float(cfg.get("sniper_min_confidence", 0.0))
        sniper_on = (sniper > 1e-9) & (sniper_confidence >= minimum_confidence)
        core_on = core > 1e-9
        both = sniper_on & core_on
        sniper_only = sniper_on & ~core_on
        core_only = core_on & ~sniper_on
        out = pd.Series(0.0, index=core.index)
        out = out.where(~sniper_only, sniper.clip(upper=cap))
        out = out.where(~core_only, (core * core_scale).clip(upper=cap))
        stacked = (sniper + both_fraction * core * core_scale).clip(upper=cap)
        return out.where(~both, stacked).astype(float)

    def _zero_diagnostics(self, code: str, index: pd.Index, reason: str) -> pd.Series:
        zero = pd.Series(0.0, index=index, dtype=float)
        self.last_confidence[code] = zero.copy()
        self.last_expert[code] = pd.Series("CASH", index=index, dtype=object)
        self.last_regime[code] = pd.Series(-1, index=index, dtype=int)
        self.last_drift[code] = pd.Series(False, index=index, dtype=bool)
        self.last_evidence[code] = pd.Series(0, index=index, dtype=int)
        self.last_context_quality[code] = zero.copy()
        self.last_support_margin[code] = zero.copy()
        self.last_readiness_reason[code] = reason
        return zero

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        canonical, aliases = _canonicalize_data_map(data_map)
        target_codes = [code for code in canonical if code not in CONTEXT_ONLY]
        expert_data = {code: canonical[code] for code in target_codes}

        self.last_confidence = {}
        self.last_expert = {}
        self.last_regime = {}
        self.last_drift = {}
        self.last_evidence = {}
        self.last_context_quality = {}
        self.last_support_margin = {}
        self.last_readiness_reason = {}

        ready_codes = [
            code
            for code in target_codes
            if not canonical[code].empty and len(canonical[code]) >= self._min_history_bars
        ]
        ready_data = {code: expert_data[code] for code in ready_codes}
        core_signals: dict[str, pd.Series] = {}
        v45_signals: dict[str, pd.Series] = {}
        if ready_data:
            try:
                core_signals = self._core.generate(ready_data)
                v45_signals = self._v45.generate(ready_data)
            except Exception as exc:
                raise RuntimeError(f"frozen expert generation failed: {exc}") from exc

        vix_input = canonical.get("VIX")
        if vix_input is None:
            vix_input = canonical.get("^VIX")
        vix_daily = _to_daily(vix_input) if vix_input is not None else self._vix_daily
        hyg_input = _to_daily(canonical.get("HYG.US"))
        lqd_input = _to_daily(canonical.get("LQD.US"))
        hyg_daily = hyg_input if hyg_input is not None else self._hyg_daily
        lqd_daily = lqd_input if lqd_input is not None else self._lqd_daily
        spy = canonical.get("SPY.US")

        canonical_output: dict[str, pd.Series] = {}
        for code, frame in canonical.items():
            if frame.empty:
                canonical_output[code] = self._zero_diagnostics(code, frame.index, "empty_frame")
                continue
            if code in CONTEXT_ONLY:
                canonical_output[code] = pd.Series(0.0, index=frame.index, dtype=float)
                continue
            if code not in ready_codes:
                canonical_output[code] = self._zero_diagnostics(
                    code,
                    frame.index,
                    f"need_at_least_{self._min_history_bars}_completed_bars",
                )
                continue

            index = frame.index
            core = core_signals.get(code, pd.Series(0.0, index=index)).reindex(index).fillna(0.0)
            primary = v45_signals.get(code, pd.Series(0.0, index=index)).reindex(index).fillna(0.0)
            sniper, sniper_conf = self._sniper_from_v45(frame, primary)
            dual = self._dual_signal(sniper, core, sniper_conf)
            context = self._router_module.build_causal_context(
                frame,
                spy=spy,
                vix_daily=vix_daily,
                hyg_daily=hyg_daily,
                lqd_daily=lqd_daily,
            )
            routed, diagnostics = self._router_module.route_experts(
                frame["open"].astype(float),
                {"DUAL": dual, "CORE": core, "SNIPER": sniper},
                context,
                config=self._router_config,
                prior=self._prior,
            )
            canonical_output[code] = routed
            self.last_confidence[code] = diagnostics["selected_weight"].astype(float)
            self.last_expert[code] = diagnostics["selected_name"].astype(str)
            self.last_regime[code] = diagnostics["context_bucket"].astype(int)
            # This is a primary-posterior alert, not a formal change detector.
            self.last_drift[code] = diagnostics["drift_warning"].astype(bool)
            self.last_evidence[code] = diagnostics["context_updates"].astype(int)
            self.last_context_quality[code] = diagnostics["context_quality"].astype(float)
            self.last_support_margin[code] = diagnostics["selected_support_margin"].astype(float)
            self.last_readiness_reason[code] = "ready"

        output: dict[str, pd.Series] = {}
        for alias, code in aliases.items():
            frame = data_map[alias]
            signal = canonical_output.get(code)
            output[alias] = (
                signal.reindex(frame.index).fillna(0.0).astype(float)
                if signal is not None
                else pd.Series(0.0, index=frame.index, dtype=float)
            )
            if alias != code and code in self.last_confidence:
                self.last_confidence[alias] = self.last_confidence[code]
                self.last_expert[alias] = self.last_expert[code]
                self.last_regime[alias] = self.last_regime[code]
                self.last_drift[alias] = self.last_drift[code]
                self.last_evidence[alias] = self.last_evidence[code]
                self.last_context_quality[alias] = self.last_context_quality[code]
                self.last_support_margin[alias] = self.last_support_margin[code]
                self.last_readiness_reason[alias] = self.last_readiness_reason[code]
        return output
