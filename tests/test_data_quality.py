import pandas as pd

from tools.data_quality import validate_frame


def _valid_frame():
    return pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [12.0, 12.0],
            "low": [9.0, 10.0],
            "close": [11.0, 11.5],
            "volume": [100.0, 120.0],
        },
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )


def test_valid_ohlcv_contract_passes():
    assert validate_frame(_valid_frame(), symbol="TEST") == []


def test_ohlcv_contract_rejects_duplicates_and_impossible_high():
    frame = _valid_frame()
    frame.index = pd.to_datetime(["2026-01-01", "2026-01-01"])
    frame.loc[frame.index[-1], "high"] = 5.0
    errors = validate_frame(frame, symbol="TEST")
    assert "TEST:duplicate_timestamps" in errors
    assert "TEST:high_inconsistent" in errors

