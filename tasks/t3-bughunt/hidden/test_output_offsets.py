import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill import fmt, render
from meterbill.accounts import Account, load_accounts
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period, parse_timestamp
from meterbill.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
MARCH = Period(2026, 3)
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "10.00",
     "metrics": [{"metric": "api_calls", "label": "API calls", "unit": "call",
                  "tiers": [{"up_to": None, "unit_price": "0.01"}]}]},
]}


def call_event(ts, account_id="acct", event_id="e1", quantity="10"):
    return UsageEvent(event_id=event_id, account_id=account_id, metric="api_calls",
                      quantity=D(quantity), unit="call", timestamp=parse_timestamp(ts))


def loaded_account(offset_text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "accounts.csv"
        path.write_text("account_id,name,plan,utc_offset\nacct,Avalon,basic,%s\n" % offset_text,
                        encoding="utf-8")
        return load_accounts(path)["acct"]


class FormatOffsetTests(unittest.TestCase):
    def test_minus_three_thirty(self):
        self.assertEqual(fmt.offset(-210), "-03:30")

    def test_minus_thirty_minutes(self):
        self.assertEqual(fmt.offset(-30), "-00:30")

    def test_minus_nine_thirty(self):
        self.assertEqual(fmt.offset(-570), "-09:30")

    def test_positive_and_zero_offsets(self):
        self.assertEqual(fmt.offset(330), "+05:30")
        self.assertEqual(fmt.offset(0), "+00:00")

    def test_negative_whole_hours(self):
        self.assertEqual(fmt.offset(-300), "-05:00")

    def test_timestamp_keeps_received_offset(self):
        ts = parse_timestamp("2026-03-10T08:00:00-03:30")
        self.assertEqual(fmt.timestamp(ts), "2026-03-10T08:00:00-03:30")

    def test_usage_received_at_keeps_half_hour_offset(self):
        acct = Account(account_id="acct", name="Acct", plan_id="basic", utc_offset=-300)
        workspace = Workspace(PriceBook.from_dict(PLANS), {"acct": acct})
        entries = workspace.usage(MARCH, [call_event("2026-03-10T08:00:00-03:30")])
        row = render.usage_csv(entries).splitlines()[1]
        self.assertEqual(row, "acct,e1,api_calls,10,call,2026-03-10T08:00:00-03:30,"
                              "2026-03-10T06:30:00-05:00")

    def test_text_header_for_offset_in_minutes(self):
        acct = Account(account_id="acct", name="Acct", plan_id="basic", utc_offset=-210)
        invoice = build_invoice(acct, PriceBook.from_dict(PLANS), MARCH, [])
        self.assertIn("Period: 2026-03-01 to 2026-03-31 (UTC-03:30)",
                      render.invoice_text(invoice).splitlines())


class NegativeHalfHourAccountOutputTests(unittest.TestCase):
    def test_text_header_for_loaded_account(self):
        invoice = build_invoice(loaded_account("-03:30"), PriceBook.from_dict(PLANS), MARCH, [])
        self.assertIn("Period: 2026-03-01 to 2026-03-31 (UTC-03:30)",
                      render.invoice_text(invoice).splitlines())

    def test_json_utc_offset_for_loaded_account(self):
        invoice = build_invoice(loaded_account("-03:30"), PriceBook.from_dict(PLANS), MARCH, [])
        self.assertEqual(json.loads(render.invoices_json([invoice]))[0]["utc_offset"], "-03:30")

    def test_usage_local_time_for_loaded_account(self):
        workspace = Workspace(PriceBook.from_dict(PLANS), {"acct": loaded_account("-03:30")})
        entries = workspace.usage(MARCH, [call_event("2026-03-15T12:00:00Z")])
        row = render.usage_csv(entries).splitlines()[1].split(",")
        self.assertEqual(row[5:], ["2026-03-15T12:00:00+00:00", "2026-03-15T08:30:00-03:30"])

    def test_cli_usage_listing_for_half_hour_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
            (data / "accounts.csv").write_text(
                "account_id,name,plan,utc_offset\navalon,Avalon,basic,-03:30\n", encoding="utf-8")
            (data / "u.csv").write_text(
                "event_id,account_id,metric,quantity,unit,timestamp\n"
                "n1,avalon,api_calls,3,call,2026-03-31T22:00:00-03:30\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(data),
                                   "usage", "--period", "2026-03", str(data / "u.csv")],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines()[1:],
                         ["avalon,n1,api_calls,3,call,2026-03-31T22:00:00-03:30,"
                          "2026-03-31T22:00:00-03:30"])


if __name__ == "__main__":
    unittest.main()
