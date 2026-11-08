import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "data"
REPORT = str(DATA / "report.journal")


def run(*args, env_file=None):
    env = dict(os.environ)
    env.pop("LEDGERLITE_FILE", None)
    if env_file is not None:
        env["LEDGERLITE_FILE"] = env_file
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


class CommandTests(unittest.TestCase):
    def assertSuccess(self, result, stdout):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, stdout)

    def test_balance(self):
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
        self.assertSuccess(run("-f", REPORT, "balance"), expected)

    def test_bal_alias(self):
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
        self.assertSuccess(run("-f", REPORT, "bal", "--depth", "1"), expected)

    def test_register_with_pattern(self):
        expected = text(
            "2024-01-01 Opening                Assets:Bank:Checking    $5,000.00    $5,000.00",
            "2024-01-15 Buy shares             Assets:Bank:Checking   -$1,800.00    $3,200.00",
            "2024-02-01 Rent for February in.. Assets:Bank:Checking   -$1,200.00    $2,000.00",
            "2024-03-01 Card payment           Assets:Bank:Checking      -$85.40    $1,914.60",
        )
        self.assertSuccess(run("-f", REPORT, "register", "checking"), expected)

    def test_reg_alias(self):
        expected = text(
            "2024-02-10 Groceries              Expenses:Food              $85.40       $85.40",
            "                                  Liabilities:Card          -$85.40            0",
            "2024-02-20 Trip to Lisbon         ..ses:Travel:Lodging   150.00 EUR   150.00 EUR",
            "                                  Liabilities:Card      -150.00 EUR            0",
        )
        self.assertSuccess(
            run("-f", REPORT, "reg", "-b", "2024-02-10", "-e", "2024-03-01"), expected
        )

    def test_accounts(self):
        expected = text(
            "Assets:Bank:Checking",
            "Assets:Bank:Savings",
            "Assets:Broker",
            "Equity:Opening",
            "Expenses:Food",
            "Expenses:Housing:Rent",
            "Expenses:Travel:Lodging",
            "Liabilities:Card",
        )
        self.assertSuccess(run("-f", REPORT, "accounts"), expected)

    def test_accounts_with_patterns(self):
        expected = text(
            "Expenses:Food",
            "Expenses:Housing:Rent",
            "Expenses:Travel:Lodging",
            "Liabilities:Card",
        )
        self.assertSuccess(run("-f", REPORT, "accounts", "CARD", "^exp"), expected)

    def test_check(self):
        self.assertSuccess(
            run("-f", REPORT, "check"), "OK transactions=6 postings=13 assertions=1 prices=3\n"
        )

    def test_check_counts_postings_after_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "multi.journal")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "P 2024-01-01 EUR $1.10\n\n"
                    "2024-01-01 Open\n    Assets:Euro  5.00 EUR = 5.00 EUR\n"
                    "    Assets:Cash  $10\n    Equity:Opening\n\n"
                    "2024-01-02 Two\n    A  $1 = $1\n    B\n"
                )
            self.assertSuccess(
                run("-f", path, "check"), "OK transactions=2 postings=6 assertions=2 prices=1\n"
            )

    def test_environment_variable_names_the_journal(self):
        self.assertSuccess(
            run("check", env_file=REPORT), "OK transactions=6 postings=13 assertions=1 prices=3\n"
        )

    def test_file_option_wins_over_environment(self):
        missing = str(DATA / "does-not-exist.journal")
        self.assertSuccess(
            run("--file", REPORT, "check", env_file=missing),
            "OK transactions=6 postings=13 assertions=1 prices=3\n",
        )

    def test_empty_environment_variable_is_ignored(self):
        result = run("check", env_file="")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
