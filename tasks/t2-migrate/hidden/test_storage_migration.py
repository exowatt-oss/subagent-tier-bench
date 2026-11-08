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


class MigrationCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def fixture(self, name, target="data.json"):
        dest = self.tmp / target
        shutil.copyfile(DATA / name, dest)
        return dest

    def wo(self, path, *args, env=None):
        return run_cli("--file", str(path), *args, env=env)

    def load(self, path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)


class AutomaticMigrationTest(MigrationCase):
    def test_read_only_list_rewrites_v1_file_as_format_2(self):
        path = self.fixture("plant_v1.json")
        result = self.wo(path, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = self.load(path)
        self.assertEqual(doc["format"], 2)
        self.assertNotIn("next_id", doc)
        self.assertEqual(doc["next_number"], 7)

    def test_backup_is_byte_identical_copy_of_original(self):
        path = self.fixture("plant_v1.json")
        original = path.read_bytes()
        self.wo(path, "report")
        backup = Path(str(path) + ".v1.bak")
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_bytes(), original)

    def test_existing_backup_is_never_overwritten(self):
        path = self.fixture("plant_v1.json")
        backup = Path(str(path) + ".v1.bak")
        backup.write_text("older backup\n", encoding="utf-8")
        result = self.wo(path, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(backup.read_text(encoding="utf-8"), "older backup\n")
        self.assertEqual(self.load(path)["format"], 2)

    def test_migration_note_printed_to_stderr(self):
        path = self.fixture("plant_v1.json")
        result = self.wo(path, "list")
        expected = "note: migrated %s from format 1 to format 2 (backup: %s.v1.bak)" % (path, path)
        self.assertIn(expected, result.stderr.splitlines())
        self.assertNotIn("note:", result.stdout)

    def test_second_run_prints_no_note_and_leaves_file_alone(self):
        path = self.fixture("plant_v1.json")
        self.wo(path, "list")
        self.assertEqual(self.load(path)["format"], 2)
        migrated = path.read_bytes()
        result = self.wo(path, "list", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("note:", result.stderr)
        self.assertEqual(path.read_bytes(), migrated)

    def test_format_2_file_never_gets_a_backup(self):
        path = self.fixture("multi_v2.json")
        before = path.read_bytes()
        result = self.wo(path, "report")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(Path(str(path) + ".v1.bak").exists())
        self.assertEqual(path.read_bytes(), before)

    def test_failing_command_still_leaves_migrated_file_and_backup(self):
        path = self.fixture("plant_v1.json")
        result = self.wo(path, "show", "99")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.load(path)["format"], 2)
        self.assertTrue(Path(str(path) + ".v1.bak").exists())

    def test_unparseable_timestamp_exit_4_and_nothing_written(self):
        path = self.fixture("bad_timestamp_v1.json")
        before = path.read_bytes()
        result = self.wo(path, "list")
        self.assertEqual(result.returncode, 4)
        self.assertTrue(result.stderr.startswith("error:"), result.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(Path(str(path) + ".v1.bak").exists())

    def test_file_without_format_key_is_migrated(self):
        path = self.fixture("legacy_v1.json")
        result = self.wo(path, "list", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = self.load(path)
        self.assertEqual(doc["format"], 2)
        self.assertEqual([o["id"] for o in doc["orders"]], ["WO-00002", "WO-00009", "WO-00014"])


class MigrateCommandTest(MigrationCase):
    def test_migrate_reports_number_of_orders(self):
        path = self.fixture("plant_v1.json")
        result = self.wo(path, "migrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "migrated %s to format 2 (work orders: 6)\n" % path)

    def test_migrate_on_format_2_file_says_already(self):
        path = self.fixture("multi_v2.json")
        before = path.read_bytes()
        result = self.wo(path, "migrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "%s is already format 2\n" % path)
        self.assertEqual(path.read_bytes(), before)

    def test_migrate_on_missing_file_is_storage_error(self):
        path = self.tmp / "absent.json"
        result = self.wo(path, "migrate")
        self.assertEqual(result.returncode, 4)
        self.assertIn("error: no such file: %s" % path, result.stderr)
        self.assertFalse(path.exists())


class StorageRegressionTest(MigrationCase):
    def test_list_on_missing_file_does_not_create_it(self):
        path = self.tmp / "nothing.json"
        result = self.wo(path, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "no work orders")
        self.assertFalse(path.exists())

    def test_wotrack_file_env_selects_data_file(self):
        path = self.tmp / "from-env.json"
        result = run_cli("add", "Check fire extinguishers", env={"WOTRACK_FILE": str(path)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(path.exists())

if __name__ == "__main__":
    unittest.main()
