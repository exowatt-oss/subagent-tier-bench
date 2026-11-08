# Task: implement `ledgerlite`

Build `ledgerlite`, a small plain-text double-entry accounting library with a
command-line interface, in the `ledgerlite/` package of this directory.

Read these first:

- `README.md`: layout of the project and how to run things.
- `SPEC.md`: the complete specification. Every behaviour that will be checked is defined
  there, including exact error messages, output layouts, ordering, rounding, option
  names and exit codes. Read all of it carefully; small details matter.

Constraints:

- Python 3.9+ with the standard library only. No third-party packages, no network.
- Keep the public API named in SPEC.md section 1. `ledgerlite/model.py` is provided:
  keep its classes, fields and defaults as they are.
- Do not modify anything under `tests/`. You may add your own tests in other files.

Visible tests (your feedback loop), run from this directory:

    python3 -m unittest discover -s tests -t . -q

Grading: a larger hidden test suite checks the behaviour described in SPEC.md. The
score is the share of hidden tests that pass.

Done means: everything in SPEC.md is implemented and the visible tests pass.
