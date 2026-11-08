import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill.errors import InputError
from meterbill.events import load_events, read_events
from meterbill.units import convert

HEADER = "event_id,account_id,metric,quantity,unit,timestamp\n"


class EventFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_read_csv_events(self):
        path = self.write("u.csv", HEADER + "e1,acme,api_calls,1200,call,2026-03-02T14:00:00Z\n")
        events = read_events(path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "e1")
        self.assertEqual(events[0].quantity, Decimal("1200"))
        self.assertEqual(events[0].unit, "call")

    def test_duplicate_event_ids_keep_first(self):
        first = self.write("a.csv", HEADER + "e1,acme,api_calls,10,call,2026-03-02T14:00:00Z\n")
        second = self.write("b.csv", HEADER + "e1,acme,api_calls,99,call,2026-03-03T14:00:00Z\n"
                                     "e2,acme,api_calls,5,call,2026-03-03T14:00:00Z\n")
        log = load_events([first, second])
        self.assertEqual([e.event_id for e in log.events], ["e1", "e2"])
        self.assertEqual(log.events[0].quantity, Decimal("10"))
        self.assertEqual(log.duplicates, 1)

    def test_negative_quantity_is_rejected(self):
        path = self.write("u.csv", HEADER + "e1,acme,api_calls,-1,call,2026-03-02T14:00:00Z\n")
        with self.assertRaises(InputError):
            read_events(path)

    def test_megabytes_convert_to_gigabytes(self):
        self.assertEqual(convert(Decimal("1500"), "MB", "GB"), Decimal("1.5"))


if __name__ == "__main__":
    unittest.main()
