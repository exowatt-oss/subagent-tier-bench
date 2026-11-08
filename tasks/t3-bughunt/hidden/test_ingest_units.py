import unittest
from decimal import Decimal

from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.errors import InputError
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period, parse_timestamp
from meterbill.units import convert

D = Decimal
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "10.00",
     "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB",
                  "tiers": [{"up_to": None, "unit_price": "0.10"}]}]},
]}


class DecimalUnitTests(unittest.TestCase):
    def test_megabytes_are_decimal_units(self):
        self.assertEqual(convert(D("1536"), "MB", "GB"), D("1.536"))

    def test_invoice_quantity_for_megabyte_events(self):
        events = [UsageEvent(event_id="m1", account_id="acct", metric="storage",
                             quantity=D("1536"), unit="MB",
                             timestamp=parse_timestamp("2026-03-05T00:00:00Z"))]
        acct = Account(account_id="acct", name="Acct", plan_id="basic")
        invoice = build_invoice(acct, PriceBook.from_dict(PLANS), Period(2026, 3), events)
        line = invoice.section("usage")[0]
        self.assertEqual(line.quantity, D("1.536"))
        self.assertEqual(line.amount, D("0.15"))

    def test_cross_family_conversion_is_rejected(self):
        with self.assertRaises(InputError):
            convert(D("5"), "MB", "call")


if __name__ == "__main__":
    unittest.main()
