import unittest
from datetime import date
from decimal import Decimal

from meterbill.accounts import Account, Coupon
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.tax import TaxTable
from meterbill.timeutil import Period, parse_timestamp

D = Decimal
PLANS = {"plans": [
    {"id": "std", "name": "Standard", "base_fee": "50.00", "minimum_commit": "40.00",
     "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB",
                  "tiers": [{"up_to": None, "unit_price": "0.25"}]}]},
]}
MARCH = Period(2026, 3)


def event(event_id, account_id, quantity, unit="GB", ts="2026-03-10T12:00:00Z", metric="storage"):
    return UsageEvent(event_id=event_id, account_id=account_id, metric=metric,
                      quantity=D(quantity), unit=unit, timestamp=parse_timestamp(ts))


class InvoiceTests(unittest.TestCase):
    def setUp(self):
        self.book = PriceBook.from_dict(PLANS)

    def test_simple_invoice_totals(self):
        account = Account(account_id="acme", name="Acme", plan_id="std", region="US-NY",
                          coupons=("WELCOME10",))
        coupons = {"WELCOME10": Coupon("WELCOME10", "percent", D("10"))}
        taxes = TaxTable({"US-NY": "8.875"})
        invoice = build_invoice(account, self.book, MARCH, [event("e1", "acme", "200")],
                                coupons=coupons, tax_table=taxes)
        self.assertEqual([l.amount for l in invoice.lines], [D("50.00"), D("50.00")])
        self.assertEqual(invoice.subtotal, D("100.00"))
        self.assertEqual([l.amount for l in invoice.discounts], [D("-10.00")])
        self.assertEqual(invoice.tax.amount, D("7.99"))
        self.assertEqual(invoice.total, D("97.99"))

    def test_minimum_commitment_top_up(self):
        account = Account(account_id="acme", name="Acme", plan_id="std")
        invoice = build_invoice(account, self.book, MARCH, [event("e1", "acme", "100")])
        top_up = invoice.section("adjustment")
        self.assertEqual(len(top_up), 1)
        self.assertEqual(top_up[0].description, "Minimum commitment top-up")
        self.assertEqual(top_up[0].amount, D("15.00"))
        self.assertEqual(invoice.total, D("90.00"))

    def test_prorated_base_fee(self):
        account = Account(account_id="late", name="Late", plan_id="std",
                          start_date=date(2026, 3, 17))
        invoice = build_invoice(account, self.book, MARCH, [event("e1", "late", "200")])
        self.assertEqual(invoice.lines[0].amount, D("24.19"))
        self.assertIn("Base fee prorated: 15 of 31 days", invoice.notes)


if __name__ == "__main__":
    unittest.main()
