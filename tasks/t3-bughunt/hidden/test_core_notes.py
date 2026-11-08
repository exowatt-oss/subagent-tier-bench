import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import Invoice, build_invoice
from meterbill.timeutil import Period, parse_timestamp
from meterbill.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
MARCH = Period(2026, 3)
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "31.00",
     "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB",
                  "tiers": [{"up_to": None, "unit_price": "0.20"}]}]},
]}
PRORATED_NOTE = "Base fee prorated: 15 of 31 days"
IGNORED_NOTE = "Ignored 3 event(s) for metrics not in plan: gpu_hours, sms"

LATE = Account(account_id="late", name="Late Start", plan_id="basic", start_date=date(2026, 3, 17))
ODD = Account(account_id="odd", name="Odd Metrics", plan_id="basic")
PLAIN = Account(account_id="plain", name="Plain", plan_id="basic")


def ev(event_id, account_id, metric, quantity="1", unit="GB"):
    return UsageEvent(event_id=event_id, account_id=account_id, metric=metric,
                      quantity=D(quantity), unit=unit,
                      timestamp=parse_timestamp("2026-03-20T00:00:00Z"))


EVENTS = [
    ev("e1", "late", "storage", "10"),
    ev("e2", "odd", "gpu_hours", "2", "hour"),
    ev("e3", "odd", "sms", "40", "call"),
    ev("e4", "odd", "gpu_hours", "1", "hour"),
    ev("e5", "plain", "storage", "5"),
]


def build(account):
    return build_invoice(account, PriceBook.from_dict(PLANS), MARCH, EVENTS)


ACCOUNTS_CSV = ("account_id,name,plan,start_date\n"
                "late,Late Start,basic,2026-03-17\n"
                "odd,Odd Metrics,basic,\n"
                "plain,Plain,basic,\n")
USAGE_CSV = ("event_id,account_id,metric,quantity,unit,timestamp\n"
             "e1,late,storage,10,GB,2026-03-20T00:00:00Z\n"
             "e2,odd,gpu_hours,2,hour,2026-03-20T00:00:00Z\n"
             "e3,odd,sms,40,call,2026-03-20T00:00:00Z\n"
             "e4,odd,gpu_hours,1,hour,2026-03-20T00:00:00Z\n"
             "e5,plain,storage,5,GB,2026-03-20T00:00:00Z\n")


class InvoiceNotesIsolationTests(unittest.TestCase):
    def test_second_invoice_has_no_notes(self):
        build(LATE)
        self.assertEqual(build(PLAIN).notes, [])

    def test_earlier_invoice_keeps_only_its_own_note(self):
        first = build(LATE)
        second = build(ODD)
        self.assertEqual(first.notes, [PRORATED_NOTE])
        self.assertEqual(second.notes, [IGNORED_NOTE])

    def test_new_invoice_objects_do_not_share_notes(self):
        plan = PriceBook.from_dict(PLANS).plan("basic")
        one = Invoice(PLAIN, plan, MARCH)
        two = Invoice(PLAIN, plan, MARCH)
        one.notes.append("only on one")
        self.assertEqual(two.notes, [])

    def test_rebuilding_an_invoice_does_not_repeat_notes(self):
        build(LATE)
        self.assertEqual(build(LATE).notes, [PRORATED_NOTE])

    def test_workspace_batch_notes_per_account(self):
        workspace = Workspace(PriceBook.from_dict(PLANS), {"late": LATE, "odd": ODD, "plain": PLAIN})
        invoices = workspace.invoices(MARCH, EVENTS)
        self.assertEqual({i.account.account_id: i.notes for i in invoices},
                         {"late": [PRORATED_NOTE], "odd": [IGNORED_NOTE], "plain": []})


class CliBatchNotesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
        (self.dir / "accounts.csv").write_text(ACCOUNTS_CSV, encoding="utf-8")
        (self.dir / "usage.csv").write_text(USAGE_CSV, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def run_invoice(self, fmt):
        proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(self.dir),
                               "invoice", "--period", "2026-03", "--format", fmt,
                               str(self.dir / "usage.csv")],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_text_batch_shows_notes_only_where_due(self):
        blocks = {}
        current = None
        for line in self.run_invoice("text").splitlines():
            if line.startswith("Invoice "):
                current = line.split()[1].rstrip(":")
                blocks[current] = []
            elif current is not None and line.startswith("- "):
                blocks[current].append(line[2:])
        self.assertEqual(blocks, {"late": [PRORATED_NOTE], "odd": [IGNORED_NOTE], "plain": []})

    def test_json_batch_notes(self):
        data = json.loads(self.run_invoice("json"))
        self.assertEqual([(i["account_id"], i["notes"]) for i in data],
                         [("late", [PRORATED_NOTE]), ("odd", [IGNORED_NOTE]), ("plain", [])])


class NoteContentTests(unittest.TestCase):
    def test_prorated_fee_and_note(self):
        invoice = build(LATE)
        self.assertEqual(invoice.lines[0].amount, D("15.00"))
        self.assertIn(PRORATED_NOTE, invoice.notes)

    def test_ignored_metrics_note(self):
        invoice = build(ODD)
        self.assertIn(IGNORED_NOTE, invoice.notes)
        self.assertEqual(invoice.section("usage")[0].quantity, D("0"))


if __name__ == "__main__":
    unittest.main()
