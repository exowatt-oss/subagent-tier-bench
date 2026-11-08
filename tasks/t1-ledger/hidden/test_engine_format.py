import unittest
from decimal import Decimal

from ledgerlite import build_ledger, commodity_precisions, format_amount, parse_string


class FormatTests(unittest.TestCase):
    def test_grouping_and_padding(self):
        self.assertEqual(format_amount(Decimal("1234567.5"), "$", 2), "$1,234,567.50")
        self.assertEqual(format_amount(Decimal("5"), "$", 2), "$5.00")
        self.assertEqual(format_amount(Decimal("3"), "BTC", 4), "3.0000 BTC")
        self.assertEqual(format_amount(Decimal("999"), "¥", 0), "¥999")

    def test_round_half_up_away_from_zero(self):
        self.assertEqual(format_amount(Decimal("0.125"), "$", 2), "$0.13")
        self.assertEqual(format_amount(Decimal("-2.5"), "AAPL", 0), "-3 AAPL")
        self.assertEqual(format_amount(Decimal("1234.5675"), "EUR", 3), "1,234.568 EUR")
        self.assertEqual(format_amount(Decimal("-999.995"), "$", 2), "-$1,000.00")

    def test_zero_never_has_a_minus_sign(self):
        self.assertEqual(format_amount(Decimal("-0.004"), "$", 2), "$0.00")
        self.assertEqual(format_amount(Decimal("-0.4"), "EUR", 0), "0 EUR")
        self.assertEqual(format_amount(Decimal("-0.00"), "£", 1), "£0.0")

    def test_negative_symbol_and_code(self):
        self.assertEqual(format_amount(Decimal("-45.2"), "£", 2), "-£45.20")
        self.assertEqual(format_amount(Decimal("-1000"), "USD", 0), "-1,000 USD")


class PrecisionTests(unittest.TestCase):
    def test_max_over_posting_and_assertion_amounts(self):
        journal = parse_string(
            "2024-01-01 X\n    A  $5\n    B  $12.125\n    C\n\n"
            "2024-01-02 Y\n    A  $0 = $5.0000\n    B  $0\n"
        )
        self.assertEqual(commodity_precisions(journal)["$"], 4)

    def test_costs_do_not_count_when_postings_exist(self):
        journal = parse_string(
            "2024-01-01 Buy\n    Assets:Broker  10 AAPL @ $1.255\n    Assets:Cash  -$12.55\n"
        )
        self.assertEqual(commodity_precisions(journal), {"$": 2, "AAPL": 0})

    def test_fallback_to_costs_and_prices(self):
        journal = parse_string(
            "P 2024-01-01 $ 1.0850 EUR\n"
            "2024-01-02 Fx\n    Assets:Cash  -$10.00 @ 0.9 EUR\n    Assets:Euro\n"
        )
        ledger = build_ledger(journal)
        self.assertEqual(ledger.precision("EUR"), 4)
        self.assertEqual(ledger.precision("$"), 2)

    def test_price_only_commodity_and_unknown_commodity(self):
        journal = parse_string("P 2024-01-01 GOLD $1,900.00\n")
        self.assertEqual(commodity_precisions(journal), {"GOLD": 0, "$": 2})
        self.assertEqual(build_ledger(journal).precision("XYZ"), 0)


if __name__ == "__main__":
    unittest.main()
