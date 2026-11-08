# RFC 0007 — Projects, string work-order ids and data format 2

Status: **accepted** · Target: wotrack 2.0 · Applies on top of README.md (wotrack 1.4)

## 0. Summary and conventions

Several teams now share one data file. wotrack 2.0 therefore (A) gives work
orders prefixed string ids, (B) puts every work order into a **project**,
(C) moves the data file to **format 2** and migrates format-1 files
automatically, (D) extends `list` and `report`, and (E) adds `--json` output,
deprecations and distinct exit codes. Everything README.md describes that this
RFC does not change must keep working exactly as before (the status workflow,
`list` filters and their defaults, `--limit`, the `report` text, the table
layout rules, file selection, `WOTRACK_NOW`, `assign ID -`, `edit --due none`, …).

Terms used below:

* **active** order: status `open`, `in_progress` or `blocked` (the README's "not closed").
* **now** / **today**: as in README (system clock or `WOTRACK_NOW`; UTC).
* `<path>`: the data file path exactly as selected (the `--file` value, else
  `WOTRACK_FILE`, else `workorders.json`) — used as given, not made absolute.
* **exit N**: the process exit status, see E.4.
* Messages shown as `error: …` / `warning: …` / `note: …` go to **stderr**; all
  other output goes to stdout.

## Part A — Work-order ids

**A.1 Numbers.** Every order still has a positive integer **number** taken from
one file-wide counter (format 1 `next_id`, format 2 `next_number`). Numbering is
*not* per project, and numbers are never reused, even after `delete`.

**A.2 Canonical id.** `WO-` followed by the number zero-padded to at least five
digits: 7 → `WO-00007`, 12345 → `WO-12345`, 123456 → `WO-123456`.

**A.3 Id references.** Every command argument that names a work order accepts,
after stripping surrounding whitespace, either `WO-` in any letter case followed
by one or more digits (`WO-00007`, `wo-7`, `Wo-007`), or digits only — a
**legacy** 1.x id (`7`, `007`). Leading zeros are allowed. The number must be
at least 1. Anything else (`X-7`, `WO-`, `WO-7a`, `WO7`, `-7`, `0`, `WO-00000`)
is exit 2 with `error: invalid work order id: <argument as typed>`.

**A.4 Ids in output.** Every message, table cell and JSON value that shows a
work order shows its canonical id — error messages included:
`show 9` without such an order prints `error: no such work order: WO-00009` (exit 1).
Changed messages (wording otherwise unchanged):

| Command | 1.x | 2.0 |
| --- | --- | --- |
| `add` | `created 7: TITLE` | `created WO-00007 in GEN: TITLE` (the order's project key) |
| `edit` | `updated 7` | `updated WO-00007` |
| `status`, `close` | `7: open -> done` | `WO-00007: open -> done` |
| `assign` | `7 assigned to dana` / `7 unassigned` | `WO-00007 assigned to dana` / `WO-00007 unassigned` |
| `note` | `note added to 7` | `note added to WO-00007` |
| `delete` | `deleted 7: TITLE` | `deleted WO-00007: TITLE` |
| same-status error | `work order 3 is already open` | `work order WO-00003 is already open` |

## Part B — Projects

**B.1** A project has a **key**, a **name** and a `created_at` timestamp. Every
work order belongs to exactly one project.

**B.2 Keys** are 2–10 characters: uppercase letters `A`–`Z` and digits, starting
with a letter. Keys given on the command line are trimmed and uppercased first
(`ops` → `OPS`). If the result is not a valid key: exit 3,
`error: invalid project key: <argument as typed>`. A valid key that names no
project: exit 1, `error: no such project: OPS`. A project's key never changes.

**B.3 Names** are trimmed and must then be 1–60 characters (exit 3:
`project name must not be empty` / `project name is longer than 60 characters`).

**B.4 Uniqueness** (exit 3): keys are unique (`project key already exists: OPS`);
names are unique ignoring letter case (`project name already in use: <name>`,
the requested name after trimming).
Renaming a project to another spelling of its own name (e.g. different case) is allowed.

**B.5 Default project.** Key `GEN`, name `General`. It always exists: a new data
file starts with it, and migration creates it (C.4). It cannot be removed
(exit 3, `cannot remove the default project GEN`). A missing data file behaves
like a new, empty file containing only `GEN` (its `created_at` is now);
read-only commands still never create the file.

**B.6 Title rule.** Within one project, no two **active** orders may have the
same title, comparing titles after trimming, collapsing every run of whitespace
to a single space, and ignoring letter case (`Replace  PUMP seal` equals
`replace pump seal`). Titles are still *stored* as typed (trimmed only). The
rule is checked whenever an order would become an active order with that title
in that project: `add`; `edit --title` of an active order (the order itself is
not compared with itself); `move` of an active order (against the target
project); and reopening, i.e. `status ID open` from `done` or `cancelled`.
Changes to closed orders are never refused by this rule, and migration does not
apply it (existing duplicates are kept). Violation: exit 3,
`error: an active work order in GEN already has this title: WO-00003` naming the
conflicting order (the lowest-numbered one if several conflict).

**B.7 `project` commands.**

| Command | Effect | Prints |
| --- | --- | --- |
| `project add KEY NAME` | create a project (`created_at` = now) | `created project OPS: Operations` |
| `project list [--json]` | list projects, ordered by key | table below |
| `project rename KEY NAME` | change the name | `renamed project OPS: Operations -> Field Ops` |
| `project remove KEY` | delete a project that has no orders | `removed project OPS` |

`project remove` of a project that still has orders (of any status) is exit 3,
`error: project OPS is not empty`. The `project list` table has the columns
`KEY NAME ACTIVE TOTAL` (active orders / all orders of the project); `ACTIVE`
and `TOTAL` are numeric columns in the sense of the README table layout:

```
KEY  NAME        ACTIVE  TOTAL
GEN  General          3      5
OPS  Operations       2      2
```

**B.8 `add --project KEY`.** Without `--project`, a new order goes to the project
named by the `WOTRACK_PROJECT` environment variable if it is set and non-empty,
otherwise to `GEN`. Both are checked as in B.2.

**B.9 `move ID KEY`** puts an order into another project and updates its
`updated_at`; prints `WO-00003: GEN -> OPS`. If the order is already in that
project nothing changes — the file is not written and `updated_at` is untouched —
and it prints `WO-00003 is already in OPS` (exit 0).

## Part C — Data format 2 and automatic migration

**C.1 Format 2.** wotrack 2.0 writes only format 2, serialised exactly like
format 1 (`json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)` plus a
newline, UTF-8, atomic replace). Example (`samples/plant.json` after migration,
first order only):

```json
{
  "format": 2,
  "next_number": 7,
  "orders": [
    {
      "asset": "PUMP-07",
      "assignee": "dana",
      "created_at": "2026-03-01T09:15:00Z",
      "due": "2026-03-05",
      "estimate_minutes": 150,
      "id": "WO-00001",
      "notes": [
        {"at": "2026-03-01T10:00:00Z", "text": "parts ordered"},
        {"at": "2026-03-02T08:00:00Z", "text": "seal arrived"}
      ],
      "priority": "high",
      "project": "GEN",
      "status": "in_progress",
      "tags": ["mechanical", "urgent"],
      "title": "Replace pump seal",
      "updated_at": "2026-03-02T08:00:00Z"
    }
  ],
  "projects": [
    {"created_at": "2026-02-20T13:00:00Z", "key": "GEN", "name": "General"}
  ],
  "site": "North Plant"
}
```

* Every order has all 13 keys shown. `asset`, `assignee`, `estimate_minutes`
  (integer minutes) and `due` are `null` when empty — never `""`.
* Every timestamp (`created_at`, `updated_at`, `notes[].at`, `projects[].created_at`)
  is UTC in exactly the form `YYYY-MM-DDTHH:MM:SSZ`.
* `tags` are lowercase, unique and sorted. Orders are sorted by number,
  projects by key, notes oldest first.
* **Unknown keys are preserved**: any key not listed above — at the top level,
  in an order or in a project — is kept unchanged through every later load and
  save (note objects keep only `at` and `text`).

**C.2 Reading.** A document with `"format": 2` is used as is. A document whose
`format` is `1` or absent is migrated (C.3). Any other value: exit 4,
`error: unsupported data format: 3`. Invalid JSON: exit 4,
`error: cannot read <path>: invalid JSON`. Other unreadable or malformed data: exit 4.

**C.3 Automatic migration.** When any command — read-only ones included — opens
a format-1 file, wotrack, before running the command itself:

1. converts the document as in C.4 (if that fails, e.g. on an unparseable
   timestamp: exit 4, and neither the backup nor the data file is written);
2. copies the original file byte for byte to `<path>.v1.bak`, unless that file
   already exists (an existing backup is never overwritten);
3. writes the converted document to `<path>`;
4. prints `note: migrated <path> from format 1 to format 2 (backup: <path>.v1.bak)`
   to stderr. Standard output is unaffected (so `list --json` stays parseable).

The command then runs normally; if it fails (say, an unknown id) the migrated
file and the backup stay in place. Opening a format-2 file never creates a
backup and never writes the file unless the command changes data, so running
any command again after a migration prints no note and leaves the file as is.

**C.4 Mapping.** Per order (defaults for missing keys as in README "Older files"):

| Format 1 | Format 2 |
| --- | --- |
| `id`: 7 | `id`: `"WO-00007"` |
| — | `project`: `"GEN"` |
| `title`, `priority`, `status`, `due` | same values (`due` `null` when missing) |
| `asset`, `assignee` | `null` when `""` or missing, otherwise unchanged |
| `tags` | lowercased, duplicates removed, sorted: `["Pump", "oil", "pump"]` → `["oil", "pump"]` |
| `estimate_hours`: H | `estimate_minutes`: floor(H × 60 + 0.5) — halves round **up** (0.375 h → 23, 2.5 h → 150); `null` stays `null` |
| `created` | `created_at`, normalised |
| `updated` (missing → `created`) | `updated_at`, normalised |
| `notes` | each `{"at": normalised, "text": …}`, then stable-sorted by time (oldest first) |
| any other key | copied unchanged (if it collides with a format-2 key, the format-2 value wins) |

At the top level: `format` becomes `2`; `next_id` becomes `next_number` =
max(`next_id` (1 when missing), highest order number + 1); `projects` becomes
one project `{"key": "GEN", "name": "General", "created_at": …}` whose
`created_at` is the earliest normalised `created_at` of all orders, or now if
there are no orders; every other top-level key is copied unchanged.

**Normalising** a timestamp means parsing it with the README *Timestamps* rules,
converting it to UTC, dropping any fraction of a second and writing it as
`YYYY-MM-DDTHH:MM:SSZ`:

| Format 1 value | Normalised |
| --- | --- |
| `2026-03-01 09:15:00` | `2026-03-01T09:15:00Z` |
| `2025-11-04T07:45` | `2025-11-04T07:45:00Z` |
| `2025-11-05 23:30:00-02:00` | `2025-11-06T01:30:00Z` |
| `2025-11-06T09:10:42.918Z` | `2025-11-06T09:10:42Z` |

**C.5 `migrate` command.** Opens the file like any command (so a format-1 file is
migrated as in C.3, note included) and then prints
`migrated <path> to format 2 (work orders: 6)` — or, if the file already was
format 2, `<path> is already format 2`. A missing file: exit 4,
`error: no such file: <path>`.

**C.6 New files.** The first command that changes data on a missing file creates
it in format 2 with project `GEN` (`created_at` = now); numbering starts at 1.

## Part D — Queries and reports

**D.1 `list --project KEY`** (repeatable) keeps orders in any of the given
projects; combined with the other filters by AND; keys checked as in B.2. The
`list` table gains a `PROJECT` column after `ID`; the `ID` column holds
canonical ids and is left-aligned (the table has no numeric columns any more):

```
ID        PROJECT  PRIORITY  STATUS       DUE          ASSIGNEE  TITLE
WO-00001  GEN      high      in_progress  2026-03-05!  dana      Replace pump seal
```

**D.2 Tags are case-insensitive.** Tags given to `add --tag`, `edit --add-tag`
and `edit --remove-tag` are lowercased (then validated as before); an order's
tags are kept unique and sorted. `list --tag T` matches ignoring case.

**D.3 Sorting.** `--sort` takes a comma-separated list of keys; earlier keys take
precedence. A key prefixed with `-` is reversed. Write `--sort=-priority` (with
`=`) when the value starts with `-`, as usual for argparse.

| Key | Natural order |
| --- | --- |
| `id` | number, ascending |
| `priority` | most urgent first: urgent, high, normal, low (as in 1.x) |
| `status` | open, in_progress, blocked, done, cancelled |
| `due` | earliest first; orders without a due date always last |
| `created` / `updated` | oldest first |
| `project` | project key A→Z |
| `assignee` | name A→Z ignoring case; unassigned orders always last |
| `title` | A→Z ignoring case |

Reversing affects only orders that have a value: orders without a due date (for
`due`) or without an assignee (for `assignee`) stay last either way. Whatever
ties remain after all keys are broken by number, ascending. An unknown key:
exit 2, `error: unknown sort key: <key>`. Example: `--sort=project,-priority`
lists projects A→Z and, within each project, the least urgent orders first.

**D.4 Durations.** Estimates are whole minutes. They are **shown** as `<m>m`
below one hour (`0m`, `45m`), else `<h>h` for whole hours (`2h`), else
`<h>h<mm>m` with two-digit minutes (`1h05m`, `10h15m`). They are **given** (see
E.2) as `<H>h`, `<M>m` or `<H>h<M>m`, letters in either case, no spaces; `H` is
digits with an optional decimal fraction (`1.5h`), `M` is digits. The value is
floor(H × 60 + 0.5) + M minutes and must be from 1 minute to 1000 hours
(60000 minutes), both inclusive; anything else (`90`, `1h 30m`, `h`, `0m`) is exit 3 with an `error:` message.

**D.5 `show`.** A `Project:` line follows the first line; the estimate is shown
as a duration; timestamps use the format-2 form:

```
Work order WO-00007
Project:   OPS (Operations)
Title:     Replace pump seal
Asset:     -
Priority:  normal
Status:    open
Assignee:  -
Tags:      mechanical, pumps
Estimate:  1h30m
Due:       -
Created:   2026-03-10T12:00:00Z
Updated:   2026-03-10T12:00:00Z
Notes:     -
```

**D.6 `report`** gains `--project KEY` (repeatable; counts only those projects'
orders — the text format is unchanged), `--json` (E.1) and `--by project`, which
prints one row per project ordered by key — projects without orders included,
only the `--project` ones if given — and then a `TOTAL` row summing the rows
shown. Every column except `PROJECT` is numeric (right-aligned). `EST_ACTIVE` is
the sum of the estimates of the **active** orders (orders without an estimate
count 0), shown as a duration (D.4):

```
PROJECT  OPEN  IN_PROGRESS  BLOCKED  DONE  CANCELLED  TOTAL  EST_ACTIVE
GEN         1            1        1     1          1      5       9h15m
OPS         2            0        0     0          0      2       2h30m
TOTAL       3            1        1     1          1      7      11h45m
```

## Part E — Command line

**E.1 `--json`.** `list`, `show`, `report` and `project list` accept `--json`
(after the sub-command). They then print exactly one JSON document to stdout
(`json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)` plus a
newline) and nothing else, applying the same selection, sorting and `--limit`
as the text output. `list --json` with no matches prints `[]`.

A **work-order object** has exactly these keys, and no others (unknown keys
preserved in the file never appear): `id` (canonical), `number` (int),
`project` (key), `title`, `priority`, `status`, `asset` and `assignee` (string
or `null`), `tags` (list), `estimate_minutes` (int or `null`), `due`
(`"YYYY-MM-DD"` or `null`), `created_at`, `updated_at` (format-2 timestamps),
`overdue` (boolean, as of today). `list --json` prints a list of them; `show
--json` prints one, with one extra key `notes`: a list of `{"at", "text"}`.

`project list --json`: a list ordered by key of
`{"key", "name", "created_at", "active", "total"}`.

`report --json`: `{"total", "by_status", "by_priority", "overdue",
"active_estimate_minutes"}` where `by_status` / `by_priority` map every status /
priority (zeros included) to a count; `--project` applies.

`report --by project --json`: `{"projects": [...], "totals": {...}}`; each
project entry has `key`, `name`, one count per status (`open`, `in_progress`,
`blocked`, `done`, `cancelled`), `total` and `active_estimate_minutes`;
`totals` has the same keys minus `key` and `name`.

**E.2 Estimates.** `add` and `edit` take `--estimate DURATION` (D.4);
`edit --estimate none` removes the estimate. `--hours H` keeps working with its
1.x meaning (converted with floor(H × 60 + 0.5) and the same range check) but is
deprecated: using it prints `warning: --hours is deprecated; use --estimate`.
Giving both options is exit 2: `error: --hours and --estimate cannot be used together`.

**E.3 `close ID`** keeps working but is deprecated; it prints
`warning: 'close' is deprecated; use 'status ID done'` (literally `ID`).
Deprecation warnings are printed once, before the command runs (so also when it
then fails).

**E.4 Exit status.** Errors still print `error: <message>` to stderr.

| Status | Meaning |
| --- | --- |
| 0 | success |
| 1 | not found: unknown work order or project |
| 2 | usage: argument-parser errors, malformed id references, unknown sort keys, `--hours` together with `--estimate` |
| 3 | validation: invalid field values (title, priority, status, tag, due date, duration/estimate, project key or name), forbidden status changes, `nothing to change`, the title rule, duplicate project keys/names, removing `GEN` or a non-empty project |
| 4 | storage: invalid JSON, unsupported format, malformed records or timestamps, `migrate` on a missing file, read/write failures |

**E.5 Library API.** Besides the command line, these are public and stable:

* `wotrack.ids.format_id(number) -> str` — A.2; `ValueError` if `number` < 1.
* `wotrack.ids.parse_id(text) -> int` — A.3, returns the number; raises
  `wotrack.errors.UsageError` for an invalid reference.
* `wotrack.timeutil.normalize_timestamp(text) -> str` — C.4; `ValueError` if unparseable.
* `wotrack.timeutil.parse_duration(text) -> int` — the D.4 input syntax to minutes
  (no range check); `ValueError` if malformed.
* `wotrack.timeutil.format_duration(minutes) -> str` — the D.4 display form.
* `wotrack.migration.migrate_v1(document, now) -> dict` — the C.4 conversion of
  a parsed format-1 document (a `dict`) into a format-2 document, without
  touching any file and without modifying `document`; `now` is an aware UTC
  `datetime`, used only for the default project when there are no orders.
* `wotrack.errors`: `NotFoundError` (exit_code 1), `UsageError` (2),
  `ValidationError` (3), `ConflictError` (a `ValidationError`, 3),
  `StorageError` (4), all subclasses of `WotrackError`.

## Worked example

With `WOTRACK_NOW=2026-03-10T12:00:00Z` and a copy of `samples/plant.json` at
`/tmp/plant.json` (`W` stands for `python3 -m wotrack --file /tmp/plant.json`):

```
$ W project list
note: migrated /tmp/plant.json from format 1 to format 2 (backup: /tmp/plant.json.v1.bak)
KEY  NAME     ACTIVE  TOTAL
GEN  General       4      6
$ W project add ops Operations
created project OPS: Operations
$ W move 2 ops
WO-00002: GEN -> OPS
$ W add "Replace pump seal" --project OPS --estimate 1h30m --tag Mechanical --tag PUMPS
created WO-00007 in OPS: Replace pump seal
$ W add "replace  PUMP seal"
error: an active work order in GEN already has this title: WO-00001      (exit 3)
$ W list --sort=project,-priority
ID        PROJECT  PRIORITY  STATUS       DUE          ASSIGNEE  TITLE
WO-00005  GEN      normal    open         2026-04-01   -         Calibrate flow meter
WO-00001  GEN      high      in_progress  2026-03-05!  dana      Replace pump seal
WO-00003  GEN      urgent    blocked      2026-03-02!  lee       Fix conveyor drive
WO-00002  OPS      normal    open         -            -         Inspect boiler relief valve
WO-00007  OPS      normal    open         -            -         Replace pump seal
```

After these commands `W report --by project`, `W project list` and `W show wo-7`
print exactly the examples in D.6, B.7 and D.5.
