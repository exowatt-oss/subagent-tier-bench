import copy
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
DATA = Path(__file__).resolve().parent / "data"
NOW = "2026-03-10T12:00:00Z"
NOW_DT = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def load_fixture(name):
    with open(DATA / name, encoding="utf-8") as handle:
        return json.load(handle)


def migrate(document):
    from wotrack.migration import migrate_v1

    return migrate_v1(document, NOW_DT)


def order(doc, order_id):
    for record in doc["orders"]:
        if record["id"] == order_id:
            return record
    raise AssertionError("order %s not found" % order_id)


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


class MigrateFunctionTest(unittest.TestCase):
    def test_whole_legacy_document_matches_expected(self):
        self.assertEqual(migrate(load_fixture("legacy_v1.json")), load_fixture("legacy_v2_expected.json"))

    def test_half_minute_estimate_rounds_up(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        self.assertEqual(order(doc, "WO-00014")["estimate_minutes"], 53)
        self.assertNotIn("estimate_hours", order(doc, "WO-00014"))

    def test_offset_timestamp_converted_to_utc_across_midnight(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        self.assertEqual(order(doc, "WO-00014")["created_at"], "2025-10-03T01:30:00Z")
        self.assertNotIn("created", order(doc, "WO-00014"))

    def test_fractional_seconds_dropped(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        self.assertEqual(order(doc, "WO-00014")["updated_at"], "2025-10-03T09:00:00Z")

    def test_notes_sorted_stably_by_normalised_time(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        notes = order(doc, "WO-00014")["notes"]
        self.assertEqual(
            [note["text"] for note in notes],
            ["valve stripped", "inspection started", "seals ordered"],
        )
        self.assertEqual(notes[0], {"at": "2025-10-03T07:15:00Z", "text": "valve stripped"})

    def test_tags_lowercased_deduplicated_and_sorted(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        self.assertEqual(order(doc, "WO-00014")["tags"], ["hydraulics", "press"])

    def test_unknown_order_keys_copied_unchanged(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        record = order(doc, "WO-00014")
        self.assertEqual(record["supplier"], "Hytec")
        self.assertEqual(record["labels"], {"color": "red", "rank": 2})

    def test_next_number_is_above_highest_number(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        self.assertEqual(doc["next_number"], 15)

    def test_default_project_created_at_is_earliest_normalised_created(self):
        doc = migrate(load_fixture("legacy_v1.json"))
        self.assertEqual(
            doc["projects"],
            [{"key": "GEN", "name": "General", "created_at": "2025-10-03T00:10:00Z"}],
        )

    def test_document_without_orders_uses_now_for_default_project(self):
        doc = migrate(load_fixture("empty_v1.json"))
        self.assertEqual(doc["projects"][0]["created_at"], "2030-01-02T03:04:05Z")
        self.assertEqual(doc["next_number"], 5)
        self.assertEqual(doc["orders"], [])

    def test_argument_is_not_modified(self):
        source = load_fixture("legacy_v1.json")
        pristine = copy.deepcopy(source)
        migrate(source)
        self.assertEqual(source, pristine)


class FormatTwoFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def load(self, path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_new_file_is_format_2_with_default_project(self):
        path = self.tmp / "new.json"
        result = run_cli("--file", str(path), "add", "Check sprinkler valves")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = self.load(path)
        self.assertEqual(doc["format"], 2)
        self.assertEqual(doc["next_number"], 2)
        self.assertEqual(doc["projects"], [{"key": "GEN", "name": "General", "created_at": NOW}])
        record = doc["orders"][0]
        self.assertEqual(
            sorted(record),
            sorted(["id", "project", "title", "asset", "priority", "status", "assignee", "tags",
                    "estimate_minutes", "due", "created_at", "updated_at", "notes"]),
        )
        self.assertEqual(record["id"], "WO-00001")
        self.assertIsNone(record["asset"])
        self.assertIsNone(record["assignee"])
        self.assertEqual(record["created_at"], NOW)

    def test_unknown_keys_survive_later_edits(self):
        path = self.tmp / "data.json"
        shutil.copyfile(DATA / "legacy_v1.json", path)
        result = run_cli("--file", str(path), "edit", "14", "--priority", "high")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = self.load(path)
        self.assertEqual(doc["site"], {"name": "Workshop B", "shift": "early"})
        record = order(doc, "WO-00014")
        self.assertEqual(record["priority"], "high")
        self.assertEqual(record["supplier"], "Hytec")
        self.assertEqual(record["labels"], {"color": "red", "rank": 2})

    def test_unknown_project_key_survives_project_rename(self):
        path = self.tmp / "data.json"
        shutil.copyfile(DATA / "multi_v2.json", path)
        result = run_cli("--file", str(path), "project", "rename", "OPS", "Plant Operations")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = self.load(path)
        ops = [p for p in doc["projects"] if p["key"] == "OPS"][0]
        self.assertEqual(ops["name"], "Plant Operations")
        self.assertEqual(ops["owner"], "ops-team")
        self.assertEqual(order(doc, "WO-00002")["work_center"], "WC-7")

    def test_unsupported_format_is_exit_4(self):
        path = self.tmp / "future.json"
        path.write_text('{"format": 3, "orders": []}\n', encoding="utf-8")
        result = run_cli("--file", str(path), "list")
        self.assertEqual(result.returncode, 4)
        self.assertIn("error: unsupported data format: 3", result.stderr)

    def test_written_file_is_sorted_indented_json(self):
        path = self.tmp / "data.json"
        shutil.copyfile(DATA / "multi_v2.json", path)
        run_cli("--file", str(path), "add", "Flush eyewash", "--project", "QA")
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text)
        self.assertEqual(text, json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        self.assertEqual([o["id"] for o in doc["orders"]][-2:], ["WO-00009", "WO-00012"])

    def test_invalid_json_message(self):
        path = self.tmp / "broken.json"
        path.write_text('{"format": 2, "orders": [', encoding="utf-8")
        result = run_cli("--file", str(path), "report")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error: cannot read %s: invalid JSON" % path, result.stderr)


if __name__ == "__main__":
    unittest.main()
