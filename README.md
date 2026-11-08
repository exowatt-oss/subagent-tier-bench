# subagent-tier-bench

A reproducible benchmark for measuring quality, token cost, wall time, and coordination overhead in single-agent, flat, and three-tier coding teams.

![Status: provided as is](https://img.shields.io/badge/status-provided--as--is-lightgrey) ![License: Apache--2.0](https://img.shields.io/badge/license-Apache--2.0-blue)

Created at [Exowatt](https://exowatt.com).

## Status

Provided as-is, without a maintenance or model-performance commitment. Three synthetic Python tasks are included. Hidden grading tests are shipped in `tasks/*/hidden/` but are **not** copied into run directories. Do not put the repository within reach of agents under test.

## Install and prerequisites

Python 3.9+ and Git; the tasks and runner use only the Python standard library. `uv` is optional (substitute `python3` in the commands). To run an actual comparison, separately provide an agent harness able to launch roots and persistent, cost-visible delegated children. No external service is needed to inspect, validate, or score starter tasks.

## Quickstart

```sh
uv run bench.py --help
uv run bench.py selftest
uv run bench.py list
uv run bench.py plan --suite smoke
```

For real runs, see [RUNBOOK.md](RUNBOOK.md): `setup` writes a prompt and starter checkout; your harness launches the root and any children; `finish` scores hidden tests and aggregates recorded session costs; `report` summarizes completed runs. A small canary must verify nested session capture before collecting comparison data.

## Configuration

Copy/edit [`models.json`](models.json) or set `STB_CONFIG=/path/to/models.json` (or pass `--config /path/to/models.json` **before** the subcommand). Map each arm alias to your model ID (`phi` key), session-model regex (`version`), label, and **current USD-per-million-token** input/output/cache prices. Checked-in `example/*` IDs and prices are illustrative placeholders, not usable provider quotes. `STB_ROOT` or `--root` sets the run/results directory. `--sessions` adds a session root for costing; see [adapter contract](docs/ADAPTER.md). No internal infrastructure is required by default.

## Results caveats

Three deliberately well-specified tasks may saturate, so quality differences can reflect hand-off loss more than raw capability. The hidden tests are available to anyone who downloads this repo; keep them out of agent context and do not treat results as tamper-resistant. Report your model config, harness/adapter, token coverage (`unpriced_messages`), task versions, repetitions, and pricing date. No provider bill is implied by configured-price estimates. No model rankings are supplied by this release.

## License

Original code is licensed under [Apache-2.0](LICENSE). See [NOTICE](NOTICE).

## Contributing

See [CONTRIBUTING](https://github.com/exowatt-oss/.github/blob/main/CONTRIBUTING.md). Contributions require DCO sign-off (`git commit -s`); no CLA is required.

## Security

Report vulnerabilities privately via [GitHub private vulnerability reporting](https://github.com/exowatt-oss/subagent-tier-bench/security/advisories/new), or contact software@exowatt.com. See the [security policy](https://github.com/exowatt-oss/.github/blob/main/SECURITY.md); do not open a public issue.
