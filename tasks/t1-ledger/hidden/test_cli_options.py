import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "data"
REPORT = str(DATA / "report.journal")

DEPTH_ONE = (
    "  $11,914.60\n"
    "     10 AAPL  Assets\n"
    " -$15,000.00  Equity\n"
    "   $1,285.40\n"
    "  150.00 EUR  Expenses\n"
    " -150.00 EUR  Liabilities\n"
    "------------\n"
    "  -$1,800.00\n"
    "     10 AAPL\n"
)


def run(*args):
    env = dict(os.environ)
    env.pop("LEDGERLITE_FILE", None)
    return subprocess.run(
        [sys.executable, "-m", "ledgerlite"] + list(args),
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def text(*lines):
    return "".join(line + "\n" for line in lines)


class OptionTests(unittest.TestCase):
    def assertOutput(self, result, stdout):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, stdout)

    def assertUsageError(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_depth_short_option(self):
        self.assertOutput(run("-f", REPORT, "balance", "-d", "1"), DEPTH_ONE)

    def test_depth_must_be_a_positive_integer(self):
        self.assertUsageError(run("-f", REPORT, "balance", "--depth", "0"))
        self.assertUsageError(run("-f", REPORT, "balance", "--depth", "two"))

    def test_month_date_forms(self):
        expected = text(
            "2024-02-10 Groceries              Liabilities:Card          -$85.40      -$85.40",
            "2024-02-20 Trip to Lisbon         Liabilities:Card      -150.00 EUR      -$85.40",
            "                                                                     -150.00 EUR",
        )
        self.assertOutput(
            run("-f", REPORT, "register", "-b", "2024-02", "-e", "2024-03", "card"), expected
        )

    def test_year_date_forms(self):
        self.assertOutput(
            run("-f", REPORT, "balance", "--begin", "2024", "--end", "2025", "-d", "1"), DEPTH_ONE
        )
        self.assertOutput(
            run("-f", REPORT, "balance", "--end", "2024"), "------------\n           0\n"
        )

    def test_slash_date_form(self):
        self.assertOutput(
            run("-f", REPORT, "register", "-b", "2024/03/01", "checking"),
            text(
                "2024-03-01 Card payment           Assets:Bank:Checking      -$85.40      -$85.40"
            ),
        )

    def test_invalid_date_values(self):
        self.assertUsageError(run("-f", REPORT, "balance", "-b", "2024-02-30"))
        self.assertUsageError(run("-f", REPORT, "register", "-e", "02/10/2024"))
        self.assertUsageError(run("-f", REPORT, "register", "--begin", "2024-2"))

    def test_exchange(self):
        expected = text(
            "  $13,914.60  Assets",
            " -$15,000.00  Equity",
            "   $1,450.40  Expenses",
            "    -$165.00  Liabilities",
            "------------",
            "     $200.00",
        )
        self.assertOutput(run("-f", REPORT, "balance", "-d", "1", "-X", "$"), expected)
        self.assertOutput(run("-f", REPORT, "balance", "--exchange", "$", "--depth", "1"), expected)

    def test_exchange_needs_a_commodity_name(self):
        self.assertUsageError(run("-f", REPORT, "balance", "-X", "usd"))
        self.assertUsageError(run("-f", REPORT, "register", "--exchange", "1EUR"))

    def test_register_exchange_with_two_patterns(self):
        expected = text(
            "2024-01-15 Buy shares             Assets:Broker             10 AAPL      10 AAPL",
            "2024-02-20 Trip to Lisbon         ..ses:Travel:Lodging      $165.00      $165.00",
            "                                                                         10 AAPL",
        )
        self.assertOutput(run("-f", REPORT, "reg", "-X", "$", "Broker", "LODGING"), expected)

    def test_no_total_and_cleared(self):
        expected = text(
            "  $13,114.60  Assets",
            "  $13,114.60    Bank",
            "   $3,114.60      Checking",
            "  $10,000.00      Savings",
        )
        self.assertOutput(
            run("-f", REPORT, "balance", "-C", "--no-total", "^assets:bank"), expected
        )

    def test_cleared_register(self):
        expected = text(
            "2024-01-01 Opening                Assets:Bank:Checking    $5,000.00    $5,000.00",
            "2024-01-15 Buy shares             Assets:Bank:Checking   -$1,800.00    $3,200.00",
            "2024-03-01 Card payment           Assets:Bank:Checking      -$85.40    $3,114.60",
        )
        self.assertOutput(run("-f", REPORT, "register", "--cleared", "checking"), expected)

    def test_empty_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "zeros.journal")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "2024-01-01 Move\n    Assets:A  $5.00\n    Assets:B  -$5.00\n\n"
                    "2024-01-02 Other\n    Expenses:X  $1.00\n    Equity:Y  -$1.00\n\n"
                    "2024-01-03 Back\n    Expenses:X  -$1.00\n    Equity:Y  $1.00\n"
                )
            self.assertOutput(
                run("-f", path, "balance", "-E", "-d", "1", "--no-total"),
                text("           0  Assets", "           0  Equity", "           0  Expenses"),
            )
            self.assertOutput(
                run("-f", path, "balance", "--depth", "1"), text("------------", "           0")
            )


if __name__ == "__main__":
    unittest.main()
