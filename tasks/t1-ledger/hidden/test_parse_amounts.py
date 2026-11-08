import unittest
from decimal import Decimal

from ledgerlite import Amount, ParseError, parse_amount, parse_string


def first_posting(line):
    text = "2024-01-01 Test\n" + line + "\n    Assets:Cash\n"
    return parse_string(text, "a.journal").transactions[0].postings[0]


def error_for(line):
    text = "2024-01-01 Test\n" + line + "\n    Assets:Cash\n"
    try:
        parse_string(text, "a.journal")
    except ParseError as exc:
        return exc
    raise AssertionError("no ParseError raised")


class AmountTests(unittest.TestCase):
    def test_minus_before_or_after_symbol(self):
        self.assertEqual(parse_amount("-$5"), Amount(Decimal("-5"), "$"))
        self.assertEqual(parse_amount("$-5"), Amount(Decimal("-5"), "$"))
        self.assertEqual(parse_amount("  £0.75 "), Amount(Decimal("0.75"), "£"))

    def test_code_form_with_grouping(self):
        amount = parse_amount("-1,234,567.80   USD")
        self.assertEqual(amount.commodity, "USD")
        self.assertEqual(str(amount.quantity), "-1234567.80")

    def test_bad_number_shapes_rejected(self):
        for text in ("$1,23", "1234,567 EUR", ".5 EUR", "5. EUR", "$1,2345", "$1.2.3"):
            with self.assertRaises(ValueError, msg=text):
                parse_amount(text)

    def test_bad_commodity_placement_and_signs_rejected(self):
        for text in ("12", "5$", "USD 5", "5 usd", "$ 5", "5USD", "+$5", "--$5", "-$-5", "- 5 EUR"):
            with self.assertRaises(ValueError, msg=text):
                parse_amount(text)

    def test_amount_cost_assertion_and_comment(self):
        p = first_posting("    Assets:Broker  -2 AAPL @@ $300=8 AAPL ; sold some")
        self.assertEqual(p.amount, Amount(Decimal("-2"), "AAPL"))
        self.assertEqual(p.cost, Amount(Decimal("300"), "$"))
        self.assertEqual(p.cost_type, "@@")
        self.assertEqual(p.assertion, Amount(Decimal("8"), "AAPL"))
        self.assertEqual(p.comment, "sold some")

    def test_cost_without_amount(self):
        exc = error_for("    Assets:Broker  @ $5")
        self.assertEqual(exc.message, "invalid amount ''")

    def test_negative_cost(self):
        exc = error_for("    Assets:Broker  10 AAPL @ -$5")
        self.assertEqual(str(exc), "a.journal:2: cost must not be negative")

    def test_cost_in_same_commodity(self):
        exc = error_for("    Assets:Bank  $10 @@ $10")
        self.assertEqual(exc.message, "cost commodity must differ from amount commodity")

    def test_assertion_needs_explicit_amount(self):
        exc = error_for("    Assets:Bank   = $5")
        self.assertEqual(str(exc), "a.journal:2: balance assertion requires an explicit amount")


if __name__ == "__main__":
    unittest.main()
