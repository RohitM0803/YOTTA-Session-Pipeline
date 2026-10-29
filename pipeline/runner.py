"""Orchestrates one pipeline run: read -> validate -> de-duplicate -> load -> build sessions.

Safety properties
  * Everything that changes data (users, events, sessions, run counters) happens in ONE
    database transaction: either the whole run is applied or none of it is.
  * Re-running the same input changes nothing (events are keyed by event_id; sessions are
    rebuilt only for users that received new events).
  * A failed run is still recorded (status FAILED + failure_reason) and its rejects are kept
    for diagnosis, but no events/sessions from it are visible.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import store
from .config import Config
from .dedupe import dedupe_batch
from .ingest import read_source, read_user_ids
from .models import Reject, RunResult, SessionEvent, ValidEvent
from .schema import QualityGateError, Reason, SchemaError
from .sessionize import sessionize
from .validate import validate_all

log = logging.getLogger("pipeline")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]


def rebuild_sessions(conn, user_ids: Sequence[str], gap_seconds: int, run_id: str) -> int:
    """Recompute sessions from the full stored event history for the given users."""
    written = 0
    for part in store.chunks(list(user_ids)):
        rows = store.fetch_events(conn, part)
        sessions = []
        for user_id, group in groupby(rows, key=itemgetter(0)):
            events = [SessionEvent(event_id=r[1], event_time=r[2], event_ts=r[3]) for r in group]
            sessions.extend(sessionize(user_id, events, gap_seconds))
        store.replace_sessions(conn, part, sessions, run_id)
        written += len(sessions)
    return written


def run_pipeline(cfg: Config, inputs: List[str], users_path: Optional[str] = None,
                 run_id: Optional[str] = None) -> RunResult:
    """Run the pipeline once. Never raises for data problems; returns a RunResult with status."""
    cfg.validate()
    run_id = run_id or new_run_id()
    result = RunResult(run_id=run_id)
    conn = store.connect(cfg.db_path)
    store.init_db(conn)
    started_at = utc_now_iso()
    t_start = time.perf_counter()
    store.start_run(conn, run_id, started_at, [Path(p).as_posix() for p in inputs], cfg.gap_seconds)
    log.info("run_id=%s started inputs=%s gap_seconds=%d", run_id, inputs, cfg.gap_seconds)
    rejects: List[Reject] = []

    def tick(stage: str, since: float) -> float:
        now = time.perf_counter()
        result.timings[stage] = round(now - since, 4)
        return now

    try:
        # ---- 1. read & validate files (no database writes yet)
        t = time.perf_counter()
        user_ids = read_user_ids(users_path) if users_path else []
        raw_records, extra_columns = [], set()
        for path in inputs:
            ingested = read_source(path, cfg.column_map)
            raw_records.extend(ingested.records)
            rejects.extend(ingested.rejects)
            extra_columns |= ingested.extra_columns
            result.rows_in += ingested.rows_read
        if extra_columns:
            result.notes["ignored_extra_columns"] = sorted(extra_columns)
            log.warning("run_id=%s ignoring unexpected columns: %s", run_id, sorted(extra_columns))
        t = tick("read", t)

        conn.execute("BEGIN IMMEDIATE")
        if users_path:
            result.notes["users_added"] = store.load_users(conn, user_ids)
        

        known = store.known_users(conn)

        # An explicitly supplied users file enables reference validation,
        # even when it contains no user IDs.
        if known is None and users_path:
            known = set()

        if known is None:
            result.notes["reference_check"] = "skipped (no users loaded)"

        valid, bad = validate_all(raw_records, known)
        rejects.extend(bad)
        t = tick("validate", t)

        unique, dupes = dedupe_batch(valid)
        rejects.extend(dupes)
        t = tick("dedupe", t)

        # ---- 2. compare with what is already stored (idempotency / conflicts)
        stored = store.existing_events(conn, [e.event_id for e in unique])
        new_events: List[ValidEvent] = []
        for ev in unique:
            hit = stored.get(ev.event_id)
            if hit is None:
                new_events.append(ev)
            elif hit[0] == ev.content_key():
                result.rows_skipped_existing += 1
            else:
                rejects.append(
                    Reject(
                        ev.source_file,
                        ev.source_row,
                        Reason.CONFLICTING_DUPLICATE_EVENT,
                        f"event_id already stored (run {hit[1]}) with different content; "
                        f"stored version kept",
                        ev.raw_record,
                    )
                )

        result.rows_rejected = len(rejects)
        result.rows_inserted = len(new_events)
        for r in rejects:
            result.rejects_by_reason[r.reason] = (
                result.rejects_by_reason.get(r.reason, 0) + 1
            )
        t = tick("classify", t)

        # ---- 3. quality gate
        if result.rows_in and result.rows_rejected / result.rows_in > cfg.max_reject_rate:
            raise QualityGateError(
                f"reject_rate_exceeded: {result.rows_rejected}/{result.rows_in} rows rejected "
                f"({result.rows_rejected / result.rows_in:.1%}) > allowed {cfg.max_reject_rate:.1%}"
            )

        # ---- 4. load events and rebuild affected sessions
        affected = sorted({e.user_id for e in new_events})
        previous_max = store.max_ts_by_user(conn, affected)
        result.late_events = sum(
            1 for e in new_events
            if e.user_id in previous_max and e.event_ts < previous_max[e.user_id]
        )
        store.insert_events(conn, new_events, run_id)
        t = tick("insert_events", t)

        gaps = store.session_gaps_in_use(conn)
        if gaps and gaps != {cfg.gap_seconds}:
            affected = store.all_event_user_ids(conn)
            result.notes["full_rebuild_reason"] = (
                f"gap changed from {sorted(gaps)} to {cfg.gap_seconds} seconds"
            )
            log.warning("run_id=%s %s", run_id, result.notes["full_rebuild_reason"])

        result.users_affected = len(affected)
        result.sessions_written = rebuild_sessions(conn, affected, cfg.gap_seconds, run_id)
        t = tick("sessionize", t)

        # ---- 5. record rejects and success in the same transaction
        store.insert_rejects(conn, rejects, run_id)
        result.duration_seconds = time.perf_counter() - t_start
        result.status = "SUCCESS"
        store.finish_run(conn, run_id, "SUCCESS", utc_now_iso(), result, None)
        conn.execute("COMMIT")
        log.info(
            "run_id=%s SUCCESS in=%d inserted=%d skipped_existing=%d rejected=%d sessions=%d (%.2fs)",
            run_id, result.rows_in, result.rows_inserted, result.rows_skipped_existing,
            result.rows_rejected, result.sessions_written, result.duration_seconds
        )
        conn.close()

    except Exception as exc:  # noqa: BLE001 - any failure must be recorded, then reported
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        reason = str(exc) if isinstance(
            exc, (SchemaError, QualityGateError, FileNotFoundError)
        ) else f"{type(exc).__name__}: {exc}"
        if isinstance(exc, FileNotFoundError) and not reason.startswith("input_not_found"):
            reason = f"input_not_found: {exc}"

        result.status = "FAILED"
        result.failure_reason = reason
        result.rows_rejected = len(rejects)
        result.rows_inserted = result.sessions_written = result.users_affected = 0
        result.duration_seconds = time.perf_counter() - t_start
        log.error("run_id=%s FAILED: %s", run_id, reason)

        try:
            conn.execute("BEGIN IMMEDIATE")
            store.insert_rejects(conn, rejects, run_id)
            store.finish_run(conn, run_id, "FAILED", utc_now_iso(), result, reason)
            conn.execute("COMMIT")
        except Exception:  # noqa: BLE001
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            log.exception("run_id=%s could not record failure", run_id)
        finally:
            conn.close()

    return result
