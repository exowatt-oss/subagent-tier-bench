import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill.accounts import Account, Coupon
from meterbill.catalog import PriceBook
from meterbill.discounts import apply_coupons
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
P10 = Coupon("WELCOME10", "percent", D("10"))
P5 = Coupon("LOYAL5", "percent", D("5"))
P50 = Coupon("HALF", "percent", D("50"))
F20 = Coupon("SAVE20", "fixed", D("20.00"))
F50 = Coupon("SAVE50", "fixed", D("50.00"))
COUPONS = {c.code: c for c in (P10, P5, P50, F20, F50)}
PLANS = {"plans": [{"id": "flat", "name": "Flat", "base_fee": "200.00", "metrics": []},
                   {"id": "tiny", "name": "Tiny", "base_fee": "30.00", "metrics": []}]}


def codes(applied):
    return [(coupon.code, amount) for coupon, amount in applied]


def invoice_with(coupon_codes, plan_id="flat"):
    acct = Account(account_id="acct", name="Acct", plan_id=plan_id, coupons=tuple(coupon_codes))
    return build_invoice(acct, PriceBook.from_dict(PLANS), Period(2026, 3), [], coupons=COUPONS)


class CouponOrderTests(unittest.TestCase):
    def test_percent_applies_before_fixed_listed_earlier(self):
        self.assertEqual(codes(apply_coupons(D("200.00"), [F20, P10])),
                         [("WELCOME10", D("20.00")), ("SAVE20", D("20.00"))])

    def test_result_does_not_depend_on_listing_order(self):
        self.assertEqual(codes(apply_coupons(D("200.00"), [F20, P10])),
                         codes(apply_coupons(D("200.00"), [P10, F20])))

    def test_all_percentages_before_fixed_in_listing_order(self):
        self.assertEqual(codes(apply_coupons(D("200.00"), [P10, F20, P5])),
                         [("WELCOME10", D("20.00")), ("LOYAL5", D("9.00")), ("SAVE20", D("20.00"))])

    def test_fixed_listed_first_is_capped_after_percentage(self):
        self.assertEqual(codes(apply_coupons(D("80.00"), [F50, P50])),
                         [("HALF", D("40.00")), ("SAVE50", D("40.00"))])

    def test_invoice_discount_lines_in_application_order(self):
        invoice = invoice_with(["SAVE20", "WELCOME10"])
        self.assertEqual([(l.description, l.amount) for l in invoice.discounts],
                         [("Coupon WELCOME10 (10% off)", D("-20.00")),
                          ("Coupon SAVE20 (20.00 off)", D("-20.00"))])

    def test_invoice_total_with_fixed_coupon_listed_first(self):
        invoice = invoice_with(["SAVE20", "WELCOME10"])
        self.assertEqual(invoice.discount_total, D("40.00"))
        self.assertEqual(invoice.total, D("160.00"))

    def test_cli_csv_discount_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "plans.json").write_text(json.dumps(PLANS), encoding="utf-8")
            (data / "accounts.csv").write_text(
                "account_id,name,plan,coupons\nhooli,Hooli,flat,save20; welcome10\n",
                encoding="utf-8")
            (data / "coupons.json").write_text(json.dumps({"coupons": [
                {"code": "WELCOME10", "type": "percent", "value": "10"},
                {"code": "SAVE20", "type": "fixed", "value": "20"}]}), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "meterbill", "--data", str(data),
                                   "invoice", "--period", "2026-03", "--format", "csv"],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = [r for r in proc.stdout.splitlines() if ",discount," in r or ",total," in r]
        self.assertEqual(rows, ["hooli,2026-03,discount,Coupon WELCOME10 (10% off),,,-20.00",
                                "hooli,2026-03,discount,Coupon SAVE20 (20.00 off),,,-20.00",
                                "hooli,2026-03,total,Total,,,160.00"])


class CouponRegressionTests(unittest.TestCase):
    def test_percent_then_fixed_listing(self):
        self.assertEqual(codes(apply_coupons(D("200.00"), [P10, F20])),
                         [("WELCOME10", D("20.00")), ("SAVE20", D("20.00"))])

    def test_percentages_compound(self):
        self.assertEqual(codes(apply_coupons(D("100.00"), [P10, P10])),
                         [("WELCOME10", D("10.00")), ("WELCOME10", D("9.00"))])

    def test_fixed_coupon_is_capped_and_not_carried_over(self):
        invoice = invoice_with(["SAVE50"], plan_id="tiny")
        self.assertEqual([l.amount for l in invoice.discounts], [D("-30.00")])
        self.assertEqual(invoice.total, D("0.00"))


if __name__ == "__main__":
    unittest.main()
