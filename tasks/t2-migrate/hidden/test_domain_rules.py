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


class RuleCase(unittest.TestCase):
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


class TitleRuleTest(RuleCase):
    def test_add_duplicate_active_title_in_same_project_is_conflict(self):
        result = self.wo("add", "  replace   PUMP seal ")
        self.assertEqual(result.returncode, 3)
        self.assertIn("error: an active work order in GEN already has this title: WO-00001", result.stderr)
        self.assertIsNone(self.order("WO-00012"))

    def test_same_title_allowed_in_another_project(self):
        result = self.wo("add", "Replace pump seal", "--project", "OPS")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_title_of_closed_order_may_be_reused(self):
        result = self.wo("add", "Repaint safety lines", "--project", "LAB")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reopening_into_a_title_clash_is_refused(self):
        result = self.wo("status", "6", "open")
        self.assertEqual(result.returncode, 3)
        self.assertIn("WO-00001", result.stderr)
        self.assertEqual(self.order("WO-00006")["status"], "cancelled")

    def test_edit_title_to_clash_is_refused_but_own_recase_allowed(self):
        clash = self.wo("edit", "9", "--title", "Fix Conveyor Drive")
        self.assertEqual(clash.returncode, 3)
        own = self.wo("edit", "3", "--title", "FIX conveyor drive")
        self.assertEqual(own.returncode, 0, own.stderr)
        self.assertEqual(self.order("WO-00003")["title"], "FIX conveyor drive")

    def test_moving_active_order_into_clash_is_refused(self):
        self.wo("add", "Order spare belts", "--project", "GEN")
        result = self.wo("move", "8", "GEN")
        self.assertEqual(result.returncode, 3)
        self.assertIn("WO-00012", result.stderr)
        self.assertEqual(self.order("WO-00008")["project"], "OPS")

    def test_moving_closed_order_is_not_checked(self):
        self.wo("add", "Repaint safety lines", "--project", "GEN")
        result = self.wo("move", "4", "GEN")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.order("WO-00004")["project"], "GEN")


class TagRulesTest(RuleCase):
    def test_tags_lowercased_unique_sorted_on_add(self):
        self.wo("add", "Check gauges", "--tag", "Zeta", "--tag", "alpha", "--tag", "ALPHA")
        self.assertEqual(self.order("WO-00012")["tags"], ["alpha", "zeta"])

    def test_add_and_remove_tag_ignore_case(self):
        result = self.wo("edit", "7", "--add-tag", "Annual", "--remove-tag", "SAFETY")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.order("WO-00007")["tags"], ["annual", "lab"])

class LegacyNumberingTest(unittest.TestCase):
    def test_new_order_after_migration_continues_above_highest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            shutil.copyfile(DATA / "legacy_v1.json", path)
            result = run_cli("--file", str(path), "add", "Inspect welding screens")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "created WO-00015 in GEN: Inspect welding screens\n")


class DomainRegressionTest(RuleCase):
    fixture_name = "plant_v1.json"

    def test_forbidden_transition_is_refused(self):
        result = self.wo("status", "4", "blocked")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot change status from done to blocked", result.stderr)

    def test_changing_to_current_status_is_refused(self):
        result = self.wo("status", "2", "open")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is already open", result.stderr)

    def test_status_input_accepts_hyphen_and_case(self):
        result = self.wo("status", "2", "IN-PROGRESS")
        self.assertEqual(result.returncode, 0, result.stderr)
        shown = self.wo("show", "2")
        self.assertIn("Status:    in_progress", shown.stdout)

    def test_numbers_are_not_reused_after_delete(self):
        self.wo("add", "First new order")
        self.wo("delete", "7")
        self.wo("add", "Second new order")
        shown = self.wo("show", "8")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Title:     Second new order", shown.stdout)

if __name__ == "__main__":
    unittest.main()
