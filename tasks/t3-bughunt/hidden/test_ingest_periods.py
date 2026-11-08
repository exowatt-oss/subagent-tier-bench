import unittest
from decimal import Decimal

from meterbill.accounts import Account
from meterbill.catalog import PriceBook
from meterbill.events import UsageEvent
from meterbill.invoice import build_invoice
from meterbill.timeutil import Period, parse_timestamp

D = Decimal
PLANS = {"plans": [
    {"id": "basic", "name": "Basic", "base_fee": "10.00",
     "metrics": [{"metric": "compute", "label": "Compute", "unit": "hour",
                  "tiers": [{"up_to": None, "unit_price": "0.50"}]}]},
]}


def compute(quantity, ts, event_id="c1", account_id="acct"):
    return UsageEvent(event_id=event_id, account_id=account_id, metric="compute",
                      quantity=D(quantity), unit="hour", timestamp=parse_timestamp(ts))


def compute_hours(acct, period, events):
    invoice = build_invoice(acct, PriceBook.from_dict(PLANS), period, events)
    return invoice.section("usage")[0].quantity


UTC_ACCOUNT = Account(account_id="acct", name="Acct", plan_id="basic", utc_offset=0)


class PeriodBoundaryTests(unittest.TestCase):
    def test_event_at_period_end_is_not_in_month(self):
        events = [compute("10", "2026-04-01T00:00:00Z")]
        self.assertEqual(compute_hours(UTC_ACCOUNT, Period(2026, 3), events), D("0"))

    def test_event_at_period_end_opens_next_month(self):
        events = [compute("10", "2026-04-01T00:00:00Z")]
        self.assertEqual(compute_hours(UTC_ACCOUNT, Period(2026, 4), events), D("10"))

    def test_local_midnight_end_for_positive_offset(self):
        acct = Account(account_id="acct", name="Acct", plan_id="basic", utc_offset=330)
        events = [compute("6", "2026-03-31T18:30:00Z", "c1"),
                  compute("2", "2026-03-31T18:29:59Z", "c2")]
        self.assertEqual(compute_hours(acct, Period(2026, 3), events), D("2"))

    def test_last_microsecond_belongs_to_month(self):
        events = [compute("3", "2026-03-31T23:59:59.999999Z")]
        self.assertEqual(compute_hours(UTC_ACCOUNT, Period(2026, 3), events), D("3"))


if __name__ == "__main__":
    unittest.main()
