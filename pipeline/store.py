"""All SQLite access lives here (so SQL is easy to find, review and test)."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .models import Reject, Session, ValidEvent

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
CHUNK = 500  # max ids per "IN (...)" query; stays far below SQLite's variable limit


def chunks(items: Sequence, size: int = CHUNK) -> Iterator[Sequence]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def connect(db_path: str) -> sqlite3.Connection:
    """Open the database. Autocommit mode: we start/commit transactions explicitly."""
    if db_path != ":memory:":
        parent = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- run log
def start_run(conn, run_id: str, started_at: str, input_files: List[str], gap_seconds: int) -> None:
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, started_at, status, input_files, gap_seconds) VALUES (?,?,?,?,?)",
        (run_id, started_at, "RUNNING", json.dumps(input_files), gap_seconds))


def finish_run(conn, run_id: str, status: str, ended_at: str, result, failure_reason: Optional[str]) -> None:
    conn.execute(
        """UPDATE pipeline_runs SET ended_at=?, status=?, rows_in=?, rows_rejected=?, rows_inserted=?,
           rows_skipped_existing=?, late_events=?, users_affected=?, sessions_written=?,
           duration_seconds=?, failure_reason=?, notes=? WHERE run_id=?""",
        (ended_at, status, result.rows_in, result.rows_rejected, result.rows_inserted,
         result.rows_skipped_existing, result.late_events, result.users_affected, result.sessions_written,
         round(result.duration_seconds, 4), failure_reason, json.dumps(result.notes, sort_keys=True), run_id))


# ---------------------------------------------------------------- users
def load_users(conn, user_ids: Iterable[str]) -> int:
    before = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.executemany("INSERT OR IGNORE INTO users (user_id) VALUES (?)", [(u,) for u in user_ids])
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] - before


def known_users(conn) -> Optional[Set[str]]:
    """The set of valid user ids, or None when no users were ever loaded (reference check disabled)."""
    ids = {row[0] for row in conn.execute("SELECT user_id FROM users")}
    return ids or None


# ---------------------------------------------------------------- events
def existing_events(conn, event_ids: Sequence[str]) -> Dict[str, Tuple[tuple, str]]:
    """Map event_id -> (content_key, run_id) for events already stored."""
    found: Dict[str, Tuple[tuple, str]] = {}
    for part in chunks(list(event_ids)):
        marks = ",".join("?" * len(part))
        for eid, user_id, etype, etime, page, run_id in conn.execute(
                f"SELECT event_id, user_id, event_type, event_time, page, run_id FROM events "
                f"WHERE event_id IN ({marks})", list(part)):
            found[eid] = ((user_id, etype, etime, page), run_id)
    return found


def max_ts_by_user(conn, user_ids: Sequence[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for part in chunks(list(user_ids)):
        marks = ",".join("?" * len(part))
        for user_id, max_ts in conn.execute(
                f"SELECT user_id, MAX(event_ts) FROM events WHERE user_id IN ({marks}) GROUP BY user_id", list(part)):
            result[user_id] = max_ts
    return result


def insert_events(conn, events: Sequence[ValidEvent], run_id: str) -> None:
    conn.executemany(
        """INSERT INTO events (event_id, user_id, event_type, event_time, event_ts, page,
           source_file, source_row, run_id) VALUES (?,?,?,?,?,?,?,?,?)""",
        [(e.event_id, e.user_id, e.event_type, e.event_time, e.event_ts, e.page,
          e.source_file, e.source_row, run_id) for e in events])


def all_event_user_ids(conn) -> List[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT user_id FROM events ORDER BY user_id")]


def fetch_events(conn, user_ids: Sequence[str]) -> List[tuple]:
    """Events for the given users ordered by user, time, id: (user_id, event_id, event_time, event_ts)."""
    marks = ",".join("?" * len(user_ids))
    return conn.execute(
        f"SELECT user_id, event_id, event_time, event_ts FROM events WHERE user_id IN ({marks}) "
        f"ORDER BY user_id, event_ts, event_id", list(user_ids)).fetchall()


# ---------------------------------------------------------------- sessions
def session_gaps_in_use(conn) -> Set[int]:
    return {r[0] for r in conn.execute("SELECT DISTINCT gap_seconds FROM sessions")}


def replace_sessions(conn, user_ids: Sequence[str], sessions: Sequence[Session], run_id: str) -> None:
    """Delete these users' sessions and insert the freshly computed ones (caller owns the transaction)."""
    marks = ",".join("?" * len(user_ids))
    conn.execute(f"DELETE FROM sessions WHERE user_id IN ({marks})", list(user_ids))
    conn.executemany(
        """INSERT INTO sessions (session_id, user_id, session_start, session_end, session_start_ts,
           session_end_ts, duration_seconds, event_count, is_bounce, gap_seconds, run_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [(s.session_id, s.user_id, s.session_start, s.session_end, s.session_start_ts, s.session_end_ts,
          s.duration_seconds, s.event_count, s.is_bounce, s.gap_seconds, run_id) for s in sessions])


# ---------------------------------------------------------------- rejects
def insert_rejects(conn, rejects: Sequence[Reject], run_id: str) -> None:
    conn.executemany(
        """INSERT INTO rejected_events (run_id, source_file, source_row, reject_reason, reject_detail, raw_record)
           VALUES (?,?,?,?,?,?)""",
        [(run_id, r.source_file, r.source_row, r.reason, r.detail, r.raw_record) for r in rejects])
