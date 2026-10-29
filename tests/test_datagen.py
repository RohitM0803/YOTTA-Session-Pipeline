import csv
import os
import unittest

from pipeline.datagen import generate
from pipeline.reconcile import compare_with_expected, reconcile
from pipeline.schema import Reason
from tests.base import PipelineTestCase


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


class GeneratorTests(PipelineTestCase):
    def gen(self, name, **kw):
        return generate(f"{self.tmp}/{name}", f"{self.tmp}/{name}_exp", **kw)

    def test_same_seed_gives_byte_identical_files(self):
        self.gen("a", rows=800, seed=11)
        self.gen("b", rows=800, seed=11)
        self.assertEqual(read(f"{self.tmp}/a/events.csv"), read(f"{self.tmp}/b/events.csv"))
        self.assertEqual(read(f"{self.tmp}/a_exp/expected_sessions.csv"), read(f"{self.tmp}/b_exp/expected_sessions.csv"))
        self.assertEqual(read(f"{self.tmp}/a_exp/expected_rejects.csv"), read(f"{self.tmp}/b_exp/expected_rejects.csv"))

    def test_different_seed_gives_different_data(self):
        self.gen("a", rows=800, seed=1)
        self.gen("b", rows=800, seed=2)
        self.assertNotEqual(read(f"{self.tmp}/a/events.csv"), read(f"{self.tmp}/b/events.csv"))

    def test_row_count_is_exact_and_labels_are_separate_from_input(self):
        m = self.gen("a", rows=777, seed=4)
        with open(f"{self.tmp}/a/events.csv", newline="") as fh:
            self.assertEqual(len(list(csv.reader(fh))), 778)    # header + rows
        self.assertEqual(sorted(os.listdir(f"{self.tmp}/a")), ["events.csv", "users.csv"])
        self.assertIn("expected_sessions.csv", os.listdir(f"{self.tmp}/a_exp"))
        self.assertEqual(m["valid_unique_events"] + m["expected_rejects"], 777)

    def test_every_anomaly_type_is_present_in_a_moderate_file(self):
        m = self.gen("a", rows=1000, seed=9)
        self.assertEqual(set(m["expected_rejects_by_reason"]), set(Reason.ALL))

    def test_pipeline_matches_answer_key_csv(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self.db_path = f"{self.tmp}/s{seed}.db"
                m = self.gen(f"c{seed}", rows=3000, seed=seed)
                res = self.run_it(m["events_file"], users=f"{self.tmp}/c{seed}/users.csv")
                self.assertEqual(res.status, "SUCCESS")
                c = self.conn()
                checks = reconcile(c, res.run_id) + compare_with_expected(c, f"{self.tmp}/c{seed}_exp", res.run_id)
                c.close()
                self.assertEqual([x.name for x in checks if not x.passed], [])

    def test_pipeline_matches_answer_key_jsonl(self):
        m = self.gen("j", rows=3000, seed=8, fmt="jsonl")
        res = self.run_it(m["events_file"], users=f"{self.tmp}/j/users.csv")
        c = self.conn()
        checks = reconcile(c, res.run_id) + compare_with_expected(c, f"{self.tmp}/j_exp", res.run_id)
        c.close()
        self.assertEqual([x.name for x in checks if not x.passed], [])

    def test_pipeline_matches_answer_key_with_different_gap(self):
        m = self.gen("g", rows=2000, seed=6, gap_minutes=10)
        res = self.run_it(m["events_file"], users=f"{self.tmp}/g/users.csv", cfg=self.cfg(gap_minutes=10))
        c = self.conn()
        checks = compare_with_expected(c, f"{self.tmp}/g_exp", res.run_id)
        c.close()
        self.assertEqual([x.name for x in checks if not x.passed], [])

    def test_wrong_gap_does_not_match_answer_key(self):
        # sanity check that the answer key is actually sensitive to the gap rule
        m = self.gen("g", rows=2000, seed=6, gap_minutes=10)
        res = self.run_it(m["events_file"], users=f"{self.tmp}/g/users.csv", cfg=self.cfg(gap_minutes=30))
        c = self.conn()
        checks = compare_with_expected(c, f"{self.tmp}/g_exp", res.run_id)
        c.close()
        self.assertIn("sessions_match_answer_key", [x.name for x in checks if not x.passed])

    def test_tiny_sizes_work(self):
        for rows in (1, 2, 5):
            with self.subTest(rows=rows):
                self.assertEqual(self.gen(f"t{rows}", rows=rows, seed=1)["rows"], rows)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            self.gen("x", rows=0)
        with self.assertRaises(ValueError):
            self.gen("x", rows=10, fmt="xml")
        with self.assertRaises(ValueError):
            self.gen("x", rows=10, anomaly_rate=1.0)


if __name__ == "__main__":
    unittest.main()
