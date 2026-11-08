"""Assembling one account's invoice for one billing period."""

from dataclasses import dataclass
from decimal import Decimal

from .discounts import apply_coupons, describe_coupon
from .errors import InputError
from .money import ZERO, plain, round_money
from .rating import rate_metric
from .tax import TaxTable, compute_tax
from .units import convert

ZERO_QTY = Decimal("0")


class Line:
    """One invoice line. ``amount`` is in cents; discounts are negative."""

    __slots__ = ("section", "description", "amount", "quantity", "unit", "code")

    def __init__(self, section, description, amount, quantity=None, unit=None, code=None):
        self.section = section
        self.description = description
        self.amount = amount
        self.quantity = quantity
        self.unit = unit
        self.code = code

    def __repr__(self):
        return "Line(%r, %r, %s)" % (self.section, self.description, self.amount)


class Invoice:
    def __init__(self, account, plan, period, lines=None, notes=[]):
        self.account = account
        self.plan = plan
        self.period = period
        self.lines = list(lines) if lines is not None else []
        self.discounts = []
        self.tax = Line("tax", "Tax (exempt)", ZERO)
        self.tax_rate = None
        self.notes = notes

    def section(self, name):
        return [line for line in self.lines if line.section == name]

    @property
    def subtotal(self):
        return sum((line.amount for line in self.lines), ZERO)

    @property
    def discount_total(self):
        return sum((-line.amount for line in self.discounts), ZERO)

    @property
    def taxable(self):
        return self.subtotal - self.discount_total

    @property
    def total(self):
        return self.taxable + self.tax.amount

    def __repr__(self):
        return "Invoice(%s, %s, total=%s)" % (self.account.account_id, self.period, self.total)


@dataclass(frozen=True)
class UsageEntry:
    account: object
    event: object
    quantity: Decimal
    unit: str


def _account_events(account, period, events):
    for event in events:
        if event.account_id == account.account_id and period.contains(
            event.timestamp, account.utc_offset
        ):
            yield event


def _canonical(event, metric_price):
    try:
        return convert(event.quantity, event.unit, metric_price.unit)
    except InputError as exc:
        raise InputError("event %s: %s" % (event.event_id, exc)) from None


def aggregate_usage(account, plan, period, events):
    """Sum the account's in-period quantities per plan metric (canonical units).

    Returns ``(totals, ignored)`` where ``ignored`` counts events whose metric is
    not part of the plan.
    """
    totals = {}
    ignored = {}
    for event in _account_events(account, period, events):
        metric_price = plan.metric(event.metric)
        if metric_price is None:
            ignored[event.metric] = ignored.get(event.metric, 0) + 1
            continue
        totals[event.metric] = totals.get(event.metric, ZERO_QTY) + _canonical(event, metric_price)
    return totals, ignored


def usage_entries(account, plan, period, events):
    """The account's in-period events for plan metrics, ordered by time then event id."""
    entries = []
    for event in _account_events(account, period, events):
        metric_price = plan.metric(event.metric)
        if metric_price is None:
            continue
        entries.append(UsageEntry(account, event, _canonical(event, metric_price), metric_price.unit))
    entries.sort(key=lambda entry: (entry.event.timestamp, entry.event.event_id))
    return entries


def is_billable(account, period):
    return account.start_date is None or account.start_date <= period.last_day


def build_invoice(account, book, period, events, coupons=None, tax_table=None, adjustments=()):
    """Build the invoice of ``account`` for ``period``.

    Returns ``None`` when the account starts after the period. ``events`` may
    contain events of other accounts and other months; they are skipped.
    """
    if not is_billable(account, period):
        return None
    plan = book.plan(account.plan_id)
    invoice = Invoice(account, plan, period)

    fee = plan.base_fee
    if account.start_date is not None and account.start_date > period.first_day:
        active = (period.last_day - account.start_date).days + 1
        fee = round_money(plan.base_fee * active / period.days)
        invoice.notes.append("Base fee prorated: %d of %d days" % (active, period.days))
    invoice.lines.append(Line("fee", "Base fee", fee))

    totals, ignored = aggregate_usage(account, plan, period, events)
    usage_amount = ZERO
    for metric_price in plan.metrics:
        rated = rate_metric(
            metric_price,
            book.tiers(plan.plan_id, metric_price.metric),
            totals.get(metric_price.metric, ZERO_QTY),
        )
        invoice.lines.append(
            Line(
                "usage",
                rated.label,
                rated.amount,
                quantity=rated.quantity,
                unit=rated.unit,
                code=rated.metric,
            )
        )
        usage_amount += rated.amount
    if ignored:
        invoice.notes.append(
            "Ignored %d event(s) for metrics not in plan: %s"
            % (sum(ignored.values()), ", ".join(sorted(ignored)))
        )

    if plan.minimum_commit > usage_amount:
        invoice.lines.append(
            Line("adjustment", "Minimum commitment top-up", plan.minimum_commit - usage_amount)
        )
    for adjustment in adjustments:
        invoice.lines.append(Line("adjustment", adjustment.description, adjustment.amount))

    resolved = []
    for code in account.coupons:
        coupon = (coupons or {}).get(code)
        if coupon is None:
            raise InputError("account %s: unknown coupon %s" % (account.account_id, code))
        resolved.append(coupon)
    for coupon, amount in apply_coupons(invoice.subtotal, resolved):
        invoice.discounts.append(
            Line("discount", describe_coupon(coupon), -amount, code=coupon.code)
        )

    if account.tax_exempt:
        invoice.tax = Line("tax", "Tax (exempt)", ZERO)
        invoice.tax_rate = None
    else:
        key, rate = (tax_table or TaxTable()).lookup(account.region)
        invoice.tax = Line(
            "tax", "Tax (%s %s%%)" % (key, plain(rate)), compute_tax(invoice.taxable, rate), code=key
        )
        invoice.tax_rate = rate
    return invoice
