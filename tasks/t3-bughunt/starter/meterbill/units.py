"""Units of measure and exact conversions between them.

Each unit belongs to a family; quantities convert only within a family. Data
units are decimal (SI): 1 GB = 1000 MB.
"""

from decimal import Decimal

from .errors import InputError

UNITS = {
    "call": ("count", Decimal("1")),
    "kcall": ("count", Decimal("1000")),
    "KB": ("data", Decimal("0.000001")),
    "MB": ("data", Decimal("0.001")),
    "GB": ("data", Decimal("1")),
    "TB": ("data", Decimal("1000")),
    "hour": ("time", Decimal("1")),
}


def is_unit(name):
    return name in UNITS


def family(unit):
    try:
        return UNITS[unit][0]
    except KeyError:
        raise InputError("unknown unit %r" % (unit,)) from None


def convert(quantity, from_unit, to_unit):
    """Convert ``quantity`` from ``from_unit`` to ``to_unit`` exactly."""
    if from_unit not in UNITS:
        raise InputError("unknown unit %r" % (from_unit,))
    if to_unit not in UNITS:
        raise InputError("unknown unit %r" % (to_unit,))
    if from_unit == to_unit:
        return quantity
    from_family, from_factor = UNITS[from_unit]
    to_family, to_factor = UNITS[to_unit]
    if from_family != to_family:
        raise InputError("cannot convert %s to %s" % (from_unit, to_unit))
    return quantity * from_factor / to_factor
