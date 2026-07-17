"""Conservative normalization for LSE/Vault options activity snapshots.

The Vault options surface can be polled repeatedly.  Its ``volume`` field is
therefore treated as a cumulative per-contract session counter, *not* as a new
trade size on every response.  Rows are normalized, de-duplicated, ordered by
contract and market timestamp, and converted to non-negative activity
increments.

This module intentionally does not create a directional trading signal.  A
call contract is not evidence that a customer bought to open, and neither
aggressor side, opening/closing status, nor dealer inventory is inferred from
contract type, volume, price, or premium.  Invalid, incomplete, stale, or
otherwise ambiguous input fails closed to a neutral/abstain result.

The implementation uses only the Python standard library and performs no
network I/O, which keeps it suitable for both historical replays and the live
runtime boundary.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Optional


DEFAULT_STALE_AFTER = timedelta(minutes=15)
DEFAULT_FUTURE_TOLERANCE = timedelta(minutes=5)

_TIMESTAMP_KEYS = (
    "timestamp",
    "ts",
    "datetime",
    "time",
    "trade_time",
    "last_trade_time",
    "updated_at",
    "market_asof",
    "asof",
)
_VOLUME_KEYS = (
    "cumulative_volume",
    "volume_today",
    "day_volume",
    "total_volume",
    "volume",
    "contracts",
)
_EXPLICIT_CONTRACT_KEYS = ("contract_id", "option_id", "option_symbol", "contract")
_TICKER_KEYS = ("ticker", "symbol")
_UNDERLYING_KEYS = ("underlying", "underlying_symbol", "root", "underlier")
_EXPIRY_KEYS = ("expiry", "expiration", "expiration_date", "expiry_date")
_RIGHT_KEYS = ("right", "type", "option_type", "contract_type")
_STRIKE_KEYS = ("strike", "strike_price")

# Compact OSI/OCC form after removal of the optional ``O:`` prefix and spaces.
_OSI_RE = re.compile(r"^([A-Z0-9.]{1,6})(\d{6})([CP])(\d{8})$")


def _pick(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _finite_number(value: Any, *, allow_zero: bool = True) -> Optional[float]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if number < 0 or (not allow_zero and number <= 0):
        return None
    return number


def _timestamp_datetime(value: Any) -> Optional[datetime]:
    """Parse common Vault timestamps and return an aware UTC datetime.

    Naive provider strings are interpreted as UTC.  Numeric Unix timestamps in
    seconds, milliseconds, microseconds, or nanoseconds are also accepted.
    """

    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        magnitude = abs(number)
        if magnitude >= 1e17:  # nanoseconds
            number /= 1e9
        elif magnitude >= 1e14:  # microseconds
            number /= 1e6
        elif magnitude >= 1e11:  # milliseconds
            number /= 1e3
        try:
            parsed = datetime.fromtimestamp(number, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
            try:
                return _timestamp_datetime(float(text))
            except ValueError:
                return None
        normalized = text.replace(" ", "T", 1)
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _iso_utc(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_timestamp(value: Any) -> Optional[str]:
    """Return a canonical UTC ISO-8601 timestamp, or ``None`` if invalid."""

    parsed = _timestamp_datetime(value)
    return _iso_utc(parsed) if parsed is not None else None


def _normalize_expiry(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or value == "":
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{6}", text):
        text = f"20{text[:2]}-{text[2:4]}-{text[4:]}"
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _normalize_right(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if text in {"c", "call", "calls"}:
        return "C"
    if text in {"p", "put", "puts"}:
        return "P"
    return None


def _normalize_root(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if text.endswith(".US"):
        text = text[:-3]
    text = re.sub(r"\s+", "", text)
    return text if text and re.fullmatch(r"[A-Z0-9.]+", text) else None


def _osi_parts(value: Any) -> Optional[tuple[str, str, str, float, str]]:
    text = str(value or "").strip().upper()
    if text.startswith("O:"):
        text = text[2:]
    text = re.sub(r"\s+", "", text)
    match = _OSI_RE.fullmatch(text)
    if match is None:
        return None
    root, yymmdd, right, raw_strike = match.groups()
    expiry = _normalize_expiry(yymmdd)
    if expiry is None:
        return None
    strike = int(raw_strike) / 1000.0
    if strike <= 0:
        return None
    canonical = f"{root}{yymmdd}{right}{raw_strike}"
    return root, expiry, right, strike, canonical


def _component_contract(row: Mapping[str, Any]) -> Optional[tuple[str, str, str, float, str]]:
    root = _normalize_root(_pick(row, _UNDERLYING_KEYS))
    if root is None:
        # A plain ticker/symbol may provide the root when full option components
        # are present.  An OSI ticker is handled separately before this path.
        ticker = _pick(row, _TICKER_KEYS)
        root = _normalize_root(ticker) if _osi_parts(ticker) is None else None
    expiry = _normalize_expiry(_pick(row, _EXPIRY_KEYS))
    right = _normalize_right(_pick(row, _RIGHT_KEYS))
    strike_value = _pick(row, _STRIKE_KEYS)
    strike = _finite_number(strike_value, allow_zero=False)
    if root is None or expiry is None or right is None or strike is None:
        return None

    try:
        strike_mills = int(
            (Decimal(str(strike_value)) * Decimal("1000")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    except (InvalidOperation, TypeError, ValueError):
        return None
    yymmdd = expiry[2:4] + expiry[5:7] + expiry[8:10]
    if len(root) <= 6 and strike_mills <= 99_999_999:
        canonical = f"{root}{yymmdd}{right}{strike_mills:08d}"
    else:
        canonical = f"{root}|{expiry}|{right}|{strike:g}"
    return root, expiry, right, strike, canonical


def _contract_parts(row: Mapping[str, Any]) -> Optional[tuple[Optional[str], Optional[str], Optional[str], Optional[float], str]]:
    for key in (*_EXPLICIT_CONTRACT_KEYS, *_TICKER_KEYS):
        raw = row.get(key)
        parsed = _osi_parts(raw)
        if parsed is not None:
            return parsed

    components = _component_contract(row)
    if components is not None:
        return components

    # Explicit IDs are allowed to be provider-native opaque identifiers.  A
    # plain equity ticker is not: it would merge every option for an underlying.
    for key in _EXPLICIT_CONTRACT_KEYS:
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        canonical = re.sub(r"\s+", "", str(raw).strip().upper())
        if canonical:
            return None, None, None, None, canonical
    return None


def normalize_contract_id(value: Any) -> Optional[str]:
    """Normalize an OSI/provider contract ID or construct one from a row.

    Mapping input may contain either a full contract identifier or the
    underlying/expiry/right/strike components.  A plain underlying ticker alone
    is rejected because it is not unique at the option-contract level.
    """

    if isinstance(value, Mapping):
        parts = _contract_parts(value)
        return parts[4] if parts is not None else None
    parsed = _osi_parts(value)
    if parsed is not None:
        return parsed[4]
    text = re.sub(r"\s+", "", str(value or "").strip().upper())
    return text or None


def _duration(value: Any, default: timedelta) -> timedelta:
    if isinstance(value, timedelta):
        return value if value.total_seconds() >= 0 else default
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(seconds) or seconds < 0:
        return default
    return timedelta(seconds=seconds)


def _unwrap_rows(raw: Any) -> tuple[list[Any], Optional[str]]:
    if raw is None:
        return [], "missing_input"
    if isinstance(raw, Mapping):
        for key in ("data", "rows", "results"):
            wrapped = raw.get(key)
            if isinstance(wrapped, (list, tuple)):
                return list(wrapped), None
        return [], "invalid_input_container"
    if isinstance(raw, (str, bytes)):
        return [], "invalid_input_container"
    try:
        return list(raw), None
    except TypeError:
        return [], "invalid_input_container"


def normalize_options_activity(
    rows: Any,
    *,
    now: Any = None,
    stale_after: Any = DEFAULT_STALE_AFTER,
    future_tolerance: Any = DEFAULT_FUTURE_TOLERANCE,
) -> dict[str, Any]:
    """Build a fail-closed options-activity context from Vault snapshots.

    The first snapshot for each contract on each UTC session date contributes
    its observed cumulative volume.  Later snapshots contribute
    ``max(current - previous, 0)``.  A same-session counter decrease contributes
    zero and establishes the new baseline for subsequent observations.

    The returned rows and aggregates describe activity only.  The directional
    signal is always neutral/abstain because this data contract does not observe
    aggressor, opening/closing, or dealer side.
    """

    evaluated_at = _timestamp_datetime(now) if now is not None else datetime.now(timezone.utc)
    if evaluated_at is None:
        evaluated_at = datetime.now(timezone.utc)
        invalid_now = True
    else:
        invalid_now = False
    stale_limit = _duration(stale_after, DEFAULT_STALE_AFTER)
    future_limit = _duration(future_tolerance, DEFAULT_FUTURE_TOLERANCE)

    raw_rows, input_error = _unwrap_rows(rows)
    invalid_reasons: Counter[str] = Counter()
    if input_error:
        invalid_reasons[input_error] += 1
    if invalid_now:
        invalid_reasons["invalid_evaluation_time"] += 1

    candidates: list[dict[str, Any]] = []
    required_present = Counter({"contract_id": 0, "timestamp": 0, "cumulative_volume": 0})

    for source_index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            invalid_reasons["row_not_mapping"] += 1
            continue

        parts = _contract_parts(raw_row)
        if parts is None:
            invalid_reasons["missing_or_invalid_contract_id"] += 1
        else:
            required_present["contract_id"] += 1

        raw_timestamp = _pick(raw_row, _TIMESTAMP_KEYS)
        timestamp = _timestamp_datetime(raw_timestamp)
        if timestamp is None:
            invalid_reasons["missing_or_invalid_timestamp"] += 1
        else:
            required_present["timestamp"] += 1

        raw_volume = _pick(raw_row, _VOLUME_KEYS)
        volume = _finite_number(raw_volume)
        if volume is None:
            invalid_reasons["missing_or_invalid_cumulative_volume"] += 1
        else:
            required_present["cumulative_volume"] += 1

        if parts is None or timestamp is None or volume is None:
            continue

        underlying, expiry, right, strike, contract_id = parts
        price = _finite_number(
            _pick(raw_row, ("price", "trade_price", "last", "last_price", "mid")),
            allow_zero=False,
        )
        open_interest = _finite_number(_pick(raw_row, ("open_interest", "openInterest")))
        candidates.append(
            {
                "source_index": source_index,
                "contract_id": contract_id,
                "timestamp_dt": timestamp,
                "timestamp": _iso_utc(timestamp),
                "session_date": timestamp.date().isoformat(),
                "underlying": underlying,
                "expiry": expiry,
                "option_type": "call" if right == "C" else ("put" if right == "P" else None),
                "right": right,
                "strike": strike,
                "cumulative_volume": volume,
                "price": price,
                "open_interest": open_interest,
            }
        )

    # One observation per normalized contract/timestamp.  Conflicting snapshots
    # at the same key are ambiguous; retain the lower counter conservatively and
    # mark the entire context non-actionable.
    by_key: dict[tuple[str, datetime], dict[str, Any]] = {}
    duplicate_rows_removed = 0
    conflicting_duplicate_keys = 0
    for candidate in candidates:
        key = (candidate["contract_id"], candidate["timestamp_dt"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = candidate
            continue
        duplicate_rows_removed += 1
        if candidate["cumulative_volume"] != existing["cumulative_volume"]:
            conflicting_duplicate_keys += 1
            if candidate["cumulative_volume"] < existing["cumulative_volume"]:
                by_key[key] = candidate

    normalized = sorted(
        by_key.values(),
        key=lambda item: (item["contract_id"], item["timestamp_dt"], item["source_index"]),
    )

    previous: dict[str, tuple[str, float]] = {}
    same_session_volume_decreases = 0
    total_increment = 0.0
    type_increments = {"call": 0.0, "put": 0.0, "unknown": 0.0}
    for item in normalized:
        prior = previous.get(item["contract_id"])
        basis = "session_baseline"
        if prior is None or prior[0] != item["session_date"]:
            increment = item["cumulative_volume"]
        else:
            delta = item["cumulative_volume"] - prior[1]
            if delta < 0:
                same_session_volume_decreases += 1
                increment = 0.0
                basis = "counter_decrease_clamped"
            else:
                increment = delta
                basis = "snapshot_delta"
        previous[item["contract_id"]] = (item["session_date"], item["cumulative_volume"])
        item["volume_increment"] = increment
        item["increment_basis"] = basis
        # These fields are explicitly unknown even if similarly named raw input
        # fields were supplied; the normalizer does not certify their semantics.
        item["aggressor_side"] = None
        item["opening_closing"] = None
        item["dealer_direction"] = None
        item["directionality"] = "unknown"
        total_increment += increment
        type_increments[item["option_type"] or "unknown"] += increment

    for item in normalized:
        item.pop("timestamp_dt", None)
        item.pop("source_index", None)

    latest_dt = max(
        (_timestamp_datetime(item["timestamp"]) for item in normalized),
        default=None,
    )
    if latest_dt is None:
        freshness_status = "unknown"
        age_seconds = None
        is_stale = True
        is_future = False
    else:
        age_seconds = (evaluated_at - latest_dt).total_seconds()
        is_future = age_seconds < -future_limit.total_seconds()
        is_stale = is_future or age_seconds > stale_limit.total_seconds()
        freshness_status = "future" if is_future else ("stale" if is_stale else "fresh")

    input_count = len(raw_rows)
    required_total = input_count * 3
    required_found = sum(required_present.values())
    required_field_ratio = required_found / required_total if required_total else 0.0
    invalid_row_count = input_count - len(candidates)
    schema_complete = (
        input_count > 0
        and invalid_row_count == 0
        and conflicting_duplicate_keys == 0
        and input_error is None
    )
    if schema_complete:
        completeness_status = "complete_required_fields"
    elif candidates:
        completeness_status = "partial_required_fields"
    else:
        completeness_status = "missing_required_fields"

    quality_issues: list[str] = []
    quality_issues.extend(sorted(invalid_reasons.elements()))
    if duplicate_rows_removed:
        quality_issues.append("duplicate_contract_timestamp_rows_removed")
    if conflicting_duplicate_keys:
        quality_issues.append("conflicting_contract_timestamp_rows")
    if same_session_volume_decreases:
        quality_issues.append("same_session_cumulative_volume_decrease")
    if not candidates:
        quality_status = "invalid"
    elif invalid_reasons or conflicting_duplicate_keys or same_session_volume_decreases:
        quality_status = "degraded"
    else:
        quality_status = "good"

    data_valid = quality_status == "good" and schema_complete
    fresh_and_valid = data_valid and freshness_status == "fresh"
    abstain_reasons: list[str] = []
    if not data_valid:
        abstain_reasons.append("invalid_or_incomplete_options_activity")
    if freshness_status != "fresh":
        abstain_reasons.append(f"options_activity_{freshness_status}")
    abstain_reasons.append("directionality_not_observed")

    call_increment = type_increments["call"]
    put_increment = type_increments["put"]
    known_type_total = call_increment + put_increment
    call_share = call_increment / known_type_total if known_type_total > 0 else None

    return {
        "ok": fresh_and_valid,
        "source": "lse_vault_options_activity",
        "methodology": "cumulative_contract_snapshot_deltas",
        "asof_utc": _iso_utc(latest_dt) if latest_dt is not None else None,
        "evaluated_at_utc": _iso_utc(evaluated_at),
        "rows": normalized,
        "activity": {
            "total_volume_increment": total_increment,
            "call_volume_increment": call_increment,
            "put_volume_increment": put_increment,
            "unknown_type_volume_increment": type_increments["unknown"],
            "call_share_of_known_type_activity": call_share,
            "interpretation": "contract_activity_only_not_trade_direction",
        },
        "data_quality": {
            "status": quality_status,
            "input_rows": input_count,
            "valid_rows_before_deduplication": len(candidates),
            "normalized_rows": len(normalized),
            "invalid_rows": invalid_row_count,
            "duplicate_rows_removed": duplicate_rows_removed,
            "conflicting_duplicate_keys": conflicting_duplicate_keys,
            "same_session_volume_decreases": same_session_volume_decreases,
            "issues": quality_issues,
        },
        "freshness": {
            "status": freshness_status,
            "asof_utc": _iso_utc(latest_dt) if latest_dt is not None else None,
            "evaluated_at_utc": _iso_utc(evaluated_at),
            "age_seconds": age_seconds,
            "stale_after_seconds": stale_limit.total_seconds(),
            "future_tolerance_seconds": future_limit.total_seconds(),
            "is_stale": is_stale,
            "is_future": is_future,
        },
        "completeness": {
            "status": completeness_status,
            "required_fields": ["contract_id", "timestamp", "cumulative_volume"],
            "required_field_ratio": required_field_ratio,
            "valid_row_ratio": len(candidates) / input_count if input_count else 0.0,
            "required_fields_complete": schema_complete,
            # A page of valid rows does not prove full-market/tape coverage.
            "tape_completeness": "unknown",
            "tape_complete": None,
        },
        "signal": {
            "stance": "neutral",
            "direction": "neutral",
            "action": "abstain",
            "abstain": True,
            "bullish_supported": False,
            "bearish_supported": False,
            "semantic_label": "neutral_activity_only_bullish_unsupported",
            "reasons": abstain_reasons,
        },
        # Convenient fail-closed fields for consumers that do not inspect the
        # nested signal contract.
        "bias": "neutral",
        "bullish_supported": False,
        "bearish_supported": False,
        "actionable": False,
        "abstain": True,
        "limitations": [
            "volume_is_a_cumulative_snapshot_not_an_individual_trade_size",
            "aggressor_side_not_observed_or_inferred",
            "opening_closing_not_observed_or_inferred",
            "dealer_direction_not_observed_or_inferred",
            "call_put_contract_type_does_not_imply_bullish_bearish_direction",
        ],
    }


# Readable integration aliases.  All return the same complete context object.
normalize_options_flow_context = normalize_options_activity
build_options_flow_context = normalize_options_activity
normalize_lse_options_activity = normalize_options_activity


__all__ = [
    "DEFAULT_FUTURE_TOLERANCE",
    "DEFAULT_STALE_AFTER",
    "build_options_flow_context",
    "normalize_contract_id",
    "normalize_lse_options_activity",
    "normalize_options_activity",
    "normalize_options_flow_context",
    "normalize_timestamp",
]
