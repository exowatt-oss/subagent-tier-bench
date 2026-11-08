"""Formatting of money, quantities, UTC offsets and timestamps for output."""

from decimal import Decimal

from .money import plain
from .timeutil import tz_for


def money(amount):
    """Money with thousands separators: ``1,234.50``, ``-20.00``."""
    return "{:,.2f}".format(Decimal(amount))


def plain_money(amount):
    """Money without separators: ``1234.50``, ``-20.00``."""
    return "{:.2f}".format(Decimal(amount))


def quantity(value):
    """Plain quantity: ``2.675``, ``1000``, ``1.5`` (no exponent, no trailing zeros)."""
    return plain(value)


def quantity_text(value):
    """Quantity with thousands separators for the text invoice: ``125,000``."""
    text = "{:,f}".format(Decimal(value).normalize())
    return "0" if text == "-0" else text


def offset(minutes):
    """UTC offset given in minutes, as ``+HH:MM`` or ``-HH:MM``."""
    hours, mins = divmod(minutes, 60)
    return "%+03d:%02d" % (hours, mins)


def timestamp(ts, offset_minutes=None):
    """``YYYY-MM-DDTHH:MM:SS+HH:MM`` in the timestamp's own offset or ``offset_minutes``.

    Fractional seconds are dropped.
    """
    if offset_minutes is None:
        minutes = int(ts.utcoffset().total_seconds() // 60)
        local = ts
    else:
        minutes = offset_minutes
        local = ts.astimezone(tz_for(offset_minutes))
    return local.strftime("%Y-%m-%dT%H:%M:%S") + offset(minutes)
