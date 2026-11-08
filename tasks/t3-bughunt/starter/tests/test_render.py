import json
import unittest
from decimal import Decimal

from meterbill import render
from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period, parse_timestamp

D = Decimal
PLANS = {"plans": [
    {"id": "std", "name": "Standard", "base_fee": "1250.00",
     "metrics": [{"metric": "api_calls", "label": "API calls", "unit": "call",
                  "tiers": [{"up_to": None, "unit_price": "0.001"}]}]},
]}
MARCH = Period(2026, 3)


def make_invoice():
    book = PriceBook.from_dict(PLANS)
    account = Account(account_id="acme", name="Acme Corp", plan_id="std", utc_offset=-300)
    events = [UsageEvent(event_id="e1", account_id="acme", metric="api_calls",
                         quantity=D("125000"), unit="call",
                         timestamp=parse_timestamp("2026-03-10T12:00:00Z"))]
    return build_invoice(account, book, MARCH, events)


class RenderTests(unittest.TestCase):
    def test_text_header_and_lines(self):
        lines = render.invoice_text(make_invoice()).splitlines()
        self.assertEqual(lines[0], "Invoice acme: Acme Corp")
        self.assertEqual(lines[1], "Plan: Standard (std)")
        self.assertEqual(lines[2], "Period: 2026-03-01 to 2026-03-31 (UTC-05:00)")
        self.assertIn("Base fee".ljust(28) + "".rjust(20) + "1,250.00".rjust(12), lines)
        self.assertIn("API calls".ljust(28) + "125,000 call".rjust(20) + "125.00".rjust(12), lines)

    def test_csv_export_rows(self):
        rows = render.invoices_csv([make_invoice()]).splitlines()
        self.assertEqual(rows[0], "account_id,period,section,description,quantity,unit,amount")
        self.assertEqual(rows[1], "acme,2026-03,fee,Base fee,,,1250.00")
        self.assertEqual(rows[2], "acme,2026-03,usage,API calls,125000,call,125.00")
        self.assertEqual(rows[-1], "acme,2026-03,total,Total,,,1375.00")

    def test_json_amounts_are_strings(self):
        data = json.loads(render.invoices_json([make_invoice()]))
        self.assertEqual(data[0]["subtotal"], "1375.00")
        self.assertEqual(data[0]["lines"][1]["quantity"], "125000")
        self.assertEqual(data[0]["utc_offset"], "-05:00")


if __name__ == "__main__":
    unittest.main()
