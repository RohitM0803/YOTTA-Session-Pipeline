import unittest

from pipeline.models import SessionEvent
from pipeline.sessionize import make_session_id, sessionize

BASE = 1767268800  # 2026-01-01T12:00:00Z


def iso(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def events(*offsets, prefix="e"):
    return [SessionEvent(f"{prefix}{i:03d}", iso(BASE + o), BASE + o) for i, o in enumerate(offsets)]


G = 1800  # 30 minutes


class SessionizeTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(sessionize("u1", [], G), [])

    def test_single_event_is_a_bounce_with_zero_duration(self):
        (s,) = sessionize("u1", events(0), G)
        self.assertEqual((s.event_count, s.duration_seconds, s.is_bounce), (1, 0, 1))

    def test_gap_of_exactly_30_minutes_stays_in_same_session(self):
        sessions = sessionize("u1", events(0, G), G)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].duration_seconds, G)

    def test_gap_of_30_minutes_1_second_starts_new_session(self):
        sessions = sessionize("u1", events(0, G + 1), G)
        self.assertEqual([s.event_count for s in sessions], [1, 1])

    def test_gap_is_measured_from_previous_event_not_session_start(self):
        # each step is < gap, total span far exceeds gap -> still one session
        sessions = sessionize("u1", events(*[i * 1500 for i in range(10)]), G)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].event_count, 10)

    def test_out_of_order_input_gives_same_result_as_sorted(self):
        ordered = events(0, 60, 120, 5000, 5060)
        shuffled = [ordered[3], ordered[0], ordered[4], ordered[2], ordered[1]]
        self.assertEqual(sessionize("u1", shuffled, G), sessionize("u1", ordered, G))

    def test_identical_timestamps_are_one_session_and_deterministic(self):
        a = [SessionEvent("b", iso(BASE), BASE), SessionEvent("a", iso(BASE), BASE)]
        s1 = sessionize("u1", a, G)
        s2 = sessionize("u1", list(reversed(a)), G)
        self.assertEqual(s1, s2)
        self.assertEqual((s1[0].event_count, s1[0].duration_seconds), (2, 0))

    def test_session_can_span_midnight(self):
        # 23:50 and 00:10 (next day) UTC are 20 minutes apart
        t1 = 1767311400 + 0   # 2026-01-01T23:50:00Z
        evs = [SessionEvent("a", iso(t1), t1), SessionEvent("b", iso(t1 + 1200), t1 + 1200)]
        (s,) = sessionize("u1", evs, G)
        self.assertEqual((s.session_start[:10], s.session_end[:10]), ("2026-01-01", "2026-01-02"))

    def test_multiple_sessions_values(self):
        s1, s2, s3 = sessionize("u1", events(0, 600, 1200, 10000, 20000, 20100), G)
        self.assertEqual((s1.event_count, s1.duration_seconds, s1.is_bounce), (3, 1200, 0))
        self.assertEqual((s2.event_count, s2.is_bounce), (1, 1))
        self.assertEqual((s3.event_count, s3.duration_seconds), (2, 100))
        self.assertLess(s1.session_end_ts, s2.session_start_ts)

    def test_session_id_is_deterministic_and_user_specific(self):
        self.assertEqual(make_session_id("u1", "2026-01-01T12:00:00Z"), make_session_id("u1", "2026-01-01T12:00:00Z"))
        self.assertNotEqual(make_session_id("u1", "2026-01-01T12:00:00Z"), make_session_id("u2", "2026-01-01T12:00:00Z"))
        self.assertTrue(make_session_id("u1", "x").startswith("ses_"))

    def test_gap_setting_changes_result(self):
        evs = events(0, 600)
        self.assertEqual(len(sessionize("u1", evs, 900)), 1)
        self.assertEqual(len(sessionize("u1", evs, 599)), 2)

    def test_invalid_gap_rejected(self):
        with self.assertRaises(ValueError):
            sessionize("u1", events(0), 0)


if __name__ == "__main__":
    unittest.main()
