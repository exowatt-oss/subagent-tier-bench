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


class ReportCase(unittest.TestCase):
    fixture_name = "multi_v2.json"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls._tmp.name) / "data.json"
        shutil.copyfile(DATA / cls.fixture_name, cls.path)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def out(self, *args):
        result = run_cli("--file", str(self.path), *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


class ByProjectReportTest(ReportCase):
    def test_by_project_table(self):
        self.assertEqual(
            self.out("report", "--by", "project"),
            "PROJECT  OPEN  IN_PROGRESS  BLOCKED  DONE  CANCELLED  TOTAL  EST_ACTIVE\n"
            "GEN         0            2        1     0          1      4          9h\n"
            "LAB         1            0        0     1          0      2          2h\n"
            "OPS         3            0        0     0          0      3       1h45m\n"
            "QA          0            0        0     0          0      0          0m\n"
            "TOTAL       4            2        1     1          1      9      12h45m\n",
        )

    def test_by_project_restricted_to_given_projects(self):
        self.assertEqual(
            self.out("report", "--by", "project", "--project", "ops", "--project", "LAB"),
            "PROJECT  OPEN  IN_PROGRESS  BLOCKED  DONE  CANCELLED  TOTAL  EST_ACTIVE\n"
            "LAB         1            0        0     1          0      2          2h\n"
            "OPS         3            0        0     0          0      3       1h45m\n"
            "TOTAL       4            0        0     1          0      5       3h45m\n",
        )

    def test_by_project_json(self):
        data = json.loads(self.out("report", "--by", "project", "--json"))
        self.assertEqual([row["key"] for row in data["projects"]], ["GEN", "LAB", "OPS", "QA"])
        self.assertEqual(
            data["projects"][2],
            {"key": "OPS", "name": "Operations", "open": 3, "in_progress": 0, "blocked": 0,
             "done": 0, "cancelled": 0, "total": 3, "active_estimate_minutes": 105},
        )
        self.assertEqual(
            data["totals"],
            {"open": 4, "in_progress": 2, "blocked": 1, "done": 1, "cancelled": 1,
             "total": 9, "active_estimate_minutes": 765},
        )

    def test_summary_restricted_to_project_keeps_text_format(self):
        self.assertEqual(
            self.out("report", "--project", "gen"),
            "Work orders: 4\n"
            "By status:\n"
            "  open         0\n"
            "  in_progress  2\n"
            "  blocked      1\n"
            "  done         0\n"
            "  cancelled    1\n"
            "By priority:\n"
            "  urgent  1\n"
            "  high    2\n"
            "  normal  1\n"
            "  low     0\n"
            "Overdue: 2\n",
        )

    def test_summary_json(self):
        data = json.loads(self.out("report", "--json"))
        self.assertEqual(
            data,
            {
                "total": 9,
                "by_status": {"open": 4, "in_progress": 2, "blocked": 1, "done": 1, "cancelled": 1},
                "by_priority": {"low": 2, "normal": 3, "high": 2, "urgent": 2},
                "overdue": 3,
                "active_estimate_minutes": 765,
            },
        )

class ProjectListTest(ReportCase):
    def test_project_list_table(self):
        self.assertEqual(
            self.out("project", "list"),
            "KEY  NAME        ACTIVE  TOTAL\n"
            "GEN  General          3      4\n"
            "LAB  Laboratory       1      2\n"
            "OPS  Operations       3      3\n"
            "QA   Quality          0      0\n",
        )

    def test_project_list_json(self):
        data = json.loads(self.out("project", "list", "--json"))
        self.assertEqual(len(data), 4)
        self.assertEqual(
            data[1],
            {"key": "LAB", "name": "Laboratory", "created_at": "2026-02-01T08:00:00Z",
             "active": 1, "total": 2},
        )


class ListTableTest(ReportCase):
    def test_list_table_has_project_column_and_left_aligned_ids(self):
        self.assertEqual(
            self.out("list", "--project", "LAB", "--all"),
            "ID        PROJECT  PRIORITY  STATUS  DUE         ASSIGNEE  TITLE\n"
            "WO-00004  LAB      low       done    -           dana      Repaint safety lines\n"
            "WO-00007  LAB      urgent    open    2026-03-12  bea       Audit fume hoods\n",
        )

    def test_overdue_marker_in_table(self):
        lines = self.out("list", "--project", "OPS", "--sort", "due").splitlines()
        self.assertEqual(
            lines[1], "WO-00008  OPS      low       open    2026-03-09!  Omar      Order spare belts"
        )

class DurationFunctionsTest(unittest.TestCase):
    def test_parse_duration_forms(self):
        from wotrack.timeutil import parse_duration

        self.assertEqual(parse_duration("45m"), 45)
        self.assertEqual(parse_duration("2h"), 120)
        self.assertEqual(parse_duration("1h30m"), 90)
        self.assertEqual(parse_duration("2H05M"), 125)

    def test_parse_duration_rejects_other_spellings(self):
        from wotrack.timeutil import parse_duration

        for text in ("1h 30m", "90", "h", "1.5m", "m30"):
            with self.assertRaises(ValueError):
                parse_duration(text)

    def test_format_duration(self):
        from wotrack.timeutil import format_duration

        self.assertEqual(
            [format_duration(m) for m in (0, 45, 60, 65, 120, 615, 6000)],
            ["0m", "45m", "1h", "1h05m", "2h", "10h15m", "100h"],
        )


class ReportRegressionTest(ReportCase):
    fixture_name = "plant_v1.json"

    def test_report_text_unchanged(self):
        self.assertEqual(
            self.out("report"),
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


if __name__ == "__main__":
    unittest.main()
