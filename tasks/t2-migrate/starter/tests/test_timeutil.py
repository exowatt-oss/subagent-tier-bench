import unittest
from datetime import date, datetime, timezone

from wotrack import timeutil


class ParseTimestampTest(unittest.TestCase):
    def test_offset_is_converted_to_utc(self):
        self.assertEqual(
            timeutil.parse_timestamp("2026-03-01 11:15:00+02:00"),
            datetime(2026, 3, 1, 9, 15, tzinfo=timezone.utc),
        )

    def test_minutes_precision_and_fraction(self):
        self.assertEqual(
            timeutil.parse_timestamp("2026-03-01T09:15"),
            datetime(2026, 3, 1, 9, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(
            timeutil.parse_timestamp("2026-03-01 09:15:07.999Z"),
            datetime(2026, 3, 1, 9, 15, 7, tzinfo=timezone.utc),
        )

    def test_dates_are_strict(self):
        self.assertEqual(timeutil.parse_date("2026-03-01"), date(2026, 3, 1))
        with self.assertRaises(ValueError):
            timeutil.parse_date("2026-3-1")


if __name__ == "__main__":
    unittest.main()
