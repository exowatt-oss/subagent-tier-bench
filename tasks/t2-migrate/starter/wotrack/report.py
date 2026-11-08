"""The ``report`` command: counts over all work orders."""

from dataclasses import dataclass, field
from typing import Dict

from .models import PRIORITIES, STATUSES


@dataclass
class Summary:
    total: int = 0
    by_status: Dict[str, int] = field(default_factory=lambda: {s: 0 for s in STATUSES})
    by_priority: Dict[str, int] = field(default_factory=lambda: {p: 0 for p in PRIORITIES})
    overdue: int = 0


def summarize(orders, today):
    """Count orders by status and priority, and how many are overdue."""
    summary = Summary()
    for order in orders:
        summary.total += 1
        summary.by_status[order.status] += 1
        summary.by_priority[order.priority] += 1
        if order.is_overdue(today):
            summary.overdue += 1
    return summary


def render_summary(summary):
    """Render a :class:`Summary` as the text ``report`` prints."""
    lines = ["Work orders: %d" % summary.total, "By status:"]
    for status in STATUSES:
        lines.append("  %-12s %d" % (status, summary.by_status[status]))
    lines.append("By priority:")
    for priority in reversed(PRIORITIES):
        lines.append("  %-7s %d" % (priority, summary.by_priority[priority]))
    lines.append("Overdue: %d" % summary.overdue)
    return "\n".join(lines)
