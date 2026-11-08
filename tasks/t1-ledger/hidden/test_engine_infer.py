import datetime
import unittest
from decimal import Decimal

from ledgerlite import Amount, Posting, build_ledger, parse_string, posting_weight


def built(text):
    return build_ledger(parse_string(text, "i.journal"))


class InferenceTests(unittest.TestCase):
    def test_inferred_from_total_cost_with_negative_quantity(self):
        ledger = built("2024-01-01 Sell\n    Assets:Broker  -10 AAPL @@ $1,600\n    Assets:Cash\n")
        cash = ledger.transactions[0].postings[1]
        self.assertEqual(cash.amount, Amount(Decimal("1600"), "$"))
        self.assertTrue(cash.inferred)
        self.assertFalse(ledger.transactions[0].postings[0].inferred)

    def test_posting_weight(self):
        unit = Posting("A", Amount(Decimal("-4"), "AAPL"), Amount(Decimal("2.5"), "$"), "@")
        total = Posting("A", Amount(Decimal("-4"), "AAPL"), Amount(Decimal("10"), "$"), "@@")
        plain = Posting("A", Amount(Decimal("3"), "EUR"))
        self.assertEqual(posting_weight(unit), Amount(Decimal("-10"), "$"))
        self.assertEqual(posting_weight(total), Amount(Decimal("-10"), "$"))
        self.assertEqual(posting_weight(plain), Amount(Decimal("3"), "EUR"))

    def test_multi_commodity_inference_expands(self):
        ledger = built(
            "2024-01-01 Open\n"
            "    Assets:Euro  5.00 EUR\n"
            "    Assets:Cash  $10\n"
            "    Equity:Opening   ; balancing\n"
        )
        postings = ledger.transactions[0].postings
        self.assertEqual(len(postings), 4)
        generated = postings[2:]
        self.assertEqual(
            [p.amount for p in generated],
            [Amount(Decimal("-10"), "$"), Amount(Decimal("-5.00"), "EUR")],
        )
        for p in generated:
            self.assertEqual(p.account, "Equity:Opening")
            self.assertEqual(p.lineno, 4)
            self.assertEqual(p.filename, "i.journal")
            self.assertEqual(p.comment, "balancing")
            self.assertTrue(p.inferred)
            self.assertIsNone(p.cost)
            self.assertIsNone(p.assertion)

    def test_generated_postings_take_the_omitted_position(self):
        ledger = built(
            "2024-01-01 Mix\n    A  2 GBP\n    Middle\n    Z  $3\n    Y  -1 AAPL\n"
        )
        postings = ledger.transactions[0].postings
        self.assertEqual(
            [(p.account, p.amount.commodity) for p in postings],
            [("A", "GBP"), ("Middle", "$"), ("Middle", "AAPL"), ("Middle", "GBP"), ("Z", "$"), ("Y", "AAPL")],
        )

    def test_inferred_amount_is_exact(self):
        ledger = built("2024-01-01 Buy\n    Assets:Broker  3 AAPL @ $150.255\n    Assets:Cash  $0.00\n    Assets:Other\n")
        amount = ledger.transactions[0].postings[2].amount
        self.assertEqual(amount.quantity, Decimal("-450.765"))

    def test_build_does_not_modify_the_journal(self):
        journal = parse_string("2024-01-01 Open\n    A  5 EUR\n    B  $10\n    C\n")
        ledger = build_ledger(journal)
        self.assertEqual(len(ledger.transactions[0].postings), 4)
        original = journal.transactions[0].postings
        self.assertEqual(len(original), 3)
        self.assertIsNone(original[2].amount)
        self.assertFalse(original[2].inferred)

    def test_transactions_sorted_by_date_stably(self):
        ledger = built(
            "2024-01-05 b\n    A  $1\n    B\n"
            "2024-01-01 a\n    A  $1\n    B\n"
            "2024-01-05 c\n    A  $1\n    B\n"
            "2023-12-31 z\n    A  $1\n    B\n"
        )
        self.assertEqual([t.description for t in ledger.transactions], ["z", "a", "b", "c"])
        self.assertEqual(ledger.transactions[0].date, datetime.date(2023, 12, 31))

    def test_accounts_sorted_in_plain_string_order(self):
        ledger = built(
            "2024-01-01 X\n    Assets:Bank:Checking  $1\n    Assets:Bank Fees  $1\n"
            "    Assets:Bank  $1\n    expenses:misc  $1\n    Equity\n"
        )
        self.assertEqual(
            ledger.accounts(),
            ["Assets:Bank", "Assets:Bank Fees", "Assets:Bank:Checking", "Equity", "expenses:misc"],
        )


if __name__ == "__main__":
    unittest.main()
