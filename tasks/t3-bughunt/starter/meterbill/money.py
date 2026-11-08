"""Decimal helpers for money and plain numbers.

Every amount in meterbill is a ``decimal.Decimal``. Binary floats are never used
for money or quantities.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .errors import InputError

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def round_money(amount):
    """Round to whole cents, half away from zero (0.125 -> 0.13, -0.125 -> -0.13)."""
    return Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_decimal(raw, what="value"):
    """Parse a decimal from a string, an int or a Decimal.

    Booleans, floats and anything non-finite are rejected so that a typo in a
    data file cannot silently turn into a binary-float approximation.
    """
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, bool) or raw is None:
        raise InputError("%s must be a number, got %r" % (what, raw))
    elif isinstance(raw, int):
        value = Decimal(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise InputError("%s is empty" % what)
        try:
            value = Decimal(text)
        except InvalidOperation:
            raise InputError("%s is not a number: %r" % (what, raw)) from None
    else:
        raise InputError("%s must be a decimal string or an integer, got %r" % (what, raw))
    if not value.is_finite():
        raise InputError("%s must be finite, got %r" % (what, raw))
    return value


def parse_money(raw, what="amount", allow_negative=False):
    """Parse a money value and round it to cents (half up)."""
    value = parse_decimal(raw, what)
    if value < 0 and not allow_negative:
        raise InputError("%s must not be negative, got %s" % (what, raw))
    return round_money(value)


def plain(value):
    """Plain decimal notation without exponent or trailing fractional zeros.

    ``plain(Decimal("1.500")) == "1.5"``, ``plain(Decimal("1E+3")) == "1000"``.
    """
    text = format(Decimal(value).normalize(), "f")
    return "0" if text in ("-0", "") else text
