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


def ids(*numbers):
    return ["WO-%05d" % n for n in numbers]


class QueryCase(unittest.TestCase):
    fixture_name = "multi_v2.json"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls._tmp.name) / "data.json"
        shutil.copyfile(DATA / cls.fixture_name, cls.path)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def wo(self, *args):
        return run_cli("--file", str(self.path), *args)

    def listed(self, *args):
        result = self.wo("list", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0].split()[0], "ID")
        return [line.split()[0] for line in lines[1:]]


class ProjectFilterTest(QueryCase):
    def test_single_project(self):
        self.assertEqual(self.listed("--project", "OPS"), ids(2, 5, 8))

    def test_repeated_project_keys_are_case_insensitive(self):
        self.assertEqual(self.listed("--project", "ops", "--project", "lab"), ids(2, 5, 7, 8))

    def test_project_combines_with_status_options(self):
        self.assertEqual(self.listed("--project", "GEN", "--all"), ids(1, 3, 6, 9))

    def test_unknown_project_is_not_found(self):
        result = self.wo("list", "--project", "NOPE")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error: no such project: NOPE", result.stderr)

    def test_tag_filter_ignores_case(self):
        self.assertEqual(self.listed("--tag", "MECHANICAL"), ids(1, 3, 9))
        self.assertEqual(self.listed("--tag", "Safety", "--project", "LAB"), ids(7))


class SortTest(QueryCase):
    def test_title_ignores_case(self):
        self.assertEqual(self.listed("--all", "--sort", "title"), ids(7, 5, 9, 3, 2, 8, 4, 1, 6))

    def test_assignee_ignores_case_and_puts_unassigned_last(self):
        self.assertEqual(self.listed("--all", "--sort", "assignee"), ids(7, 1, 4, 3, 6, 8, 2, 5, 9))

    def test_reversed_assignee_keeps_unassigned_last_and_ties_ascending(self):
        self.assertEqual(self.listed("--all", "--sort=-assignee"), ids(8, 3, 6, 1, 4, 7, 2, 5, 9))

    def test_due_earliest_first_missing_last(self):
        self.assertEqual(self.listed("--sort", "due"), ids(3, 1, 8, 7, 9, 5, 2))

    def test_reversed_due_keeps_missing_last(self):
        self.assertEqual(self.listed("--sort=-due"), ids(5, 7, 9, 8, 1, 3, 2))

    def test_status_follows_workflow_order(self):
        self.assertEqual(self.listed("--all", "--sort", "status"), ids(2, 5, 7, 8, 1, 9, 3, 4, 6))

    def test_project_then_reversed_priority(self):
        self.assertEqual(
            self.listed("--all", "--sort=project,-priority"), ids(9, 1, 6, 3, 4, 7, 8, 2, 5)
        )

    def test_reversed_priority_then_title(self):
        self.assertEqual(
            self.listed("--all", "--sort=-priority,title"), ids(8, 4, 5, 9, 2, 1, 6, 7, 3)
        )

    def test_updated_oldest_first(self):
        self.assertEqual(self.listed("--sort", "updated"), ids(3, 1, 5, 2, 7, 8, 9))

    def test_reversed_created_with_limit(self):
        self.assertEqual(self.listed("--sort=-created", "--limit", "3"), ids(9, 8, 7))

    def test_unknown_sort_key_is_usage_error(self):
        result = self.wo("list", "--sort", "priority,colour")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown sort key", result.stderr)


class ListRegressionTest(QueryCase):
    fixture_name = "plant_v1.json"

    def rows(self, *args):
        result = self.wo("list", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()[1:]

    def test_default_list_hides_closed_orders(self):
        rows = self.rows()
        self.assertEqual(len(rows), 4)
        self.assertFalse(any("Repaint safety lines" in row for row in rows))

    def test_text_matches_asset_ignoring_case(self):
        rows = self.rows("--text", "fm-12")
        self.assertEqual(len(rows), 1)
        self.assertIn("Calibrate flow meter", rows[0])

    def test_overdue_filter(self):
        rows = self.rows("--overdue")
        self.assertEqual(len(rows), 2)
        self.assertIn("Replace pump seal", rows[0])
        self.assertIn("Fix conveyor drive", rows[1])

    def test_single_key_due_sort(self):
        rows = self.rows("--sort", "due")
        titles = ["Fix conveyor drive", "Replace pump seal", "Calibrate flow meter",
                  "Inspect boiler relief valve"]
        for row, title in zip(rows, titles):
            self.assertIn(title, row)
        self.assertEqual(len(rows), 4)


if __name__ == "__main__":
    unittest.main()
