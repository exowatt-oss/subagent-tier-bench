import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.summary import summarize, summary_csv
from meterbill.tax import TaxTable, compute_tax
from meterbill.timeutil import Period, parse_timestamp

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
PLANS = {"plans": [
    {"id": "flat", "name": "Flat", "base_fee": "170.50", "metrics": []},
    {"id": "small", "name": "Small", "base_fee": "10.50", "metrics": []},
    {"id": "metered", "name": "Metered", "base_fee": "0.00",
     "metrics": [{"metric": "api_calls", "label": "API calls", "unit": "call",
                  "tiers": [{"up_to": None, "unit_price": "0.025"}]}]},
]}
TAXES = {"US": "5", "US-NY": "8.875"}


def invoice_for(plan_id, region="US", tax_exempt=False, events=()):
    acct = Account(account_id="acct", name="Acct", plan_id=plan_id, region=region,
                   tax_exempt=tax_exempt)
    return build_invoice(acct, PriceBook.from_dict(PLANS), Period(2026, 3), list(events),
                         tax_table=TaxTable(TAXES))


class TaxRoundingTests(unittest.TestCase):
    def test_half_cent_rounds_up(self):
        self.assertEqual(compute_tax(D("10.50"), D("5")), D("0.53"))

    def test_small_half_cent_rounds_up(self):
        self.assertEqual(compute_tax(D("0.50"), D("5")), D("0.03"))

    def test_half_cent_with_fractional_rate(self):
        self.assertEqual(compute_tax(D("12.00"), D("8.875")), D("1.07"))

    def test_invoice_tax_line_rounds_half_up(self):
        invoice = invoice_for("flat")
        self.assertEqual(invoice.tax.description, "Tax (US 5%)")
        self.assertEqual(invoice.tax.amount, D("8.53"))
        self.assertEqual(invoice.total, D("179.03"))

    def test_summary_tax_column_rounds_half_up(self):
        rows = summary_csv(summarize([invoice_for("small")])).splitlines()
        self.assertEqual(rows[1], "1,acct,Acct,10.50,0.00,0.53,11.03")

    def test_cli_json_tax_rounds_half_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
            (data / "accounts.csv").write_text(
                "account_id,name,plan,region\nny,NY Shop,small,us-ny\n", encoding="utf-8")
            (data / "tax.json").write_text(json.dumps({"rates": {"US-NY": "9", "US": "5"}}),
                                           encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(data),
                                   "invoice", "--period", "2026-03", "--format", "json"],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        invoice = json.loads(proc.stdout)[0]
        self.assertEqual(invoice["tax"], {"description": "Tax (US-NY 9%)", "rate": "9",
                                          "amount": "0.95"})
        self.assertEqual(invoice["total"], "11.45")


class TaxRegressionTests(unittest.TestCase):
    def test_odd_half_cent_rounds_up(self):
        self.assertEqual(compute_tax(D("10.70"), D("5")), D("0.54"))

    def test_exempt_account_pays_no_tax(self):
        invoice = invoice_for("flat", tax_exempt=True)
        self.assertEqual(invoice.tax.description, "Tax (exempt)")
        self.assertEqual(invoice.tax.amount, D("0.00"))
        self.assertEqual(invoice.total, D("170.50"))

    def test_usage_line_rounds_half_up(self):
        events = [UsageEvent(event_id="a1", account_id="acct", metric="api_calls",
                             quantity=D("5"), unit="call",
                             timestamp=parse_timestamp("2026-03-03T00:00:00Z"))]
        invoice = invoice_for("metered", region="", events=events)
        self.assertEqual(invoice.section("usage")[0].amount, D("0.13"))


if __name__ == "__main__":
    unittest.main()
