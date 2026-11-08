# meterbill design

This document is the specification. Code, tests and bug reports are judged against it.

## 1. Pipeline

1. Load the data directory: plans (`plans.json`), accounts (`accounts.csv`), coupons
   (`coupons.json`, optional), tax rates (`tax.json`, optional). Validate every plan and
   every account reference. Then apply price overrides, if any, and load adjustments, if
   any.
2. Read usage event files in command-line order and drop repeated event ids.
3. For every selected account, in account-id order: pick its events that fall inside the
   billing period (in the account's local time), total them per metric, rate them, and
   assemble the invoice (fees, usage, adjustments, coupons, tax).
4. Render the invoices, the summary or the usage listing.

## 2. Numbers and money

- Every quantity, price, rate and amount is a `decimal.Decimal`. Binary floats are never
  used, and a value read from a file is taken exactly as written.
- Money is rounded to whole cents with **ROUND_HALF_UP** (half away from zero):
  `0.125 -> 0.13`, `0.124 -> 0.12`, `-0.125 -> -0.13`. There is no banker's rounding
  anywhere in meterbill.
- Rounding happens at these points and nowhere else:
  - money values read from files (base fee, minimum commitment, fixed coupon values,
    adjustment amounts) are rounded to cents when loaded;
  - each usage line amount, once, after its tier parts are added up;
  - the prorated base fee;
  - each percentage-coupon discount;
  - the tax amount.
  Subtotals and totals are sums of already-rounded amounts, so they are exact.
- Quantities and unit prices are never rounded. Unit prices may have any number of
  decimals (for example `0.0015`).

## 3. Time

### 3.1 Event timestamps

Event timestamps have the form `YYYY-MM-DDTHH:MM:SS`, optionally followed by `.fff` or
`.ffffff`, and then **must** end with a UTC designator: `Z` or `+HH:MM` / `-HH:MM`.
A timestamp without a designator, with a space instead of `T`, or without seconds is an
input error. The designator is part of the instant: `2026-03-31T23:15:00-03:30` is
`2026-04-01T02:45:00Z`.

### 3.2 Account offsets

Each account has one fixed UTC offset, written `+HH:MM` or `-HH:MM` (or `Z`), between
`-12:00` and `+14:00`. There is no daylight-saving time: the offset never changes.
Local time = UTC + offset, so an account at `-03:30` sees `2026-04-01T02:45:00Z` as
`2026-03-31 23:15`. Offsets are handled internally as signed minutes east of UTC:
`+05:30` is `330`, `-05:00` is `-300`, `-03:30` is `-210`, `-00:30` is `-30`.

### 3.3 Billing periods

A billing period is one calendar month, written `YYYY-MM`. For an account it is the
**half-open** interval

    [ local midnight starting the 1st of the month, local midnight starting the 1st of the next month )

in the account's local time. An event belongs to the period when its instant is inside
that interval. Consequences:

- An event at exactly the start (`2026-03-01T00:00:00` local) belongs to March.
- An event at exactly the end (`2026-04-01T00:00:00` local) belongs to **April**, not
  March. This is intended: the boundary instant always opens the next period. A job that
  stamps "end of March" usage at midnight must stamp it before midnight.
- `2026-03-31T23:59:59.999999` local belongs to March.
- Because the interval is in local time, the same UTC instant can fall into different
  months for accounts with different offsets.

The period's `first_day` and `last_day` are the local calendar dates of the 1st and of the
last day of the month; `days` is the number of days in the month (28-31).

## 4. Units

Each plan metric declares a canonical unit; events may report a compatible unit and are
converted exactly before rating. Units and families (names are case-sensitive):

| family | units |
|---|---|
| count | `call` = 1, `kcall` = 1000 calls |
| data | `KB` = 0.000001 GB, `MB` = 0.001 GB, `GB` = 1, `TB` = 1000 GB |
| time | `hour` |

Data units are **decimal (SI)**: 1 GB = 1000 MB and 1 TB = 1000 GB. Binary units
(1 GB = 1024 MB) are not supported, so `1536 MB` is `1.536 GB`, not `1.5 GB`. Converting
between different families (for example `MB` to `call`) is an input error naming the
event id; an unknown unit is an input error.

## 5. Input files

All text files are UTF-8. CSV files have a header row; column order is free, extra
columns are ignored, surrounding whitespace in cells is ignored, and completely empty
rows are skipped.

### 5.1 plans.json

```json
{"plans": [
  {"id": "pro", "name": "Pro", "base_fee": "99.00", "minimum_commit": "50.00",
   "metrics": [
     {"metric": "storage", "label": "Storage", "unit": "GB", "pricing": "volume",
      "included": "0",
      "tiers": [{"up_to": "1000", "unit_price": "0.10"},
                {"up_to": "5000", "unit_price": "0.08"},
                {"up_to": null,   "unit_price": "0.06"}]}
   ]}
]}
```

- `id` is required and unique. `name` defaults to the id. `base_fee` and
  `minimum_commit` default to `0`.
- Metrics are listed in invoice order; a plan may have no metrics (a flat fee).
  `metric` ids are unique within a plan; `label` defaults to the metric id; `pricing` is
  `graduated` (default) or `volume`; `included` (default `0`) is a free allowance in the
  canonical unit.
- `tiers` is a non-empty list. `up_to` values are positive, strictly increasing and
  **inclusive**; the last tier, and only the last tier, has `"up_to": null` (unbounded).
  `unit_price` must not be negative.
- Numbers may be JSON strings or JSON numbers; both are read exactly.

### 5.2 accounts.csv

Columns: `account_id`, `name`, `plan` (required), and optional `utc_offset`, `region`,
`tax_exempt`, `coupons`, `start_date`.

- `account_id` is unique. `name` defaults to the account id. `plan` must name a plan.
- `utc_offset`: see 3.2; empty means `+00:00`.
- `region`: a tax region such as `US-NY`, `US` or `DE`; case-insensitive (stored upper
  case); may be empty.
- `tax_exempt`: `yes`/`no`, `true`/`false` or `1`/`0` (case-insensitive); empty means
  `no`. Anything else is an input error.
- `coupons`: coupon codes separated by `;`, for example `WELCOME10;SAVE20`. Codes are
  case-insensitive (stored upper case); blanks are ignored; the listing order is kept.
  Every code must exist in `coupons.json`.
- `start_date`: `YYYY-MM-DD` in the account's local calendar, or empty (active since
  forever).

### 5.3 coupons.json

```json
{"coupons": [{"code": "WELCOME10", "type": "percent", "value": "10"},
             {"code": "SAVE20", "type": "fixed", "value": "20.00"}]}
```

`percent` values are in (0, 100]. `fixed` values are positive money amounts. Codes are
unique and case-insensitive.

### 5.4 tax.json

```json
{"rates": {"US-NY": "8.875", "US": "5", "DE": "19", "*": "0"}}
```

Rates are percentages between 0 and 100. Keys are case-insensitive.

### 5.5 Usage events

Six fields: `event_id`, `account_id`, `metric`, `quantity`, `unit`, `timestamp`.

- CSV (`.csv`): a header with those column names.
- JSON Lines (`.jsonl` or `.ndjson`): one JSON object per line; blank lines are skipped.
  `event_id`, `account_id`, `metric`, `unit` and `timestamp` are JSON strings.
  `quantity` is a JSON number or a string holding a decimal number. A JSON number is
  taken **exactly as written in the file**: `2.675` is exactly 2.675 and `0.1` is
  exactly one tenth, never a binary floating-point approximation.
- `quantity` must not be negative. `unit` must be a known unit (section 4).
- Any other file extension is an input error. Errors name the file and line.

Event ids are global. When the same `event_id` appears more than once (in one file or
across files), the **first** occurrence in reading order is kept and the later ones are
dropped, even if their contents differ. Events for unknown accounts are ignored.

### 5.6 adjustments.csv (`--adjustments`)

Columns `account_id`, `description`, `amount`. One manual line per row, for example a
credit (`-15.00`) or a one-off charge. Amounts may be negative and are rounded to cents.
Every `account_id` must be a known account.

### 5.7 Price overrides (`--price-overrides`)

Same shape as `plans.json`. Each plan in the file replaces the plan with the same id as a
whole (or adds a new plan). Overrides are applied after the base catalog and the accounts
have been loaded and validated, and before anything is rated. From that moment on the
overriding plan is the only version of that plan: its base fee, minimum commitment,
metrics, allowances and tier prices are what every invoice uses. The `plans` command
shows the plans with overrides applied.

## 6. Rating one metric

Let `Q` be the account's total quantity of the metric in the period (canonical unit) and
`I` the plan's `included` allowance. The billable quantity is `B = max(0, Q - I)`. The
allowance is always subtracted first, for both pricing models.

Tier `k` covers billable quantities in `(up_to[k-1], up_to[k]]` (with `up_to[0] = 0`).

- **graduated**: each part of `B` is priced at the unit price of the tier it falls in, and
  the parts are added. With tiers `1000 @ 0.10`, `5000 @ 0.08`, `rest @ 0.06` and
  `B = 1500`: `1000 x 0.10 + 500 x 0.08 = 140.00`.
- **volume**: all of `B` is priced at the unit price of the single tier that contains
  `B`. Because `up_to` is inclusive, `B = 1000` uses the first tier
  (`1000 x 0.10 = 100.00`), `B = 1000.001` uses the second tier, `B = 5000` uses the
  second tier and `B = 5000.5` uses the third.
- `B = 0` costs `0.00` in both models.

The line amount is rounded to cents once, after the parts are added.

## 7. Invoice assembly

An account gets an invoice for a period unless its `start_date` is after the period's
last day (then it is skipped). Accounts with no usage still get an invoice.

### 7.1 Lines, in this order

1. **Fee** section: one line `Base fee`. If `start_date` is after the period's first day,
   the fee is prorated: `active = last_day - start_date + 1` days (the start date counts),
   `fee = base_fee x active / days`, rounded to cents once, and the note
   `Base fee prorated: <active> of <days> days` is added. Usage is billed for the whole
   period regardless of `start_date`.
2. **Usage** section: one line per plan metric, in plan order, even with zero usage.
   Description = metric label, quantity = `Q` (before the allowance), unit = canonical
   unit, amount from section 6. Events of the account whose metric is not in the plan are
   ignored, and the note `Ignored <n> event(s) for metrics not in plan: <metrics>` is
   added (`<n>` counts the events, `<metrics>` are the distinct metric ids sorted and
   joined with `, `).
3. **Adjustment** section: first, if the plan's `minimum_commit` is greater than the sum
   of the usage line amounts, a line `Minimum commitment top-up` for the difference (the
   base fee and adjustments do not count towards the commitment, and the commitment is
   not prorated). Then the account's manual adjustments in file order.

`subtotal` = sum of all these line amounts.

### 7.2 Coupons

Coupons apply to the subtotal, producing discount lines (negative amounts):

- **Percentage coupons are applied first**, in the order the account lists them, and
  **fixed-amount coupons after all percentage coupons**, in the order the account lists
  them. Listing a fixed coupon before a percentage coupon in `accounts.csv` does not
  change this.
- A running amount starts at the subtotal. Each coupon works on the running amount left
  by the coupons before it: a percentage coupon takes `running x value / 100` rounded to
  cents; a fixed coupon takes `min(value, running)`. Two 10 % coupons on `100.00` give
  `10.00` and `9.00`.
- The running amount never goes below `0.00`. The unused part of a fixed coupon is lost:
  there is no carry-over to later months and no negative invoice from coupons.
- A coupon that would give `0.00` (because the running amount is already `0.00`, or the
  subtotal is zero or negative) produces no line.
- Descriptions: `Coupon WELCOME10 (10% off)` for percentages (the percentage in plain
  notation), `Coupon SAVE20 (20.00 off)` for fixed amounts.

`discount_total` = sum of the discounts (a positive amount); `taxable` = `subtotal -
discount_total`.

### 7.3 Tax

- A `tax_exempt` account gets the tax line `Tax (exempt)` with `0.00`.
- Otherwise the rate is looked up by the account's region: the exact region (`US-NY`),
  then its country part (`US`, the text before the first `-`), then `*`; if nothing
  matches the rate is 0. The tax line is `Tax (<key> <rate>%)`, for example
  `Tax (US-NY 8.875%)`, `Tax (DE 19%)` or `Tax (* 0%)`, with the rate in plain notation.
- `tax = taxable x rate / 100`, rounded half up to cents (`0.525 -> 0.53`). Tax is `0.00`
  when `taxable` is zero or negative.

`total` = `taxable + tax`.

### 7.4 Notes

Notes are invoice-specific remarks, in the order they are produced (proration first,
then ignored metrics). An invoice without either has no notes. Each invoice owns its
lines, discounts and notes: building one invoice never changes another invoice, whether
it is built alone or in a batch with other accounts.

## 8. Output formats

Money in text and HTML output uses thousands separators (`1,234.50`); money in CSV and
JSON output is plain (`1234.50`). Negative amounts have a leading `-`. Quantities in CSV
and JSON are in plain notation without trailing zeros (`2.675`, `1000`, `0.8`, `0`);
in text and HTML they also have thousands separators (`125,000`).

UTC offsets are always printed `+HH:MM` or `-HH:MM` with two-digit hours and minutes:
`330 -> +05:30`, `0 -> +00:00`, `-300 -> -05:00`, `-210 -> -03:30`, `-30 -> -00:30`.
Timestamps are printed `YYYY-MM-DDTHH:MM:SS+HH:MM` (fractional seconds dropped).

### 8.1 Text invoice

```
Invoice acme: Acme Corp
Plan: Pro (pro)
Period: 2026-03-01 to 2026-03-31 (UTC-05:00)

Base fee                                               99.00
API calls                           122,500 call      162.50
Storage                                 1,250 GB      100.00
Compute                                   0 hour        0.00
------------------------------------------------------------
Subtotal                                              361.50
Coupon WELCOME10 (10% off)                            -36.15
Tax (US-NY 8.875%)                                     28.87
Total                                                 354.22
Notes:
- Ignored 1 event(s) for metrics not in plan: gpu_hours
```

- The period line shows the local `first_day` and `last_day` and the account's offset.
- Each fee, usage and adjustment line is `description.ljust(28) + quantity.rjust(20) +
  amount.rjust(12)`, where quantity is `"<quantity> <unit>"` for usage lines and empty
  otherwise.
- Then 60 dashes, then `Subtotal`, the discount lines, the tax line and `Total`, each as
  `label.ljust(48) + amount.rjust(12)`.
- `Notes:` and one `- <note>` line per note follow only when there are notes.
- Several invoices are separated by one empty line.

### 8.2 CSV invoice export (`--format csv`)

Header `account_id,period,section,description,quantity,unit,amount`, then per invoice one
row per line (sections `fee`, `usage`, `adjustment`), one per discount (section
`discount`), one tax row (`tax`) and one total row (`total`, description `Total`).
Quantity and unit are empty except on usage rows. Standard CSV quoting (Python's `csv`
module defaults), `\n` line endings.

### 8.3 JSON invoice export (`--format json`)

A JSON array with one object per invoice:

```json
{"account_id": "acme", "name": "Acme Corp", "plan": "pro", "period": "2026-03",
 "utc_offset": "-05:00",
 "lines": [{"section": "fee", "description": "Base fee", "quantity": null, "unit": null,
            "amount": "99.00"}, ...],
 "subtotal": "361.50",
 "discounts": [{"code": "WELCOME10", "description": "Coupon WELCOME10 (10% off)",
                "amount": "-36.15"}],
 "discount_total": "36.15",
 "tax": {"description": "Tax (US-NY 8.875%)", "rate": "8.875", "amount": "28.87"},
 "total": "354.22",
 "notes": ["Ignored 1 event(s) for metrics not in plan: gpu_hours"]}
```

All amounts, quantities and rates are JSON **strings**, so no precision is lost in
consumers that parse JSON numbers as floats. `tax.rate` is `null` for exempt accounts.
The array is printed with `indent=2` and non-ASCII characters unescaped.

### 8.4 HTML invoice export (`--format html`)

One UTF-8 HTML document (`<title>Invoices <period></title>`) with one section per
invoice, shaped like this:

```html
<section class="invoice" id="invoice-acme">
<h1>Invoice acme: Acme Corp</h1>
<p class="plan">Plan: Pro (pro)</p>
<p class="period">Period: 2026-03-01 to 2026-03-31 (UTC-05:00)</p>
<table>
<tr><th>Description</th><th>Quantity</th><th>Amount</th></tr>
<tr class="fee"><td>Base fee</td><td></td><td>99.00</td></tr>
<tr class="usage"><td>API calls</td><td>122,500 call</td><td>162.50</td></tr>
<tr class="subtotal"><td>Subtotal</td><td></td><td>361.50</td></tr>
<tr class="discount"><td>Coupon WELCOME10 (10% off)</td><td></td><td>-36.15</td></tr>
<tr class="tax"><td>Tax (US-NY 8.875%)</td><td></td><td>28.87</td></tr>
<tr class="total"><td>Total</td><td></td><td>354.22</td></tr>
</table>
<ul class="notes">
<li>Ignored 1 event(s) for metrics not in plan: gpu_hours</li>
</ul>
</section>
```

One `<tr>` per fee, usage and adjustment line (`class` = its section), then the
subtotal, discount, tax and total rows. The `<ul class="notes">` appears only when there
are notes.

Every piece of text placed in the page (account ids and names, plan names, descriptions,
quantities, notes, the period) is escaped **exactly once**, exactly as Python's
`html.escape(text, quote=True)` does: `&` -> `&amp;`, `<` -> `&lt;`, `>` -> `&gt;`,
`"` -> `&quot;`, `'` -> `&#x27;`. A browser therefore shows the original text, for
example `O'Brien <Ops> & Co`.

### 8.5 Usage listing (`usage` command)

CSV with header `account_id,event_id,metric,quantity,unit,received_at,local_time`: one
row per de-duplicated event of the selected billable accounts that falls in the period
and whose metric is in the account's plan. Rows are grouped by account id (ascending);
within an account they are ordered by instant, then event id. `quantity` and `unit` are
converted to the metric's canonical unit. `received_at` is the event timestamp as sent
(same instant, same offset as in the input), `local_time` is the same instant at the
account's offset; both use the timestamp format above.

### 8.6 Summary report (`summary` command)

One row per invoice of the period (all accounts). Rows are ranked by `total`, **highest
first**; accounts with equal totals are ordered by account id, ascending (plain string
comparison). `rank` is the 1-based position in that order (no shared ranks).

- `--format csv`: header `rank,account_id,name,subtotal,discount,tax,total` with plain
  money (`discount` is the positive `discount_total`).
- `--format text` (default): the title `Summary <period>`, a header row, one row per
  account in rank order, and a `Grand total` row with the sum of the totals:

  ```
  Summary 2026-03
     #  Account         Name                             Total
     1  umbrella        Umbrella Health                 561.00
     2  acme            Acme Corp                       354.22
        Grand total                                     915.22
  ```

  Each account row is `str(rank).rjust(4) + "  " + account_id.ljust(16) +
  name.ljust(24) + total.rjust(14)` (total with thousands separators); the last row is
  `6 spaces + "Grand total".ljust(40) + sum.rjust(14)`.

### 8.7 Plans listing (`plans` command)

Plans in id order, with overrides applied, numbers in plain notation:

```
pro: Pro (base fee 99.00, minimum commit 50.00)
  storage: Storage [volume, per GB, 0 included]
    up to 1000: 0.1
    up to 5000: 0.08
    above 5000: 0.06
```

One `up to <up_to>: <unit_price>` line per bounded tier and `above <last up_to>:
<unit_price>` for the unbounded tier (`all: <unit_price>` when it is the only tier).

## 9. Python API

The modules can be used directly; the CLI is a thin layer over `Workspace`. Every
validation failure (bad file, bad value, unknown reference) raises
`meterbill.errors.InputError`. All money, quantity and rate values are `Decimal`.

- `meterbill.errors.InputError`
- `meterbill.money.round_money(amount)` -> Decimal rounded half up to cents.
- `meterbill.timeutil.parse_offset(text)` -> int minutes (`"-03:30"` -> `-210`);
  `parse_timestamp(text)` -> aware `datetime`; `Period(year, month)` /
  `Period.parse("2026-03")` with `first_day`, `last_day`, `days`,
  `start_utc(offset)`, `end_utc(offset)`, `contains(ts, offset)`; `str(period)` is
  `"2026-03"`.
- `meterbill.units.convert(quantity, from_unit, to_unit)` -> Decimal.
- `meterbill.events.UsageEvent(event_id, account_id, metric, quantity, unit, timestamp,
  source="")` (a frozen dataclass; `timestamp` is an aware `datetime`);
  `read_events(path)` -> list of `UsageEvent` in file order; `load_events(paths)` ->
  `EventLog` with `.events` (de-duplicated, reading order) and `.duplicates` (count).
- `meterbill.accounts.Account(account_id, name, plan_id, utc_offset=0, region="",
  tax_exempt=False, coupons=(), start_date=None)` (a frozen dataclass; `utc_offset` in
  minutes, `coupons` a tuple of upper-case codes, `start_date` a `date` or `None`);
  `load_accounts(path)` -> dict id -> `Account`, in account-id order.
  `Coupon(code, kind, value)` with `kind` `"percent"` or `"fixed"`;
  `load_coupons(path)` -> dict code -> `Coupon`. `Adjustment(account_id, description,
  amount)`; `load_adjustments(path)` -> dict id -> list of `Adjustment` in file order.
- `meterbill.catalog.Plan` has `plan_id`, `name`, `base_fee`, `minimum_commit`,
  `metrics` (tuple of `MetricPrice` in plan order) and `metric(metric_id)` ->
  `MetricPrice` or `None`; `MetricPrice` has `metric`, `label`, `unit`, `pricing`,
  `included`, `tiers`.
- `meterbill.catalog.PriceBook`: `PriceBook.load(path)`, `PriceBook.from_dict(data)`
  (`data` shaped like `plans.json`), `plan(plan_id)` -> `Plan`, `plan_ids()` (sorted),
  `tiers(plan_id, metric)` -> tuple of
  `(up_to, unit_price)` (`up_to` is `None` for the last tier), `validate()`,
  `update_plan(plan_or_dict)`, `apply_overrides(path)`. After `update_plan` or
  `apply_overrides`, every later `plan()` and `tiers()` call, and therefore all rating,
  reflects the new plan.
- `meterbill.rating.price(pricing, tiers, billable)` -> unrounded Decimal amount;
  `rate_metric(metric_price, tiers, quantity)` -> `RatedMetric` with the rounded
  `amount` and the `billable` quantity.
- `meterbill.discounts.apply_coupons(subtotal, coupons)` -> list of
  `(coupon, discount)` in application order (section 7.2).
- `meterbill.tax.TaxTable(rates)` / `TaxTable.from_dict(data)` / `TaxTable.load(path)`,
  `lookup(region)` -> `(key, rate)`; `compute_tax(taxable, rate)` -> Decimal.
- `meterbill.invoice.build_invoice(account, book, period, events, coupons=None,
  tax_table=None, adjustments=())` -> `Invoice` or `None`. `coupons` maps codes to
  `Coupon`s, `adjustments` is the account's list of `Adjustment`s; without a
  `tax_table` no region matches (rate 0). `Invoice(account, plan, period)` creates an
  empty invoice; an invoice has `lines` (fee, usage and adjustment lines in section 7.1
  order), `section(name)` (the lines of one section), `discounts` (lines with negative
  amounts), `tax` (a line), `tax_rate` (`None` when exempt), `notes` (list of strings),
  and the properties `subtotal`, `discount_total`, `taxable`, `total`. Each line has
  `section`, `description`, `amount`, `quantity` and `unit` (`None` except on usage
  lines) and `code`.
- `meterbill.workspace.Workspace(book, accounts, coupons=None, tax_table=None,
  adjustments=None)` (`accounts` is a dict id -> `Account`, `adjustments` a dict id ->
  list of `Adjustment`) or `Workspace.load(data_dir, price_overrides=None,
  adjustments=None)`; `invoices(period, events, account_ids=None)` -> invoices in
  account-id order; `usage(period, events, account_ids=None)` -> usage entries (each has
  `account`, `event`, `quantity`, `unit`) in the order of section 8.5.
- `meterbill.fmt.offset(minutes)`; `fmt.timestamp(ts)` prints `ts` at its own offset
  and `fmt.timestamp(ts, offset_minutes)` prints the same instant at the given offset
  (section 8); `fmt.money(amount)` (`1,234.50`), `fmt.plain_money(amount)` (`1234.50`),
  `fmt.quantity(q)` (`2.675`).
- `meterbill.render.invoice_text(invoice)`, `invoices_text(invoices)`,
  `invoices_csv(invoices)`, `invoices_json(invoices)`, `invoices_html(invoices, period)`,
  `usage_csv(entries)`.
- `meterbill.summary.summarize(invoices)` -> list of `SummaryRow` (`rank`,
  `account_id`, `name`, `subtotal`, `discount`, `tax`, `total`); `summary_csv(rows)`;
  `summary_text(rows, period)`.
- `meterbill.cli.main(argv)` -> exit status.
