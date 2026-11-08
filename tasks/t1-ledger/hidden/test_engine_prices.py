import datetime
import unittest
from decimal import Decimal

from ledgerlite import Amount, build_ledger, parse_string

D = datetime.date


def ledger_for(text):
    return build_ledger(parse_string(text, "prices.journal"))


class PriceTests(unittest.TestCase):
    def setUp(self):
        self.ledger = ledger_for(
            "P 2024-01-01 AAPL $150.00\n"
            "P 2024-02-01 AAPL $160.00\n"
            "P 2024-03-01 AAPL $170.00\n"
            "P 2024-02-01 AAPL $165.00\n"
            "P 2024-01-01 EUR $1.25\n"
            "P 2024-01-10 $ 0.90 EUR\n"
            "P 2024-03-01 EUR $1.50\n"
            "P 2024-01-01 GBP 1.10 EUR\n"
        )

    def test_latest_direct_price_on_or_before(self):
        self.assertEqual(self.ledger.price("AAPL", "$", D(2024, 2, 15)), Decimal("165.00"))
        self.assertEqual(self.ledger.price("AAPL", "$", D(2024, 3, 1)), Decimal("170.00"))
        self.assertEqual(self.ledger.price("AAPL", "$", D(2024, 2, 29)), Decimal("165.00"))
        self.assertIsNone(self.ledger.price("AAPL", "$", D(2023, 12, 31)))

    def test_inverse_price_when_no_direct(self):
        self.assertEqual(self.ledger.price("$", "EUR", D(2024, 1, 5)), Decimal("0.8"))
        self.assertEqual(self.ledger.price("$", "AAPL", D(2024, 1, 1)), Decimal(1) / Decimal("150.00"))

    def test_direct_beats_more_recent_inverse(self):
        self.assertEqual(self.ledger.price("$", "EUR", D(2024, 6, 1)), Decimal("0.90"))
        self.assertEqual(self.ledger.price("EUR", "$", D(2024, 6, 1)), Decimal("1.50"))

    def test_no_chaining_and_identity(self):
        self.assertIsNone(self.ledger.price("GBP", "$", D(2024, 6, 1)))
        self.assertIsNone(self.ledger.price("AAPL", "EUR", D(2024, 6, 1)))
        self.assertEqual(self.ledger.price("XYZ", "XYZ", D(2000, 1, 1)), Decimal(1))

    def test_convert(self):
        self.assertEqual(
            self.ledger.convert(Amount(Decimal("10"), "AAPL"), "$", D(2024, 2, 1)),
            Amount(Decimal("1650.00"), "$"),
        )
        self.assertEqual(
            self.ledger.convert(Amount(Decimal("-8"), "$"), "EUR", D(2024, 1, 2)),
            Amount(Decimal("-6.4"), "EUR"),
        )
        unchanged = Amount(Decimal("3"), "GBP")
        self.assertEqual(self.ledger.convert(unchanged, "$", D(2024, 6, 1)), unchanged)


if __name__ == "__main__":
    unittest.main()
