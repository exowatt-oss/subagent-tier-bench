"""The cross-account summary report."""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal

from . import fmt
from .money import ZERO


@dataclass(frozen=True)
class SummaryRow:
    rank: int
    account_id: str
    name: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal


def summarize(invoices):
    """One row per invoice, in ranking order (DESIGN.md, "Summary report")."""
    ordered = sorted(
        invoices, key=lambda invoice: (invoice.total, invoice.account.account_id), reverse=True
    )
    return [
        SummaryRow(
            rank=index + 1,
            account_id=invoice.account.account_id,
            name=invoice.account.name,
            subtotal=invoice.subtotal,
            discount=invoice.discount_total,
            tax=invoice.tax.amount,
            total=invoice.total,
        )
        for index, invoice in enumerate(ordered)
    ]


def grand_total(rows):
    return sum((row.total for row in rows), ZERO)


SUMMARY_COLUMNS = ("rank", "account_id", "name", "subtotal", "discount", "tax", "total")


def summary_csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(SUMMARY_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.rank,
                row.account_id,
                row.name,
                fmt.plain_money(row.subtotal),
                fmt.plain_money(row.discount),
                fmt.plain_money(row.tax),
                fmt.plain_money(row.total),
            ]
        )
    return buffer.getvalue()


def summary_text(rows, period):
    out = ["Summary %s" % period, "%4s  %-16s%-24s%14s" % ("#", "Account", "Name", "Total")]
    for row in rows:
        out.append("%4d  %-16s%-24s%14s" % (row.rank, row.account_id, row.name, fmt.money(row.total)))
    out.append("%4s  %-40s%14s" % ("", "Grand total", fmt.money(grand_total(rows))))
    return "\n".join(out) + "\n"
