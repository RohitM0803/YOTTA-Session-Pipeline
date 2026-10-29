import os
import unittest

from pipeline.ingest import read_csv, read_jsonl, read_source, read_user_ids
from pipeline.schema import Reason, SchemaError
from tests.base import HEADER, PipelineTestCase, ev


class CsvIngestTests(PipelineTestCase):
    def test_reads_valid_rows_with_line_numbers(self):
        p = self.csv_file("a.csv", [ev("e1", "u1", "2026-01-01T10:00:00Z"), ev("e2", "u1", "2026-01-01T10:01:00Z")])
        res = read_csv(p)
        self.assertEqual([(r.data["event_id"], r.source_row) for r in res.records], [("e1", 2), ("e2", 3)])
        self.assertEqual((res.rows_read, res.rejects), (2, []))

    def test_wrong_field_count_is_malformed_row_with_location(self):
        p = self.csv_file("a.csv", [ev("e1", "u1", "2026-01-01T10:00:00Z"), "e2,u1", "e3,u1,click,t,/x,extra,more"])
        res = read_csv(p)
        self.assertEqual(len(res.records), 1)
        self.assertEqual([(r.source_row, r.reason) for r in res.rejects],
                         [(3, Reason.MALFORMED_ROW), (4, Reason.MALFORMED_ROW)])
        self.assertIn("expected 5 fields", res.rejects[0].detail)

    def test_blank_lines_skipped_and_line_numbers_stay_physical(self):
        p = self.write("a.csv", HEADER + "\n\n" + ev("e1", "u1", "2026-01-01T10:00:00Z") + "\n\n\n"
                       + ev("e2", "u1", "2026-01-01T10:01:00Z") + "\n")
        res = read_csv(p)
        self.assertEqual([r.source_row for r in res.records], [3, 6])
        self.assertEqual(res.rows_read, 2)

    def test_missing_required_column_is_schema_error(self):
        p = self.write("a.csv", "event_id,user_id,event_type,page\ne1,u1,click,/x\n")
        with self.assertRaises(SchemaError) as ctx:
            read_csv(p)
        self.assertIn("event_time", str(ctx.exception))
        self.assertTrue(str(ctx.exception).startswith("schema_mismatch"))

    def test_extra_columns_are_ignored_but_reported(self):
        p = self.write("a.csv", HEADER + ",browser\n" + ev("e1", "u1", "2026-01-01T10:00:00Z") + ",chrome\n")
        res = read_csv(p)
        self.assertEqual(res.extra_columns, {"browser"})
        self.assertEqual(len(res.records), 1)

    def test_column_order_does_not_matter(self):
        p = self.write("a.csv", "page,event_time,event_type,user_id,event_id\n/x,2026-01-01T10:00:00Z,click,u1,e1\n")
        self.assertEqual(read_csv(p).records[0].data["event_id"], "e1")

    def test_utf8_bom_is_handled(self):
        p = os.path.join(self.tmp, "bom.csv")
        with open(p, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + (HEADER + "\n" + ev("e1", "u1", "2026-01-01T10:00:00Z") + "\n").encode())
        self.assertEqual(len(read_csv(p).records), 1)

    def test_header_names_are_trimmed_and_case_insensitive(self):
        p = self.write("a.csv", " Event_ID , USER_ID,event_type ,Event_Time,PAGE\ne1,u1,click,2026-01-01T10:00:00Z,/x\n")
        self.assertEqual(len(read_csv(p).records), 1)

    def test_header_only_file_is_an_empty_batch(self):
        res = read_csv(self.write("a.csv", HEADER + "\n"))
        self.assertEqual((res.records, res.rows_read), ([], 0))

    def test_zero_byte_file_is_an_empty_batch(self):
        res = read_csv(self.write("a.csv", ""))
        self.assertEqual((res.records, res.rows_read), ([], 0))

    def test_column_map_renames_source_columns(self):
        p = self.write("a.csv", "id,uid,kind,ts\ne1,u1,click,2026-01-01T10:00:00Z\n")
        res = read_csv(p, {"id": "event_id", "UID": "user_id", "kind": "event_type", "ts": "event_time"})
        self.assertEqual(res.records[0].data["event_time"], "2026-01-01T10:00:00Z")

    def test_duplicate_column_after_mapping_is_error(self):
        p = self.write("a.csv", "event_id,user_id,event_type,event_time,ts\ne1,u1,click,t,t2\n")
        with self.assertRaises(SchemaError):
            read_csv(p, {"ts": "event_time"})

    def test_invalid_utf8_is_clear_schema_error(self):
        p = os.path.join(self.tmp, "bad.csv")
        with open(p, "wb") as fh:
            fh.write(HEADER.encode() + b"\ne1,u1,click,2026-01-01T10:00:00Z,/caf\xe9\n")
        with self.assertRaises(SchemaError) as ctx:
            read_csv(p)
        self.assertIn("not_valid_utf8", str(ctx.exception))

    def test_quoted_commas_are_parsed_correctly(self):
        p = self.write("a.csv", HEADER + '\ne1,u1,click,2026-01-01T10:00:00Z,"/search?q=a,b"\n')
        self.assertEqual(read_csv(p).records[0].data["page"], "/search?q=a,b")


class JsonlIngestTests(PipelineTestCase):
    def test_reads_objects_and_bad_lines(self):
        p = self.write("a.jsonl", '{"event_id":"e1","user_id":"u1","event_type":"click","event_time":"t"}\n'
                                  '{"event_id": "e2", "user_id": \n[1,2,3]\n\n'
                                  '{"event_id":"e3","user_id":"u1","event_type":"click","event_time":null,"x":{"a":1}}\n')
        res = read_jsonl(p)
        self.assertEqual([r.source_row for r in res.records], [1])
        self.assertEqual([(r.source_row, r.reason) for r in res.rejects],
                         [(2, Reason.MALFORMED_ROW), (3, Reason.MALFORMED_ROW), (5, Reason.MALFORMED_ROW)])

    def test_null_values_become_none_and_row_level_missing_keys_are_allowed(self):
        p = self.write("a.jsonl", '{"event_id":"e1","user_id":"u1","event_type":"click","event_time":null}\n'
                                  '{"event_id":"e2","user_id":"u1","event_type":"click","event_time":"t"}\n')
        res = read_jsonl(p)
        self.assertIsNone(res.records[0].data["event_time"])

    def test_required_key_absent_from_every_record_is_schema_error(self):
        p = self.write("a.jsonl", '{"event_id":"e1","user_id":"u1","event_type":"click"}\n')
        with self.assertRaises(SchemaError):
            read_jsonl(p)

    def test_empty_jsonl_is_empty_batch(self):
        self.assertEqual(read_jsonl(self.write("a.jsonl", "")).rows_read, 0)


class SourceAndUsersTests(PipelineTestCase):
    def test_unsupported_extension(self):
        with self.assertRaises(SchemaError):
            read_source(self.write("a.txt", "x"))

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            read_source(os.path.join(self.tmp, "nope.csv"))

    def test_read_user_ids_strips_and_skips_blank(self):
        self.assertEqual(read_user_ids(self.write("u.csv", "user_id\n u1 \n\nu2\n,\n")), ["u1", "u2"])

    def test_users_file_requires_user_id_column(self):
        with self.assertRaises(SchemaError):
            read_user_ids(self.write("u.csv", "id\nu1\n"))


if __name__ == "__main__":
    unittest.main()
