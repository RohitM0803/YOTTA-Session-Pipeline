# Data Dictionary

Stored timestamps use ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). Tables and columns are snake_case. Input event timestamps may include an offset or omit it; offsets are converted to UTC, and an omitted offset is treated as UTC.

## How the pipeline reads the data

The event file is the source of activity. A users file is optional; supplied user IDs are added to the database's accumulated reference list. The pipeline validates events, keeps the first valid occurrence of an event ID, stores new events, and derives sessions from stored event history.

- CSV files need the required columns in their header. A row with the wrong number of fields is rejected. JSON Lines files contain one flat JSON object per non-blank line; malformed JSON and nested values are rejected.
- Required values are checked in a fixed order, and each rejected row receives one reason: missing required fields, missing timestamp, invalid timestamp, then invalid user reference. Duplicate checks happen after validation.
- If users have been loaded, event user IDs are checked against the users stored in the database. Supplying a users file enables checking even on a fresh database. An empty file on a fresh database therefore rejects every event user ID; on a populated database it adds no users, and previously stored users remain valid.
- Events are ordered by `(event_ts, event_id)`. A new session starts only when the gap from the previous event is greater than `gap_seconds`; an exact gap stays in the same session.
- Source file and line number are retained so an event or rejection can be traced back to its input. Blank lines are skipped. A CSV header is line 1; for a quoted CSV record spanning multiple lines, the recorded line is where the parser finishes that record. JSON Lines uses the line containing the record.

## Source: events file (`.csv` or `.jsonl`)

Grain: one row = one user event. Column order is irrelevant; names are trimmed and case-insensitive; `column_map` in the
config can rename source columns.

| Column | Required | Type | Rules |
|---|---|---|---|
| `event_id` | yes | text | unique per event; blank/null-like rejected; first occurrence wins |
| `user_id` | yes | text | must exist in `users` when a users list is loaded |
| `event_type` | yes | text | any non-blank value (e.g. `page_view`, `click`) |
| `event_time` | yes | ISO-8601 date-time | offsets converted to UTC; no offset = UTC; fractional seconds truncated (can affect ordering and gap boundaries); year 2000-2100 |
| `page` | no | text | null-like becomes NULL |
| other columns | - | - | ignored, listed in the run notes |

Null-like text (case-insensitive, after trimming): empty, `null`, `none`, `nan`, `n/a`.

## Source: users file (`users.csv`)

| Column | Required | Notes |
|---|---|---|
| `user_id` | yes | reference list; blank ids skipped; duplicates ignored |

## Target tables (`sql/schema.sql`)

### `users` - reference data
| Column | Type | Constraint |
|---|---|---|
| `user_id` | TEXT | PRIMARY KEY |

### `events` - clean, de-duplicated event history (never overwritten)
Grain: one row per unique `event_id`.

| Column | Type | Constraint / meaning |
|---|---|---|
| `event_id` | TEXT | PRIMARY KEY |
| `user_id` | TEXT | NOT NULL |
| `event_type` | TEXT | NOT NULL |
| `event_time` | TEXT | NOT NULL, normalised ISO-8601 UTC |
| `event_ts` | INTEGER | NOT NULL, same instant as Unix epoch seconds (derived) |
| `page` | TEXT | nullable |
| `source_file` | TEXT | NOT NULL, file the event was first loaded from |
| `source_row` | INTEGER | NOT NULL, physical line number in that file |
| `run_id` | TEXT | NOT NULL, FOREIGN KEY to `pipeline_runs`; run that loaded it |

`source_file` and `source_row` identify where the stored event first appeared. A later identical copy is skipped; a later conflicting copy is rejected and does not replace the stored event.

Index: `(user_id, event_ts, event_id)`.

### `sessions` - derived output
Grain: one row per user session. Rebuilt per affected user (delete + insert in the run transaction).

| Column | Type | Meaning |
|---|---|---|
| `session_id` | TEXT PK | `ses_` + first 16 hex chars of `sha1(user_id + "|" + session_start)`; deterministic |
| `user_id` | TEXT | owner |
| `session_start`, `session_end` | TEXT | time of first / last event (ISO-8601 UTC) |
| `session_start_ts`, `session_end_ts` | INTEGER | same instants as epoch seconds |
| `duration_seconds` | INTEGER | `end - start`, >= 0 (derived) |
| `event_count` | INTEGER | events in the session, >= 1 (derived) |
| `is_bounce` | INTEGER | 1 when `event_count = 1` (derived) |
| `gap_seconds` | INTEGER | inactivity gap used to build it |
| `run_id` | TEXT | run that last wrote the row |

Sessions are derived from all stored events for a user, so late or backfilled events can change earlier session boundaries. `session_id` depends on the user and session start; if a late event moves the start, the ID changes with it.

Index: `(user_id, session_start_ts)`. Invariant: consecutive sessions of a user are separated by more than `gap_seconds`.

### `rejected_events` - quarantine (append-only audit, one set per run)
| Column | Type | Meaning |
|---|---|---|
| `reject_id` | INTEGER PK | autoincrement |
| `run_id` | TEXT | run that rejected it |
| `source_file`, `source_row` | TEXT, INTEGER | location of the record in the source |
| `reject_reason` | TEXT | one of the reason codes below |
| `reject_detail` | TEXT | human-readable explanation (e.g. which field, which earlier row) |
| `raw_record` | TEXT | captured input record serialized as JSON for diagnosis; CSV quoting and formatting are normalized rather than stored byte-for-byte |

Reason codes: `malformed_row`, `missing_required_field`, `missing_timestamp`, `invalid_timestamp`,
`invalid_reference_key`, `duplicate_event`, `conflicting_duplicate_event`.

### `pipeline_runs` - operational log
| Column | Meaning |
|---|---|
| `run_id` | PK, `run_<UTC time>_<8 hex>` |
| `started_at`, `ended_at` | ISO-8601 UTC |
| `status` | `RUNNING`, `SUCCESS` or `FAILED` (a row left `RUNNING` means the process was killed) |
| `input_files` | JSON list of input paths |
| `gap_seconds` | gap used |
| `rows_in` | records read (blank lines excluded) |
| `rows_rejected` | records quarantined |
| `rows_inserted` | new events stored |
| `rows_skipped_existing` | identical events already stored (idempotent reruns) |
| `late_events` | new events older than the user's latest stored event |
| `users_affected`, `sessions_written` | scope of the session rebuild |
| `duration_seconds` | wall time |
| `failure_reason` | set when `FAILED`, e.g. `schema_mismatch: ...`, `input_not_found: ...`, `reject_rate_exceeded: ...` |
| `notes` | JSON: ignored extra columns, skipped reference check, full-rebuild reason |

**Reconciliation identity (SUCCESS runs):** `rows_in = rows_rejected + rows_inserted + rows_skipped_existing`.
Reconciliation also checks that each session's event count matches the stored events in its time range and that every event belongs to exactly one session.

## Relationships
`events.user_id -> users.user_id` (checked at validation, not a DB foreign key, so a missing users list is allowed);
`events.run_id -> pipeline_runs.run_id` (foreign key); `sessions.user_id` groups `events.user_id`;
each event belongs to exactly one session of its user (checked by reconciliation).
