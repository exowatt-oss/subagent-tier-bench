import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "data"
REPORT = str(DATA / "report.journal")

TWO_FAILURES = (
    "2024-03-01 Late\n    A  $1 = $9\n    B\n\n"
    "2024-01-01 Early\n    A  $1 = $7\n    B\n\n"
    "2024-02-01 Middle\n    A  $1 = $2\n    B\n"
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


class ErrorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def assertUsageError(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr, "")

    def assertJournalError(self, result, stderr):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, stderr)

    def test_no_journal_given(self):
        self.assertUsageError(run("balance"))

    def test_missing_journal_file(self):
        missing = os.path.join(self.tmp, "nope.journal")
        result = run("-f", missing, "balance")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: journal file not found: " + missing + "\n")

    def test_unknown_or_missing_command(self):
        self.assertUsageError(run("-f", REPORT, "summary"))
        self.assertUsageError(run("-f", REPORT))

    def test_parse_error(self):
        path = self.write("bad.journal", "2024-01-01 X\n    A  $1\n    B  $1,0\n")
        self.assertJournalError(
            run("-f", path, "register"), "error: " + path + ":3: invalid amount '$1,0'\n"
        )

    def test_balance_error(self):
        path = self.write("off.journal", "\n2024-01-01 X\n    A  $1.00\n    B  -$1.25\n")
        self.assertJournalError(
            run("-f", path, "balance"),
            "error: " + path + ":2: transaction does not balance: off by -$0.25\n",
        )

    def test_reports_show_only_first_assertion_failure(self):
        path = self.write("assert.journal", TWO_FAILURES)
        self.assertJournalError(
            run("-f", path, "balance"),
            "error: " + path + ":6: balance assertion failed for A: expected $7, got $1\n",
        )

    def test_check_shows_every_assertion_failure(self):
        path = self.write("assert.journal", TWO_FAILURES)
        self.assertJournalError(
            run("-f", path, "check"),
            "error: " + path + ":6: balance assertion failed for A: expected $7, got $1\n"
            "error: " + path + ":2: balance assertion failed for A: expected $9, got $3\n",
        )

    def test_missing_include_is_a_journal_error(self):
        path = self.write("main.journal", "include nope.journal\n")
        self.assertJournalError(
            run("-f", path, "check"), "error: " + path + ":1: include file not found: nope.journal\n"
        )

    def test_check_takes_no_patterns(self):
        self.assertUsageError(run("-f", REPORT, "check", "Assets"))

    def test_invalid_regex_is_usage_error(self):
        self.assertUsageError(run("-f", REPORT, "balance", "Assets:("))

    def test_unknown_options(self):
        self.assertUsageError(run("-f", REPORT, "balance", "--bogus"))
        self.assertUsageError(run("-f", REPORT, "register", "--depth", "1"))
        self.assertUsageError(run("-f", REPORT, "accounts", "--empty"))

    def test_usage_errors_win_over_journal_errors(self):
        path = self.write("bad.journal", "garbage\n")
        self.assertUsageError(run("-f", path, "balance", "--depth", "0"))


if __name__ == "__main__":
    unittest.main()
