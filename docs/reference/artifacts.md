# Artifact reference

One entry per artifact kind Rubrica's schemas define, plus the two
human-authored config files no stage produces. Each stage-produced entry
states its schema under `src/rubrica/schema/`, the stage that writes it
(`validate.STAGE_ARTIFACTS`), which stages read it, its on-disk path within a
run (`paths.py`), what it is for, and the fields worth knowing before you open
one. Entries are ordered the way a run produces them, not alphabetically.

See [`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md)
for the rule that these files are the only channel between stages, and
[`docs/concepts/pipeline.md`](../concepts/pipeline.md) for the stage order
that writes them.

## `catalogue`

- **Schema:** `src/rubrica/schema/catalogue-0.1.json`
- **Written by:** `survey` (code)
- **Read by:** `rb-triage`; `intake` (the `--run` path, admitting whatever
  triage already ruled on)
- **Path:** `00-catalogue.json`

Every candidate a survey found in a corpus, each with a bounded digest rather
than its own bytes — `sha256`, `bytes`, `kind`, and a `digest` object, never a
copy of the source content. It also carries the survey `request` (target,
objective, corpus roots, limits) and the `policy` that governed digesting and
exclusion, so a later reader can see what the survey was told to look for
without re-deriving it. `excluded` records every path the survey chose not to
catalogue, with a `reason` (`gitignored`, `binary`, `duplicate`, and the like).

Fields worth knowing: `candidates[].origin` (`corpus`, `container_element`, or
`projection` — a candidate exploded out of a container file, or manufactured
by `adopt-projection`, still gets its own entry here); `candidates[].kind`
(the same seven-value enum `manifest.inputs[].kind` uses); `candidates[].
admissible` (a structural flag, not triage's disposition — a candidate can be
admissible and still be declined).

## `triage`

- **Schema:** `src/rubrica/schema/triage-0.1.json`
- **Written by:** `triage`, run as `rb-triage`
- **Read by:** `intake` (the `--run` path)
- **Path:** `00-triage.json`

One disposition per catalogued candidate — `admit` or `decline`, each with a
`reason` and an `authority` (`triage` or `human`, so an override at gate 0 is
distinguishable from triage's own ruling) — plus `objective_review` (whether
the corpus actually supports the survey's declared `breadth`/`depth`
objective), `deficiencies` (named gaps in the corpus itself), and
`projections` (proposed manufactured artifacts closing a deficiency, each with
a `method`, an `acceptance` criterion, and a `boundary` statement of what it
does not cover). Gate 0 reads this record, never the corpus again — a
candidate declined here is gone as completely as if the corpus never
contained it, because nothing downstream of `intake` re-reads the corpus.

Fields worth knowing: `dispositions[].reason_code` (`off_objective`,
`near_duplicate`, `needs_projection`, and five more — a fixed vocabulary, not
free text); `projections[].closes` (the `deficiency_id`s a projection is
supposed to resolve — `adopt-projection` checks structural acceptance against
this, never the prose criterion, which stays a human's call).

## `manifest`

- **Schema:** `src/rubrica/schema/manifest-0.1.json`
- **Written by:** `intake` (code); amended by `rb-orchestrate`'s
  `record-stage` and `set-limit` calls
- **Read by:** `rb-extract`, `rb-reconcile`, `rb-propose`, `rb-score`,
  `rb-orchestrate`
- **Path:** `manifest.json`

The run's identity: `run_id`, `target` (name and interface), the registered
`inputs` (each with its `artifact_id`, `source_path`, `stored_as` name,
`sha256`, `kind`, and `bytes`), the current `limits` (`max_rounds`,
`max_scenarios`), and `stages` — one entry per stage that has actually run,
recording the `model`, `effort`, and `skill_sha256` `record-stage` computed
from the skill file used. `stages` gains entries for the seven skill-run stages
between `extract` and `emit`, plus `triage` — which is recorded **after** gate
0 rather than when it ran, because a run minted by `survey` has no manifest to
merge into until `intake --run` writes one
([`docs/guides/running-a-stage-by-hand.md`](../guides/running-a-stage-by-hand.md)
§4 has the command). `intake`, `smoke`, and `survey` are code: they have no
skill file for `record-stage` to hash, so they never appear there, and their
absence is not a finding. The schema's `propertyNames` enum permits all eleven
stage names — it constrains the vocabulary, not which of them a real run
records.

Fields worth knowing: `inputs[].provenance` (present only for an input that
came from inside a container file or from a projection — `container_sha256`
+ `json_pointer`, or `projection_id` + `source_candidate_ids`); a recorded
`skill_sha256` that no longer matches the file on disk on re-inspection means
the skill was edited after that stage ran — the hook working, not a defect.

## `claims`

- **Schema:** `src/rubrica/schema/claims-0.1.json`
- **Written by:** `extract`, run as `rb-extract` (fan-out, one file per input)
- **Read by:** `rb-reconcile`
- **Path:** `01-claims/<artifact_id>.json`

One atomic, evidence-backed statement per claim, extracted from exactly one
input artifact — `rb-extract` is dispatched once per registered input and
never sees a sibling's file, so every claims document names only the
`artifact_id` it was extracted from. Nothing later fabricates a claim without
tracing back to one.

Fields worth knowing: `claims[].kind` (`capability`, `entity`, `invariant`,
`actor`, `goal`, or `outcome_class`); `claims[].derivation` (`stated`,
`inferred`, or `reverse_engineered` — a claim's honesty grade, carried forward
into the world model); `claims[].evidence[].locator` (required on every claim,
so a claim with no way to find where it came from cannot exist).

## The reconcile partials

The seven entries below are one logical step — building the world model —
engineered as bounded passes, each writing its own slice into the `01-` band
and none of them reading `01-world-model.json`. `reconcile-seal` assembles all
seven into that file, which is unchanged: nothing downstream of `reconcile`
knows the partials exist.

Every one of these schemas resolves its element definitions against
`world-model-0.1.json#/$defs/...` through `validate._schema_registry`, rather
than restating them — a duplicated `$defs/entity` that fell behind would make a
partial accept an element the sealed world model then rejects.
`capabilities-part` is the single exception and says so in its own entry.

> **Note.** The passes named as writers below are not in `paths.STAGES` yet: the
> artifact kinds, schemas and paths land ahead of the stages that fill them, so
> the contract exists before anything writes to it. Until the passes are
> registered, `rubrica validate --stage` cannot name these kinds.

## `subjects`

- **Schema:** `src/rubrica/schema/subjects-0.1.json`
- **Written by:** `reconcile-subjects`, run as `rb-reconcile-subjects`
- **Read by:** `rb-reconcile-contradict` (which is fanned out over it),
  `rb-reconcile-gaps`; `check-refs`
- **Path:** `01-subjects.json`

A cover of every claim in `01-claims/`, grouping them into subjects so the
contradiction sweep can be fanned out without any member losing sight of a
claim it needs to compare against. A **cover, not a partition**: a claim may
appear under several subjects, and the pass is instructed to over-assign when
the subject is unclear, because a claim in no subject is never compared against
anything. That is what a heuristic pair filter could not give — `check-refs`
holds the cover to totality, so every claim id in the run appears here.

Fields worth knowing: `subjects[].claims` (a `claim_refs` array, so it can
never be empty); `subjects[].note` (optional, for why a claim was assigned
where a reader would not expect it).

## `contradictions-part`

- **Schema:** `src/rubrica/schema/contradictions-part-0.1.json`
- **Written by:** `reconcile-contradict`, run as `rb-reconcile-contradict`
  (fan-out, one file per subject)
- **Read by:** `rb-reconcile-capabilities`, `rb-reconcile-outcomes`,
  `rb-reconcile-entities`, `rb-reconcile-goals`, `rb-reconcile-gaps`,
  `reconcile-seal` (code); `check-refs`
- **Path:** `01-contradictions/<subject_id>.json`

What one fan-out member found within its own subject, reading every claim in
that subject **across all input files** — which is what preserves
cross-artifact contradiction detection through the fan-out. Each part names the
`subject_id` it was dispatched with, and a member never sees a sibling's file.

An **empty `contradictions` array is a real record**, not a missing one: it
says this member swept this subject and found no disagreement. That is why the
array carries no `minItems`, and why the layer-2 check requires a file per
subject rather than a non-empty one. The contradictions recorded here are a
constraint on every later pass — a disagreement recorded `unresolved` may not
be quietly settled by how a later pass chooses to model the thing.

Fields worth knowing: `contradictions[]` is
`world-model-0.1.json#/$defs/contradiction` itself, so `resolution` is the same
four-value enum (`unresolved`, `preferred_a`, `preferred_b`, `both_possible`)
the sealed world model carries.

## `capabilities-part`

- **Schema:** `src/rubrica/schema/capabilities-part-0.1.json`
- **Written by:** `reconcile-capabilities`, run as `rb-reconcile-capabilities`
- **Read by:** `rb-reconcile-outcomes`, `rb-reconcile-entities`,
  `rb-reconcile-goals`, `rb-reconcile-gaps`, `reconcile-seal` (code)
- **Path:** `01-capabilities.json`

Each capability's identity, `operation`, `params` and `binding` — and **no
`outcome_classes`**, which are the next pass's output. Writing the capability
list to a file is the point of splitting the two: `rb-reconcile-outcomes` then
quantifies over a list it can read, rather than over a memory of having just
written one.

The one place in this family where a definition is restated rather than
`$ref`'d. `$defs/capability_core` is `world-model-0.1.json#/$defs/capability`
minus `outcome_classes`, and JSON Schema cannot express that subtraction while
`additionalProperties: false` holds — a `$ref` plus an override does not
compose under it. `tests/unit/test_schema_part_sharing.py` pins the restated
`properties` and `required` sets to the world model's, in both directions, so
the duplication cannot drift silently.

Fields worth knowing: `capabilities[].binding` (optional in the schema and
required by `emit`, which reports a finding for an accepted scenario whose
capability has none — so a capability without one is a defect deferred, not
avoided).

## `outcomes-part`

- **Schema:** `src/rubrica/schema/outcomes-part-0.1.json`
- **Written by:** `reconcile-outcomes`, run as `rb-reconcile-outcomes`
- **Read by:** `rb-reconcile-gaps`, `reconcile-seal` (code); `check-refs`
- **Path:** `01-outcomes.json`

A **join table, not a collection**: `outcome_classes` is nested inside the
capability object in the world model, so this pass cannot write a sibling
array. Each entry names a `capability_id` from `01-capabilities.json` and the
outcome classes for it, and `reconcile-seal` folds each entry into its
capability.

Fields worth knowing: `outcomes[].outcome_classes[].kind` (the same five-value
enum the world model uses — `success`, `empty`, `not_found`, `error`,
`underspecified`; `underspecified` is the one that records "nothing addresses
this", which is not the same as silence, and dropping it costs the coverage
denominator a column for every capability).

## `entities-part`

- **Schema:** `src/rubrica/schema/entities-part-0.1.json`
- **Written by:** `reconcile-entities`, run as `rb-reconcile-entities`
- **Read by:** `rb-reconcile-goals`, `rb-reconcile-gaps`, `reconcile-seal`
  (code)
- **Path:** `01-entities.json`

The entities, with their fields, relations and invariants, quantified over the
capabilities already declared in `01-capabilities.json`: if a claim spells out
the shape a capability returns, that shape becomes an entity here. Elements are
`world-model-0.1.json#/$defs/entity`, so the sealed world model accepts exactly
what this file carries.

Fields worth knowing: `entities[].invariants[].machine` versus `.prose` — the
same distinction the `world-model` entry describes, and the same consequence:
`prose` leaves the reachability gate nothing to evaluate, while a `machine`
invariant promoted from an inference fails every seed that is actually correct.

## `goals-part`

- **Schema:** `src/rubrica/schema/goals-part-0.1.json`
- **Written by:** `reconcile-goals`, run as `rb-reconcile-goals`
- **Read by:** `rb-reconcile-gaps`, `reconcile-seal` (code)
- **Path:** `01-goals.json`

Actors and the goals they hold. Its own pass rather than folded into entities
because goals are half the frozen denominator: `reconcile-seal` counts them,
`rb-propose` designs against exactly this list, and a later stage may only
*request* an amendment — which costs an explicit orchestrator decision and a
`denominator_version` bump. Actors travel with goals in the same file because
every goal needs a real `actor_id` to resolve.

Fields worth knowing: `goals[].expected_hop_depths` (as in the world model, the
multi-hop depths a goal is expected to be tested at); both arrays lack
`minItems`, because a corpus that establishes no actor is a fact for
`rb-reconcile-gaps` to record rather than one for the schema to forbid.

## `gaps-part`

- **Schema:** `src/rubrica/schema/gaps-part-0.1.json`
- **Written by:** `reconcile-gaps`, run as `rb-reconcile-gaps`
- **Read by:** `reconcile-seal` (code)
- **Path:** `01-gaps.json`

Last of the prompt passes on purpose. It reads every prior partial as well as
every claim, because the refusal conditions of every pass before it resolve to
"record a gap instead" — so the pass that writes gaps is the one positioned to
audit what its predecessors declared: a capability with no supporting claim, an
invariant promoted to `machine` on an inference, an outcome class nothing
states.

An empty `gaps` array is legal and is a strong claim: a world model with no
gaps, built from claims that leave things unstated, has erased the silence
rather than recorded it.

Fields worth knowing: `gaps[].blocks` (the later stages a gap makes
unsafe — a gap blocking `propose` is what makes the orchestrator halt, so it is
named honestly rather than narrowly, and never left empty to avoid a halt).

## `world-model`

- **Schema:** `src/rubrica/schema/world-model-0.1.json`
- **Written by:** `reconcile`, run as `rb-reconcile`
- **Read by:** `rb-propose`, `rb-score`, `rb-instantiate`, `emit` (code),
  `rb-orchestrate`; `check-refs`
- **Path:** `01-world-model.json`

The single reconciled picture of the target system, built from every claim
`rb-extract` produced: `capabilities`, `entities`, `actors`, `goals`, recorded
`contradictions` (disagreements carried forward rather than silently
resolved), recorded `gaps` (things no input says anything about, each naming
which later stages it `blocks`), and a `denominator` frozen at a `version` for
the rest of the run. Every element carries a `claims` array of the claim ids
that support it.

**No representation for a field's value domain.** `capability.params` and
`entity.fields` carry only a name and a type, with `additionalProperties:
false` on both — a param must additionally state whether it is `required`,
and a field cannot state that at all — and neither has anywhere in the schema
to record that a field's value must be, say, one of three enumerated strings.
So every concrete value anywhere downstream of `reconcile` is a prescription
`rb-instantiate` invents, never an assertion grounded in a claim. See
[`docs/design/limitations.md`](../design/limitations.md) for what this rules
out checking.

Fields worth knowing: `entities[].invariants[].machine` (one of four typed
forms — `compare`, `count`, `join`, `unique` — evaluated mechanically by
`check-refs` against a seed; an invariant may instead carry `prose` and no
`machine`, which no check layer evaluates); `goals[].expected_hop_depths`
(the multi-hop depths a goal is expected to be tested at, read by `rb-score`'s
goal matrix).

## `scenarios`

- **Schema:** `src/rubrica/schema/scenarios-0.1.json`
- **Written by:** `propose`, run as `rb-propose` (appends; never renumbers a
  prior round); also rewritten by `score`, run as `rb-score`, which folds
  duplicates and applies rejections
- **Read by:** `rb-propose` itself (it declares `scenarios` in `reads` and has
  to read the file it appends to, so an earlier round's ids survive
  unrenumbered), `rb-score`, `rb-instantiate`, `rb-challenge`, `emit` (code),
  `rb-orchestrate`; `dedupe-candidates`, `compare-gold`
- **Path:** `02-scenarios.json`

Every proposed test across every round of the propose/score loop, each with a
`status` (`proposed`, `active`, `duplicate`, or `rejected`) and a `provenance`
block naming the `hole_refs` and `claim_ids` that motivated it. A scenario's
`id` is permanent even once a later round marks it `duplicate` or `rejected` —
the round history stays legible rather than being overwritten.

Fields worth knowing: `capability_refs[]` (each pairs a `capability_id` with
an `outcome_class_id` — the coverage cell this scenario is meant to close);
`duplicate_of` (required when `status` is `duplicate`); `rejected_reason`
(required when `status` is `rejected` — one of five fixed values, including
`blocked_by_gap`).

## `coverage`

- **Schema:** `src/rubrica/schema/coverage-0.1.json`
- **Written by:** `score`, run as `rb-score` (one `round-N.json` per round,
  plus `latest.json` pointing at the most recent)
- **Read by:** `rb-propose` (via `latest.json`), `rb-orchestrate`
- **Path:** `03-coverage/round-<N>.json`, `03-coverage/latest.json`

One round's coverage report against the frozen `denominator`: a
`capability_matrix` (capability × outcome-class cells, each `covered` or not,
with the `scenario_ids` that cover it), a `goal_matrix` (same shape, per
goal), a list of uncovered `holes` (each with a `reason` — `not_yet_
attempted`, `unreachable`, `out_of_scope`, or `blocked_by_gap`, the last
requiring a `gap_id`), `progress` counters, and the round's `verdict`.

Fields worth knowing: `verdict` (`continue`, `converged`, `halted_no_progress`,
or `halted_round_cap` — *computed* here; only `rb-orchestrate` acts on it, by
dispatching another `propose`/`score` round or stopping the loop);
`denominator_version` (must match the world model's frozen value, or the
percentages this round reports are meaningless).

## `seed`

- **Schema:** `src/rubrica/schema/seed-0.1.json`
- **Written by:** `instantiate`, run as `rb-instantiate` (fan-out, one per
  active scenario)
- **Read by:** `rb-challenge`, `emit` (code); `check-refs` (seed conformance,
  invariant evaluation, the reachability gate)
- **Path:** `04-instances/<scenario_id>/seed.json`

The concrete world one scenario's test runs against, distractors included.
The schema constrains only the envelope — `schema_version` and a `collections`
object of arrays of objects — because a seed's real shape comes from the
world model's entities, which `refs.py` checks it against rather than a
second copy of the schema.

**Seed conformance is one-directional.** `check-refs` verifies every
collection, field, and type a seed *does* declare against the world model
(seed→world), but never that a seed supplies everything the world model
*declares* (world→seed) — a seed can drop an entire declared collection, or
declare all of them empty, and pass both check layers with zero findings.
Whether partial seeds are legal is an open design question. See
[`docs/design/limitations.md`](../design/limitations.md).

## `expected`

- **Schema:** `src/rubrica/schema/expected-0.1.json`
- **Written by:** `instantiate`, run as `rb-instantiate`
- **Read by:** `rb-challenge`, `emit` (code); `check-refs` (the reachability
  gate)
- **Path:** `04-instances/<scenario_id>/expected.json`

The oracle for one instantiated scenario, derived from its own `seed.json`
rather than the seed being built to fit a pre-chosen answer. Carries the
`discriminating_fact` that makes the scenario answerable only one way, an
`answer_reference`, one or more `assertions`, a `trajectory` (the tool calls
expected, under a `match` mode of `subset`, `exact-set`, or `exact-sequence`),
and a `completion` status.

Fields worth knowing: `assertions[].kind` — `answer_contains`,
`answer_excludes`, and `value_equals` each require a `grounded_in.
seed_pointer` (a JSON Pointer into this scenario's own seed, and only this
scenario's — the reachability gate cannot resolve a pointer into a sibling's
seed); `tool_called` and `tool_not_called` instead require a `capability_id`
and forbid `grounded_in`.

## `verdict`

- **Schema:** `src/rubrica/schema/verdict-0.1.json`
- **Written by:** `challenge`, run as `rb-challenge` (fan-out, one per
  instance)
- **Read by:** `emit` (code); `rb-orchestrate` (a `re-seed` verdict's fields
  are appended verbatim, never paraphrased, to the re-dispatch they provoke)
- **Path:** `05-verdicts/<scenario_id>.json`

`rb-challenge`'s adversarial ruling on one instantiated scenario: `accept`,
`re-seed`, or `reject`, plus `uniquely_determined`, `derivable_without_
guessing`, and `minimum_tool_calls_found`. A `false` `uniquely_determined`
requires at least one `alternative_answers` entry with its own
`world_consistent_reason` — a verdict claiming ambiguity must show the
ambiguity it found, not merely assert it.

Fields worth knowing: `flags` (currently only `difficulty_overstated`);
`notes` (required on every verdict — the field `rb-orchestrate` quotes
verbatim on a `re-seed` re-dispatch, so its wording is what the next attempt
actually receives).

## `suite-expected`

- **Schema:** `src/rubrica/schema/suite-expected-0.1.json`
- **Written by:** `emit`, run as `rb-emit` (a thin wrapper over the code in
  `emit.py`)
- **Read by:** the verifier `smoke` runs inside each task container
  (`src/rubrica/suite/verify.py`) — not itself a pipeline stage
- **Path:** `06-suite/<scenario_id>/tests/expected.json`

A projection of the matching `04-instances/<sid>/expected.json` onto tool
names a transcript will actually show, plus fixed scoring `weights`
(`assertions: 0.8`, `trajectory: 0.2`, both `const`). `grounded_in` is
deliberately absent from this schema — the emitted task container carries no
`seed.json` for a verifier to resolve a pointer against, so the projection
drops what it cannot check at that point.

Fields worth knowing: `contract` (always the literal string `rubrica/v1` —
the value `suite/verify.py` checks before trusting anything else in the
file); `trajectory.operations[].tool`/`args` (the capability's `binding.tool`
and `binding.fixed_args` merged with the scenario's own call arguments, not
the world model's `capability_id` — a transcript never shows a capability id).

## `report`

- **Schema:** `src/rubrica/schema/report-0.1.json`
- **Written by:** `smoke` (code)
- **Read by:** `check-refs` (cross-checked against `manifest.json`'s `run_id`
  and the emitted suite); otherwise the terminal artifact — nothing downstream
  reads it
- **Path:** `07-report.json`

The result of running the emitted suite against three agent roles — a
`weak_baseline` that should fail nearly everything, the `under_test` agent,
and an `oracle` handed the reference answer that should pass nearly
everything — with one `tasks[]` entry per emitted scenario and a `summary`
rolling up `mean_reward_by_role`. `tasks[]` requires at least one entry: an
empty report would otherwise validate cleanly and describe a suite nobody ran.

Fields worth knowing: `verdict` — `healthy` (a real spread), `degenerate_
trivial` (the weak baseline passes too much, indicting the suite), `broken_
labels` (the oracle fails too much, indicting the labels or the verifier —
never the agent under test — and outranking `degenerate_trivial` when both
could apply), or `inconclusive` (too few scoreable tasks to say anything).

## Human-authored configs

Two more schemas exist under `src/rubrica/schema/` for files no stage ever
writes — a person authors them, and they are handed to a subcommand as a
flag, not read by any pipeline stage. **A config that fails its own schema is
a usage error (exit 2), not a finding (exit 1): there is no stage to hand a
repair prompt to**, so the same defect that would be a repairable `1` in a
stage's own output is unrecoverable here.

### `agents-0.1.json`

- **Schema:** `src/rubrica/schema/agents-0.1.json`
- **Consumed by:** `rubrica smoke --agents PATH`

The agent roster for a smoke run: one entry per role (`weak_baseline`,
`under_test`, `oracle`), each with a `model` label and a `command` argv list.
`smoke` substitutes `{task_dir}`, `{logs_dir}`, and `{scenario_id}` into each
argv element and resolves the executable *before* any agent runs — a bad
command fails the whole roster at exit 2, never partway through a run.

### `gold-0.1.json`

- **Schema:** `src/rubrica/schema/gold-0.1.json`
- **Consumed by:** `rubrica compare-gold --gold PATH`

A hand-authored benchmark — the roughly ten hand-written bench tasks
`compare-gold` measures a generated suite's recall and novelty against. Its
`goal_id` and `capability_refs` are world-model ids, so a gold file has to
name the same goals, capabilities, and outcome classes the run's own
`01-world-model.json` declares, or nothing in it can match.
