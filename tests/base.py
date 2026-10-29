"""Shared helpers for tests (standard library only)."""
import os
import shutil
import sqlite3
import tempfile
import unittest

from pipeline.config import Config
from pipeline.runner import run_pipeline

HEADER = "event_id,user_id,event_type,event_time,page"


def ev(event_id, user_id, time, page="/home", event_type="click"):
    """One CSV data line."""
    return f"{event_id},{user_id},{event_type},{time},{page}"


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sessions_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db_path = os.path.join(self.tmp, "test.db")

    def cfg(self, **overrides):
        return Config(db_path=self.db_path, report_dir=os.path.join(self.tmp, "reports"), **overrides)

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def csv_file(self, name, lines, header=HEADER):
        return self.write(name, "\n".join([header] + list(lines)) + "\n")

    def users_file(self, ids, name="users.csv"):
        return self.write(name, "\n".join(["user_id"] + list(ids)) + "\n")

    def run_it(self, inputs, users=None, cfg=None, **kwargs):
        if isinstance(inputs, str):
            inputs = [inputs]
        return run_pipeline(cfg or self.cfg(), inputs, users_path=users, **kwargs)

    def conn(self):
        return sqlite3.connect(self.db_path)

    def rows(self, sql, params=()):
        c = self.conn()
        try:
            return c.execute(sql, params).fetchall()
        finally:
            c.close()

    def snapshot(self):
        """Full content of the analytical tables (not the per-run audit tables)."""
        return (self.rows("SELECT event_id, user_id, event_time, page FROM events ORDER BY event_id"),
                self.rows("SELECT session_id, user_id, session_start, session_end, event_count FROM sessions "
                          "ORDER BY session_id"))
