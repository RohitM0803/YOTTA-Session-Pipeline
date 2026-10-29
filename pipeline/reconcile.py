"""Reconciliation: independent SQL checks that the numbers add up and the output is consistent."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _scalar(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchone()[0]


def latest_success_run(conn) -> Optional[str]:
    row = conn.execute(
        "SELECT run_id FROM pipeline_runs WHERE status='SUCCESS' ORDER BY started_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def reconcile(conn, run_id: Optional[str] = None) -> List[Check]:
    """Run all checks. Run-level checks use `run_id` (default: latest successful run)."""
    checks: List[Check] = []
    run_id = run_id or latest_success_run(conn)

    if run_id is None:
        checks.append(Check("run_found", False, "no successful run found in pipeline_runs"))
    else:
        row = conn.execute(
            "SELECT status, rows_in, rows_rejected, rows_inserted, rows_skipped_existing "
            "FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            checks.append(Check("run_found", False, f"run_id {run_id} not found"))
        else:
            status, rows_in, rejected, inserted, skipped = row
            checks.append(Check("run_found", status == "SUCCESS", f"{run_id} status={status}"))
            if status == "SUCCESS":
                total = rejected + inserted + skipped
                checks.append(Check(
                    "rows_in_equals_rejected_plus_inserted_plus_skipped", rows_in == total,
                    f"rows_in={rows_in} vs rejected({rejected}) + inserted({inserted}) + "
                    f"skipped_existing({skipped}) = {total}"))
                in_table = _scalar(conn, "SELECT COUNT(*) FROM rejected_events WHERE run_id=?", (run_id,))
                checks.append(Check("rejects_table_matches_run_counter", in_table == rejected,
                                    f"rejected_events rows={in_table}, pipeline_runs.rows_rejected={rejected}"))
                inserted_in_table = _scalar(conn, "SELECT COUNT(*) FROM events WHERE run_id=?", (run_id,))
                checks.append(Check("events_table_matches_run_counter", inserted_in_table == inserted,
                                    f"events rows from this run={inserted_in_table}, rows_inserted={inserted}"))
        bad_rejects = _scalar(
            conn,
            "SELECT COUNT(*) FROM rejected_events WHERE run_id=? AND (TRIM(reject_reason)='' "
            "OR TRIM(source_file)='' OR source_row IS NULL OR source_row < 1)", (run_id,))
        checks.append(Check("every_reject_has_reason_and_source", bad_rejects == 0,
                            f"{bad_rejects} reject rows lack reason/source"))

    n_events = _scalar(conn, "SELECT COUNT(*) FROM events")
    n_in_sessions = _scalar(conn, "SELECT COALESCE(SUM(event_count),0) FROM sessions")
    checks.append(Check("stored_events_equal_sum_of_session_event_counts", n_events == n_in_sessions,
                        f"events={n_events}, sum(sessions.event_count)={n_in_sessions}"))

    uncovered = _scalar(conn, """
        SELECT COUNT(*) FROM events e WHERE NOT EXISTS (
            SELECT 1 FROM sessions s WHERE s.user_id = e.user_id
              AND e.event_ts BETWEEN s.session_start_ts AND s.session_end_ts)""")
    checks.append(Check("every_event_falls_inside_a_session", uncovered == 0, f"{uncovered} events outside sessions"))

    overlaps = _scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT session_start_ts, gap_seconds,
                   LAG(session_end_ts) OVER (PARTITION BY user_id ORDER BY session_start_ts) AS prev_end
            FROM sessions)
        WHERE prev_end IS NOT NULL AND session_start_ts - prev_end <= gap_seconds""")
    checks.append(Check("sessions_per_user_are_separated_by_more_than_the_gap", overlaps == 0,
                        f"{overlaps} session pairs closer than the gap or overlapping"))

    inconsistent = _scalar(conn, """
        SELECT COUNT(*) FROM sessions WHERE duration_seconds != session_end_ts - session_start_ts
           OR event_count < 1 OR is_bounce != (event_count = 1)""")
    checks.append(Check("session_fields_are_internally_consistent", inconsistent == 0,
                        f"{inconsistent} sessions with inconsistent duration/event_count/is_bounce"))

    gaps = [r[0] for r in conn.execute("SELECT DISTINCT gap_seconds FROM sessions")]
    checks.append(Check("all_sessions_built_with_one_gap_setting", len(gaps) <= 1, f"gap_seconds in use: {gaps}"))

    if _scalar(conn, "SELECT COUNT(*) FROM users") == 0:
        checks.append(Check("events_reference_known_users", True, "skipped: no users loaded"))
    else:
        orphans = _scalar(conn, "SELECT COUNT(*) FROM events WHERE user_id NOT IN (SELECT user_id FROM users)")
        checks.append(Check("events_reference_known_users", orphans == 0, f"{orphans} events with unknown user"))
    return checks


def compare_with_expected(conn, expected_dir: str, run_id: Optional[str] = None) -> List[Check]:
    """Compare output with the generator's answer key (kept in a separate folder from the input)."""
    run_id = run_id or latest_success_run(conn)
    base = Path(expected_dir)
    checks: List[Check] = []

    with open(base / "expected_sessions.csv", newline="", encoding="utf-8") as fh:
        expected = {(r["user_id"], r["session_start"], r["session_end"], int(r["event_count"]))
                    for r in csv.DictReader(fh)}
    actual = set(conn.execute("SELECT user_id, session_start, session_end, event_count FROM sessions"))
    missing, unexpected = expected - actual, actual - expected
    checks.append(Check("sessions_match_answer_key", not missing and not unexpected,
                        f"expected={len(expected)} actual={len(actual)} missing={len(missing)} "
                        f"unexpected={len(unexpected)}"))

    with open(base / "expected_rejects.csv", newline="", encoding="utf-8") as fh:
        exp_rej = {(int(r["row_number"]), r["reject_reason"]) for r in csv.DictReader(fh)}
    act_rej = set(conn.execute(
        "SELECT source_row, reject_reason FROM rejected_events WHERE run_id=?", (run_id,)))
    missing, unexpected = exp_rej - act_rej, act_rej - exp_rej
    checks.append(Check("rejects_match_answer_key", not missing and not unexpected,
                        f"expected={len(exp_rej)} actual={len(act_rej)} missing={len(missing)} "
                        f"unexpected={len(unexpected)}"))
    return checks
