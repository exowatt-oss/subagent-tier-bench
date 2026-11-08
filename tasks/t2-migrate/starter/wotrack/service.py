"""Business operations on work orders.

The service owns every rule about *changing* data: validation, the status
workflow and timestamp bookkeeping.  It works on an in-memory
:class:`~wotrack.storage.Database`; saving is the caller's job.
"""

from . import models, timeutil
from .errors import ValidationError
from .models import Note, WorkOrder

#: Marker for "argument not given" where ``None`` is a meaningful value.
UNSET = object()


class WorkOrderService:
    def __init__(self, database, clock=timeutil.now):
        self.db = database
        self._clock = clock

    def _now(self):
        return self._clock()

    def get(self, order_id):
        return self.db.get(order_id)

    def create(
        self,
        title,
        asset="",
        priority="normal",
        assignee="",
        tags=(),
        hours=None,
        due=None,
    ):
        """Create, store and return a new open work order."""
        title = models.clean_title(title)
        priority = models.clean_priority(priority)
        clean_tags = []
        for raw in tags:
            tag = models.clean_tag(raw)
            if tag not in clean_tags:
                clean_tags.append(tag)
        estimate = models.clean_hours(hours) if hours is not None else None
        due_date = models.clean_due(due) if due is not None else None
        stamp = self._now()
        order = WorkOrder(
            id=self.db.allocate_id(),
            title=title,
            created=stamp,
            updated=stamp,
            priority=priority,
            asset=(asset or "").strip(),
            assignee=models.clean_person(assignee),
            tags=clean_tags,
            estimate_hours=estimate,
            due=due_date,
        )
        self.db.add(order)
        return order

    def update(
        self,
        order_id,
        title=None,
        asset=None,
        priority=None,
        assignee=None,
        hours=None,
        due=UNSET,
        add_tags=(),
        remove_tags=(),
    ):
        """Change several fields at once.  At least one change is required."""
        order = self.db.get(order_id)
        changes = {}
        if title is not None:
            changes["title"] = models.clean_title(title)
        if asset is not None:
            changes["asset"] = asset.strip()
        if priority is not None:
            changes["priority"] = models.clean_priority(priority)
        if assignee is not None:
            changes["assignee"] = models.clean_person(assignee)
        if hours is not None:
            changes["estimate_hours"] = models.clean_hours(hours)
        if due is not UNSET:
            changes["due"] = models.clean_due(due)
        added = [models.clean_tag(tag) for tag in add_tags]
        removed = [models.clean_tag(tag) for tag in remove_tags]
        if not changes and not added and not removed:
            raise ValidationError("nothing to change")
        for name, value in changes.items():
            setattr(order, name, value)
        for tag in added:
            order.add_tag(tag)
        for tag in removed:
            order.remove_tag(tag)
        self._touch(order)
        return order

    def set_status(self, order_id, status):
        """Move an order through the workflow; returns ``(old, new)``."""
        order = self.db.get(order_id)
        new_status = models.clean_status(status)
        order.check_transition(new_status)
        old_status = order.status
        order.status = new_status
        self._touch(order)
        return old_status, new_status

    def assign(self, order_id, assignee):
        """Assign an order; an empty name or ``-`` unassigns it."""
        order = self.db.get(order_id)
        name = models.clean_person(assignee)
        if name == "-":
            name = ""
        order.assignee = name
        self._touch(order)
        return order

    def add_note(self, order_id, text):
        order = self.db.get(order_id)
        note = Note(at=self._now(), text=models.clean_note_text(text))
        order.notes.append(note)
        self._touch(order)
        return note

    def delete(self, order_id):
        return self.db.remove(order_id)

    def _touch(self, order):
        order.updated = self._now()
