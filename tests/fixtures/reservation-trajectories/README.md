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

`capture-reservation-trajectories.py` reads its two target paths from the
environment. The defaults are the paths the 2026-08-12 capture actually used,
written here relative to the `rossoctl` checkout named in *Capture conditions*
below; the script's own defaults are those two paths absolute:

    RUBRICA_ROSSOCTL_TOOL_DIR    -> examples/mcp/reservation_tool
    RUBRICA_ROSSOCTL_AGENT_SRC   -> examples/a2a/reservation_service/src

That checkout is still present on the capture machine and both defaults still
resolve there, but it is no longer a git checkout, so the commit sha in the table
below can no longer be verified against it. Anyone re-running the harness
anywhere else must set both. Set them rather than editing the script: an edit to
the source is indistinguishable from a change to the harness, which is exactly
what this record exists to let a reader rule out.

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

# Second capture: `trajectories2.json`

A full pipeline run over `trajectories.json` (`runs/run-20260816-085526`) reached
`rb-reconcile`, produced a clean world model, and then **halted at B4**: all
seven of its gaps named a stage still to come. Six of the seven asked for
evidence this capture could supply, and an operator ruling put
`gap-a2a-method-envelope` out of scope. `p11`–`p17` were appended to
`PROMPTS` to close the other six, and the harness was run once over the whole
list.

`p11` is the one that unblocked the run, and it is a one-line addition rather
than a new mechanism. `p05-cancel` already cancels jane's reservation with a
`{reservation_id}` filled from an observed `place_reservation` span; nothing in
`p01`–`p10` ever listed afterwards, so whether cancelling deletes the record or
flags it was unknowable, and every place-then-cancel-then-list scenario had two
possible gold answers. Listing the same guest after `p05` settles it.

## Capture conditions

| | |
|---|---|
| Date | 2026-08-16 |
| Model | `Azure/gpt-4.1` via litellm proxy (`OPENAI_API_BASE`) — same as the first capture |
| MLflow | 3.15.1, `sqlite:///` backend, `autolog()` for LangChain |
| Target | `rossoctl/examples` at `dbbc5e0f46cc92c8f642e44d1124965394cf36e5`, clean — the same commit |
| MCP server | in-process build, `streamable-http` on `127.0.0.1:8765` |
| Agent | `graph.ainvoke` driven directly; A2A layer not used |
| Traces written | 17 |

Same harness, same model, same target commit as `trajectories.json`. So the two
files differ by exactly two things: LLM nondeterminism, and the seven appended
prompts. Anything else a reader finds between them is a finding, not a
configuration difference.

**This file re-captures `p01`–`p10` as well as adding `p11`–`p17`**, because the
harness runs its whole `PROMPTS` list. The two files therefore hold independent
captures of the same first ten prompts, and the corpus containing both has
deliberate redundancy for triage to rule on rather than for this fixture to
pre-resolve.

## Added prompts, verbatim, and the gap each closes

| id | text | closes |
|---|---|---|
| `p11-list-after-cancel` | List all reservations for jane@example.com | `gap-post-cancellation-state` |
| `p12-check-over-capacity` | Check availability at restaurant `{restaurant_id}` for 30 people on 2025-03-15 at 7:00 PM | `gap-check-availability-party-size` |
| `p13-list-by-phone` | List all reservations for +1-555-987-6543 | `gap-list-reservations-user-id` |
| `p14-check-bad-datetime` | Check availability at restaurant `{restaurant_id}` for 4 people on the 45th of Foguary at 25:00 | `gap-argument-validation` |
| `p15-search-bad-price-tier` | Find restaurants in Boston with price tier 9 | `gap-argument-validation` |
| `p16-place-over-capacity` | Book a table at restaurant `{restaurant_id}` for 2025-03-15T19:00:00, party of 40. Name: Overflow Test, Phone: +1-555-000-0002, Email: overflow@example.com | `gap-place-reservation-failures` |
| `p17-search-city-catalogue` | List every restaurant you know about in Boston, with cuisine and price tier for each | `gap-restaurant-catalogue` |

`p12`, `p14` and `p16` use `{restaurant_id}` rather than a literal `rest_001` so
they inherit `substitute()`'s discipline: if `p01-search` never observes an id
they skip, rather than run against an authored one.

**The gap ids live here and never in the capture.** An earlier attempt at this
capture used a bespoke driver that wrapped each invocation in an MLflow span
carrying `label` and `targets_gap` attributes, which put the string
`gap-post-cancellation-state` inside the trace data. Admitting that would have
let `rb-extract` read the analysis instead of deriving it, and every gate would
still have passed — schema-valid, references resolvable, no finding anywhere. It
was caught by grepping the file before admitting it, not by any check. That
driver's output was discarded; this file is the harness's.

The same wrapper did quiet second damage worth recording, because it is not
obvious: it made MLflow name each trace after the wrapper span rather than
`LangGraph`, and consequently record **no `request_preview`** — which is exactly
the field `digest.py`'s `request_text` heuristic reads. The user's own utterance
would have been invisible to `rb-triage`, reproducing the blindness the first
run's `def-multi-turn-utterances` deficiency complained about. One instrumentation
choice both injected the answer and hid the question.

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
| `p11-list-after-cancel` | captured | `list_reservations` |
| `p12-check-over-capacity` | captured | `check_availability` |
| `p13-list-by-phone` | captured | `list_reservations` |
| `p14-check-bad-datetime` | captured | *(none)* |
| `p15-search-bad-price-tier` | captured | *(none)* |
| `p16-place-over-capacity` | captured | `check_availability` |
| `p17-search-city-catalogue` | captured | `search_restaurants` |

All seventeen captured; none skipped, errored, or `no-trace`.

Three outcomes are results rather than failures, and each answers its gap
differently from how the gap expected:

- `p14` and `p15` called **no tool at all**. The agent rejected "the 45th of
  Foguary at 25:00" and "price tier 9" in its own turn, before dispatching
  anything. `gap-argument-validation` asked what the *tools* reject; the observed
  answer is that these arguments never reach them.
- `p16` stopped at `check_availability` and never attempted
  `place_reservation`, the same shape `p08-place-unknown` showed in the first
  capture. `gap-place-reservation-failures` asked what happens when that call
  fails; the observed answer is that the agent's guard stops it earlier. Two
  independent bad-booking shapes now attest that guard.
- `p11` returned `[]`. Cancellation removes the record; a cancelled reservation
  does not linger with a status. `reservation_61e0d19f75d1` is present in
  `p04-list`, receipted in `p05-cancel`, and absent in `p11`.

## Capture history

The harness was launched twice. The first launch **hung** on `p03-place`'s LLM
call and was killed after roughly fifty minutes of silence; it wrote no output
file, because `capture_trajectories` writes only after every prompt completes,
so there was nothing to select from and nothing to discard. The second launch
produced this file.

That is an infrastructure stall, not a re-roll: no prompt was re-run to obtain a
better trace, and no trace from a first attempt was compared against a second.
The single-pass rule holds for this file.

The stall has a cause worth recording as a finding about the target rather than
about the harness. `graph.py` builds `ChatOpenAI` with `temperature=0` and
**no `timeout` and no `max_retries`**, so a stalled upstream request hangs the
agent indefinitely with no recovery. The second launch was given a wall-clock
`timeout 1500` for exactly that reason. A suite built from this corpus arguably
ought to cover the behaviour; it is recorded here because the capture harness
inherits the agent's own client construction and therefore inherits the defect.

## Single-pass rule

Captured in one pass over the full seventeen-prompt list. No prompt was re-run
to obtain a better trace, and no value was filled that was not observed.
