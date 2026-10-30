import sqlite3
import unittest

from pipeline import store
from pipeline.datagen import generate
from pipeline.reconcile import compare_with_expected, reconcile
from pipeline.report import format_table, load_sample_queries
from tests.base import PipelineTestCase, ev


def failed(checks):
    return {c.name for c in checks if not c.passed}


class ReconcileTests(PipelineTestCase):
    def setUp(self):
        super().setUp()
        self.res = self.run_it(self.csv_file("a.csv", [
            ev("e1", "u1", "2026-01-01T10:00:00Z"), ev("e2", "u1", "2026-01-01T10:10:00Z"),
            ev("e3", "u1", "2026-01-01T13:00:00Z"), "broken", ev("e1", "u1", "2026-01-01T10:00:00Z")]),
            users=self.users_file(["u1"]))

    def test_all_checks_pass_on_good_run(self):
        c = self.conn()
        self.assertEqual(failed(reconcile(c, self.res.run_id)), set())
        c.close()

    def test_latest_run_is_used_by_default(self):
        c = self.conn()
        self.assertEqual(failed(reconcile(c)), set())
        c.close()

    def test_detects_missing_session(self):
        c = self.conn()
        c.execute("DELETE FROM sessions WHERE event_count = 1")
        failed_names = failed(reconcile(c))
        c.close()
        self.assertIn("stored_events_equal_sum_of_session_event_counts", failed_names)
        self.assertIn("every_event_falls_inside_a_session", failed_names)

    def test_detects_overlapping_sessions(self):
        c = self.conn()
        c.execute("""INSERT INTO sessions VALUES ('ses_fake','u1','2026-01-01T10:05:00Z','2026-01-01T10:06:00Z',
                     1767261900,1767261960,60,1,0,1800,'x')""")
        self.assertIn("sessions_per_user_are_separated_by_more_than_the_gap", failed(reconcile(c)))
        c.close()

    def test_detects_inconsistent_session_fields(self):
        c = self.conn()
        c.execute("UPDATE sessions SET duration_seconds = duration_seconds + 5 WHERE event_count = 2")
        self.assertIn("session_fields_are_internally_consistent", failed(reconcile(c)))
        c.close()

    def test_detects_event_counts_assigned_to_the_wrong_sessions(self):
        c = self.conn()
        c.execute("UPDATE sessions SET event_count = 1, is_bounce = 1 WHERE session_start = '2026-01-01T10:00:00Z'")
        c.execute("UPDATE sessions SET event_count = 2, is_bounce = 0 WHERE session_start = '2026-01-01T13:00:00Z'")
        failed_names = failed(reconcile(c))
        c.close()
        self.assertNotIn("stored_events_equal_sum_of_session_event_counts", failed_names)
        self.assertIn("session_event_counts_match_stored_events", failed_names)

    def test_detects_orphan_event_user(self):
        c = self.conn()
        c.execute("DELETE FROM users")
        c.execute("INSERT INTO users VALUES ('someone_else')")
        self.assertIn("events_reference_known_users", failed(reconcile(c)))
        c.close()

    def test_detects_tampered_run_counters(self):
        c = self.conn()
        c.execute("UPDATE pipeline_runs SET rows_in = rows_in + 1")
        self.assertIn("rows_in_equals_rejected_plus_inserted_plus_skipped", failed(reconcile(c)))
        c.close()

    def test_no_successful_run(self):
        c = store.connect(":memory:")
        store.init_db(c)
        self.assertIn("run_found", failed(reconcile(c)))
        c.close()


class ExpectedComparisonTests(PipelineTestCase):
    def test_pipeline_output_matches_answer_key_and_tampering_is_detected(self):
        manifest = generate(self.tmp + "/data", self.tmp + "/exp", rows=500, seed=3)
        res = self.run_it(manifest["events_file"], users=self.tmp + "/data/users.csv")
        c = self.conn()
        self.assertEqual(failed(compare_with_expected(c, self.tmp + "/exp", res.run_id)), set())
        c.execute("DELETE FROM sessions WHERE rowid = (SELECT MIN(rowid) FROM sessions)")
        self.assertEqual(failed(compare_with_expected(c, self.tmp + "/exp", res.run_id)), {"sessions_match_answer_key"})
        c.execute("DELETE FROM rejected_events WHERE rowid = (SELECT MIN(rowid) FROM rejected_events)")
        self.assertIn("rejects_match_answer_key", failed(compare_with_expected(c, self.tmp + "/exp", res.run_id)))
        c.close()


class SampleQueryTests(PipelineTestCase):
    def test_every_sample_query_runs_and_formats(self):
        manifest = generate(self.tmp + "/data", self.tmp + "/exp", rows=300, seed=5)
        self.run_it(manifest["events_file"], users=self.tmp + "/data/users.csv")
        queries = load_sample_queries()
        self.assertGreaterEqual(len(queries), 5)
        c = self.conn()
        for name, sql in queries:
            with self.subTest(query=name):
                cur = c.execute(sql)
                text = format_table([d[0] for d in cur.description], cur.fetchall())
                self.assertTrue(text)
        c.close()


if __name__ == "__main__":
    unittest.main()
