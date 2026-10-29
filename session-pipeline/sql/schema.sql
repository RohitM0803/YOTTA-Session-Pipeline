-- Target schema for the sessionization pipeline (SQLite).
-- Naming: snake_case tables/columns, ISO-8601 UTC timestamps ("YYYY-MM-DDTHH:MM:SSZ").
-- *_ts columns hold the same instant as Unix epoch seconds (used for fast, exact gap math).
-- Safe to run repeatedly: every statement is IF NOT EXISTS.

-- Reference table: users that are allowed to appear in events.
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY
);

-- One row per pipeline execution (the audit / observability log).
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id                TEXT PRIMARY KEY,
    started_at            TEXT NOT NULL,
    ended_at              TEXT,
    status                TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    input_files           TEXT,
    gap_seconds           INTEGER NOT NULL,
    rows_in               INTEGER,
    rows_rejected         INTEGER,
    rows_inserted         INTEGER,
    rows_skipped_existing INTEGER,
    late_events           INTEGER,
    users_affected        INTEGER,
    sessions_written      INTEGER,
    duration_seconds      REAL,
    failure_reason        TEXT,
    notes                 TEXT
);

-- Clean, de-duplicated events (the history we keep; never silently overwritten).
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    event_time  TEXT NOT NULL,
    event_ts    INTEGER NOT NULL,
    page        TEXT,
    source_file TEXT NOT NULL,
    source_row  INTEGER NOT NULL,
    run_id      TEXT NOT NULL REFERENCES pipeline_runs (run_id)
);
CREATE INDEX IF NOT EXISTS idx_events_user_ts ON events (user_id, event_ts, event_id);

-- Derived sessions (the analytical output). Rebuilt per affected user, never appended blindly.
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    session_start    TEXT NOT NULL,
    session_end      TEXT NOT NULL,
    session_start_ts INTEGER NOT NULL,
    session_end_ts   INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0),
    event_count      INTEGER NOT NULL CHECK (event_count >= 1),
    is_bounce        INTEGER NOT NULL CHECK (is_bounce IN (0, 1)),
    gap_seconds      INTEGER NOT NULL,
    run_id           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_start ON sessions (user_id, session_start_ts);

-- Quarantine: every rejected input record, traceable to file + line, per run.
CREATE TABLE IF NOT EXISTS rejected_events (
    reject_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    source_file   TEXT NOT NULL,
    source_row    INTEGER NOT NULL,
    reject_reason TEXT NOT NULL,
    reject_detail TEXT,
    raw_record    TEXT
);
CREATE INDEX IF NOT EXISTS idx_rejected_run ON rejected_events (run_id);
