"""Re-export shared causal drawdown risk helpers for dmr run_code copies."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_shared():
    here = Path(__file__).resolve().parent
    # Prefer local copy (when dmr DEPENDENCIES vendored the file)
    local = here / "drawdown_risk.py"
    if local.exists():
        name = f"v72_drawdown_risk_{id(local)}"
        if name in sys.modules:
            return sys.modules[name]
        spec = importlib.util.spec_from_file_location(name, local)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        return mod
    # Fall back to repo _shared
    for p in here.resolve().parents:
        shared = p / "models" / "poc_va_macdha" / "_shared" / "drawdown_risk.py"
        if shared.exists():
            name = f"v72_drawdown_risk_{id(shared)}"
            if name in sys.modules:
                return sys.modules[name]
            spec = importlib.util.spec_from_file_location(name, shared)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("drawdown_risk helpers not found")


_m = _load_shared()

drawdown_from_peak = _m.drawdown_from_peak
lagged_returns = _m.lagged_returns
realized_vol = _m.realized_vol
vol_ratio = _m.vol_ratio
below_ma = _m.below_ma
rolling_corr = _m.rolling_corr
dd_stress = _m.dd_stress
vol_stress = _m.vol_stress
composite_risk_score = _m.composite_risk_score
size_multiplier = _m.size_multiplier
apply_size_mult = _m.apply_size_mult
risk_state_label = _m.risk_state_label
default_params = _m.default_params
score_from_data_map = _m.score_from_data_map
