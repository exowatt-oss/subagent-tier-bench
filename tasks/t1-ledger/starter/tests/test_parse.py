import datetime
import os
import unittest
from decimal import Decimal
from pathlib import Path

from ledgerlite import Amount, ParseError, parse_amount, parse_file, parse_string

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class ParseVisibleTests(unittest.TestCase):
    def test_example_transaction_header(self):
        journal = parse_file(str(EXAMPLES / "basic.journal"))
        txn = journal.transactions[1]
        self.assertEqual(txn.date, datetime.date(2024, 1, 5))
        self.assertEqual(txn.status, "*")
        self.assertEqual(txn.code, "1001")
        self.assertEqual(txn.description, "Grocery store")
        self.assertEqual(txn.comment, "weekly shop")
        self.assertEqual(txn.lineno, 8)
        self.assertEqual([p.account for p in txn.postings], ["Expenses:Food:Groceries", "Assets:Bank:Checking"])
        self.assertEqual(txn.postings[0].amount, Amount(Decimal("45.20"), "$"))
        self.assertIsNone(txn.postings[1].amount)

    def test_status_flags(self):
        journal = parse_file(str(EXAMPLES / "basic.journal"))
        self.assertEqual([t.status for t in journal.transactions], ["*", "*", "!", "", "*"])

    def test_amount_forms(self):
        self.assertEqual(str(parse_amount("$1,234.50").quantity), "1234.50")
        self.assertEqual(parse_amount("$-5"), Amount(Decimal("-5"), "$"))
        self.assertEqual(parse_amount("-3 AAPL"), Amount(Decimal("-3"), "AAPL"))
        for bad in ("12", "USD 5", "5.", "1,23 EUR"):
            with self.assertRaises(ValueError):
                parse_amount(bad)

    def test_cost_and_assertion(self):
        journal = parse_string(
            "2024-01-01 Buy\n    Assets:Broker  20 AAPL @ $170.25 = 20 AAPL\n    Assets:Cash\n"
        )
        posting = journal.transactions[0].postings[0]
        self.assertEqual(posting.amount, Amount(Decimal("20"), "AAPL"))
        self.assertEqual(posting.cost_type, "@")
        self.assertEqual(posting.cost, Amount(Decimal("170.25"), "$"))
        self.assertEqual(posting.assertion, Amount(Decimal("20"), "AAPL"))

    def test_parse_error_format(self):
        with self.assertRaises(ParseError) as cm:
            parse_string("; comment\n\n2024-02-30 Bad\n    A  $1\n    B\n", "v.journal")
        self.assertEqual(cm.exception.lineno, 3)
        self.assertEqual(str(cm.exception), "v.journal:3: invalid date '2024-02-30'")

    def test_unexpected_indented_line(self):
        with self.assertRaises(ParseError) as cm:
            parse_string("2024-01-01 X\n    A  $1\n    B\n\n    C  $2\n", "v.journal")
        self.assertEqual(str(cm.exception), "v.journal:5: unexpected indented line")

    def test_include_and_prices(self):
        journal = parse_file(str(EXAMPLES / "invest.journal"))
        self.assertEqual(len(journal.transactions), 4)
        self.assertEqual([p.price for p in journal.prices], [Amount(Decimal("171.00"), "$"), Amount(Decimal("180.50"), "$")])
        self.assertEqual(journal.prices[0].filename, os.path.join(str(EXAMPLES), "invest-prices.journal"))
        self.assertEqual(journal.prices[1].lineno, 3)


if __name__ == "__main__":
    unittest.main()
