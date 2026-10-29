"""Shared constants: column names, reject reasons and error types.

Keeping these in one place means validation, storage, tests and docs all
use exactly the same vocabulary.
"""
from __future__ import annotations

REQUIRED_COLUMNS = ("event_id", "user_id", "event_type", "event_time")
OPTIONAL_COLUMNS = ("page",)
CANONICAL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Text values that mean "no value" (compared case-insensitively after strip()).
NULL_TOKENS = frozenset({"", "null", "none", "nan", "n/a"})

# Timestamps outside this year range are treated as invalid (guards against 1970 / 9999 placeholders).
MIN_YEAR = 2000
MAX_YEAR = 2100

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Reason:
    """Stable reject-reason codes written to rejected_events.reject_reason."""

    MALFORMED_ROW = "malformed_row"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    MISSING_TIMESTAMP = "missing_timestamp"
    INVALID_TIMESTAMP = "invalid_timestamp"
    INVALID_REFERENCE_KEY = "invalid_reference_key"
    DUPLICATE_EVENT = "duplicate_event"
    CONFLICTING_DUPLICATE_EVENT = "conflicting_duplicate_event"

    ALL = (
        MALFORMED_ROW,
        MISSING_REQUIRED_FIELD,
        MISSING_TIMESTAMP,
        INVALID_TIMESTAMP,
        INVALID_REFERENCE_KEY,
        DUPLICATE_EVENT,
        CONFLICTING_DUPLICATE_EVENT,
    )


class SchemaError(Exception):
    """The whole file/batch cannot be processed (e.g. a required column is missing)."""


class QualityGateError(Exception):
    """Too many records were rejected; the run is failed and nothing is loaded."""
