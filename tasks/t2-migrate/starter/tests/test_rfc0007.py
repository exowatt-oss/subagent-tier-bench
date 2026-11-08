"""Acceptance tests for RFC 0007 (projects, string ids, data format 2).

These fail until the RFC is implemented.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
NOW = "2026-03-10T12:00:00Z"


def run_cli(*args, env=None):
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("WOTRACK_")}
    full_env["WOTRACK_NOW"] = NOW
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "wotrack", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        env=full_env,
    )


class LibraryTest(unittest.TestCase):
    def test_format_and_parse_ids(self):
        from wotrack.ids import format_id, parse_id

        self.assertEqual(format_id(7), "WO-00007")
        self.assertEqual(parse_id("WO-00007"), 7)
        self.assertEqual(parse_id("7"), 7)

    def test_durations(self):
        from wotrack.timeutil import format_duration, parse_duration

        self.assertEqual(parse_duration("1h30m"), 90)
        self.assertEqual(format_duration(90), "1h30m")
        self.assertEqual(format_duration(30), "30m")

    def test_migrate_v1_maps_an_order(self):
        from wotrack.migration import migrate_v1

        with open(SAMPLES / "plant.json", encoding="utf-8") as handle:
            source = json.load(handle)
        doc = migrate_v1(source, datetime(2026, 3, 10, tzinfo=timezone.utc))
        self.assertEqual(doc["format"], 2)
        first = doc["orders"][0]
        self.assertEqual(first["id"], "WO-00001")
        self.assertEqual(first["project"], "GEN")
        self.assertEqual(first["estimate_minutes"], 150)
        self.assertEqual(first["created_at"], "2026-03-01T09:15:00Z")
        self.assertEqual(doc["site"], "North Plant")


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "plant.json"
        shutil.copyfile(SAMPLES / "plant.json", self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def wo(self, *args, env=None):
        return run_cli("--file", str(self.path), *args, env=env)

    def test_any_command_migrates_and_backs_up(self):
        original = self.path.read_bytes()
        result = self.wo("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["format"], 2)
        self.assertEqual(Path(str(self.path) + ".v1.bak").read_bytes(), original)
        self.assertIn("note: migrated %s from format 1 to format 2" % self.path, result.stderr)

    def test_show_uses_canonical_id_and_project(self):
        lines = self.wo("show", "1").stdout.splitlines()
        self.assertEqual(lines[0], "Work order WO-00001")
        self.assertEqual(lines[1], "Project:   GEN (General)")

    def test_add_message(self):
        result = self.wo("add", "Check fire doors")
        self.assertEqual(result.stdout, "created WO-00007 in GEN: Check fire doors\n")

    def test_projects(self):
        self.assertEqual(
            self.wo("project", "add", "ops", "Operations").stdout,
            "created project OPS: Operations\n",
        )
        self.assertEqual(
            self.wo("project", "list").stdout,
            "KEY  NAME        ACTIVE  TOTAL\n"
            "GEN  General          4      6\n"
            "OPS  Operations       0      0\n",
        )

    def test_list_json_for_a_project(self):
        self.wo("project", "add", "OPS", "Operations")
        self.wo("add", "Check fire doors", "--project", "ops")
        data = json.loads(self.wo("list", "--project", "OPS", "--json").stdout)
        self.assertEqual([item["id"] for item in data], ["WO-00007"])
        self.assertEqual(data[0]["project"], "OPS")

    def test_title_rule(self):
        result = self.wo("add", "replace pump SEAL")
        self.assertEqual(result.returncode, 3)
        self.assertIn("already has this title: WO-00001", result.stderr)

    def test_multi_key_sort(self):
        self.wo("project", "add", "ops", "Operations")
        self.wo("move", "2", "ops")
        self.assertEqual(
            self.wo("list", "--sort=project,-priority").stdout,
            "ID        PROJECT  PRIORITY  STATUS       DUE          ASSIGNEE  TITLE\n"
            "WO-00005  GEN      normal    open         2026-04-01   -         Calibrate flow meter\n"
            "WO-00001  GEN      high      in_progress  2026-03-05!  dana      Replace pump seal\n"
            "WO-00003  GEN      urgent    blocked      2026-03-02!  lee       Fix conveyor drive\n"
            "WO-00002  OPS      normal    open         -            -         Inspect boiler relief valve\n",
        )

    def test_report_by_project(self):
        self.assertEqual(
            self.wo("report", "--by", "project").stdout,
            "PROJECT  OPEN  IN_PROGRESS  BLOCKED  DONE  CANCELLED  TOTAL  EST_ACTIVE\n"
            "GEN         2            1        1     1          1      6      10h15m\n"
            "TOTAL       2            1        1     1          1      6      10h15m\n",
        )

    def test_hours_is_deprecated(self):
        result = self.wo("add", "Check fire doors", "--hours", "1.5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning: --hours is deprecated; use --estimate", result.stderr)
        self.assertIn("Estimate:  1h30m\n", self.wo("show", "7").stdout)

    def test_validation_errors_exit_3(self):
        result = self.wo("add", "Check fire doors", "--priority", "critical")
        self.assertEqual(result.returncode, 3)


if __name__ == "__main__":
    unittest.main()
