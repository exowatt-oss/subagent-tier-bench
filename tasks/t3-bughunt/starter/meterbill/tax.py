"""Sales-tax rates by region and the tax calculation."""

import json
from decimal import Decimal
from pathlib import Path

from .errors import InputError
from .money import ZERO, parse_decimal


class TaxTable:
    """Tax rates in percent, keyed by region code (``US-NY``), country (``US``) or ``*``."""

    def __init__(self, rates=None):
        self._rates = {}
        for key, raw in (rates or {}).items():
            code = str(key).strip().upper()
            rate = parse_decimal(raw, "tax rate for %s" % code)
            if not Decimal(0) <= rate <= Decimal(100):
                raise InputError("tax rate for %s must be between 0 and 100" % code)
            self._rates[code] = rate

    @classmethod
    def from_dict(cls, data):
        rates = data.get("rates") if isinstance(data, dict) else None
        if not isinstance(rates, dict):
            raise InputError("expected {\"rates\": {...}}")
        return cls(rates)

    @classmethod
    def load(cls, path):
        path = Path(path)
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle, parse_float=Decimal)
        except FileNotFoundError:
            raise InputError("tax file not found: %s" % path) from None
        except ValueError as exc:
            raise InputError("%s: invalid JSON (%s)" % (path.name, exc)) from None
        return cls.from_dict(data)

    def lookup(self, region):
        """Return ``(key, rate)``: exact region, then its country, then ``*``, else 0%."""
        code = (region or "").strip().upper()
        if code and code in self._rates:
            return code, self._rates[code]
        country = code.split("-", 1)[0]
        if country and country in self._rates:
            return country, self._rates[country]
        if "*" in self._rates:
            return "*", self._rates["*"]
        return "*", Decimal("0")


def compute_tax(taxable, rate):
    """Tax on ``taxable`` at ``rate`` percent, in whole cents."""
    if taxable <= 0 or rate == 0:
        return ZERO
    return round(taxable * rate / 100, 2)
