import os
import tempfile
import unittest

from ledgerlite import AssertionFailure, build_ledger, load, parse_string


def failures(text):
    return build_ledger(parse_string(text, "x.journal")).assertion_failures()


class AssertionTests(unittest.TestCase):
    def test_failure_message(self):
        found = failures(
            "2024-01-01 Open\n    Assets:Cash  $100.00\n    Equity\n\n"
            "2024-01-02 Spend\n    Assets:Cash  -$5.00 = $100.00\n    Expenses\n"
        )
        self.assertEqual(len(found), 1)
        self.assertIsInstance(found[0], AssertionFailure)
        self.assertEqual(
            str(found[0]),
            "x.journal:6: balance assertion failed for Assets:Cash: expected $100.00, got $95.00",
        )

    def test_subaccounts_are_not_included(self):
        found = failures(
            "2024-01-01 Open\n    Assets:Bank  $100\n    Assets:Bank:Savings  $50\n    Equity\n\n"
            "2024-01-02 Check\n    Assets:Bank  $0 = $100\n    Equity  $0\n"
        )
        self.assertEqual(found, [])

    def test_assertions_follow_date_order_not_file_order(self):
        found = failures(
            "2024-02-01 Check\n    Assets:A  $0 = $30\n    Equity  $0\n\n"
            "2024-01-15 Second\n    Assets:A  $10\n    Equity\n\n"
            "2024-01-01 First\n    Assets:A  $20\n    Equity\n"
        )
        self.assertEqual(found, [])

    def test_checked_right_after_its_posting(self):
        ok = failures("2024-01-01 X\n    A  $10 = $10\n    A  $5 = $15\n    B\n")
        self.assertEqual(ok, [])
        bad = failures("2024-01-01 X\n    A  $10 = $15\n    A  $5\n    B\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].message, "balance assertion failed for A: expected $15, got $10")

    def test_balance_is_rounded_before_comparing(self):
        text = (
            "2024-01-01 Buy\n    Assets:Broker  3 AAPL @ $150.255\n    Assets:Cash  $0.00\n    Assets:Cash\n\n"
            "2024-01-02 Check\n    Assets:Cash  $0.00 = {}\n    Equity  $0.00\n"
        )
        self.assertEqual(failures(text.format("-$450.77")), [])
        found = failures(text.format("-$450.76"))
        self.assertEqual(
            found[0].message,
            "balance assertion failed for Assets:Cash: expected -$450.76, got -$450.77",
        )

    def test_zero_actual_balance_is_formatted_with_commodity(self):
        found = failures("2024-01-01 X\n    Assets:New  $0.00 = $5.00\n    Equity  $0.00\n    Other  1 EUR = 0 EUR\n    Equity  -1 EUR\n")
        self.assertEqual([f.lineno for f in found], [2, 4])
        self.assertEqual(found[0].message, "balance assertion failed for Assets:New: expected $5.00, got $0.00")
        self.assertEqual(found[1].message, "balance assertion failed for Other: expected 0 EUR, got 1 EUR")

    def test_all_failures_in_processing_order(self):
        journal = parse_string(
            "2024-03-01 C\n    A  $1 = $9\n    B\n\n"
            "2024-01-01 A\n    A  $1 = $7\n    B\n\n"
            "2024-02-01 B\n    A  $1 = $2\n    B\n"
        )
        ledger = build_ledger(journal)
        self.assertEqual([f.lineno for f in ledger.assertion_failures()], [6, 2])

    def test_load_raises_first_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.journal")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "2024-01-02 Two\n    A  $1 = $5\n    B\n\n"
                    "2024-01-01 One\n    A  $1 = $3\n    B\n"
                )
            with self.assertRaises(AssertionFailure) as cm:
                load(path)
            self.assertEqual(
                str(cm.exception),
                path + ":6: balance assertion failed for A: expected $3, got $1",
            )


if __name__ == "__main__":
    unittest.main()
