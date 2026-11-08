# Open bug reports

Reports collected from billing operations, finance and two customers since release 1.4.
They describe what people saw; the guesses about causes are theirs. All commands run from
the project root against the bundled `examples/` data unless a report says otherwise.

---

## BUG-01: Batch invoice run puts other customers' notes on invoices

**Reported by:** billing operations

Running the monthly batch:

```
python3 -m meterbill --data examples/data invoice --period 2026-03 examples/usage-2026-03.csv
```

**Observed:** every invoice ends with the same two notes, for example Initech's:

```
Notes:
- Ignored 1 event(s) for metrics not in plan: gpu_hours
- Base fee prorated: 15 of 31 days
```

Initech has no gpu_hours usage and has been a customer since 2024. Rendering Initech alone
(`--account initech`) shows no notes at all.

**Expected:** only Acme's invoice mentions the ignored gpu_hours event and only Globex's
invoice (start date 2026-03-17) mentions proration. Looks like the text renderer prints
the notes of the whole batch under each invoice.

---

## BUG-02: Exactly 1000 GB of storage is billed at the cheaper rate

**Reported by:** finance

Pro storage is volume-priced: up to 1000 GB at 0.10, up to 5000 GB at 0.08, above that
0.06. `boundary.csv`:

```
event_id,account_id,metric,quantity,unit,timestamp
b-1,initech,storage,1000,GB,2026-03-10T00:00:00Z
```

```
python3 -m meterbill --data examples/data invoice --period 2026-03 --account initech boundary.csv
```

**Observed:** `Storage   1,000 GB   80.00`

**Expected:** `100.00`. 1000 GB is within the first tier.

---

## BUG-03: Usage listing changes the offset of timestamps we send

**Reported by:** Acme Corp (integration team)

Some of our collectors run in Newfoundland and stamp events in their local time.
`halfhour.csv`:

```
event_id,account_id,metric,quantity,unit,timestamp
n-1,acme,api_calls,250,call,2026-03-10T08:00:00-03:30
```

```
python3 -m meterbill --data examples/data usage --period 2026-03 --account acme halfhour.csv
```

**Observed:**

```
acme,n-1,api_calls,250,call,2026-03-10T08:00:00-04:30,2026-03-10T06:30:00-05:00
```

**Expected:** `received_at` should be the timestamp we sent, `2026-03-10T08:00:00-03:30`.
The `local_time` column looks right.

---

## BUG-04: Usage stamped at midnight lands on the next month's invoice

**Reported by:** Initech

Our nightly exporter writes the closing usage of a month with the timestamp of the
month's end. `midnight.csv`:

```
event_id,account_id,metric,quantity,unit,timestamp
m-1,initech,compute,10,hour,2026-04-01T00:00:00Z
```

**Observed:** the March invoice shows `Compute  0 hour  0.00`; the 10 hours appear on
the April invoice (`--period 2026-04`).

**Expected:** this is March usage and should be on the March invoice (Initech's offset
is `+00:00`).

---

## BUG-05: Storage from the JSON feed is rounded the wrong way

**Reported by:** finance

Globex's storage arrives through our JSON feed. `feed.jsonl`:

```
{"event_id": "fx-9", "account_id": "globex", "metric": "storage", "quantity": 10.02, "unit": "GB", "timestamp": "2026-03-20T12:00:00Z"}
```

```
python3 -m meterbill --data examples/data invoice --period 2026-03 --account globex --format csv feed.jsonl
```

**Observed:** the storage row amount is `2.50`.

**Expected:** 10.02 GB x 0.25 = 2.505, which rounds half up to `2.51`. The rating code
seems to use banker's rounding for storage.

---

## BUG-06: Special characters in names come out garbled in HTML invoices

**Reported by:** billing operations

We added an account `obrien` named `O'Brien <Ops> & Co` (CSV-quoted) to `accounts.csv`
and rendered its invoice with `--format html`.

**Observed:** the browser shows the heading as `Invoice obrien: O&#x27;Brien &lt;Ops&gt; & Co`.
Names with only `&` (like `Fish & Chips`) look fine.

**Expected:** `Invoice obrien: O'Brien <Ops> & Co`.

---

## BUG-07: The order of coupon codes changes the discount

**Reported by:** finance

Umbrella Health has two coupons. With `coupons` set to `SAVE20;WELCOME10` in
`examples/data/accounts.csv`:

```
python3 -m meterbill --data examples/data invoice --period 2026-03 --account umbrella examples/usage-2026-03.csv
```

**Observed:**

```
Subtotal                         581.00
Coupon SAVE20 (20.00 off)        -20.00
Coupon WELCOME10 (10% off)       -56.10
Total                            504.90
```

With `WELCOME10;SAVE20` the total is `502.90` (`-58.10`, then `-20.00`).

**Expected:** the order we type the codes in should not matter. Both spellings should
give `502.90`.

---

## BUG-08: Price overrides are only half applied

**Reported by:** billing operations

`overrides.json` is the Pro plan from `examples/data/plans.json` with `base_fee` raised
to `109.00` and the storage `up to 5000` tier raised from `0.08` to `0.09`.

```
python3 -m meterbill --data examples/data --price-overrides overrides.json invoice --period 2026-03 --account acme examples/usage-2026-03.csv
```

**Observed:** `Base fee 109.00` (new) but `Storage 1,250 GB 100.00`, which is still the
old 0.08. `meterbill ... --price-overrides overrides.json plans` lists
`up to 5000: 0.09`, so the file is read correctly.

**Expected:** `Storage 1,250 GB 112.50` and a total of `376.27`.

---

## BUG-09: Late-evening usage of our St. John's customer lands in the next month

**Reported by:** billing operations

Avalon Fisheries (`avalon`, `utc_offset` `-03:30`). `avalon.csv`:

```
event_id,account_id,metric,quantity,unit,timestamp
a-1,avalon,api_calls,30000,call,2026-04-01T02:45:00Z
```

That is 23:15 on 31 March in St. John's.

**Observed:** the March invoice shows `API calls  0 call  0.00`; the April invoice shows
`API calls  30,000 call  58.00`.

**Expected:** the usage belongs to March.

---

## BUG-10: MB are converted to GB with the wrong factor

**Reported by:** Globex GmbH

We report storage in MB. `mb.csv`:

```
event_id,account_id,metric,quantity,unit,timestamp
g-1,globex,storage,512000,MB,2026-03-20T12:00:00Z
```

**Observed:** `Storage  512 GB  128.00`.

**Expected:** 512000 MB is 500 GB, so `Storage  500 GB  125.00`.

---

## BUG-11: Tax is sometimes a cent short

**Reported by:** finance

```
python3 -m meterbill --data examples/data invoice --period 2026-03 --account initech examples/usage-2026-03.csv examples/feed-2026-03.jsonl
```

**Observed:**

```
Subtotal                         170.50
Tax (US 5%)                        8.52
Total                            179.02
```

**Expected:** 5 % of 170.50 is 8.525, so the tax should be `8.53` and the total
`179.03`.

---

## BUG-12: Summary order of accounts with the same total looks backwards

**Reported by:** finance

```
python3 -m meterbill --data examples/data summary --period 2026-03 examples/usage-2026-03.csv
```

**Observed:** the three accounts at 19.00 are listed `wayne`, `stark`, `avalon` (ranks
5, 6, 7).

**Expected:** `avalon`, `stark`, `wayne`. Our month-end reconciliation sheet relies on a
stable order.
