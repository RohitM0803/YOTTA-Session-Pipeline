"""The core business rule: split one user's events into sessions by inactivity gap.

A new session starts when the time since the PREVIOUS event is strictly greater
than gap_seconds. A gap of exactly gap_seconds stays in the same session.
Events are ordered by (event_ts, event_id) so out-of-order input and identical
timestamps always give the same answer.
"""
from __future__ import annotations

import hashlib
from typing import List, Sequence

from .models import Session, SessionEvent


def make_session_id(user_id: str, session_start: str) -> str:
    """Deterministic ID: the same user + start time always gives the same ID."""
    digest = hashlib.sha1(f"{user_id}|{session_start}".encode("utf-8")).hexdigest()
    return "ses_" + digest[:16]


def sessionize(user_id: str, events: Sequence[SessionEvent], gap_seconds: int) -> List[Session]:
    if gap_seconds < 1:
        raise ValueError("gap_seconds must be >= 1")
    ordered = sorted(events, key=lambda e: (e.event_ts, e.event_id))
    sessions: List[Session] = []
    start = end = None  # SessionEvent of first/last event in the open session
    count = 0

    def close() -> None:
        duration = end.event_ts - start.event_ts
        sessions.append(Session(
            session_id=make_session_id(user_id, start.event_time), user_id=user_id,
            session_start=start.event_time, session_end=end.event_time,
            session_start_ts=start.event_ts, session_end_ts=end.event_ts,
            duration_seconds=duration, event_count=count, is_bounce=1 if count == 1 else 0,
            gap_seconds=gap_seconds))

    for ev in ordered:
        if start is not None and ev.event_ts - end.event_ts > gap_seconds:
            close()
            start = None
            count = 0
        if start is None:
            start = ev
        end = ev
        count += 1
    if start is not None:
        close()
    return sessions
