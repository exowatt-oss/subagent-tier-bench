import unittest

from ledgerlite import BalanceError, build_ledger, parse_string


def balance_error(text):
    try:
        build_ledger(parse_string(text, "b.journal"))
    except BalanceError as exc:
        return exc
    raise AssertionError("no BalanceError raised")


class BalanceTests(unittest.TestCase):
    def test_unbalanced_transaction_message(self):
        exc = balance_error("2024-01-01 Off\n    Expenses:A  $10.00\n    Assets:B  -$9.50\n")
        self.assertEqual(str(exc), "b.journal:1: transaction does not balance: off by $0.50")

    def test_unbalanced_commodities_sorted(self):
        exc = balance_error(
            "\n2024-01-01 Off\n    A  $5.00\n    B  -$4.00\n    C  -2 EUR\n    D  5 AAPL\n"
        )
        self.assertEqual(exc.lineno, 2)
        self.assertEqual(exc.message, "transaction does not balance: off by $1.00, 5 AAPL, -2 EUR")

    def test_residual_rounding_to_zero_balances(self):
        ledger = build_ledger(
            parse_string("2024-01-01 Buy\n    Assets:Broker  7 XYZ @ $1.333\n    Assets:Cash  -$9.33\n")
        )
        self.assertEqual(len(ledger.transactions), 1)

    def test_exact_half_cent_rounds_away_from_zero(self):
        exc = balance_error(
            "2024-01-01 Buy\n    Assets:Broker  2 XYZ @ $1.2525\n    Assets:Cash  -$2.50\n"
        )
        self.assertEqual(exc.message, "transaction does not balance: off by $0.01")

    def test_more_than_one_omitted_amount(self):
        exc = balance_error("2024-01-01 Two\n    A  $5\n    B\n    C\n")
        self.assertEqual(str(exc), "b.journal:1: more than one posting without an amount")

    def test_omitted_amount_but_already_balanced(self):
        exc = balance_error("2024-01-01 Done\n    A  $5\n    B  -$5\n    C\n")
        self.assertEqual(exc.message, "cannot infer amount: transaction already balances")

    def test_first_error_in_processing_order(self):
        exc = balance_error(
            "2024-03-01 Later\n    A  $1\n    B  $1\n\n"
            "2024-02-01 Earlier\n    A  $2\n    B  $2\n"
        )
        self.assertEqual((exc.lineno, exc.message), (5, "transaction does not balance: off by $4"))


if __name__ == "__main__":
    unittest.main()
