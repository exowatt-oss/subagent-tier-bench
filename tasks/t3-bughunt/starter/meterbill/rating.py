"""Turning a metric's monthly quantity into money."""

from dataclasses import dataclass
from decimal import Decimal

from .errors import InputError
from .money import round_money

ZERO_QTY = Decimal("0")


@dataclass(frozen=True)
class RatedMetric:
    metric: str
    label: str
    quantity: Decimal
    unit: str
    billable: Decimal
    amount: Decimal


def _graduated(tiers, quantity):
    total = Decimal("0")
    lower = ZERO_QTY
    for up_to, unit_price in tiers:
        upper = quantity if up_to is None else min(quantity, up_to)
        if upper > lower:
            total += (upper - lower) * unit_price
        if up_to is None or quantity <= up_to:
            break
        lower = up_to
    return total


def _volume(tiers, quantity):
    for up_to, unit_price in tiers:
        if up_to is None or quantity < up_to:
            return quantity * unit_price
    raise InputError("tier table has no unbounded last tier")


def price(pricing, tiers, quantity):
    """Unrounded charge for ``quantity`` billable units under ``tiers``.

    ``tiers`` is a sequence of ``(up_to, unit_price)`` with ``up_to`` inclusive and
    ``None`` for the unbounded last tier.
    """
    if quantity <= 0:
        return Decimal("0")
    if pricing == "graduated":
        return _graduated(tiers, quantity)
    if pricing == "volume":
        return _volume(tiers, quantity)
    raise InputError("unknown pricing model %r" % (pricing,))


def rate_metric(metric_price, tiers, quantity):
    """Rate one metric: subtract the included allowance, price it, round once."""
    billable = quantity - metric_price.included
    if billable < 0:
        billable = ZERO_QTY
    amount = round_money(price(metric_price.pricing, tiers, billable))
    return RatedMetric(
        metric=metric_price.metric,
        label=metric_price.label,
        quantity=quantity,
        unit=metric_price.unit,
        billable=billable,
        amount=amount,
    )
