# Adding a task to subagent-tier-bench

The bench compares agent team shapes (one agent, two tiers, three tiers) on the same
coding tasks. A task is graded only by hidden unit tests, so every rule below exists to
make that grade fair, stable and cheap to run.

## Layout

```
tasks/<id>/
  task.json     metadata (see below)
  brief.md      the prompt the root agent receives (the bench prepends the team policy)
  starter/      copied verbatim into a fresh run directory; the agents only ever see this
    tests/      visible tests: __init__.py + test_*.py, run with
                python3 -m unittest discover -s tests -t . -q
  hidden/       hidden tests, copied to <run>/tests_hidden/ at scoring time
    __init__.py (empty)
    test_<workstream>_*.py
    data/       optional fixture files for hidden tests
```

Reference solutions are never committed. Keep them outside the repo (for example
`~/src/stb-reference/<id>/`) and use them only to prove the task is solvable.

## task.json

```json
{
  "id": "t1-ledger",
  "title": "Plain-text ledger from a spec",
  "shape": "greenfield | brownfield-change | bug-hunt",
  "package": "ledgerlite",
  "workstreams": ["parse", "engine", "report", "cli"],
  "hidden_file_timeout_s": 120,
  "notes": "one or two sentences on what the task exercises"
}
```

`bench.py selftest` adds `starter_hidden_pass` (the share of hidden tests the untouched
starter already passes) so reports can show the gain over the starter.

## Test rules (hidden and visible)

- Python 3.9 compatible, standard library only, `unittest` only. No network, no
  wall-clock, no randomness without a fixed seed, no dependence on locale, timezone
  (`TZ`), terminal width or dict-order accidents. The whole hidden suite runs in under
  30 seconds on a laptop.
- Every test is a literal `def test_...(self)` method on a `unittest.TestCase` subclass.
  No generated test methods, no parametrised loops pretending to be many tests. One method
  is one point, so keep methods focused (one behaviour each).
- Hidden test files are self-contained: no imports from other hidden files, no relative
  imports. Shared fixtures go in `hidden/data/` and are found with
  `Path(__file__).resolve().parent / "data"`.
- The project root is `Path(__file__).resolve().parents[1]` (tests live in `tests/` or
  `tests_hidden/` directly under it). Import the package normally (the scorer puts the root
  on `sys.path` and runs with the root as cwd). Run CLIs with
  `subprocess.run([sys.executable, "-m", "<package>", ...], cwd=ROOT, capture_output=True, text=True, timeout=30)`.
- Use temporary directories (`tempfile.TemporaryDirectory`) for anything a test writes.
- Name hidden files `test_<workstream>_<topic>.py` with `<workstream>` from task.json, so
  reports can break the score down by workstream. Spread tests roughly evenly across
  workstreams.
- Visible tests are a small, honest sample (about 15–25 % of the hidden count) that gives
  agents a feedback loop. Hidden tests may overlap with visible ones in behaviour but
  should mostly probe the rest of the spec, including edge cases the spec states plainly.
- Never test anything the brief or spec does not state or clearly imply. A careful
  engineer reading the docs in `starter/` must be able to reach 100 %.

## Validation (required before a task is accepted)

1. Reference passes 100 % of visible and hidden tests under Python 3.9 and a
   current Python (3.13).
2. The untouched starter scores low on hidden tests (greenfield: under 10 %;
   brownfield/bug-hunt: under 40 %, with the passing ones being regression checks).
3. Hidden suite runtime under 30 s.
4. `brief.md` is under about 60 lines, names the docs to read, the visible test command,
   and the acceptance bar; it says nothing about how to staff the work.
