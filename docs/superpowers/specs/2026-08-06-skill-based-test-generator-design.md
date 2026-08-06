# Skill-Based Test Generator — Design

**Date:** 2026-08-06
**Status:** Approved design, pending implementation plan
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
  decisions.md            append-only orchestrator log
```

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
 assertions: [{kind: answer_contains|answer_excludes|tool_called|tool_not_called|value_equals,
               target, value, rationale,
               grounded_in: {seed_pointer}}],       ← JSON pointer into this scenario's seed.json
 trajectory: {match: subset|exact-set|exact-sequence, operations},
 completion: {status, nonempty_answer},
 negative_expectations: [...]}
```

`grounded_in.seed_pointer` reduces the reachability gate to a few lines of code:
for a positive assertion the pointer must resolve and contain its value; for
`answer_excludes` and negative expectations the check inverts — the pointer must
resolve to nothing. That is how `log-does-not-say`-style tests become both
expressible and verifiable.

**Verdict** (`05-verdicts/<sid>.json`):

```
{scenario_id, uniquely_determined,
 alternative_answers: [{answer, world_consistent_reason}],
 derivable_without_guessing, minimum_tool_calls_found,
 verdict: accept|re-seed|reject, notes}
```

`minimum_tool_calls_found` is the adversary independently measuring difficulty,
cross-checking stage 2's `hop_depth` claim.

### Three validation layers

1. **Schema** — `bin/validate <run-dir> <stage>` runs after every stage; output
   must validate before the next dispatch. On failure: **one** repair attempt
   (re-dispatch the same stage with the validator error appended), then halt.
   Bounded, not a retry spiral.
2. **Referential integrity** — `bin/check-refs`, expressing what JSON Schema
   cannot: every `capability_id` in 02 exists in 01; every `scenario_id` under
   04/05/06 is `active` in 02; every `seed_pointer` resolves within its *own*
   scenario's seed; `machine:` invariants hold over each seed.
3. **Smoke** — stage 7: does the emitted suite actually execute.

### Reproducibility hooks

`manifest.json` records, per stage: model, effort, and a content hash of the
`SKILL.md` used. Two runs are comparable only if those match.

`bin/diff-runs A B` compares artifact by artifact, so variance can be attributed
to a stage — the difference between "the pipeline is nondeterministic" and
"stage 2 is nondeterministic and everything downstream is stable given a fixed
02."

**Run ids and timestamps are minted by intake (code), never by skills.** A skill
that invents a timestamp makes two otherwise-identical artifacts diff.

## 5. Skill anatomy and orchestration

```
skills/tg-{orchestrate,extract,reconcile,propose,score,instantiate,challenge,emit}/SKILL.md
schema/*.json
bin/{intake,validate,check-refs,dedupe-candidates,emit,smoke,diff-runs,compare-gold,sample-for-review}
```

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

## 8. First slice

- **aap2 only**, one simulation skill.
- Inputs deliberately small: the aap2 `api.json` + `schema.json` + a handful of
  traces. **Not** the source tree — three artifacts still exercise fan-out,
  reconciliation, and contradiction detection at a fraction of the cost.
- **All stages present.** `K=2` loop rounds, cap ~8 scenarios.
- All three code gates real: `validate`, `check-refs`, `smoke`.
- Measurement: `smoke` (with oracle + weak baseline) and `compare-gold`.

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

## 10. Risks

| Risk | Mitigation |
|---|---|
| Confabulation under under-specification — skills invent facts to be helpful. | Explicit refusal conditions in every skill; halt on blocking gap; negative fixtures that prove refusal fires. |
| Correlated labeler/adversary blind spots. | Expert review sampled from high-confidence accepts. Not solvable within the pipeline. |
| Silent schema drift between prompt stages. | Schema validation after every stage; referential-integrity linter; bounded single repair then halt. |
| Trivial suite that all-passes. | Distractor design as an explicit numbered step; weak-baseline agent in smoke; per-task all-pass flags. |
| Broken gold labels that all-fail. | Oracle agent in smoke; `tg-challenge` row 4; `grounded_in` reachability gate. |
| Non-terminating enrichment loop. | Denominator frozen in 1b; round cap `K`; no-progress fixpoint guard; amendments require a recorded orchestrator decision. |
| Nondeterminism swamping any measured improvement. | Manifest pins model/effort/skill hash; `diff-runs` attributes variance per stage; artifacts are pinnable so downstream stages can be re-run against a frozen predecessor. |
| Scope creep on invariant expression. | `machine:` form limited to a handful of expression types; everything else is `prose:` and skill-self-checked. |

## 11. Next step

Produce an implementation plan (via the `writing-plans` skill) covering the first
slice in §8.
