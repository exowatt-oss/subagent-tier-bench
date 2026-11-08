import unittest
from decimal import Decimal

from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.rating import price, rate_metric
from meterbill.timeutil import Period, parse_timestamp

D = Decimal
TIERS = ((D("1000"), D("0.10")), (D("5000"), D("0.08")), (None, D("0.06")))
PLANS = {"plans": [
    {"id": "pro", "name": "Pro", "base_fee": "0.00",
     "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB", "pricing": "volume",
                  "tiers": [{"up_to": "1000", "unit_price": "0.10"},
                            {"up_to": "5000", "unit_price": "0.08"},
                            {"up_to": None, "unit_price": "0.06"}]}]},
    {"id": "allow", "name": "Allowance", "base_fee": "0.00",
     "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB", "pricing": "volume",
                  "included": "500",
                  "tiers": [{"up_to": "1000", "unit_price": "0.10"},
                            {"up_to": "5000", "unit_price": "0.08"},
                            {"up_to": None, "unit_price": "0.06"}]}]},
]}


def storage_invoice(quantity, unit="GB", plan_id="pro"):
    book = PriceBook.from_dict(PLANS)
    acct = Account(account_id="acct", name="Acct", plan_id=plan_id)
    events = [UsageEvent(event_id="s1", account_id="acct", metric="storage",
                         quantity=D(quantity), unit=unit,
                         timestamp=parse_timestamp("2026-03-12T00:00:00Z"))]
    return build_invoice(acct, book, Period(2026, 3), events)


class VolumeBoundaryTests(unittest.TestCase):
    def test_volume_exactly_at_first_boundary(self):
        self.assertEqual(price("volume", TIERS, D("1000")), D("100"))

    def test_volume_exactly_at_second_boundary(self):
        self.assertEqual(price("volume", TIERS, D("5000")), D("400"))

    def test_volume_boundary_written_with_trailing_zeros(self):
        self.assertEqual(price("volume", TIERS, D("1000.000")), D("100"))

    def test_volume_boundary_reached_after_allowance(self):
        book = PriceBook.from_dict(PLANS)
        metric = book.plan("allow").metric("storage")
        rated = rate_metric(metric, book.tiers("allow", "storage"), D("1500"))
        self.assertEqual(rated.billable, D("1000"))
        self.assertEqual(rated.amount, D("100.00"))

    def test_invoice_line_at_boundary(self):
        line = storage_invoice("1000").section("usage")[0]
        self.assertEqual(line.amount, D("100.00"))

    def test_invoice_line_at_boundary_from_megabytes(self):
        line = storage_invoice("1000000", unit="MB").section("usage")[0]
        self.assertEqual(line.quantity, D("1000"))
        self.assertEqual(line.amount, D("100.00"))


class TierRegressionTests(unittest.TestCase):
    def test_volume_just_above_boundary_uses_next_tier(self):
        self.assertEqual(price("volume", TIERS, D("1000.001")), D("80.00008"))

    def test_volume_just_below_boundary(self):
        self.assertEqual(price("volume", TIERS, D("999.5")), D("99.95"))

    def test_graduated_exactly_at_boundary(self):
        self.assertEqual(price("graduated", TIERS, D("1000")), D("100"))

    def test_graduated_across_two_boundaries(self):
        self.assertEqual(price("graduated", TIERS, D("6000")), D("480"))


if __name__ == "__main__":
    unittest.main()
