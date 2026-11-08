import unittest
from pathlib import Path

from ledgerlite import balance_report, build_ledger, load, parse_string, register_report

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def text(*lines):
    return "".join(line + "\n" for line in lines)


class ReportVisibleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.basic = load(str(EXAMPLES / "basic.journal"))
        cls.invest = load(str(EXAMPLES / "invest.journal"))

    def test_spec_balance_example(self):
        expected = text(
            "   $3,338.30",
            "  100.00 EUR  Assets",
            "   $3,342.80",
            "  100.00 EUR    Bank",
            "   $3,342.80      Checking",
            "  100.00 EUR      Euro",
            "      -$4.50    Cash",
            "  -$1,000.00  Equity",
            "  -$1,000.00    Opening",
            "      $49.70  Expenses",
            "      $49.70    Food",
            "       $4.50      Dining Out",
            "      $45.20      Groceries",
            "  -$2,500.00  Income",
            "  -$2,500.00    Salary",
            "------------",
            "    -$112.00",
            "  100.00 EUR",
        )
        self.assertEqual(balance_report(self.basic), expected)

    def test_spec_balance_depth_and_exchange(self):
        expected = text(
            " 3,134.82 EUR  Assets",
            "  -909.09 EUR  Equity",
            "    45.18 EUR  Expenses",
            "-2,272.73 EUR  Income",
            "-------------",
            "    -1.82 EUR",
        )
        self.assertEqual(balance_report(self.basic, depth=1, exchange="EUR"), expected)

    def test_balance_exchange_with_shares(self):
        expected = text(
            "     $202.50  Assets",
            "  -$5,000.00    Bank",
            "  -$5,000.00      Checking",
            "   $5,202.50    Broker",
            "   $2,495.00      Cash",
            "   $2,707.50      Shares",
            "------------",
            "     $202.50",
        )
        self.assertEqual(balance_report(self.invest, exchange="$"), expected)

    def test_spec_register_example(self):
        expected = text(
            "2024-01-01 Opening balance        Assets:Bank:Checking    $1,000.00    $1,000.00",
            "                                  Equity:Opening         -$1,000.00            0",
            "2024-01-05 Grocery store          ..ses:Food:Groceries       $45.20       $45.20",
            "                                  Assets:Bank:Checking      -$45.20            0",
            "2024-01-07 Coffee with a collea.. ..es:Food:Dining Out        $4.50        $4.50",
            "                                  Assets:Cash                -$4.50            0",
            "2024-01-10 Salary                 Assets:Bank:Checking    $2,500.00    $2,500.00",
            "                                  Income:Salary          -$2,500.00            0",
            "2024-01-12 Currency exchange      Assets:Bank:Euro       100.00 EUR   100.00 EUR",
            "                                  Assets:Bank:Checking     -$112.00     -$112.00",
            "                                                                      100.00 EUR",
        )
        self.assertEqual(register_report(self.basic), expected)

    def test_register_pattern(self):
        expected = text(
            "2024-03-01 Fund the broker acco.. Assets:Broker:Cash      $5,000.00    $5,000.00",
            "2024-03-04 Buy shares             Assets:Broker:Cash     -$3,405.00    $1,595.00",
            "2024-03-20 Sell shares            Assets:Broker:Cash        $900.00    $2,495.00",
            "2024-03-31 Statement              Assets:Broker:Cash          $0.00    $2,495.00",
        )
        self.assertEqual(register_report(self.invest, patterns=["cash"]), expected)

    def test_hidden_zero_accounts_and_empty_register(self):
        ledger = build_ledger(parse_string(
            "2024-01-01 In\n    Assets:Cash  $5\n    Income:Gift\n\n"
            "2024-01-02 Out\n    Income:Gift  $5\n    Assets:Cash\n"
        ))
        self.assertEqual(balance_report(ledger), text("------------", "           0"))
        self.assertEqual(register_report(ledger, patterns=["nothing"]), "")


if __name__ == "__main__":
    unittest.main()
