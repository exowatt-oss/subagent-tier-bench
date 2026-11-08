"""Command-line interface: ``python3 -m wotrack COMMAND ...``.

Each sub-command has a ``cmd_*`` handler that receives the parsed arguments
and a :class:`Session` (the loaded data file plus the service operating on
it).  Handlers that change data mark the session dirty; ``main`` saves dirty
sessions once the handler has finished successfully.
"""

import argparse
import sys

from . import __version__, formatting, query, report, storage, timeutil
from .errors import WotrackError
from .service import UNSET, WorkOrderService


class Session:
    """The data file being worked on during one command."""

    def __init__(self, path):
        self.path = path
        self.db = storage.load(path)
        self.service = WorkOrderService(self.db)
        self.dirty = False

    def changed(self):
        self.dirty = True

    def save(self):
        storage.save(self.db, self.path)


def emit(text):
    print(text)


# ---------------------------------------------------------------------------
# Argument types
# ---------------------------------------------------------------------------


def order_id(text):
    """A work order id as typed on the command line: a positive integer."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid work order id: %r" % text) from None
    if value < 1:
        raise argparse.ArgumentTypeError("invalid work order id: %r" % text)
    return value


def positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("not a number: %r" % text) from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1: %r" % text)
    return value


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def cmd_add(args, session):
    order = session.service.create(
        args.title,
        asset=args.asset,
        priority=args.priority,
        assignee=args.assignee,
        tags=args.tags,
        hours=args.hours,
        due=args.due,
    )
    session.changed()
    emit("created %d: %s" % (order.id, order.title))


def cmd_list(args, session):
    flt = query.build_filter(
        statuses=args.status,
        show_all=args.all,
        priority=args.priority,
        min_priority=args.min_priority,
        assignee=args.assignee,
        tags=args.tags,
        text=args.text,
        overdue=args.overdue,
    )
    today = timeutil.today()
    orders = query.run_query(session.db.all(), flt, today, sort=args.sort, limit=args.limit)
    emit(formatting.render_order_list(orders, today))


def cmd_show(args, session):
    order = session.service.get(args.id)
    emit(formatting.render_order_detail(order, timeutil.today()))


def cmd_edit(args, session):
    order = session.service.update(
        args.id,
        title=args.title,
        asset=args.asset,
        priority=args.priority,
        assignee=args.assignee,
        hours=args.hours,
        due=args.due if args.due is not None else UNSET,
        add_tags=args.add_tags,
        remove_tags=args.remove_tags,
    )
    session.changed()
    emit("updated %d" % order.id)


def cmd_status(args, session):
    old, new = session.service.set_status(args.id, args.status)
    session.changed()
    emit("%d: %s -> %s" % (args.id, old, new))


def cmd_close(args, session):
    old, new = session.service.set_status(args.id, "done")
    session.changed()
    emit("%d: %s -> %s" % (args.id, old, new))


def cmd_assign(args, session):
    order = session.service.assign(args.id, args.name)
    session.changed()
    if order.assignee:
        emit("%d assigned to %s" % (order.id, order.assignee))
    else:
        emit("%d unassigned" % order.id)


def cmd_note(args, session):
    session.service.add_note(args.id, args.text)
    session.changed()
    emit("note added to %d" % args.id)


def cmd_delete(args, session):
    order = session.service.delete(args.id)
    session.changed()
    emit("deleted %d: %s" % (order.id, order.title))


def cmd_report(args, session):
    summary = report.summarize(session.db.all(), timeutil.today())
    emit(report.render_summary(summary))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wotrack", description="Track maintenance work orders in a JSON file."
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="data file (default: $WOTRACK_FILE or %s)" % storage.DEFAULT_FILE,
    )
    parser.add_argument("--version", action="version", version="wotrack " + __version__)
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.required = True

    p = commands.add_parser("add", help="create a work order")
    p.add_argument("title")
    p.add_argument("--asset", default="")
    p.add_argument("--priority", default="normal")
    p.add_argument("--assignee", default="")
    p.add_argument("--tag", dest="tags", action="append", default=[], metavar="TAG")
    p.add_argument("--hours", metavar="H", help="estimated effort in hours")
    p.add_argument("--due", metavar="YYYY-MM-DD")
    p.set_defaults(handler=cmd_add)

    p = commands.add_parser("list", help="list work orders")
    p.add_argument("--status", action="append", default=[], metavar="STATUS")
    p.add_argument("--all", action="store_true", help="include done and cancelled")
    p.add_argument("--priority")
    p.add_argument("--min-priority", dest="min_priority")
    p.add_argument("--assignee", help="exact name, or - for unassigned")
    p.add_argument("--tag", dest="tags", action="append", default=[], metavar="TAG")
    p.add_argument("--text")
    p.add_argument("--overdue", action="store_true")
    p.add_argument("--sort", choices=query.SORT_KEYS, default="id")
    p.add_argument("--limit", type=positive_int)
    p.set_defaults(handler=cmd_list)

    p = commands.add_parser("show", help="show one work order")
    p.add_argument("id", type=order_id)
    p.set_defaults(handler=cmd_show)

    p = commands.add_parser("edit", help="change fields of a work order")
    p.add_argument("id", type=order_id)
    p.add_argument("--title")
    p.add_argument("--asset")
    p.add_argument("--priority")
    p.add_argument("--assignee")
    p.add_argument("--hours", metavar="H")
    p.add_argument("--due", metavar="YYYY-MM-DD|none")
    p.add_argument("--add-tag", dest="add_tags", action="append", default=[], metavar="TAG")
    p.add_argument(
        "--remove-tag", dest="remove_tags", action="append", default=[], metavar="TAG"
    )
    p.set_defaults(handler=cmd_edit)

    p = commands.add_parser("status", help="change the status of a work order")
    p.add_argument("id", type=order_id)
    p.add_argument("status")
    p.set_defaults(handler=cmd_status)

    p = commands.add_parser("close", help="mark a work order done")
    p.add_argument("id", type=order_id)
    p.set_defaults(handler=cmd_close)

    p = commands.add_parser("assign", help="assign a work order (- to unassign)")
    p.add_argument("id", type=order_id)
    p.add_argument("name")
    p.set_defaults(handler=cmd_assign)

    p = commands.add_parser("note", help="append a note to a work order")
    p.add_argument("id", type=order_id)
    p.add_argument("text")
    p.set_defaults(handler=cmd_note)

    p = commands.add_parser("delete", help="delete a work order")
    p.add_argument("id", type=order_id)
    p.set_defaults(handler=cmd_delete)

    p = commands.add_parser("report", help="summary counts")
    p.set_defaults(handler=cmd_report)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        session = Session(storage.resolve_path(args.file))
        args.handler(args, session)
        if session.dirty:
            session.save()
    except WotrackError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return exc.exit_code
    return 0
