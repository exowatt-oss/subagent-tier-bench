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


class ProjectCase(unittest.TestCase):
    fixture_name = "multi_v2.json"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "data.json"
        shutil.copyfile(DATA / self.fixture_name, self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def wo(self, *args, env=None):
        return run_cli("--file", str(self.path), *args, env=env)

    def doc(self):
        with open(self.path, encoding="utf-8") as handle:
            return json.load(handle)

    def project(self, key):
        for record in self.doc()["projects"]:
            if record["key"] == key:
                return record
        return None


class ProjectCommandsTest(ProjectCase):
    def test_add_uppercases_key_and_records_creation_time(self):
        result = self.wo("project", "add", "maint", "  Maintenance  ")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "created project MAINT: Maintenance\n")
        self.assertEqual(
            self.project("MAINT"),
            {"key": "MAINT", "name": "Maintenance", "created_at": NOW},
        )

    def test_key_must_be_letters_and_digits_starting_with_letter(self):
        for key in ("o", "1AB", "OPS-2", "ABCDEFGHIJK"):
            result = self.wo("project", "add", key, "Something %s" % key)
            self.assertEqual(result.returncode, 3, key)
        self.assertIn("error: invalid project key: 1AB", self.wo("project", "add", "1AB", "X").stderr)

    def test_ten_character_key_with_digits_is_valid(self):
        result = self.wo("project", "add", "Line2Pumps", "Line two pumps")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(self.project("LINE2PUMPS"))

    def test_duplicate_key_ignoring_case_is_conflict(self):
        result = self.wo("project", "add", "ops", "Other operations")
        self.assertEqual(result.returncode, 3)
        self.assertIn("error: project key already exists: OPS", result.stderr)

    def test_duplicate_name_ignoring_case_is_conflict(self):
        result = self.wo("project", "add", "OPS2", "OPERATIONS")
        self.assertEqual(result.returncode, 3)
        self.assertIn("already in use", result.stderr)
        self.assertIsNone(self.project("OPS2"))

    def test_rename_to_other_case_of_own_name_is_allowed(self):
        result = self.wo("project", "rename", "lab", "LABORATORY")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "renamed project LAB: Laboratory -> LABORATORY\n")
        self.assertEqual(self.project("LAB")["name"], "LABORATORY")

    def test_name_longer_than_sixty_characters_rejected(self):
        result = self.wo("project", "add", "LONG", "x" * 61)
        self.assertEqual(result.returncode, 3)
        ok = self.wo("project", "add", "LONG", "y" * 60)
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_default_project_cannot_be_removed(self):
        result = self.wo("project", "remove", "gen")
        self.assertEqual(result.returncode, 3)
        self.assertIn("error: cannot remove the default project GEN", result.stderr)

    def test_project_with_only_closed_orders_cannot_be_removed(self):
        self.wo("project", "add", "TMP", "Temporary")
        self.wo("add", "Short job", "--project", "TMP")
        self.wo("status", "WO-00012", "cancelled")
        result = self.wo("project", "remove", "TMP")
        self.assertEqual(result.returncode, 3)
        self.assertIn("error: project TMP is not empty", result.stderr)
        self.assertIsNotNone(self.project("TMP"))

    def test_empty_project_is_removed(self):
        result = self.wo("project", "remove", "qa")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "removed project QA\n")
        self.assertIsNone(self.project("QA"))

if __name__ == "__main__":
    unittest.main()
