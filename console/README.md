# rubrica console

A local web page for operating rubrica runs: start a run from a corpus or from
hand-picked files, run each stage or a stretch up to the next human gate, watch
dispatches and their cost as they happen, hold the gates, and read every report.

```bash
uv run rubrica-console --runs-dir runs
```

[`docs/guides/console.md`](../docs/guides/console.md) is the guide: what each
screen does, how model access is set up, what happens when a check fails, and
the safety rules.

## Why it is a separate folder

The `rubrica` package under `src/` is the pipeline. This folder is a tool for
operating it, and the line between them is kept on purpose:

- **It drives the pipeline only from outside.** Code stages, gates and records run
  as `rubrica` subprocesses; prompt stages run through `scripts/dispatch-stage.sh`.
  Nothing it does could not be done by hand at a shell.
- **Nothing under `src/` imports it.** Deleting this folder removes the console and
  leaves the pipeline, its CLI and its tests exactly as they were.
- **It writes into a run only through those commands.** Its own job records, logs
  and ledger live in a lab folder outside every run.

A run driven from here does not exercise the `rb-orchestrate` skill;
[`docs/design/limitations.md`](../docs/design/limitations.md) says why that matters.

## Layout

| Path | What it holds |
|---|---|
| `rubrica_console/cli.py` | the `rubrica-console` command |
| `rubrica_console/pipeline.py` | the run as an ordered list of steps, read from disk |
| `rubrica_console/jobs.py` | running steps: subprocesses, the dispatch cap, repairs, the ledger |
| `rubrica_console/dispatch.py` | calling `dispatch-stage.sh` and reading its output |
| `rubrica_console/credentials.py` | the console's own model credentials |
| `rubrica_console/server.py` | the HTTP server: JSON API, report pages, safety checks |
| `rubrica_console/static/` | the page itself: plain HTML, CSS and JavaScript, no build step |
| `tests/` | its tests, run by `make test` with the rest |

It is installed with the rest by `make setup`; `pyproject.toml` finds packages in
both `src/` and `console/`.
