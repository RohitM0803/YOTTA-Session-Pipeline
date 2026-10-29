import contextlib
import io
import os
import unittest

from pipeline.cli import main
from tests.base import PipelineTestCase

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(PipelineTestCase):
    def generate(self, rows=400):
        code, out, _ = cli("generate", "--out-dir", f"{self.tmp}/d", "--expected-dir", f"{self.tmp}/e",
                           "--rows", str(rows), "--seed", "5")
        self.assertEqual(code, 0)
        return f"{self.tmp}/d/events.csv", f"{self.tmp}/d/users.csv"

    def run_args(self, events, users):
        return ["run", "--input", events, "--users", users, "--db", self.db_path,
                "--report-dir", f"{self.tmp}/rep", "--expected-dir", f"{self.tmp}/e"]

    def test_generate_then_run_succeeds_and_writes_report_and_exports(self):
        events, users = self.generate()
        code, out, _ = cli(*self.run_args(events, users))
        self.assertEqual(code, 0)
        self.assertIn("SUCCESS", out)
        self.assertNotIn("[FAIL]", out)
        files = os.listdir(f"{self.tmp}/rep")
        self.assertTrue(any(f.startswith("report_") for f in files))
        self.assertIn("sessions.csv", files)
        self.assertIn("rejected_events.csv", files)

    def test_running_twice_is_safe(self):
        events, users = self.generate()
        cli(*self.run_args(events, users))
        before = self.snapshot()
        code, out, _ = cli(*self.run_args(events, users))
        self.assertEqual(code, 0)
        self.assertIn("new events=0", out)
        self.assertEqual(self.snapshot(), before)

    def test_failed_run_returns_exit_code_1_and_report(self):
        code, out, _ = cli("run", "--input", f"{self.tmp}/missing.csv", "--db", self.db_path,
                           "--report-dir", f"{self.tmp}/rep")
        self.assertEqual(code, 1)
        self.assertIn("input_not_found", out)
        self.assertTrue(any(f.startswith("report_") for f in os.listdir(f"{self.tmp}/rep")))

    def test_bad_config_returns_exit_code_2(self):
        bad = self.write("bad.json", "{not json")
        code, _, err = cli("run", "--input", "x.csv", "--config", bad)
        self.assertEqual(code, 2)
        self.assertIn("Configuration error", err)

    def test_invalid_gap_flag_returns_exit_code_2(self):
        events, users = self.generate(50)
        code, _, err = cli("run", "--input", events, "--gap-minutes", "0", "--db", self.db_path)
        self.assertEqual(code, 2)

    def test_config_file_and_flag_override(self):
        events, users = self.generate(200)
        cfgfile = self.write("c.json", '{"gap_minutes": 5, "db_path": "%s"}' % self.db_path.replace("\\", "/"))
        cli("run", "--input", events, "--config", cfgfile, "--report-dir", f"{self.tmp}/rep")
        self.assertEqual(self.rows("SELECT DISTINCT gap_seconds FROM sessions"), [(300,)])

    def test_reconcile_and_queries_commands(self):
        events, users = self.generate()
        cli(*self.run_args(events, users))
        code, out, _ = cli("reconcile", "--db", self.db_path, "--expected-dir", f"{self.tmp}/e")
        self.assertEqual(code, 0)
        self.assertIn("sessions_match_answer_key", out)
        code, out, _ = cli("queries", "--db", self.db_path)
        self.assertEqual(code, 0)
        self.assertIn("bounce_rate_percent", out)

    def test_reconcile_returns_3_when_a_check_fails(self):
        events, users = self.generate()
        cli(*self.run_args(events, users))
        c = self.conn()
        c.execute("DELETE FROM sessions WHERE rowid = (SELECT MIN(rowid) FROM sessions)")
        c.commit()
        c.close()
        self.assertEqual(cli("reconcile", "--db", self.db_path)[0], 3)

    def test_committed_sample_data_runs_clean(self):
        code, out, _ = cli("run", "--input", os.path.join(REPO, "data/sample/events.csv"),
                           "--users", os.path.join(REPO, "data/sample/users.csv"), "--db", self.db_path,
                           "--report-dir", f"{self.tmp}/rep",
                           "--expected-dir", os.path.join(REPO, "data/expected/sample"))
        self.assertEqual(code, 0, out)
        self.assertIn("rows read=40", out)


if __name__ == "__main__":
    unittest.main()
