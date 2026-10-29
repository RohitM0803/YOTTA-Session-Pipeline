# Data Dictionary

All timestamps are ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). Tables and columns are snake_case.

## Source: events file (`.csv` or `.jsonl`)

Grain: one row = one user event. Column order is irrelevant; names are trimmed and case-insensitive; `column_map` in the
config can rename source columns.

| Column | Required | Type | Rules |
|---|---|---|---|
| `event_id` | yes | text | unique per event; blank/null-like rejected; first occurrence wins |
| `user_id` | yes | text | must exist in `users` when a users list is loaded |
| `event_type` | yes | text | any non-blank value (e.g. `page_view`, `click`) |
| `event_time` | yes | ISO-8601 date-time | offsets converted to UTC; no offset = UTC; sub-seconds truncated; year 2000-2100 |
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

Index: `(user_id, session_start_ts)`. Invariant: consecutive sessions of a user are separated by more than `gap_seconds`.

### `rejected_events` - quarantine (append-only audit, one set per run)
| Column | Type | Meaning |
|---|---|---|
| `reject_id` | INTEGER PK | autoincrement |
| `run_id` | TEXT | run that rejected it |
| `source_file`, `source_row` | TEXT, INTEGER | location of the record in the source |
| `reject_reason` | TEXT | one of the reason codes below |
| `reject_detail` | TEXT | human-readable explanation (e.g. which field, which earlier row) |
| `raw_record` | TEXT | original record as JSON, so nothing is lost |

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

## Relationships
`events.user_id -> users.user_id` (checked at validation, not a DB foreign key, so a missing users list is allowed);
`events.run_id -> pipeline_runs.run_id` (foreign key); `sessions.user_id` groups `events.user_id`;
each event belongs to exactly one session of its user (checked by reconciliation).
