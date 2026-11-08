"""Rendering invoices and usage listings as text, CSV, HTML and JSON."""

import csv
import io
import json

from . import fmt
from .money import plain

TEXT_WIDTH = 60
_DESC_WIDTH = 28
_QTY_WIDTH = 20
_AMOUNT_WIDTH = 12

_HTML_ESCAPES = (
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#x27;"),
    ("&", "&amp;"),
)


def _esc(text):
    text = str(text)
    for char, entity in _HTML_ESCAPES:
        text = text.replace(char, entity)
    return text


def _period_text(invoice):
    period = invoice.period
    return "%s to %s (UTC%s)" % (
        period.first_day.isoformat(),
        period.last_day.isoformat(),
        fmt.offset(invoice.account.utc_offset),
    )


def _quantity_cell(line):
    if line.quantity is None:
        return ""
    return "%s %s" % (fmt.quantity_text(line.quantity), line.unit)


# -- text -------------------------------------------------------------------


def _row(description, quantity, amount):
    return "%s%s%s" % (
        description.ljust(_DESC_WIDTH),
        quantity.rjust(_QTY_WIDTH),
        fmt.money(amount).rjust(_AMOUNT_WIDTH),
    )


def _total_row(label, amount):
    return "%s%s" % (label.ljust(_DESC_WIDTH + _QTY_WIDTH), fmt.money(amount).rjust(_AMOUNT_WIDTH))


def invoice_text(invoice):
    account = invoice.account
    out = [
        "Invoice %s: %s" % (account.account_id, account.name),
        "Plan: %s (%s)" % (invoice.plan.name, invoice.plan.plan_id),
        "Period: %s" % _period_text(invoice),
        "",
    ]
    for line in invoice.lines:
        out.append(_row(line.description, _quantity_cell(line), line.amount))
    out.append("-" * TEXT_WIDTH)
    out.append(_total_row("Subtotal", invoice.subtotal))
    for line in invoice.discounts:
        out.append(_total_row(line.description, line.amount))
    out.append(_total_row(invoice.tax.description, invoice.tax.amount))
    out.append(_total_row("Total", invoice.total))
    if invoice.notes:
        out.append("Notes:")
        out.extend("- %s" % note for note in invoice.notes)
    return "\n".join(out) + "\n"


def invoices_text(invoices):
    return "\n".join(invoice_text(invoice) for invoice in invoices)


# -- CSV --------------------------------------------------------------------

CSV_COLUMNS = ("account_id", "period", "section", "description", "quantity", "unit", "amount")


def invoices_csv(invoices):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for invoice in invoices:
        head = [invoice.account.account_id, str(invoice.period)]
        for line in invoice.lines:
            quantity = "" if line.quantity is None else fmt.quantity(line.quantity)
            writer.writerow(
                head + [line.section, line.description, quantity, line.unit or "",
                        fmt.plain_money(line.amount)]
            )
        for line in invoice.discounts:
            writer.writerow(head + ["discount", line.description, "", "", fmt.plain_money(line.amount)])
        writer.writerow(head + ["tax", invoice.tax.description, "", "", fmt.plain_money(invoice.tax.amount)])
        writer.writerow(head + ["total", "Total", "", "", fmt.plain_money(invoice.total)])
    return buffer.getvalue()


# -- JSON -------------------------------------------------------------------


def invoice_dict(invoice):
    account = invoice.account
    return {
        "account_id": account.account_id,
        "name": account.name,
        "plan": invoice.plan.plan_id,
        "period": str(invoice.period),
        "utc_offset": fmt.offset(account.utc_offset),
        "lines": [
            {
                "section": line.section,
                "description": line.description,
                "quantity": None if line.quantity is None else fmt.quantity(line.quantity),
                "unit": line.unit,
                "amount": fmt.plain_money(line.amount),
            }
            for line in invoice.lines
        ],
        "subtotal": fmt.plain_money(invoice.subtotal),
        "discounts": [
            {"code": line.code, "description": line.description, "amount": fmt.plain_money(line.amount)}
            for line in invoice.discounts
        ],
        "discount_total": fmt.plain_money(invoice.discount_total),
        "tax": {
            "description": invoice.tax.description,
            "rate": None if invoice.tax_rate is None else plain(invoice.tax_rate),
            "amount": fmt.plain_money(invoice.tax.amount),
        },
        "total": fmt.plain_money(invoice.total),
        "notes": list(invoice.notes),
    }


def invoices_json(invoices):
    return json.dumps([invoice_dict(invoice) for invoice in invoices], indent=2, ensure_ascii=False) + "\n"


# -- HTML -------------------------------------------------------------------


def _html_row(css, description, quantity, amount):
    return '<tr class="%s"><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        css,
        _esc(description),
        _esc(quantity),
        fmt.money(amount),
    )


def _html_invoice(invoice):
    account = invoice.account
    out = [
        '<section class="invoice" id="invoice-%s">' % _esc(account.account_id),
        "<h1>Invoice %s: %s</h1>" % (_esc(account.account_id), _esc(account.name)),
        '<p class="plan">Plan: %s (%s)</p>' % (_esc(invoice.plan.name), _esc(invoice.plan.plan_id)),
        '<p class="period">Period: %s</p>' % _esc(_period_text(invoice)),
        "<table>",
        "<tr><th>Description</th><th>Quantity</th><th>Amount</th></tr>",
    ]
    for line in invoice.lines:
        out.append(_html_row(line.section, line.description, _quantity_cell(line), line.amount))
    out.append(_html_row("subtotal", "Subtotal", "", invoice.subtotal))
    for line in invoice.discounts:
        out.append(_html_row("discount", line.description, "", line.amount))
    out.append(_html_row("tax", invoice.tax.description, "", invoice.tax.amount))
    out.append(_html_row("total", "Total", "", invoice.total))
    out.append("</table>")
    if invoice.notes:
        out.append('<ul class="notes">')
        out.extend("<li>%s</li>" % _esc(note) for note in invoice.notes)
        out.append("</ul>")
    out.append("</section>")
    return out


def invoices_html(invoices, period):
    out = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Invoices %s</title>" % _esc(period),
        "</head>",
        "<body>",
    ]
    for invoice in invoices:
        out.extend(_html_invoice(invoice))
    out.extend(["</body>", "</html>"])
    return "\n".join(out) + "\n"


# -- usage listing ----------------------------------------------------------

USAGE_COLUMNS = ("account_id", "event_id", "metric", "quantity", "unit", "received_at", "local_time")


def usage_csv(entries):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(USAGE_COLUMNS)
    for entry in entries:
        event = entry.event
        writer.writerow(
            [
                entry.account.account_id,
                event.event_id,
                event.metric,
                fmt.quantity(entry.quantity),
                entry.unit,
                fmt.timestamp(event.timestamp),
                fmt.timestamp(event.timestamp, entry.account.utc_offset),
            ]
        )
    return buffer.getvalue()
