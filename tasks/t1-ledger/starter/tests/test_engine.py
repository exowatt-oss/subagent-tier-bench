import datetime
import unittest
from decimal import Decimal
from pathlib import Path

from ledgerlite import (
    Amount,
    AssertionFailure,
    BalanceError,
    build_ledger,
    commodity_precisions,
    format_amount,
    load,
    parse_string,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class EngineVisibleTests(unittest.TestCase):
    def test_format_amount_examples(self):
        self.assertEqual(format_amount(Decimal("1234.5"), "$", 2), "$1,234.50")
        self.assertEqual(format_amount(Decimal("-0.125"), "$", 2), "-$0.13")
        self.assertEqual(format_amount(Decimal("-0.004"), "€", 2), "€0.00")
        self.assertEqual(format_amount(Decimal("-1000"), "USD", 0), "-1,000 USD")
        self.assertEqual(format_amount(Decimal("2.5"), "AAPL", 0), "3 AAPL")

    def test_inferred_amount(self):
        ledger = load(str(EXAMPLES / "basic.journal"))
        posting = ledger.transactions[0].postings[1]
        self.assertEqual(posting.account, "Equity:Opening")
        self.assertEqual(posting.amount, Amount(Decimal("-1000.00"), "$"))
        self.assertTrue(posting.inferred)
        exchange = ledger.transactions[4].postings[1]
        self.assertEqual(exchange.amount, Amount(Decimal("-112.00"), "$"))

    def test_total_cost_weight(self):
        ledger = load(str(EXAMPLES / "invest.journal"))
        sell = ledger.transactions[2]
        self.assertEqual(sell.description, "Sell shares")
        self.assertEqual(len(sell.postings), 2)

    def test_unbalanced_transaction(self):
        with self.assertRaises(BalanceError) as cm:
            build_ledger(parse_string("2024-01-01 Off\n    A  $10.00\n    B  -$9.50\n", "u.journal"))
        self.assertEqual(str(cm.exception), "u.journal:1: transaction does not balance: off by $0.50")

    def test_precision_ignores_costs(self):
        journal = parse_string(
            "2024-01-01 Buy\n    Assets:Broker  10 XYZ @ $1.255\n    Assets:Cash  -$12.55\n"
        )
        self.assertEqual(commodity_precisions(journal)["$"], 2)

    def test_assertion_failure(self):
        ledger = build_ledger(parse_string(
            "2024-01-01 Open\n    Assets:Cash  $100.00\n    Equity\n\n"
            "2024-01-02 Spend\n    Assets:Cash  -$5.00 = $100.00\n    Expenses\n",
            "x.journal",
        ))
        failures = ledger.assertion_failures()
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], AssertionFailure)
        self.assertEqual(
            str(failures[0]),
            "x.journal:6: balance assertion failed for Assets:Cash: expected $100.00, got $95.00",
        )

    def test_price_lookup(self):
        ledger = load(str(EXAMPLES / "invest.journal"))
        self.assertEqual(ledger.price("AAPL", "$", datetime.date(2024, 3, 27)), Decimal("171.00"))
        self.assertEqual(ledger.price("AAPL", "$", datetime.date(2024, 3, 28)), Decimal("180.50"))
        self.assertIsNone(ledger.price("AAPL", "$", datetime.date(2024, 2, 1)))


if __name__ == "__main__":
    unittest.main()
