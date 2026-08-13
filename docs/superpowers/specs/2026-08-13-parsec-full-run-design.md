# Parsec full-pipeline run — design and record

**Status:** In progress, started 2026-08-13. This file is written before the run
and appended to as each gate is held; sections numbered above §6 are results.

**Target:** `parsec` — a natural-language cloud-cost and provisioning
investigation agent for the RHDP platform. A clone lives at
`/tmp/parsec/parsec`; 130 captured MLflow traces of it live at
`/tmp/parsec/traces_parsec-agent-metrics_20260713_115226.json`.

**What is being asked of the pipeline:** a complete run, intake through emit,
on a target nobody involved in building rubrica has read. Every prior run used
the reservation service — a target designed alongside the skills. This is the
first run where the target's shape was not chosen to suit the pipeline, so it
is the first one that can falsify anything about generality.

---

## 1. The one thing that makes this run weaker evidence than the last one

**All three human gates are held by the orchestrator, because the human asked
for an uninterrupted run and is asleep.** Gates 1, 2 and 3 exist precisely
because a model is the wrong thing to hold them, and `rb-orchestrate` says so.
Every ruling recorded in `decisions.md` for this run is therefore a model's
ruling wearing a human gate's clothes, and any conclusion drawn from this run
that depends on a gate having been held properly is not supported.

What that does *not* excuse: the rulings are recorded verbatim as rulings, with
their reasoning, so a human reading `decisions.md` in the morning can overturn
any of them and see exactly what followed from it. A gate held badly and
recorded is recoverable; a gate skipped silently is not.

## 2. Scope: what parsec is, and which slice of it this run covers

Parsec is large — 73 Python modules, 13 declared data-source tools, six
sub-agent personas (orchestrator, cost, aap2, babylon, ocpv, icinga, security),
four skills, and an SSE chat API. A run over all of it at ten scenarios would
produce a suite too thin per capability to mean anything.

So the *target* is parsec, undivided, and the **input set** is bounded to one
coherent surface: **investigation via the orchestrator's routing, the Icinga
alert-triage agent, the AAP2 job-failure-triage agent, and the provision-DB
lookups both share.** Chosen because it is the surface with the most
behavioural evidence (33 icinga + 31 aap2 + 30 orchestrator-direct traces of
130) and because its chains are deep — an AAP2 debug goes job → catalog item →
agnosticv config → GitHub file, which is exactly the multi-hop shape rubrica's
coverage model scores.

Deliberately excluded, and the exclusions are the reason gaps will appear:
the cost/babylon/ocpv/security agents and their prompts, every cost tool, the
CloudTrail and marketplace surfaces, the report/chart generators, and all 73
source modules. **No parsec source file is registered as an input.** Two
reasons, and the second is the load-bearing one:

1. `src/agent/orchestrator.py` alone is 56KB and `tool_definitions.py` 74KB —
   they would dominate the extract fan-out.
2. Reading the implementation is how you learn what the system *does*, and this
   run is a test of whether the pipeline can build a suite from what the system
   *claims and was observed to do*. Registering the source would improve the
   suite and destroy the measurement.

`config/prompts/*.md` are registered, and are the one judgment call in this
list that deserves stating: they are the agent's own instructions, so they are
a specification of intended behaviour rather than an implementation. They are
also, unavoidably, prose the agent under test was itself given — a suite built
from them tests conformance to its own brief, which is a real thing to test but
not the same as testing conformance to the platform.

## 3. The sixteen inputs

Staged at `/tmp/rubrica-lab/inputs-parsec/`. Kinds are `intake.classify`'s.

| Input | Kind | Bytes | Why it is in the set |
|---|---|---|---|
| `parsec-readme.md` | design_doc | 8179 | The tool table and the six-step request flow |
| `parsec-architecture.md` | design_doc | 13029 | Routing, sub-agent dispatch, streaming |
| `prompt-orchestrator.md` | design_doc | 11689 | The routing contract: fast-path vs LLM |
| `prompt-shared-context.md` | design_doc | 12114 | Domain vocabulary — GUID, sandbox, catalog item |
| `prompt-icinga-agent.md` | design_doc | 15563 | The Icinga persona's obligations |
| `prompt-aap2-agent.md` | design_doc | 23305 | The AAP2 persona's obligations |
| `skill-icinga-triage.md` | design_doc | 6761 | The triage procedure, stated as steps |
| `skill-aap2-job-failure-triage.md` | design_doc | 1733 | The job-failure procedure |
| `tools-list.json` | mcp_tool_schema | 19020 | 11 tool schemas — see below |
| `trajectory-t1-icinga-severity-report.json` | trace | 38104 | Severity rollup; 7 spans, fast-path |
| `trajectory-t2-icinga-alert-triage.json` | trace | 38518 | Alert → GitHub config; 17 spans |
| `trajectory-t3-icinga-aap2-crossover.json` | trace | 57220 | Icinga alert about AAP2; 23 spans |
| `trajectory-t4-aap2-debug-from-url.json` | trace | 40738 | Job URL → catalog → repo → file; 15 spans |
| `trajectory-t5-aap2-compare-three-jobs.json` | trace | 90331 | Three jobs compared; 33 spans, LLM-routed |
| `trajectory-t6-guid-owner-lookup.json` | trace | 24972 | The canonical GUID lookup; 8 spans |
| `trajectory-t7-error-region-rollup.json` | trace | 17415 | **The only failing trace** — 3 spans, ERROR |

`tools-list.json` is assembled, not copied: `src/agent/tool_definitions.py`
holds the schemas as Python literals, so the eleven in scope were imported and
dumped — the eight data-source tools the selected trajectories call, the two
delegation tools by which the orchestrator routes (`investigate_aap2_job`,
`investigate_icinga`), and `submit_alert_verdict`. Assembling rather than
registering the 74KB module keeps the input a *contract* rather than an
implementation, consistent with §2.

The seven trajectories were picked from the 130 for distinct shape, not for
size or success: one aggregation, two triages, two multi-hop debugs, one
identity lookup, one failure. Everything else in the capture is a near-duplicate
of one of these or belongs to an excluded surface.

**t7 is in the set on purpose.** It is the run's only evidence of what parsec
does when something goes wrong, and what it shows is specific: the tool
returned `{"_truncated": true, "preview": ...}` and the orchestrator span
recorded an `exception` event with no response. Error behaviour that appears
exactly once is the kind of thing a pipeline either notices or silently drops,
and which of those happens is worth knowing.

## 4. Run parameters

`max_rounds` 2, `max_scenarios` 10 — both matching
`run-20260813-064150` so the two runs are comparable. Model `claude-sonnet-5`,
effort `medium`, per-dispatch budget $2 (raised to $3 for the two inputs over
20KB). Target name `parsec`, interface `http-sse`.

Every stage is dispatched through `scripts/dispatch-stage.sh`, so no dispatch
sees this repository's `CLAUDE.md`, `docs/`, `tests/`, a sibling skill, or this
file.

## 5. Pre-registered predictions

Written before intake. Recorded here rather than in `decisions.md` because the
dispatches can read the run directory and a prediction sitting in it is an
answer key — measured on 2026-08-13, when a `propose` dispatch ran `ls -la` one
`Read` from exactly that. `scripts/dispatch-stage.sh` now denies
`decisions.md`, and this file lives outside the run regardless.

Two of my predictions on the last run were wrong the same way — I asserted
against a field the artifacts already carried. So each of these names the
artifact and the field that settles it.

- **P1** — At least one of the multiplexed tools (`query_aap2`, `query_icinga`,
  `query_provisions_db` all take an `action` discriminator with many values)
  is split into per-action capabilities rather than one capability per tool.
  *Settled by:* `01-world-model.json` — two capabilities with the same
  `binding.tool` and different `binding.fixed_args`.
- **P2** — `db_describe_table` does **not** become a capability. It is called
  in three of the seven trajectories and has no schema in `tools-list.json`
  (it is discovered dynamically from the Reporting MCP server at runtime), so
  the honest disposition is a gap. *Settled by:* absence from `capabilities[]`,
  presence in `gaps[]`.
- **P3** — At least one gap names the truncated-result shape from t7.
  *Settled by:* `gaps[].subject` or `.unknown` mentioning truncation.
- **P4** — Round 1 of the propose/score loop returns `continue`, not
  `converged`. *Settled by:* `03-coverage/round-1.json` verdict.
- **P5** — `submit_alert_verdict` becomes a capability, and the icinga-triage
  skill's "if in doubt, `should_alert=true`" rule survives into the world model
  as an invariant or an outcome class rather than being dropped as prose.
  *Settled by:* `capabilities[]` for the tool, and a grep of the world model
  for the rule.
- **P6** — At least 35% of claims are uncited after reconcile.
  Prior run measured 130 of 287 (45%). *Settled by:* `rubrica claim-utilisation`.
- **P7** — At least one contradiction is recorded. Parsec's inputs describe the
  same two procedures twice — once in a persona prompt and once in a skill file —
  and independently maintained prose of that kind drifts. This is the
  prediction I would least bet on: the prior run recorded zero, and a
  contradiction requires a stage to assert a conflict rather than pick a side.
  *Settled by:* `world_model.contradictions`.
- **P8** — At least one goal carries an `expected_hop_depths` entry ≥ 3, from
  the t4/t5 chain job → catalog item → repo search → file fetch.
  *Settled by:* `goals[].expected_hop_depths`.
- **P9** — The suite emits with at least 8 of 10 scenarios accepted, and
  `rb-emit`'s dispatch reproduces `rubrica emit`'s bytes exactly.
  *Settled by:* `05-verdicts/`, and a `sha256` of `06-suite` from both paths.
