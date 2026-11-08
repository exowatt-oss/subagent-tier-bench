import unittest
from decimal import Decimal

from meterbill.catalog import PriceBook
from meterbill.rating import price, rate_metric

D = Decimal
TIERS = ((D("1000"), D("0.10")), (D("5000"), D("0.08")), (None, D("0.06")))


class RatingTests(unittest.TestCase):
    def test_graduated_spans_tiers(self):
        self.assertEqual(price("graduated", TIERS, D("1500")), D("140.00"))

    def test_volume_inside_second_tier(self):
        self.assertEqual(price("volume", TIERS, D("1500")), D("120.00"))

    def test_included_allowance_is_subtracted_first(self):
        book = PriceBook.from_dict({"plans": [{
            "id": "p", "metrics": [{
                "metric": "api_calls", "unit": "call", "included": "1000",
                "tiers": [{"up_to": None, "unit_price": "0.002"}]}]}]})
        metric = book.plan("p").metric("api_calls")
        rated = rate_metric(metric, book.tiers("p", "api_calls"), D("4500"))
        self.assertEqual(rated.billable, D("3500"))
        self.assertEqual(rated.amount, D("7.00"))


if __name__ == "__main__":
    unittest.main()
