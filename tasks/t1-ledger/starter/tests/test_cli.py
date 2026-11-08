import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASIC = os.path.join("examples", "basic.journal")


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


class CliVisibleTests(unittest.TestCase):
    def test_balance_depth_exchange(self):
        result = run("-f", BASIC, "balance", "--depth", "1", "-X", "EUR")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            result.stdout,
            " 3,134.82 EUR  Assets\n"
            "  -909.09 EUR  Equity\n"
            "    45.18 EUR  Expenses\n"
            "-2,272.73 EUR  Income\n"
            "-------------\n"
            "    -1.82 EUR\n",
        )

    def test_reg_alias_with_pattern(self):
        result = run("-f", BASIC, "reg", "cash")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "2024-01-07 Coffee with a collea.. Assets:Cash                -$4.50       -$4.50\n",
        )

    def test_check(self):
        result = run("-f", BASIC, "check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "OK transactions=5 postings=10 assertions=1 prices=1\n")

    def test_accounts(self):
        result = run("-f", BASIC, "accounts", "^assets")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Assets:Bank:Checking\nAssets:Bank:Euro\nAssets:Cash\n")

    def test_parse_error_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.journal")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("2024-01-01 X\n    A  $1\n    B  5\n")
            result = run("-f", path, "balance")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: " + path + ":3: invalid amount '5'\n")

    def test_missing_file_exit_code(self):
        result = run("-f", "examples/missing.journal", "check")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: journal file not found: examples/missing.journal\n")

    def test_bad_depth_is_usage_error(self):
        result = run("-f", BASIC, "balance", "--depth", "0")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
