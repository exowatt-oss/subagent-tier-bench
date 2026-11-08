# Task: implement RFC 0007 in `wotrack`

You are working in an existing, working Python codebase: `wotrack`, a small
maintenance work-order tracker (standard library only, Python 3.9+) that keeps
all its data in one JSON file and is driven from the command line
(`python3 -m wotrack ...`).

A change request has been accepted: **implement `RFC.md` in this codebase.**
In short, it introduces projects, prefixed string work-order ids, data format 2
with automatic migration of existing format-1 files, project-aware queries and
reports, `--json` output, deprecations and new exit codes — but the RFC itself
is the specification, and its details matter.

## Read first

1. `README.md` — the current behaviour (wotrack 1.4), the command line, the
   table layout, timestamps and data format 1.
2. `RFC.md` — the required changes, with exact messages, file formats, JSON
   shapes, sort rules, exit codes and worked examples.
3. The code under `wotrack/` and the sample data files under `samples/`.

## Rules

- Change the code under `wotrack/` (adding modules is fine). Do not edit
  anything under `tests/`. Standard library only; keep Python 3.9 compatibility.
- Everything README.md describes that RFC.md does not change must keep working
  exactly as before.
- Where the RFC names a module, function, message, key or exit status, use
  exactly that name, text or value.

## Tests

The visible test suite is run from the project root with:

```
python3 -m unittest discover -s tests -t . -q
```

It contains the project's existing tests (which pass today and must keep
passing) and a few acceptance tests for the RFC (which fail until the RFC is
implemented). A larger hidden test suite will grade the result against
README.md and RFC.md — every behaviour it checks is stated in those two
documents, including the edge cases and the backward-compatibility
requirements, so read them carefully rather than relying on the visible tests.

## Done means

- Every part of RFC.md (A–E, including the library API in E.5) is implemented.
- `python3 -m unittest discover -s tests -t . -q` passes with no failures.
