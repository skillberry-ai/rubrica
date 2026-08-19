# Glossary

Terms used across the artifact contract, the schemas, and the CLI, defined
from what actually produces or consumes them. Alphabetical.

## candidate

One catalogued file (or exploded element of a container file) from a survey's
corpus, recorded with a bounded digest and never its own bytes — the
catalogue schema's `candidates[]` entries carry `sha256`, `bytes`, `kind`, and
`digest`, but nothing that reproduces the source content
(`src/rubrica/schema/catalogue-0.1.json`). `rubrica survey` writes one entry
per candidate; `rb-triage` then rules on each as `admit` or `decline`, with
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
way for goals. How many cells exist is fixed by `denominator.capability_cells`
before the first round runs, so "coverage" here always means a fraction of a
frozen set — never a judgment that enough tests exist. A cell that is not
covered is recorded as a `hole`, with a reason for why not.

## claim

One atomic, evidence-backed statement about the target system, extracted by
`rb-extract` from exactly one input artifact. Its schema requires a `kind`
(`capability`, `entity`, `invariant`, `actor`, `goal`, or `outcome_class`), a
`statement`, at least one `evidence` entry carrying an `artifact_id` and a
`locator`, a `confidence`, and a `derivation`
(`src/rubrica/schema/claims-0.1.json`). Every claim traces back to the one
input it came from; nothing later fabricates a claim without a locator.

## contradiction

Two claims that cannot both hold, recorded rather than resolved.
`rb-reconcile` writes one entry per contradiction it finds, naming `claim_a`,
`claim_b`, the `nature` of the conflict, a `resolution`
(`unresolved`, `preferred_a`, `preferred_b`, or `both_possible`), and a
`rationale` (`src/rubrica/schema/world-model-0.1.json`'s `contradiction`
definition). The world model carries the disagreement forward instead of
quietly picking a side.

## corpus

The directory roots `rubrica survey` walks, recorded verbatim in
`request.corpus_roots` (`src/rubrica/schema/catalogue-0.1.json`). It is the only
thing a run ever sees of the target's own files, and it is read exactly once:
`survey` catalogues what it finds, `rb-triage` rules on the catalogue, and
nothing downstream of `intake` opens the corpus again.

A file can fail to reach `extract` two different ways, and the difference is
load-bearing. `survey` *excludes* it mechanically, recording a `path` and one
`exclusion_reason` — `gitignored`, `vcs_metadata`, `binary`, `lockfile`,
`vendored`, `duplicate`, `unreadable`, or `operator_excluded` — and it never
becomes a candidate at all. `rb-triage` *declines* a candidate as a judgment,
under one of the `decline_reason` codes. An exclusion is arithmetic; a decline
is the thing gate 0 exists to review.

## deficiency

Something the admitted set does not cover that the objective needs, recorded by
`rb-triage` with a `deficiency_id`, a `subject`, a `statement`, and optionally a
`closed_by` naming the projection that answers it
(`src/rubrica/schema/triage-0.1.json`). It is triage's own account of what its
selection cannot do, which is why an empty `deficiencies` array is a claim
rather than an absence: it says the admitted candidates cover everything the
objective needs, and a human at gate 0 will read it as that. Distinct from a
`gap`, which `rb-reconcile` records later about the *target* rather than about
the corpus.

## denominator

The coverage denominator, computed once by `rb-reconcile` and frozen at a
`version` for the rest of the run. `denominator.capability_cells` counts
capability × outcome-class pairs, and `denominator.goals` counts goals
(`src/rubrica/schema/world-model-0.1.json`). Every later coverage report
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
and the only thing `rb-triage` ever reads about that candidate — never its
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

`rb-triage`'s ruling on one candidate: `admit` or `decline`, carrying a prose
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

Something no input artifact says anything about, recorded by `rb-reconcile`
with a `subject`, an `unknown`, `why_it_matters`, and a `blocks` list naming
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
and read by `rb-triage` before it rules on any candidate. Triage judges whether
the objective is `supported` against the surfaces it found — `depth` on a surface
with one candidate is not supported, and neither is `breadth` when almost every
surface has no behavioural evidence at all. It may record a
`recommended_objective` if it disagrees, but its contract forbids acting on
that recommendation — it selects against the objective it was given and lets
a human decide at gate 0 (`src/rubrica/skills/rb-triage/SKILL.md`).

## oracle

The reference answer for one instantiated scenario, derived *from* the seed
rather than the seed being built to fit it — `rb-instantiate`'s frontmatter
states the ordering explicitly: distractors first, "then derive that world's
oracle from the seed rather than the other way round"
(`src/rubrica/skills/rb-instantiate/SKILL.md`). Building the seed first and
the answer second is what keeps the oracle honest about what the seed
actually contains, including every distractor placed to defeat a
fabricating agent.

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
downstream of reconcile is a prescription to `rb-instantiate`, never an
assertion about the target system. See `docs/design/limitations.md` for the
consequences this has for what a seed can and cannot be checked against.

## surface

A coherent region of the target's behaviour that a suite could be built about: a
persona, an API area, a workflow, a subsystem. `rb-triage` groups every
candidate into exactly one surface — including the ones it declines — and records
each with a `name`, the `evidence` candidate ids, and a `weight` of
`{candidates, bytes}` that is plain arithmetic over the catalogue so a reader can
check it (`src/rubrica/schema/triage-0.1.json`'s `objective_review.surfaces[]`;
the term itself is defined in `src/rubrica/skills/rb-triage/SKILL.md`).

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

The single reconciled picture of the target system that `rb-reconcile`
produces from every extracted claim: capabilities, entities, actors, goals,
recorded contradictions, recorded gaps, and the frozen coverage denominator,
all required by `src/rubrica/schema/world-model-0.1.json`. Every element in it
— a capability, an entity, a goal — carries a `claims` array pointing back to
the claim ids that support it, so nothing in the world model floats free of
the evidence it came from.
