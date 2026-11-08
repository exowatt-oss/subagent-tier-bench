"""Selecting and ordering work orders for ``list``."""

from dataclasses import dataclass
from typing import Optional, Tuple

from .errors import ValidationError
from .models import PRIORITY_RANK, clean_priority, clean_status

#: Sort keys accepted by ``list --sort``.
SORT_KEYS = ("id", "priority", "due")

#: Statuses ``list`` shows when no ``--status`` and no ``--all`` is given.
DEFAULT_STATUSES = ("open", "in_progress", "blocked")


@dataclass
class Filter:
    """Criteria an order must meet to be listed.  All criteria are ANDed."""

    statuses: Tuple[str, ...] = DEFAULT_STATUSES
    priority: Optional[str] = None
    min_priority: Optional[str] = None
    assignee: Optional[str] = None
    tags: Tuple[str, ...] = ()
    text: Optional[str] = None
    overdue: bool = False

    def matches(self, order, today):
        if self.statuses and order.status not in self.statuses:
            return False
        if self.priority is not None and order.priority != self.priority:
            return False
        if self.min_priority is not None:
            if PRIORITY_RANK[order.priority] < PRIORITY_RANK[self.min_priority]:
                return False
        if self.assignee is not None:
            if self.assignee == "-":
                if order.assignee:
                    return False
            elif order.assignee.lower() != self.assignee.lower():
                return False
        for tag in self.tags:
            if tag not in order.tags:
                return False
        if self.text is not None:
            needle = self.text.lower()
            if needle not in order.title.lower() and needle not in order.asset.lower():
                return False
        if self.overdue and not order.is_overdue(today):
            return False
        return True


def build_filter(
    statuses=(),
    show_all=False,
    priority=None,
    min_priority=None,
    assignee=None,
    tags=(),
    text=None,
    overdue=False,
):
    """Build a :class:`Filter` from raw command-line values."""
    if statuses:
        chosen = tuple(dict.fromkeys(clean_status(value) for value in statuses))
    elif show_all:
        chosen = ()
    else:
        chosen = DEFAULT_STATUSES
    return Filter(
        statuses=chosen,
        priority=clean_priority(priority) if priority is not None else None,
        min_priority=clean_priority(min_priority) if min_priority is not None else None,
        assignee=assignee.strip() if assignee is not None else None,
        tags=tuple(tags),
        text=text if text else None,
        overdue=overdue,
    )


def _sort_by_priority(orders):
    return sorted(orders, key=lambda order: (-PRIORITY_RANK[order.priority], order.id))


def _sort_by_due(orders):
    with_due = sorted((o for o in orders if o.due is not None), key=lambda o: (o.due, o.id))
    without_due = sorted((o for o in orders if o.due is None), key=lambda o: o.id)
    return with_due + without_due


def sort_orders(orders, key="id"):
    """Order work orders by one of :data:`SORT_KEYS`."""
    if key == "id":
        return sorted(orders, key=lambda order: order.id)
    if key == "priority":
        return _sort_by_priority(orders)
    if key == "due":
        return _sort_by_due(orders)
    raise ValidationError("unknown sort key: %s" % key)


def run_query(orders, flt, today, sort="id", limit=None):
    """Filter, sort and truncate ``orders``."""
    selected = [order for order in orders if flt.matches(order, today)]
    selected = sort_orders(selected, sort)
    if limit is not None:
        selected = selected[:limit]
    return selected
