"""Duplicate handling inside one batch.

Rule: the FIRST occurrence of an event_id (in input order) is kept.
Later occurrences are rejected:
  * identical business content   -> duplicate_event
  * different business content   -> conflicting_duplicate_event
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .models import Reject, ValidEvent
from .schema import Reason


def dedupe_batch(events: List[ValidEvent]) -> Tuple[List[ValidEvent], List[Reject]]:
    first_seen: Dict[str, ValidEvent] = {}
    unique: List[ValidEvent] = []
    rejects: List[Reject] = []
    for ev in events:
        kept = first_seen.get(ev.event_id)
        if kept is None:
            first_seen[ev.event_id] = ev
            unique.append(ev)
            continue
        where = f"{kept.source_file}:{kept.source_row}"
        if ev.content_key() == kept.content_key():
            rejects.append(Reject(ev.source_file, ev.source_row, Reason.DUPLICATE_EVENT,
                                  f"same event_id and content as {where}", ev.raw_record))
        else:
            rejects.append(Reject(ev.source_file, ev.source_row, Reason.CONFLICTING_DUPLICATE_EVENT,
                                  f"same event_id as {where} but different content; first occurrence kept",
                                  ev.raw_record))
    return unique, rejects
