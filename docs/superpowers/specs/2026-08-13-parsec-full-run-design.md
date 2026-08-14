# Parsec full-pipeline run — design and record

**Status:** Executed 2026-08-13/14, complete through stage 06. This file is written before the run
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

`intake` was invoked with `max_rounds` 2 and `max_scenarios` 10, to match
`run-20260813-064150`. **Both were then raised by hand, before extract ran, to 3
and 64** — 10 is far too low for an application of parsec's size, and the human's
ruling is that the cap cannot sensibly sit below ~50 for any real target
(`intake`'s default is 8). So the run is *not* parameter-comparable to its
predecessor, by design rather than by accident, and the 36-scenario suite is
intended scale rather than overrun. A proper heuristic for the cap — presumably a
function of the world model's cell and goal denominators rather than a constant —
is owed and deferred; see §11 and §12, where it turns out to be the same question
as input triage.

Model `claude-sonnet-5`, effort `medium`, per-dispatch budget $2, raised per stage
as the artifacts grew: $3 for the two inputs over 20KB, $10 for reconcile (362KB
of claims to fold), $5–6 for the score dispatches. Budget is a harness parameter
rather than a prompt parameter, so raising it does not change the judgment under
test. Target name `parsec`, interface `http-sse`.

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

---

# Results

**Status: complete through stage 06.** 23 Harbor packages at
`runs/run-20260813-204203/06-suite/`. Stage 07 `smoke` not run — the packages
need parsec's MCP backends and Docker, which §2 excludes. Total dispatch spend
**$85.98**; 54 rulings in `decisions.md`.

## 6. What the run produced

| Stage | Result |
|---|---|
| intake | 16 inputs, `validate` 0 |
| 01a extract | 16/16 members, **815 claims**, $11.96, zero out-of-contract reads, zero denials |
| 01b reconcile | 6 actors, 14 capabilities, 12 entities, 12 goals, 7 gaps, **2 contradictions**; 28 cells / 12 goals; $5.72, 42 turns |
| 02/03 round 1 | 25 scenarios, verdict `continue`, 23/28 cells, 1/12 goals |
| 02/03 round 2 | +11 scenarios, verdict `halted_no_progress`, 23/28 cells, 3/12 goals |
| 04 instantiate | 36 dispatched, **30 instances, 6 refusals**, $35.66 |
| 05 challenge | 30 verdicts → **23 accept, 6 reject, 1 unrepaired re-seed** |
| 06 emit | **23 packages, byte-identical across both paths**, `1f484e9e0d30f8d7…` |

Final coverage **22/28 capability cells, 3/12 goals**. The cell count fell by one
when a rejected scenario stopped crediting a row — the asymmetry rb-score's
Method step 3 warns about, observed rather than assumed.

## 7. Prediction scoring

| | Prediction | Outcome |
|---|---|---|
| P1 | A multiplexed tool is split into per-action capabilities | **Wrong.** Every `binding.fixed_args` is `{}` — one capability per tool, `action` left a param |
| P2 | `db_describe_table` becomes a gap, not a capability | **Wrong.** It became `cap-db-describe-table` (confidence `medium`) from one trace claim, with no schema anywhere in the input set |
| P3 | A gap names t7's truncated-result shape | **Wrong, in the better direction.** Truncation came back as a *testable outcome class* on `fetch_github_file` rather than an acknowledged unknown |
| P4 | Round 1 returns `continue` | **Held** |
| P5 | `submit_alert_verdict` becomes a capability and the "if in doubt" rule survives | **Half.** The capability exists; what survived is the *system default* to `should_alert=true`, not the skill's "if in doubt" instruction |
| P6 | ≥35% of claims uncited | **Held decisively.** 148 of 815 cited — **82% uncited** |
| P7 | At least one contradiction (my least-confident) | **Held.** Two, both verified against the raw traces |
| P8 | A goal carries `expected_hop_depths` ≥ 3 | **Held.** Up to `[4,5]` |
| P9 | ≥8/10 accepted, and `rb-emit` reproduces `emit` byte-for-byte | **Half.** Byte-identity confirmed; acceptance 23/30 = 77%, just under the 80% predicted |

Four of nine wrong or half, against 23 of 24 on the reservation-service run. That
is the price of predicting against a target nobody involved had read, and it is
the more honest number of the two.

## 8. Findings

**F1 — the loop's stopping rule is blind to goal-coverage progress.**
`coverage-0.1.json` defines `progress` as `new_cells_this_round` plus
`rounds_without_progress`, with no goal term. All five remaining cell holes are
`blocked_by_gap`, so `new_cells_this_round` was structurally guaranteed to be 0 in
every future round — the loop was certain to halt after round 2 however much goal
coverage remained closable. Round 2 tripled goal coverage and registered as zero
progress. After it, **each of the nine uncovered goals was missing exactly one hop
depth, always the deepest**, and `max_rounds` permitted a third round. The suite
ships at 3/12 goals as a direct result. Not overridden: that arithmetic is score's
to own, and the fix belongs in the schema, not in one run's control flow.

**F2 — propose is not held to the world model's entity set.** It wrote scenarios
requiring seeded agnosticv PR results, GitHub file content, AWS account records
with a `region` field, and Icinga downtime objects — none declared as entities.
`validate` and `check-refs` both pass such a scenario. Cost: six refusals plus
scn-011's reject, roughly $5, and 7 of 36 scenarios.

**F3 — a re-challenge is indistinguishable from a first challenge.** The repair
loop is "re-dispatch rb-instantiate, then re-challenge", but a plain challenge
re-dispatch found a complete verdict in its one `writes` slot and correctly
declined to re-judge. The loop's second half was a $0.37 no-op leaving a verdict
that described a seed which no longer existed. Once the stale verdict was moved
aside, the genuine re-judgment returned `accept`. **The repair worked; only the
signalling was missing.**

**F4 — a re-seed whose remedy lies outside instantiate's `writes` cannot be
repaired at all.** scn-003's notice asked for a `capability_refs` change in
`02-scenarios.json`, which `rb-propose` owns; the member verified seed and
expected could not close it, and declined. `rb-orchestrate` shuts the propose door
explicitly. scn-003 is the run's one unrepairable scenario and the sole reason
`emit` exits 1.

**F5 — the rejection notice cannot express an escalated re-seed.** Its three
fields are the re-seed's own and encode no rejection reason, so `rb-score` cannot
choose from the enum. It reported that back rather than guessing.

**F6 — a dispatch wrote outside the run, and the harness allowed it.** The
permissions allow list carried a bare `Write` while `Edit` was scoped; `rb-emit`
used it to write `check_prune_scratch.py` into the *repository root*, run it, and
delete it. Content harmless, capability not: the same grant reaches
`src/rubrica/*.py` and every sibling `SKILL.md`. The sandbox scope's
`allowWrite: [$run]` did not stop it — a third data point for that layer's
unreliability. Both prior observed isolation violations in this project were
reads; this is the first write. Fixed and pinned by a test measured both ways.

## 9. What the prompts got right, which is the substance of the run

**Five instantiate members refused rather than fabricate.** Each hit §5 — the
scenario needs an entity the world model does not declare — enumerated all 12
declared entities to prove the absence, and wrote nothing. Inventing a collection
name is legitimate for that stage and would have produced an artifact both gates
pass. None did it.

**reconcile found a contradiction no mechanical check could reach.** Two
trajectories make the identical `search_github_repo(owner=rhpds,
repo=agnosticd-v2)` call; t4 returns 8 matches, t5 returns `GitHub API returned
404: Not Found`. It also caught that `prompt-aap2-agent-md` contradicts itself on
the same point in two of its own sections, and recorded the whole thing
`unresolved` with a stated refusal to confidence-weight. Verified verbatim against
the raw traces.

**challenge earned its stage three separate ways.** It found a seed that embedded
a check threshold inside an output string, making a "deep" scenario answerable in
one call; a seed where two records each self-declared an exact match for the same
key, with the oracle ruling one out by strict `value_equals` rather than by
anything the world states; and a seed whose `github_repos` collection had no file
index, so nothing in that world could answer at all. Unprompted, it also flagged a
scenario whose `trajectory` requires two operations while none of its three
assertions grades the second.

**score refused to act on a bad notice.** Handed scn-003 among the rejections, it
observed that the quoted evidence is the *accept* pattern, that no enum value
fits, and reported it back as a gap in the notice — which is what its skill says to
do, and which caught the orchestrator's error.

**propose read only `03-coverage/latest.json`** and produced exactly 11 scenarios
for the 11 uncovered goal rows, each deeper than that goal had. It never saw
score's reasoning.

## 10. The orchestrator's own errors, for the record

1. **Escalated scn-003 to a rejection on a rule that did not apply.** "Second
   re-seed becomes a rejection" needs a second re-seed *verdict*; scn-003's
   re-dispatch refused without judging, so only one existed. `rb-score` caught it.
   Worse, the stderr note added to `RUBRICA_REJECT` dressed the mis-application as
   sanctioned.
2. **Reported `audit-reads.sh` as under-reporting reconcile's bash section.** The
   script was right; a bad `sed` range had truncated its output.
3. **Read scn-006's unchanged `expected.json` mtime as an inconsistency.** It was
   correct: the re-seed changed the world and left the oracle alone, because the
   right answer had not moved.
4. **Called the `max_scenarios` value an unexplained discrepancy.** It was a
   deliberate human edit. Every mechanism was checked except the person.

## 11. §2's descoping, reconsidered

**§2's second reason for excluding all parsec source does not survive.** It says
registering source "would improve the suite and destroy the measurement" — true
when a run exists to test the *pipeline*, which is what every prior run did. For a
run whose deliverable is a parsec suite it is backwards, and importing that
constraint was a category error.

The cost is measurable rather than hypothetical: the six refusals and scn-011's
reject all died for want of entities whose result shapes are declared in
`src/tools/*.py` — precisely what was excluded. **A triage pass asking "are these
13 tools' result shapes declared anywhere in the candidate set?" would have
predicted that exact failure before intake minted the run.**

Three constraints such a phase would have to respect, each from this run's data:

- **Its output cannot be a scalar.** `tool_definitions.py` at 74KB was unusable
  whole and fine as a projected 19KB eleven-tool contract, whose claims came back
  7% cited but load-bearing — every capability binds to them. The useful verdict is
  "container of N independent contracts, extract per-tool", not "0.4, keep". Size
  was never the binding constraint; shape was.
- **Utilisation is what a value indicator would be predicting**, and it is already
  measurable after the fact: 18% overall, prose 2–21%, traces 36–73%,
  `prompt-aap2-agent-md` at 5 of 139. Roughly $6.7 of extract bought ~46 citations
  from eight prose documents; ~$5.9 bought ~92 from seven traces.
- **Declining must stay visible, or descoping becomes invisible.** A gap whose
  closing evidence was declined at triage is indistinguishable, in the world model,
  from a gap nothing could close — and this run has four of the first kind
  presenting as the second. Guard: triage records every candidate it scored *and*
  every one it declined with a reason, and `check-refs` gains the ability to report
  a gap whose named closing input was declined as a finding rather than as a fact
  about the target.

The objective has to be explicit too. This run's manual pass optimised for a
*coherent* run — one surface, deep chains, comparable to its predecessor.
Optimising for *coverage of parsec* would have chosen differently: the
tool-definition projection, one trajectory per agent persona, and almost none of
the prompt files, which were the 2–21% cohort.

## 12. Owed

- A `max_scenarios` heuristic and a triage phase — the same question, since both
  size the run from the target rather than from a constant. `intake`'s default is
  8; the floor for a real target is ~50.
- `progress` needs a goal term, or `halted_no_progress` needs a name admitting it
  means "no new cells".
- A gate holding propose's scenarios to the world model's declared entities.
- A signal that makes a re-judgment distinguishable from a first judgment.
- A disposition for a re-seed whose remedy lies outside instantiate's `writes`.
- Whether the five internal-persona goals belong in the denominator at all: three
  of twelve goals describe one journey from three vantage points, and only
  `act-end-user` goals are exercisable through an `http-sse` interface.
