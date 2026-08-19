# Rubrica

Rubrica builds an agent test suite for a target system out of whatever
artifacts describe it — specifications, captured trajectories, source code —
by chaining AI skills over a schema-validated, on-disk artifact contract.

## How it works

A run moves through eleven stages. `survey` and `intake` are deterministic
code that mint the run and admit its inputs, and `smoke` is deterministic code
that exercises the emitted suite. The other eight are dispatched as prompts,
with only a run directory, a stage name, and a skill file — plus, for the three
fan-out stages (`extract`, `instantiate`, `challenge`), the id of its own
slice, which is an address rather than context — never a summary of what an
earlier stage concluded. Seven of those eight carry the pipeline's judgment:
`triage`, `extract`, `reconcile`, `propose`, `score`, `instantiate`, and
`challenge`. The eighth, `emit`, is the exception that the rest of the design
leans on — its skill is a thin wrapper that runs `rubrica emit` and writes
nothing itself, because compiling the suite has to be deterministic code: two
runs with identical inputs to it must produce byte-identical suites, or
variance stops being attributable to any one stage. See
[`docs/concepts/artifact-contract.md`](docs/concepts/artifact-contract.md)
for the exact rule, including the two things an orchestrator may append when
it retries one. Every handoff between stages is therefore a file on disk you
can open, schema-check, and diff, never something carried only in a model's
memory.

## Status

Early. The pipeline has run end to end against a toy world with a model
dispatched at every stage, and that is the extent of what has been observed
directly — it has not yet been hardened against a real target, and several
known gaps are recorded rather than fixed. Read
[`docs/design/limitations.md`](docs/design/limitations.md) before trusting a
corner of it that has not been exercised, and
[`docs/design/rationale.md`](docs/design/rationale.md) for why it is shaped
the way it is, including the trade-offs made on purpose.

## Install

Python 3.13+ and [`uv`](https://docs.astral.sh/uv/). Nothing else: every
`rubrica` subcommand is pure Python, so a machine that can `make setup` can run
the pipeline's whole deterministic half.

```bash
make setup     # create the venv, install runtime + dev deps from uv.lock
make test      # run the test suite
make check     # ruff lint + format check, no changes
make lint      # ruff check --fix
make format    # ruff format
make help      # every target, with its one-line description
```

The two scripts under `scripts/` are the exception, because they drive a real
dispatch rather than the CLI: `dispatch-stage.sh` and `audit-reads.sh` each need
`jq` on `PATH`, and `dispatch-stage.sh` needs the `claude` CLI as well. Both
check up front and exit `2` naming the missing tool — a misconfigured
environment, not a stage defect. See
[`docs/guides/running-a-stage-by-hand.md`](docs/guides/running-a-stage-by-hand.md).

There is one more target, `make live`, deliberately not part of `make test`:
it runs behind the `live` pytest marker and the `RUBRICA_LIVE` opt-in,
asserting against committed recordings of a real dispatch, so running it
costs nothing. Producing or re-producing one of those recordings is the part
that dispatches a model and costs money.

## Quickstart

Commands below assume the venv `make setup` created is on `PATH`; otherwise
prefix each with `uv run`.

```bash
export RUN=$(rubrica intake \
  --input tests/fixtures/toy/api.json \
  --input tests/fixtures/toy/notes.md \
  --input tests/fixtures/toy/trace.json \
  --runs-dir runs --target-name toy --target-interface mcp)
rubrica validate --run "$RUN" --stage intake
rubrica check-refs --run "$RUN"
```

This mints a run from three hand-picked files and checks it clean; nothing
past `intake` runs without dispatching a model. The full walkthrough,
including the survey/triage path for a whole corpus, is
[`docs/getting-started.md`](docs/getting-started.md).

## Documentation

- [`docs/README.md`](docs/README.md) — the full index.
- [`docs/getting-started.md`](docs/getting-started.md) — a first run, start
  to finish.
- Concepts: [`docs/concepts/pipeline.md`](docs/concepts/pipeline.md),
  [`docs/concepts/artifact-contract.md`](docs/concepts/artifact-contract.md),
  [`docs/concepts/glossary.md`](docs/concepts/glossary.md).
- Reference: [`docs/reference/cli.md`](docs/reference/cli.md),
  [`docs/reference/artifacts.md`](docs/reference/artifacts.md).
- Guides:
  [`docs/guides/running-a-stage-by-hand.md`](docs/guides/running-a-stage-by-hand.md).
- Design: [`docs/design/rationale.md`](docs/design/rationale.md),
  [`docs/design/limitations.md`](docs/design/limitations.md).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the checks a change has to clear
and the commit conventions this repository holds to.

## License

Apache-2.0, © IBM Corp. See [`LICENSE`](LICENSE).
