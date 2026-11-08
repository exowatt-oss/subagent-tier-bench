import unittest

from ledgerlite import ParseError, parse_string


def parse_error(text, filename="s.journal"):
    try:
        parse_string(text, filename)
    except ParseError as exc:
        return exc
    raise AssertionError("no ParseError raised")


class StructureTests(unittest.TestCase):
    def test_blank_line_ends_transaction(self):
        text = "2024-01-01 X\n    A  $5\n\n    B  -$5\n"
        exc = parse_error(text)
        self.assertEqual(str(exc), "s.journal:4: unexpected indented line")

    def test_whitespace_only_line_counts_as_blank(self):
        text = "2024-01-01 X\n    A  $5\n \t  \n    B  -$5\n"
        exc = parse_error(text)
        self.assertEqual((exc.lineno, exc.message), (4, "unexpected indented line"))

    def test_column_zero_comment_ends_transaction(self):
        text = "2024-01-01 X\n    A  $5\n; a note\n    B  -$5\n"
        exc = parse_error(text)
        self.assertEqual((exc.lineno, exc.message), (4, "unexpected indented line"))

    def test_transaction_without_postings(self):
        text = "2024-01-01 Empty\n    ; only a comment\n\n2024-01-02 X\n    A  $1\n    B\n"
        exc = parse_error(text)
        self.assertEqual(str(exc), "s.journal:1: transaction has no postings")

    def test_unknown_directive(self):
        exc = parse_error("# header comment\naccount Assets:Cash\n")
        self.assertEqual(str(exc), "s.journal:2: unknown directive 'account'")

    def test_price_directive_errors(self):
        self.assertEqual(parse_error("P 2024-02-01 AAPL\n").message, "invalid price directive")
        self.assertEqual(parse_error("P 2024-02-01 aapl $5\n").message, "invalid price directive")
        self.assertEqual(parse_error("P 2024-02-01 USD 5 USD\n").message, "invalid price directive")
        self.assertEqual(parse_error("P 2024-2-01 AAPL $5\n").message, "invalid date '2024-2-01'")
        self.assertEqual(parse_error("P 2024-02-01 AAPL 5\n").message, "invalid amount '5'")

    def test_journal_order_is_file_order(self):
        text = (
            "2024-03-01 Later\n    A  $1\n    B\n"
            "P 2024-05-01 AAPL $3\n"
            "2024-01-01 Earlier\n    A  $2\n    B\n"
            "P 2024-01-01 AAPL $2\n"
        )
        journal = parse_string(text)
        self.assertEqual([t.description for t in journal.transactions], ["Later", "Earlier"])
        self.assertEqual([p.date.month for p in journal.prices], [5, 1])
        self.assertEqual(journal.transactions[1].lineno, 5)
        self.assertEqual(journal.transactions[1].filename, "<string>")


if __name__ == "__main__":
    unittest.main()
