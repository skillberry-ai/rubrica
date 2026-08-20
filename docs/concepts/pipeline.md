# The pipeline

Rubrica builds a test suite for an agentic system out of whatever artifacts
describe that system — specs, captured trajectories, source — by running a
chain of AI skills over a schema-validated contract on disk.

The one design choice everything else follows from: **artifacts on disk are
the only channel between stages.** A stage is dispatched with exactly three
things — the run directory, its stage name, and its skill file. No
conversational context is threaded through. If a stage needs a fact, it reads
it from an artifact, or it does not have it. That constraint is what makes the
pipeline inspectable: every handoff is a file you can open, schema-check, and
diff between runs.

[`pipeline-diagram.html`](pipeline-diagram.html) draws the same pipeline this
document describes — open it in a browser. The drawing is where the fan-outs,
their barriers, the round loop and the human gates are easiest to see; the
tables below are where the exact reads and writes live.

## The stages

Stage numbers are the real on-disk directory numbers — the ordering is the
contract, not a diagram convention.

| Dir | Stage | Runs as | Reads | Writes | Gate |
|---|---|---|---|---|---|
| — | `survey` | code — walks a corpus and mints the run | the corpus roots you name, plus target name, interface, objective | `00-catalogue.json` | validate |
| — | `triage` | `rb-triage` | `00-catalogue.json` only | `00-triage.json` | validate · check-refs · human gate 0 |
| `00` | `intake` | code | the input files you name, plus target name, interface, limits — or, on the survey path, an already-admitted `00-triage.json` | `manifest.json`, `00-inputs/<stored_as>` | validate |
| `01a` | `extract` | `rb-extract` — fan-out, one per input | the manifest, and its own one file under `00-inputs/` — never a sibling's | `01-claims/<artifact-id>.json` | validate |
| `01b` | `reconcile-subjects` | `rb-reconcile-subjects` — barrier | the manifest and every claims file | `01-subjects.json` | validate · check-refs |
| `01c` | `reconcile-contradict` | `rb-reconcile-contradict` — fan-out, one per subject | the manifest, every claims file, `01-subjects.json` | `01-contradictions/<subject-id>.json` | validate · check-refs |
| `01d` | `reconcile-capabilities` | `rb-reconcile-capabilities` | the manifest, every claims file, `01-contradictions/` | `01-capabilities.json` | validate · check-refs |
| `01e` | `reconcile-outcomes` | `rb-reconcile-outcomes` | the above, plus `01-capabilities.json` | `01-outcomes.json` | validate · check-refs |
| `01f` | `reconcile-entities` | `rb-reconcile-entities` | the above, plus `01-capabilities.json` | `01-entities.json` | validate · check-refs |
| `01g` | `reconcile-goals` | `rb-reconcile-goals` | the above, plus `01-capabilities.json` and `01-entities.json` | `01-goals.json` | validate · check-refs |
| `01h` | `reconcile-gaps` | `rb-reconcile-gaps` | the manifest, every claims file, and every partial above | `01-gaps.json` | validate · check-refs |
| `01i` | `reconcile-seal` | code — `rubrica reconcile-seal` | the manifest and all seven partials | `01-world-model.json` | validate · check-refs · human gate 1 |
| `02` | `propose` | `rb-propose` | `manifest.json`, `01-world-model.json`, `02-scenarios.json`, `03-coverage/latest.json` | `02-scenarios.json` (appends this round) | validate |
| `03` | `score` | `rb-score` — barrier | `manifest.json`, `01-world-model.json`, `02-scenarios.json` | `03-coverage/round-N.json`, `03-coverage/latest.json`, `02-scenarios.json` (statuses) | validate · check-refs · human gate 2 |
| `04` | `instantiate` | `rb-instantiate` — fan-out, one per active scenario | `01-world-model.json`, `02-scenarios.json` | `04-instances/<sid>/{seed.json,expected.json,rationale.md}` | validate · check-refs |
| `05` | `challenge` | `rb-challenge` — fan-out, one per instance | the scenario and the seed — then `expected.json` last | `05-verdicts/<sid>.json` | validate · check-refs · human gate 3 |
| `06` | `emit` | `rb-emit` — wraps code | `02-scenarios.json`, `05-verdicts/`, `04-instances/*/expected.json`, `01-world-model.json` | `06-suite/<sid>/` task packages | validate · check-refs |
| `07` | `smoke` | code | the emitted suite and the agent roster | `07-report.json` | validate · check-refs |

`survey` and `triage` carry no `0N` prefix of their own. They write
`00-catalogue.json` and `00-triage.json` ahead of the `manifest.json` and
`00-inputs/` that `intake` mints once gate 0 has passed, so the numbering
stays intake's — `intake` is what fixes the run's identity, and neither
`survey` nor `triage` has minted one yet. `intake --input` still works
unchanged for anyone who would rather hand-pick the inputs directly, with no
corpus, no catalogue, no triage record, and no gate 0.

### Reconcile is one logical step, engineered as substeps

Rows `01b` through `01i` are one job: merge every extractor's claims into one
world model. It was one stage and one dispatch, and it was split because that
dispatch had to hold every claim in view, plan an eight-collection merge, and
only then write its first byte — the shape most exposed to a gateway that
closes a stream which has produced nothing for long enough, regardless of how
long a *producing* stream is allowed to run.

Every pass still reads all of `01-claims/`, so the barrier property is
untouched: **the split is on output, not on claims.** A contradiction between
two inputs is still visible to the pass that records it, which is the whole
reason a barrier exists here at all.

They are separate stages rather than one skill branching on a slice id for
three reasons, all of which the design leans on:

- **Per-pass repair.** A gate failure names one pass's artifact, and the
  orchestrator's one bounded retry re-dispatches only that pass.
- **Per-pass model and effort.** `manifest.stages` records model, effort and
  skill digest per stage, so a think-heavy pass can carry a different budget
  from a mechanical one, on the record.
- **Per-pass observability.** `check-skills` binds one skill file to one stage
  name, so each pass's judgment is a file a reader can hold to its own
  contract, and each pass's output is a file a human can read at gate 1.

The last pass, `reconcile-seal`, is code rather than a prompt for the reason
`emit` is: two runs with identical partials must produce a byte-identical world
model, or variance stops being attributable to the pass that caused it. It
joins each capability's outcome classes into that capability, and counts the
coverage denominator once. It writes nothing at all when it reports a finding,
so a partial it cannot represent faithfully is a repair rather than a
half-assembled world model that clears layer 1.

`01-world-model.json` keeps its path, schema and shape, so nothing downstream
of the seal can tell that the file was assembled by eight passes rather than
written by one.

### The human gates

- **Gate 0, after triage** — decides what the run can ever know.
- **Gate 1, after the reconcile seal** — highest leverage in the pipeline: every
  downstream stage inherits an error made here, and it is the one artifact
  small enough to read carefully.
- **Gate 2, after the coverage loop** — the cost gate, reviewing the scenario
  list and coverage report before per-scenario fan-out is paid for.
- **Gate 3, after challenge** — skim rejects and re-seeds; mostly
  informational.

**Gate 0 is different in kind from gates 1 through 3.** Gates 1–3 review a
judgment made from evidence already in the run, so a human overturning one of
them corrects an inference about the target. Gate 0 decides what the run can
ever know: nothing downstream of `intake` reads the corpus again, so a
candidate `rb-triage` declines is gone as completely as if the corpus never
contained it. That is why triage cannot also hold its own gate — the same
party selecting the inputs and ratifying the selection would make the whole
run unfalsifiable.

Gates 1 through 3 are skippable with `--no-gate`, and have to be: five
identical pipelines cannot be run if a human intervenes in each. Gate 0 is not
the orchestrator's to skip, because the orchestrator never holds it — `--no-gate`
is an argument to the *orchestrator skill's invocation*, not a `rubrica` flag.
The gates live in the prompt and no code enforces them. A prompt-level flag
can be forgotten in a way a CLI flag cannot; that is a known cost, accepted
because enforcing the gates in code would mean the orchestrator stops being a
skill, which is the thing being tested.

## The 02↔03 loop

`propose` and `score` form a loop. `propose` targets the holes the coverage
report names; `score` recomputes coverage against the frozen denominator and
returns a verdict — `continue`, `converged`, `halted_no_progress`, or
`halted_round_cap`. `score` *computes* that verdict; only the orchestrator acts
on it. The loop is bounded by `max_rounds` in the manifest.

## Fan-out means isolation, not just parallelism

An extract subagent sees one input file, so it cannot smuggle a sibling's
conclusion into its claims. A `reconcile-contradict` member is the deliberate
exception that proves the rule: it is fanned out over *subjects* rather than
over inputs, and inside its own subject it reads every claim from every input,
because comparing two inputs is the one thing no input-scoped member could do.
An instantiate subagent builds one seed world
without knowing what the other tests cover. That isolation is the point: it is
what makes a contradiction between two inputs something the pipeline *records*
rather than something a single reader silently resolves.

## What each skill contributes

A skill is a prompt file, not code. The judgment lives in the prose; the
contract block above it is what keeps that prose from drifting away from the
artifacts.

| Skill | Job |
|---|---|
| `rb-triage` | Rules on every candidate in the catalogue against the declared objective — admit, or decline with a reason — and states what the admitted set cannot cover. Every decline is a fact about the target that no later stage can recover, since nothing downstream reads the corpus. |
| `rb-extract` | Turns one input artifact into atomic, evidence-backed claims. Every claim carries a locator and an honest `derivation` — *stated*, *inferred*, or *reverse_engineered* — so "the spec says this" and "I guessed from one trace" never look alike downstream. |
| `rb-reconcile-subjects` | Cuts the claim set into subjects — every claim assigned to one or more of them — so the contradiction sweep has a slice to fan out over. A cover, not a partition: over-assignment is instructed, because a claim in no subject is never compared against anything. |
| `rb-reconcile-contradict` | One member per subject. Compares claim against claim inside its own subject, across every input file, and records what disagrees — `unresolved` where nothing in the claims breaks the tie. Every resolution binds the passes below it. |
| `rb-reconcile-capabilities` | Declares the capabilities, each with its params, its `binding` and the claims it rests on. No outcome classes: they are the next pass's output, quantified over this list. |
| `rb-reconcile-outcomes` | For every capability in `01-capabilities.json`, enumerates its outcome classes — success, empty, not_found, error, underspecified — harvested from claims of every `kind`, not only the ones already tagged `outcome_class`. |
| `rb-reconcile-entities` | Models what the declared capabilities return, with `machine:` invariants only where a statement fits one of the four implemented forms and `prose:` everywhere else — a `machine:` invariant promoted from an inference fails every seed that is actually correct. |
| `rb-reconcile-goals` | Names the actors and enumerates their goals: half the frozen denominator. A later stage may only *request* an amendment, so a goal left out costs an explicit decision and a `denominator_version` bump to put back. |
| `rb-reconcile-gaps` | Records what no input says and reasoning cannot supply, naming honestly every stage each gap `blocks` — and audits every partial above it for what was modelled without evidence, which no gate can check because support is semantic. |
| `rb-propose` | Reads the world model and latest coverage report, then appends scenarios targeting real, closable holes — never rewriting or renumbering what an earlier round proposed. |
| `rb-score` | Folds the scenario pairs that are one test, promotes the rest, computes both coverage matrices against the frozen denominator, justifies every uncovered row with a hole, and computes the verdict. |
| `rb-instantiate` | Builds one scenario's seed world — **distractors first**, so no agent can pass by reading back the only matching record — then derives the oracle from that seed rather than the other way round, and records which near-misses exist so a reviewer can judge fairness. |
| `rb-challenge` | The adversary. Verifies one instance is a fair, discriminating test, reading the oracle *last* — an adversary who sees the answer first confirms almost anything. |
| `rb-emit` | A deliberately thin entry point over `rubrica emit`; writes nothing itself. `emit` is code, not a prompt, because two runs with identical stage-4 and stage-5 artifacts must produce identical suites — otherwise variance can no longer be attributed to a stage. |
| `rb-orchestrate` | The loop itself: dispatch each stage, validate, allow one bounded repair, hold gates 1 through 3, record each stage's model and skill hash, append every decision to the run's lab notebook. **Not a stage** — it declares no `stage` and no `schemas`. It dispatches `extract` through `emit` only: it never runs `survey`, never dispatches `rb-triage`, and never holds gate 0. |

`intake`, `smoke`, `survey`, and `reconcile-seal` are code, not skills. They have no `SKILL.md`
and no entry in `manifest.stages` — their absence there is not a defect.
