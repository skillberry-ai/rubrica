# Glossary

Terms used across the artifact contract, the schemas, and the CLI, defined
from what actually produces or consumes them. Alphabetical.

## candidate

One catalogued file (or exploded element of a container file) from a survey's
corpus, recorded with a bounded digest and never its own bytes — the
catalogue schema's `candidates[]` entries carry `sha256`, `bytes`, `kind`, and
`digest`, but nothing that reproduces the source content
(`src/rubrica/schema/catalogue-0.1.json`). `rubrica survey` writes one entry
per candidate; the `triage-*` family then rules on each as `admit` or `decline`,
with
`needs_projection` recorded as a decline reason code when the candidate is
valuable but not usable as-is (`src/rubrica/schema/triage-0.1.json`'s
`decline_reason` enum). A candidate also carries `admissible`, and a container
file whose elements were exploded into candidates of their own is recorded
`admissible: false` — it stays visible rather than vanishing, because declining
it and saying why is what tells a reader at gate 0 that its elements are the
real candidates.

## cell

One capability × outcome-class pair, and the unit coverage is counted in. Each
`capability_matrix.cells[]` entry names a `capability_id`, an
`outcome_class_id`, the `scenario_ids` that reach it, and a boolean `covered`
(`src/rubrica/schema/coverage-0.1.json`); the goal matrix counts `rows` the same
way for goals. How many cells are *counted* is fixed by
`denominator.capability_cells` before the first round runs, so "coverage" here
always means a fraction of a frozen set — never a judgment that enough tests
exist. **Declared and counted are not the same set.** Only the cells whose
capability declares a `binding.tool` are drivable through the target, and only
those are scored; the rest are declared, unscored, and accounted for as computed
`unreachable` holes. A cell that is not covered is recorded as a `hole` either
way, with a reason for why not.

## claim

One atomic, evidence-backed statement about the target system, extracted by
`rb-extract` from exactly one input artifact. Its schema requires a `kind`
(`capability`, `entity`, `invariant`, `actor`, `goal`, `outcome_class`, or
`tool`), a `statement`, at least one `evidence` entry carrying an `artifact_id`
and a `locator`, a `confidence`, and a `derivation`
(`src/rubrica/schema/claims-0.1.json`). Every claim traces back to the one
input it came from; nothing later fabricates a claim without a locator.

## contradiction

Two claims that cannot both hold, recorded rather than resolved. One
`rb-reconcile-contradict` member sweeps one **subject** and writes one entry
per contradiction it finds there, naming `claim_a`,
`claim_b`, the `nature` of the conflict, a `resolution`
(`unresolved`, `preferred_a`, `preferred_b`, or `both_possible`), and a
`rationale` (`src/rubrica/schema/world-model-0.1.json`'s `contradiction`
definition). The world model carries the disagreement forward instead of
quietly picking a side, and every reconcile pass below the sweep is held to
that: a disagreement recorded `unresolved` is not one they may settle by how
they choose to model the thing.

## corpus

The directory roots `rubrica survey` walks, recorded verbatim in
`request.corpus_roots` (`src/rubrica/schema/catalogue-0.1.json`). It is the only
thing a run ever sees of the target's own files, and it is read exactly once:
`survey` catalogues what it finds, the `triage-*` family rules on the
catalogue, and
nothing downstream of `intake` opens the corpus again.

A file can fail to reach `extract` two different ways, and the difference is
load-bearing. `survey` *excludes* it mechanically, recording a `path` and one
`exclusion_reason` — `gitignored`, `vcs_metadata`, `binary`, `lockfile`,
`vendored`, `duplicate`, `unreadable`, or `operator_excluded` — and it never
becomes a candidate at all. `rb-triage-rule` *declines* a candidate as a
judgment,
under one of the `decline_reason` codes. An exclusion is arithmetic; a decline
is the thing gate 0 exists to review.

## deficiency

Something the admitted set does not cover that the objective needs, recorded by
`rb-triage-audit` with a `deficiency_id`, a `subject`, a `statement`, and
optionally a
`closed_by` naming the projection that answers it
(`src/rubrica/schema/triage-0.1.json`). It is triage's own account of what its
selection cannot do, which is why an empty `deficiencies` array is a claim
rather than an absence: it says the admitted candidates cover everything the
objective needs, and a human at gate 0 will read it as that. Distinct from a
`gap`, which `rb-reconcile-gaps` records later about the *target* rather than
about the corpus.

## denominator

The coverage denominator, computed once by `reconcile-seal` — code, not a
prompt — and frozen at a `version` for the rest of the run.
`denominator.capability_cells` counts the **drivable** capability × outcome-class
pairs, those whose capability declares a `binding.tool`, and `denominator.goals`
counts goals (`src/rubrica/schema/world-model-0.1.json`). Goals are not narrowed:
a goal is closable with no binding anywhere. Every later coverage report
carries the same `denominator_version` it was computed against, so a round
cannot silently change what "covered" means partway through.

## derivation

A claim's honesty grade: `stated`, `inferred`, or `reverse_engineered`
(`src/rubrica/schema/claims-0.1.json`'s `claim.derivation` enum). The point is
that "the spec says this" and "I guessed from one trace" never look alike
downstream — a claim's derivation travels with it through the world model and
into every scenario that cites it.

## digest

The bounded summary of one candidate that `survey` writes into the catalogue,
and the only thing `rb-triage-rule` ever reads about that candidate — never its
bytes. `policy.digest_body_chars` caps the size and `digest_truncated` records
when the cap bit (`src/rubrica/schema/catalogue-0.1.json`).

`src/rubrica/digest.py` calls itself "the design's single point of failure and is
written knowing it": a fact absent from a digest is a fact triage does not have,
and the generator is code that cannot know what matters about a target it has
never seen. Completeness being unreachable, the mitigation is honesty instead —
`heuristics_fired` records which extractors actually found something, and a
triage that cannot rule on a candidate declines it `digest_insufficient` and
names the field it needed. That turns the module's blindness into a finding a
human reads at gate 0 rather than a silent bad selection.

## disposition

`rb-triage-rule`'s ruling on one candidate: `admit` or `decline`, carrying a
prose
`reason`, an `authority`, a `reason_code` from the `decline_reason` enum when it
declines, and a `priority` when it admits
(`src/rubrica/schema/triage-0.1.json`). No code acts on `priority` — an integer
rank, 1 for the most valuable — it orders the human's reading. There is exactly
one disposition per catalogued candidate, including containers marked
`admissible: false` and every candidate that will be declined, because a surface
with nothing but declines is precisely what a human needs to see at gate 0.

`authority` is `triage` for everything the skill wrote, and `human` for a gate-0
override — written by a person, or by `rubrica adopt-projection` when a
manufactured projection is admitted. Both edit that same record rather than
starting a new run, so `authority` is the only field that tells which admissions
the stage authored from which a human made at the gate.

## distractor

A near-miss record placed in a scenario's seed so an agent cannot pass the
test by reading back the only matching row. `rb-instantiate`'s contract
requires designing the distractor set *before* deriving the oracle
("distractors first ... then derive that world's oracle from the seed rather
than the other way round," `src/rubrica/skills/rb-instantiate/SKILL.md`
frontmatter) — a seed built to fit an already-chosen answer tends to omit the
near-misses that would make the test hard to fake.

## gap

Something no input artifact says anything about, recorded by
`rb-reconcile-gaps` with a `subject`, an `unknown`, `why_it_matters`, and a `blocks` list naming
which later stages it prevents (`src/rubrica/schema/world-model-0.1.json`'s
`gap` definition; the enum is `propose`, `score`, `instantiate`, `challenge`,
`emit`, `smoke`). A gap that blocks nothing is informational; a gap naming
`propose` in its `blocks` list is what makes the *orchestrator* halt and ask
for the missing artifact, rather than letting the pipeline invent the missing
knowledge and run on. A cell that cannot be covered because of a gap is
separately recorded as a `blocked_by_gap` hole rather than `not_yet_attempted`
— which is what lets `rb-score` reach `converged` instead of spending rounds
on something no round can close.

## gate

A check standing between one stage and the next, in two kinds that are not
interchangeable. A *deterministic* gate is `rubrica validate` (layer 1, JSON
Schema, one per artifact kind) or `rubrica check-refs` (layer 2, cross-artifact
references, seed conformance, reachability, invariant evaluation): it passes or
fails on evidence already in the run, and its findings are machine text the
orchestrator may hand back to a stage verbatim. A *human* gate is a point where
the pipeline stops and a person rules; `brief.GATES` enumerates them and
`rubrica gate-brief --gate N` composes the reading surface for each
(`src/rubrica/brief.py`).

Gate 0, which follows `triage`, is different in kind from the human gates after
it. They review a judgment made from evidence the run already holds, so
overturning one corrects an inference about the target. Gate 0 decides what the
run can ever know — nothing after `intake` reads the corpus again — which is also
why `triage` cannot hold it: the same party selecting the inputs and ratifying
the selection would make the run unfalsifiable.

## Harbor

The external task-package format that stage 6 (`emit`) targets — `rubrica
--help` describes the `emit` subcommand as compiling "accepted instances into
Harbor packages" (`src/rubrica/cli.py`). `emit.py` pins
`HARBOR_SCHEMA_VERSION = "1.3"` into every package's `task.toml` as
`schema_version`, because a suite emitted against one Harbor task schema and
scored against another would be a silent mismatch; `emit.py`'s module
docstring states it is "the only Harbor-aware module in the project" — every
stage upstream of it is platform-neutral, so retargeting a second evaluation
platform means writing a second emitter, not re-running the pipeline. Harbor's
verifier contract is a bare float written to `/logs/verifier/reward.txt`
(`src/rubrica/suite/test.sh`); `reward.json` and `reward-detail.json` are
written alongside for a human to read, but the platform itself reads only the
bare float. `emit_run` writes one `06-suite/<sid>/` directory per accepted
scenario, containing `task.toml`, `instruction.md`, `seed.json`,
`golden.json`, `provenance.md`, and a `tests/` subdirectory holding
`expected.json`, `verify.py`, and `test.sh` (`src/rubrica/emit.py`). The
package itself has no `agent/` or `verifier/` children; those are Harbor's
runtime log paths (`/logs/agent`, `/logs/verifier`) inside the container that
actually runs the task, which `smoke.py`'s local `smoke_dir` mirrors so the
same verifier reads the same relative paths in both places
(`src/rubrica/paths.py`).

## hole

An uncovered cell in a coverage matrix, each carrying a `reason` and a
`justification` (`src/rubrica/schema/coverage-0.1.json`'s `hole` definition).
`blocked_by_gap` requires a `gap_id` and means the cell cannot close until
that gap does; `not_yet_attempted` carries no such requirement and implies
another round of `propose` could still close it — the two reasons are not
interchangeable even though both leave the cell uncovered today.

## instance

One instantiated scenario: the directory `04-instances/<scenario_id>/` holding
`seed.json`, `expected.json`, and `rationale.md`, written by a single
`rb-instantiate` fan-out member (`src/rubrica/paths.py`'s `instance_dir`,
`seed`, `expected` and `rationale`). A scenario becomes an instance only if
`rb-score` left it `active`, and from there the run's later stages address
instances rather than scenarios: `rb-challenge` writes one verdict per instance,
and `emit` compiles one Harbor package per instance whose verdict accepted it.
`RunPaths.scenario_ids_with_instances` is how the rest of the run asks which
scenarios got that far.

## manifest

`manifest.json`, minted by `intake`, holding the run's identity: its `target`
(`name` and `interface`), one `inputs[]` entry per admitted artifact carrying
`artifact_id`, `source_path`, `stored_as`, `sha256`, `kind` and `bytes`, the
`limits` (`max_rounds`, `max_scenarios`), and a `stages` map
(`src/rubrica/schema/manifest-0.1.json`). Changing a limit is `rubrica
set-limit`, which records the reason in `decisions.md` — so raising a ceiling is
a decision on the record rather than a silent hand-edit.

The `stages` map is written by `rubrica record-stage` as each stage is
dispatched: one entry per stage name with the `model`, the `effort`, and the
`skill_sha256` of the skill file that dispatch actually used. A digest that no
longer matches the file on disk therefore means the file changed after the run —
the hook working, not a defect. `intake`, `smoke` and `survey` are code and have
no entry there, and their absence is not a finding.

## objective

The survey's stated aim, `breadth` or `depth`, recorded in
`request.objective` in the catalogue (`src/rubrica/schema/catalogue-0.1.json`)
and copied verbatim onto the slice plan's `catalogue_facts.request`
(`src/rubrica/schema/slices-0.1.json`), which is where
`rb-triage-objective` reads it before any candidate is ruled on — that pass
never opens the catalogue itself. It judges whether
the objective is `supported` against the surfaces it found — `depth` on a surface
with one candidate is not supported, and neither is `breadth` when almost every
surface has no behavioural evidence at all. It may record a
`recommended_objective` if it disagrees, but its contract forbids acting on
that recommendation — it selects against the objective it was given and lets
a human decide at gate 0
(`src/rubrica/skills/rb-triage-objective/SKILL.md`).

## oracle

The reference answer for one instantiated scenario, derived *from* the seed
rather than the seed being built to fit it — `rb-instantiate`'s frontmatter
states the ordering explicitly: distractors first, "then derive that world's
oracle from the seed rather than the other way round"
(`src/rubrica/skills/rb-instantiate/SKILL.md`). Building the seed first and
the answer second is what keeps the oracle honest about what the seed
actually contains, including every distractor placed to defeat a
fabricating agent.

## partial

One `reconcile-*` pass's slice of the world model, written into the `01-` band
as its own file: `01-subjects.json`, `01-contradictions/<subject_id>.json`,
`01-capabilities.json`, `01-outcomes.json`, `01-entities.json`,
`01-goals.json`, `01-gaps.json`. Each has its own schema and its own layer-1
gate, and a later pass reads an earlier pass's partial as a *file* rather than
as a memory of having written it — which is what lets `rb-reconcile-outcomes`
quantify over the capability list instead of recalling it. No partial reads
`01-world-model.json`; the **seal** is what joins them into one — all of them
except `01-subjects.json`, which the world model has no field for.

## projection

A manufactured artifact standing in for something the corpus lacks, admitted
into the catalogue structurally by `rubrica adopt-projection` without
touching the corpus itself or the run's identity. A projection's record names
which deficiency it `closes`, which candidates it draws on as `sources`, and
a `method` with a stated `confidence`
(`src/rubrica/schema/triage-0.1.json`'s `projection` definition) — it is a
declared substitute, never a silent stand-in.

## round

One `propose` → `score` iteration of the loop that stages 02 and 03 form,
bounded by `limits.max_rounds`. `rb-propose` appends that round's scenarios to
`02-scenarios.json` and never renumbers an earlier round's; `rb-score` writes
`03-coverage/round-N.json` alongside `03-coverage/latest.json`, carrying
`progress.new_cells_this_round`, `progress.rounds_without_progress`, and a
`verdict` of `continue`, `converged`, `halted_no_progress`, or
`halted_round_cap` (`src/rubrica/schema/coverage-0.1.json`). Score *computes*
that verdict and stops there; only the orchestrator acts on it, so the stage
that measures progress is never the stage that decides whether to spend another
round.

## run

One directory holding the entire state of one pipeline execution — every
artifact `RunPaths` names, from `00-catalogue.json` through `06-suite/` and
`07-report.json`, addressed off a single `root` (`src/rubrica/paths.py`'s
`RunPaths` class). Nothing about a run's state lives anywhere else; a stage
that needs a fact reads it from this directory or does not have it.

## scenario

A proposed test, appended to `02-scenarios.json` by one round of `rb-propose`
and never renumbered by a later round. Its schema requires a `goal_id`, an
`actor_id`, a `hop_depth`, at least one `capability_refs` entry, a
`discriminating_fact`, a `status` (`proposed`, `active`, `duplicate`, or
`rejected`), and a `provenance` block naming the `hole_refs` and `claim_ids`
that motivated it (`src/rubrica/schema/scenarios-0.1.json`). A scenario's `id`
is permanent even if a later round marks it `duplicate` or `rejected` — the
round history is preserved, not overwritten.

## seal

A code step that assembles one stage's record out of the staged parts a fan-out
wrote, and writes nothing at all when it cannot assemble faithfully. Code rather
than a prompt for the reason `emit` is code — two runs with identical parts must
produce a byte-identical record, or variance stops being attributable to the pass
that caused it — and for one more: a code step streams nothing, so it cannot be
killed mid-record by an idle reset however large the assembled record gets.

This pipeline has two. `triage-seal` reads `00-objective.json`,
`00-slices.json`, every `00-dispositions/<slice_id>.json`, `00-audit.json` and
`00-adoptions.json`, and writes `00-triage.json` (`src/rubrica/seal.py`).
`reconcile-seal` reads the manifest, the five singleton partials and every
`01-contradictions/*.json` — and **not** `01-subjects.json`: the world model has
no subjects field, so the cover is an input to the contradiction fan-out, to
`reconcile-gaps`, and to `check-refs`, not to the seal — folds each capability's
outcome classes into that capability, counts the `denominator` once, and writes
`01-world-model.json` (`src/rubrica/reconcile.py`, run as
`rubrica reconcile-seal`).

**A seal assembles; it does not check.** Cross-artifact checking is layer 2 and
lives in `refs.py`, which runs over the sealed record afterwards on any run,
including one this seal never sealed. What a seal itself reports is the narrow
class where assembly cannot faithfully represent what it was handed, and in every
one of those it writes no record at all — a half-assembled record would clear
layer 1 for the fields it did manage to fill and read as a complete decision to a
human at the gate.

For `triage-seal` that class is: a part absent, unparseable, or missing its
payload key; a candidate with no disposition anywhere across every part and
adoption, or with more than one; a part ruling on a candidate outside its own
slice; no `admit` anywhere across the union of every part and adoption; and a
`digest_insufficient` or `needs_projection` decline whose matching deficiency or
projection is nowhere in the audit. For `reconcile-seal` it is four items, listed
under `rubrica reconcile-seal` in [`docs/reference/cli.md`](../reference/cli.md).

Sealing is idempotent: nothing a seal reads is the sealed record, so a re-seal
after a gate-0 adoption re-derives the record from the parts rather than editing
what is already there.

## seed

The concrete world one scenario's test runs against, including its
distractors, written by `rb-instantiate` per instance. The seed schema
constrains only the envelope — `schema_version` and a `collections` object of
arrays — because a seed's real shape comes from the world model's entities,
which `refs.py` checks it against (`src/rubrica/schema/seed-0.1.json`).
Every seed value is synthetic by construction: the world model has no
representation for a field's *value domain* — `capability.params` and
`entity.fields` carry only a name and a type, with `additionalProperties:
false` on both — a param must additionally state whether it is `required`,
and a field cannot state that at all
(`src/rubrica/schema/world-model-0.1.json`) — so a concrete value anywhere
downstream of the seal is a prescription to `rb-instantiate`, never an
assertion about the target system. See `docs/design/limitations.md` for the
consequences this has for what a seed can and cannot be checked against.

## shard

One slice's own file — `00-slices/<slice_id>.json`, written by `triage-slices`
alongside the plan — and the entire input one `rb-triage-rule` member reads. It
carries `slice_id`, the run's `request` and `policy` verbatim, that slice's
provenance, and the full catalogue record of every candidate the slice owns
(`src/rubrica/slices.py`'s `write_slices`). `refs.check_slices` holds the shards
and `00-slices.json` to the same partition of the catalogue, so a shard cannot
drift from the plan that named it.

Two things about it are deliberate. Copying `request` and `policy` into every
shard is not redundancy for its own sake: `canonical_bytes` sorts keys, so in
the 595KB catalogue that motivated slicing `run_id` lands some 608KB into the
file, and a dispatch reading only its own candidates still had to seek across
the whole catalogue for two small fields. And a shard is sized so that reading
it is one `Read` call — the default cap is 64KB against the harness's 256KB
whole-file refusal — because a slice a member had to read in pieces would
reproduce the cost slicing exists to remove.

## slice

A byte-bounded set of the catalogue's admissible candidates that one dispatch
can hold, minted by `triage-slices` (code) and recorded in `00-slices.json`
with an `id`, a human-readable `label`, the catalogue `groups` it draws from,
its total digest `bytes`, its `candidate_ids` and its provenance
(`src/rubrica/schema/slices-0.1.json`). One `rb-triage-rule` member is
dispatched per slice and reads that slice's shard only, never a sibling's.

**A slice is a reading unit, not a decision unit**, and that distinction is what
makes cutting the catalogue in code acceptable at all. Nothing about the cut
decides anything: every candidate still reaches a member, still receives a
reasoned per-candidate disposition, and is still overrulable one at a time by a
human at gate 0 — where a code-side filter that dropped or merged candidates
would be deciding. The cut is top-down (descend the directory tree only where
the cap forces it, cluster a container's elements by digest signature before any
byte split, pack only adjacent siblings), and `src/rubrica/slices.py` records
the two
alternatives that were measured and rejected. What no check can rule on is
whether a slice is *coherent*; see
[`docs/design/limitations.md`](../design/limitations.md).

## slice provenance

What a slice says about the groups it is only a part of: one entry per group it
draws from, naming the `group`, how many of that group's candidates are
`in_this_slice`, how many exist in `in_group_total`, and the `other_slices`
holding the rest (`src/rubrica/schema/slices-0.1.json`). An empty `other_slices`
means the group was not split. It is written by `triage-slices` into both the
plan and every shard, because the member is the reader who needs it.

It exists for the one thing a member cannot otherwise know. A member holding 42
of 500 elements that share a digest signature has no way to tell from its shard
alone that it is holding a twelfth of a near-duplicate family; code knows,
cheaply and deterministically. Stating it takes no judgment away — it lets the
member name the situation in a disposition's `reason`, and `rubrica gate-brief`
renders every group the slicer split across more than one slice for the human at
gate 0. That is what converts the residue of slicing from an invisible
over-admission into a recorded one.
## subject

A topic two claims could disagree inside — one operation, one entity, one rule
the store maintains — used as the fan-out slice for the contradiction sweep.
`rb-reconcile-subjects` names them and assigns claims to them; one
`rb-reconcile-contradict` member is dispatched per subject with that
`subject_id` and nothing about a sibling's, and writes
`01-contradictions/<subject_id>.json` — empty array included, because the file
is the record that the subject was swept
(`src/rubrica/schema/subjects-0.1.json`).

## subject cover

The whole of `01-subjects.json`: every claim in `01-claims/` assigned to at
least one subject. A **cover, not a partition** — a claim may appear under
several subjects, and `rb-reconcile-subjects` is instructed to over-assign
when the subject is unclear, because over-assignment costs a member some
re-reading while under-assignment costs a contradiction nobody ever finds.
`refs.check_subjects` holds it to totality: a claim no subject covers is a
finding, which is the property a heuristic pair filter could never have had.
What stays unchecked is a disagreement whose two claims land under *different*
subjects — see `docs/design/limitations.md`.

## surface

A coherent region of the target's behaviour that a suite could be built about:
a persona, an API area, a workflow, a subsystem. `rb-triage-objective` groups
the slice plan's own `groups` and slice labels into surfaces by what they are
evidence *about* — one surface can span several groups, and one group can be a
surface on its own — and records each with a `name`, the `evidence` candidate
ids, and a `weight` of `{candidates, bytes}` that is plain arithmetic so a
reader can check it — `refs.check_objective` recomputes both numbers and reports
a disagreement (`src/rubrica/schema/triage-0.1.json`'s
`objective_review.surfaces[]`; the term itself is defined in
`src/rubrica/skills/rb-triage-objective/SKILL.md`). It declines nothing: a
candidate is admitted or declined by the per-slice `rb-triage-rule` fan-out
that runs after it. `weight.bytes` sums each evidence candidate's entry in
`00-slices.json`'s `catalogue_facts.candidate_bytes` — the size of the source
file — and never the size of its serialised catalogue row. The pass reads that
map rather than the catalogue, and `refs.check_objective` recomputes the same
sum from the catalogue's own `candidates[].bytes`; the two agree by
construction, and that agreement is what `refs.check_slices` verifies. A row is
clamped, so row size saturates:
a 2.7MB source and a 20KB one can serialise to nearly the same row, and a
weight that saturates stops discriminating exactly where this pass needs it.

A surface is not a guess at the target's internal structure — it groups the
evidence by what that evidence is *about*. Enumerating them is not a courtesy
either: the surfaces and their weights are what let a human at gate 0 see that
the objective they declared excludes something they wanted, and `supported` in
the same record is triage's judgment on whether the surfaces it found can carry
that objective at all.

## verdict

`rb-challenge`'s ruling on one instantiated scenario: `accept`, `re-seed`, or
`reject`. The schema also requires `uniquely_determined`,
`derivable_without_guessing`, `minimum_tool_calls_found`, and `notes`
(`src/rubrica/schema/verdict-0.1.json`); a `false` `uniquely_determined`
requires at least one `alternative_answers` entry with its own
`world_consistent_reason`, so a verdict that says the scenario is ambiguous
must also show the ambiguity it found rather than merely asserting it.

## world model

The single reconciled picture of the target system, assembled by
`reconcile-seal` from the **partials** the `reconcile-*` passes wrote out
of every extracted claim: capabilities, entities, actors, goals,
recorded contradictions, recorded gaps, and the frozen coverage denominator,
all required by `src/rubrica/schema/world-model-0.1.json`. Every element in it
— a capability, an entity, a goal — carries a `claims` array pointing back to
the claim ids that support it, so nothing in the world model floats free of
the evidence it came from.
