import os
import tempfile
import unittest
from pathlib import Path

from ledgerlite import ParseError, parse_file


def txn(desc, day="01"):
    return "2024-01-{} {}\n    Expenses:X  $1\n    Assets:Cash\n".format(day, desc)


class IncludeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, text):
        path = Path(self.root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_nested_include_is_relative_to_including_file(self):
        main = self.write("main.journal", "include sub/a.journal\n")
        self.write("sub/a.journal", "include b.journal\n")
        self.write("sub/b.journal", txn("deep"))
        journal = parse_file(main)
        self.assertEqual([t.description for t in journal.transactions], ["deep"])
        expected = os.path.join(self.root, "sub", "b.journal")
        self.assertEqual(journal.transactions[0].filename, expected)
        self.assertEqual(journal.transactions[0].postings[1].filename, expected)

    def test_included_content_is_inserted_in_place(self):
        main = self.write(
            "main.journal",
            txn("first") + "include mid.journal\n" + txn("last") + "P 2024-01-09 AAPL $3\n",
        )
        self.write("mid.journal", "P 2024-01-08 AAPL $2\n" + txn("middle"))
        journal = parse_file(main)
        self.assertEqual(
            [t.description for t in journal.transactions], ["first", "middle", "last"]
        )
        self.assertEqual([p.date.day for p in journal.prices], [8, 9])

    def test_missing_include(self):
        main = self.write("main.journal", "; top\ninclude missing.journal\n")
        with self.assertRaises(ParseError) as cm:
            parse_file(main)
        self.assertEqual(str(cm.exception), main + ":2: include file not found: missing.journal")

    def test_include_cycle(self):
        a = self.write("a.journal", txn("a") + "include b.journal\n")
        self.write("b.journal", "\ninclude a.journal\n")
        with self.assertRaises(ParseError) as cm:
            parse_file(a)
        b_display = os.path.join(self.root, "b.journal")
        self.assertEqual(str(cm.exception), b_display + ":2: include cycle: a.journal")

    def test_diamond_include_is_allowed(self):
        main = self.write("main.journal", "include x.journal\ninclude y.journal\n")
        self.write("x.journal", "include common.journal\n")
        self.write("y.journal", "include common.journal\n" + txn("y"))
        self.write("common.journal", txn("common"))
        journal = parse_file(main)
        self.assertEqual(
            [t.description for t in journal.transactions], ["common", "common", "y"]
        )

    def test_error_inside_included_file(self):
        main = self.write("main.journal", "include sub/bad.journal\n")
        self.write("sub/bad.journal", "; bad\n\n2024-13-01 Oops\n    A  $1\n    B\n")
        with self.assertRaises(ParseError) as cm:
            parse_file(main)
        expected = os.path.join(self.root, "sub", "bad.journal")
        self.assertEqual(str(cm.exception), expected + ":3: invalid date '2024-13-01'")

    def test_display_names_are_not_normalised(self):
        os.makedirs(os.path.join(self.root, "sub"))
        main = self.write("main.journal", "include sub/../other files/o.journal\n")
        self.write("other files/o.journal", txn("other"))
        journal = parse_file(main)
        self.assertEqual(
            journal.transactions[0].filename,
            os.path.join(self.root, "sub/../other files/o.journal"),
        )


if __name__ == "__main__":
    unittest.main()
