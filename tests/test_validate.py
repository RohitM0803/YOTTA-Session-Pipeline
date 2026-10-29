import unittest

from pipeline.models import RawRecord, Reject, ValidEvent
from pipeline.schema import Reason
from pipeline.validate import clean_text, parse_timestamp, validate_record


def rec(**fields):
    data = {"event_id": "e1", "user_id": "u1", "event_type": "click",
            "event_time": "2026-01-01T10:00:00Z", "page": "/home"}
    data.update(fields)
    return RawRecord("f.csv", 7, data, "{}")


class ParseTimestampTests(unittest.TestCase):
    def test_utc_z(self):
        self.assertEqual(parse_timestamp("2026-01-01T10:00:00Z")[0], "2026-01-01T10:00:00Z")

    def test_offset_is_converted_to_utc(self):
        self.assertEqual(parse_timestamp("2026-01-01T15:30:00+05:30")[0], "2026-01-01T10:00:00Z")

    def test_naive_timestamp_is_assumed_utc(self):
        self.assertEqual(parse_timestamp("2026-01-01T10:00:00")[0], "2026-01-01T10:00:00Z")

    def test_space_separator_and_whitespace_accepted(self):
        self.assertEqual(parse_timestamp("  2026-01-01 10:00:00 ")[0], "2026-01-01T10:00:00Z")

    def test_subseconds_are_truncated(self):
        self.assertEqual(parse_timestamp("2026-01-01T10:00:00.987Z")[0], "2026-01-01T10:00:00Z")

    def test_epoch_seconds_value_matches(self):
        self.assertEqual(parse_timestamp("2000-01-01T00:00:00Z")[1], 946684800)

    def test_invalid_values_raise(self):
        for bad in ["not-a-time", "2026-01-01", "1767225600", "2026-13-45T99:00:00Z", "yesterday",
                    "0000-00-00T00:00:00Z", "1970-01-01T00:00:00Z", "9999-12-31T23:59:59Z", "2026-02-30T10:00:00Z"]:
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    parse_timestamp(bad)


class CleanTextTests(unittest.TestCase):
    def test_null_like_values(self):
        for v in [None, "", "  ", "NULL", "null", "None", "NaN", "n/a"]:
            with self.subTest(value=v):
                self.assertIsNone(clean_text(v))

    def test_strips_whitespace(self):
        self.assertEqual(clean_text("  abc "), "abc")


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_is_normalised(self):
        out = validate_record(rec(event_id=" e1 ", event_time="2026-01-01T15:30:00+05:30"))
        self.assertIsInstance(out, ValidEvent)
        self.assertEqual((out.event_id, out.event_time, out.source_row), ("e1", "2026-01-01T10:00:00Z", 7))

    def test_missing_required_fields(self):
        for field in ("event_id", "user_id", "event_type"):
            for blank in ("", "NULL", None):
                with self.subTest(field=field, blank=blank):
                    out = validate_record(rec(**{field: blank}))
                    self.assertIsInstance(out, Reject)
                    self.assertEqual(out.reason, Reason.MISSING_REQUIRED_FIELD)
                    self.assertIn(field, out.detail)

    def test_missing_key_entirely(self):
        r = rec()
        del r.data["event_time"]
        self.assertEqual(validate_record(r).reason, Reason.MISSING_TIMESTAMP)

    def test_missing_timestamp(self):
        for blank in ("", "null", None):
            self.assertEqual(validate_record(rec(event_time=blank)).reason, Reason.MISSING_TIMESTAMP)

    def test_invalid_timestamp(self):
        self.assertEqual(validate_record(rec(event_time="garbage-text-here")).reason, Reason.INVALID_TIMESTAMP)

    def test_unknown_user_is_invalid_reference_key(self):
        out = validate_record(rec(user_id="ghost"), known_users={"u1"})
        self.assertEqual(out.reason, Reason.INVALID_REFERENCE_KEY)

    def test_reference_check_skipped_when_users_unknown(self):
        self.assertIsInstance(validate_record(rec(user_id="ghost"), known_users=None), ValidEvent)

    def test_rule_precedence_is_deterministic(self):
        # missing field beats bad timestamp; bad timestamp beats unknown user
        self.assertEqual(validate_record(rec(user_id="", event_time="x"), {"u9"}).reason,
                         Reason.MISSING_REQUIRED_FIELD)
        self.assertEqual(validate_record(rec(user_id="ghost", event_time="zzzzzzzzzzzzz"), {"u1"}).reason,
                         Reason.INVALID_TIMESTAMP)

    def test_reject_keeps_traceability(self):
        out = validate_record(rec(event_id=""))
        self.assertEqual((out.source_file, out.source_row), ("f.csv", 7))

    def test_page_is_optional(self):
        self.assertIsNone(validate_record(rec(page="")).page)


if __name__ == "__main__":
    unittest.main()
