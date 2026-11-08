import unittest


class FormatIdTest(unittest.TestCase):
    def test_pads_to_at_least_five_digits(self):
        from wotrack.ids import format_id

        self.assertEqual(format_id(7), "WO-00007")
        self.assertEqual(format_id(12345), "WO-12345")
        self.assertEqual(format_id(123456), "WO-123456")

    def test_zero_is_rejected(self):
        from wotrack.ids import format_id

        with self.assertRaises(ValueError):
            format_id(0)


class ParseIdTest(unittest.TestCase):
    def test_prefix_is_case_insensitive_and_padding_optional(self):
        from wotrack.ids import parse_id

        self.assertEqual(parse_id("wo-7"), 7)
        self.assertEqual(parse_id("Wo-007"), 7)

    def test_legacy_digits_with_leading_zeros(self):
        from wotrack.ids import parse_id

        self.assertEqual(parse_id("007"), 7)
        self.assertEqual(parse_id("15"), 15)

    def test_surrounding_whitespace_is_ignored(self):
        from wotrack.ids import parse_id

        self.assertEqual(parse_id("  WO-12 "), 12)

    def test_zero_number_is_rejected(self):
        from wotrack.errors import UsageError
        from wotrack.ids import parse_id

        for text in ("0", "WO-00000"):
            with self.assertRaises(UsageError):
                parse_id(text)

    def test_other_prefixes_and_garbage_rejected(self):
        from wotrack.errors import UsageError
        from wotrack.ids import parse_id

        for text in ("X-7", "WO-", "WO7", "WO-7a", "-7"):
            with self.assertRaises(UsageError):
                parse_id(text)


class ErrorClassesTest(unittest.TestCase):
    def test_exit_codes(self):
        from wotrack import errors

        self.assertEqual(errors.NotFoundError.exit_code, 1)
        self.assertEqual(errors.UsageError.exit_code, 2)
        self.assertEqual(errors.ValidationError.exit_code, 3)
        self.assertEqual(errors.StorageError.exit_code, 4)

    def test_conflict_error_is_a_validation_error(self):
        from wotrack import errors

        self.assertTrue(issubclass(errors.ConflictError, errors.ValidationError))
        self.assertEqual(errors.ConflictError.exit_code, 3)
        self.assertTrue(issubclass(errors.UsageError, errors.WotrackError))


if __name__ == "__main__":
    unittest.main()
