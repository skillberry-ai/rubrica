# Skill-Based Test Generator — Design

**Date:** 2026-08-06
**Status:** Approved design. Fully implemented as of the skills build — contract
spine, measurement layer and all eight skills — and reconciled against what four
builds measured. Not yet run on the real target; see §11.
**Author:** Jonathan Bnayahu (with Claude)

## 1. What this is

A pipeline that takes heterogeneous artifacts describing an agentic system —
design and specification documents, captured logs and trajectories, source code —
and produces a runnable, scored test suite for it.

The pipeline is implemented as a set of AI skills driven by an agentic harness
(Claude Code). It is a **greenfield experiment**: `task-extractor` and
`harbor-test` in the sibling directories are *references only*, not dependencies.
Nothing here reuses their code.

### The hypothesis under test

> Can prompt-carried judgment survive a chain of schema-validated artifact
> handoffs, and produce a test suite good enough to run?

Every design decision below is subordinate to making that question answerable.
Where a choice trades output quality for the ability to *localize a defect to a
stage*, we take the localization.

### The central design claim

Skills are stateless prompt injections. They carry judgment, not state. So the
real design object is **not the set of skills** — it is the **on-disk artifact
contract between them**. Get that contract right (versioned, schema-validated,
each stage reading its predecessor's file and writing its own) and the skills
become independently testable and swappable. Get it wrong and you have six
prompts playing telephone.

Corollary, applied throughout: **judgment-heavy steps are skills; contract-
enforcing steps are deterministic code that a skill invokes.**

## 2. Decisions taken

| Question | Decision |
|---|---|
| Relation to `task-extractor` | None. Greenfield; `task-extractor` and `harbor-test` are references. |
| First target | PARSEC / aap2-style agent — chosen because `harbor-test` has ~10 hand-authored aap2 bench tasks that serve as a human gold suite to measure against. |
| Skill purity | Prompt-first, harden empirically. Stages start as pure prompt + file conventions. Exception from day one: schema validation and a "does the suite run" gate are real code, because the experiment is unevaluable without a trustworthy scorer. Extract more code only where a stage proves flaky across runs. |
| Orchestration | An orchestrator skill dispatches **one subagent per stage**, communicating only through on-disk artifacts. Stage skills are written so they are *both* standalone-invocable and subagent-dispatchable. |
| Test data | Stage 4 seeds a **simulated backend** (the `db.json` / `seed.json` shape). Tests are hermetic; assertion reachability holds by construction. The IR keeps data requirements declarative so a live-backend binder remains possible later without redesign. |
| Coverage denominator | **Two dimensions, reported separately.** (a) Capability coverage: every operation × its outcome classes (success, empty, not-found/error, underspecified). (b) Goal coverage: every inferred user goal has ≥1 scenario at each hop-depth it supports. |
| Success criteria | All four: suite executes and yields a non-degenerate score spread; recall + novelty vs. the human gold suite; run-to-run reproducibility; expert review of a stratified sample. |

## 3. Pipeline shape

### Organizing principle

Stage boundaries sit where the **work changes shape** — at a fan-out point or a
genuine barrier — rather than where the vocabulary changes. Four of those
boundaries carry real weight, and the reasoning behind each is what the rest of
this design rests on.

**Ingestion is two stages: extract, then reconcile.** Reading a design document, a
trace, and a source tree are independent jobs — one subagent each, none seeing the
others' conclusions — so extract is a fan-out. Merging their claim sets is
inherently cross-artifact, so reconcile is a barrier. Keeping them separate is
what makes "the spec says this returns 404 but the trace shows an empty list" a
*recorded contradiction* rather than something silently resolved by whichever
artifact was read last. Gap and contradiction reporting are structural
consequences of this split, not features bolted onto a single ingest step.

**Seeding a world and stating its oracle are one stage, run per scenario.** The two
are mutually constraining, so neither can come first. `harbor-test`'s
`bench-aap2-010-log-does-not-say` is a task whose entire point is that the answer
*is not in the data* — that world cannot be authored without already knowing what
will be verified. Any ordering that fixes the data first forces the labeler to
accept whatever world it was handed, which yields labels that are true but
trivial ("the query returned some jobs").

So a single stage co-designs them: identify the **discriminating fact** the test
hinges on → seed a world in which that fact is *uniquely* determined → state the
oracle in terms of it. Reachability then holds by construction, and the
reachability gate is a regression test on that invariant rather than the mechanism
enforcing it.

**Verifying a test is adversarial, and comes after it is authored.** A labeler must
read the seed in order to label at all, so no arrangement of the authoring stages
yields an independent check — independence has to be bought separately. A fresh
subagent, given only the seed and the instruction, attempts to find a *second*
world-consistent answer. Ambiguous-but-plausible tests are the primary defect
class in generated benchmarks, and only a stage structured this way catches them
(§6).

**Deduplication belongs inside the coverage loop, and execution is a gate.** The
loop proposes scenarios round by round and will produce near-duplicates across
rounds; deduplicating *before* the per-scenario fan-out is what stops the
expensive stages from being paid twice for the same test. And because "the suite
actually runs" is a stated success criterion (§2), it is a gate with a report
rather than an assumption.

### Stages

```
0.  intake        code                       register + hash inputs, classify by type
1a. extract       skill, fan-out/artifact    01-claims/<aid>.json
1b. reconcile     skill, barrier             01-world-model.json
2.  propose       skill, fan-out/hole-cluster 02-scenarios.json  (round-tagged)
3.  score         skill + code               03-coverage/round-N.json
      └─ orchestrator loop: dedupe → score → (holes ∧ rounds<K ∧ progress) → back to 2
4.  instantiate   skill, fan-out/scenario    04-instances/<sid>/{seed,expected}.json + rationale.md
5.  challenge     skill, fan-out/scenario    05-verdicts/<sid>.json
6.  emit          code + thin skill          06-suite/<sid>/   Harbor package
7.  smoke         code                       07-report.json
```

Six stage skills and three code stages, plus an orchestrator skill (§5) and a
thin `tg-emit` entry point (§7).

**Terminology, used consistently below.** A **gap** is missing *knowledge about
the target* recorded in the world model — the pipeline cannot proceed past it by
reasoning, only by being given another input artifact. A **hole** is an
*uncovered coverage cell* recorded in the coverage report — the pipeline closes
holes by proposing more scenarios. The two never substitute for one another: a
hole whose cause is a gap is recorded as `blocked_by_gap:<gap_id>` and is not
counted as closable.

### Deliberately not a stage

**Difficulty calibration.** Success criterion #1 wants a non-degenerate score
spread, and a suite of single-tool-call probes will all-pass. Rather than add a
calibration stage, `hop_depth` is a first-class scenario field, the coverage
report shows its distribution, and `tg-challenge` independently measures
`minimum_tool_calls_found` as a cross-check. Decide whether calibration needs
machinery *after* seeing a real spread from stage 7. Consciously deferred.

## 4. The artifact contract

### Consequence for stage boundaries

The **goal inventory lives in stage 1b**, and stage 2 designs scenarios against a
*frozen goal list*. A goal-based denominator that stage 2 also invents can reach
100% by simply not imagining more goals. So 1b enumerates capabilities, outcome
classes, and goals, and computes the denominator once. Stage 2 may *request* an
amendment, but that costs an explicit orchestrator decision, bumps
`denominator_version`, and is recorded in `decisions.md`. The denominator can
move; it cannot move silently.

### Run directory

```
runs/<run-id>/
  manifest.json           run id, target, input hashes, per-stage model+effort+skill hash
  00-inputs/              registered copies, classified
  01-claims/<aid>.json    one per input artifact          (1a, fan-out)
  01-world-model.json     reconciled                      (1b, barrier)
  02-scenarios.json       round-tagged, append-only       (2)
  03-coverage/round-N.json + latest.json                  (3)
  04-instances/<sid>/     seed.json expected.json rationale.md
  05-verdicts/<sid>.json
  06-suite/<sid>/         Harbor package
  07-report.json
  measurement/            outputs of the measurement tools, which are not stages
    smoke/<role>/<sid>/    agent/ (transcript) + verifier/ (reward.json, reward.txt)
    recall.json recall.md  compare-gold
    review/                packet.md, sample.json
  decisions.md            append-only orchestrator log
```

`measurement/` is outside the numbered prefixes on purpose. Those name pipeline
stages the orchestrator dispatches, and `STAGES`/`STAGE_ARTIFACTS` must not grow
an entry for a tool nothing dispatches. `diff-runs` writes nothing at all: it
spans two runs and belongs to neither.

Artifacts are the **only** channel between stages. A dispatched subagent receives
exactly three things: the run directory path, its stage name, and its skill. No
conversational context is threaded through. That is what makes the contract real.

### Schemas

**Claim** — the atom of stage 1a. Every statement about the target is a claim,
never a bare assertion:

```
{id, kind: capability|entity|invariant|actor|goal|outcome_class,
 statement, payload,
 evidence: [{artifact_id, locator, quote}],
 confidence: high|medium|low,
 derivation: stated | inferred | reverse_engineered}
```

`derivation` is what makes gap reporting honest — "the OpenAPI spec states this"
and "I guessed from one trace" must not be indistinguishable downstream.

**World model** (`01-world-model.json`) — reconciled, and the only place the
denominator is computed:

```
capabilities:    [{id, operation, params,
                   outcome_classes: [{id, kind: success|empty|not_found|error|underspecified}],
                   claims, confidence}]
entities:        [{id, fields, relations, invariants, claims}]
actors:          [{id, name, claims}]
goals:           [{id, actor_id, statement, expected_hop_depths, claims}]
contradictions:  [{claim_a, claim_b, nature,
                   resolution: unresolved|preferred_a|preferred_b|both_possible, rationale}]
gaps:            [{id, subject, unknown, why_it_matters, blocks: [stage], suggested_input}]
denominator:     {version, capability_cells: M, goals: N}
```

Entity `invariants` carry either `machine:` (a small safe expression form —
equality, ordering, count-of-relation, string-join) or `prose:` when they do not
fit. `check-refs` evaluates the `machine:` ones; `prose:` ones are skill
self-checks. This is bounded on purpose: no general DSL. It covers the invariant
class that demonstrably bites (see §6).

**The world model has no representation for a field's value domain, and the
consequence is architectural rather than cosmetic.** `capability.params` and
`entity.fields` are both `additionalProperties: false` carrying only a name, a
type, and — for params — whether it is required. No enum, no range, no examples. A
prose `invariant` could smuggle a domain in, but nothing is designed to read one.
So no stage downstream of 1b can ground a *value* in anything: a concrete value
appearing in a scenario's `discriminating_fact`, or in a seed, is always a
**prescription to `tg-instantiate`** and never an assertion about the target, and
**every seed value is synthetic by construction.** That is what makes the
discriminating fact's uniqueness requirement satisfiable at all — uniqueness is a
property of the seeded world, which stage 4 builds, not of the target's real
data, which nothing here has. It is written down because not knowing it cost this
build two wrong fix rounds: a queue name in a proposed scenario was read as an
unsupported claim about the target and driven as a finding through two rounds,
when the world model contains no queue name at all, has nowhere to put one, and
the only real defect was that the fact was *valueless* and therefore not unique.
Prescribing any concrete value is an instruction to stage 4, not a claim.

**Scenario** (`02-scenarios.json`):

```
{id, round, goal_id, actor_id, title, user_intent, hop_depth,
 capability_refs: [{capability_id, outcome_class_id}],   ← the cells it claims to cover
 discriminating_fact,                                    ← the spec stage 4 builds to
 status: proposed|active|duplicate_of:<id>|rejected:<reason>,
 provenance: {hole_refs, claim_ids, round}}    ← which coverage holes it targets
```

`discriminating_fact`, declared at proposal time, is what stops stage 4 from
facing a blank page and inventing a trivial world.

**Coverage** (`03-coverage/round-N.json`):

```
{round, denominator_version,
 capability_matrix: {cells: [{capability_id, outcome_class_id, scenario_ids, covered}],
                     covered, total, pct},
 goal_matrix:       {rows: [{goal_id, scenario_ids, hop_depths_present,
                             hop_depths_expected, covered}], covered, total, pct},
 holes: [{ref, reason: not_yet_attempted|unreachable|out_of_scope|blocked_by_gap:<id>,
           justification}],
 progress: {new_cells_this_round, rounds_without_progress},
 verdict: continue|converged|halted_no_progress|halted_round_cap}
```

`verdict` is *computed* here and *acted on* by the orchestrator — scoring does not
decide to iterate.

**Oracle** (`04-instances/<sid>/expected.json`) — the reachability link is a
field, not a convention:

```
{scenario_id, discriminating_fact, answer_reference,
 assertions: [{kind: answer_contains|answer_excludes|value_equals,
               target, value, rationale,
               grounded_in: {seed_pointer}}          ← JSON pointer into this scenario's seed.json
              |{kind: tool_called|tool_not_called,
               target, value, rationale, capability_id}],  ← grounded in the world model instead
 trajectory: {match: subset|exact-set|exact-sequence, operations},
 completion: {status, nonempty_answer}}
```

Grounding differs by assertion kind. Data assertions point into the seed;
trajectory assertions name a capability, because a JSON pointer into seed data
would be meaningless for them. There is no separate `negative_expectations`
field: everything it was for — "must not claim a root cause the data does not
support" — is `answer_excludes`, and a second field expressing the same thing
would either duplicate the verifier or hold prose nothing evaluates.

`grounded_in.seed_pointer` reduces the reachability gate to a few lines of code:
for a positive assertion the pointer must resolve and contain its value; for
`answer_excludes` the check inverts — the pointer must resolve to nothing. That
is how `log-does-not-say`-style tests become both expressible and verifiable.

**Verdict** (`05-verdicts/<sid>.json`):

```
{scenario_id, uniquely_determined,
 alternative_answers: [{answer, world_consistent_reason}],
 derivable_without_guessing, minimum_tool_calls_found,
 verdict: accept|re-seed|reject, notes}
```

`minimum_tool_calls_found` is the adversary independently measuring difficulty,
cross-checking stage 2's `hop_depth` claim.

Each entry in `manifest.json`'s `inputs` list carries a `stored_as` field — the
filename the artifact was registered under inside `00-inputs/` — so a reader
re-verifying a digest does not have to re-derive intake's naming rule. Two
definitions of that rule is how they drift.

Two schemas in `src/testgen/schema/` are not stage artifacts at all:
`agents-0.1.json` and `gold-0.1.json` validate the human-authored config files
the measurement tools take as input (the agent roster, the hand-authored gold
benchmark). A schema gates artifacts the code did not write. Measurement
outputs, which this project's own code writes, are gated by unit tests
instead; a schema over them would only restate the writer. A failure in a
human-authored config is exit 2, not exit 1: there is no stage to hand a
repair prompt to.

### Three validation layers

1. **Schema** — `bin/validate <run-dir> <stage>` runs after every stage; output
   must validate before the next dispatch. On failure: **one** repair attempt
   (re-dispatch the same stage with the validator error appended), then halt.
   Bounded, not a retry spiral.
2. **Referential integrity** — `bin/check-refs`, expressing what JSON Schema
   cannot: every `capability_id` in 02 exists in 01; every `scenario_id` under
   04/05/06 is judged (`active` or `rejected`) in 02; every `seed_pointer`
   resolves within its *own* scenario's seed; `machine:` invariants hold over
   each seed. `rejected` is admitted here rather than `active` alone because the
   challenge loop below marks a scenario `rejected` *after* it has been
   instantiated and judged, and that artifact record of the rejection is
   precisely what the honest-hole report ("87%, 3 cells lost to rejected
   scenarios") is built from — requiring `active` would make this check
   permanently dirty in a state the pipeline prescribes, and would delete the
   evidence the report needs. `proposed` and `duplicate` are still findings.
3. **Smoke** — stage 7: does the emitted suite actually execute.

**What layer 2 cannot check, stated here because two real defects lived under
it.** Every world-model element cites the claims it rests on, and `check-refs`
verifies that each of those citations *resolves* — never that the claim it
resolves to *supports* the element. The golden fixture, which is the model answer
a skill imitates, shipped two elements asserting more than their cited claims
said: an outcome class describing a return value no claim mentioned, and a
contradiction rationale resting on a fact no claim supplied. Both passed layer 2
clean. A live `tg-reconcile` run reported the first as a gap — correctly, from the
claim set it was given; the second was found by reading the fixture against its
own claims while reviewing that same run. Neither was reachable any other way. No
mechanical check is proposed for this, and the reason is not
laziness — support is semantic. The clearest illustration is a third case from the
same sweep, ruled *not* a defect: an entity's relation cardinality whose
supporting claims do exist and are cited, from neighbouring nodes rather than
from the entity itself. Reference locality, not invention. If "supported" meant
"some claim somewhere in this file mentions it", that case would pass and so
would the two real ones; if it meant "cited from the element that asserts it",
the legitimate case would fail. There is no predicate in between that is not a
reading of the prose. So this stays a human check, and §9's negative fixtures are
how it is exercised.

### Reproducibility hooks

`manifest.json` records, per stage: model, effort, and a content hash of the
`SKILL.md` used. Two runs are comparable only if those match.

**`testgen record-stage` is the writer, and until the skills build there was
none.** That absence was not cosmetic. `stability.comparability` gates
`diff-runs`' headline verdict on the two runs' stage maps agreeing, and it
iterates the *union* of their keys — so with both maps always empty the loop body
never ran and no reason was ever appended. Every pair of runs with matching
inputs compared as comparable: a check passing because its input was absent.

Adding the writer fixed the cause and not the check, and the check needed
fixing too: an empty `stages` map is still reachable — it is *every* intake-only
run, and any run where the orchestrator never called `record-stage` — and the
loop still took it zero times. So `comparability` now names an empty stage map
on either side as its own reason, per side, the same way it already named an
unreadable manifest as its own reason rather than as an empty digest set. One
principle at three depths: **absence must not read as agreement.** A `stages`
value that is not a mapping at all is normalised to empty so it reaches that
check instead of raising `TypeError` on a stage-name index.
`record-stage` computes the digest from the `--skill` path it is handed rather
than accepting a digest string, because the whole point of the hook is that the
recorded hash is of the file the run actually used, and a caller that can pass a
digest can pass the wrong one. It hashes the whole file, prose included, since a
changed Method section changes what the run did. A consequence worth stating so
it is not misread as a defect: a recorded `skill_sha256` that no longer matches
the file on disk means the skill was edited *after* that stage ran. This build
produced exactly that case by accident, and the hook was behaving correctly.

**`decisions.md` has a writer for the same reason: `testgen decide`.** One
timestamped line per orchestrator branch, appended. It refuses an empty or
whitespace-only note — a blank entry records that a decision was made and not
what it was, which is worse than no entry — and refuses a note containing a
newline, because every reader of this file parses it one line per entry and an
embedded newline silently corrupts the format for every line written after it.

`bin/diff-runs A B` compares artifact by artifact, so variance can be attributed
to a stage — the difference between "the pipeline is nondeterministic" and
"stage 2 is nondeterministic and everything downstream is stable given a fixed
02."

**Run ids and timestamps are minted by intake (code), never by skills.** A skill
that invents a timestamp makes two otherwise-identical artifacts diff. Exactly two
places in the codebase write one — `intake`, for `manifest.created_utc`, and
`decide`, for each notebook line (`record-stage` writes no timestamp at all) — and
both go through one format string, `manifest.UTC_FORMAT`, for the same reason
`manifest.stored_as` exists: two spellings of a format is how a reader's parser
comes to work on one file and not the other.

## 5. Skill anatomy and orchestration

```
src/testgen/skills/tg-{orchestrate,extract,reconcile,propose,score,instantiate,challenge,emit}/SKILL.md
                            (package data, for the same reason the schemas are)
src/testgen/schema/*.json   (package data: an installed copy can validate)
bin/{intake,validate,check-refs,dedupe-candidates,emit,smoke,diff-runs,compare-gold,
     sample-for-review,check-skills,record-stage,decide}
```

Shipped as one console script with subcommands — `testgen intake`,
`testgen validate`, … — rather than a `bin/` directory of separate files. The
names and the responsibilities are as listed; only the packaging differs.

**The skills ship as package data too**, under `src/testgen/skills/` rather than
at the repository root, for the reason the schemas moved there: an installed
non-editable copy that can validate and emit but cannot find its own skills is a
copy that cannot run. `TESTGEN_SKILLS_DIR` overrides the location so a candidate
skill set can be checked without reinstalling. The names and the
responsibilities are unchanged from the list above.

**Each skill carries a machine-readable `## Contract` block** alongside its five
prose sections — a TOML table declaring `stage`, `reads`, `writes`, `schemas` and
`invokes`, with every artifact named by its `paths.RunPaths` attribute and never
as a literal path. `testgen check-skills` holds that declaration to the code that
owns each name: `stage` against `paths.STAGES` *and* against the directory name,
since the orchestrator dispatches a skill as `tg-<stage>` and validates its
output as `<stage>`; every `reads`/`writes` entry against a public `RunPaths`
attribute; `schemas` against `validate.STAGE_ARTIFACTS[stage]` by set equality in
both directions, so an omitted kind and an invented one are separate findings;
and every `invokes` entry against the CLI's own subparser roster (`cli.SUBCOMMANDS`,
the same tuple `_build_parser` iterates, so the parser and the check cannot
disagree). It also checks that the five sections are present, in order, and that
section 5 is not empty — a skill with no stated refusal conditions confabulates
rather than recording a gap. The roster of required skills is *derived* from
`STAGES` rather than restated, so adding a stage demands a skill without anyone
remembering to edit a constant. `tg-orchestrate` is the one special case: it is not
one of `STAGES`, so there is no stage to declare and no artifact for `validate` to
gate it on, and it declares neither. **Both halves are enforced**, as two branches
rather than one compound condition: a `stage` key on the orchestrator is a finding,
and so is a `schemas` key, for any value including the empty list. It was written
as `if skill.name != ORCHESTRATOR and stage in STAGES:` wrapping the whole schemas
block, which meant the one skill that must declare no artifact kinds was the one
skill whose declaration of them went unexamined — in the module whose entire job is
examining declarations. The shape is worth naming: a guard that folds two
unrelated conditions into one condition skips more than either one says.

This is §10's silent-drift risk answered on the prompt side. A `SKILL.md` can
name an artifact path that does not exist, a stage that was renamed, or a
subcommand spelled with an underscore, and nothing downstream notices until a
model has already been paid to follow it. A `SKILL.md` that cannot be *parsed*
is exit 2, not a finding: it is human-authored, like the `--agents` roster, so no
repair prompt fixes it. A contract that parses but declares something wrong is
an ordinary exit-1 finding, because it names exactly what to edit.

**Dispatch is by file path, not by harness skill discovery.** A dispatch names
`src/testgen/skills/tg-<stage>/SKILL.md` outright rather than asking the agentic
harness to resolve a skill by name. Three reasons, the last load-bearing: the
skills live as package data inside the Python package, not in a harness's skills
directory, so there is nothing there to discover; `check-skills` reads that same
tree, so the file CI checks is the file that gets dispatched; and
`manifest.stages[].skill_sha256` hashes the file at that path, which only means
something if the run and the hash refer to the same bytes. A name resolved to
whichever copy happens to be installed cannot be pinned that way, and the
reproducibility criterion is exactly the claim that pinning supports.

Dedupe folds into stage 3 rather than standing alone: recognizing that "find the
oldest failing job on prod0" and "which prod0 job failed longest ago" are the
same test needs judgment, but the *candidate pairs* are cheap to compute
deterministically (same `goal_id`, overlapping `capability_refs`). So
`bin/dedupe-candidates` proposes pairs and `tg-score` — which already holds every
scenario in context — marks `duplicate_of`.

### Uniform five-section skill shape

1. **Inputs** — the exact artifact paths it reads, and that it must read nothing
   else.
2. **Output** — the single path it writes, plus its schema path.
3. **Method** — the judgment. The only section that differs meaningfully between
   skills.
4. **Invariants** — what must hold beyond the schema, stated so the skill
   self-checks before writing.
5. **Refusal conditions** — when to record a gap or halt instead of guessing.

**Section 5 is the most important prompt-level decision in the system.** The
characteristic failure of a multi-stage prompt pipeline is not bad reasoning, it
is confabulation under under-specification: handed a world model with a hole
where error semantics should be, `tg-propose` will invent error semantics and
every downstream stage will treat them as fact. Each skill needs explicit license
to fail loudly — write `blocked_by_gap`, not a plausible fabrication. Skills
default to helpfulness; this must be written against.

### Fan-out isolation rule

A fan-out subagent reads only its own slice. `tg-instantiate` for scenario S sees
the world model and scenario S — not the other scenarios, not their seeds. This
is what actually buys the cross-contamination protection that subagents were
chosen for, and `check-refs` enforces part of it mechanically (a `seed_pointer`
may only resolve within its own scenario's seed).

One caveat the fan-out stages taught, because it changes what the rule can mean:
`02-scenarios.json` physically contains every sibling scenario, so for
`tg-instantiate` the file boundary cannot do the work and the rule has to be about
what a member *uses*, not what it saw. The narrow rule is enforceable only where
each slice has its own file.

**Before withholding an artifact from a skill, ask whether a deterministic gate
already enforces the property that withholding it was meant to protect.** This
build wrote five skills' contracts twice over that question, and the test settles
it cleanly in both directions — five reads declared, two deliberately left out. `tg-score` and `tg-propose` both had prose citing
`manifest.limits.max_rounds` while `manifest` was absent from `reads`; nothing
else supplies that number, so the honest fix was to declare the read.
`tg-challenge` had a refusal condition about a seed violating a world-model
invariant while `world_model` was absent; there `check-refs` already evaluates
every entity's `machine:` invariant over the seed, so widening `reads` bought no
coverage and only added anchoring surface to the one stage whose entire value is
*not* being anchored — the requirement belongs to the gate, and the prose says so.
The same test produced "declare" three more times — `tg-emit` needs a status and a
verdict value, `tg-orchestrate` needs the verdict value, and no gate surfaces any
of them in time to act on — and "do not declare" one further time, for
`tg-orchestrate` and the smoke report, which `smoke` itself already turns into a
finding the caller cannot miss. A contract that withholds a path its own prose
depends on is worse than a wide one: the contract block is the only place a path is
named, so the prose has nothing to be held to.

### Orchestrator loop

```
bin/intake
fan-out tg-extract per artifact        → validate each
tg-reconcile                           → validate → check-refs
if any gap blocks a downstream stage   → HALT, report, request the missing artifact
loop (round = 1..K):                       # K configurable; K=2 in the first slice
    fan-out tg-propose per hole cluster                 → validate
    bin/dedupe-candidates → tg-score                    → validate
    on latest.json.verdict: continue → round++ | converged|halted_* → break
    append decision to decisions.md
fan-out tg-instantiate per active scenario  → validate → check-refs   ← reachability gate
fan-out tg-challenge per instantiated one   → validate
    re-seed → re-dispatch tg-instantiate ONCE, adversary's alternatives appended
    reject  → mark rejected in 02, recompute coverage
bin/emit → 06-suite/ ; bin/smoke → 07-report.json
```

**Halting on a blocking gap is the payoff for first-class gaps.** The pipeline
stops and asks for the missing spec rather than inventing one. If this never
fires on a real run, gap detection is not working.

**Rejections reopen coverage, and we let them.** When `tg-challenge` rejects a
scenario as ambiguous, the cell it claimed is uncovered again. The tempting move
is to loop back to `tg-propose`; instead we recompute and report an honest hole.
Looping after instantiation makes run cost unbounded and the experiment much
harder to read, and a report reading "87%, 3 cells lost to rejected scenarios" is
more informative than a 100% that hides how it got there. Deferred, not
forgotten.

### Human gates

Three, placed where review is cheapest relative to what it saves:

- **After 1b** — confirm the world model, resolve contradictions, rule on gaps.
  Highest leverage in the pipeline: every downstream stage inherits these errors,
  and it is the one artifact small enough to read carefully.
- **After the loop** — review the scenario list and coverage report *before*
  paying for per-scenario fan-out. This is the cost gate.
- **After 05** — skim rejects and re-seeds. Mostly informational.

All three are skippable via `--no-gate`. The reproducibility criterion is
impossible otherwise: five identical pipelines cannot be run if a human
intervenes in each.

Per-stage model and effort are recorded in the manifest. `tg-reconcile`
(contradiction resolution) and `tg-challenge` (adversarial search) are the
genuinely hard reasoning; `tg-extract` is mostly careful reading. No tuning
beyond recording in v1 — a model effect cannot be distinguished from a prompt
effect until the pipeline is stable.

## 6. Instantiate and challenge

These two stages determine whether the suite is worth running. Everything before
them is bookkeeping by comparison.

### tg-instantiate — order of operations is the method

Given the world model and one scenario carrying its `discriminating_fact`:

1. **Restate the discriminating fact as a decision problem.** What must the agent
   determine that it could plausibly get wrong?
2. **Design the distractor set.** The step a naive generator skips, and skipping
   it is how an all-pass suite happens. A world containing exactly one failing job
   makes "find the failing job" passable by any agent that calls the API once and
   reads back the only row. The seed needs near-misses: a job that failed on a
   *different* controller, one that failed *outside* the window, one with a
   superficially similar error message. **The distractor set — not `hop_depth` —
   is what actually sets difficulty.**
3. **Seed the world, respecting the world model's invariants.** This matters more
   than it sounds. The aap2 simulation skill already declares that `event_count`
   equals the number of matching `JobEvent` records, that `log` is the
   newline-join of `stdout` ordered by `counter`, and that `duration_seconds` is
   `finished − started`. A seed violating those is not merely unrealistic — the
   simulation *recomputes* those fields, so authored log content silently changes
   and the gold label is now wrong about a world that no longer exists. This is
   the invariant class the `machine:` expression form exists to check.
4. **Derive the reference answer from the seed.** Read the answer out of the world
   just built. Never write the answer first and hope the world agrees.
5. **Write assertions with `grounded_in` pointers**, negatives included.
6. **Record the rationale** — which distractors exist and why — so a reviewer can
   judge fairness without reverse-engineering the seed.

### tg-challenge — the independence is structural

The adversary's input slice is `seed.json` plus `user_intent`, and **deliberately
not `expected.json`**. It proceeds in this order:

1. Answer the question independently from the seed. Record the answer and the
   minimum number of tool calls actually needed.
2. Search for a *second* world-consistent answer — is the question ambiguous
   given this world?
3. Check derivability: can this be answered from the available capabilities at
   all, or does it require knowledge the world does not contain?
4. **Only then** read `expected.json` and compare.

The ordering is the whole point. An adversary that sees the oracle first anchors
on it and confirms almost anything. Pre-registration cannot be obtained from a
skill whose context already holds the answer — which is the concrete reason
challenge is a separate subagent with a restricted input slice rather than a
section appended to instantiate.

**How the built skill carries an ordering no artifact can record.** `expected` is
declared in `tg-challenge`'s `reads`, because step 4 has to open it; "deliberately
not `expected.json`" is a statement about *when*, and a verdict written by an
adversary that peeked is byte-identical to one written by an adversary that did
not. So the skill makes the order readable: the four judgments of steps 1–3 are
**pre-registered into `notes`** before step 4 runs, and step 4 may only *append*
to them. That is the best answer a text-level stage can give to an unobservable
property, and it is what made the live exercise decidable — the filed notes showed
a first candidate considered and eliminated *with its reason*, which an adversary
that had already read the oracle would have had no reason to write. The
elimination is the derivation.

| Adversary result | Verdict |
|---|---|
| Matches expected, unique, derivable | `accept` |
| Found a second consistent answer | `re-seed` (add distractors / tighten intent), once |
| Not derivable from available capabilities | `reject` — the test is unfair |
| Disagrees with expected, and is right | `reject` or `re-seed` |
| `minimum_tool_calls_found` < claimed `hop_depth` | `accept`, flagged `difficulty_overstated` |

Row 4 is the highest-value catch in the pipeline: it is how a wrong gold label is
found before it becomes a benchmark that punishes correct agents. Row 5 is how
the hop-depth distribution gets audited by something other than the stage that
claimed it.

**Known limitation:** the adversary is the same model family as the labeler, so
correlated blind spots survive. Expert review is the only real defense, which is
why §7 samples preferentially from high-confidence `accept` verdicts.

## 7. Emit and measurement

### Emit is code, as a requirement

`bin/emit` reads accepted instances plus the world model and writes
`06-suite/<sid>/` as a Harbor package. It is the **only** Harbor-aware component;
everything upstream is platform-neutral, so retargeting another evaluation
platform means a second emitter, not a re-run. (That boundary discipline is taken
from `task-extractor` as an idea, not as code.)

It must be code rather than a skill because of the reproducibility criterion: if
emit is a prompt, two runs with identical stage-4 and stage-5 artifacts can still
produce different suites, and variance can no longer be attributed to a stage.
A thin `tg-emit` skill exists purely as the human-facing entry point.

**One generic `verify.py`, never a generated one.** A per-task generated verifier
is untrustworthy code sitting directly in the scoring path — the one place a bug
silently inflates every score. Instead a single hand-written verifier consumes
`expected.json`. This forces a constraint that is load-bearing: **the assertion
vocabulary is closed** — `answer_contains`, `answer_excludes`, `tool_called`,
`tool_not_called`, `value_equals`. A skill cannot invent a new assertion kind;
adding one is a human change to the verifier. Otherwise skills emit assertions
nothing can evaluate, and the schema does not catch it because the *shape* is
fine.

### An exclusion satisfied by absence scores a point, so a refusal is not a zero

`verify.score_assertions` takes one denominator over every assertion and awards a
point for an `answer_excludes` whose target is absent from the answer, rather than
merely withholding a penalty. That is the right shape and was chosen
deliberately: it makes a fabrication trap a positively-scored item, and it is what
lets a pure-absence scenario consist entirely of exclusions and score at all. But
it has a consequence this build **measured** rather than predicted:
**an absence-shaped scenario built only of exclusions is substantially passable by
a refusal** — which removes exactly the weak-baseline signal §7 depends on, for
precisely the `log-does-not-say` class of test that motivated absence scenarios in
the first place.

The numbers, from the golden fixture's four tasks scored by the real verifier. The
weak baseline — no tools, answering "I don't have enough information" — scores
**0.4 on each of the two absence-shaped tasks and 0.0 on the other two, for an
overall mean of 0.2** against `WEAK_BASELINE_CEILING` of **0.30**. The 0.4 is
`0.5 × 0.8 + 0.0 × 0.2`: half the assertions satisfied at the assertion weight,
nothing at all on the trajectory. So the suite's verdict is `healthy` and nothing
failed — and two of its four tasks were carrying a refusal to within 0.1 of the
threshold that would have condemned the whole suite as trivial.

`tg-instantiate` therefore carries the invariant that closes it: **an
absence-shaped scenario must carry at least one assertion a refusal cannot
satisfy** — a `tool_called`, or a positive `answer_contains` on something the seed
does contain. The golden fixture pins the invariant at the fixture level, and pins
the four per-task weak-baseline numbers *separately*, because an edit that dropped
the `tool_called` from an absence scenario would move only the aggregate mean — a
number no reader can attribute to a cause.

### Measurement harness

`bin/smoke` runs the suite against three agents:

- a **weak baseline** (no tools, or one-call-only) — should fail nearly
  everything. If it passes much, the tests are trivial.
- the **real agent** under test — the spread that matters.
- an **oracle agent handed the reference answer** — should pass nearly
  everything. **If it does not, the gold labels or the verifier are broken, not
  the agent.**

That third run is a test of the test suite, and it is cheap. Combined with
per-task all-pass / all-fail flags it gives degenerate-suite detection rather
than a single average that hides everything.

`bin/compare-gold` handles recall and novelty against the ~10 authored aap2 bench
tasks — matching on `capability_refs` + goal overlap, human-confirmed, with
novelty categorized as *new outcome class / new capability / new hop-depth /
spurious*. The report must state inline that with a denominator of 10, 7/10 vs.
8/10 is noise; recall is a smoke signal, not a metric to optimize.

`bin/diff-runs` reports a per-stage stability number across N identical ungated
runs — Jaccard on capability sets after 1b, on goal×cell claims after 2, on final
task ids after 6.

`bin/sample-for-review` emits a stratified review packet (instruction, seed
digest, expected, rationale, adversary notes) with a fixed rubric — fair /
unambiguous / correctly labeled / non-trivial — appended to the run so review
becomes a trend line. Sample preferentially from high-confidence `accept`
verdicts: that is precisely where a correlated labeler/adversary blind spot
hides.

**Decisions this build made, for the next reader who needs to know why a
number is what it is:**

- The thresholds are named constants, not magic numbers scattered through the
  code: `WEAK_BASELINE_CEILING` (0.30), `ORACLE_FLOOR` (0.80), and
  `PASS_THRESHOLD` / `FAIL_CEILING` (0.999 / 0.001) for the per-task all-pass /
  all-fail flags. `broken_labels` (oracle mean below its floor) outranks
  `degenerate_trivial` (weak-baseline mean above its ceiling) when both trip:
  a suite whose oracle cannot pass its own reference answer is not
  trustworthy evidence about whether the suite is trivial either.
- Every mean is taken over **comparable** tasks only — a task where every
  declared role actually produced a score — never over however many rows
  happened to land. A task with one timed-out role would otherwise silently
  drop out of that role's mean while still counting in the others', turning a
  ragged denominator into a false signal. `unscoreable` is its own bucket,
  neither `all_pass` nor `all_fail`: a task no role could score is not
  evidence the suite is easy or hard.
- `smoke` scores an agent by executing the package's own copied `verify.py`
  under `python -S` with a scrubbed environment, not by re-implementing
  scoring logic against the transcript. This is the stdlib-only constraint
  enforced by actually running it, rather than declared and hoped for.
- A transcript's non-string `result` scores as **no answer** — never coerced
  with `str()` — and the reason is recorded in `reward-detail.json`. Silently
  stringifying a malformed result would let a broken agent's structured
  garbage pass an `answer_contains` check by accident.
- `compare-gold` proposes matches, it does not declare them: a gold task and a
  generated task must share a goal identity and clear a cell-overlap floor
  before either is even eligible, matches are assigned one-to-one, and the
  result is handed to a human to confirm, not treated as ground truth.
- `diff-runs` reports every per-stage number even when the two runs are
  incomparable — comparability is a precondition on trusting the *headline*
  verdict, not on computing it, because a reader deciding whether the
  incomparability itself matters needs the numbers to decide with. Every
  Jaccard is reported alongside both set sizes and the actual difference, not
  as a bare fraction: 1.0 on two empty sets and 1.0 on two 40-element sets are
  not the same claim.
- `sample-for-review` picks its sample deterministically from `hashlib.sha256`
  of the scenario id, never the builtin `hash()` — which is salted per
  process and would make the same run sample differently on every
  invocation — and the packet carries the seed's digest rather than the seed
  itself, so a reviewer can confirm which world a label was authored against
  without the simulated backend burying the four questions that matter.

## 8. First slice

- **aap2 only**, one simulation skill.
- Inputs deliberately small: the aap2 `api.json` + `schema.json` + a handful of
  traces. **Not** the source tree — three artifacts still exercise fan-out,
  reconciliation, and contradiction detection at a fraction of the cost.
- **All stages present.** `K=2` loop rounds, cap ~8 scenarios.
- All three code gates real: `validate`, `check-refs`, `smoke`.
- Measurement: `smoke` (with oracle + weak baseline) and `compare-gold`.

**Status: every component this slice names now exists.** The contract spine, the
measurement layer, and all eight skills are built; `testgen check-skills` exits 0
against a complete roster; and the pipeline has run end to end with a model at
every stage — halting on a blocking gap, taking a real human gate-1 ruling,
resuming, and producing a suite whose scored spread was `healthy` with **no task
passed by every role and none failed by every role**, which is the property a
generated suite exists to have and the first one a degenerate suite loses.
What it has *not* run on is aap2 — that end-to-end run was on §9's
two-capability toy world, which is a test of the pipeline and not of the
hypothesis. **The aap2 run is Plan 5**, and it is what §11 now points at.

**Why not smaller.** The tempting cut is to drop `tg-challenge` and the
reachability gate as polish for later. But a slice without them does not test the
hypothesis — it tests whether an LLM can produce plausible-looking test files,
which is already known. **The gates are the experiment.**

### Deferred to later slices

| Deferred | Reason |
|---|---|
| `bin/diff-runs` execution | Needs 5× run cost; build the tool, run it in slice 2. |
| `bin/sample-for-review` execution | Needs human time; build the tool, run it in slice 2. |
| Source-code ingestion | Largest artifact class; adds cost without testing anything new in slice 1. |
| Live-backend binding | Requires a second binder for stages 4–5. |
| Difficulty calibration | Decide after seeing a real spread from stage 7. |
| Post-rejection re-looping | Makes run cost unbounded; report honest holes instead. |
| Multi-target | One target is enough to test the hypothesis. |
| Declarative pipeline manifest | Where this design likely converges after 2–3 iterations; wrong place to start. |

### Carried forward from the contract-spine build

Surfaced by the whole-branch review after the contract spine shipped, and
deliberately deferred rather than folded into a fix wave. **These are layer-2
gaps in a contract that later stages are meant to be constrained by, so they
belong at the front of the next plan, not the back.**

**Status: fully closed as of the measurement build.** The tenth and last item,
*re-verify input digests*, is closed by `refs.check_inputs`, which re-hashes
`00-inputs/`'s bytes against the digest `manifest.json` recorded for them — the
hole this list existed to name. `manifest.stored_as` closes the related naming
gap alongside it: each input entry now carries the filename it was registered
under, so a reader (or `check_inputs` itself) does not have to re-derive
intake's slugging rule to know which file a digest belongs to. The ten are
kept below, now a historical record rather than a to-do, of what was owed and
why.

| Carried forward | Why it matters |
|---|---|
| A referential check for the manifest | Layer 2 never reads `manifest.json`, so the chain `manifest.inputs[].artifact_id` → `01-claims/<aid>.json` filename → that file's own `artifact_id` → `claims[].evidence[].artifact_id` is entirely unchecked. `_claim_ids` also unions ids into a set, so two claims files defining the same claim id merge silently — a real reconciliation hazard that reads as clean. |
| Enforce `manifest.limits` | `max_rounds` and `max_scenarios` are written by intake and read by nothing. A scenarios document with `round: 99` under `max_rounds: 2`, or 400 scenarios under a cap of 8, passes both layers. |
| Compare `discriminating_fact` between scenario and oracle | §4 makes this field the mechanism that stops the instantiate stage inventing an easier world than the one proposed. Nothing compares the two strings, so the field is currently decorative. |
| Constrain `trajectory.operations[].capability_id` to the scenario's own `capability_refs` | Operations are checked against the world model but not against what the scenario claimed, so an instance can exercise capabilities the scenario never declared while coverage credits it. Coverage becomes confidently wrong with no finding. |
| Relate `coverage.holes` to the matrices | Hole refs are checked for existence, but a coverage report can declare zero holes while cells are `covered: false`. The "every uncovered cell is justified" discipline that makes the hole vocabulary worth having is unenforced. |
| Bring `goal_matrix` up to `capability_matrix`'s rigour | `hop_depths_expected` is never compared to `goals[].expected_hop_depths`, `hop_depths_present` is never derived from the scenarios, and the covered-with-no-scenarios check has no goal-row counterpart. |
| Switch the schemas' `id` anchors from `^…$` to `\A…\Z` | Python's `re` lets `$` match before a trailing newline; `paths.safe_segment` uses `\Z` and does not. Not reachable today, but it goes live the moment `emit` calls `run.task_dir(sid)` with an id read from `02-scenarios.json`. Eight one-word edits. |
| Give `emit` and `smoke` real layer-1 gates | `STAGE_ARTIFACTS` maps both to `()`, so `validate --stage emit` returns exit 0 unconditionally even if emit produced nothing. Fine as a placeholder, wrong as a merged contract: an orchestrator will read 0 as success. |
| Enforce `manifest.created_utc`'s `date-time` format | The validator is built without a `format_checker`, so `"not-a-timestamp"` validates clean. The schema documents a constraint it does not have. |
| Re-verify input digests | Nothing confirms the bytes in `00-inputs/` are the bytes whose hash the manifest records — a hole underneath the reproducibility claim. `diff-runs` is the natural home. |

### Carried forward from the closure-and-emit build

Surfaced by that build's whole-branch review and its fix-wave re-review, and
parked with rulings rather than fixed. **None is reachable through the
deterministic pipeline — every one needs a hand-authored or tampered artifact —
but so did `weights: 5`, which was fixed, so reachability alone is not the test.**

**Five of the nine closed in the measurement build; four stay parked below.**

| Closed this build | Where |
|---|---|
| Cross-check `07-report.json` against `06-suite/` | `refs.check_report`. Distinguishes a scenario absent because `emit` pruned it from one absent because the challenge loop rejected it — the two look identical to a checker that only asks "is it there," and only one of them is a defect. |
| `parse_transcript` on a non-string `result` | Ruled: a non-string `result` scores as no answer, never `str()`-coerced, with the reason recorded in `reward-detail.json`. See §7's Measurement harness for why coercion was rejected. |
| A syntactically invalid `expected.json` in a package | `verify.read_contract` now refuses before `_contract_problems` runs, so a file that cannot even parse hits the same refusal path as one that parses but fails the contract, instead of an uncaught `json.loads` traceback. |
| `emit` prunes on a repairable upstream defect | The docstring was the actual defect, not the behavior: it drew the line at "a missing *input*" while the code correctly also pruned on a truncated oracle. Corrected to describe what the code does. |
| `refs._load` swallows `ArtifactError` | `check_readable` now names the artifact that actually failed to parse and short-circuits `check_all` before it can blame `03-coverage/latest.json` or `04-instances/` for a defect that lives in `02-scenarios.json`. |

| Still parked | Why it matters |
|---|---|
| An unsafe directory name under `06-suite/` | Skipped by `scenario_ids_with_tasks()`, so it is neither pruned nor reported, and would ship. There is no `unsafe_task_dir_names()` counterpart to the one `04-instances/` has. Requires manual tampering. |
| `cli.py`'s `except Exception` blames the artifact | A genuine bug in `testgen` code is reported as "your artifact is malformed; run validate". If `validate` is then clean the orchestrator gets contradictory signals. The traceback on stderr mitigates it. |
| `intake` sits outside the exception net | Its own `try` returns before the outer handler, so an unexpected exception there exits 1 with empty stdout — the mode that net was added to close. Crash surface is small: `slug` cannot emit an unsafe segment and IO raises `OSError`. Re-examined in the measurement build; still holds. |
| Re-verifying digests **across** runs | Partly addressed: `diff-runs`' comparability precondition now refuses to call two runs comparable unless their manifests record identical `input_digests`. What it does not do is re-hash either run's `00-inputs/` bytes itself — it compares the two manifests' *recorded* digests, trusting each at face value. That trust is exactly what `refs.check_inputs` closes, but only within one run; `diff-runs` does not chain to it. Two runs tampered identically, or a run whose `check_inputs` was never run, can still report `comparable: true` on a false premise. |

### Parked from the measurement build

The whole-branch review and its single fix wave surfaced three additional findings, adjudicated as parked rather than fixed because none is load-bearing: the finding line is present and parseable, nothing downstream depends on the specific target artifact, or the defect is isolated to a single subcommand and the measurement pipeline runs without triggering it.

| Parked | Why it matters |
|---|---|
| `cli.py`'s catch-all finding names the wrong run for `diff-runs` | The exception handler builds its finding against `args.run`, falling back to `args.a`. Since `diff-runs` is the only subcommand taking two run directories (`--a` and `--b`), a defect in run **b** surfaces as a malformed artifact in run **a** — which an orchestrator would attempt to repair. The finding line is still present and parseable, which is strictly better than the empty exit 1 it replaced, and nothing downstream reads the artifact field. The fix would require naming both roots or dropping the "this run" phrasing for `diff-runs`. |
| `dedupe-candidates` maps a stage defect to exit 2 | It reads `02-scenarios.json` through a path whose narrow exception catch turns an unparseable file into exit 2 (`misconfigured harness`), while `validate`, `check-refs`, `emit`, `compare-gold` and `sample-for-review` all return exit 1 with a finding for the same file. This violates the module docstring: a repairable stage defect must never surface as a misconfigured harness, because the orchestrator halts instead of spending its one repair attempt. The line is untouched by this branch and represents a single-subcommand inconsistency in a class the branch otherwise closed. |

### Parked from the skills build

Fifteen tasks, their reviews and their fix rounds, plus a live exercise for each
of Tasks 7–13 and the two recorded dispatches of Task 14.
What those closed is written into the sections that own it — §4's two writers and
the two limitations layer 2 and the world model each carry, §5's contract block
and declaration test, §7's absence-scoring ruling, §9's three fixtures. What they
did not close is below, each with the ruling that parked it. The pattern worth
noticing in the first eleven rows: almost none are code defects. They are prompts
that under- or over-state a rule, and mechanical checks that pin a shape instead
of the property the shape was standing in for.

**The rows after those come from the final whole-branch review rather than from a
task**, and they are here because the alternative was losing them. That review
split the 61-commit diff three ways, its eleven merge-blocking findings were
fixed in seven commits, and what follows is what it raised and I then adjudicated
park-don't-fix. They break the pattern above — several of them *are* code
defects, and two are one-directional checks whose missing half no per-task review
was positioned to see, which is the whole argument for reading a branch at once
as well as a task at a time. Two of them do not get rows of their own: the
one-directional field-name gap is the root cause of the `source_field` row below,
and the one-directional structural guard belongs in the negative-fixtures row, so
each is folded into the row it explains.

| Parked | Why it matters |
|---|---|
| `--no-gate` is a prompt-level flag, not a CLI flag | §5's three human gates live in `tg-orchestrate`'s prose, and no code enforces them, so `--no-gate` is an argument to the *skill's invocation*. A prompt-level flag can be forgotten in a way a CLI flag cannot. Accepted as the right cost for this slice: enforcing the gates in code would mean the orchestrator stops being a skill, which is the thing being tested. |
| The orchestrator has no lever for `effort` | It records `model` and `effort` per stage through `record-stage`, and its prose says where both come from — but the dispatch mechanism cannot *supply* an effort level. The one completed run recorded the most neutral characterization available and flagged the assumption rather than presenting it as fact. So every `effort` in a manifest today is a characterization, not a setting, and §4's comparability claim rests on `model` and `skill_sha256` doing the real work. |
| The isolation rule is enforceable on artifacts inside a run and unenforceable on everything else a subagent can reach | Already named as this build's weakest link: an instantiate member that read a sibling's seed produces a byte-identical artifact to one that did not. This build widened the scope twice, both times measured. An extract member self-reported reading both sibling *input files* while checking locator conventions; a reconcile member volunteered that it had consulted a *different fixture* as a reference, outside its declared `reads`. Both outputs were correct and independently verified, so nothing was harmed — and no schema, no `check-refs` and no digest could have detected either. Both surfaced only because a subagent mentioned it in a report nobody obliged it to write. The exposure is therefore not "another scenario's slice" but anything on the filesystem, and the only instrument is a transcript audit at dispatch time. |
| `tg-extract` speculates about the sibling it did not read | Three of five dispatches honoured the file boundary on reads and then volunteered a guess about the unread sibling's contents ("that lives only in `notes.md`", "presumably in the sibling `api.json`"). No file was opened and no claim was filed on any of it, so the rule held where it is enforceable. Parked as prompt hardening rather than dismissed, because a guess about an unread sibling in a *report* is one step from the same guess inside a *claim*, and a confabulated claim is byte-identical to an extracted one. |
| `tg-reconcile`'s corroboration test never says what "independent" excludes | §1 asks whether "a second, independent claim" supports one side, and its only worked example contributes exactly one claim per artifact — so nothing in the text rules out counting two claims from the *same* document as independent corroboration, which would make a self-contradicting document look like two sources. Settled empirically rather than pre-emptively: the prose gap is real, and it did not mislead the model, which reasoned that the two claims "cancel out rather than one confidently corroborating the other" and named the pull it was resisting. Recorded as *sufficient for this model on this input* — weaker evidence than "the prompt says so", and it must not be filed as the latter. The one-line clarification is a hardening, not a fix. |
| `invariants.py` reads a `join` invariant's `source_field` with a default rather than a sentinel | Production code, not a fixture defect. Every other key uses the MISSING sentinel; `source_field` uses `.get(default="")`, so a mistyped one silently compares against a join of empty strings and produces no direct diagnostic — it is caught only by a coincidental string mismatch. Latent today because the golden fixture uses no `join` invariant, and adding one purely to reach this would be YAGNI. **The final review found the root cause, and it is wider than this key: `refs.py` never checks a `machine:` invariant's field names against the entity's declared fields at all.** Its invariant loop iterates exactly `("collection", "of")` and checks those two against the world model's declared collections; `field`, `local_key`, `foreign_key`, `order_by` and `source_field` are checked by nobody. The schema requires all five to be non-empty strings and cannot tie any of them to a declared field name, because a field name is a fact about the entity being referenced. So a typo in any of the five is caught only coincidentally — by an invariant message about a record missing a field, if the seed happens to hold records at all — and for `source_field` specifically by the empty-string default above, which is the one key whose typo produces no message even then. Fixing the sentinel narrows one symptom; the check that would remove the class is the missing one, and it is a checkable check: the entity's `fields[].name` set is right there in the same object. |
| `skills.py`'s contract-block regex backtracks quadratically on unclosed fences | Measured: 6s at 8000 unclosed fences against 0.37s at 2000. Not reachable — `SKILL.md` files are hand-authored and repo-shipped, eight of them at ~200 lines. The narrow fix does not help, because proving "exactly one `toml` block in this section" requires scanning to the end; the real fix is replacing the regex with the fence-aware line walk already in that module, which churns a parsing core two reviews validated. If `SKILL.md` ever becomes user-supplied, that walk is the named replacement. |
| `check_contract`'s message for a non-string *element* of `invokes`/`reads`/`writes` | It reports "invokes `{'tool': 'validate'}`, which is not a testgen subcommand" rather than "must be a string". Deliberately not fixed, and the distinction from the case that *was* fixed is the exit-code contract: a bad `schemas` element used to **crash** into exit 1 with an internal message naming the wrong tool, while these all return a parseable exit-1 finding that renders the offending element, so a reader can see what to edit. Unifying all four keys behind one helper would remove the class and refactor a function three reviews validated, for Minor benefit. |
| Two prompt statements stronger or narrower than the rule they describe | `tg-score`'s survivor rule claims determinism that "pins its world down more tightly" cannot deliver, since that is a judgment; stability across two scorings comes only from the round tiebreak. `tg-instantiate`'s concurrency-scoped self-check sorts a gate finding into *yours* or *a sibling's* and is silent on a third case — a finding against a shared frozen input, which names neither instance directory — so nothing tells the member to forward it. (A third entry, a `tg-challenge` test whose name said "the three boolean judgments" where the schema has two booleans, an integer and an array, was fixed in the final wave: the test now derives the field set from the schema, so the name cannot drift from it again.) |
| Two documentation-accuracy residues inside strengthened tests | `tg-orchestrate`'s exit-code predicate passes on the delivered file partly *because* the same fix round retitled a table cell (`\| **0** \|` → `\| **exit 0** \|`). The property still generalizes — it survives a full prose rewrite and goes red on deletion — but a fix that tightened its source document to satisfy its own new test is a shape that could hide a real circularity in a less careful instance, and the dependency is recorded only in a report. Separately, one strengthened predicate's docstring justifies itself with a hazard that measurement showed never occurs in this document. |
| The negative fixtures' remaining unguarded surfaces | Five, each ruled rather than overlooked. The structural key-path guard keys on positional list indices, so inserting a tool ahead of the existing one would report 18 paths missing when nothing was lost (demonstrated). The gap fixture's `notes.md` goal prose stays unguarded, because no predicate catches its deletion without anchoring on a single incidental word — *and* that prose is byte-identical across all three fixtures including the golden one, so it is not a negative-fixture property at all; declining to write a test that would give false confidence was the right call. Several contradiction-fixture predicates key off exact substrings rather than the semantic property. The live test that iterated `capabilities`, and so would have passed vacuously on a re-recording with zero of them, is fixed rather than parked: it pins the count against the number of actions the fixture's own `api.json` declares, requires each capability to enumerate at least one outcome class, and checks the total against the recording's own `denominator.capability_cells`. What stays open is the schema: `capabilities` still has no `minItems`, so a world model with none is valid, and the guard is the test rather than the gate. **The fifth is the final review's, and it is the same one-directional shape as the seed-conformance row above: the structural guard asserts `_key_paths(golden) - _key_paths(fixture)` and so says nothing about structure the fixture *added*.** The value guard written in the same fix wave does not cover the gap either, because it reads exactly one path — `tools[0].returns.get_ticket`. So appending a *second* tool to `toy-contradiction/api.json` whose `returns` describes error behaviour reconstructs the two-independent-artifacts corroboration that `tg-reconcile`'s §1 names as what makes `preferred_a` defensible — the precise property this fixture exists to deny, and the one its recorded `unresolved` rationale cites api.json's silence about an unknown id in support of. Demonstrated: with such a tool appended, all 1126 tests pass. Left open rather than guarded because the honest fix is the direction, not another path: assert the key-path sets *equal* and let a legitimate fixture edit be the thing that has to justify itself. |
| Seed conformance is one-directional, so a seed may drop or empty a declared collection and no layer objects | `refs._check_seed_conformance` checks seed→world — `set(collections) - set(entities)`, "seed declares a collection no world-model entity declares" — and no check anywhere runs world→seed: nothing asks whether every entity the world model declares has a collection in the seed, or whether that collection holds a record. Measured on the toy run: dropping `tickets` from `scn-empty`'s seed, and keeping both of its collections present but empty, each leave `validate --stage instantiate` **and** `check-refs` at exit 0 with zero findings. The cases that *are* caught are caught by accident, which is the part worth knowing: dropping `comments` trips `inv-comment-count`, an invariant that happens to count related records, and emptying `scn-open`'s seed trips *reachability*, because its `value_equals` grounds in a pointer that has to resolve. Neither accident is available for an absence-shaped scenario — `scn-empty` and `scn-missing` ground `answer_excludes` at a pointer that must resolve to *nothing*, so an emptied seed satisfies it — and those are exactly the scenarios where an under-built world is most plausible. Layer 1 catches only the degenerate `{"collections": {}}`, via the seed schema's `minProperties: 1`. `invariants._records` returns `[]` for an absent collection with a docstring saying an absent collection is "refs.py's finding to report, [and] duplicating it here would double-count one defect", and refs.py never reports it — so that docstring is false whichever way this is settled, and it is the reason the gap survived: each half was written believing the other half held it. **This one needs a design ruling before anyone fixes it.** `tg-instantiate` states only the one-directional rule — "every collection must be one some entity declares" — so a *partial* seed may well be intended, and a scenario about one entity has no obvious duty to populate every other. What is indefensible under any reading of that rule is "every declared collection present and empty": a seed that satisfies the letter of conformance while containing no world at all. So the follow-up is real; what it is not is obvious, and guessing the rule in code would be the wrong order. |
| Golden `scn-empty`'s `answer_excludes` marks a correct answer wrong | Measured through the real scorer on the emitted package: the oracle's own `answer_reference` scores `reward` 1.0, and that same answer plus "Its only ticket, 4103 (Label printer offline in DC2), is open" — correct, and strictly more informative — fails the exclusion, scoring assertions 0.5 and `reward` 0.6. Nothing mechanical will ever raise it: the exclusion is grounded at `/collections/tickets/2`, which resolves to nothing, so layer 2 is right to be silent, and §7's absence-scoring ruling is untouched by this. It matters because of what this fixture *is* — the golden run is the model answer a skill imitates and the worked shape a reader calibrates from, so a label that punishes the better answer teaches that as the pattern. Parked rather than fixed because the numbers this assertion feeds are pinned in three separate places in `tests/unit/test_toy_end_to_end.py`: the exact `mean_reward_by_role` dict, the per-task `weak_baseline` values for both absence-shaped tasks, and a third test's docstring reasoning from the absence-shaped spread `(0.4 / 1.0 / 1.0)` to why a seed swap between `scn-empty` and `scn-missing` moves nothing. Deleting the assertion turns the first two red (measured), and re-deriving all three belongs with a deliberate re-record rather than a merge-eve edit. `tests/toy.py` carries the same admission in a comment above the oracles; this row exists so the finding does not depend on someone reading that comment. |
| `skills.load()` ignores a second `## Contract` section | The function is deliberately strict about the fence: it counts `toml` blocks *within* the Contract section and refuses anything but exactly one, precisely so a toml-fenced example earlier in the prose cannot be mistaken for the declaration. But `_section_text` returns on the first heading that matches, so a file with two `## Contract` sections is parsed from the first and the second is never looked at — the one-block rule is enforced inside a window that stops before the impostor. Demonstrated: a whole second Contract block appended to `tg-emit/SKILL.md` declaring `stage = "bogus-stage"` and `reads = ["not_a_thing"]` gives `check-skills` exit 0, neither name reaching `check_contract`. The hazard is not the tampering case, it is the ordinary one: an author who edits the wrong block, sees a green `check-skills`, and reads that 0 as validation of the edit they just made — the declaration-drifts-from-the-code failure this module exists to prevent, arriving with the module's own blessing. Parked because the narrow fix (refuse a duplicate heading) is a change to a parsing core two reviews validated, and because `SKILL.md` files are hand-authored and repo-shipped; the fix belongs with the fence-aware line walk already named as `_TOML_BLOCK`'s replacement in the row above. |
| `tg-emit`'s `reads` is over-broad by the skill's own stated criterion | Its §1 justifies the report pair — `scenarios` and `verdict` — with a rule stated as general: they are there "because a requirement of this skill needs them, which is the only reason anything is ever in a `reads` list". By that criterion `world_model` and `expected` do not belong. `testgen emit` consumes them to compile a package; no requirement of *this skill* opens either. Method steps 1–4 read emit's stdout, `02-scenarios.json` and `05-verdicts/`, and Invariant 5's own enumeration of where every reported fact comes from names those three and not these two. The cost is not tidiness. `reads` is what a dispatched model is told it may open, and a declaration it cannot tie to any step of its own Method invites the plausible reading — open every oracle "to understand the compilation" — which is one step from reviewing the suite instead of reporting it, the exact move Invariant 5 forbids by name. Parked rather than narrowed because the two names are also the truthful answer to a different question the document asks and answers well ("what will a finding about a package name?"), so the fix is a wording decision about what `reads` means for a stage that only reports — and `check-skills` holds `reads` to the artifact vocabulary, not to the skill's Method, so no gate is affected either way. |
| `README.md` states the dispatch rule absolutely, omitting `tg-orchestrate` A1's two exceptions | Verified against the README as it now stands: "Every dispatch carries exactly three things — the run directory, the stage name, and the path to that stage's `SKILL.md` — plus, for the three fan-out stages, the id of its own slice… Nothing else: no summary of what an earlier stage concluded, no excerpt of the world model." A1 says the same thing and then names two exceptions, both repairs rather than fresh work: the bounded repair of A4 appends the gate's findings verbatim, and a re-dispatch appends verdict fields quoted from the file that holds them — `alternative_answers` and its `notes` on a `re-seed`, the rejected scenario ids and the judgments behind them on a post-rejection `tg-score`. What makes the omission more than a summary's licence is that the README's own preceding sentence already says the orchestrator "spends at most one repair attempt per failure": a reader calibrating from that page has the repair mechanism and an absolute prohibition two sentences apart with nothing to reconcile them, and would read A4's bounded repair as a contract violation. Parked, not dismissed: the README is a summary and A1 is the contract, so the wrong document winning here costs nothing mechanical. What it costs is a reader's trust in whichever one they read second, and this project's whole method is that the prose is the artifact. |
| Two content-derived failures exit 2 rather than 1, under the `OSError` catch the final wave widened | Both measured. A stage that wrote a *directory* where `04-instances/<sid>/seed.json` belongs: `validate --stage instantiate` and `check-refs` both exit 2 with `[Errno 21] Is a directory` on stderr and an empty stdout, where an absent or unparseable `seed.json` at the same path is an exit-1 layer-1 finding naming the file. An over-long `stored_as` in the manifest: layer 1 does report it, `validate --stage intake` exiting 1 on the schema's `maxLength` at `/inputs/0/stored_as`, while `check-refs` exits 2 with `ENAMETOOLONG` — where a `stored_as` naming a merely absent file is an exit-1 `refs` finding at that same pointer. So the class the widening was aimed at (the filesystem refusing, which no repair can fix) has swept in two cases where a stage wrote the content that fails. The widening was still right, and for the directory case exit 2 is arguably *correct* under the contract's own definition: `write_json` cannot overwrite a directory, so a re-dispatch of that stage genuinely cannot clear it, and exit 2's meaning is "repeating the stage cannot help" rather than "the content is fine". The over-long name is the weaker case, since layer 1 shows a repairable finding exists. Parked because deciding it means deciding whether the 1-vs-2 line is drawn on *what failed* or on *what a repair could do*, and those two readings disagree here rather than one being an oversight. **No test pins this boundary either way, which is the part that should not survive another build:** whichever reading wins, the states belong in `tests/unit/test_refs_states.py` as process change 3 prescribes. |
| None of the three reconciled stage-handoff statements is pinned by a test, and neither are the two transcribed `## Run record` sections | Measured by deletion, one at a time, restoring between: remove `tg-score`'s §2 rejection-notice exception together with its Method step 3 rejection-notice block; remove `tg-instantiate`'s entire `re-seed` notice section; remove `tg-score`'s Method step 1 paragraph on what `dedupe-candidates` does *not* exclude along with the matching passage in `dedupe.py`'s docstring. Each deletion leaves 1126 tests passing. So all three fixes can regress silently, and each of the three failure modes the fix wave named — a silently-green coverage report after a rejection, a re-seed notice read as out-of-contract text, a deliberately non-folded pair folded on its re-raise — is reachable again by an edit no gate objects to. Accepted rather than fixed, and the reason is a measurement this build already owns: pinning prompt prose produces the *substring-of-message* weakness of process change 4, and the fix wave immediately before this ruling had to repair six prompt and refusal predicates that each passed with the rule they name deleted. A predicate written under merge-eve time pressure would most likely be the seventh, and a test that gives false confidence about a handoff is worse than a recorded gap about one, because it retires the question. The same reasoning covers the two `## Run record` sections transcribed into `tg-propose/exercise.md` and `tg-reconcile/exercise.md`: no test reads any `exercise.md` at all, including `tg-reconcile/exercise.md`'s own written requirement that a negative result "belongs in this file… rather than only in a review ledger elsewhere" — the requirement whose breach the final review caught, now met and unguarded. |
| A symlink loop in an artifact position is silently skipped | `paths.list_json` filters on `is_file()`, which swallows `ELOOP` and answers False rather than raising, so a self-referential `01-claims/loop.json → loop.json` is not a claims artifact, not a finding, and not an error: `validate --stage extract` and `check-refs` both exit 0 over it (measured). Arguably the right tolerance — a loop is neither a claims file nor evidence that the ones present are wrong, and this is the same "skip what is not a file" rule that keeps a stray subdirectory from being read as JSON. What makes it worth a row is that it is the one listing shape `list_json` does not surface. Its whole reason for replacing `glob("*.json")` was that a listing failure must be visible: `list_dir` converts `EACCES` and friends into a `UsageError` naming the directory, so the run stops with the harness blamed rather than an artifact. `ELOOP` on a member of the listing is the one that gets through, and it gets through inside the guard added to close exactly that class. |
| `manifest_stage_efforts`' test docstring claims more than its body | `test_the_effort_choices_are_read_from_the_schema` opens "Not a second copy of the enum" and then asserts `manifest_stage_efforts() == ("low", "medium", "high", "xhigh", "max")` — a literal copy of the enum, in a test file, which is the thing the docstring says this is not. Harmless in effect, because the property it names is genuinely covered elsewhere: `test_manifest_stage_efforts_tracks_a_schema_override` in `tests/unit/test_validate.py` points `TESTGEN_SCHEMA_DIR` at a rewritten manifest schema and asserts the tuple follows it to `("low", "ludicrous")`, and that test's own docstring says it exists to keep the "no second copy" claim from being false in exactly the case a candidate schema is being tried. Recorded because the pair is a small instance of the shape this build kept finding at full size — the *name and the docstring* asserting a property that lives in a different test than the reader is looking at — and a reader who checks only the first one concludes the value pin is the guard. |
| `test_live_marker.py` writes into the tracked tree | Its subprocess helper writes `tests/test_generated_<tmp_name>.py` into the repository's own `tests/` directory, on purpose and for a good reason (the property under test is default *collection* behaviour with `tests/conftest.py` in scope, which an in-process run would not reproduce). The ordinary path is clean: `finally: target.unlink(missing_ok=True)`. Two things are not covered, and no `.gitignore` pattern matches the name. A hard-killed run — the pytest process killed rather than failing — leaves a file in the tracked tree that looks committable and is named as though a tool generated it deliberately, which is precisely the shape a `git add -A` sweeps up. And the write makes the suite unrunnable from a read-only checkout, where every other test in this project is a pure function of its inputs and a `tmp_path` — the path is also relative (`Path("tests") / …`), so it is a fact about the working directory rather than about the repository. Parked as the smallest of these findings, and half of it is one line: a `tests/test_generated_*.py` entry in `.gitignore` closes the looks-committable half outright. The other half is not a relocation, which is why it is parked rather than done — the default skip lives in `tests/conftest.py` and applies to what is collected beneath it, so a file written into `tmp_path` is a file the hook under test never sees, and moving the write means finding a different way to put the repo's `conftest.py` in scope. |

### Process changes for the next plan

The first two come from the contract-spine build; the third is what the
closure-and-emit build added, and it was the one that caught the most. All
three held through the measurement build's twelve tasks and are kept
unchanged below.

1. **Enumerate the pipeline states and require `check_all` to be clean in each.**
   Tolerance was asserted in prose and tested for two states, which is how a
   check that fired spuriously in normal operation shipped — with a test
   asserting the wrong behaviour as correct. This is now
   `tests/unit/test_refs_states.py`; extend it whenever a stage is added.
2. **Index the plan's self-review by artifact × layer, not by spec element ×
   task.** Both structural gaps above are invisible in a table keyed on "which
   task implements this requirement" and obvious in one keyed on "which layer
   checks this artifact."
3. **Require deletion-mutation evidence for every check, and name the state each
   check must stay silent in.** The first half was added mid-build after three
   consecutive tasks shipped a test whose *name* claimed a check its *values*
   never reached, and it then caught nearly every remaining defect — a check is
   not tested until deleting it makes a named test fail. But it is a
   per-*check* counter, and every defect the whole-branch review found was
   per-*seam*: two checks that each mutate correctly and jointly disagree, a
   constant duplicated into a schema, a gate whose complement is unguarded.
   Deletion-mutation cannot see any of those. The dual is the fix: for every new
   check, name the pipeline state in which it must stay silent and add that
   state to `tests/unit/test_refs_states.py`. That file was under-populated by
   four reachable states, one of which *was* the Critical. (A tooling note that
   belongs with this one because it silently corrupts the evidence: a
   byte-length-preserving mutate-then-restore within the same second leaves
   CPython's mutated `.pyc` live, since `.pyc` validation checks source size and
   mtime-to-the-second only. Every mutation harness here must set
   `PYTHONDONTWRITEBYTECODE=1` or sweep `__pycache__` between mutate and
   restore. A second hazard of the same standing, from the skills build:
   **restore with `cp` from a copy taken before the mutation, never with
   `git checkout --`** — during a fix round the working tree always holds
   uncommitted work, and `git checkout` reverts to the last *committed* state,
   silently discarding the fix the mutation was verifying. It happened once and
   was caught by luck.)

A narrower lesson, confirmed for a third time and now emphatically: **when a
plan supplies both the code and its tests, the tests cannot be trusted to
bound the code**, because both came from the same understanding. In the
contract-spine build three defects were plan-mandated test text exercising
only the path on which the plan-mandated code was correct; in the
closure-and-emit build four of the seven tasks that needed a fix round needed
it for a plan defect, not an implementation defect; the measurement build's
ledger (`progress.md`) records fourteen more such instances across its twelve
tasks — the fifth through eighteenth in a numbering that runs across all
three builds, not eighteen of its own. Having each task's reviewer name one
input class the plan's tests do not reach remains a cheap counter — item 4
below is what it grew into once there were enough instances to see the shapes
repeating.

The measurement build adds five more, each drawn from that ledger:

4. **Three test-weakness shapes, now a self-check checklist.** Most of the
   fourteen instances above reduce to three recurring shapes. *Substring-of-
   message*: Task 8's `mean_reward_by_role` example, where deleting a check
   left twenty tests green because a different finding's message happened to
   contain the literal word the assertion searched for. *Fixture-cannot-
   reach*: Task 9's "only emitted scenarios" test, where a fixture with one of
   everything cannot distinguish "filtered correctly" from "never filtered at
   all" — the fixture has nothing left over for the check to have missed.
   *Holds-identically-before-and-after*, i.e. hash luck: Task 12's three checks
   whose expected answers happened to coincide with the sha256 tie-break,
   including a determinism test that could not detect the salted `hash()`
   substitution its own docstring named, because it compared orderings within
   one process, where the salt is constant across every comparison it made.
   Once this checklist was added to task dispatches, implementers found real
   gaps in three consecutive tasks — it earns its place as a standing
   self-check, not a one-time retrospective finding.
5. **A fix round needs the same scrutiny as the task it fixes.** Task 5's
   round-1 fix introduced a Critical worse than the finding it closed: a
   `shutil.rmtree` on a caller-supplied path that silently deleted the emitted
   package, or the whole run, if the path was wrong. Deletion-mutation could
   not see it, because the hazard was a new capability with no caller yet to
   exercise it — there was nothing to delete-and-check. What caught it was
   asking the re-reviewer point-blank what happens if a caller passes the
   wrong path, a question deletion-mutation cannot ask on its own.
6. **"Nothing fails when I delete it" cuts both ways.** The same Task 5
   episode is the sharpest example: the fix round's mutation pass exposed five
   unpinned checks and, in the same breath, certified the destructive
   `rmtree` as harmless, because nothing in the suite exercised the path
   where it mattered. A per-check counter measures how well the checks are
   pinned; it says nothing about whether the surrounding code is safe to run.
7. **Ask reviewers to run the experiment, not read the code.** Task 7's
   defect was found only by execution: a timed-out agent, marked
   unscoreable, voided all three roles' means through `comparable()`'s strict
   requirement — collapsing the verdict to `inconclusive` even though two of
   the three roles had scored perfectly. Two individually correct decisions
   (score the partial transcript on a timeout; require every declared role to
   score before a task counts toward any mean) jointly deleted data that a
   code read did not surface, because each rule looks right in isolation and
   only their interaction is wrong.
8. **When a plan states a principle and its own code contradicts it, the
   principle governs.** This generalizes the closure-and-emit build's "a
   ruling can create a gap" corollary from one incident into a standing
   adjudication rule, because it recurred a third time: Task 3's
   silent-concessions-versus-recorded-notes question, Task 8's `check_report`
   docstring promising `.get()`-style tolerance while the code indexed
   directly, and the timeout ruling in item 7 above. Writing the rule down
   lets the next build resolve the contradiction on the spot instead of
   stopping to ask.

The skills build adds five, and the first four were measured in its ledger rather
than reasoned to:

9. **A prompt's whole text is the haystack, so a substring assertion is vacuous
   by default — and the mandated structure is what satisfies it.** Nineteen
   plan-supplied assertions across Tasks 8–14 were *measured* satisfiable by
   content unrelated to the property their own docstring named; nine of the
   nineteen were in one task. The shape that recurred is §8 item 4's
   *substring-of-message*, transposed: `skills.load()` sets `body` to the entire
   file, so the whole document is the message. Three carriers did the satisfying
   over and over. **The mandated section headings**: `"refusal" in body.lower()`
   is satisfied by the required `## 5. Refusal conditions` heading, which makes it
   structurally vacuous for every conforming skill, forever. **The frontmatter
   `description:` line**, which by design paraphrases the whole skill — in one case
   it alone satisfied all three predicates of a test, so the test constrained no
   prose whatever. **The plan-mandated `## Contract` block**, which satisfied two
   of three predicates of a test about the subcommands the prose is supposed to
   name — two-sides-from-one-source *inside a single file*, a shape that recurred
   seven times and twice within one document. Digits are the same trap one level
   down: `"0"`, `"1"`, `"2"` occur 34/46/36 times in a `SKILL.md` as section
   numbers and version strings, so deleting the entire exit-code section left
   eleven tests green. Calibration worth keeping, because it says the weakness is
   targeted rather than total: a *fully* prose-stripped skeleton fails 6 of 11
   checks, so this is deletion-specific vacuity, not blanket vacuity. Net real
   automated coverage for the one skill whose defects no gate can ever see was
   four checks out of eleven before the strengthening.
   **On the other two shapes of item 4, for completeness.**
   *Fixture-cannot-reach* recurred and is treated below, in the answer to this
   section's transfer prediction. *Holds-identically-before-and-after* did **not**
   recur in its literal form and has no prompt analogue: it was hash luck, and a
   text predicate has no hash to be lucky about. Its generalization did recur, and
   this build named it — **two-sides-from-one-source**: a test whose asserted side
   and expected side derive from the same source, so no mutation of that source can
   separate them. Seven instances, two of them *inside a single document*, where a
   prompt's own mandated `## Contract` block satisfied a test about the prompt's
   prose. The counter is the one this build made a standing constraint: when a test
   derives both sides from one source, the mutation must sit on the path *between*
   them — the copy, the compile step, the writer — never on the source. Before
   writing "verify by mutating X", trace whether X reaches both sides.
10. **"Strengthen the assertion" is not a safe default; strengthening is a
    two-axis measurement.** The mirror failure is just as real and appeared in the
    same task: one strengthened predicate anchored on `**bold**` table markers,
    so reformatting the table into prose broke a still-conforming file. Another
    pinned three `Human gate N` *identifiers* where the concern had been that
    gates could go *undescribed* — a real improvement, but not the one claimed,
    and recorded as narrowed rather than closed. And a proposed strengthening was
    caught going red on the conforming file before it shipped. So four directions,
    not two: red on deletion, green on the delivered file, green on a paraphrase
    or reformat of the same rule, and evaluated against the delivered file
    *before* adoption. The rule that made this affordable at scale: strengthen
    only what an implementer has **measured**, never what it suspects — the
    measurement is what separates this from rewriting a plan's tests to taste.
11. **Before raising a finding against a skill's output, check what the stage's
    `reads` actually gives it.** A finding that requires knowledge outside the
    contract is a finding against the *contract or the fixture*, never against
    the prompt. This is here because it cost this build two wrong fix rounds and
    a retraction: a value in a proposed scenario was faulted for being ungrounded,
    reasoning from a claims file that `tg-propose` is forbidden to read. It was
    the controller committing the exact isolation failure the design exists to
    prevent, and one grep would have settled it before the first round instead of
    after the third. A worked example that a prompt's own reader cannot follow is
    the same error one step further along, and round 3 shipped one.
12. **A fixture test that pins the presence of a defect does not pin the absence
    of collateral damage.** The gap fixture was built by removing error semantics
    and tested for exactly that. It over-removed: deleting a whole `returns` block
    took a happy-path capability fact with it, which no CI predicate could see and
    a live run exposed immediately — reconcile's loudest gap blocked all six
    downstream stages, where the four purpose-built gaps each blocked only two.
    The contrast *is* the evidence. It showed upstream too, which is the sharpest
    measurement of the damage: against the over-subtracted file the two extracts
    filed **zero** `outcome_class` claims between them, where against the repaired
    one they file two. That recording was discarded and re-made; the numbers in §9
    are the repaired fixture's. Then guarding it took two goes in two
    directions: a structural key-path guard caught key *deletion* and was
    values-blind, so blanking the same values to `""` left every test passing.
    Guarding one direction does not guard the other, and neither guard would have
    existed without a live run to point at the damage.
13. **A deferral that lives only in a report evaporates. Give the ledger a
    standing section for them.** One requirement crossed three tasks in this
    build, each with a locally reasonable story — deferred in writing by one
    task's report, never picked up by the next, and answered by the third with a
    narrower question than the one that had been asked. Nothing was lying; the
    ledger simply had nowhere to carry an obligation. The fix is mechanical and
    worked for the remaining nine tasks: a `DEFERRALS OWED` section at the top of
    the ledger, one line per open item naming the task that owes it, and every
    dispatch must carry the ones addressed to it *explicitly* rather than trusting
    the implementer to read back.
    **Two mechanisms did this work, and a build that adopts only one will lose
    half of it.** `DEFERRALS OWED` carries *obligations that cross tasks* — a
    requirement one task defers and another must discharge — and it is where §4's
    two limitations and item 11 above came from. The parked table came from a
    different and equally necessary convention: a per-task
    `minor (deferred) / parked, for the final whole-branch review to triage` line,
    written at the moment a review's Minor was ruled not worth a fix round, which
    is where all but a couple of its rows originate. An obligation needs an
    addressee and a deadline; triaged residue needs neither, and putting it in the
    section that has both would bury the items that are actually owed. Between
    them, everything written back here came off the ledger rather than out of
    memory.

**Which of these survive when the producer is a prompt rather than code.**
Plan 4 replaces most of this build's producers — the six stage skills and the
orchestrator — with prompts, and not every counter above transfers unchanged.
Deletion-mutation (item 3) has no meaning for a prompt: there is no line to
delete and no diff to recompile. Fixture reachability (items 3's dual, and
item 4's *fixture-cannot-reach* shape) transfers and matters more, not less —
§9's negative refusal fixtures are exactly the "one of everything" shape that
cannot tell "the skill refused correctly" from "the skill never checked."
"Run the experiment, not read the code" (item 7) transfers best of all: a
prompt's failure mode is behavioral, so an execution trace is the only
artifact that will show it, and reading a `SKILL.md` tells you what it asked
for, not what a model did with it. What does not transfer is the confidence
this build earned from its own numbers — pinned-check counts, mutation-kill
rates — because those numbers were counting something (lines, branches) that
a skill's markdown does not have. The next build should expect to find these
shapes again, not to find these counters again.

**What actually happened, now that the build is done.** Two of the four
predictions above held and **two were wrong**. Both wrong ones are kept above as
the record of what was predicted; what follows is what the build measured
instead.

*Deletion-mutation has no meaning for a prompt* — **wrong, and usefully so.**
Deleting a numbered step, a table row or a whole section from a copy of a
`SKILL.md` and re-running the delivered test file against it turned out to be the
build's single most productive instrument: it is what measured all nineteen
vacuous assertions in item 9, and it is what let a fix round demonstrate a
*latent* hazard rather than only the current state — deleting an ordering
instruction from both places it appeared *and* quoting a fixture's own phrase into
the section, which is the exact future edit that would have made the old test
green forever. What has no meaning for a prompt is *coverage arithmetic* over
mutations, not mutation itself.

*Fixture reachability transfers and matters more* — **held, and §9's negative
fixtures were where it bit**, exactly as predicted. The reviewer restored the one
sentence whose removal creates the contradiction fixture's whole point, and all
five of its CI tests still passed: nothing in them read that file's *content* at
all, because the classifier only checks it is JSON with a `tools` key. So the
fixture-cannot-reach shape the task existed to close was left open on one of three
files, and closing it took four fix rounds. The shape also appeared somewhere the
prediction did not look — inside a live *exercise* rather than a test. One skill's
primary behavioural property could not be discriminated because all four coverage
cells happened to be claimed: full coverage is precisely the state in which a
completeness rule cannot be tested, and an unclaimed cell is what would settle it.

*Run the experiment, not read the code* — **held most emphatically of all, and it
is the finding this build would keep if it could keep only one.** Every defect
that no gate and no test could see came from a live dispatch. The same proposition
filed under two different `kind` values by two extract slices, silently costing the
coverage denominator a column — both gates clean, found by reading output. A real
reconcile *halting* the pipeline on a blocking gap on the first real run, which is
§5's own stated test of whether gap detection works. A real reconcile over real
extract output enumerating **six** capability cells where the hand-authored world
model had four — a *larger* denominator, the opposite of the silent-column-loss
failure the check was watching for. And the number moves with the input rather
than with the prompt: the same skill on the same target measured **seven** cells
from hand-authored fixture claims and **six** from real extract claims. Two
measurements of two inputs, not a prediction beaten by a measurement — which makes
it stage-level variance driven by upstream claim quality, sitting in the one
artifact that freezes the coverage denominator for the whole run. An orchestrator handed
`--no-gate` still refusing to overrule a halt, because the flag skips human review
and a blocking gap is not a human gate — a distinction that lives in one sentence
of prose and had no other instrument. An adversary proving its own read order from
the *content* of its filed notes, having considered and eliminated the first
candidate with its reason, which an adversary that had already seen the oracle
would have had no reason to write. And the two isolation self-reports in the parked
table above, which are the only evidence that will ever exist for that rule.

*What does not transfer is the confidence earned from this build's own numbers —
pinned-check counts, mutation-kill rates* — **wrong, and wrong in the same way the
deletion-mutation prediction was.** Items 9 and 10 above are made of exactly those
counters, taken over a skill's markdown: a fully prose-stripped skeleton failing
**6 of 11** checks is a mutation-kill rate, "**four** real checks out of eleven" is
a pinned-check count, and the search-space measurements that rebalanced a fragile
predicate (3/6/6 against 3/26/18 occurrences) are the same arithmetic one scope
narrower. The prediction's error was assuming the countable population had to be
lines or branches. It does not: a `SKILL.md` has numbered Method steps, invariants,
refusal conditions and table rows, and its test file has assertions — all
enumerable, all mutable one at a time, all divisible into a denominator. What
genuinely does not transfer is a **coverage** claim over the artifact. There is no
enumerable set of "everything this prose asks for" the way there is a set of every
branch, so "11 checks, 4 of them real" is a statement about the checks and never
about the prompt. Count the checks; do not infer the prompt is covered.

One further counter this build needed and the prediction did not anticipate:
**when two independent slices agree on a value, that is not yet a leak.** Three of
four instantiate members independently chose the same summary string, tripping a
suspicious-agreement heuristic. The discriminator is stronger than the heuristic
and is now written into that skill's exercise record: a leaked value must exist in
the artifact it leaked from, and a converged value exists nowhere upstream. So
grep the readable artifacts *and* the forbidden ones — absent from both means a
shared model prior, present in a forbidden one means a real leak, present in a
readable one means it was never a leak at all. Without it, the heuristic alone
raises an isolation finding against a stage that did nothing wrong, which is item
11's error in a different costume.

## 9. Testing the pipeline itself

- **Code components** (`validate`, `check-refs`, `dedupe-candidates`, `emit`,
  `smoke`, `diff-runs`, `compare-gold`) get ordinary unit tests. That is most of
  the actual lines of code in the project.
- **Skills get fixture-based stage tests asserting invariants, not outputs** —
  output validates; every claim carries evidence; no capability exists without a
  claim. Exact-match assertions are impossible and undesirable.
- **The valuable tests are negative fixtures proving the refusal conditions
  fire:** a deliberately self-contradictory input pair *must* produce a
  `contradictions` entry; an input with error semantics removed *must* produce a
  `gap` that blocks stage 2. If those do not fail loudly, §5's refusal conditions
  are decorative.
- **One golden end-to-end fixture:** a two-capability toy world small enough to
  review by hand, run in CI.

### All three fixtures now exist, and both refusals have fired

**The golden fixture** is `tests/fixtures/toy/{api.json,notes.md,trace.json}` —
three real input files in three of the artifact classes §1 names: a tool
specification, an operator's prose notes, and a captured trace. (Not source code,
which §8 defers.) `tests/toy.py` builds every stage's artifact over them, up to
and including a scored suite. It carries the two-stated-artifacts-against-one-trace-span shape, so
its recorded contradiction is one where preferring a side is *defensible*.

**The two negative fixtures** are `tests/fixtures/toy-contradiction/` and
`tests/fixtures/toy-gap/`. The contradiction fixture carries all three files and is
built so that *nothing* licenses preferring either side, which is what makes
`unresolved` the only honest answer and distinguishes it from the golden world. The
gap fixture deliberately carries **no `trace.json`**: a trace would leak the
removed behaviour back in through the one artifact that observes it directly.

**The recorded-output convention, and why a recording is committed.** A refusal
needs a model's output to assert against, and pytest cannot dispatch a subagent. So
the dispatch is run by hand per `docs/running-a-stage-by-hand.md` and the resulting
world model is committed at `tests/fixtures/<name>/recorded/01-world-model.json`.
The tests over it are behind the `live` marker. Committing the recording is the
whole point: **a refusal observed once and never again is exactly the decorative
refusal condition this section warns about**, and a committed recording turns it
into a regression test. The cost is stated rather than hidden — a recording is
evidence of what a skill did *at one commit*, so changing a skill obliges
re-recording, and that re-recording is a reviewable diff rather than a silent
drift. (`check-refs` pointed at a bare `recorded/` directory exits 1 with every
claim reference unresolvable. That is expected, not a defect: a lone world model
carries no claims file and no manifest for its references to resolve against.)

**Both refusals fired, on real `tg-extract` output rather than hand-authored
claims** — which matters because a hand-authored claim set can be built to make the
refusal easy. On the gap fixture the two extracts filed exactly **two**
`outcome_class` claims between them, and both describe a happy-path return: the
list `find_tickets` gives for matching filters, and the ticket-with-comments
`get_ticket` gives back. Nothing in the claim set says what either call does in any
other case, and both claims came from `api.json` — the other extract filed no
outcome class at all. So
reconcile met a schema requiring at least one outcome class per capability with
material for the success class and nothing for any other — and it declined to
invent one. Both capabilities came back `success` plus two `underspecified`, with
no `error`, `not_found` or `empty` kind anywhere, plus three gaps, all three
blocking `propose`. That `underspecified` exists in the outcome-class enum
precisely so a model has somewhere honest to put an outcome nobody documented, and
a model reached for it unprompted, is the schema and the prompt agreeing. On the
contradiction fixture it
recorded two contradictions — two entries because the schema is pairwise — both
`resolution: "unresolved"`, and filed the unknown-id outcome as `underspecified`
rather than `error`: it refused twice in two registers about the same fact. The
discrimination is per outcome class rather than per capability, and the proof is
that the *other* capability in the same file did get a real `empty` class, because
that fixture's `api.json` does still say "possibly empty".

## 10. Risks

| Risk | Mitigation |
|---|---|
| Confabulation under under-specification — skills invent facts to be helpful. | Explicit refusal conditions in every skill; halt on blocking gap; negative fixtures that prove refusal fires. |
| Correlated labeler/adversary blind spots. | Expert review sampled from high-confidence accepts. Not solvable within the pipeline. |
| Silent schema drift between prompt stages. | Schema validation after every stage; referential-integrity linter; bounded single repair then halt. Plus `check-skills`, which catches the drift one step earlier — in the prompt's own `## Contract` block, before a model has been paid to follow it (§5). |
| Trivial suite that all-passes. | Distractor design as an explicit numbered step; weak-baseline agent in smoke; per-task all-pass flags. |
| Broken gold labels that all-fail. | Oracle agent in smoke; `tg-challenge` row 4; `grounded_in` reachability gate. |
| Non-terminating enrichment loop. | Denominator frozen in 1b; round cap `K`; no-progress fixpoint guard; amendments require a recorded orchestrator decision. |
| Nondeterminism swamping any measured improvement. | Manifest pins model/effort/skill hash, written by `record-stage`; `diff-runs` attributes variance per stage; artifacts are pinnable so downstream stages can be re-run against a frozen predecessor. One caveat measured in the skills build and parked in §8: the orchestrator has no lever for `effort`, so that field records a characterization rather than a setting and `model` + `skill_sha256` carry the pin. |
| Scope creep on invariant expression. | `machine:` form limited to a handful of expression types; everything else is `prose:` and skill-self-checked. |

## 11. Next step

**Run the slice.** Every component §8 names is built and the pipeline has run end
to end with a model at every stage — on §9's toy world, which tests the pipeline
rather than the hypothesis. What is left is the experiment itself: intake the real
aap2 `api.json` + `schema.json` + a handful of traces, drive `tg-orchestrate`
through `K=2` rounds with a cap of ~8 scenarios, and measure with `smoke` and
`compare-gold` against the ~10 hand-authored bench tasks. Two things the toy run
already tells the next plan to expect. First, a real `tg-reconcile` halts on a
blocking gap, and on a real target it will halt more than once — so the plan needs
a budget for gate-1 rulings and the missing inputs they ask for, not a single
unattended pass. Second, an ungated run and a run resumed after a human ruling are
different experiments, and only the first can carry the reproducibility claim
`--no-gate` exists for; §8's deferral of `diff-runs` execution to a later slice is
what makes that affordable, and it stays deferred.
