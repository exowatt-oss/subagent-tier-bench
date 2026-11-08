# Task: triage and fix the open bug reports in meterbill

You are working in a small Python package, `meterbill`, a usage-based billing engine
(standard library only, Python 3.9+). Billing operations, finance and two customers have
filed twelve reports in `BUGS.md` (BUG-01 to BUG-12). Your job is to triage every report
and fix the real bugs.

## Read first

- `README.md`: what the tool does, how to run it, and the module layout.
- `DESIGN.md`: the specification. **DESIGN.md is the source of truth for intended
  behaviour**: rounding, time zones and billing periods, units, file formats, rating,
  invoice assembly and every output format. When a report and DESIGN.md disagree,
  DESIGN.md wins.
- `BUGS.md`: the reports. They describe what users saw, with reproduction steps. The
  reporters' guesses about causes, and the modules they blame, may be wrong.

## What to do

1. Reproduce and diagnose each report. Fix every real bug **at its root cause**, in the
   module where the mistake actually is, so that every path through the code behaves as
   DESIGN.md says, not just the exact input in the report.
2. Some reports may describe behaviour that DESIGN.md documents as intended. Do not change
   that behaviour.
3. Keep everything else as it is: behaviour DESIGN.md specifies and no report questions
   must stay the same. Do not rewrite modules that work, and do not change the public
   API listed in DESIGN.md section 9.
4. Write `TRIAGE.md` in the project root with one entry per report, in order:
   `BUG-NN: <real bug | not a bug> - <one line: root cause (file and function) and fix, or the DESIGN.md section that documents the behaviour>`.

## Rules

- Do not edit anything under `tests/`. You may add your own tests in new files elsewhere.
- Do not edit `DESIGN.md` or `BUGS.md`.
- Standard library only.

## Checking your work

Visible tests (a few of them reproduce reported bugs and fail until those are fixed):

```bash
python3 -m unittest discover -s tests -t . -q
```

A larger hidden test suite, written against DESIGN.md, grades the result.

## Done means

- Every real bug in `BUGS.md` is fixed at its root cause.
- Reports that describe documented behaviour are left unchanged and marked as such in
  `TRIAGE.md`.
- `python3 -m unittest discover -s tests -t . -q` passes.
- `TRIAGE.md` has a verdict and a root cause (or DESIGN.md reference) for all twelve
  reports.
