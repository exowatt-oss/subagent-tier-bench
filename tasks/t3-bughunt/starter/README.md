# meterbill

`meterbill` is a small usage-based billing engine. It reads price plans, customer
accounts, coupons, tax rates and metered usage events, rates one calendar month of usage
per account, and renders invoices (text, CSV, HTML, JSON), a ranked summary, and a usage
listing.

Standard library only; Python 3.9 or newer.

**DESIGN.md is the source of truth** for every rule: number handling and rounding, time
zones and billing periods, units, the input file formats, rating, invoice assembly and
the exact output formats. If this README and DESIGN.md ever disagree, DESIGN.md wins.

## Quick start

```bash
python3 -m meterbill --data examples/data invoice --period 2026-03 \
    examples/usage-2026-03.csv examples/feed-2026-03.jsonl
python3 -m meterbill --data examples/data summary --period 2026-03 examples/usage-2026-03.csv
python3 -m meterbill --data examples/data usage --period 2026-03 --account acme examples/usage-2026-03.csv
python3 -m meterbill --data examples/data plans
```

Global options go before the command:

| option | meaning |
|---|---|
| `--data DIR` | data directory: `plans.json`, `accounts.csv`, optional `coupons.json`, `tax.json` |
| `--price-overrides FILE` | JSON file of plans that replace or add plans from `plans.json` |
| `--adjustments FILE` | CSV file of manual adjustment lines (credits or charges) |

Commands:

| command | output |
|---|---|
| `invoice --period YYYY-MM [--account ID]... [--format text\|csv\|html\|json] EVENTS...` | invoices |
| `summary --period YYYY-MM [--format text\|csv] EVENTS...` | accounts ranked by invoice total |
| `usage --period YYYY-MM [--account ID]... EVENTS...` | CSV listing of the rated events |
| `plans` | plans and tier prices (after overrides) |

`EVENTS` are usage files ending in `.csv`, `.jsonl` or `.ndjson`. Invalid input prints
`error: <message>` on stderr and exits with status 2.

## Layout

```
meterbill/
  errors.py      InputError
  money.py       Decimal helpers, cent rounding
  timeutil.py    timestamps, UTC offsets, monthly periods          (ingest)
  units.py       units of measure and conversions                  (ingest)
  events.py      reading usage events, de-duplication               (ingest)
  accounts.py    accounts.csv, coupons.json, adjustments.csv        (ingest)
  catalog.py     plans.json, price overrides, the PriceBook         (ingest)
  rating.py      graduated and volume tier pricing                  (core)
  discounts.py   coupons                                            (core)
  tax.py         tax rates and tax calculation                      (core)
  invoice.py     assembling an invoice                              (core)
  workspace.py   loading a data directory, running the pipeline     (core)
  fmt.py         number, offset and timestamp formatting            (output)
  render.py      text, CSV, HTML, JSON invoices; usage listing      (output)
  summary.py     the summary report                                 (output)
  cli.py         the command-line interface                         (output)
examples/        a small data directory and two usage files
tests/           unit tests
```

## Tests

```bash
python3 -m unittest discover -s tests -t . -q
```
