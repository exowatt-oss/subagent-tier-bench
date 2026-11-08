import datetime
import unittest
from pathlib import Path

from ledgerlite import balance_report, build_ledger, load, parse_string

DATA = Path(__file__).resolve().parent / "data"


def text(*lines):
    return "".join(line + "\n" for line in lines)


def ledger_from(source):
    return build_ledger(parse_string(source, "bal.journal"))


ZEROS = (
    "2024-01-01 Move\n    Assets:A  $5.00\n    Assets:B  -$5.00\n\n"
    "2024-01-02 Other\n    Expenses:X  $1.00\n    Equity:Y  -$1.00\n\n"
    "2024-01-03 Back\n    Expenses:X  -$1.00\n    Equity:Y  $1.00\n"
)


class BalanceReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = load(str(DATA / "report.journal"))

    def test_full_report(self):
        expected = text(
            "  $11,914.60",
            "     10 AAPL  Assets",
            "  $11,914.60    Bank",
            "   $1,914.60      Checking",
            "  $10,000.00      Savings",
            "     10 AAPL    Broker",
            " -$15,000.00  Equity",
            " -$15,000.00    Opening",
            "   $1,285.40",
            "  150.00 EUR  Expenses",
            "      $85.40    Food",
            "   $1,200.00    Housing",
            "   $1,200.00      Rent",
            "  150.00 EUR    Travel",
            "  150.00 EUR      Lodging",
            " -150.00 EUR  Liabilities",
            " -150.00 EUR    Card",
            "------------",
            "  -$1,800.00",
            "     10 AAPL",
        )
        self.assertEqual(balance_report(self.ledger), expected)

    def test_depth_limit_keeps_rolled_up_values(self):
        expected = text(
            "  $11,914.60",
            "     10 AAPL  Assets",
            " -$15,000.00  Equity",
            "   $1,285.40",
            "  150.00 EUR  Expenses",
            " -150.00 EUR  Liabilities",
            "------------",
            "  -$1,800.00",
            "     10 AAPL",
        )
        self.assertEqual(balance_report(self.ledger, depth=1), expected)

    def test_zero_components_are_not_printed(self):
        expected = text(
            " -150.00 EUR  Liabilities",
            " -150.00 EUR    Card",
            "------------",
            " -150.00 EUR",
        )
        self.assertEqual(balance_report(self.ledger, patterns=["card"]), expected)

    def test_patterns_are_case_insensitive_and_any_match(self):
        expected = text(
            "      $85.40  Expenses",
            "      $85.40    Food",
            " -150.00 EUR  Liabilities",
            " -150.00 EUR    Card",
            "------------",
            "      $85.40",
            " -150.00 EUR",
        )
        self.assertEqual(balance_report(self.ledger, patterns=["card", "FOOD"]), expected)

    def test_begin_inclusive_end_exclusive(self):
        expected = text(
            "  -$1,200.00  Assets",
            "  -$1,200.00    Bank",
            "  -$1,200.00      Checking",
            "   $1,285.40",
            "  150.00 EUR  Expenses",
            "      $85.40    Food",
            "   $1,200.00    Housing",
            "   $1,200.00      Rent",
            "  150.00 EUR    Travel",
            "  150.00 EUR      Lodging",
            "     -$85.40",
            " -150.00 EUR  Liabilities",
            "     -$85.40",
            " -150.00 EUR    Card",
            "------------",
            "           0",
        )
        report = balance_report(
            self.ledger, begin=datetime.date(2024, 2, 1), end=datetime.date(2024, 3, 1)
        )
        self.assertEqual(report, expected)

    def test_cleared_only(self):
        expected = text(
            "  $13,114.60  Assets",
            "  $13,114.60    Bank",
            "   $3,114.60      Checking",
            "  $10,000.00      Savings",
            "------------",
            "  $13,114.60",
        )
        self.assertEqual(
            balance_report(self.ledger, patterns=["^assets:bank"], cleared=True), expected
        )

    def test_exchange_values_at_latest_transaction_date(self):
        expected = text(
            "  $13,914.60  Assets",
            " -$15,000.00  Equity",
            "   $1,450.40  Expenses",
            "    -$165.00  Liabilities",
            "------------",
            "     $200.00",
        )
        self.assertEqual(balance_report(self.ledger, depth=1, exchange="$"), expected)

    def test_exchange_with_end_values_on_the_day_before(self):
        expected = text(
            "  $13,900.00  Assets",
            " -$15,000.00  Equity",
            "   $1,450.40  Expenses",
            "    -$250.40  Liabilities",
            "------------",
            "     $100.00",
        )
        report = balance_report(
            self.ledger, depth=1, exchange="$", end=datetime.date(2024, 2, 29)
        )
        self.assertEqual(report, expected)

    def test_exchange_leaves_unconvertible_commodities(self):
        expected = text(
            "      10 AAPL",
            "10,831.45 EUR  Assets",
            "10,831.45 EUR    Bank",
            "      10 AAPL    Broker",
            "-------------",
            "      10 AAPL",
            "10,831.45 EUR",
        )
        report = balance_report(self.ledger, patterns=["^Assets"], depth=2, exchange="EUR")
        self.assertEqual(report, expected)

    def test_no_matching_postings(self):
        self.assertEqual(
            balance_report(self.ledger, patterns=["nomatch"]), text("------------", "           0")
        )
        self.assertEqual(balance_report(self.ledger, patterns=["nomatch"], total=False), "")

    def test_zero_parent_with_nonzero_children_prints_0(self):
        expected = text(
            "           0  Assets",
            "       $5.00    A",
            "      -$5.00    B",
            "------------",
            "           0",
        )
        self.assertEqual(balance_report(ledger_from(ZEROS)), expected)

    def test_zero_parent_hidden_when_children_beyond_depth(self):
        self.assertEqual(
            balance_report(ledger_from(ZEROS), depth=1), text("------------", "           0")
        )

    def test_empty_shows_zero_accounts(self):
        expected = text(
            "           0  Assets",
            "       $5.00    A",
            "      -$5.00    B",
            "           0  Equity",
            "           0    Y",
            "           0  Expenses",
            "           0    X",
            "------------",
            "           0",
        )
        self.assertEqual(balance_report(ledger_from(ZEROS), empty=True), expected)

    def test_empty_with_depth_and_no_total(self):
        expected = text(
            "           0  Assets",
            "           0  Equity",
            "           0  Expenses",
        )
        report = balance_report(ledger_from(ZEROS), empty=True, depth=1, total=False)
        self.assertEqual(report, expected)

    def test_width_follows_longest_printed_amount(self):
        ledger = ledger_from("2024-01-01 Big\n    A  $9,000,000.00\n    B  $9,000,000.00\n    C\n")
        with_total = text(
            " $9,000,000.00  A",
            " $9,000,000.00  B",
            "--------------",
            "$18,000,000.00",
        )
        self.assertEqual(balance_report(ledger, patterns=["^A", "^B"]), with_total)
        without_total = text("$9,000,000.00  A", "$9,000,000.00  B")
        self.assertEqual(balance_report(ledger, patterns=["^A", "^B"], total=False), without_total)

    def test_hiding_uses_converted_value(self):
        ledger = ledger_from(
            "P 2024-01-01 AAPL $150.00\n\n"
            "2024-01-02 Buy\n    Assets:Broker  10 AAPL @ $150.00\n    Assets:Broker\n\n"
            "2024-01-03 Fee\n    Expenses:Fees  $5.00\n    Assets:Cash\n"
        )
        expected = text(
            "      -$5.00  Assets",
            "      -$5.00    Cash",
            "       $5.00  Expenses",
            "       $5.00    Fees",
            "------------",
            "           0",
        )
        self.assertEqual(balance_report(ledger, exchange="$"), expected)

    def test_siblings_sorted_by_last_segment(self):
        ledger = ledger_from(
            "2024-01-01 X\n    Assets:Bank:Checking  $1.00\n    Assets:Bank Fees  $2.00\n"
            "    Assets:Zeta  $3.00\n    Assets:bank  $4.00\n    Equity\n"
        )
        expected = text(
            "      $10.00  Assets",
            "       $1.00    Bank",
            "       $1.00      Checking",
            "       $2.00    Bank Fees",
            "       $3.00    Zeta",
            "       $4.00    bank",
            "     -$10.00  Equity",
            "------------",
            "           0",
        )
        self.assertEqual(balance_report(ledger), expected)


if __name__ == "__main__":
    unittest.main()
