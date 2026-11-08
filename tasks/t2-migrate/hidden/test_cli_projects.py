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


class OrderProjectTest(ProjectCase):
    def test_add_to_project_by_lowercase_key(self):
        result = self.wo("add", "Swap filter cartridges", "--project", "lab")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "created WO-00012 in LAB: Swap filter cartridges\n")

    def test_add_uses_wotrack_project_environment_variable(self):
        result = self.wo("add", "Label sample fridges", env={"WOTRACK_PROJECT": "qa"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "created WO-00012 in QA: Label sample fridges\n")

    def test_add_to_unknown_project_is_not_found(self):
        result = self.wo("add", "Ghost order", "--project", "ZZZ")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error: no such project: ZZZ", result.stderr)
        self.assertEqual(len(self.doc()["orders"]), 9)

    def test_move_changes_project_and_updated_at(self):
        result = self.wo("move", "wo-5", "lab")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "WO-00005: OPS -> LAB\n")
        record = [o for o in self.doc()["orders"] if o["id"] == "WO-00005"][0]
        self.assertEqual(record["project"], "LAB")
        self.assertEqual(record["updated_at"], NOW)

    def test_move_to_current_project_changes_nothing(self):
        before = self.path.read_bytes()
        result = self.wo("move", "5", "OPS")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "WO-00005 is already in OPS\n")
        self.assertEqual(self.path.read_bytes(), before)



if __name__ == "__main__":
    unittest.main()
