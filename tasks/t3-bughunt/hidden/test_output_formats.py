import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill import render
from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent, read_events
from meterbill.invoice import build_invoice
from meterbill.tax import TaxTable
from meterbill.timeutil import Period, parse_timestamp
from meterbill.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
MARCH = Period(2026, 3)
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "1200.00",
     "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB",
                  "tiers": [{"up_to": None, "unit_price": "0.25"}]}]},
]}
FEED_LINE = ('{"event_id": "j1", "account_id": "acct", "metric": "storage", "quantity": %s, '
             '"unit": "GB", "timestamp": "2026-03-20T12:00:00Z"}\n')


class OutputTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def feed_invoice(self, literal):
        path = self.dir / "feed.jsonl"
        path.write_text(FEED_LINE % literal, encoding="utf-8")
        acct = Account(account_id="acct", name="Acct", plan_id="basic")
        return build_invoice(acct, PriceBook.from_dict(PLANS), MARCH, read_events(path))


class JsonFeedOutputTests(OutputTestCase):
    def test_usage_listing_quantity_from_json_feed(self):
        data = self.dir / "data"
        data.mkdir()
        (data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
        (data / "accounts.csv").write_text("account_id,name,plan\nacct,Acct,basic\n",
                                           encoding="utf-8")
        feed = self.dir / "feed.jsonl"
        feed.write_text(FEED_LINE % "2.675", encoding="utf-8")
        proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(data), "usage",
                               "--period", "2026-03", str(feed)],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines()[1].split(",")[3:5], ["2.675", "GB"])

    def test_json_export_of_json_feed(self):
        data = json.loads(render.invoices_json([self.feed_invoice("10.02")]))
        storage = data[0]["lines"][1]
        self.assertEqual((storage["quantity"], storage["amount"]), ("10.02", "2.51"))



class FormatRegressionTests(OutputTestCase):
    def test_usage_listing_megabytes_in_canonical_unit(self):
        acct = Account(account_id="acct", name="Acct", plan_id="basic")
        workspace = Workspace(PriceBook.from_dict(PLANS), {"acct": acct})
        events = [UsageEvent(event_id="m1", account_id="acct", metric="storage",
                             quantity=D("1536"), unit="MB",
                             timestamp=parse_timestamp("2026-03-05T00:00:00Z"))]
        row = render.usage_csv(workspace.usage(MARCH, events)).splitlines()[1]
        self.assertEqual(row.split(",")[3:5], ["1.536", "GB"])

    def test_json_values_are_strings(self):
        acct = Account(account_id="acct", name="Acct", plan_id="basic", region="DE")
        invoice = build_invoice(acct, PriceBook.from_dict(PLANS), MARCH, [],
                                tax_table=TaxTable({"DE": "19"}))
        data = json.loads(render.invoices_json([invoice]))[0]
        self.assertEqual(data["subtotal"], "1200.00")
        self.assertEqual(data["tax"], {"description": "Tax (DE 19%)", "rate": "19",
                                       "amount": "228.00"})
        self.assertEqual(data["total"], "1428.00")

    def test_text_totals_block(self):
        acct = Account(account_id="acct", name="Acct", plan_id="basic", region="DE")
        invoice = build_invoice(acct, PriceBook.from_dict(PLANS), MARCH, [],
                                tax_table=TaxTable({"DE": "19"}))
        lines = render.invoice_text(invoice).splitlines()
        start = lines.index("-" * 60)
        self.assertEqual(lines[start + 1:start + 4],
                         ["Subtotal".ljust(48) + "1,200.00".rjust(12),
                          "Tax (DE 19%)".ljust(48) + "228.00".rjust(12),
                          "Total".ljust(48) + "1,428.00".rjust(12)])


if __name__ == "__main__":
    unittest.main()
