"""Reading metered usage events from CSV and JSON Lines files."""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import InputError
from .timeutil import parse_timestamp
from .units import is_unit

FIELDS = ("event_id", "account_id", "metric", "quantity", "unit", "timestamp")


@dataclass(frozen=True)
class UsageEvent:
    event_id: str
    account_id: str
    metric: str
    quantity: Decimal
    unit: str
    timestamp: datetime
    source: str = ""


@dataclass
class EventLog:
    """Events kept after de-duplication, in input order."""

    events: list = field(default_factory=list)
    duplicates: int = 0

    def __iter__(self):
        return iter(self.events)

    def __len__(self):
        return len(self.events)


def _text(raw, name, where):
    if raw is None:
        raise InputError("%s: missing %s" % (where, name))
    if not isinstance(raw, str):
        raise InputError("%s: %s must be a string" % (where, name))
    value = raw.strip()
    if not value:
        raise InputError("%s: empty %s" % (where, name))
    return value


def _quantity(raw, where):
    if raw is None or isinstance(raw, bool):
        raise InputError("%s: quantity must be a number" % where)
    try:
        value = Decimal(raw.strip() if isinstance(raw, str) else raw)
    except (InvalidOperation, TypeError, ValueError):
        raise InputError("%s: invalid quantity %r" % (where, raw)) from None
    if not value.is_finite():
        raise InputError("%s: invalid quantity %r" % (where, raw))
    if value < 0:
        raise InputError("%s: quantity must not be negative" % where)
    return value


def make_event(record, where="event"):
    """Build a ``UsageEvent`` from a mapping with the six event fields."""
    for name in FIELDS:
        if name not in record:
            raise InputError("%s: missing %s" % (where, name))
    unit = _text(record["unit"], "unit", where)
    if not is_unit(unit):
        raise InputError("%s: unknown unit %r" % (where, unit))
    try:
        timestamp = parse_timestamp(_text(record["timestamp"], "timestamp", where))
    except InputError as exc:
        raise InputError("%s: %s" % (where, exc)) from None
    return UsageEvent(
        event_id=_text(record["event_id"], "event_id", where),
        account_id=_text(record["account_id"], "account_id", where),
        metric=_text(record["metric"], "metric", where),
        quantity=_quantity(record["quantity"], where),
        unit=unit,
        timestamp=timestamp,
        source=where,
    )


def read_events_csv(path):
    path = Path(path)
    events = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return events
        columns = {name.strip() for name in reader.fieldnames if name}
        missing = [name for name in FIELDS if name not in columns]
        if missing:
            raise InputError("%s: missing column(s): %s" % (path.name, ", ".join(missing)))
        for row in reader:
            record = {key.strip(): value for key, value in row.items() if key}
            if all(not (value or "").strip() for value in record.values()):
                continue
            events.append(make_event(record, "%s:%d" % (path.name, reader.line_num)))
    return events


def read_events_jsonl(path):
    path = Path(path)
    events = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            where = "%s:%d" % (path.name, lineno)
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise InputError("%s: invalid JSON (%s)" % (where, exc)) from None
            if not isinstance(record, dict):
                raise InputError("%s: expected a JSON object" % where)
            events.append(make_event(record, where))
    return events


def read_events(path):
    """Read one event file; the format follows the file extension."""
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return read_events_csv(path)
    if suffix in (".jsonl", ".ndjson"):
        return read_events_jsonl(path)
    raise InputError("%s: unsupported event file (use .csv, .jsonl or .ndjson)" % path)


def load_events(paths):
    """Read event files in order and drop repeated event ids (first one wins)."""
    log = EventLog()
    seen = set()
    for path in paths:
        if not Path(path).is_file():
            raise InputError("event file not found: %s" % path)
        for event in read_events(path):
            if event.event_id in seen:
                log.duplicates += 1
                continue
            seen.add(event.event_id)
            log.events.append(event)
    return log
