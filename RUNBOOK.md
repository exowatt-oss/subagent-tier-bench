# Runbook: hierarchical agent benchmark

The driver prepares each run, launches an isolated team, waits for all descendants to stop, and grades the result. Agents under test see only a copy of `starter/` and the generated prompt; never show them this repository's `hidden/` tests. Run directories are disposable and must not be reused.

## Adapter contract

The runner prepares files and scores work; **your harness launches agents**. An adapter must:

1. Start one fresh root agent in the `run_dir`, using `root_model`, `root_effort`, and the full `prompt_file` from `setup`.
2. Expose a delegation operation that lets the root/leads launch children on an explicitly requested model and effort **in the same checkout**; each child receives a self-contained brief and its policy. Do not substitute another launch mechanism mid-run.
3. Persist each root and child as a phi-compatible JSONL session with a `session` header containing `cwd` and `timestamp`, `thinking_level_change` events, and assistant message `model`, `provider`, and `usage` (input/output/cacheRead/cacheWrite). Pass session directories with `--sessions` when not stored under the usual phi session root. Sessionless children are invisible to cost/tier accounting. If your harness uses another format, convert to this shape or supply a session importer before reporting costs.
4. Start the clock at launch, wait for root **and descendants**, cancel all remaining work at `time_limit_min`, and record `ok`, `timeout`, or `infra` honestly. Do not prompt or coach the agents during a run. Use a separate directory for blind review, so its cost is not attributed to a benchmark arm.

**Optional phi/P3 Code adapter example:** In P3 Code, run the root on phi with a configured model; use P3's `delegate_task` for children with model/effort overrides, same checkout and session persistence. Do not use a sessionless native subagent invocation for costed children. In standalone phi, verify that the chosen child launcher persists JSONL sessions before collecting cost. APIs and model availability change; consult your harness's current capabilities rather than copying old launch parameters. See [adapter details](docs/ADAPTER.md).

## Preflight

Install Python 3.9+, standard library, and Git. Configure **real** model IDs and current per-million-token USD rates in `models.json` (or pass `--config path.json` / set `STB_CONFIG`); the checked-in `example/*` IDs and rates are placeholders. Run:

```sh
uv run bench.py --help
uv run bench.py selftest
uv run bench.py list
uv run bench.py plan --suite smoke
```

A small nesting canary should launch one root, one lead and one worker in a throwaway checkout. Then run `uv run bench.py cost --dir /path/to/canary --arm h-opus-sonnet-luna --sessions /path/to/sessions`; check exactly one L0/L1/L2 session, no off-policy warnings, and nonzero token counts. Legacy arm IDs are experiment labels: `opus` = strong, `sonnet` = balanced, `luna` = economy, `fable` = premium. Efforts (`high`, `xhigh`, `max`) must be supported or mapped consistently by your adapter. Do not trust cost comparisons until the canary works. Ensure global agent instructions do not override the arm's staffing policy.

## One run

```sh
uv run bench.py setup --task t1-ledger --arm h-opus-sonnet-luna --rep 1
# Start a fresh agent as described above using the JSON returned by setup.
uv run bench.py finish --run RUN_ID --status ok --wall-s 420 --sessions /path/to/sessions
# Or use --status timeout / infra / error and --note as appropriate.
```

`finish` runs the hidden tests against a scratch copy, computes configured-price token costs, and appends to `$STB_ROOT/results.jsonl` (default `~/stb-runs`). A grader can instead run `score --run RUN_ID` and `cost --run RUN_ID`. For a blind code review, run `judge-pack --run RUN_ID`, give the resulting `judge.md` to an independent reviewer outside the run directory, then `judge-record --run RUN_ID --json '...'`. Never disclose the arm to that reviewer.

## Suites and reporting

```sh
uv run bench.py plan --suite core
uv run bench.py plan --suite full
uv run bench.py report
```

Start with `smoke`, check tier attribution and token coverage, then `core`; `full` adds a second repetition. Limit concurrency to avoid rate limiting; classify provider failures as `infra` and retry in a new run directory. Treat scores as task-specific, not a universal model ranking. Historical calibration tied to private infrastructure is not part of this export.
