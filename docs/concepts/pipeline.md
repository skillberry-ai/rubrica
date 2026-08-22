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
| — | `triage-slices` | code — partitions the catalogue into byte-bounded slices | `00-catalogue.json` only | `00-slices.json`, `00-slices/<id>.json` | validate |
| — | `triage-objective` | `rb-triage-objective` | `00-slices.json`, `00-catalogue.json` — never a candidate digest | `00-objective.json` | validate |
| — | `triage-seal` | code — assembles the triage record from the staged parts | `00-objective.json`, `00-slices.json`, `00-dispositions/<slice>.json`, `00-audit.json`, `00-adoptions.json` (optional) | `00-triage.json` | validate |
| `00` | `intake` | code | the input files you name, plus target name, interface, limits — or, on the survey path, an already-admitted `00-triage.json` | `manifest.json`, `00-inputs/<stored_as>` | validate |
| `01a` | `extract` | `rb-extract` — fan-out, one per input | the manifest, and its own one file under `00-inputs/` — never a sibling's | `01-claims/<artifact-id>.json` | validate |
| `01b` | `reconcile` | `rb-reconcile` — barrier | the manifest and every claims file | `01-world-model.json` | validate · check-refs · human gate 1 |
| `02` | `propose` | `rb-propose` | `manifest.json`, `01-world-model.json`, `02-scenarios.json`, `03-coverage/latest.json` | `02-scenarios.json` (appends this round) | validate |
| `03` | `score` | `rb-score` — barrier | `manifest.json`, `01-world-model.json`, `02-scenarios.json` | `03-coverage/round-N.json`, `03-coverage/latest.json`, `02-scenarios.json` (statuses) | validate · check-refs · human gate 2 |
| `04` | `instantiate` | `rb-instantiate` — fan-out, one per active scenario | `01-world-model.json`, `02-scenarios.json` | `04-instances/<sid>/{seed.json,expected.json,rationale.md}` | validate · check-refs |
| `05` | `challenge` | `rb-challenge` — fan-out, one per instance | the scenario and the seed — then `expected.json` last | `05-verdicts/<sid>.json` | validate · check-refs · human gate 3 |
| `06` | `emit` | `rb-emit` — wraps code | `02-scenarios.json`, `05-verdicts/`, `04-instances/*/expected.json`, `01-world-model.json` | `06-suite/<sid>/` task packages | validate · check-refs |
| `07` | `smoke` | code | the emitted suite and the agent roster | `07-report.json` | validate · check-refs |

`survey`, `triage`, `triage-slices`, `triage-objective`, and `triage-seal`
carry no `0N` prefix of their own. They write `00-catalogue.json`,
`00-triage.json` (`triage` and `triage-seal` both resolve to the identical
physical file — the sealed record's shape does not change, only which code
produces it), `00-slices.json` (plus its `00-slices/<id>.json` shards), and
`00-objective.json` ahead of the `manifest.json` and `00-inputs/` that
`intake` mints once gate 0 has passed, so the numbering stays intake's —
`intake` is what fixes the run's identity, and none of the five has minted
one yet. `intake --input` still works unchanged for anyone who would rather
hand-pick the inputs directly, with no corpus, no catalogue, no triage
record, no slices, and no gate 0.

### The human gates

- **Gate 0, after triage** — decides what the run can ever know.
- **Gate 1, after reconcile** — highest leverage in the pipeline: every
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
conclusion into its claims. An instantiate subagent builds one seed world
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
| `rb-triage-objective` | The first of the staged-triage family's prompt passes: rules whether the declared objective is supported by the corpus map — slice labels, groups, and byte/candidate counts — before any per-slice member reads a single candidate digest, and before that fan-out is ever dispatched. |
| `rb-extract` | Turns one input artifact into atomic, evidence-backed claims. Every claim carries a locator and an honest `derivation` — *stated*, *inferred*, or *reverse_engineered* — so "the spec says this" and "I guessed from one trace" never look alike downstream. |
| `rb-reconcile` | Merges every extractor's claims into one world model, *recording* contradictions and gaps rather than resolving them, and freezes the coverage denominator exactly once. |
| `rb-propose` | Reads the world model and latest coverage report, then appends scenarios targeting real, closable holes — never rewriting or renumbering what an earlier round proposed. |
| `rb-score` | Folds the scenario pairs that are one test, promotes the rest, computes both coverage matrices against the frozen denominator, justifies every uncovered row with a hole, and computes the verdict. |
| `rb-instantiate` | Builds one scenario's seed world — **distractors first**, so no agent can pass by reading back the only matching record — then derives the oracle from that seed rather than the other way round, and records which near-misses exist so a reviewer can judge fairness. |
| `rb-challenge` | The adversary. Verifies one instance is a fair, discriminating test, reading the oracle *last* — an adversary who sees the answer first confirms almost anything. |
| `rb-emit` | A deliberately thin entry point over `rubrica emit`; writes nothing itself. `emit` is code, not a prompt, because two runs with identical stage-4 and stage-5 artifacts must produce identical suites — otherwise variance can no longer be attributed to a stage. |
| `rb-orchestrate` | The loop itself: dispatch each stage, validate, allow one bounded repair, hold gates 1 through 3, record each stage's model and skill hash, append every decision to the run's lab notebook. **Not a stage** — it declares no `stage` and no `schemas`. It dispatches `extract` through `emit` only: it never runs `survey`, never dispatches `rb-triage`, and never holds gate 0. |

`intake`, `smoke`, `survey`, `triage-slices`, and `triage-seal` are code, not
skills. They have no `SKILL.md` and no entry in `manifest.stages` — their
absence there is not a defect.
