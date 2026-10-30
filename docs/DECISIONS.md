# Design decisions and trade-offs

| # | Decision | Why | Trade-off / alternative |
|---|---|---|---|
| 1 | Python standard library + SQLite only | Runs anywhere in one command, nothing to install, easy to review | Single writer, no parallelism; a warehouse would replace `store.py` |
| 2 | Gap rule is *strictly greater than* 30 min | Most common definition; exact 30:00 stays in session; boundary is tested | Some tools use `>=`; the rule is one line in `sessionize.py` and documented |
| 3 | Order by `(event_ts, event_id)` | Deterministic for out-of-order input and identical timestamps | Ties are broken by id, not by "true" order (unknowable) |
| 4 | Sessions are **derived from stored event history**, not from the current file | Late and backfilled data fix earlier sessions automatically; reruns are trivial | Needs the events table; costs a re-read of affected users |
| 5 | Rebuild only **affected users** (batches of 500) | In the recorded benchmark, 42 of 4,223 users were rebuilt (~100x fewer); elapsed rebuild time was 0.009s vs 0.510s (~57x faster) for that workload. A rerun rebuilds none. | Slightly more code than "rebuild everything"; full rebuild still happens when the gap setting changes. These measurements are workload- and machine-specific. |
| 6 | Apply each run's event, session, user, and successful-reject changes in a transaction | A failure rolls back the data changes, so no partial event/session load remains. | The initial `RUNNING` audit row is committed before the data transaction. On failure, the rollback is followed by a separate transaction that records `FAILED` and captured rejects. Large successful runs use one large data transaction. |
| 7 | First `event_id` wins; later copies rejected (exact vs conflicting) | Never silently overwrite history; conflicts stay visible | A legitimate correction from the source is rejected until handled explicitly |
| 8 | Duplicate of an already-stored event is *skipped*, not rejected | Rerunning a file must not flood the quarantine with "errors" | `rows_skipped_existing` is a separate counter so counts still reconcile |
| 9 | Rejects are an append-only audit **per run** | Full history of what each run saw; traceable by `run_id`, file, line | Rerun of a bad file adds a new set of reject rows (analytics tables stay unchanged) |
| 10 | One reject reason per row, fixed rule order | Deterministic and testable; clean counts by reason | A row with several problems shows only the first |
| 11 | File-level problems (missing column, bad encoding) fail the whole run; row-level problems quarantine the row | A renamed column would otherwise reject 100% silently; one bad row must not stop the batch | Optional quality gate (`--max-reject-rate`) also fails runs with too many rejects |
| 12 | Timestamps: offsets converted to UTC, naive = UTC, fractional seconds discarded, year 2000-2100 | One comparable representation; guards against placeholder dates like 1970 | Discarding fractions can change ordering and gap classification near a boundary. For example, 12:00:00.1 to 12:30:00.9 is an actual 30:00.8 gap, but becomes exactly 30 minutes after truncation and stays in one session. Events in the same second are ordered by `event_id`. A client with local naive times must supply offsets. |
| 13 | Check event user IDs against the users accumulated in the database when that set is non-empty, or when a users file is explicitly supplied | Sources without a users list can run without a reference check; supplying a list enables strict checking. | On a fresh database, an explicitly supplied empty users file enables the check against an empty set, so all event user IDs are rejected. On a database with existing users, an empty file adds none and validation still uses the stored users. Users are added, not replaced. |
| 14 | Answer key built by the generator **before** the pipeline runs | Independent oracle; catches logic errors the code's own tests would share | Only as realistic as the generator's anomaly types |
| 15 | Tests use `unittest` (also run by pytest) | Zero dependencies for reviewers | Slightly more verbose than pytest style |
| 16 | Record the physical source line in `source_row` | Reviewers can locate an input row; JSON Lines uses the line containing the record. | CSV quoted fields may span lines; `csv.reader.line_num` records the line where that record ends, not where it starts. |

## Failure modes considered
Missing/renamed columns, wrong file type, invalid UTF-8, Excel BOM, blank lines, ragged CSV rows, invalid JSON,
nested JSON, null-like strings, timezone offsets, date-only / epoch timestamps, duplicate IDs (same and different
content, across files and across runs), unknown users, empty and header-only files, crash mid-load, concurrent
writers, changed gap setting, too many rejects.
