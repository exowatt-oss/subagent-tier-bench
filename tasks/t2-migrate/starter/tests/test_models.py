import unittest

from wotrack import models
from wotrack.errors import ValidationError


class CleanFieldTest(unittest.TestCase):
    def test_title_is_trimmed(self):
        self.assertEqual(models.clean_title("  Replace pump seal "), "Replace pump seal")

    def test_empty_title_is_rejected(self):
        with self.assertRaises(ValidationError):
            models.clean_title("   ")

    def test_priority_is_case_insensitive(self):
        self.assertEqual(models.clean_priority("Urgent"), "urgent")
        with self.assertRaises(ValidationError):
            models.clean_priority("critical")

    def test_status_accepts_hyphen(self):
        self.assertEqual(models.clean_status("in-progress"), "in_progress")


class WorkflowTest(unittest.TestCase):
    def test_done_can_only_be_reopened(self):
        self.assertEqual(models.TRANSITIONS["done"], ("open",))
        self.assertNotIn("done", models.TRANSITIONS["blocked"])


if __name__ == "__main__":
    unittest.main()
