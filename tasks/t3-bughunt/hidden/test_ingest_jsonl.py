import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import load_events, read_events
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "10.00",
     "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB",
                  "tiers": [{"up_to": None, "unit_price": "0.25"}]}]},
]}


def jsonl_line(event_id, quantity_literal, account_id="acct", metric="storage", unit="GB",
               ts="2026-03-20T12:00:00Z"):
    return ('{"event_id": "%s", "account_id": "%s", "metric": "%s", "quantity": %s, '
            '"unit": "%s", "timestamp": "%s"}\n' % (event_id, account_id, metric,
                                                    quantity_literal, unit, ts))


class JsonlTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path


class JsonNumberQuantityTests(JsonlTestCase):
    def test_json_number_is_read_exactly(self):
        events = read_events(self.write("f.jsonl", jsonl_line("j1", "2.675")))
        self.assertEqual(events[0].quantity, D("2.675"))

    def test_json_quantities_add_up_exactly(self):
        text = "".join(jsonl_line("j%d" % i, "0.1") for i in range(3))
        log = load_events([self.write("f.ndjson", text)])
        self.assertEqual(sum((e.quantity for e in log.events), D(0)), D("0.3"))

    def test_json_number_with_four_decimals(self):
        events = read_events(self.write("f.jsonl", jsonl_line("j1", "1.0005")))
        self.assertEqual(events[0].quantity, D("1.0005"))

    def test_storage_line_from_json_number_rounds_half_up(self):
        events = read_events(self.write("f.jsonl", jsonl_line("j1", "10.02")))
        account = Account(account_id="acct", name="Acct", plan_id="basic")
        invoice = build_invoice(account, PriceBook.from_dict(PLANS), Period(2026, 3), events)
        line = invoice.section("usage")[0]
        self.assertEqual(line.quantity, D("10.02"))
        self.assertEqual(line.amount, D("2.51"))

    def test_second_json_feed_amount(self):
        events = read_events(self.write("f.jsonl", jsonl_line("j1", "4.18")))
        account = Account(account_id="acct", name="Acct", plan_id="basic")
        invoice = build_invoice(account, PriceBook.from_dict(PLANS), Period(2026, 3), events)
        self.assertEqual(invoice.section("usage")[0].amount, D("1.05"))

    def test_cli_csv_export_of_json_feed(self):
        data = self.dir / "data"
        data.mkdir()
        (data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
        (data / "accounts.csv").write_text("account_id,name,plan\nacct,Acct,basic\n",
                                           encoding="utf-8")
        feed = self.write("feed.jsonl", jsonl_line("j1", "10.02"))
        proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(data), "invoice",
                               "--period", "2026-03", "--format", "csv", str(feed)],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("acct,2026-03,usage,Storage,10.02,GB,2.51", proc.stdout.splitlines())


class JsonOtherQuantityFormsTests(JsonlTestCase):
    def test_json_string_quantity(self):
        events = read_events(self.write("f.jsonl", jsonl_line("j1", '"2.675"')))
        self.assertEqual(events[0].quantity, D("2.675"))

    def test_json_integer_quantity(self):
        events = read_events(self.write("f.jsonl", jsonl_line("j1", "15000")))
        self.assertEqual(events[0].quantity, D("15000"))


if __name__ == "__main__":
    unittest.main()
