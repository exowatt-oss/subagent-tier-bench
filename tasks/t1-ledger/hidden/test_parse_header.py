import datetime
import unittest

from ledgerlite import ParseError, parse_string


def first_txn(header):
    journal = parse_string(header + "\n    Expenses:Misc  $1.00\n    Assets:Cash\n", "h.journal")
    return journal.transactions[0]


class HeaderTests(unittest.TestCase):
    def test_slash_date(self):
        txn = first_txn("2024/03/09 Rent")
        self.assertEqual(txn.date, datetime.date(2024, 3, 9))
        self.assertEqual(txn.description, "Rent")

    def test_mixed_separators_rejected(self):
        with self.assertRaises(ParseError) as cm:
            parse_string("2024-03/09 Rent\n    A  $1\n    B\n", "h.journal")
        self.assertEqual(str(cm.exception), "h.journal:1: invalid date '2024-03/09'")

    def test_impossible_calendar_date_reports_its_line(self):
        text = "; leading comment\n\n2023-02-29 Leap?\n    A  $1\n    B\n"
        with self.assertRaises(ParseError) as cm:
            parse_string(text, "h.journal")
        self.assertEqual(cm.exception.lineno, 3)
        self.assertEqual(cm.exception.message, "invalid date '2023-02-29'")

    def test_status_needs_whitespace_after_it(self):
        txn = first_txn("2024-01-02 *Coffee")
        self.assertEqual(txn.status, "")
        self.assertEqual(txn.description, "*Coffee")

    def test_code_is_stripped_and_removed(self):
        txn = first_txn("2024-01-02 ! ( 1042 )   Hardware store")
        self.assertEqual(txn.status, "!")
        self.assertEqual(txn.code, "1042")
        self.assertEqual(txn.description, "Hardware store")

    def test_date_only_header_and_comment_right_after_date(self):
        txn = first_txn("2024-01-02;note")
        self.assertEqual(txn.date, datetime.date(2024, 1, 2))
        self.assertEqual(txn.description, "")
        self.assertEqual(txn.code, "")
        self.assertEqual(txn.comment, "note")


if __name__ == "__main__":
    unittest.main()
