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

ORDER_KEYS = {
    "id", "number", "project", "title", "priority", "status", "asset", "assignee", "tags",
    "estimate_minutes", "due", "created_at", "updated_at", "overdue",
}


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


class OutputCase(unittest.TestCase):
    fixture_name = "plant_v1.json"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "data.json"
        shutil.copyfile(DATA / self.fixture_name, self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def wo(self, *args, env=None):
        return run_cli("--file", str(self.path), *args, env=env)


class ShowTextTest(OutputCase):
    def test_show_full_text(self):
        result = self.wo("show", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "Work order WO-00001\n"
            "Project:   GEN (General)\n"
            "Title:     Replace pump seal\n"
            "Asset:     PUMP-07\n"
            "Priority:  high\n"
            "Status:    in_progress\n"
            "Assignee:  dana\n"
            "Tags:      mechanical, urgent\n"
            "Estimate:  2h30m\n"
            "Due:       2026-03-05 (overdue)\n"
            "Created:   2026-03-01T09:15:00Z\n"
            "Updated:   2026-03-02T08:00:00Z\n"
            "Notes:\n"
            "  [2026-03-01T10:00:00Z] parts ordered\n"
            "  [2026-03-02T08:00:00Z] seal arrived\n",
        )

    def test_show_estimates_as_durations(self):
        self.assertIn("Estimate:  45m\n", self.wo("show", "5").stdout)
        self.assertIn("Estimate:  1h\n", self.wo("show", "2").stdout)
        self.assertIn("Estimate:  -\n", self.wo("show", "4").stdout)

class JsonOutputTest(OutputCase):
    def test_show_json(self):
        result = self.wo("show", "3", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "id": "WO-00003",
                "number": 3,
                "project": "GEN",
                "title": "Fix conveyor drive",
                "asset": "CONV-3",
                "priority": "urgent",
                "status": "blocked",
                "assignee": "lee",
                "tags": ["mechanical"],
                "estimate_minutes": 360,
                "due": "2026-03-02",
                "created_at": "2026-02-27T16:05:00Z",
                "updated_at": "2026-02-28T07:30:00Z",
                "overdue": True,
                "notes": [{"at": "2026-02-28T07:30:00Z", "text": "waiting for gearbox"}],
            },
        )

    def test_list_json_objects_have_exactly_the_documented_keys(self):
        shutil.copyfile(DATA / "multi_v2.json", self.path)
        data = json.loads(self.wo("list", "--json", "--project", "OPS").stdout)
        self.assertEqual([item["id"] for item in data], ["WO-00002", "WO-00005", "WO-00008"])
        for item in data:
            self.assertEqual(set(item), ORDER_KEYS)
        self.assertEqual(data[0]["number"], 2)
        self.assertIsNone(data[0]["assignee"])
        self.assertIsNone(data[2]["estimate_minutes"])

    def test_list_json_without_matches_prints_empty_list(self):
        result = self.wo("list", "--json", "--text", "no such thing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])
        self.assertNotIn("no work orders", result.stdout)

    def test_list_json_stdout_stays_clean_during_migration(self):
        result = self.wo("list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual([item["id"] for item in data], ["WO-00001", "WO-00002", "WO-00003", "WO-00005"])
        self.assertIn("note: migrated", result.stderr)

if __name__ == "__main__":
    unittest.main()
