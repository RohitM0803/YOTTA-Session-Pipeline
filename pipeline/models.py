"""Plain data containers passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class RawRecord:
    """One data row exactly as read from a file (values still untrusted strings)."""

    source_file: str
    source_row: int  # 1-based physical line number in the source file
    data: Dict[str, Optional[str]]
    raw_text: str  # JSON text of the original record, kept for the quarantine table


@dataclass(frozen=True)
class Reject:
    """A record that was set aside, with enough information to trace it back."""

    source_file: str
    source_row: int
    reason: str
    detail: str
    raw_record: str


@dataclass(frozen=True)
class ValidEvent:
    """A record that passed validation, with normalised values."""

    event_id: str
    user_id: str
    event_type: str
    event_time: str  # ISO-8601 UTC, e.g. 2026-01-01T10:00:00Z
    event_ts: int  # same instant as Unix epoch seconds
    page: Optional[str]
    source_file: str
    source_row: int
    raw_record: str

    def content_key(self):
        """Business content used to tell an exact duplicate from a conflicting one."""
        return (self.user_id, self.event_type, self.event_time, self.page)


@dataclass(frozen=True)
class SessionEvent:
    event_id: str
    event_time: str
    event_ts: int


@dataclass(frozen=True)
class Session:
    session_id: str
    user_id: str
    session_start: str
    session_end: str
    session_start_ts: int
    session_end_ts: int
    duration_seconds: int
    event_count: int
    is_bounce: int
    gap_seconds: int


@dataclass
class RunResult:
    run_id: str
    status: str = "RUNNING"
    rows_in: int = 0
    rows_rejected: int = 0
    rows_inserted: int = 0
    rows_skipped_existing: int = 0
    late_events: int = 0
    users_affected: int = 0
    sessions_written: int = 0
    duration_seconds: float = 0.0
    failure_reason: Optional[str] = None
    rejects_by_reason: Dict[str, int] = field(default_factory=dict)
    timings: Dict[str, float] = field(default_factory=dict)
    notes: Dict[str, object] = field(default_factory=dict)
