"""Human-readable output: the ``list`` table and the ``show`` detail view."""

from . import timeutil

#: Shown in place of an empty value.
EMPTY = "-"

#: Width of the label column in ``show`` output ("Assignee:" plus padding).
LABEL_WIDTH = 11

#: Columns of the ``list`` table.
LIST_HEADERS = ("ID", "PRIORITY", "STATUS", "DUE", "ASSIGNEE", "TITLE")


def render_table(headers, rows, right_align=()):
    """Render rows as an aligned plain-text table.

    Columns are separated by two spaces and are as wide as their widest cell
    (header included).  Columns whose index is in ``right_align`` are
    right-aligned, all others left-aligned.  Trailing spaces are stripped
    from every line.
    """
    table = [list(headers)] + [[str(cell) for cell in row] for row in rows]
    widths = [max(len(row[col]) for row in table) for col in range(len(headers))]
    lines = []
    for row in table:
        cells = []
        for col, cell in enumerate(row):
            if col in right_align:
                cells.append(cell.rjust(widths[col]))
            else:
                cells.append(cell.ljust(widths[col]))
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def or_empty(value):
    return value if value else EMPTY


def due_cell(order, today):
    """The DUE cell: the date, with ``!`` appended when the order is overdue."""
    if order.due is None:
        return EMPTY
    text = timeutil.format_date(order.due)
    if order.is_overdue(today):
        text += "!"
    return text


def list_row(order, today):
    return [
        str(order.id),
        order.priority,
        order.status,
        due_cell(order, today),
        or_empty(order.assignee),
        order.title,
    ]


def render_order_list(orders, today):
    """The ``list`` output for already filtered and sorted orders."""
    if not orders:
        return "no work orders"
    rows = [list_row(order, today) for order in orders]
    return render_table(LIST_HEADERS, rows, right_align={0})


def _line(label, value):
    return ("%s:" % label).ljust(LABEL_WIDTH) + value


def render_order_detail(order, today):
    """The ``show`` output for one order."""
    due = EMPTY
    if order.due is not None:
        due = timeutil.format_date(order.due)
        if order.is_overdue(today):
            due += " (overdue)"
    estimate = EMPTY
    if order.estimate_hours is not None:
        estimate = timeutil.format_hours(order.estimate_hours)
    lines = [
        "Work order %d" % order.id,
        _line("Title", order.title),
        _line("Asset", or_empty(order.asset)),
        _line("Priority", order.priority),
        _line("Status", order.status),
        _line("Assignee", or_empty(order.assignee)),
        _line("Tags", ", ".join(order.tags) if order.tags else EMPTY),
        _line("Estimate", estimate),
        _line("Due", due),
        _line("Created", timeutil.format_timestamp(order.created)),
        _line("Updated", timeutil.format_timestamp(order.updated)),
    ]
    if order.notes:
        lines.append("Notes:")
        for note in order.notes:
            lines.append("  [%s] %s" % (timeutil.format_timestamp(note.at), note.text))
    else:
        lines.append(_line("Notes", EMPTY))
    return "\n".join(lines)
