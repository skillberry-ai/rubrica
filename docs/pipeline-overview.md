# How the test generator works

> **For team review.** All eight skills now exist and the pipeline has run end to
> end with a model at every stage — against the two-capability toy world, not yet
> against a real target. Numbers below are measured from that run unless labelled
> otherwise.

It builds a test suite for an agentic system out of whatever artifacts describe
that system — specs, captured trajectories, source — by running a chain of AI
skills over a schema-validated contract on disk.

## The idea in one read

This is an **experiment**, with a single question: does prompt-carried judgment
survive a chain of artifact handoffs well enough to produce a suite worth
running?

Everything follows from one design choice: **artifacts on disk are the only
channel between stages.** A stage is dispatched with exactly three things — the
run directory, its stage name, and its skill file. No conversational context is
threaded through. If a stage needs a fact, it reads it from an artifact, or it
does not have it.

That constraint is what makes the pipeline inspectable: every handoff is a file
you can open, schema-check, and diff between runs.

| | |
|---|---|
| **Layer 1** | `testgen validate --stage X` — JSON Schema, one per artifact kind. *Is this file shaped correctly?* |
| **Layer 2** | `testgen check-refs` — cross-artifact references, seed conformance, reachability. *Do the files agree with each other?* |
| **Exit codes** | `0` clean · `1` findings, one per line on stdout · `2` usage error or unreadable run. The split matters: a `1` is a repairable stage defect worth one retry, a `2` means the harness is misconfigured and retrying cannot help. |
| **Skill contract** | Every `SKILL.md` declares its `stage`, `reads`, `writes`, `schemas` and `invokes` in a machine-readable block. `testgen check-skills` verifies each name against the code that owns it — so a prompt naming a path or stage that does not exist fails in CI, not at run time. |

## The pipeline

Stage numbers are the real on-disk directory numbers — the ordering is the
contract, not a diagram convention.

| Dir | Stage | Runs as | Reads | Writes | Gate |
|---|---|---|---|---|---|
| `00` | intake | code | the input files you name, plus target name, interface, limits | `manifest.json`, `00-inputs/<stored_as>` | validate |
| `01a` | extract | `tg-extract` — **fan-out**, one per input | the manifest, and its own one file under `00-inputs/` — never a sibling's | `01-claims/<artifact-id>.json` | validate |
| `01b` | reconcile | `tg-reconcile` — **barrier** | the manifest and every claims file | `01-world-model.json` | validate · check-refs · **human gate 1** |
| `02` | propose | `tg-propose` | `manifest.json`, `01-world-model.json`, `02-scenarios.json`, `03-coverage/latest.json` | `02-scenarios.json` (appends this round) | validate |
| `03` | score | `tg-score` — **barrier** | `manifest.json`, `01-world-model.json`, `02-scenarios.json` | `03-coverage/round-N.json`, `03-coverage/latest.json`, `02-scenarios.json` (statuses) | validate · check-refs · **human gate 2** |
| `04` | instantiate | `tg-instantiate` — **fan-out**, one per active scenario | `01-world-model.json`, `02-scenarios.json` | `04-instances/<sid>/{seed.json,expected.json,rationale.md}` | validate · check-refs |
| `05` | challenge | `tg-challenge` — **fan-out**, one per instance | the scenario and the seed — then `expected.json` **last** | `05-verdicts/<sid>.json` | validate · **human gate 3** |
| `06` | emit | `tg-emit` — wraps code | `02-scenarios.json`, `05-verdicts/`, `04-instances/*/expected.json`, `01-world-model.json` | `06-suite/<sid>/` task packages | validate · check-refs |
| `07` | smoke | code | the emitted suite and the agent roster | `07-report.json` | validate · check-refs |

**Stages 02 and 03 are a loop.** Propose targets the holes the coverage report
names; score recomputes coverage and returns a verdict — `continue`,
`converged`, `halted_no_progress`, or `halted_round_cap`. Score *computes* that
verdict; only the orchestrator acts on it. The loop is bounded by `max_rounds`
in the manifest.

**Fan-out means isolation, not just parallelism.** An extract subagent sees one
input file, so it cannot smuggle a sibling's conclusion into its claims. An
instantiate subagent builds one seed world without knowing what the other tests
cover. That isolation is the point: it is what makes a contradiction between two
inputs something the pipeline *records* rather than something a single reader
silently resolves.

### Three human gates

- **After reconcile** — confirm the world model, resolve contradictions, rule on
  gaps. Highest leverage in the pipeline: every downstream stage inherits these
  errors, and it is the one artifact small enough to read carefully.
- **After the coverage loop** — review the scenario list and coverage report
  *before* paying for per-scenario fan-out. This is the cost gate.
- **After challenge** — skim rejects and re-seeds. Mostly informational.

All three are skippable with `--no-gate`, and have to be: five identical
pipelines cannot be run if a human intervenes in each. Note that `--no-gate` is
an argument to the *orchestrator skill's invocation*, not a `testgen` flag — the
gates live in the prompt and no code enforces them. A prompt-level flag can be
forgotten in a way a CLI flag cannot; that is a known cost, accepted because
enforcing the gates in code would mean the orchestrator stops being a skill,
which is the thing being tested.

## What each skill contributes

A skill is a prompt file, not code. The judgment lives in the prose; the
contract block above it is what keeps that prose from drifting away from the
artifacts.

| Skill | Job |
|---|---|
| `tg-extract` | Turns one input artifact into atomic, evidence-backed claims. Every claim carries a locator and an honest `derivation` — *stated*, *inferred*, or *reverse_engineered* — so "the spec says this" and "I guessed from one trace" never look alike downstream. |
| `tg-reconcile` | Merges every extractor's claims into one world model, *recording* contradictions and gaps rather than resolving them, and freezes the coverage denominator exactly once. |
| `tg-propose` | Reads the world model and latest coverage report, then appends scenarios targeting real, closable holes — never rewriting or renumbering what an earlier round proposed. |
| `tg-score` | Folds the scenario pairs that are one test, promotes the rest, computes both coverage matrices against the frozen denominator, justifies every uncovered row with a hole, and computes the verdict. |
| `tg-instantiate` | Builds one scenario's seed world — **distractors first**, so no agent can pass by reading back the only matching record — then derives the oracle from that seed rather than the other way round, and records which near-misses exist so a reviewer can judge fairness. |
| `tg-challenge` | The adversary. Verifies one instance is a fair, discriminating test, reading the oracle *last* — an adversary who sees the answer first confirms almost anything. |
| `tg-emit` | A deliberately thin entry point over `testgen emit`; writes nothing itself. Emit is code, not a prompt, because two runs with identical stage-4 and stage-5 artifacts must produce identical suites — otherwise variance can no longer be attributed to a stage. |
| `tg-orchestrate` | The loop itself: dispatch each stage, validate, allow one bounded repair, hold the human gates, record each stage's model and skill hash, append every decision to the run's lab notebook. Not a stage — it declares no `stage` and no `schemas`. |

## What a real run produced

One whole-pipeline run, three input files in, a scored suite out, with a model at
every stage and no human intervention except the one gate ruling noted below.

**The number that matters most: `all_pass_tasks: 0` and `all_fail_tasks: 0`.**
No task was passed by every agent role or failed by every role. Mean reward by
role came out **1.0 oracle / 0.7 under-test / 0.2 weak baseline**, with
`oracle_failures: 0` and `unscoreable: 0`. An agent handed the reference answer
passes everything, and a deliberately weak agent does not — which is the property
a generated suite exists to have, and the first one a degenerate suite loses.

**It halted at the gap gate on its own, before proposing anything.** Reconcile
recorded a gap whose `blocks` named `propose` — none of the three inputs says
anything about invalid-argument behaviour — and the orchestrator stopped rather
than working around it. Handed `--no-gate`, it reasoned that the flag skips the
human review and does not lift a halt. The design's own statement of the test is
that if a blocking gap never stops a real run, gap detection is not working.

**A human ruled the gap non-blocking for its own cells only, and the ruling was
honoured exactly.** Coverage came back **4 of 6 capability cells** and 2 of 2
goals, `converged` in round 1 of 2, with both bad-argument cells returned as
`blocked_by_gap` holes carrying the gap id — not `not_yet_attempted`, which would
have implied another round could close them. The world model was never edited.

**Real inputs produced a *larger* denominator than the hand-authored fixture** —
6 capability cells against the fixture's 4 — which is the opposite of the failure
that read was watching for. The feared outcome was a run reporting 100% because a
column was silently dropped; the actual outcome is an honest 66.7% with two
justified holes.

### Both refusal conditions fire

Two negative fixtures check that the skills decline rather than guess, and both
were exercised against real extract output rather than hand-authored claims.

- **A world with all error semantics removed** (`tests/fixtures/toy-gap/`): the
  two extracts filed no outcome-class claims between them, so reconcile faced a
  schema requiring at least one outcome class per capability and claims supplying
  none. It filed `success` plus `underspecified` throughout — **not one invented
  `error`, `not_found` or `empty` class** — and recorded three gaps, all blocking
  `propose`.
- **A self-contradictory input pair** (`tests/fixtures/toy-contradiction/`): two
  contradictions, both `resolution: "unresolved"`, with the unknown-id outcome
  filed as `underspecified` rather than `error`. It declined the reading that
  would have let two claims from one self-contradicting document outvote a third,
  and named the pull it was resisting.

Both recorded outputs are committed at
`tests/fixtures/<name>/recorded/01-world-model.json`, so a refusal observed once
becomes a regression test. Changing a skill obliges re-recording — and that
re-record is a reviewable diff rather than silent drift.

## A run on disk

One directory per run. This is the whole state of the system — there is nowhere
else state hides.

```
runs/run-20260810-051723/
├── manifest.json            # inputs, hashes, limits, per-stage model + skill hash
├── decisions.md             # append-only lab notebook
├── 00-inputs/               # byte copies of every registered input
├── 01-claims/
│   ├── api-json.json        # one file per input artifact
│   ├── notes-md.json
│   └── trace-json.json
├── 01-world-model.json      # capabilities, entities, goals, invariants,
│                            # contradictions, gaps, frozen denominator
├── 02-scenarios.json        # every round's scenarios, with status
├── 03-coverage/
│   ├── round-1.json
│   └── latest.json          # the pointer the next round reads
├── 04-instances/<scenario-id>/
│   ├── seed.json            # the world, distractors included
│   ├── expected.json        # the oracle, derived from that seed
│   └── rationale.md         # which near-misses exist, and why
├── 05-verdicts/<scenario-id>.json
├── 06-suite/<scenario-id>/   # the emitted task package
├── 07-report.json
└── measurement/             # recall, stability, review sampling
```

## The deterministic surface

Everything a skill is not trusted to do itself. One console script, twelve
subcommands — the exit codes above are the contract the orchestrator branches on.

| Command | Job |
|---|---|
| `intake` | register and hash inputs, mint the run |
| `validate` | schema-validate one stage's output |
| `check-refs` | cross-artifact and reachability checks |
| `check-skills` | check every skill's contract against the code it names |
| `dedupe-candidates` | propose candidate duplicate scenario pairs — proposes, never decides |
| `record-stage` | record a stage's model, effort and skill hash in the manifest |
| `decide` | append one orchestrator decision to the run's notebook |
| `emit` | compile accepted instances into task packages |
| `smoke` | run the emitted suite against the agent roster |
| `compare-gold` | recall and novelty against hand-authored bench tasks |
| `diff-runs` | per-stage stability across two runs |
| `sample-for-review` | write a stratified human-review packet |

## Where the build is

| Piece | State |
|---|---|
| Contract spine — paths, schemas, both check layers, intake, emit, smoke | done |
| Measurement — recall vs. gold, run-to-run stability, review sampling | done |
| Skill contract parser and `check-skills` | done |
| Two-capability toy world, run end to end in CI with no model at all | done |
| All eight skills — extract, reconcile, propose, score, instantiate, challenge, emit, orchestrate | done |
| Refusal fixtures — a contradictory world and a gapped one, with recorded outcomes | done |
| Whole pipeline run end to end with a model at every stage | done (toy world) |
| First run against a real target | separate plan |
| Run-to-run variance measured with `diff-runs` | separate plan |

1126 tests passing, 4 live tests passing against committed recordings, `ruff`
clean, `testgen check-skills` clean.

Each skill also has one **live exercise**: a fresh subagent, given only the three
permitted things, run against the toy world, with the result recorded beside the
skill in `exercise.md`. That is deliberate — reading a prompt tells you what it
asked for, not what a model did with it, so a prompt's failure mode is only
visible in an execution trace.

## What we know does not work yet

Stated plainly, because a design document that lists only what works is not much
use for planning. The full list, with the reasoning that parked each item, is in
§8 of `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md`.

- **The isolation rule is enforceable on artifacts inside a run and unenforceable
  on everything else a subagent can reach.** A member that read a sibling's seed
  produces a byte-identical artifact to one that did not. Two violations were
  observed during the build; both surfaced *only* because a subagent volunteered
  it in a report nobody obliged it to write. No schema, no `check-refs` and no
  digest could have caught either. This is the weakest link and the first thing a
  later slice should harden.
- **The world model has no representation for a field's value domain.** So every
  seed value is synthetic by construction, and a concrete value anywhere
  downstream of reconcile is a *prescription* to `tg-instantiate` rather than an
  assertion about the target.
- **Layer 2 checks that an element *references* a resolvable claim, never that
  the claim *supports* it.** Support is semantic. Two real defects lived under
  that hole in the golden fixture itself.
- **Seed conformance is one-directional.** A seed can drop a declared collection,
  or declare all of them empty, and pass both check layers with zero findings.
  Whether *partial* seeds are legal is an open design question.
- **The orchestrator has no lever for `effort`.** It records the field, but the
  dispatch mechanism cannot supply the value, so every `effort` in a manifest
  today is a characterization rather than a setting — `model` and `skill_sha256`
  carry the reproducibility claim.
- **One exercise is one sample.** A prompt that works once may not work twice,
  and nothing has yet measured variance. `diff-runs` exists for exactly that.
