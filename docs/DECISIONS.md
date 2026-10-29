# Design decisions and trade-offs

| # | Decision | Why | Trade-off / alternative |
|---|---|---|---|
| 1 | Python standard library + SQLite only | Runs anywhere in one command, nothing to install, easy to review | Single writer, no parallelism; a warehouse would replace `store.py` |
| 2 | Gap rule is *strictly greater than* 30 min | Most common definition; exact 30:00 stays in session; boundary is tested | Some tools use `>=`; the rule is one line in `sessionize.py` and documented |
| 3 | Order by `(event_ts, event_id)` | Deterministic for out-of-order input and identical timestamps | Ties are broken by id, not by "true" order (unknowable) |
| 4 | Sessions are **derived from stored event history**, not from the current file | Late and backfilled data fix earlier sessions automatically; reruns are trivial | Needs the events table; costs a re-read of affected users |
| 5 | Rebuild only **affected users** (batches of 500) | Measured ~100x less work for a small late batch; rerun does none | Slightly more code than "rebuild everything"; full rebuild still happens when the gap setting changes |
| 6 | One DB transaction per run | A crash can never leave half-loaded data; retry is always safe | A very large file means one large transaction |
| 7 | First `event_id` wins; later copies rejected (exact vs conflicting) | Never silently overwrite history; conflicts stay visible | A legitimate correction from the source is rejected until handled explicitly |
| 8 | Duplicate of an already-stored event is *skipped*, not rejected | Rerunning a file must not flood the quarantine with "errors" | `rows_skipped_existing` is a separate counter so counts still reconcile |
| 9 | Rejects are an append-only audit **per run** | Full history of what each run saw; traceable by `run_id`, file, line | Rerun of a bad file adds a new set of reject rows (analytics tables stay unchanged) |
| 10 | One reject reason per row, fixed rule order | Deterministic and testable; clean counts by reason | A row with several problems shows only the first |
| 11 | File-level problems (missing column, bad encoding) fail the whole run; row-level problems quarantine the row | A renamed column would otherwise reject 100% silently; one bad row must not stop the batch | Optional quality gate (`--max-reject-rate`) also fails runs with too many rejects |
| 12 | Timestamps: offsets converted to UTC, naive = UTC, truncated to seconds, year 2000-2100 | One comparable representation; guards against placeholder dates like 1970 | Sub-second ordering is lost; a client with local naive times must supply offsets |
| 13 | Reference check active only when users are loaded | Works for sources without a users list, strict when one exists | State-dependent behaviour is recorded in run notes |
| 14 | Answer key built by the generator **before** the pipeline runs | Independent oracle; catches logic errors the code's own tests would share | Only as realistic as the generator's anomaly types |
| 15 | Tests use `unittest` (also run by pytest) | Zero dependencies for reviewers | Slightly more verbose than pytest style |
| 16 | Physical line numbers as `source_row` | Reviewer can open the file at that line | Multi-line quoted CSV fields report the line where the record ends |

## Failure modes considered
Missing/renamed columns, wrong file type, invalid UTF-8, Excel BOM, blank lines, ragged CSV rows, invalid JSON,
nested JSON, null-like strings, timezone offsets, date-only / epoch timestamps, duplicate IDs (same and different
content, across files and across runs), unknown users, empty and header-only files, crash mid-load, concurrent
writers, changed gap setting, too many rejects.
