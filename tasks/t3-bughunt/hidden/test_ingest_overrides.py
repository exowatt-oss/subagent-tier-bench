import copy
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period, parse_timestamp
from meterbill.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
PRO = {"id": "pro", "name": "Pro", "base_fee": "100.00",
       "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB", "pricing": "volume",
                    "tiers": [{"up_to": "1000", "unit_price": "0.10"},
                              {"up_to": "5000", "unit_price": "0.08"},
                              {"up_to": None, "unit_price": "0.06"}]}]}
BASIC = {"id": "basic", "name": "Basic", "base_fee": "10.00",
         "metrics": [{"metric": "storage", "label": "Storage", "unit": "GB",
                      "tiers": [{"up_to": None, "unit_price": "0.25"}]}]}
PLANS = {"plans": [PRO, BASIC]}


def pro_with_tier2(price, base_fee="100.00"):
    plan = copy.deepcopy(PRO)
    plan["base_fee"] = base_fee
    plan["metrics"][0]["tiers"][1]["unit_price"] = price
    return plan


def storage_event(quantity, account_id="acme"):
    return UsageEvent(event_id="s1", account_id=account_id, metric="storage",
                      quantity=D(quantity), unit="GB",
                      timestamp=parse_timestamp("2026-03-10T00:00:00Z"))


ACME = Account(account_id="acme", name="Acme", plan_id="pro")


class PriceBookUpdateTests(unittest.TestCase):
    def test_tiers_follow_update_after_lookup(self):
        book = PriceBook.from_dict(PLANS)
        self.assertEqual(book.tiers("pro", "storage")[1], (D("5000"), D("0.08")))
        book.update_plan(pro_with_tier2("0.09"))
        self.assertEqual(book.tiers("pro", "storage")[1], (D("5000"), D("0.09")))

    def test_tiers_follow_update_after_validate(self):
        book = PriceBook.from_dict(PLANS)
        book.validate()
        book.update_plan(pro_with_tier2("0.07"))
        self.assertEqual(book.tiers("pro", "storage")[1][1], D("0.07"))

    def test_update_changing_tier_count(self):
        book = PriceBook.from_dict(PLANS)
        book.validate()
        plan = copy.deepcopy(BASIC)
        plan["metrics"][0]["tiers"] = [{"up_to": "100", "unit_price": "0.30"},
                                       {"up_to": None, "unit_price": "0.20"}]
        book.update_plan(plan)
        self.assertEqual(book.tiers("basic", "storage"),
                         ((D("100"), D("0.30")), (None, D("0.20"))))

    def test_apply_overrides_file_after_validate(self):
        book = PriceBook.from_dict(PLANS)
        book.validate()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.json"
            path.write_text(json.dumps({"plans": [pro_with_tier2("0.09")]}), encoding="utf-8")
            book.apply_overrides(path)
        self.assertEqual(book.tiers("pro", "storage")[1][1], D("0.09"))

    def test_invoice_uses_updated_unit_price(self):
        book = PriceBook.from_dict(PLANS)
        book.validate()
        book.update_plan(pro_with_tier2("0.09"))
        invoice = build_invoice(ACME, book, Period(2026, 3), [storage_event("2000")])
        self.assertEqual(invoice.section("usage")[0].amount, D("180.00"))

    def test_updating_one_plan_leaves_other_plans_alone(self):
        book = PriceBook.from_dict(PLANS)
        book.validate()
        plan = copy.deepcopy(BASIC)
        plan["base_fee"] = "12.00"
        book.update_plan(plan)
        self.assertEqual(book.plan("basic").base_fee, D("12.00"))
        self.assertEqual(book.tiers("pro", "storage")[1], (D("5000"), D("0.08")))


class OverridesThroughWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.data = self.dir / "data"
        self.data.mkdir()
        (self.data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
        (self.data / "accounts.csv").write_text(
            "account_id,name,plan\nacme,Acme,pro\nzed,Zed,basic\n", encoding="utf-8")
        self.overrides = self.dir / "overrides.json"
        self.overrides.write_text(
            json.dumps({"plans": [pro_with_tier2("0.09", base_fee="120.00")]}), encoding="utf-8")
        self.events = self.dir / "usage.csv"
        self.events.write_text("event_id,account_id,metric,quantity,unit,timestamp\n"
                               "s1,acme,storage,2000,GB,2026-03-10T00:00:00Z\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "meterbill", "--data", str(self.data),
                               "--price-overrides", str(self.overrides), *args],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=30)

    def test_workspace_rates_overridden_price(self):
        workspace = Workspace.load(self.data, price_overrides=self.overrides)
        invoices = workspace.invoices(Period(2026, 3), [storage_event("2000")], ["acme"])
        self.assertEqual(invoices[0].section("usage")[0].amount, D("180.00"))

    def test_workspace_uses_overridden_base_fee(self):
        workspace = Workspace.load(self.data, price_overrides=self.overrides)
        invoices = workspace.invoices(Period(2026, 3), [], ["acme"])
        self.assertEqual(invoices[0].lines[0].amount, D("120.00"))

    def test_cli_invoice_with_price_overrides(self):
        proc = self.cli("invoice", "--period", "2026-03", "--account", "acme", "--format", "csv",
                        str(self.events))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = proc.stdout.splitlines()
        self.assertIn("acme,2026-03,usage,Storage,2000,GB,180.00", rows)
        self.assertIn("acme,2026-03,total,Total,,,300.00", rows)

    def test_cli_plans_lists_overridden_price(self):
        proc = self.cli("plans")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("    up to 5000: 0.09", proc.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
