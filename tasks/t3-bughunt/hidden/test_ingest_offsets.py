import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from meterbill.accounts import Account, load_accounts
from meterbill.catalog import PriceBook
from meterbill.errors import InputError
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period, parse_offset, parse_timestamp

D = Decimal
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "10.00",
     "metrics": [{"metric": "api_calls", "label": "API calls", "unit": "call",
                  "tiers": [{"up_to": None, "unit_price": "0.01"}]}]},
]}


def account(offset_text, account_id="acct"):
    return Account(account_id=account_id, name="Test", plan_id="basic",
                   utc_offset=parse_offset(offset_text))


def calls(account_id, quantity, ts):
    return UsageEvent(event_id="ev-" + ts, account_id=account_id, metric="api_calls",
                      quantity=D(quantity), unit="call", timestamp=parse_timestamp(ts))


def usage_quantity(acct, period, events):
    invoice = build_invoice(acct, PriceBook.from_dict(PLANS), period, events)
    return invoice.section("usage")[0].quantity


class ParseOffsetTests(unittest.TestCase):
    def test_minus_three_thirty(self):
        self.assertEqual(parse_offset("-03:30"), -210)

    def test_minus_zero_thirty(self):
        self.assertEqual(parse_offset("-00:30"), -30)

    def test_offset_below_minus_twelve_is_rejected(self):
        with self.assertRaises(InputError):
            parse_offset("-12:30")

    def test_whole_hour_and_positive_offsets(self):
        self.assertEqual(parse_offset("-05:00"), -300)
        self.assertEqual(parse_offset("+05:45"), 345)


class AccountsFileOffsetTests(unittest.TestCase):
    def test_accounts_csv_negative_half_hour_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.csv"
            path.write_text("account_id,name,plan,utc_offset\n"
                            "avalon,Avalon Fisheries,basic,-03:30\n"
                            "acme,Acme,basic,-05:00\n", encoding="utf-8")
            accounts = load_accounts(path)
        self.assertEqual(accounts["avalon"].utc_offset, -210)
        self.assertEqual(accounts["acme"].utc_offset, -300)


class NegativeHalfHourBucketingTests(unittest.TestCase):
    def test_late_evening_on_last_day_is_in_month(self):
        acct = account("-03:30")
        events = [calls("acct", "40", "2026-04-01T03:15:00Z")]
        self.assertEqual(usage_quantity(acct, Period(2026, 3), events), D("40"))

    def test_late_evening_on_last_day_is_not_in_next_month(self):
        acct = account("-03:30")
        events = [calls("acct", "40", "2026-04-01T03:15:00Z")]
        self.assertEqual(usage_quantity(acct, Period(2026, 4), events), D("0"))

    def test_evening_before_month_start_is_excluded(self):
        acct = account("-03:30")
        events = [calls("acct", "25", "2026-03-01T03:15:00Z"),
                  calls("acct", "7", "2026-03-01T03:45:00Z")]
        self.assertEqual(usage_quantity(acct, Period(2026, 3), events), D("7"))

    def test_minus_nine_thirty_account_month_end(self):
        acct = account("-09:30")
        events = [calls("acct", "12", "2026-07-01T09:00:00Z")]
        self.assertEqual(usage_quantity(acct, Period(2026, 6), events), D("12"))

    def test_whole_hour_negative_offset_month_end(self):
        acct = account("-05:00")
        events = [calls("acct", "9", "2026-04-01T04:30:00Z"),
                  calls("acct", "4", "2026-04-01T05:00:00Z")]
        self.assertEqual(usage_quantity(acct, Period(2026, 3), events), D("9"))


if __name__ == "__main__":
    unittest.main()
