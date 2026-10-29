-- Example analytical questions a client could ask of the output.
-- Run them all with:  python -m pipeline queries --db out/sessions.db

-- name: sessions_per_day
SELECT substr(session_start, 1, 10) AS day,
       COUNT(*)                     AS sessions,
       COUNT(DISTINCT user_id)      AS active_users
FROM sessions
GROUP BY day
ORDER BY day
LIMIT 10;

-- name: overall_session_metrics
SELECT COUNT(*)                                  AS sessions,
       ROUND(AVG(duration_seconds) / 60.0, 2)    AS avg_duration_minutes,
       ROUND(AVG(event_count), 2)                AS avg_events_per_session,
       ROUND(100.0 * AVG(is_bounce), 1)          AS bounce_rate_percent
FROM sessions;

-- name: top_5_users_by_sessions
SELECT user_id, COUNT(*) AS sessions, SUM(event_count) AS events
FROM sessions
GROUP BY user_id
ORDER BY sessions DESC, user_id
LIMIT 5;

-- name: session_length_buckets
SELECT CASE WHEN duration_seconds = 0     THEN '0: single moment'
            WHEN duration_seconds < 300   THEN '1: under 5 min'
            WHEN duration_seconds < 1800  THEN '2: 5-30 min'
            ELSE                               '3: 30+ min' END AS bucket,
       COUNT(*) AS sessions
FROM sessions
GROUP BY bucket
ORDER BY bucket;

-- name: data_quality_rejects_by_reason
SELECT reject_reason, COUNT(*) AS rejected_rows
FROM rejected_events
GROUP BY reject_reason
ORDER BY rejected_rows DESC, reject_reason;

-- name: run_history
SELECT run_id, status, rows_in, rows_inserted, rows_skipped_existing, rows_rejected,
       sessions_written, ROUND(duration_seconds, 2) AS seconds, failure_reason
FROM pipeline_runs
ORDER BY started_at DESC, rowid DESC
LIMIT 10;
