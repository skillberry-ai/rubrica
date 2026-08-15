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
`decline_reason` enum).

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
`emit`, `smoke`). A gap naming `propose` in its `blocks` list is what makes
`rb-score` compute a coverage verdict of `halted_no_progress` rather than
letting the round loop spin forever on something no input can ever answer.

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

## objective

The survey's stated aim, `breadth` or `depth`, recorded in
`request.objective` in the catalogue (`src/rubrica/schema/catalogue-0.1.json`)
and read by `rb-triage` before it rules on any candidate. Triage may record a
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
`entity.fields` carry only `name`/`type`(`/required`), with
`additionalProperties: false`
(`src/rubrica/schema/world-model-0.1.json`) — so a concrete value anywhere
downstream of reconcile is a prescription to `rb-instantiate`, never an
assertion about the target system. See `docs/design/limitations.md` for the
consequences this has for what a seed can and cannot be checked against.

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
