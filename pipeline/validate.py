"""Row-level validation and normalisation.

Rules are checked in a fixed order and a record gets exactly ONE reject reason
(the first rule it breaks), so results are deterministic:

  1. missing_required_field   event_id / user_id / event_type blank or null-like
  2. missing_timestamp        event_time blank or null-like
  3. invalid_timestamp        event_time not an ISO-8601 date-time, or outside 2000-2100
  4. invalid_reference_key    user_id not in the known users (only if users are known)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional, Set, Tuple, Union

from .models import RawRecord, Reject, ValidEvent
from .schema import MAX_YEAR, MIN_YEAR, NULL_TOKENS, TIMESTAMP_FORMAT, Reason

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def clean_text(value: Optional[str]) -> Optional[str]:
    """Strip whitespace; return None for null-like values."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in NULL_TOKENS else text


def parse_timestamp(value: str) -> Tuple[str, int]:
    """Parse an ISO-8601 date-time into (UTC 'YYYY-MM-DDTHH:MM:SSZ', epoch_seconds).

    Accepts 'Z' or numeric offsets (+05:30). A timestamp with no offset is assumed UTC.
    Sub-second precision is truncated to whole seconds. Raises ValueError if invalid.
    """
    text = value.strip()
    # Require a time part: reject date-only values and plain numbers such as epoch seconds.
    if len(text) < 11 or text[10] not in "T ":
        raise ValueError("expected ISO-8601 date-time like 2026-01-31T10:15:00Z")
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"cannot parse as ISO-8601: {exc}")
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise ValueError(f"year {parsed.year} outside supported range {MIN_YEAR}-{MAX_YEAR}")
    return parsed.strftime(TIMESTAMP_FORMAT), int((parsed - _EPOCH).total_seconds())


def validate_record(record: RawRecord, known_users: Optional[Set[str]] = None) -> Union[ValidEvent, Reject]:
    """Return a ValidEvent, or a Reject describing the first rule broken."""

    def reject(reason: str, detail: str) -> Reject:
        return Reject(record.source_file, record.source_row, reason, detail, record.raw_text)

    data = record.data
    event_id = clean_text(data.get("event_id"))
    user_id = clean_text(data.get("user_id"))
    event_type = clean_text(data.get("event_type"))
    missing = [name for name, val in (("event_id", event_id), ("user_id", user_id), ("event_type", event_type))
               if val is None]
    if missing:
        return reject(Reason.MISSING_REQUIRED_FIELD, f"missing: {', '.join(missing)}")

    raw_time = clean_text(data.get("event_time"))
    if raw_time is None:
        return reject(Reason.MISSING_TIMESTAMP, "event_time is blank or null")
    try:
        event_time, event_ts = parse_timestamp(raw_time)
    except ValueError as exc:
        return reject(Reason.INVALID_TIMESTAMP, f"{raw_time!r}: {exc}")

    if known_users is not None and user_id not in known_users:
        return reject(Reason.INVALID_REFERENCE_KEY, f"user_id {user_id!r} not found in users")

    return ValidEvent(
        event_id=event_id, user_id=user_id, event_type=event_type, event_time=event_time,
        event_ts=event_ts, page=clean_text(data.get("page")),
        source_file=record.source_file, source_row=record.source_row, raw_record=record.raw_text,
    )


def validate_all(records: Iterable[RawRecord], known_users: Optional[Set[str]]) -> Tuple[List[ValidEvent], List[Reject]]:
    valid: List[ValidEvent] = []
    rejects: List[Reject] = []
    for rec in records:
        out = validate_record(rec, known_users)
        (valid if isinstance(out, ValidEvent) else rejects).append(out)
    return valid, rejects
