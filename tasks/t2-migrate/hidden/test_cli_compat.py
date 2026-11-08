import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "data"
NOW = "2026-03-10T12:00:00Z"

HOURS_WARNING = "warning: --hours is deprecated; use --estimate"
CLOSE_WARNING = "warning: 'close' is deprecated; use 'status ID done'"


def run_cli(*args, env=None):
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("WOTRACK_")}
    full_env["WOTRACK_NOW"] = NOW
    full_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "wotrack", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env=full_env,
    )


class CompatCase(unittest.TestCase):
    fixture_name = "multi_v2.json"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "data.json"
        shutil.copyfile(DATA / self.fixture_name, self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def wo(self, *args, env=None):
        return run_cli("--file", str(self.path), *args, env=env)

    def order(self, order_id):
        with open(self.path, encoding="utf-8") as handle:
            doc = json.load(handle)
        for record in doc["orders"]:
            if record["id"] == order_id:
                return record
        return None


class DeprecationTest(CompatCase):
    def test_hours_still_works_and_warns(self):
        result = self.wo("add", "Rewire panel lights", "--hours", "2.5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HOURS_WARNING, result.stderr.splitlines())
        self.assertEqual(self.order("WO-00012")["estimate_minutes"], 150)

    def test_hours_on_edit_rounds_half_up(self):
        result = self.wo("edit", "8", "--hours", "0.875")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(HOURS_WARNING, result.stderr)
        self.assertEqual(self.order("WO-00008")["estimate_minutes"], 53)

    def test_hours_and_estimate_together_is_usage_error(self):
        result = self.wo("edit", "8", "--hours", "1", "--estimate", "1h")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error: --hours and --estimate cannot be used together", result.stderr)
        self.assertIsNone(self.order("WO-00008")["estimate_minutes"])

    def test_close_still_works_and_warns(self):
        result = self.wo("close", "wo-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "WO-00008: open -> done\n")
        self.assertIn(CLOSE_WARNING, result.stderr.splitlines())
        self.assertEqual(self.order("WO-00008")["status"], "done")

    def test_close_warning_printed_even_when_command_fails(self):
        result = self.wo("close", "3")
        self.assertEqual(result.returncode, 3)
        self.assertIn(CLOSE_WARNING, result.stderr)
        self.assertIn("cannot change status from blocked to done", result.stderr)

class ExitStatusTest(CompatCase):
    def test_invalid_priority_is_exit_3(self):
        result = self.wo("add", "Check belts", "--priority", "critical")
        self.assertEqual(result.returncode, 3)
        self.assertTrue(result.stderr.startswith("error: "))

    def test_invalid_due_date_is_exit_3(self):
        self.assertEqual(self.wo("edit", "8", "--due", "2026-02-30").returncode, 3)

    def test_nothing_to_change_is_exit_3(self):
        self.assertEqual(self.wo("edit", "8").returncode, 3)

class EstimateOptionTest(CompatCase):
    def test_bare_number_estimate_is_validation_error(self):
        result = self.wo("edit", "8", "--estimate", "90")
        self.assertEqual(result.returncode, 3)
        self.assertIsNone(self.order("WO-00008")["estimate_minutes"])

    def test_zero_and_over_1000_hours_rejected(self):
        self.assertEqual(self.wo("edit", "8", "--estimate", "0m").returncode, 3)
        self.assertEqual(self.wo("edit", "8", "--estimate", "1000h1m").returncode, 3)
        self.assertEqual(self.wo("edit", "8", "--estimate", "1000h").returncode, 0)

    def test_estimate_none_clears(self):
        result = self.wo("edit", "WO-00001", "--estimate", "none")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(self.order("WO-00001")["estimate_minutes"])


if __name__ == "__main__":
    unittest.main()
