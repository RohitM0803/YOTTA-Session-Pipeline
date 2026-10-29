import json
import unittest
from unittest import mock

from pipeline import runner
from pipeline.config import Config, ConfigError
from pipeline.schema import Reason
from tests.base import HEADER, PipelineTestCase, ev

T = "2026-01-01T"


def t(hms):
    return T + hms + "Z"


class HappyPathTests(PipelineTestCase):
    def test_basic_run_builds_sessions_and_counts(self):
        f = self.csv_file("a.csv", [
            ev("e1", "u1", t("10:00:00")), ev("e2", "u1", t("10:10:00")), ev("e3", "u1", t("12:00:00")),
            ev("e4", "u2", t("10:00:00")),
        ])
        res = self.run_it(f, users=self.users_file(["u1", "u2"]))
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual((res.rows_in, res.rows_inserted, res.rows_rejected, res.sessions_written), (4, 4, 0, 3))
        sessions = self.rows("SELECT user_id, session_start, session_end, event_count, duration_seconds, is_bounce "
                             "FROM sessions ORDER BY user_id, session_start")
        self.assertEqual(sessions, [
            ("u1", t("10:00:00"), t("10:10:00"), 2, 600, 0),
            ("u1", t("12:00:00"), t("12:00:00"), 1, 0, 1),
            ("u2", t("10:00:00"), t("10:00:00"), 1, 0, 1),
        ])

    def test_run_metrics_are_persisted(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), "garbage"])
        res = self.run_it(f, run_id="run_fixed")
        row = self.rows("SELECT run_id, status, rows_in, rows_rejected, rows_inserted, sessions_written, "
                        "started_at, ended_at, failure_reason, gap_seconds FROM pipeline_runs")[0]
        self.assertEqual(row[:6], ("run_fixed", "SUCCESS", 2, 1, 1, 1))
        self.assertTrue(row[6] and row[7])
        self.assertEqual((row[8], row[9]), (None, 1800))
        self.assertEqual(res.run_id, "run_fixed")

    def test_timezone_offsets_are_normalised(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", "2026-01-01T15:30:00+05:30"), ev("e2", "u1", t("10:20:00"))])
        self.run_it(f)
        self.assertEqual(self.rows("SELECT event_time FROM events ORDER BY event_ts"),
                         [(t("10:00:00"),), (t("10:20:00"),)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sessions"), [(1,)])

    def test_jsonl_input(self):
        lines = [json.dumps({"event_id": "e1", "user_id": "u1", "event_type": "click", "event_time": t("10:00:00")}),
                 json.dumps({"event_id": "e2", "user_id": "u1", "event_type": "click", "event_time": t("10:05:00")})]
        res = self.run_it(self.write("a.jsonl", "\n".join(lines) + "\n"))
        self.assertEqual((res.status, res.sessions_written), ("SUCCESS", 1))

    def test_multiple_input_files_and_source_tracking(self):
        a = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"))])
        b = self.csv_file("sub/b.csv", [ev("e2", "u1", t("10:05:00"))])
        res = self.run_it([a, b])
        self.assertEqual((res.rows_in, res.sessions_written), (2, 1))
        files = {r[0] for r in self.rows("SELECT source_file FROM events")}
        self.assertEqual(files, {a.replace("\\", "/"), b.replace("\\", "/")})

    def test_column_mapping_from_config(self):
        f = self.write("a.csv", "id,uid,kind,ts\ne1,u1,click," + t("10:00:00") + "\n")
        cfg = self.cfg(column_map={"id": "event_id", "uid": "user_id", "kind": "event_type", "ts": "event_time"})
        self.assertEqual(self.run_it(f, cfg=cfg).rows_inserted, 1)

    def test_extra_columns_are_noted_not_fatal(self):
        f = self.write("a.csv", HEADER + ",browser\n" + ev("e1", "u1", t("10:00:00")) + ",chrome\n")
        res = self.run_it(f)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.notes["ignored_extra_columns"], ["browser"])


class EmptyAndBadInputTests(PipelineTestCase):
    def test_empty_file_is_a_successful_empty_batch(self):
        res = self.run_it(self.write("a.csv", ""))
        self.assertEqual((res.status, res.rows_in, res.rows_inserted, res.sessions_written), ("SUCCESS", 0, 0, 0))

    def test_header_only_file(self):
        res = self.run_it(self.write("a.csv", HEADER + "\n"))
        self.assertEqual((res.status, res.rows_in), ("SUCCESS", 0))

    def test_malformed_missing_null_and_invalid_rows_are_quarantined(self):
        f = self.csv_file("a.csv", [
            ev("e1", "u1", t("10:00:00")),
            "e2,u1",                               # malformed (2 fields)
            ev("", "u1", t("10:01:00")),           # missing event_id
            ev("e4", "u1", ""),                    # missing timestamp
            ev("e5", "u1", "NULL"),                # null timestamp
            ev("e6", "u1", "not-a-timestamp"),     # invalid timestamp
            ev("e7", "ghost", t("10:02:00")),      # unknown user
        ])
        res = self.run_it(f, users=self.users_file(["u1"]))
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual((res.rows_in, res.rows_inserted, res.rows_rejected), (7, 1, 6))
        self.assertEqual(res.rejects_by_reason, {
            Reason.MALFORMED_ROW: 1, Reason.MISSING_REQUIRED_FIELD: 1, Reason.MISSING_TIMESTAMP: 2,
            Reason.INVALID_TIMESTAMP: 1, Reason.INVALID_REFERENCE_KEY: 1})
        rows = self.rows("SELECT source_row, reject_reason, run_id FROM rejected_events ORDER BY source_row")
        self.assertEqual([(r[0], r[1]) for r in rows], [(3, Reason.MALFORMED_ROW), (4, Reason.MISSING_REQUIRED_FIELD),
                                                        (5, Reason.MISSING_TIMESTAMP), (6, Reason.MISSING_TIMESTAMP),
                                                        (7, Reason.INVALID_TIMESTAMP), (8, Reason.INVALID_REFERENCE_KEY)])
        self.assertTrue(all(r[2] == res.run_id for r in rows))

    def test_all_rows_invalid_still_succeeds_with_no_sessions(self):
        res = self.run_it(self.csv_file("a.csv", ["x,y", ev("", "", "")]))
        self.assertEqual((res.status, res.rows_rejected, res.sessions_written), ("SUCCESS", 2, 0))

    def test_reference_check_skipped_without_users(self):
        res = self.run_it(self.csv_file("a.csv", [ev("e1", "anyone", t("10:00:00"))]))
        self.assertEqual((res.rows_inserted, res.notes["reference_check"]), (1, "skipped (no users loaded)"))
    
    
    def test_empty_users_file_rejects_unknown_users(self):
        events = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"))])
        empty_users = self.users_file([])

        res = self.run_it(events, users=empty_users)

        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.rows_inserted, 0)
        self.assertEqual(res.rejects_by_reason, {Reason.INVALID_REFERENCE_KEY: 1})
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events"), [(0,)])





    def test_users_from_earlier_run_still_enforced(self):
        self.run_it(self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"))]), users=self.users_file(["u1"]))
        res = self.run_it(self.csv_file("b.csv", [ev("e2", "u2", t("10:00:00"))]))   # no --users this time
        self.assertEqual(res.rejects_by_reason, {Reason.INVALID_REFERENCE_KEY: 1})


class DuplicateTests(PipelineTestCase):
    def test_exact_duplicate_in_batch_is_rejected_first_kept(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), ev("e1", "u1", t("10:00:00"))])
        res = self.run_it(f)
        self.assertEqual((res.rows_inserted, res.rejects_by_reason), (1, {Reason.DUPLICATE_EVENT: 1}))
        self.assertEqual(self.rows("SELECT source_row FROM events"), [(2,)])

    def test_same_instant_in_different_format_is_still_a_duplicate(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), ev("e1", "u1", "2026-01-01T15:30:00+05:30")])
        self.assertEqual(self.run_it(f).rejects_by_reason, {Reason.DUPLICATE_EVENT: 1})

    def test_conflicting_duplicate_in_batch(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"), page="/a"), ev("e1", "u1", t("10:00:00"), page="/b")])
        res = self.run_it(f)
        self.assertEqual(res.rejects_by_reason, {Reason.CONFLICTING_DUPLICATE_EVENT: 1})
        self.assertEqual(self.rows("SELECT page FROM events"), [("/a",)])

    def test_duplicate_across_files_in_one_run(self):
        a = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"))])
        b = self.csv_file("b.csv", [ev("e1", "u1", t("10:00:00"))])
        res = self.run_it([a, b])
        self.assertEqual((res.rows_inserted, res.rejects_by_reason), (1, {Reason.DUPLICATE_EVENT: 1}))

    def test_conflict_with_already_stored_event_keeps_stored_version(self):
        self.run_it(self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"), page="/original")]))
        res = self.run_it(self.csv_file("b.csv", [ev("e1", "u1", t("10:00:00"), page="/changed")]))
        self.assertEqual(res.rejects_by_reason, {Reason.CONFLICTING_DUPLICATE_EVENT: 1})
        self.assertEqual(self.rows("SELECT page FROM events"), [("/original",)])


class IdempotencyTests(PipelineTestCase):
    def lines(self):
        return [ev("e1", "u1", t("10:00:00")), ev("e2", "u1", t("10:10:00")), ev("e3", "u2", t("11:00:00")),
                "broken", ev("e1", "u1", t("10:00:00"))]

    def test_rerun_of_same_input_changes_nothing(self):
        f = self.csv_file("a.csv", self.lines())
        first = self.run_it(f)
        before = self.snapshot()
        second = self.run_it(f)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((second.status, second.rows_inserted, second.rows_skipped_existing, second.sessions_written),
                         ("SUCCESS", 0, 3, 0))
        self.assertEqual(first.rows_inserted, 3)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events"), [(3,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sessions"), [(2,)])

    def test_rerun_balances_and_records_its_own_audit_rows(self):
        f = self.csv_file("a.csv", self.lines())
        self.run_it(f)
        second = self.run_it(f)
        # 5 rows = 2 rejected (1 malformed + 1 in-batch duplicate) + 3 already loaded + 0 new
        self.assertEqual((second.rows_in, second.rows_rejected, second.rows_skipped_existing), (5, 2, 3))
        self.assertEqual(second.rows_in, second.rows_rejected + second.rows_inserted + second.rows_skipped_existing)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM pipeline_runs"), [(2,)])

    def test_input_order_does_not_change_result(self):
        lines = [ev(f"e{i}", "u1", t(f"10:{i:02d}:00")) for i in range(0, 50, 7)] + [ev("x1", "u1", t("14:00:00"))]
        a = self.csv_file("a.csv", lines)
        self.run_it(a)
        first = self.snapshot()
        self.db_path = self.db_path.replace("test.db", "other.db")
        self.run_it(self.csv_file("b.csv", list(reversed(lines))))
        # event rows differ in source_row only; compare sessions
        self.assertEqual(self.snapshot()[1], first[1])


class LateDataTests(PipelineTestCase):
    def test_late_event_merges_two_sessions(self):
        self.run_it(self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), ev("e2", "u1", t("11:00:00"))]))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sessions"), [(2,)])
        res = self.run_it(self.csv_file("b.csv", [ev("e3", "u1", t("10:30:00"))]))   # exactly 30 min from each
        self.assertEqual((res.rows_inserted, res.late_events, res.users_affected), (1, 1, 1))
        self.assertEqual(self.rows("SELECT session_start, session_end, event_count FROM sessions"),
                         [(t("10:00:00"), t("11:00:00"), 3)])

    def test_late_event_splits_nothing_when_inside_existing_session(self):
        self.run_it(self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), ev("e2", "u1", t("10:20:00"))]))
        self.run_it(self.csv_file("b.csv", [ev("e3", "u1", t("10:10:00"))]))
        self.assertEqual(self.rows("SELECT event_count FROM sessions"), [(3,)])

    def test_only_affected_users_are_rebuilt(self):
        self.run_it(self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), ev("e2", "u2", t("10:00:00"))]))
        res = self.run_it(self.csv_file("b.csv", [ev("e3", "u1", t("10:05:00"))]))
        self.assertEqual((res.users_affected, res.sessions_written), (1, 1))

    def test_backfill_of_older_data_after_newer(self):
        self.run_it(self.csv_file("new.csv", [ev("e1", "u1", "2026-02-01T10:00:00Z")]))
        res = self.run_it(self.csv_file("old.csv", [ev("e2", "u1", "2026-01-01T10:00:00Z"),
                                                     ev("e3", "u1", "2026-01-01T10:10:00Z")]))
        self.assertEqual(res.late_events, 2)
        self.assertEqual(self.rows("SELECT session_start, event_count FROM sessions ORDER BY session_start_ts"),
                         [("2026-01-01T10:00:00Z", 2), ("2026-02-01T10:00:00Z", 1)])

    def test_changing_the_gap_triggers_a_full_rebuild(self):
        self.run_it(self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), ev("e2", "u1", t("10:20:00")),
                                             ev("e3", "u2", t("10:00:00"))]))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sessions"), [(2,)])
        res = self.run_it(self.csv_file("b.csv", []), cfg=self.cfg(gap_minutes=10))
        self.assertEqual((res.status, res.users_affected), ("SUCCESS", 2))
        self.assertIn("full_rebuild_reason", res.notes)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sessions"), [(3,)])
        self.assertEqual(self.rows("SELECT DISTINCT gap_seconds FROM sessions"), [(600,)])


class FailureAndRecoveryTests(PipelineTestCase):
    def test_partial_failure_rolls_back_everything_and_retry_succeeds(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), ev("e2", "u1", t("10:05:00")), "broken"])
        with mock.patch.object(runner.store, "replace_sessions", side_effect=RuntimeError("disk exploded")):
            failed = self.run_it(f, run_id="run_fail")
        self.assertEqual(failed.status, "FAILED")
        self.assertIn("disk exploded", failed.failure_reason)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events"), [(0,)])      # events rolled back
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sessions"), [(0,)])
        row = self.rows("SELECT status, failure_reason FROM pipeline_runs WHERE run_id='run_fail'")[0]
        self.assertEqual(row[0], "FAILED")
        self.assertIn("RuntimeError", row[1])
        # rejects of the failed run stay visible for diagnosis
        self.assertEqual(self.rows("SELECT COUNT(*) FROM rejected_events WHERE run_id='run_fail'"), [(1,)])

        retry = self.run_it(f, run_id="run_retry")                                # retry with same input
        self.assertEqual((retry.status, retry.rows_inserted, retry.sessions_written), ("SUCCESS", 2, 1))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events"), [(2,)])

    def test_failure_in_middle_of_event_insert_leaves_no_partial_data(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"))])
        self.run_it(f)
        g = self.csv_file("b.csv", [ev("e2", "u2", t("10:00:00"))])
        with mock.patch.object(runner, "rebuild_sessions", side_effect=RuntimeError("boom")):
            self.run_it(g)
        self.assertEqual(self.rows("SELECT event_id FROM events"), [("e1",)])

    def test_schema_change_fails_run_cleanly(self):
        f = self.write("a.csv", "event_id,user_id,event_type,page\ne1,u1,click,/x\n")
        res = self.run_it(f)
        self.assertEqual(res.status, "FAILED")
        self.assertTrue(res.failure_reason.startswith("schema_mismatch"))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events"), [(0,)])
        self.assertEqual(self.rows("SELECT status FROM pipeline_runs"), [("FAILED",)])

    def test_missing_input_file_fails_run_with_reason(self):
        res = self.run_it(self.tmp + "/does_not_exist.csv")
        self.assertEqual(res.status, "FAILED")
        self.assertTrue(res.failure_reason.startswith("input_not_found"))

    def test_second_file_failing_means_nothing_from_first_is_loaded(self):
        a = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00"))])
        b = self.write("b.csv", "wrong,header\n1,2\n")
        res = self.run_it([a, b])
        self.assertEqual(res.status, "FAILED")
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events"), [(0,)])

    def test_unsupported_file_type_fails(self):
        self.assertEqual(self.run_it(self.write("a.txt", "hi")).status, "FAILED")

    def test_quality_gate_fails_and_loads_nothing(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), "bad1", "bad2", "bad3"])
        res = self.run_it(f, cfg=self.cfg(max_reject_rate=0.5))
        self.assertEqual(res.status, "FAILED")
        self.assertTrue(res.failure_reason.startswith("reject_rate_exceeded"))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events"), [(0,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM rejected_events"), [(3,)])

    def test_quality_gate_passes_at_threshold(self):
        f = self.csv_file("a.csv", [ev("e1", "u1", t("10:00:00")), "bad1"])
        self.assertEqual(self.run_it(f, cfg=self.cfg(max_reject_rate=0.5)).status, "SUCCESS")

    def test_database_is_usable_after_a_failed_run(self):
        self.run_it(self.write("bad.csv", "a,b\n1,2\n"))
        res = self.run_it(self.csv_file("ok.csv", [ev("e1", "u1", t("10:00:00"))]))
        self.assertEqual(res.status, "SUCCESS")


class ConfigTests(PipelineTestCase):
    def test_invalid_settings_are_rejected(self):
        for kwargs in ({"gap_minutes": 0}, {"gap_minutes": -5}, {"gap_minutes": 0.001}, {"max_reject_rate": 1.5}):
            with self.subTest(**kwargs):
                with self.assertRaises(ConfigError):
                    Config(**kwargs).validate()

    def test_run_pipeline_validates_config(self):
        with self.assertRaises(ConfigError):
            self.run_it(self.csv_file("a.csv", []), cfg=self.cfg(gap_minutes=0))


if __name__ == "__main__":
    unittest.main()

