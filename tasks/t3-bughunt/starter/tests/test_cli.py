import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "meterbill", *args], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=30)


class CliTests(unittest.TestCase):
    def test_invoice_for_one_account(self):
        proc = run_cli("--data", str(EXAMPLES / "data"), "invoice", "--period", "2026-03",
                       "--account", "umbrella", str(EXAMPLES / "usage-2026-03.csv"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Invoice umbrella: Umbrella Health", proc.stdout)
        self.assertIn("Total".ljust(48) + "561.00".rjust(12), proc.stdout)

    def test_missing_data_directory_exits_2(self):
        proc = run_cli("--data", str(ROOT / "no-such-dir"), "plans")
        self.assertEqual(proc.returncode, 2)
        self.assertTrue(proc.stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
