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


class CliCase(unittest.TestCase):
    fixture_name = "plant_v1.json"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "data.json"
        shutil.copyfile(DATA / self.fixture_name, self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def wo(self, *args, env=None):
        return run_cli("--file", str(self.path), *args, env=env)


class IdReferenceTest(CliCase):
    def test_show_heading_uses_canonical_id(self):
        result = self.wo("show", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "Work order WO-00001")
        self.assertEqual(lines[1], "Project:   GEN (General)")

    def test_all_reference_spellings_resolve_to_same_order(self):
        canonical = self.wo("show", "WO-00003").stdout
        self.assertIn("Fix conveyor drive", canonical)
        self.assertEqual(self.wo("show", "wo-3").stdout, canonical)
        self.assertEqual(self.wo("show", "003").stdout, canonical)

    def test_malformed_reference_is_usage_error(self):
        result = self.wo("show", "X-7")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error: invalid work order id: X-7", result.stderr)

    def test_unknown_order_message_uses_canonical_id(self):
        result = self.wo("note", "99", "anything")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error: no such work order: WO-00099", result.stderr)


class MessageTest(CliCase):
    def test_add_message(self):
        result = self.wo("add", "Grease gearbox")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "created WO-00007 in GEN: Grease gearbox\n")

    def test_assign_and_unassign_messages(self):
        self.assertEqual(self.wo("assign", "2", "kim").stdout, "WO-00002 assigned to kim\n")
        self.assertEqual(self.wo("assign", "2", "-").stdout, "WO-00002 unassigned\n")

    def test_note_and_delete_messages(self):
        self.assertEqual(self.wo("note", "5", "flange gasket ok").stdout, "note added to WO-00005\n")
        self.assertEqual(self.wo("delete", "5").stdout, "deleted WO-00005: Calibrate flow meter\n")

    def test_same_status_error_names_canonical_id(self):
        result = self.wo("status", "2", "open")
        self.assertEqual(result.returncode, 3)
        self.assertIn("error: work order WO-00002 is already open", result.stderr)


class CliRegressionTest(CliCase):
    def test_unknown_order_is_exit_1(self):
        result = self.wo("show", "99")
        self.assertEqual(result.returncode, 1)
        errors = [line for line in result.stderr.splitlines() if line.startswith("error: ")]
        self.assertEqual(len(errors), 1, result.stderr)
        self.assertTrue(errors[0].startswith("error: no such work order: "), result.stderr)

    def test_non_numeric_reference_is_exit_2(self):
        result = self.wo("show", "abc")
        self.assertEqual(result.returncode, 2)

    def test_assign_dash_unassigns(self):
        self.wo("assign", "1", "-")
        self.assertIn("Assignee:  -\n", self.wo("show", "1").stdout)

if __name__ == "__main__":
    unittest.main()
