"""Timestamps, fixed UTC offsets and monthly billing periods.

meterbill never consults the system time zone or a tz database. Every account
has one fixed UTC offset (no daylight-saving changes) and every event timestamp
carries its own offset or ``Z``.
"""

import re
from datetime import date, datetime, time, timedelta, timezone

from .errors import InputError

MIN_OFFSET = -12 * 60
MAX_OFFSET = 14 * 60

_OFFSET_RE = re.compile(r"^([+-])(\d{2}):(\d{2})$")
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3}|\.\d{6})?(?:Z|[+-]\d{2}:\d{2})$"
)
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_offset(text):
    """Parse a fixed UTC offset into minutes east of UTC.

    ``"+05:30" -> 330``, ``"-03:30" -> -210``, ``"Z" -> 0``.
    """
    if not isinstance(text, str):
        raise InputError("UTC offset must be a string, got %r" % (text,))
    value = text.strip()
    if value == "Z":
        return 0
    match = _OFFSET_RE.match(value)
    if not match:
        raise InputError("invalid UTC offset %r (expected +HH:MM or -HH:MM)" % text)
    sign = -1 if match.group(1) == "-" else 1
    hours = int(match.group(2))
    minutes = int(match.group(3))
    if minutes > 59:
        raise InputError("invalid UTC offset %r (minutes must be 00-59)" % text)
    total = sign * hours * 60 + minutes
    if not MIN_OFFSET <= total <= MAX_OFFSET:
        raise InputError("UTC offset %r is outside -12:00..+14:00" % text)
    return total


def tz_for(offset_minutes):
    """A fixed-offset ``tzinfo`` for an offset in minutes."""
    return timezone(timedelta(minutes=offset_minutes))


def parse_timestamp(text):
    """Parse an event timestamp into an aware ``datetime``.

    Accepted: ``YYYY-MM-DDTHH:MM:SS`` with optional ``.fff`` or ``.ffffff``,
    followed by ``Z`` or ``+HH:MM`` / ``-HH:MM``. A missing designator is an error.
    """
    if not isinstance(text, str):
        raise InputError("timestamp must be a string, got %r" % (text,))
    value = text.strip()
    if not _TIMESTAMP_RE.match(value):
        raise InputError(
            "invalid timestamp %r (expected YYYY-MM-DDTHH:MM:SS followed by Z or +HH:MM)" % text
        )
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise InputError("invalid timestamp %r" % text) from None


def parse_date(text, what="date"):
    """Parse ``YYYY-MM-DD`` into a ``date``."""
    value = (text or "").strip()
    if not _DATE_RE.match(value):
        raise InputError("invalid %s %r (expected YYYY-MM-DD)" % (what, text))
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InputError("invalid %s %r" % (what, text)) from None


def to_local(ts, offset_minutes):
    """The same instant expressed at a fixed UTC offset."""
    return ts.astimezone(tz_for(offset_minutes))


class Period:
    """One calendar month, interpreted in each account's local time."""

    __slots__ = ("year", "month")

    def __init__(self, year, month):
        if not 1 <= month <= 12 or not 1 <= year <= 9998:
            raise InputError("invalid billing period %04d-%02d" % (year, month))
        self.year = year
        self.month = month

    @classmethod
    def parse(cls, text):
        match = _PERIOD_RE.match((text or "").strip())
        if not match:
            raise InputError("invalid period %r (expected YYYY-MM)" % (text,))
        return cls(int(match.group(1)), int(match.group(2)))

    @property
    def first_day(self):
        return date(self.year, self.month, 1)

    @property
    def next_first_day(self):
        if self.month == 12:
            return date(self.year + 1, 1, 1)
        return date(self.year, self.month + 1, 1)

    @property
    def last_day(self):
        return self.next_first_day - timedelta(days=1)

    @property
    def days(self):
        return (self.next_first_day - self.first_day).days

    def start_utc(self, offset_minutes):
        """Local midnight of the first day, as a UTC datetime."""
        local = datetime.combine(self.first_day, time(0), tzinfo=tz_for(offset_minutes))
        return local.astimezone(timezone.utc)

    def end_utc(self, offset_minutes):
        """Local midnight of the first day of the next month, as a UTC datetime."""
        local = datetime.combine(self.next_first_day, time(0), tzinfo=tz_for(offset_minutes))
        return local.astimezone(timezone.utc)

    def contains(self, ts, offset_minutes):
        """True when the instant ``ts`` falls in this month for an account at ``offset_minutes``."""
        return self.start_utc(offset_minutes) <= ts < self.end_utc(offset_minutes)

    def __str__(self):
        return "%04d-%02d" % (self.year, self.month)

    def __repr__(self):
        return "Period(%d, %d)" % (self.year, self.month)

    def __eq__(self, other):
        if not isinstance(other, Period):
            return NotImplemented
        return (self.year, self.month) == (other.year, other.month)

    def __hash__(self):
        return hash((self.year, self.month))
