import unittest
from datetime import datetime, timedelta, timezone

from meterbill.errors import InputError
from meterbill.timeutil import Period, parse_offset, parse_timestamp


class TimestampTests(unittest.TestCase):
    def test_parse_timestamp_with_z(self):
        ts = parse_timestamp("2026-03-02T14:00:00Z")
        self.assertEqual(ts, datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc))

    def test_parse_timestamp_with_offset(self):
        ts = parse_timestamp("2026-03-02T16:00:00+02:00")
        self.assertEqual(ts.utcoffset(), timedelta(hours=2))
        self.assertEqual(ts, datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc))

    def test_timestamp_without_designator_is_rejected(self):
        with self.assertRaises(InputError):
            parse_timestamp("2026-03-02T14:00:00")


class OffsetAndPeriodTests(unittest.TestCase):
    def test_parse_positive_half_hour_offset(self):
        self.assertEqual(parse_offset("+05:30"), 330)

    def test_leap_february_has_29_days(self):
        period = Period.parse("2028-02")
        self.assertEqual(period.days, 29)
        self.assertEqual(period.last_day.isoformat(), "2028-02-29")

    def test_first_instant_belongs_to_period(self):
        period = Period.parse("2026-03")
        self.assertTrue(period.contains(parse_timestamp("2026-03-01T00:00:00Z"), 0))
        self.assertFalse(period.contains(parse_timestamp("2026-02-28T23:59:59Z"), 0))


if __name__ == "__main__":
    unittest.main()
