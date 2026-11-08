"""Reproductions of reports from BUGS.md (these fail until the reports are fixed)."""

import unittest
from decimal import Decimal

from meterbill import render
from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.rating import price
from meterbill.timeutil import Period, parse_offset, parse_timestamp

D = Decimal
PLANS = {"plans": [
    {"id": "starter", "name": "Starter", "base_fee": "19.00",
     "metrics": [{"metric": "api_calls", "label": "API calls", "unit": "call",
                  "tiers": [{"up_to": None, "unit_price": "0.002"}]}]},
]}


class Bug02VolumeBoundaryTests(unittest.TestCase):
    def test_exactly_1000_gb_uses_first_tier(self):
        tiers = ((D("1000"), D("0.10")), (D("5000"), D("0.08")), (None, D("0.06")))
        self.assertEqual(price("volume", tiers, D("1000")), D("100.00"))


class Bug06HtmlTests(unittest.TestCase):
    def test_account_name_is_escaped_once(self):
        book = PriceBook.from_dict(PLANS)
        account = Account(account_id="obrien", name="O'Brien <Ops>", plan_id="starter")
        invoice = build_invoice(account, book, Period(2026, 3), [])
        html = render.invoices_html([invoice], Period(2026, 3))
        self.assertIn("<h1>Invoice obrien: O&#x27;Brien &lt;Ops&gt;</h1>", html)


class Bug09NegativeHalfHourOffsetTests(unittest.TestCase):
    def test_offset_minus_three_thirty(self):
        self.assertEqual(parse_offset("-03:30"), -210)

    def test_late_evening_event_stays_in_march(self):
        book = PriceBook.from_dict(PLANS)
        account = Account(account_id="avalon", name="Avalon", plan_id="starter",
                          utc_offset=parse_offset("-03:30"))
        events = [UsageEvent(event_id="e1", account_id="avalon", metric="api_calls",
                             quantity=D("500"), unit="call",
                             timestamp=parse_timestamp("2026-04-01T02:45:00Z"))]
        march = build_invoice(account, book, Period(2026, 3), events)
        self.assertEqual(march.section("usage")[0].quantity, D("500"))


if __name__ == "__main__":
    unittest.main()
