import unittest
from decimal import Decimal

from ledgerlite import Amount, ParseError, parse_string


def postings(*lines):
    text = "2024-01-01 Test\n" + "".join(line + "\n" for line in lines)
    return parse_string(text, "p.journal").transactions[0].postings


def parse_error(*lines):
    text = "2024-01-01 Test\n" + "".join(line + "\n" for line in lines)
    try:
        parse_string(text, "p.journal")
    except ParseError as exc:
        return exc
    raise AssertionError("no ParseError raised")


class PostingTests(unittest.TestCase):
    def test_account_with_spaces_and_two_space_separator(self):
        p = postings("    Expenses:Dining Out  $12.00", "    Assets:Cash")
        self.assertEqual(p[0].account, "Expenses:Dining Out")
        self.assertEqual(p[0].amount, Amount(Decimal("12.00"), "$"))

    def test_tab_separator(self):
        p = postings("\tAssets:Cash\t-$5", "\tIncome:Gift")
        self.assertEqual(p[0].account, "Assets:Cash")
        self.assertEqual(p[0].amount, Amount(Decimal("-5"), "$"))

    def test_single_space_belongs_to_account(self):
        p = postings("    Assets:Cash $5", "    Income:Gift  -$5")
        self.assertEqual(p[0].account, "Assets:Cash $5")
        self.assertIsNone(p[0].amount)

    def test_posting_comment_filename_and_line(self):
        p = postings("    Expenses:Tips  $5 ;  for the waiter ", "    Assets:Cash")
        self.assertEqual(p[0].comment, "for the waiter")
        self.assertEqual(p[0].amount, Amount(Decimal("5"), "$"))
        self.assertEqual(p[0].filename, "p.journal")
        self.assertEqual(p[0].lineno, 2)
        self.assertEqual(p[1].comment, "")
        self.assertEqual(p[1].lineno, 3)

    def test_indented_comment_lines_are_ignored(self):
        p = postings("    ; a note", "  # another note", "    A  $1", "\t; tabbed note", "    B")
        self.assertEqual([x.account for x in p], ["A", "B"])
        self.assertEqual([x.lineno for x in p], [4, 6])

    def test_empty_segment_is_invalid(self):
        exc = parse_error("    Assets::Cash  $5", "    B")
        self.assertEqual(str(exc), "p.journal:2: invalid account name 'Assets::Cash'")

    def test_crlf_line_endings(self):
        journal = parse_string("2024-01-01 X\r\n    A  $5\r\n    B\r\n", "c.journal")
        txn = journal.transactions[0]
        self.assertEqual(txn.description, "X")
        self.assertEqual([p.account for p in txn.postings], ["A", "B"])
        self.assertEqual(txn.postings[0].amount, Amount(Decimal("5"), "$"))


if __name__ == "__main__":
    unittest.main()
