"""Data model shared by every ledgerlite module (see SPEC.md section 1)."""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal  # noqa: F401  (every quantity is a Decimal)
from typing import List, Optional

SYMBOLS = ("$", "€", "£", "¥")


@dataclass(frozen=True)
class Amount:
    quantity: Decimal
    commodity: str


@dataclass
class Posting:
    account: str
    amount: Optional[Amount] = None
    cost: Optional[Amount] = None
    cost_type: Optional[str] = None  # None, "@" or "@@"
    assertion: Optional[Amount] = None
    comment: str = ""
    filename: str = ""
    lineno: int = 0
    inferred: bool = False


@dataclass
class Transaction:
    date: datetime.date
    description: str = ""
    status: str = ""  # "", "*" or "!"
    code: str = ""
    comment: str = ""
    postings: List[Posting] = field(default_factory=list)
    filename: str = ""
    lineno: int = 0


@dataclass
class Price:
    date: datetime.date
    commodity: str
    price: Amount
    filename: str = ""
    lineno: int = 0


@dataclass
class Journal:
    transactions: List[Transaction] = field(default_factory=list)
    prices: List[Price] = field(default_factory=list)


class LedgerError(Exception):
    """Base class for journal errors; str() is "filename:lineno: message"."""

    def __init__(self, filename, lineno, message):
        super().__init__(filename, lineno, message)
        self.filename = filename
        self.lineno = lineno
        self.message = message

    def __str__(self):
        return "{}:{}: {}".format(self.filename, self.lineno, self.message)


class ParseError(LedgerError):
    pass


class BalanceError(LedgerError):
    pass


class AssertionFailure(LedgerError):
    pass


def format_amount(quantity, commodity, precision):
    """Format a quantity in a commodity at a display precision (SPEC 4.1)."""
    raise NotImplementedError
