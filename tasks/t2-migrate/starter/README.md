# wotrack

`wotrack` is a small maintenance **work-order tracker** for a plant or facility
team. All data lives in one JSON file; the command line reads it, applies one
command and writes it back. Standard library only, Python 3.9+.

This document describes the current release, **wotrack 1.4** (data format 1).
Planned changes are in `RFC.md`.

```
python3 -m wotrack [--file PATH] COMMAND [OPTIONS]
python3 -m unittest discover -s tests -t . -q      # run the test suite
```

## Package layout

| Module | Responsibility |
| --- | --- |
| `wotrack/errors.py` | Exception classes; each carries the CLI exit code. |
| `wotrack/timeutil.py` | Clock (`WOTRACK_NOW`), timestamp/date parsing and formatting. |
| `wotrack/models.py` | `WorkOrder`, `Note`, field validation (`clean_*`), the status workflow. |
| `wotrack/storage.py` | Data file location, `Database`, JSON encode/decode, atomic writes. |
| `wotrack/service.py` | `WorkOrderService`: every operation that changes data. |
| `wotrack/query.py` | `list` filters and sort orders. |
| `wotrack/report.py` | `report` counts. |
| `wotrack/formatting.py` | `list` table and `show` detail rendering. |
| `wotrack/cli.py` | Argument parsing, command handlers, error handling, exit codes. |

## Work orders

| Field | Meaning | Rules |
| --- | --- | --- |
| id | Positive integer, allocated in sequence | Never reused, even after `delete`. |
| title | What needs doing | Trimmed; 1–120 characters. |
| asset | Equipment tag, e.g. `PUMP-07` | Free text, trimmed; empty = none. |
| priority | `low`, `normal`, `high`, `urgent` | Default `normal`; input is case-insensitive. |
| status | `open`, `in_progress`, `blocked`, `done`, `cancelled` | New orders are `open`. Input is case-insensitive and `-` may be used for `_` (`in-progress`). |
| assignee | Person's name | Trimmed; empty = unassigned. |
| tags | List of labels | Each tag is non-empty, at most 30 characters, without whitespace or commas. Kept in the order added; adding a tag the order already has does nothing. |
| estimate | Effort in hours | A number > 0 and ≤ 1000 (`--hours 2.5`). Optional. |
| due | Due date `YYYY-MM-DD` | Optional. |
| created / updated | Timestamps (UTC) | `updated` changes on every modification. |
| notes | Timestamped free-text notes | Appended by `note`; text is trimmed and non-empty. |

**Closed** orders are those with status `done` or `cancelled`. An order is
**overdue** when it has a due date earlier than today (UTC) and is not closed.

### Status workflow

| From | Allowed new statuses |
| --- | --- |
| open | in_progress, blocked, done, cancelled |
| in_progress | open, blocked, done, cancelled |
| blocked | open, in_progress, cancelled |
| done | open |
| cancelled | open |

Changing to the current status is an error (`work order 3 is already open`),
as is any change not in the table (`cannot change status from done to blocked`).

## Data file location and the clock

The data file is chosen in this order: the global `--file PATH` option, the
`WOTRACK_FILE` environment variable, then `workorders.json` in the current
directory. A missing file behaves like an empty one; it is created by the first
command that changes data. Read-only commands (`list`, `show`, `report`) never
write the file.

The current time is the system clock in UTC. If the `WOTRACK_NOW` environment
variable is set to a timestamp (any form listed under *Timestamps* below) that
value is used instead — handy for scripts and tests. "Today" is the UTC date
of the current time.

## Commands

Every command that names a work order takes its integer `ID`. An `ID` that is
not a positive integer is rejected by the argument parser (exit status 2).

| Command | Effect | Prints |
| --- | --- | --- |
| `add TITLE [--asset A] [--priority P] [--assignee NAME] [--tag T]... [--hours H] [--due DATE]` | Create an order | `created 7: TITLE` |
| `list [filters] [--sort KEY] [--limit N]` | List orders (see below) | table |
| `show ID` | Show one order | detail view |
| `edit ID [--title T] [--asset A] [--priority P] [--assignee NAME] [--hours H] [--due DATE\|none] [--add-tag T]... [--remove-tag T]...` | Change fields; at least one option is required (`nothing to change`). `--due none` clears the due date; removing a tag the order does not have is ignored. | `updated 7` |
| `status ID STATUS` | Change status (workflow above) | `7: open -> in_progress` |
| `close ID` | Same as `status ID done` | `7: open -> done` |
| `assign ID NAME` | Assign; `NAME` of `-` unassigns | `7 assigned to dana` / `7 unassigned` |
| `note ID TEXT` | Append a note | `note added to 7` |
| `delete ID` | Delete the order | `deleted 7: TITLE` |
| `report` | Summary counts | see below |

### `list`

By default `list` shows only orders that are not closed (status `open`,
`in_progress` or `blocked`). Filters (all combined with AND):

| Option | Selects |
| --- | --- |
| `--status S` (repeatable) | Orders whose status is any of the given ones (replaces the default). |
| `--all` | All statuses (ignored when `--status` is given). |
| `--priority P` | Exactly priority `P`. |
| `--min-priority P` | Priority `P` or more urgent. |
| `--assignee NAME` | Assignee equal to `NAME`, ignoring case; `-` selects unassigned orders. |
| `--tag T` (repeatable) | Orders that have **all** the given tags (exact match). |
| `--text S` | `S` occurs in the title or the asset, ignoring case. |
| `--overdue` | Overdue orders only. |

`--sort` is one of `id` (default, ascending), `priority` (most urgent first,
ties by id), `due` (earliest first, orders without a due date last, ties by
id). `--limit N` (N ≥ 1) keeps the first N rows after sorting.

The table has the columns `ID PRIORITY STATUS DUE ASSIGNEE TITLE`. Empty
values are shown as `-`; the due date of an overdue order gets a `!` suffix.
If nothing matches, `list` prints `no work orders` instead of a table.

**Table layout** (used by every table wotrack prints): one header row and one
row per record; columns are separated by exactly two spaces; every column is
as wide as its widest cell, header included; numeric columns (here: `ID`) are
right-aligned and all others left-aligned; trailing spaces are removed from
every line.

```
$ WOTRACK_NOW=2026-03-10T12:00:00Z python3 -m wotrack --file samples/plant.json list --all
ID  PRIORITY  STATUS       DUE          ASSIGNEE  TITLE
 1  high      in_progress  2026-03-05!  dana      Replace pump seal
 2  normal    open         -            -         Inspect boiler relief valve
 3  urgent    blocked      2026-03-02!  lee       Fix conveyor drive
 4  low       done         -            dana      Repaint safety lines
 5  normal    open         2026-04-01   -         Calibrate flow meter
 6  high      cancelled    -            lee       Replace pump seal
```

### `show`

```
$ WOTRACK_NOW=2026-03-10T12:00:00Z python3 -m wotrack --file samples/plant.json show 1
Work order 1
Title:     Replace pump seal
Asset:     PUMP-07
Priority:  high
Status:    in_progress
Assignee:  dana
Tags:      mechanical, urgent
Estimate:  2.5h
Due:       2026-03-05 (overdue)
Created:   2026-03-01 09:15:00
Updated:   2026-03-02 08:00:00
Notes:
  [2026-03-01 10:00:00] parts ordered
  [2026-03-02 08:00:00] seal arrived
```

Labels are padded to 11 characters. Empty values print `-`; an order without
notes prints `Notes:     -`. The estimate prints as hours (`2.5h`, `3h`); an
overdue due date gets ` (overdue)`.

### `report`

Counts over **all** orders (closed included); `samples/plant.json` with
`WOTRACK_NOW=2026-03-10T12:00:00Z`:

```
Work orders: 6
By status:
  open         2
  in_progress  1
  blocked      1
  done         1
  cancelled    1
By priority:
  urgent  1
  high    2
  normal  2
  low     1
Overdue: 2
```

## Errors and exit status

Errors print `error: <message>` to stderr. Exit status: `0` success, `2`
command-line usage errors reported by the argument parser (unknown option,
missing argument, malformed `ID`), `1` every other error (unknown work order
`no such work order: 9`, invalid values, forbidden status changes, unreadable
data file).

## Data format 1

The data file is a JSON object, written UTF-8 with
`json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)` plus a final
newline, atomically (temporary file in the same directory, then rename).
Orders are written sorted by id.

```json
{
  "format": 1,
  "next_id": 7,
  "orders": [
    {
      "asset": "PUMP-07",
      "assignee": "dana",
      "created": "2026-03-01 09:15:00",
      "due": "2026-03-05",
      "estimate_hours": 2.5,
      "id": 1,
      "notes": [{"at": "2026-03-01 10:00:00", "text": "parts ordered"}],
      "priority": "high",
      "status": "in_progress",
      "tags": ["mechanical", "urgent"],
      "title": "Replace pump seal",
      "updated": "2026-03-02 08:00:00"
    }
  ]
}
```

| Key | Type | Notes |
| --- | --- | --- |
| `format` | int | Always `1`. Files without a `format` key (written by wotrack < 1.2) are format 1. Any other value is an error (`unsupported data format: 2`). |
| `next_id` | int | Next id to allocate. If missing, or not above the highest id, the next id is highest id + 1. |
| `orders[].id` | int | Unique. |
| `orders[].title`, `priority`, `status` | string | As in the field table. |
| `orders[].asset`, `assignee` | string | `""` means none. |
| `orders[].tags` | list of string | |
| `orders[].estimate_hours` | number or `null` | |
| `orders[].due` | `"YYYY-MM-DD"` or `null` | |
| `orders[].created`, `updated` | timestamp string | |
| `orders[].notes` | list of `{"at": timestamp, "text": string}` | In the order they were added. |

**Older files.** Files written by earlier releases may lack some order keys.
When reading: a missing `asset` or `assignee` is `""`, missing `tags` or
`notes` is an empty list, missing `estimate_hours` or `due` is `null`, missing
`priority` is `normal`, missing `status` is `open`, and missing `updated`
equals `created`. Keys wotrack does not know are ignored (and therefore not
written back).

### Timestamps

wotrack writes timestamps as `YYYY-MM-DD HH:MM:SS` in UTC. When reading (data
file or `WOTRACK_NOW`) it also accepts:

* `T` instead of the space between date and time;
* minutes precision (`YYYY-MM-DD HH:MM`, seconds = 0);
* fractional seconds (`09:15:00.250`) — the fraction is discarded;
* a `Z` suffix, or a `+HH:MM` / `-HH:MM` UTC offset, which is converted to
  UTC (`2026-03-01 11:15:00+02:00` is `2026-03-01 09:15:00` UTC).

Without a suffix the value is UTC. Anything else is an error.

## Samples

`samples/` holds example data files in format 1: `plant.json` (the file used
in the examples above) and `legacy-workshop.json` (written by wotrack 1.1:
no `format` key, older timestamp spellings and missing optional keys).
