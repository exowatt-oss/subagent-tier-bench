"""Command-line interface: ``python -m meterbill --data DIR <command> ...``."""

import argparse
import sys

from . import __version__, fmt, render
from .errors import InputError
from .events import load_events
from .summary import summarize, summary_csv, summary_text
from .timeutil import Period
from .workspace import Workspace


def build_parser():
    parser = argparse.ArgumentParser(prog="meterbill", description="Usage-based billing engine.")
    parser.add_argument("--version", action="version", version="meterbill " + __version__)
    parser.add_argument("--data", required=True, metavar="DIR",
                        help="directory with plans.json, accounts.csv and optional coupons.json, tax.json")
    parser.add_argument("--price-overrides", metavar="FILE",
                        help="JSON file with plans that replace or extend plans.json")
    parser.add_argument("--adjustments", metavar="FILE",
                        help="CSV file with manual adjustment lines")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.required = True

    invoice = commands.add_parser("invoice", help="render invoices for one period")
    invoice.add_argument("--period", required=True, help="billing month, YYYY-MM")
    invoice.add_argument("--account", action="append", metavar="ID", help="only this account (repeatable)")
    invoice.add_argument("--format", choices=("text", "csv", "html", "json"), default="text")
    invoice.add_argument("events", nargs="*", help="usage event files (.csv, .jsonl)")

    summary = commands.add_parser("summary", help="rank accounts by invoice total")
    summary.add_argument("--period", required=True, help="billing month, YYYY-MM")
    summary.add_argument("--format", choices=("text", "csv"), default="text")
    summary.add_argument("events", nargs="*", help="usage event files (.csv, .jsonl)")

    usage = commands.add_parser("usage", help="list the rated usage events of one period")
    usage.add_argument("--period", required=True, help="billing month, YYYY-MM")
    usage.add_argument("--account", action="append", metavar="ID", help="only this account (repeatable)")
    usage.add_argument("events", nargs="*", help="usage event files (.csv, .jsonl)")

    commands.add_parser("plans", help="list plans and their prices")
    return parser


def _plans_text(book):
    out = []
    for plan_id in book.plan_ids():
        plan = book.plan(plan_id)
        out.append("%s: %s (base fee %s, minimum commit %s)" % (
            plan.plan_id, plan.name, fmt.plain_money(plan.base_fee), fmt.plain_money(plan.minimum_commit)))
        for metric in plan.metrics:
            out.append("  %s: %s [%s, per %s, %s included]" % (
                metric.metric, metric.label, metric.pricing, metric.unit, fmt.quantity(metric.included)))
            previous = None
            for up_to, unit_price in metric.tiers:
                if up_to is not None:
                    out.append("    up to %s: %s" % (fmt.quantity(up_to), fmt.quantity(unit_price)))
                    previous = up_to
                elif previous is None:
                    out.append("    all: %s" % fmt.quantity(unit_price))
                else:
                    out.append("    above %s: %s" % (fmt.quantity(previous), fmt.quantity(unit_price)))
    return "\n".join(out) + ("\n" if out else "")


def run(args):
    workspace = Workspace.load(args.data, price_overrides=args.price_overrides, adjustments=args.adjustments)
    if args.command == "plans":
        return _plans_text(workspace.book)
    period = Period.parse(args.period)
    events = load_events(args.events).events
    if args.command == "invoice":
        invoices = workspace.invoices(period, events, args.account)
        if args.format == "csv":
            return render.invoices_csv(invoices)
        if args.format == "html":
            return render.invoices_html(invoices, period)
        if args.format == "json":
            return render.invoices_json(invoices)
        return render.invoices_text(invoices)
    if args.command == "summary":
        rows = summarize(workspace.invoices(period, events))
        if args.format == "csv":
            return summary_csv(rows)
        return summary_text(rows, period)
    if args.command == "usage":
        return render.usage_csv(workspace.usage(period, events, args.account))
    raise InputError("unknown command %r" % args.command)


def _write(text):
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    stream.write(text)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        output = run(args)
    except InputError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    _write(output)
    return 0
