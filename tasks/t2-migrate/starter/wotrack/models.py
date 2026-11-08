"""Domain model: work orders, notes and the rules for their fields."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from . import timeutil
from .errors import TransitionError, ValidationError

PRIORITIES = ("low", "normal", "high", "urgent")
PRIORITY_RANK = {name: rank for rank, name in enumerate(PRIORITIES)}

STATUSES = ("open", "in_progress", "blocked", "done", "cancelled")
CLOSED_STATUSES = frozenset({"done", "cancelled"})

#: Allowed status changes: current status -> statuses it may move to.
TRANSITIONS = {
    "open": ("in_progress", "blocked", "done", "cancelled"),
    "in_progress": ("open", "blocked", "done", "cancelled"),
    "blocked": ("open", "in_progress", "cancelled"),
    "done": ("open",),
    "cancelled": ("open",),
}

MAX_TITLE_LENGTH = 120
MAX_TAG_LENGTH = 30
MAX_ESTIMATE_HOURS = 1000


# ---------------------------------------------------------------------------
# Field validation.  Each ``clean_*`` function returns the normalised value or
# raises ValidationError with a user-facing message.
# ---------------------------------------------------------------------------


def clean_title(value):
    title = (value or "").strip()
    if not title:
        raise ValidationError("title must not be empty")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValidationError("title is longer than %d characters" % MAX_TITLE_LENGTH)
    return title


def clean_priority(value):
    priority = (value or "").strip().lower()
    if priority not in PRIORITY_RANK:
        raise ValidationError(
            "invalid priority: %r (expected one of %s)" % (value, ", ".join(PRIORITIES))
        )
    return priority


def clean_status(value):
    status = (value or "").strip().lower().replace("-", "_")
    if status not in STATUSES:
        raise ValidationError(
            "invalid status: %r (expected one of %s)" % (value, ", ".join(STATUSES))
        )
    return status


def clean_tag(value):
    tag = (value or "").strip()
    if not tag:
        raise ValidationError("tag must not be empty")
    if any(ch.isspace() for ch in tag) or "," in tag:
        raise ValidationError("invalid tag: %r (no spaces or commas allowed)" % value)
    if len(tag) > MAX_TAG_LENGTH:
        raise ValidationError("tag is longer than %d characters" % MAX_TAG_LENGTH)
    return tag


def clean_hours(value):
    try:
        hours = float(value)
    except (TypeError, ValueError):
        raise ValidationError("invalid estimate: %r" % (value,)) from None
    if not 0 < hours <= MAX_ESTIMATE_HOURS:
        raise ValidationError(
            "estimate must be more than 0 and at most %d hours" % MAX_ESTIMATE_HOURS
        )
    return hours


def clean_due(value):
    """Parse a due date given as text; ``None`` or ``"none"`` clears it."""
    if value is None or value.strip().lower() == "none":
        return None
    try:
        return timeutil.parse_date(value)
    except ValueError:
        raise ValidationError("invalid due date: %r (expected YYYY-MM-DD)" % value) from None


def clean_person(value):
    """Normalise an assignee name; empty means unassigned."""
    return (value or "").strip()


def clean_note_text(value):
    text = (value or "").strip()
    if not text:
        raise ValidationError("note text must not be empty")
    return text


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@dataclass
class Note:
    at: datetime
    text: str

    def to_dict(self):
        return {"at": timeutil.format_timestamp(self.at), "text": self.text}

    @classmethod
    def from_dict(cls, data):
        return cls(at=timeutil.parse_timestamp(data["at"]), text=str(data["text"]))


@dataclass
class WorkOrder:
    id: int
    title: str
    created: datetime
    updated: datetime
    priority: str = "normal"
    status: str = "open"
    asset: str = ""
    assignee: str = ""
    tags: List[str] = field(default_factory=list)
    estimate_hours: Optional[float] = None
    due: Optional[date] = None
    notes: List[Note] = field(default_factory=list)

    @property
    def is_closed(self):
        return self.status in CLOSED_STATUSES

    def is_overdue(self, today):
        """True when the order has a due date before ``today`` and is not closed."""
        return self.due is not None and not self.is_closed and self.due < today

    def check_transition(self, new_status):
        """Raise TransitionError unless the workflow allows ``new_status``."""
        if new_status == self.status:
            raise TransitionError("work order %d is already %s" % (self.id, self.status))
        if new_status not in TRANSITIONS[self.status]:
            raise TransitionError(
                "cannot change status from %s to %s" % (self.status, new_status)
            )

    def add_tag(self, tag):
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag):
        if tag in self.tags:
            self.tags.remove(tag)

    # -- serialisation (data format 1) ------------------------------------

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "asset": self.asset,
            "priority": self.priority,
            "status": self.status,
            "assignee": self.assignee,
            "tags": list(self.tags),
            "estimate_hours": self.estimate_hours,
            "due": timeutil.format_date(self.due) if self.due else None,
            "created": timeutil.format_timestamp(self.created),
            "updated": timeutil.format_timestamp(self.updated),
            "notes": [note.to_dict() for note in self.notes],
        }

    @classmethod
    def from_dict(cls, data):
        """Build a work order from a format-1 record, applying the defaults
        documented in README.md for keys that older files may lack."""
        created = timeutil.parse_timestamp(data["created"])
        updated = data.get("updated")
        due = data.get("due")
        estimate = data.get("estimate_hours")
        return cls(
            id=int(data["id"]),
            title=str(data["title"]),
            created=created,
            updated=timeutil.parse_timestamp(updated) if updated else created,
            priority=data.get("priority") or "normal",
            status=data.get("status") or "open",
            asset=data.get("asset") or "",
            assignee=data.get("assignee") or "",
            tags=list(data.get("tags") or []),
            estimate_hours=float(estimate) if estimate is not None else None,
            due=timeutil.parse_date(due) if due else None,
            notes=[Note.from_dict(item) for item in data.get("notes") or []],
        )
