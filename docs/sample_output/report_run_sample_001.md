# Run report `run_sample_001`

- **Status:** SUCCESS
- **Duration:** 0.00s

## Counts

| Metric | Value |
|---|---|
| rows read | 40 |
| new events loaded | 30 |
| already loaded (skipped, not errors) | 0 |
| rejected | 10 |
| late-arriving events | 0 |
| users re-sessionized | 8 |
| sessions written | 11 |

Reject rate: 25.00%

## Rejects by reason

| Reason | Rows |
|---|---|
| conflicting_duplicate_event | 1 |
| duplicate_event | 4 |
| invalid_reference_key | 1 |
| invalid_timestamp | 1 |
| malformed_row | 1 |
| missing_required_field | 1 |
| missing_timestamp | 1 |

## Stage timings (seconds)

| Stage | Seconds |
|---|---|
| read | 0.001 |
| validate | 0.0006 |
| dedupe | 0.0 |
| classify | 0.0001 |
| insert_events | 0.0002 |
| sessionize | 0.0006 |

## Notes

- users_added: 8

## Reconciliation

| Check | Result | Detail |
|---|---|---|
| run_found | PASS | run_sample_001 status=SUCCESS |
| rows_in_equals_rejected_plus_inserted_plus_skipped | PASS | rows_in=40 vs rejected(10) + inserted(30) + skipped_existing(0) = 40 |
| rejects_table_matches_run_counter | PASS | rejected_events rows=10, pipeline_runs.rows_rejected=10 |
| events_table_matches_run_counter | PASS | events rows from this run=30, rows_inserted=30 |
| every_reject_has_reason_and_source | PASS | 0 reject rows lack reason/source |
| stored_events_equal_sum_of_session_event_counts | PASS | events=30, sum(sessions.event_count)=30 |
| every_event_falls_inside_a_session | PASS | 0 events outside sessions |
| sessions_per_user_are_separated_by_more_than_the_gap | PASS | 0 session pairs closer than the gap or overlapping |
| session_fields_are_internally_consistent | PASS | 0 sessions with inconsistent duration/event_count/is_bounce |
| session_event_counts_match_stored_events | PASS | 0 sessions with event_count different from events in their time range |
| all_sessions_built_with_one_gap_setting | PASS | gap_seconds in use: [1800] |
| events_reference_known_users | PASS | 0 events with unknown user |
| sessions_match_answer_key | PASS | expected=11 actual=11 missing=0 unexpected=0 |
| rejects_match_answer_key | PASS | expected=10 actual=10 missing=0 unexpected=0 |
