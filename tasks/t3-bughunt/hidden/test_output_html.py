import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill import render
from meterbill.accounts import Account, Adjustment
from meterbill.catalog import PriceBook
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
MARCH = Period(2026, 3)
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "10.00",
     "metrics": [{"metric": "storage", "label": "Storage <GB-month>", "unit": "GB",
                  "tiers": [{"up_to": None, "unit_price": "0.10"}]}]},
    {"id": "plus", "name": "Plus \"Team\" & <Co>", "base_fee": "10.00", "metrics": []},
]}


def html_for(name="Plain Name", plan_id="basic", adjustments=()):
    acct = Account(account_id="acct", name=name, plan_id=plan_id)
    invoice = build_invoice(acct, PriceBook.from_dict(PLANS), MARCH, [],
                            adjustments=[Adjustment("acct", d, D("1.00")) for d in adjustments])
    return render.invoices_html([invoice], MARCH)


class HtmlEscapingTests(unittest.TestCase):
    def test_angle_brackets_escaped_once(self):
        html = html_for(name="Ops <EU>")
        self.assertIn("<h1>Invoice acct: Ops &lt;EU&gt;</h1>", html)
        self.assertNotIn("&amp;lt;", html)

    def test_apostrophe_escaped_once(self):
        html = html_for(name="O'Brien")
        self.assertIn("<h1>Invoice acct: O&#x27;Brien</h1>", html)
        self.assertNotIn("&amp;#x27;", html)

    def test_double_quote_in_adjustment_description(self):
        html = html_for(adjustments=['12" rack, monthly'])
        self.assertIn("<td>12&quot; rack, monthly</td>", html)

    def test_ampersand_next_to_other_specials(self):
        html = html_for(name="R&D <beta> \"x\"")
        self.assertIn("<h1>Invoice acct: R&amp;D &lt;beta&gt; &quot;x&quot;</h1>", html)

    def test_metric_label_escaped_once(self):
        self.assertIn("<td>Storage &lt;GB-month&gt;</td>", html_for())

    def test_plan_name_escaped_once(self):
        html = html_for(plan_id="plus")
        self.assertIn("Plus &quot;Team&quot; &amp; &lt;Co&gt; (plus)", html)

    def test_cli_html_escapes_account_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
            (data / "accounts.csv").write_text(
                "account_id,name,plan\nobrien,\"O'Brien <Ops> & Co\",basic\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(data),
                                   "invoice", "--period", "2026-03", "--format", "html"],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<h1>Invoice obrien: O&#x27;Brien &lt;Ops&gt; &amp; Co</h1>", proc.stdout)


class EscapingRegressionTests(unittest.TestCase):
    def test_lone_ampersand(self):
        html = html_for(name="Fish & Chips")
        self.assertIn("<h1>Invoice acct: Fish &amp; Chips</h1>", html)
        self.assertNotIn("&amp;amp;", html)

    def test_text_invoice_is_not_escaped(self):
        acct = Account(account_id="acct", name="O'Brien <Ops> & Co", plan_id="basic")
        invoice = build_invoice(acct, PriceBook.from_dict(PLANS), MARCH, [])
        self.assertEqual(render.invoice_text(invoice).splitlines()[0],
                         "Invoice acct: O'Brien <Ops> & Co")


if __name__ == "__main__":
    unittest.main()
