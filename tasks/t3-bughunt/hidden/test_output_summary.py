import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill.accounts import Account, Adjustment
from meterbill.catalog import PriceBook
from meterbill.invoice import build_invoice
from meterbill.summary import summarize, summary_csv, summary_text
from meterbill.timeutil import Period

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
MARCH = Period(2026, 3)
PLANS = {"plans": [{"id": "flat", "name": "Flat", "base_fee": "20.00", "metrics": []}]}


def invoice(account_id, extra="0.00"):
    acct = Account(account_id=account_id, name=account_id.title(), plan_id="flat")
    adjustments = []
    if D(extra) != 0:
        adjustments = [Adjustment(account_id=account_id, description="Manual", amount=D(extra))]
    return build_invoice(acct, PriceBook.from_dict(PLANS), MARCH, [], adjustments=adjustments)


def order(rows):
    return [(row.rank, row.account_id) for row in rows]


class TieBreakTests(unittest.TestCase):
    def test_two_way_tie_by_account_id(self):
        rows = summarize([invoice("globex"), invoice("initech")])
        self.assertEqual(order(rows), [(1, "globex"), (2, "initech")])

    def test_three_way_tie(self):
        rows = summarize([invoice("cyan"), invoice("amber"), invoice("blue")])
        self.assertEqual(order(rows), [(1, "amber"), (2, "blue"), (3, "cyan")])

    def test_tie_below_the_top(self):
        rows = summarize([invoice("delta", "30.00"), invoice("bravo"), invoice("alpha"),
                          invoice("echo", "-10.00")])
        self.assertEqual(order(rows), [(1, "delta"), (2, "alpha"), (3, "bravo"), (4, "echo")])

    def test_summary_csv_tie_order(self):
        lines = summary_csv(summarize([invoice("zeta"), invoice("eta")])).splitlines()
        self.assertEqual(lines, ["rank,account_id,name,subtotal,discount,tax,total",
                                 "1,eta,Eta,20.00,0.00,0.00,20.00",
                                 "2,zeta,Zeta,20.00,0.00,0.00,20.00"])

    def test_summary_text_tie_order(self):
        text = summary_text(summarize([invoice("stark"), invoice("avalon"), invoice("wayne")]), MARCH)
        ids = [line.split()[1] for line in text.splitlines()[2:5]]
        self.assertEqual(ids, ["avalon", "stark", "wayne"])

    def test_cli_summary_csv_ties(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
            (data / "accounts.csv").write_text(
                "account_id,name,plan\nwayne,Wayne,flat\nstark,Stark,flat\navalon,Avalon,flat\n",
                encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(data),
                                   "summary", "--period", "2026-03", "--format", "csv"],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ids = [line.split(",")[:2] for line in proc.stdout.splitlines()[1:]]
        self.assertEqual(ids, [["1", "avalon"], ["2", "stark"], ["3", "wayne"]])


class RankingRegressionTests(unittest.TestCase):
    def test_distinct_totals_highest_first(self):
        rows = summarize([invoice("a", "1.00"), invoice("b", "5.00"), invoice("c", "-3.00")])
        self.assertEqual(order(rows), [(1, "b"), (2, "a"), (3, "c")])
        self.assertEqual([row.total for row in rows], [D("25.00"), D("21.00"), D("17.00")])

    def test_grand_total_line(self):
        text = summary_text(summarize([invoice("a", "1000.00"), invoice("b", "5.25")]), MARCH)
        last = text.splitlines()[-1]
        self.assertIn("Grand total", last)
        self.assertTrue(last.endswith("1,045.25"))


if __name__ == "__main__":
    unittest.main()
