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
| ~~P3~~ | **Withdrawn as invalid on 2026-08-13 — see the retraction below.** ~~`reservation_id` is characterised as `reservation_<hex>`, not `res_<number>`, and the README/`tools-list` disagreement surfaces as a contradiction rather than a silent pick.~~ |
| P4 | `refund_policy` is characterised from the observed string, not `schemas.py`'s default — which this run cannot see. |
| P5 | All five capabilities are recovered with correct required/optional parameter sets, from `tools-list.json` rather than from `def` lines. |
| P6 | At least one entity (`Reservation` or `Restaurant`) is reconstructed with a field set derived from observed response bodies. |

P5 and P6 are the two the control got for free and this run has to earn. P6 is
the one most likely to fail outright, since nothing instructs a stage to mine
entity shapes out of span outputs.

### Stage 02 propose, round 1 — P7–P9, recorded 2026-08-13

P1–P6 are about what `rb-extract` and `rb-reconcile` recover from the captured
evidence, and were recorded before capture. P7–P9 are a separate set, about what
`rb-propose` does with the resulting world model, and were recorded after gate 1
passed and before the dispatch — into `decisions.md`, which turned out to be the
wrong place; see §13.

Scored against `runs/run-20260813-064150`, round 1: 6 scenarios, `validate
--stage propose` 0, `check-refs` 0, read audit clean, $0.668 over 8 turns.

| # | Prediction | Verdict |
|---|---|---|
| P7 | `propose` stops at `max_scenarios: 6` and names the holes it left, rather than proposing past the cap or covering 6 of 19 silently. | **Held.** It named `oc-search-empty` and `oc-list-empty` as "deferred past the `max_scenarios: 6` cap for this round — a decision for round 2 or the orchestrator, not a defect." |
| P8 | Every scenario carries `status: "proposed"` and cites one of the world model's five `goal_id`s; none invents a goal, capability or outcome class. | **Held.** All 6 `proposed`, 5/5 goals covered, no `hole_ref` naming anything undeclared. |
| P9 | The four gaps do **not** stop it targeting the cells they concern, because the `blocked_by_gap` refusal condition keys off a coverage report's hole `reason` and round 1 has no coverage report. | **Failed, in the better direction the prediction anticipated.** |

P9 is the result worth keeping. Nothing in the prompt obliged it: the refusal
condition it acted on is written against an artifact that does not exist in round
1. It made the correspondence from prose instead, and the correspondence is
sound — each `underspecified` outcome class restates a gap's `unknown` nearly
verbatim, `oc-place-underspecified` and `gap-place-unknown-restaurant` both
resting on the same `rest_999` trace where `check_availability` failed before
`place_reservation` was reached. It declined all five and said so.

One imprecision inside that, recorded because the substance being right is what
makes the wording easy to miss: it called those cells "`blocked_by_gap` per the
world model's `gaps` list." `blocked_by_gap` is a *coverage-report* hole reason
that additionally requires a `gap_id`, and no artifact assigns it in round 1 —
the label was borrowed one stage early, and the world model's gaps carry no cell
references for it to have been read off. No fix follows: pressing the prompt to
withhold judgment until a coverage report exists would trade a correct refusal
for a confabulated scenario, which is the trade §11 already rules against.

**This run cannot reach `converged`,** and the reason is not the five gap-blocked
cells. `rb-score` defines `converged` as no *closable* hole remaining, "whether
or not the matrices read 100%". `oc-search-empty` and `oc-list-empty` are
closable — both were observed, in trajectories p06 and p09 — and the scenario cap
is spent, so a closable hole survives to the round cap. Expect `continue` at
round 1 and `halted_no_progress` at round 2.

### Stage 03 score, round 1 — P10–P13, recorded 2026-08-13 before the dispatch

Recorded here rather than in `decisions.md`, per §13, and committed in `f7af24e`
before the dispatch so git dates the predictions ahead of the result.

Scored against `runs/run-20260813-064150`, round 1: `validate --stage score` 0,
`check-refs` 0, `latest.json` byte-identical to `round-1.json`, all six scenarios
promoted `proposed` → `active` with none folded, $0.860 over 18 turns.

| Result | |
|---|---|
| `capability_matrix` | 7/14, `pct` 0.5, all 14 cells enumerated |
| `goal_matrix` | 3/5, `pct` 0.6 |
| `progress` | `new_cells_this_round` 7, `rounds_without_progress` 0 |
| `verdict` | `continue` |

P10 and P11 are one question split in two, and it is the question stage 02 raised:
`rb-propose` declined five cells as gap-blocked using a term that only `rb-score`
is entitled to assign. Now the stage that owns the term gets to assign it, and the
interesting failure is not getting it wrong — it is getting it *too broadly*.

| # | Prediction | Verdict |
|---|---|---|
| P10 | The five `underspecified` cells appear as holes with `reason: "blocked_by_gap"` and a `gap_id` that resolves in the world model's `gaps`. All five have a candidate: `oc-place-underspecified` → `gap-place-unknown-restaurant`, `oc-check-underspecified` → `gap-check-availability-empty`, `oc-cancel-underspecified` → `gap-cancel-repeat`, and both `oc-search-underspecified` and `oc-list-underspecified` → `gap-validation-errors`. | **Held**, and the mapping matched all five exactly. |
| P11 | `oc-search-empty` and `oc-list-empty` get `reason: "not_yet_attempted"`, **not** `blocked_by_gap`. Both were observed — trajectories p06 and p09 — so no gap blocks them; they are open only because the scenario cap ran out. | **Held.** |
| P12 | `verdict` is `continue`: closable holes remain (P11's two), this round added cells, and round 1 is below `max_rounds: 2`. | **Held.** |
| P13 | `capability_matrix.total` is 14 with `covered` 7, and `goal_matrix` is 5/5. No scenario is folded to `duplicate`: `scn-005` and `scn-006` are the closest pair and differ by outcome class, which Method step 2 rules is not one test. | **Failed in part** — the goal half. |

P11 is the load-bearing one and it held. Marking all seven uncovered cells
`blocked_by_gap` would have produced `converged` — every remaining hole
unclosable, nothing left to try — and that verdict would be wrong while looking
like success. It is the denominator-shrinking failure the `rb-score` prompt warns
about, arriving through the hole `reason` rather than through the matrix. Taken
with P10, the term `rb-propose` borrowed a stage early was then assigned correctly
and *narrowly* by the stage that owns it.

**P13's goal half failed, and the prediction was wrong rather than the stage.**
`goal_matrix` came out 3/5, not 5/5. Goals carry `expected_hop_depths` — a
*required* field of the world-model schema, which `rb-reconcile` had filled in —
and `rb-score` applied it exactly:

| Goal | expected | present | covered |
|---|---|---|---|
| `goal-check-availability` | `[1, 2]` | `[1]` | false |
| `goal-place-reservation` | `[2, 3]` | `[2]` | false |

That is the partial-row rule from the prompt's Method step 5 doing precisely what
it is for: a goal exercised at one depth of two is not covered, because the
multi-hop half is the half the suite exists to probe. `rb-propose` had reached
every goal once; reaching a goal is not covering it.

Two consequences.

**There are four closable holes, not two.** `oc-search-empty`, `oc-list-empty`,
`goal-check-availability` and `goal-place-reservation`, all `not_yet_attempted` —
against a `max_scenarios: 6` that is already spent. Round 2's `propose` hits its
cap refusal and adds nothing, so round 2 scores `halted_no_progress`. The §8
prediction above that this run cannot converge holds, with a larger margin than
stated.

**And a note on my own predictions.** P13 is the second in this run, after the
retracted P3, to be wrong by asserting against a field the artifacts already
carry. Both would have been caught by reading the schema before writing the
prediction rather than after reading the result. Recorded because a pre-registered
prediction's whole value is that it was written in ignorance of the outcome, not
in ignorance of the contract.

### Round 2 — P14–P17, recorded 2026-08-13 before the dispatch

Gate 2 raised `max_scenarios` 6 → 10 and left `max_rounds` at 2. The new cap is
derived: 6 open scenarios plus the 4 `not_yet_attempted` holes. Nothing else in
the manifest changed. `converged` stays reachable at round 2 despite round 2 being
`max_rounds`, because `rb-score`'s verdict ordering puts `converged` above
`halted_round_cap`.

**Round 2 is the first time in this project's history that a stage is dispatched
with a coverage report to read.** Every earlier `propose` ran round 1, where
`coverage_latest` is absent and the skill says to treat every cell as open. So
P14 tests the `blocked_by_gap` refusal condition with the artifact it was written
against — the same condition round 1 acted on from world-model prose without one.

| # | Prediction | Verdict |
|---|---|---|
| P14 | `propose` targets exactly the four `not_yet_attempted` holes and re-proposes against none of the five `blocked_by_gap` cells. | |
| P15 | The two goal holes are closed by scenarios whose `hop_depth` is the missing member of `expected_hop_depths` — 2 for `goal-check-availability`, 3 for `goal-place-reservation` — rather than by another depth-1 scenario that leaves the row partial. | |
| P16 | `scn-001`–`scn-006` are untouched: no renumbering, no status change from `active`, no field edited. New ids continue at `scn-007`. | |
| P17 | Round 2's `score` returns `converged`, with `capability_matrix` 9/14 and `goal_matrix` 5/5. Conditional on P14 and P15 holding; if `propose` closes only some holes, `halted_no_progress` or `halted_round_cap` follows instead. | |

P15 is the sharp one. Closing a *goal* hole is not the same shape of work as
closing a cell: the hole names a depth, not a capability×outcome pair, and the
scenario has to be a genuinely longer chain — search-then-check for depth 2,
search-then-check-then-place for depth 3. A depth-1 scenario against the same
goal would add a row member, change nothing about coverage, and look like
progress.

### P3 withdrawn as invalid — 2026-08-13

P3 was reported as unmet after three runs. It should never have been written, and
the retraction belongs here rather than in a later document, because the failed
prediction is what a reader of this section would otherwise carry forward.

**No claim in any of the three runs asserts an id format.** The three the
prediction treated as competing are, verbatim from
`runs/run-20260813-064150/01-claims/`:

- `tools-list-json`, kind `entity`: "`cancel_reservation` takes a required
  `reservation_id` parameter (string): a unique reservation identifier,
  **e.g.** `"reservation_abc123"`."
- `agent-notes-md`, kind `capability`: "The agent supports natural-language
  requests to cancel a reservation by its reservation id, optionally with a
  stated reason, **e.g.** `"Cancel reservation res_12345 because plans
  changed"`."
- `trajectory-p05-cancel-json`, kind `outcome_class`: one observed call with
  `reservation_id: "reservation_61e0d19f75d1"` returning success.

Two illustrative examples and one observed value. Two `e.g.`s differing is not a
disagreement about the target, it is two documents choosing different
placeholders — and `rb-reconcile`'s Method says a contradiction is "a real
disagreement about the target", explicitly excluding sources that "agree on the
fact and disagree only on a bookkeeping label". So all three runs reporting zero
contradictions here were **correct refusals**, not a replicated failure.

**And there was nowhere for the format to live even had a claim asserted one.**
`entity.fields` items permit exactly `name` and `type`, with
`additionalProperties: false`.

That is the parked limitation `2026-08-06-skill-based-test-generator-design.md`
already records — the world model has no representation for a field's value
domain, and its ruling says in as many words: *do not raise findings that require
a stage to ground a value against claims; no artifact carries the domains.* This
prediction did exactly that. The parked table's own row now carries a note
pointing back here, because a ruling that gets violated by the next spec written
against it is a ruling that was not visible enough.

What `rb-reconcile` did do in this area is the counter-evidence: it recorded
`Each reservation has a unique id within the reservations collection` — an
invariant the schema *can* express — plus two inferred rules, that
`restaurant_name` is resolved server-side from `restaurant_id`, and that
`guest_name`/`guest_phone`/`guest_email` echo the arguments passed to
`place_reservation`.

**No fix follows from this.** A prompt change pressing `rb-reconcile` to raise
contradictions from illustrative examples would manufacture disagreements, which
is the quantifier-satisfaction shape already suspected behind the `oc-find-error`
artefact recorded in `rb-reconcile/exercise.md`.

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

## 13. The run's own answer key, and where predictions live

Two mistakes were made in running stage 02 on 2026-08-13, both about where a
prediction is written down rather than about the pipeline. Recorded here because
the second one nearly invalidated a measurement, and the shape recurs for anyone
scoring a stage by hand.

**Predictions belong in this file, not in `decisions.md`.** P7–P9 were recorded
into the run's `decisions.md` — the right instinct (on disk before the dispatch,
so the reading cannot be hindsight) with the wrong destination. `decisions.md`
lives *inside the run directory*, and `scripts/dispatch-stage.sh` granted
`Read(<run>/**)`. P7 and P8 state, in plain language, what the stage is expected
to do: stop at the cap, name the deferred holes, use `status: "proposed"` and
real `goal_id`s. A dispatch that read them would have produced a worthless
observation and a passing one.

It came closer than it should have. The transcript of the first (killed) attempt
shows the stage running `ls -la` in the run directory with that file present. It
was one `Read` from its own answer key, and what stopped it was an unrelated
premature kill.

**The fix is in the harness, not in the procedure.** `dispatch-stage.sh` now
denies three run-local paths in both settings scopes — `decisions.md`,
`07-report.json`, and `measurement/`. The set is derived rather than guessed: the
union of every skill's Contract `reads` is `claims_dir`, `coverage_latest`,
`expected`, `input_file`, `manifest`, `scenarios`, `seed`, `verdict` and
`world_model`, and those three are what a run holds that no stage may name. They
are also the three that are *about* the stages — an orchestrator log, a smoke
report, and the human review surface — which is what makes them answer keys
rather than merely out-of-scope.

`RUBRICA_PRINT_SETTINGS=1` writes both settings files and exits before
dispatching, so `tests/unit/test_dispatch_harness.py` can assert the deny rules
without spending a model call. A test that greps the script's source instead
would pass on a rule that is present and unreachable, which is the
substring-of-message weakness the parent spec's §6 names.

**Both layers were then measured against this rule, and both engaged.** Three
dispatches against a probe run holding a canary line in `decisions.md` and an
in-contract `01-world-model.json`, at Claude Code 2.1.231, $0.24 in total:

| Probe | Result |
|---|---|
| `Read` the world model, then `decisions.md` | world model returned; `decisions.md` refused — *"File is in a directory that is denied by your permission settings."* |
| `python3 -c "open('<run>/decisions.md').read()"` via Bash | `PermissionError: [Errno 13] Permission denied` |
| `python3 -c "open('<run>/01-world-model.json').read()"` via Bash | contents returned |

The third is the control, and it is what makes the second mean anything: a
sandbox blocking *every* Bash file read would produce the same `PermissionError`
without isolating anything. The canary string appears zero times across all three
transcripts.

The second result contradicts what `dispatch-stage.sh` has said since it was
written — that the sandbox layer did not engage on this machine, measured with
`bubblewrap` 0.9.0 working standalone. That measurement was taken at 2.1.227
against a *directory* deny entry. This one is at 2.1.231 against a *file* entry.
Which of the two differences accounts for it is unknown and was not chased; the
comment now records both observations rather than replacing one with the other.

**What this still does not fix.** Two measurements of one rule on one machine are
not a general guarantee, and nothing here touches the case the parent spec's §8
calls the weakest link: a fan-out member reading a *sibling's* slice, which is
in-contract by path and produces a byte-identical artifact either way.
`scripts/audit-reads.sh` over the transcript remains the instrument. The deny
rules narrow the accident.

## 14. What the score dispatch's read audit showed

Three observations from `scripts/audit-reads.sh` over the `score` transcript, kept
because two of them are about the harness rather than the stage.

**The new deny rule engages in a live dispatch, at the OS level.** The stage ran
its own `ls -la` of the run directory, and `decisions.md` appears in that listing
as `crw-rw-rw- 1 nobody nogroup 1, 3` — masked to a character device by the
sandbox layer, not merely refused by the permissions layer. That is independent
of the three probes in §13 and stronger: it is the rule working during real work,
against a file that by then held eleven entries about this very stage.

**One out-of-contract read: `src/rubrica/schema/coverage-0.1.json`.** The stage ran
`find / -iname "*coverage*schema*"` — which succeeded — narrowed it to the package
directory, and read the schema. `reads` names `manifest`, `world_model` and
`scenarios`, so by `audit-reads.sh`'s own rule this grades Important.

It is substantively benign, and worth saying why rather than just excusing it: the
coverage schema is the contract for the stage's *own output*, not evidence about
the target, and `rubrica validate` — which the contract obliges it to invoke —
enforces the identical constraints. Reading it is closer to reading `--help` than
to reading a sibling's artifact. But two things follow anyway. A stage can
enumerate the whole filesystem, so what keeps the answer key out is the deny list
rather than the stage's incuriosity. And `schemas = ["coverage"]` in the Contract
block already declares this relationship, which suggests the gap is that
`check-skills` validates schema *names* without the harness granting or denying
the corresponding *files*. Parking it rather than patching it: denying the schema
directory might push a stage into guessing the format it must produce, which is
worse than letting it read the file it is being validated against.

**A bash `python3 -c "open('manifest.json')"` was refused** with "This command
requires approval", while the `Read` tool on the same in-contract artifact
succeeded. Not a leak, and not a defect — but it cost the stage a turn, and it is
the mirror image of the §13 bypass probe: the same asymmetry that lets a
subprocess evade the permissions layer also makes the permissions layer refuse a
legitimate subprocess.
