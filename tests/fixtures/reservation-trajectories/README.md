# reservation-service trajectory capture

Committed live capture, produced under the plan recorded at
`docs/superpowers/specs/2026-08-12-reservation-service-trajectory-run-design.md`.
`docs/superpowers/` is dated build history, kept as a record of what was
decided and why at the time -- it is provenance for this fixture, not the
project's current documentation. That lives in `docs/design/`, indexed from
`docs/README.md`.

Re-capturing draws fresh LLM spans and a fresh `confirmation_code` sequence, so
without this record nobody could later distinguish a pipeline change from a
capture change. Changing the harness obliges re-recording, and that re-record is
a reviewable diff.

## Re-running the harness

```bash
cd /tmp/rubrica-lab/capture
FIX=/home/bnayahu/work/kaegis/rubrica/tests/fixtures/reservation-trajectories
REPO=/home/bnayahu/work/kaegis/rubrica
uv run --with fastmcp --with pydantic --with pydantic-settings --with mlflow \
       --with langgraph --with langchain --with langchain-core --with langchain-openai \
       --with langchain-mcp-adapters --with mcp \
  python "$REPO/scripts/capture-reservation-trajectories.py" trajectories --out "$FIX/trajectories.json"
```

This is the command that actually worked (Task 2 report), not the plan's
original version: `--with langchain` is required in addition to
`--with langchain-core` because `mlflow.langchain.autolog()` imports the
`langchain` package itself for a version check, even though the harness never
imports it directly. Without it the run crashes with `ModuleNotFoundError: No
module named 'langchain'` before a single prompt is issued.

`capture-reservation-trajectories.py`'s `TOOL_DIR` and `AGENT_SRC` constants
are absolute paths into this author's `rossoctl` checkout. Anyone else
re-running the harness must edit both before it will find the target.

## Capture conditions

| | |
|---|---|
| Date | 2026-08-12 |
| Model | `Azure/gpt-4.1` via litellm proxy (`OPENAI_API_BASE`) |
| MLflow | 3.15.1, `sqlite:///` backend, `autolog()` for LangChain |
| Target | `rossoctl/examples` at `dbbc5e0f46cc92c8f642e44d1124965394cf36e5`, clean |
| MCP server | in-process build, `streamable-http` on `127.0.0.1:8765` |
| Agent | `graph.ainvoke` driven directly; A2A layer not used |
| Traces written | 10 |

`MCP_TRANSPORT` is set per-process and never globally: `streamable-http` for
FastMCP, `streamable_http` for langchain-mcp-adapters. One env var, two
incompatible spellings — the hazard the control run flagged as a contradiction.

## Capture history

The first capture pass wrote only 8 of the 10 traces. `p03-place` and
`p05-cancel` were recorded `skipped-unobserved`: the id-substitution heuristic
never saw a `restaurant_id`, because `search_restaurants`'s real
`ToolMessage.content` for `p01-search` arrived as a list of content blocks
rather than a plain string, and the id-extraction loop's `except
(json.JSONDecodeError, TypeError): continue` guard silently discarded that
shape — even though `search_restaurants` had genuinely returned `rest_001`.
That is a parser defect (an instrument misreading an observation it had
already taken), not a result (the model or tool declining to produce a
value), and because `p03` never ran, `place_reservation` was never called
either, cascading `p05`'s skip from the same single failure on `p01`. The
8-trace corpus this pass produced was **discarded** and is not retained
anywhere in this fixture.

A `_content_text()` normaliser was added to `capture-reservation-trajectories.py` to resolve
list-of-content-block shapes to text before `json.loads` ever sees them,
fixing the parser rather than the trace. Rubrica's plan carries a single-pass
rule for this capture, specifically to prevent selecting on the *model's*
behaviour — re-rolling until a trace comes out the desired shape would make
the harness author the oracle for the very system this experiment withholds.
A human ruling authorised exactly one additional run as a carve-out from that
rule: nothing about the prompts, the model, or how output is judged changed
between the two runs, only a parser that had misread a reading it already
took was repaired, so this is an instrument fix, not selection. That single
re-run, and only that run, produced the 10-trace corpus committed here —
`reservation_61e0d19f75d1` and confirmation code `RES001000` among the values
now verifiable in it.

## Prompt list, verbatim

| id | text |
|---|---|
| `p01-search` | Find Italian restaurants in Boston |
| `p02-search-then-check` | Find Italian restaurants in Boston, then check availability at the first one for 4 people on 2025-03-15 at 7:00 PM |
| `p03-place` | Book a table at restaurant `{restaurant_id}` for 2025-03-15T19:00:00, party of 4. Name: Jane Smith, Phone: +1-555-987-6543, Email: jane@example.com |
| `p04-list` | List all reservations for jane@example.com |
| `p05-cancel` | Cancel reservation `{reservation_id}` because plans changed |
| `p06-search-empty` | Find Ethiopian restaurants in Fargo |
| `p07-check-unknown` | Check availability at restaurant rest_999 for 2 people on 2025-03-15 at 8:00 PM |
| `p08-place-unknown` | Book a table at restaurant rest_999 for 2025-03-15T20:00:00, party of 2. Name: Test User, Phone: +1-555-000-0000, Email: test@example.com |
| `p09-list-empty` | List all reservations for nobody@example.com |
| `p10-cancel-unknown` | Cancel reservation reservation_deadbeef1234 because it does not exist |

`{restaurant_id}` and `{reservation_id}` are filled from an **observed** span
output — the first `search_restaurants` result's `id` and the
`place_reservation` result's `id`. When a needed value was never observed the
prompt is **skipped**, never filled with a plausible guess.

## Outcome per prompt

| id | status | tools_called |
|---|---|---|
| `p01-search` | captured | `search_restaurants` |
| `p02-search-then-check` | captured | `search_restaurants`, `check_availability` |
| `p03-place` | captured | `check_availability`, `place_reservation` |
| `p04-list` | captured | `list_reservations` |
| `p05-cancel` | captured | `cancel_reservation` |
| `p06-search-empty` | captured | `search_restaurants` |
| `p07-check-unknown` | captured | `check_availability` |
| `p08-place-unknown` | captured | `check_availability` |
| `p09-list-empty` | captured | `list_reservations` |
| `p10-cancel-unknown` | captured | `cancel_reservation` |

All ten prompts captured; none skipped, errored, or `no-trace`.
`p08-place-unknown` stopped at `check_availability`'s validation error for the
invalid restaurant id without attempting `place_reservation` — a genuine
result of the model's own choice, not a parser artifact.

## The absolute paths are deliberate

`capture-reservation-trajectories.py` hardcodes the source checkout it captured
from, and `trajectories.json` embeds that same path ten times in MLflow
`mlflow.source.name` fields. Neither is sanitised. `trajectories.json` is a
committed recording, and a recording is evidence of what happened -- editing one
to look tidier corrupts the evidence it exists to carry. The harness is kept for
the same reason: it records how this fixture was produced. Re-capturing on
another machine means editing those constants, and that edit is the reviewable
part.

## Single-pass rule

Captured in one pass. No prompt was re-run to obtain a better trace. A prompt
that failed to drive its intended path is recorded as such, and the gap it was
aimed at stays open.

## Staging for intake

`trajectories.json` is the authentic capture and stays whole here. Intake,
however, registers **one file per trace**, split from this array in array order
and named from `capture-reservation-trajectories.py`'s own `PROMPTS` ids
(`trajectory-p01-search.json` … `trajectory-p10-cancel-unknown.json`). Each split
file is a complete MLflow trace verbatim, keeping the top-level `trace_id`
mirror, so `intake.classify` returns `trace` for each. The mapping was verified
by content before staging — every trace's `info.request_preview` was checked
against the prompt it is named for, rather than trusted by position.

The reason is a measurement: the combined array is **~228k tokens**, larger than
a 200k context window, so no single `rb-extract` member could read it. Almost all
of that is MLflow redundancy — `spanInputs`/`spanOutputs` repeat the entire
message history at every step, and `mlflow.chat.tools` repeats the tool schema in
all 100 spans, which is `tools-list.json` duplicated a hundred times.

Stripping those attributes was considered and **rejected**. It would have cut the
file by roughly 90% and kept a single input, but it would have put the author
inside the data path, and "deduplicating" is one short step from curating. A
mechanical split loses nothing and keeps this file the record.

One consequence worth stating: ten trace files mean ten `rb-extract` members, each
seeing exactly one run and none seeing a sibling. That is a stronger fan-out
isolation test than one member reading all ten would have been.
