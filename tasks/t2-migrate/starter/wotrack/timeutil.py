"""Time helpers: the clock, timestamp/date parsing and formatting.

All timestamps handled by wotrack are UTC.  Internally they are aware
``datetime`` objects with ``tzinfo=timezone.utc`` and whole seconds.
"""

import os
import re
from datetime import date, datetime, timedelta, timezone

#: Environment variable that pins the current time (useful for scripts/tests).
NOW_ENV = "WOTRACK_NOW"

#: How timestamps are written to the data file and shown to users.
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?"
    r"(?P<zone>Z|[+-]\d{2}:\d{2})?$"
)
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def parse_timestamp(text):
    """Parse a timestamp string into an aware UTC ``datetime``.

    Accepted forms are ``YYYY-MM-DD HH:MM:SS`` and ``YYYY-MM-DD HH:MM``, with
    either a space or a ``T`` between date and time.  Seconds may carry a
    fractional part, which is discarded.  An optional ``Z`` or ``+HH:MM`` /
    ``-HH:MM`` suffix gives the UTC offset; without a suffix the value is
    already UTC.  Raises ``ValueError`` for anything else.
    """
    if not isinstance(text, str):
        raise ValueError("invalid timestamp: %r" % (text,))
    match = _TIMESTAMP_RE.match(text.strip())
    if match is None:
        raise ValueError("invalid timestamp: %r" % (text,))
    try:
        day = _parse_date_parts(match.group("date"))
        moment = datetime(
            day.year,
            day.month,
            day.day,
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second") or 0),
        )
    except ValueError:
        raise ValueError("invalid timestamp: %r" % (text,)) from None
    zone = match.group("zone")
    if zone and zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        hours, minutes = zone[1:].split(":")
        moment -= sign * timedelta(hours=int(hours), minutes=int(minutes))
    return moment.replace(tzinfo=timezone.utc)


def to_utc(moment):
    """Return ``moment`` as an aware UTC datetime (naive values are UTC)."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def format_timestamp(moment):
    """Format a datetime the way the data file and the CLI show it."""
    return to_utc(moment).strftime(TIMESTAMP_FORMAT)


def _parse_date_parts(text):
    match = _DATE_RE.match(text)
    if match is None:
        raise ValueError("invalid date: %r" % (text,))
    year, month, day = (int(part) for part in match.groups())
    return date(year, month, day)


def parse_date(text):
    """Parse a strict ``YYYY-MM-DD`` calendar date.  Raises ``ValueError``."""
    if not isinstance(text, str):
        raise ValueError("invalid date: %r" % (text,))
    try:
        return _parse_date_parts(text.strip())
    except ValueError:
        raise ValueError("invalid date: %r" % (text,)) from None


def format_date(day):
    """Format a date as ``YYYY-MM-DD``."""
    return day.isoformat()


def now():
    """The current time as an aware UTC datetime with whole seconds.

    If the ``WOTRACK_NOW`` environment variable is set to a timestamp in any
    form accepted by :func:`parse_timestamp`, that value is used instead of the
    system clock.
    """
    pinned = os.environ.get(NOW_ENV, "").strip()
    if pinned:
        return parse_timestamp(pinned)
    return datetime.now(timezone.utc).replace(microsecond=0)


def today():
    """Today's date in UTC (honours ``WOTRACK_NOW``)."""
    return now().date()


def format_hours(hours):
    """Format an hour estimate for display: ``2.5`` -> ``2.5h``, ``3.0`` -> ``3h``."""
    return "%gh" % hours
