"""Loading a data directory and running the billing pipeline over it."""

from pathlib import Path

from .accounts import load_accounts, load_adjustments, load_coupons
from .catalog import PriceBook
from .errors import InputError
from .invoice import build_invoice, is_billable, usage_entries
from .tax import TaxTable

PLANS_FILE = "plans.json"
ACCOUNTS_FILE = "accounts.csv"
COUPONS_FILE = "coupons.json"
TAX_FILE = "tax.json"


class Workspace:
    """Everything needed to bill: plans, accounts, coupons, tax rates, adjustments."""

    def __init__(self, book, accounts, coupons=None, tax_table=None, adjustments=None):
        self.book = book
        self.accounts = dict(accounts)
        self.coupons = dict(coupons or {})
        self.tax_table = tax_table or TaxTable()
        self.adjustments = dict(adjustments or {})

    @classmethod
    def load(cls, data_dir, price_overrides=None, adjustments=None):
        data_dir = Path(data_dir)
        if not data_dir.is_dir():
            raise InputError("data directory not found: %s" % data_dir)
        book = PriceBook.load(data_dir / PLANS_FILE)
        book.validate()
        accounts = load_accounts(data_dir / ACCOUNTS_FILE)
        coupons = load_coupons(data_dir / COUPONS_FILE) if (data_dir / COUPONS_FILE).exists() else {}
        tax_table = TaxTable.load(data_dir / TAX_FILE) if (data_dir / TAX_FILE).exists() else TaxTable()
        for account in accounts.values():
            if account.plan_id not in book:
                raise InputError("account %s: unknown plan %r" % (account.account_id, account.plan_id))
            for code in account.coupons:
                if code not in coupons:
                    raise InputError("account %s: unknown coupon %s" % (account.account_id, code))
        if price_overrides:
            book.apply_overrides(price_overrides)
        adjustment_map = load_adjustments(adjustments) if adjustments else {}
        for account_id in adjustment_map:
            if account_id not in accounts:
                raise InputError("adjustments: unknown account %r" % account_id)
        return cls(book, accounts, coupons, tax_table, adjustment_map)

    def select(self, account_ids=None):
        """Accounts in account-id order; ``account_ids`` restricts the selection."""
        if not account_ids:
            return [self.accounts[key] for key in sorted(self.accounts)]
        unknown = [key for key in account_ids if key not in self.accounts]
        if unknown:
            raise InputError("unknown account(s): %s" % ", ".join(unknown))
        return [self.accounts[key] for key in sorted(set(account_ids))]

    def invoices(self, period, events, account_ids=None):
        """Invoices of the selected accounts that are billable in ``period``."""
        events = list(events)
        result = []
        for account in self.select(account_ids):
            invoice = build_invoice(
                account,
                self.book,
                period,
                events,
                coupons=self.coupons,
                tax_table=self.tax_table,
                adjustments=self.adjustments.get(account.account_id, ()),
            )
            if invoice is not None:
                result.append(invoice)
        return result

    def usage(self, period, events, account_ids=None):
        """Usage entries of the selected billable accounts, account by account."""
        events = list(events)
        entries = []
        for account in self.select(account_ids):
            if not is_billable(account, period):
                continue
            entries.extend(usage_entries(account, self.book.plan(account.plan_id), period, events))
        return entries
