import datetime
import unittest
from pathlib import Path

from ledgerlite import build_ledger, load, parse_string, register_report

DATA = Path(__file__).resolve().parent / "data"


def text(*lines):
    return "".join(line + "\n" for line in lines)


def ledger_from(source):
    return build_ledger(parse_string(source, "reg.journal"))


class RegisterReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = load(str(DATA / "report.journal"))

    def test_full_register(self):
        expected = text(
            "2024-01-01 Opening                Assets:Bank:Checking    $5,000.00    $5,000.00",
            "                                  Assets:Bank:Savings    $10,000.00   $15,000.00",
            "                                  Equity:Opening        -$15,000.00            0",
            "2024-01-15 Buy shares             Assets:Broker             10 AAPL      10 AAPL",
            "                                  Assets:Bank:Checking   -$1,800.00   -$1,800.00",
            "                                                                         10 AAPL",
            "2024-02-01 Rent for February in.. ..enses:Housing:Rent    $1,200.00     -$600.00",
            "                                                                         10 AAPL",
            "                                  Assets:Bank:Checking   -$1,200.00   -$1,800.00",
            "                                                                         10 AAPL",
            "2024-02-10 Groceries              Expenses:Food              $85.40   -$1,714.60",
            "                                                                         10 AAPL",
            "                                  Liabilities:Card          -$85.40   -$1,800.00",
            "                                                                         10 AAPL",
            "2024-02-20 Trip to Lisbon         ..ses:Travel:Lodging   150.00 EUR   -$1,800.00",
            "                                                                         10 AAPL",
            "                                                                      150.00 EUR",
            "                                  Liabilities:Card      -150.00 EUR   -$1,800.00",
            "                                                                         10 AAPL",
            "2024-03-01 Card payment           Liabilities:Card           $85.40   -$1,714.60",
            "                                                                         10 AAPL",
            "                                  Assets:Bank:Checking      -$85.40   -$1,800.00",
            "                                                                         10 AAPL",
        )
        self.assertEqual(register_report(self.ledger), expected)

    def test_pattern_limits_rows_and_running_total(self):
        expected = text(
            "2024-01-01 Opening                Assets:Bank:Checking    $5,000.00    $5,000.00",
            "2024-01-15 Buy shares             Assets:Bank:Checking   -$1,800.00    $3,200.00",
            "2024-02-01 Rent for February in.. Assets:Bank:Checking   -$1,200.00    $2,000.00",
            "2024-03-01 Card payment           Assets:Bank:Checking      -$85.40    $1,914.60",
        )
        self.assertEqual(register_report(self.ledger, patterns=["checking"]), expected)

    def test_begin_inclusive_end_exclusive(self):
        expected = text(
            "2024-02-10 Groceries              Expenses:Food              $85.40       $85.40",
            "                                  Liabilities:Card          -$85.40            0",
            "2024-02-20 Trip to Lisbon         ..ses:Travel:Lodging   150.00 EUR   150.00 EUR",
            "                                  Liabilities:Card      -150.00 EUR            0",
        )
        report = register_report(
            self.ledger, begin=datetime.date(2024, 2, 10), end=datetime.date(2024, 3, 1)
        )
        self.assertEqual(report, expected)

    def test_cleared_with_continuation_lines(self):
        expected = text(
            "2024-02-10 Groceries              Liabilities:Card          -$85.40      -$85.40",
            "2024-02-20 Trip to Lisbon         Liabilities:Card      -150.00 EUR      -$85.40",
            "                                                                     -150.00 EUR",
            "2024-03-01 Card payment           Liabilities:Card           $85.40  -150.00 EUR",
        )
        self.assertEqual(register_report(self.ledger, patterns=["^liab"], cleared=True), expected)

    def test_running_total_components_sorted(self):
        expected = text(
            "2024-01-15 Buy shares             Assets:Broker             10 AAPL      10 AAPL",
            "2024-02-20 Trip to Lisbon         ..ses:Travel:Lodging   150.00 EUR      10 AAPL",
            "                                                                      150.00 EUR",
        )
        self.assertEqual(register_report(self.ledger, patterns=["Broker|Lodging"]), expected)

    def test_exchange_uses_each_transaction_date(self):
        expected = text(
            "2024-01-15 Buy shares             Assets:Broker             10 AAPL      10 AAPL",
            "2024-02-20 Trip to Lisbon         ..ses:Travel:Lodging      $165.00      $165.00",
            "                                                                         10 AAPL",
        )
        report = register_report(self.ledger, patterns=["Broker|Lodging"], exchange="$")
        self.assertEqual(report, expected)

    def test_description_truncation(self):
        ledger = ledger_from(
            "2024-01-01 " + "D" * 22 + "\n    A  $1\n    B\n\n"
            "2024-01-02 " + "E" * 23 + "\n    A  $1\n    B\n"
        )
        expected = text(
            "2024-01-01 DDDDDDDDDDDDDDDDDDDDDD A                              $1           $1",
            "                                  B                             -$1            0",
            "2024-01-02 EEEEEEEEEEEEEEEEEEEE.. A                              $1           $1",
            "                                  B                             -$1            0",
        )
        self.assertEqual(register_report(ledger), expected)

    def test_account_truncation_keeps_the_end(self):
        ledger = ledger_from(
            "2024-01-01 Accounts\n    Assets:Twenty:Chars1  $1\n    Assets:Twenty:Chars12\n"
        )
        expected = text(
            "2024-01-01 Accounts               Assets:Twenty:Chars1           $1           $1",
            "                                  ..ets:Twenty:Chars12          -$1            0",
        )
        self.assertEqual(register_report(ledger), expected)

    def test_zero_amount_keeps_commodity_but_zero_total_is_0(self):
        ledger = ledger_from("2024-05-06 Check\n    Assets:Cash  $0.00 = $0.00\n    Equity  $0.00\n")
        expected = text(
            "2024-05-06 Check                  Assets:Cash                 $0.00            0",
            "                                  Equity                      $0.00            0",
        )
        self.assertEqual(register_report(ledger), expected)

    def test_dates_printed_in_iso_form(self):
        ledger = ledger_from("2024/05/06 Slash date\n    A  $1\n    B\n")
        self.assertEqual(
            register_report(ledger).splitlines()[0],
            "2024-05-06 Slash date             A                              $1           $1",
        )

    def test_long_amounts_are_not_truncated(self):
        ledger = ledger_from("2024-01-01 Lottery\n    Assets:Cash  $1,234,567,890.00\n    Income:Luck\n")
        expected = text(
            "2024-01-01 Lottery                Assets:Cash          $1,234,567,890.00 $1,234,567,890.00",
            "                                  Income:Luck          -$1,234,567,890.00            0",
        )
        self.assertEqual(register_report(ledger), expected)

    def test_inferred_postings_get_their_own_rows(self):
        ledger = ledger_from("2024-01-01 Open\n    Assets:Euro  5.00 EUR\n    Assets:Cash  $10\n    Equity:Opening\n")
        expected = text(
            "2024-01-01 Open                   Assets:Euro              5.00 EUR     5.00 EUR",
            "                                  Assets:Cash                   $10          $10",
            "                                                                        5.00 EUR",
            "                                  Equity:Opening               -$10     5.00 EUR",
            "                                  Equity:Opening          -5.00 EUR            0",
        )
        self.assertEqual(register_report(ledger), expected)

    def test_header_on_first_selected_posting(self):
        ledger = ledger_from(
            "2024-01-01 Split bill\n    Assets:Cash  -$30\n    Expenses:Food  $20\n    Expenses:Drinks  $10\n"
        )
        expected = text(
            "2024-01-01 Split bill             Expenses:Food                 $20          $20",
            "                                  Expenses:Drinks               $10          $30",
        )
        self.assertEqual(register_report(ledger, patterns=["^Exp"]), expected)

    def test_no_selected_postings(self):
        self.assertEqual(register_report(self.ledger, patterns=["nomatch"]), "")
        self.assertEqual(register_report(self.ledger, begin=datetime.date(2025, 1, 1)), "")


if __name__ == "__main__":
    unittest.main()
