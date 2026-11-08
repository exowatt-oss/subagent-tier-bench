# Harness adapters and cost accounting

`bench.py` owns task setup and grading, not agent launch. It uses a compatible JSONL session reader for cost. The adapter is the interface between a harness and the benchmark:

- Launch the root in `run_dir` with the configured `root_model` and `root_effort`, using the exact `prompt_file` text.
- Ensure the root and any lead can delegate on their assigned model and effort into the **same** checkout. Each delegated child must be persistently recorded with a session header identifying its `cwd`; invisible sessions invalidate tier-cost comparisons.
- Wait for the root and all descendants before grading. A missing tier or an off-policy session is an adapter configuration error, not evidence about model quality.
- Session files should provide `session` (with `cwd` and `timestamp`), `thinking_level_change` (with `thinkingLevel`), and `message` events whose assistant `message` includes `model`, `provider`, and `usage`: `input`, `output`, `cacheRead`, `cacheWrite`, optional `cacheWrite1h`, and optional `cost.total`. The runner scans configured `--sessions` roots, `$PI_CODING_AGENT_SESSION_DIR`, `$PI_CODING_AGENT_DIR/sessions`, and `~/.pi/agent/sessions`. If using a different harness format, write a converter or do not claim comparable costs.

**Example (phi with P3 Code):** Launch a root on the phi provider and use P3 Code's `delegate_task` as the child operation with explicit model/effort overrides. Do not use a sessionless child launcher; its tokens cannot be priced. Other harnesses can implement the same contract. The generic generated prompt intentionally does not prescribe an API-specific operation name.

`models.json` maps stable arm aliases to the harness model IDs (`phi`), a `version` regex matching the session's model field, a human-readable `label`, and illustrative `price` inputs in USD per million tokens. Override both IDs and rates before a real run. The `price` fields are `input`, `output`, `cacheRead`, and `cacheWrite`; optional `tiers` entries can override these above `inputTokensAbove`. If the model is unmatched, the cost reader falls back to provider-reported cost and increments `unpriced_messages`; treat that as a missing configuration, not a reliable rate comparison. Existing arm IDs are stable labels, and `models.json` maps the aliases to arbitrary model identities.
