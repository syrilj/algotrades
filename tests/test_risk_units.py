import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import trade_desk  # noqa: E402


def _state():
    return {
        "risk_per_share": 2.0,
        "sleeve_fraction": 1.0,
        "price": 100.0,
        "setup_ok": True,
        "trail_arm": 106.0,
        "symbol": "TESTSYM",
        "model": "test_model",
    }


def test_half_percent_risk_on_10k_is_50_dollars():
    sz = trade_desk._position_math(_state(), account=10_000.0, risk_pct=0.005)
    assert sz["risk_budget"] == 50.0
    assert sz["shares"] == 25            # 50 // 2.0
    assert sz["dollar_risk"] == 50.0
    assert sz["risk_pct"] == 0.005       # fraction, not percent points
