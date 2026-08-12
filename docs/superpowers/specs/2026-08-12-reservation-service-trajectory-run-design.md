# Reservation-Service Trajectory Run — Design

**Date:** 2026-08-12
**Status:** Proposed design, awaiting approval. No capture has been run yet; the
`/tools/list` and determinism findings in §3 were measured today against the
target's source, the litellm proxy in §5 was reachability- and tool-call-tested,
and everything in §8 is a prediction recorded before the fact.
**Author:** Jonathan Bnayahu (with Claude)

## 1. What this is

The first run of rubrica against a real target under a **realistic evidence
boundary**: the tools are treated as remotely installed, so their source is not
available, and what stands in for it is externally obtainable information plus
observed trajectories.

The target is the `reservation_service` A2A agent from the `rossoctl` examples
repository, whose five capabilities are MCP tools served by a sibling
`reservation_tool` MCP server.

This is the run §11 of
[`2026-08-06-skill-based-test-generator-design.md`](2026-08-06-skill-based-test-generator-design.md)
calls for, against a different target than the `aap2` one named there.

### The question

Does trajectory evidence carry the output knowledge that source access would
otherwise supply — well enough to close gaps a source-only run left open, and
without inheriting the errors that documentation introduces?

That is answerable rather than rhetorical because a source-heavier run already
exists to compare against, and its failures are on record before this run
starts. §8 pre-registers the predictions.

## 2. The prior run, and why it is a control rather than an arm

`runs/run-20260812-074017` was built earlier the same day and taken through
`reconcile` in six dispatches for **$3.83** measured — five extract members at
$0.39–$0.54 each and `reconcile` alone at $1.49, since the barrier reads every
claims file. Budget this run's `reconcile` higher again: it barriers over six.
Its five inputs were:

| Input | Origin | Tier |
|---|---|---|
| `agent-graph-py` | `a2a/.../graph.py` | agent source |
| `agent-notes-md` | `a2a/reservation_service/README.md` | agent docs |
| `mcp-tools-py` | `mcp/reservation_tool/reservation_tool.py` | **tool source** |
| `mcp-entities-py` | `mcp/reservation_tool/schemas.py` | **tool source** |
| `mcp-tool-notes-md` | `mcp/reservation_tool/README.md` | tool docs |

All five were sha256-identical to their rossoctl originals, and the tool source
was demonstrably *read*: `mcp-tools-py` produced 15 `outcome_class` claims
citing `except ValueError` branches at specific line numbers in the MCP server.

That input set is unrealistic for the scenario this project cares about — you do
not normally have a remote tool's server source. But the run is not wasted,
because of what it *failed* to do with that access. It had the full tool
interface and still raised five gaps, every one of them marked
`blocks: ["propose"]`:

- `gap-search-restaurants-empty`
- `gap-check-availability-not-found`
- `gap-check-availability-empty`
- `gap-place-reservation-not-found`
- `gap-list-reservations-empty`

Each asks an **output** question, and each is answerable only in
`providers/mock.py` — the file that was never registered. `reconcile` saw
`except ValueError → {"error": ...}` and correctly reported that nothing
connects the trigger to the handler, because the trigger lived in the withheld
file.

So the control establishes: **tool interface source does not substitute for
observations.** That is a genuine negative result and it is what makes this
run's question worth asking.

Three tiers, made explicit, since conflating the middle two is what made the
earlier run look like the wrong experiment when it is really the wrong *arm*:

| | Agent source | Tool interface | Tool behaviour | Trajectories |
|---|---|---|---|---|
| Control (`run-20260812-074017`) | yes | yes | no | no |
| **This run** | yes | external only | no | yes |

## 3. The evidence boundary, measured

The boundary is not asserted, it was probed. Loading the FastMCP app in-process
and calling `list_tools()`, then serialising each tool through
`to_mcp_tool()`, gives what a `/tools/list` call over the wire would give.

**Inputs are fully specified.** All five tools, with parameter names, types,
required/optional status, defaults, the MCP behavioural annotations
(`readOnlyHint`, `destructiveHint`, `idempotentHint`), the extended docstring
prose — including `place_reservation`'s idempotency paragraph — and human
parameter descriptions carrying example values:

```
search_restaurants.city            (e.g., "Boston", "New York")
check_availability.restaurant_id   (e.g., "rest_001")
place_reservation.date_time        (e.g., "2025-03-15T19:00:00")
place_reservation.phone            (e.g., "+1-555-123-4567")
cancel_reservation.reservation_id  (e.g., "reservation_abc123")
```

**Outputs are entirely unspecified.** All five `outputSchema` values are the
same opaque wrapper:

```json
{"properties": {"result": {"type": "string"}},
 "required": ["result"], "type": "object",
 "x-fastmcp-wrap-result": true}
```

This is the load-bearing fact of the whole design. `/tools/list` says exactly
how to *call* each tool and nothing at all about what comes *back*. Since all
five control gaps are output questions, `/tools/list` answers none of them, and
the trajectories are the only source of output knowledge. That is the split the
experiment needs, and it arrived for free rather than by construction.

Two consequences worth stating separately.

**The entity shapes are withheld too.** With `outputSchema` uninformative,
`Restaurant`, `Reservation`, `AvailabilitySlot` and `CancellationReceipt` must
be reconstructed from observed response bodies rather than read off
`schemas.py`. Recovering an entity's fields from trajectory outputs is a
strictly harder task than transcribing a pydantic model, and no previous run has
attempted it.

**One fact is contradicted three ways, and only observation is right.** The
agent README shows `res_12345`. `/tools/list` shows `reservation_abc123`. The
implementation produces `reservation_<12 hex>`, from
`sha256(confirmation_code)[:12]`. Two registered inputs disagree with each other
and both differ from reality. The control hedged this correctly as
`gap-reservation-id-format`, citing its single example. This run should surface
it as a *contradiction between sources* and settle it from spans — a sharper
test of `rb-reconcile` than the control could offer.

For the record, two more implementation facts the trajectories will expose and
no registered input states: `check_availability` is deterministic
(`sha256(restaurant_id + slot_time + party_size)`, available when
`hash_val % 10 < 7`), and `refund_policy` is actually
`"No charge for cancellations made more than 24 hours in advance"`, not the
`"No charge for cancellations"` default declared in `schemas.py` and carried as
a wrong prose invariant in the control's world model.

## 4. Inputs

Fifteen, and the fan-out is therefore fifteen `rb-extract` dispatches — not the
six (five documents plus one `trajectories.json` array) originally planned
here. §7 below records the measurement that forced the split.

| Staged as | Kind | Origin |
|---|---|---|
| `agent-graph.py` | `source_code` | `a2a/.../src/reservation_service/graph.py` |
| `agent-server.py` | `source_code` | `a2a/.../src/reservation_service/agent.py` |
| `agent-notes.md` | `design_doc` | `a2a/reservation_service/README.md` |
| `tools-list.json` | `mcp_tool_schema` | captured `/tools/list` |
| `mcp-tool-notes.md` | `design_doc` | `mcp/reservation_tool/README.md` |
| `trajectory-p01-search.json` … `trajectory-p10-cancel-unknown.json` (10 files) | `trace` | captured, one file per run — split mechanics in the fixture README's "Staging for intake" section |

`agent.py` is included because `get_agent_card()` is the only machine-readable
place the agent describes its own advertised skills, which is part of the
target's public interface rather than plumbing.

**Excluded, deliberately:** `reservation_tool.py`, `schemas.py`,
`providers/base.py`, `providers/mock.py`. The first three are the tool interface
that `/tools/list` legitimately replaces; the last is the behavioural answer key.

`intake.classify` handles all fifteen without help: `.py` → `source_code`,
`.md` → `design_doc`, a `{"tools": [...]}` document → `mcp_tool_schema`, and —
since each staged trace file is a single trace object, not an array — a JSON
object carrying a top-level `trace_id` → `trace`.

### Staging, and why it is not optional

Inputs are copied to a staging directory and `--input` points there, not at the
rossoctl tree. `manifest.inputs[].source_path` is written by `intake` and read by
no code in the repository, but it *is* reachable from a dispatched stage, and
neither `dispatch-stage.sh`'s `permissions.deny` list nor its sandbox
`allowRead` covers the rossoctl checkout. A stage following `source_path` into
the original tree could walk to `providers/mock.py`.

Staging does not, by itself, make that the only path in. Measured after
capture (`jq '.[0].info.trace_metadata' trajectories.json`): every one of the
ten trace files carries `info.trace_metadata["mlflow.source.name"]` set to the
absolute path of `tests/fixtures/reservation-trajectories/capture_harness.py`
— an MLflow-stamped provenance field, not something the harness added on
purpose. That file's `TOOL_DIR` and `AGENT_SRC` constants (lines ~38-39) name
the withheld rossoctl tree, so a staged trace is a **two-hop pointer to the
answer key**: artifact → harness → `providers/mock.py`.

What actually blocks both paths is `dispatch-stage.sh`'s `DENY` array (around
line 149), which lists `$REPO/tests` by name — covering the harness file
itself, since it lives under `tests/fixtures/`. The rossoctl checkout the
harness points at is covered by neither the permissions layer nor the sandbox,
as already noted above; the guarantee holds because the deny list keeps a
dispatched stage from ever reading the pointer in the first place, not because
staging removed it. The read audit for this run was clean on all fifteen
slices: no extract member is recorded reading `source_path`,
`mlflow.source.name`, or anything under the rossoctl tree. No leak was
observed.

Staging also renames: both READMEs would otherwise slug to `readme-md` and
`readme-md-2`, which is ambiguous in a fan-out. Extensions must survive the
rename because `classify` keys off the suffix.

A provenance note mapping staged name to original path is kept **outside** the
staging directory, since it names the wider source tree.

### The tool README carries some behaviour, and it stays anyway

`mcp/reservation_tool/README.md` has a **Mock Data** section listing the
restaurant catalog by city and stating the availability determinism rule. That
is information about the withheld implementation.

It stays, unedited. It is genuinely externally available if the README is, a
demo server documenting its own dataset is a real situation, and trimming an
input would put the spec's author into the data path — the failure this whole
design is arranged to avoid. The consequence to expect is that the world model
will know the catalog without having observed it.

## 5. Capture harness

The harness lives in the lab directory, not in `scripts/`. It depends on
rossoctl paths and on LangChain packages that rubrica does not have, so it is
not shippable here.

Environment, in a throwaway `uv` venv: `langgraph`, `langchain-core`,
`langchain-openai`, `langchain-mcp-adapters`, `mcp`, `pydantic-settings`,
`mlflow`. Not `a2a-sdk`, `uvicorn`, `python-keycloak`, or the OTel exporters.

`graph.py` is cleanly separable from `agent.py`: `get_mcpclient()` and
`get_graph(client)` are module-level, and `agent.py` only wraps them in A2A
plumbing. So the harness drives `graph.ainvoke({"messages": [...]})` directly
and skips the A2A HTTP layer entirely, which is a real full agent turn — LLM
planning, tool calls, final answer — without a server to stand up.

Flow:

1. Start the MCP server locally on `:8000` (`fastmcp` + `pydantic` only).
2. Capture `/tools/list` from the same server build that serves the
   trajectories. It need not be the same *process*: `list_tools()` reads the
   registered tool definitions and never touches `MockProvider`, so it cannot
   perturb the `_reservation_counter` ordering that §11 depends on.
3. Point `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` at the litellm proxy with
   `Azure/gpt-4.1`. The agent already reads all three and builds a `ChatOpenAI`,
   so no code change is needed. Verified today: tool calls pass through the proxy
   intact, returning a well-formed `tool_calls` array with correctly extracted
   arguments.
4. `mlflow.langchain.autolog()`, then loop the §6 prompt list.
5. Export each trace.

MLflow produces the traces. They are not assembled by hand — that is the point
of the harness existing at all.

## 6. The prompt list, and the single-pass rule

Ten prompts. Five happy paths, one per capability. Five chosen to drive exactly
the output questions the control could not answer.

| # | Aim | Control gap addressed |
|---|---|---|
| 1 | search, Italian in Boston | — |
| 2 | check availability, valid id and date | — |
| 3 | full booking: search → check → place | — |
| 4 | list reservations for a known email | — |
| 5 | cancel a reservation just created | — |
| 6 | search with no matches | `gap-search-restaurants-empty` |
| 7 | check availability, plainly invalid id | `gap-check-availability-not-found` |
| 8 | place reservation, plainly invalid id | `gap-place-reservation-not-found` |
| 9 | list reservations, email with none | `gap-list-reservations-empty` |
| 10 | cancel a nonexistent reservation id | — |

Prompts 7 and 8 must name an obviously-invalid id (`rest_999`) explicitly, or
the model will search first and never drive the error path.

**Prompts 3, 4 and 5 form a chain and cannot be issued independently.** Prompt 4
needs an email that actually has a reservation, and prompt 5 needs a
`reservation_id` that exists — both of which only prompt 3 creates. The harness
therefore captures prompt 3's `place_reservation` span output, extracts the
`reservation_id` and guest email from it, and substitutes them into prompts 4 and
5 before issuing them. That substitution is mechanical string handling over an
observed response, not authorship: the harness never supplies a value it did not
first read out of a span. Prompt 10 is the deliberate contrast — a syntactically
plausible id that was never created.

No prompt targets `gap-check-availability-empty`. There is no input that reliably
produces an all-unavailable day, which is why P2 predicts it stays open.

**The rule: fixed list, single pass, record everything — including runs where
the agent did not call the tool it was aimed at.** No re-rolling until a trace
comes out the desired shape. Re-rolling is selection bias, and it reinstates the
harness author as the oracle by the back door. If a path is never driven, the
corresponding gap stays open, and that is a result rather than a defect.

One gap is predicted to survive: `gap-check-availability-empty` needs *every*
slot unavailable, and with availability at `hash_val % 10 < 7` an all-false day
is unlikely to arise by chance. Recorded here so it is a prediction rather than
a later excuse.

## 7. Trace format, and the one additive change

MLflow's trace JSON is `{"info": {...}, "data": {"spans": [...]}}`.
`intake.classify` looks for `spans` or `trace_id` at the *top* level, so
MLflow-native output would classify as `other`.

Rather than reshape MLflow's document — which would put the harness in the data
path — the harness **copies `info.trace_id` to a top-level `trace_id`**. It is
additive, lossless, one line, and it makes `classify` return `trace`.

The mirror is not optional here, because the file is a JSON *array* of traces
and `classify`'s list branch inspects `payload[0]` for `spans` or `trace_id`. A
raw MLflow trace has neither at that level — they are at `info.trace_id` and
`data.spans` — so without the mirror the array classifies as `other`.

Three MLflow 3.15.1 behaviours were measured today and are load-bearing for the
harness. The field is `info.trace_id`; MLflow 3 renamed it from `request_id`, so
older examples are wrong. The filesystem tracking backend is in **maintenance
mode** and makes `get_trace()` return `None` with only a warning, so the harness
must set a `sqlite:///` tracking URI. And trace logging is **async**, so
`get_trace(trace_id, flush=True)` is required — without `flush=True` the call
returns `None` for a trace that was just written.

`other` would in fact be tolerable, since classification is documented as a
heuristic that seeds the extract stage's expectations and that the skill is free
to disagree with. The mirror is preferred because it costs nothing and loses
nothing.

All ten traces go into one `trajectories.json` array, so one extract member sees
every run. That was the plan as written here, and `trajectories.json` remains
the authentic, unsplit capture on disk — nothing below changes what was
recorded, only how it is staged for the fan-out.

**Measured after capture, and load-bearing:** the combined array is **~228k
tokens**, larger than a 200k context window, so no single `rb-extract` member
could in fact read it — the paragraph above describes a dispatch that cannot
happen. Almost all of that size is MLflow redundancy — `spanInputs`/
`spanOutputs` repeat the entire message history at every step, and
`mlflow.chat.tools` repeats the tool schema in all 100 spans, which is
`tools-list.json` duplicated a hundred times. Stripping those attributes was
considered and rejected: it would have cut the file by roughly 90% and kept
the single-input plan intact, but it would have put the spec's author inside
the data path, and "deduplicating" is one short step from curating. A human
ruling instead split the array into one file per trace, mechanically, in array
order — fifteen registered inputs (five documents plus ten traces) rather than
six, and ten `rb-extract` dispatches over the traces rather than the one this
section originally called for. The fixture README's "Staging for intake"
section carries the split mechanics and the isolation consequence, which runs
opposite to what this section assumed: ten members, each seeing exactly one
run and none seeing a sibling, is a *stronger* fan-out isolation test than one
member reading all ten would have been — not a weaker one.

## 8. Pre-registered predictions

Recorded before capture, so the run can be wrong.

| # | Prediction |
|---|---|
| P1 | Four of the control's five gaps close from observation. |
| P2 | `gap-check-availability-empty` does **not** close (§6). |
| P3 | `reservation_id` is characterised as `reservation_<hex>`, not `res_<number>`, and the README/`tools-list` disagreement surfaces as a contradiction rather than a silent pick. |
| P4 | `refund_policy` is characterised from the observed string, not `schemas.py`'s default — which this run cannot see. |
| P5 | All five capabilities are recovered with correct required/optional parameter sets, from `tools-list.json` rather than from `def` lines. |
| P6 | At least one entity (`Reservation` or `Restaurant`) is reconstructed with a field set derived from observed response bodies. |

P5 and P6 are the two the control got for free and this run has to earn. P6 is
the one most likely to fail outright, since nothing instructs a stage to mine
entity shapes out of span outputs.

## 9. Comparison instrument

`rubrica diff-runs --a <control> --b <this run>` reports comparability plus
stage diffs at `1b_capabilities`, `2_goal_cell_claims` and `6_task_ids`. The two
runs are incomparable by construction — different input sets — and `diff-runs`
reports the stage diffs anyway, by deliberate design: its docstring notes that
an incomparable pair is often the interesting one and that hiding the diff would
defeat the localisation the tool exists for.

Alongside it, the P1–P6 checks above are read by a person against the world
model, and `denominator.capability_cells` is compared to the control's **16**.

## 10. Provenance

The captured `tools-list.json` and `trajectories.json` are committed to
`tests/fixtures/reservation-trajectories/` with a README recording the model,
the date, the proxy, the rossoctl git SHA, and the verbatim prompt list.

This follows the `tests/fixtures/<name>/recorded/` precedent, where committed
live output makes an observation reviewable as a diff instead of mystery JSON.
Without it the experiment is unreproducible: re-capturing would draw fresh LLM
spans and a fresh `confirmation_code` sequence, so a later reader could not tell
a pipeline change from a capture change.

A light guard test asserts each committed file parses, that the trajectory array
holds ten traces each with at least one span, and that at least one trace carries
an error response. That is enough to catch silent corruption without pinning
prose that an innocuous re-capture would break.

## 11. Failure modes that are evidence, not bugs

`graph.py`'s `assistant` node mutates `state["messages"]` *and* returns the
state. With `MessagesState`'s `add_messages` reducer this may duplicate
messages. If the traces look odd here, that is plausibly the target's own defect
appearing in observation, which is legitimate evidence about the target and must
not be cleaned up in the fixture.

`place_reservation`'s `confirmation_code` is `RES{counter:06d}` from a
**process-local** counter, so codes depend on server-process ordering. Capture
must run in one server process, in list order, and the README must say so.

Timestamps (`created_at`, `cancelled_at`) come from `datetime.now()` and are the
only genuinely non-reproducible field in the tool responses. Everything else on
the tool side is deterministic given fixed inputs.

## 12. Not in scope

- Re-running the control. It stays as-is on disk.
- Standing up A2A, Keycloak, MLflow's tracking server, or Docker. §5 needs none
  of them.
- Any change to rubrica source, schemas or skills. If this run exposes a skill
  defect, that is a finding for a separate change, not a patch folded into the
  experiment.
- Registering `providers/mock.py` to close a surviving gap. Doing so would
  improve the suite and destroy the measurement.
