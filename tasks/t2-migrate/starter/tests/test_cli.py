import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
NOW = "2026-03-10T12:00:00Z"


def run_cli(*args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("WOTRACK_")}
    env["WOTRACK_NOW"] = NOW
    return subprocess.run(
        [sys.executable, "-m", "wotrack", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "plant.json"
        shutil.copyfile(SAMPLES / "plant.json", self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def wo(self, *args):
        return run_cli("--file", str(self.path), *args)

    def test_report(self):
        result = self.wo("report")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "Work orders: 6\n"
            "By status:\n"
            "  open         2\n"
            "  in_progress  1\n"
            "  blocked      1\n"
            "  done         1\n"
            "  cancelled    1\n"
            "By priority:\n"
            "  urgent  1\n"
            "  high    2\n"
            "  normal  2\n"
            "  low     1\n"
            "Overdue: 2\n",
        )

    def test_list_hides_closed_orders_by_default(self):
        rows = self.wo("list").stdout.splitlines()[1:]
        self.assertEqual(len(rows), 4)
        self.assertFalse(any("Repaint safety lines" in row for row in rows))

    def test_overdue_filter(self):
        rows = self.wo("list", "--overdue").stdout.splitlines()[1:]
        self.assertEqual(len(rows), 2)
        self.assertIn("Replace pump seal", rows[0])
        self.assertIn("Fix conveyor drive", rows[1])

    def test_forbidden_status_change(self):
        result = self.wo("status", "4", "in_progress")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error: cannot change status from done to in_progress", result.stderr)

    def test_unknown_work_order(self):
        result = self.wo("show", "42")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error: no such work order", result.stderr)

    def test_first_write_creates_the_file(self):
        path = Path(self._tmp.name) / "new.json"
        result = run_cli("--file", str(path), "add", "Check fire doors", "--priority", "HIGH")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(path.exists())
        shown = run_cli("--file", str(path), "show", "1")
        self.assertIn("Title:     Check fire doors\n", shown.stdout)
        self.assertIn("Priority:  high\n", shown.stdout)


if __name__ == "__main__":
    unittest.main()
