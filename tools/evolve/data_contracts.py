"""Data tracks and claim levels — fail closed, never mix vanity boards."""
from __future__ import annotations

from enum import Enum
from typing import Any


class DataTrack(str, Enum):
    EQUITY_OHLCV = "equity_ohlcv"
    OPTIONS_SYNTHETIC = "options_synthetic"
    GEX_LIVE_ONLY = "gex_live_only"

    @property
    def may_auto_promote(self) -> bool:
        """Only equity OHLCV can auto-write WINNER / desk default."""
        return self is DataTrack.EQUITY_OHLCV

    @property
    def pricing_label(self) -> str:
        return {
            DataTrack.EQUITY_OHLCV: "exchange_ohlcv",
            DataTrack.OPTIONS_SYNTHETIC: "synthetic_bs",
            DataTrack.GEX_LIVE_ONLY: "live_snapshot_only",
        }[self]


class ClaimLevel(str, Enum):
    """Dual bars: thin research vs shippable claim."""

    THIN = "THIN"  # n < thin_max — log only
    RESEARCH = "RESEARCH"  # interesting; cannot ship
    CLAIM = "CLAIM"  # eligible for WINNER if other gates pass
    BLOCKED_DATA = "BLOCKED_DATA"  # track cannot support claim
    ERROR = "ERROR"


# Defaults aligned with PASS_BAR + ANTI_OVERFIT
THIN_MAX_EXCLUSIVE = 12  # n < 12
RESEARCH_MAX_EXCLUSIVE = 40  # 12 <= n < 40 → RESEARCH; n >= 40 can be CLAIM


def infer_track(mode: str, model_id: str = "") -> DataTrack:
    m = (mode or "").lower()
    mid = (model_id or "").lower()
    if m == "options" or "opts" in mid or "options" in mid:
        return DataTrack.OPTIONS_SYNTHETIC
    if "gex" in mid:
        return DataTrack.GEX_LIVE_ONLY
    return DataTrack.EQUITY_OHLCV


def claim_level_from_n(
    n: int,
    *,
    track: DataTrack,
    pass_bar_ok: bool | None = None,
    error: str | None = None,
    thin_max: int = THIN_MAX_EXCLUSIVE,
    research_max: int = RESEARCH_MAX_EXCLUSIVE,
) -> ClaimLevel:
    if error:
        return ClaimLevel.ERROR
    if track is DataTrack.GEX_LIVE_ONLY:
        return ClaimLevel.BLOCKED_DATA
    if n < thin_max:
        return ClaimLevel.THIN
    if n < research_max:
        return ClaimLevel.RESEARCH
    # n >= research_max
    if track is DataTrack.OPTIONS_SYNTHETIC:
        # Options never auto-CLAIM for ship; research ceiling unless explicit override
        return ClaimLevel.RESEARCH
    if pass_bar_ok is False:
        return ClaimLevel.RESEARCH
    if pass_bar_ok is True:
        return ClaimLevel.CLAIM
    # unknown pass_bar → still CLAIM-eligible by sample size only
    return ClaimLevel.CLAIM


def annotate_row(row: dict[str, Any]) -> dict[str, Any]:
    """Attach track + claim_level to a metrics row (mutates copy)."""
    out = dict(row)
    mode = str(out.get("mode") or "daily")
    mid = str(out.get("id") or out.get("model") or "")
    track = infer_track(mode, mid)
    if out.get("data_track"):
        try:
            track = DataTrack(str(out["data_track"]))
        except ValueError:
            pass
    n = int(out.get("n") or out.get("trade_count") or 0)
    err = out.get("error")
    pb = out.get("pass_bar")
    if isinstance(pb, dict):
        pb_ok = bool(pb.get("passed"))
    elif isinstance(pb, bool):
        pb_ok = pb
    else:
        pb_ok = None
    level = claim_level_from_n(n, track=track, pass_bar_ok=pb_ok, error=str(err) if err else None)
    out["data_track"] = track.value
    out["pricing"] = track.pricing_label
    out["claim_level"] = level.value
    out["may_auto_promote"] = bool(
        track.may_auto_promote and level is ClaimLevel.CLAIM and not err
    )
    return out


def board_label(track: DataTrack | str, claim: ClaimLevel | str) -> str:
    t = track.value if isinstance(track, DataTrack) else str(track)
    c = claim.value if isinstance(claim, ClaimLevel) else str(claim)
    return f"{t} · {c}"
