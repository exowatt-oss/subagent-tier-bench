"""Accounts, coupon definitions and manual adjustments."""

import csv
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .errors import InputError
from .money import parse_decimal, parse_money
from .timeutil import parse_date, parse_offset

REQUIRED_ACCOUNT_COLUMNS = ("account_id", "name", "plan")
_TRUE = frozenset({"yes", "true", "1"})
_FALSE = frozenset({"no", "false", "0", ""})


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str
    plan_id: str
    utc_offset: int = 0
    region: str = ""
    tax_exempt: bool = False
    coupons: tuple = ()
    start_date: Optional[date] = None


@dataclass(frozen=True)
class Coupon:
    code: str
    kind: str
    value: Decimal


@dataclass(frozen=True)
class Adjustment:
    account_id: str
    description: str
    amount: Decimal


def parse_flag(raw, what="flag"):
    value = (raw or "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise InputError("invalid %s %r (use yes/no, true/false or 1/0)" % (what, raw))


def parse_coupon_codes(raw):
    """``"welcome10; SAVE20"`` -> ``("WELCOME10", "SAVE20")`` (order kept)."""
    codes = []
    for part in (raw or "").split(";"):
        code = part.strip().upper()
        if code:
            codes.append(code)
    return tuple(codes)


def _cell(row, name):
    return (row.get(name) or "").strip()


def load_accounts(path):
    """Read accounts.csv into a dict keyed by account id, sorted by id."""
    path = Path(path)
    if not path.is_file():
        raise InputError("accounts file not found: %s" % path)
    accounts = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = {name.strip() for name in (reader.fieldnames or []) if name}
        missing = [name for name in REQUIRED_ACCOUNT_COLUMNS if name not in columns]
        if missing:
            raise InputError("%s: missing column(s): %s" % (path.name, ", ".join(missing)))
        for row in reader:
            row = {key.strip(): value for key, value in row.items() if key}
            where = "%s:%d" % (path.name, reader.line_num)
            account_id = _cell(row, "account_id")
            if not account_id:
                if all(not (value or "").strip() for value in row.values()):
                    continue
                raise InputError("%s: empty account_id" % where)
            if account_id in accounts:
                raise InputError("%s: duplicate account %r" % (where, account_id))
            plan_id = _cell(row, "plan")
            if not plan_id:
                raise InputError("%s: account %r has no plan" % (where, account_id))
            offset_text = _cell(row, "utc_offset")
            try:
                offset = parse_offset(offset_text) if offset_text else 0
                tax_exempt = parse_flag(row.get("tax_exempt"), "tax_exempt")
                start_text = _cell(row, "start_date")
                start = parse_date(start_text, "start_date") if start_text else None
            except InputError as exc:
                raise InputError("%s: %s" % (where, exc)) from None
            accounts[account_id] = Account(
                account_id=account_id,
                name=_cell(row, "name") or account_id,
                plan_id=plan_id,
                utc_offset=offset,
                region=_cell(row, "region").upper(),
                tax_exempt=tax_exempt,
                coupons=parse_coupon_codes(row.get("coupons")),
                start_date=start,
            )
    return {key: accounts[key] for key in sorted(accounts)}


def parse_coupon(data, where="coupon"):
    if not isinstance(data, dict):
        raise InputError("%s: expected an object" % where)
    code = str(data.get("code") or "").strip().upper()
    if not code:
        raise InputError("%s: missing code" % where)
    kind = data.get("type")
    if kind == "percent":
        value = parse_decimal(data.get("value"), "%s value" % code)
        if not Decimal(0) < value <= Decimal(100):
            raise InputError("coupon %s: percent must be in (0, 100]" % code)
    elif kind == "fixed":
        value = parse_money(data.get("value"), "%s value" % code)
        if value <= 0:
            raise InputError("coupon %s: amount must be positive" % code)
    else:
        raise InputError("coupon %s: type must be 'percent' or 'fixed'" % code)
    return Coupon(code=code, kind=kind, value=value)


def load_coupons(path):
    """Read coupons.json into a dict keyed by upper-case code."""
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle, parse_float=Decimal)
    except FileNotFoundError:
        raise InputError("coupons file not found: %s" % path) from None
    except ValueError as exc:
        raise InputError("%s: invalid JSON (%s)" % (path.name, exc)) from None
    items = data.get("coupons") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise InputError("%s: expected {\"coupons\": [...]}" % path.name)
    coupons = {}
    for index, item in enumerate(items):
        coupon = parse_coupon(item, "%s: coupons[%d]" % (path.name, index))
        if coupon.code in coupons:
            raise InputError("%s: duplicate coupon %s" % (path.name, coupon.code))
        coupons[coupon.code] = coupon
    return coupons


def load_adjustments(path):
    """Read adjustments.csv into ``{account_id: [Adjustment, ...]}`` (file order)."""
    path = Path(path)
    if not path.is_file():
        raise InputError("adjustments file not found: %s" % path)
    result = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = {name.strip() for name in (reader.fieldnames or []) if name}
        for name in ("account_id", "description", "amount"):
            if name not in columns:
                raise InputError("%s: missing column %s" % (path.name, name))
        for row in reader:
            row = {key.strip(): value for key, value in row.items() if key}
            if all(not (value or "").strip() for value in row.values()):
                continue
            where = "%s:%d" % (path.name, reader.line_num)
            account_id = _cell(row, "account_id")
            description = _cell(row, "description")
            if not account_id or not description:
                raise InputError("%s: account_id and description are required" % where)
            try:
                amount = parse_money(row.get("amount"), "amount", allow_negative=True)
            except InputError as exc:
                raise InputError("%s: %s" % (where, exc)) from None
            result.setdefault(account_id, []).append(
                Adjustment(account_id=account_id, description=description, amount=amount)
            )
    return result
