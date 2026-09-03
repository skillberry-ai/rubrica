# Getting started

Rubrica builds an agent test suite for a target system out of whatever
artifacts describe it — specs, captured trajectories, source — by chaining AI
skills over a schema-validated contract on disk. This page walks one run from a
clone of this repository to a compiled suite, in order, naming every command
that run takes.

There are two ways to run Rubrica. Both are a shell invocation, both are
covered here, and neither is the fallback for the other:

- **Stage by stage** — `rubrica …` for the stages that are code,
  `./scripts/dispatch-stage.sh …` for the stages that are a prompt, one
  dispatch at a time. That is the body of this page, and it is the only way to
  give each fan-out member its own read isolation.
- **In one step** — hand a `claude` session a run directory and
  `src/rubrica/skills/rb-orchestrate/SKILL.md`, and it dispatches `extract`
  through `emit` itself, gating each artifact and stopping at each human gate.
  That is the closing section, "The same run in one step".

**This page states the order.** Where it names a flag — `--stage`, `--round`,
`--gate` — it does so to make the order unambiguous, not to explain the flag.
What a flag means, and what environment variables exist, are
[`docs/guides/invoking-rubrica.md`](guides/invoking-rubrica.md) — §3 for
`rubrica` subcommands, §4 for `dispatch-stage.sh`, §9 for repairing a
`re-seed` — and [`docs/reference/cli.md`](reference/cli.md), which documents
every subcommand and its flags one at a time. Where a block below would need a
flag's semantics to make sense, it links one of those two rather than restating
it.

Every stage block has the same four parts in the same order: a sentence or two
on what the stage does, the command, the gate that checks it, and — wherever a
model was dispatched — the `record-stage` call that puts that dispatch on the
record.

## Install

Prerequisites: Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
make setup
export PATH="$PWD/.venv/bin:$PATH"   # or prefix every command with `uv run`
```

`make setup` runs `uv sync --python 3.13 --extra dev`, producing a `.venv` with
the `rubrica` console script and the dev dependencies installed from the
committed `uv.lock`, so your toolchain matches CI's. Every command below is
written bare (`rubrica validate …`); without that venv on `PATH` each one needs
a `uv run` prefix instead. The two are interchangeable for a command you type
and *not* for a stage you dispatch — guide §2 carries the measurement.

Two tools the package does not install are needed once the dispatched stages
start: the `claude` CLI and `jq`. `dispatch-stage.sh` checks for both before it
dispatches anything (guide §4).

## Where each fan-out loop reads its ids

A fan-out stage dispatches one member per slice, and every loop below reads its
slice ids out of an artifact. Read this table once now, because its two right
columns disagree and the disagreement is silent:

| Loop | Address handed to the member | Read the ids with |
|---|---|---|
| `triage-rule` | `Your slice_id:` | `jq -r '.slices[].id' "$RUN"/00-slices.json` |
| `extract` | `Your artifact_id:` | `jq -r '.inputs[].artifact_id' "$RUN"/manifest.json` |
| `reconcile-contradict` | `Your subject_id:` | `jq -r '.subjects[].id' "$RUN"/01-subjects.json` |
| `propose` | `Your batch_id:` | `jq -r '.batches[].id' "$RUN"/02-batches/round-N.json` |
| `instantiate`, `challenge` | `Your scenario_id:` | `jq -r '.scenarios[] \| select(.status=="active") \| .id' "$RUN"/02-scenarios.json` |

The address a member is handed is always qualified; the JSON field it is read
out of is bare `id` everywhere except `manifest.json`, so `extract` is the one
loop whose two columns agree. Getting it wrong does not fail:
`jq -r '.subjects[].subject_id'` prints one `null` per subject, so the loop
dispatches every member as `null` and the mistake only surfaces as a stage that
cannot find its slice. [`docs/design/limitations.md`](design/limitations.md)'s
entry "An id field is bare where a thing is defined and qualified where it is
referenced" carries the ruling for why neither side is being renamed.

`challenge`'s loop is the one that does not use its row: it reads `04-instances`
instead, for the reason its own block gives.

## Survey the corpus

`survey` walks a corpus of files, digests each candidate into a bounded summary
rather than a copy of its bytes, and writes `00-catalogue.json`. Nothing is
admitted yet — there is no manifest and nothing to extract from, because
nothing has been selected.

```bash
export RUNS=runs
export RUN=$(rubrica survey --corpus tests/fixtures/corpus-toy --runs-dir "$RUNS" \
  --target-name toy --target-interface mcp --objective breadth)
echo "$RUN"
rubrica validate --run "$RUN" --stage survey
```

`$RUN` is captured from stdout rather than looked up afterwards because
`survey` prints the run directory and nothing else, and `ls -d "$RUNS"/run-*`
stops being unambiguous the moment a second run exists under `$RUNS` — the
hand-picked shortcut near the end of this page mints one.

`tests/fixtures/corpus-toy` is a small fixture describing a fictional
ticket-queue tool (TicketQ: `search_tickets`, `get_ticket`,
`escalate_ticket`), mixed in with files a real survey should exclude or
decline — a `.gitignore`d file, a duplicate README, a binary logo, a
`node_modules/` entry, a lockfile, and one file that exists only to demonstrate
an unrelated permission test.

## Triage rules on every candidate

Triage is a family of passes rather than a single stage, and it brackets the
earliest gate. `triage-slices` partitions the catalogue into byte-bounded
shards. `rb-triage-objective` rules on whether the objective the survey
declared is supported by the surfaces found, and does it reading the corpus map
rather than any candidate digest. One `rb-triage-rule` dispatch per shard rules
`admit` or `decline` on every candidate in that shard. `rb-triage-audit` reads
the parts once every member has landed and states what the admitted set still
cannot cover. `triage-seal` assembles the staged parts into `00-triage.json`.

```bash
rubrica triage-slices --run "$RUN"
rubrica validate --run "$RUN" --stage triage-slices
```

```bash
./scripts/dispatch-stage.sh triage-objective "$RUN"
rubrica validate --run "$RUN" --stage triage-objective
```

```bash
for slice_id in $(jq -r '.slices[].id' "$RUN"/00-slices.json); do
  ./scripts/dispatch-stage.sh triage-rule "$RUN" "$slice_id"
done
rubrica validate --run "$RUN" --stage triage-rule
```

```bash
./scripts/dispatch-stage.sh triage-audit "$RUN"
rubrica validate --run "$RUN" --stage triage-audit
rubrica check-refs --run "$RUN"
```

```bash
rubrica triage-seal --run "$RUN"
rubrica validate --run "$RUN" --stage triage-seal
rubrica check-refs --run "$RUN"
```

None of these four blocks carries a `record-stage`, and the reason is in the
intake step below: there is no manifest for one to write into yet.

## Gate 0: what the run is allowed to know

```bash
rubrica gate-brief --run "$RUN" --gate 0
```

The brief is the whole reading surface for this gate: the objective verdict up
top, the predicted-versus-observed surface divergence, every admit and every
decline grouped by reason, the slice table, and every group the slicer split
across more than one slice. It is a report and not a gate — it exits `0` on a
readable run — so the ruling is yours, made by reading it.

**This gate is different in kind from the three below it.** Gates 1 through 3
review a judgment made from evidence that is already in the run. Gate 0 decides
what the run can ever know: nothing downstream of `intake` reads the corpus
again, so a candidate the family declines is gone as completely as if the
corpus never held it. That is also why triage does not hold its own gate — the
same party selecting the inputs and ratifying the selection would make the
whole run unfalsifiable.

Walking past `survey` without running the family is not a broken page. Run
against a survey-only run, `validate --stage triage-seal` exits `1` with `stage
'triage-seal' produced no triage artifact`, and `gate-brief --gate 0` exits `0`
saying there is no triage record yet and nothing to review until one lands.
Each is the command telling you the stage has not run.

## Intake mints the manifest

`intake --run` writes `manifest.json` and populates `00-inputs/` in place, from
the catalogue and the triage record. It is the same run directory — `intake`
does not start a new one here — and it is what fixes the run's identity, which
is why the on-disk numbering is intake's rather than the corpus path's.

```bash
rubrica intake --run "$RUN"
rubrica validate --run "$RUN" --stage intake
```

Now the three dispatched triage passes can be recorded:

```bash
# record-stage merges into manifest.json, which did not exist until now, so the
# three dispatched triage passes are recorded here rather than where they ran
for stage in triage-objective triage-rule triage-audit; do
  rubrica record-stage --run "$RUN" --stage "$stage" \
    --model sonnet --effort medium \
    --skill src/rubrica/skills/rb-$stage/SKILL.md
done
```

Substitute the model and effort you actually dispatched with. Write down what
you dispatched at the time — nothing on disk remembers it for you until this
command runs.
`triage-slices` and `triage-seal` are code, have no skill file, and take no
entry at all: their absence from `manifest.stages` is not a finding.

## Extract, one dispatch per input

`rb-extract` reads one admitted input and writes that input's claims into
`01-claims/<artifact_id>.json`. One member per input, and no member sees another
input or another member's claims.

```bash
for artifact_id in $(jq -r '.inputs[].artifact_id' "$RUN"/manifest.json); do
  ./scripts/dispatch-stage.sh extract "$RUN" "$artifact_id"
done
rubrica validate --run "$RUN" --stage extract
rubrica check-refs --run "$RUN"   # only meaningful once every member has landed
rubrica record-stage --run "$RUN" --stage extract \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-extract/SKILL.md
```

This is the one loop on the page reading a qualified field name
(`.inputs[].artifact_id`), because the manifest is one of the two artifacts that
qualify at their own definition site. The other four loops read bare `id`; the
table above is the mapping, and `limitations.md` carries the ruling.

`record-stage` goes after the loop and takes a `--stage`, never a slice — one
entry records the pass, however many members it fanned out to. Every dispatched
block below does the same.

## Reconcile: build the world model, one pass per output

The reconcile band is one logical step engineered as substeps. Every pass reads
all of `01-claims/`, so the barrier property holds throughout and a
contradiction between two inputs is still visible to the pass that records it;
the split is on *output*, one artifact per pass.

**Eight blocks follow, and they are not a loop on purpose.** Each pass has its
own `validate --stage`, its own `check-refs`, and its own `record-stage`
carrying that pass's own model and effort — which is exactly why the band is
eight stages rather than one skill branching on a slice id, since
`manifest.stages` records model, effort and skill digest per stage and that is
what lets a think-heavy pass carry a different budget from a mechanical one. A
loop would drop those lines or bury them. The repetition below is the honest
shape of a stretch of pipeline that really does gate eight times.

`reconcile-subjects` is a barrier: it reads every claim and writes the subject
cover in `01-subjects.json`, the partition the contradiction sweep then fans out
over.

```bash
./scripts/dispatch-stage.sh reconcile-subjects "$RUN"
rubrica validate --run "$RUN" --stage reconcile-subjects
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-subjects \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-subjects/SKILL.md
```

`reconcile-contradict` fans out over that cover — one member per subject, each
given only its own `subject_id` and reading that subject's claim list out of
`01-subjects.json` itself — and records where two inputs disagree, into
`01-contradictions/<subject_id>.json`.

```bash
for subject_id in $(jq -r '.subjects[].id' "$RUN"/01-subjects.json); do
  ./scripts/dispatch-stage.sh reconcile-contradict "$RUN" "$subject_id"
done
rubrica validate --run "$RUN" --stage reconcile-contradict
rubrica check-refs --run "$RUN"   # only meaningful once every member has landed
rubrica record-stage --run "$RUN" --stage reconcile-contradict \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-contradict/SKILL.md
```

That comment is load-bearing: `refs.check_contradiction_parts` reports every
missing slice from the moment the directory exists, so run mid-fan-out it names
most of the subjects — by construction, not because anything is wrong. The same
holds for `extract` above and for `challenge` later.

`reconcile-capabilities` merges the capability claims into
`01-capabilities.json`.

```bash
./scripts/dispatch-stage.sh reconcile-capabilities "$RUN"
rubrica validate --run "$RUN" --stage reconcile-capabilities
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-capabilities \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-capabilities/SKILL.md
```

`reconcile-outcomes` merges the outcome claims into `01-outcomes.json`.

```bash
./scripts/dispatch-stage.sh reconcile-outcomes "$RUN"
rubrica validate --run "$RUN" --stage reconcile-outcomes
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-outcomes \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-outcomes/SKILL.md
```

`reconcile-entities` merges the entity claims into `01-entities.json`.

```bash
./scripts/dispatch-stage.sh reconcile-entities "$RUN"
rubrica validate --run "$RUN" --stage reconcile-entities
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-entities \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-entities/SKILL.md
```

`reconcile-goals` merges the actor and goal claims into `01-goals.json`.

```bash
./scripts/dispatch-stage.sh reconcile-goals "$RUN"
rubrica validate --run "$RUN" --stage reconcile-goals
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-goals \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-goals/SKILL.md
```

`reconcile-gaps` records what the admitted inputs do not settle, into
`01-gaps.json`.

```bash
./scripts/dispatch-stage.sh reconcile-gaps "$RUN"
rubrica validate --run "$RUN" --stage reconcile-gaps
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-gaps \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-gaps/SKILL.md
```

`reconcile-services` is the band's closing barrier: it groups the target's
tools into services in `01-services.json`, which is what the next stage derives
an interface document from.

```bash
./scripts/dispatch-stage.sh reconcile-services "$RUN"
rubrica validate --run "$RUN" --stage reconcile-services
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-services \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-services/SKILL.md
```

## Derive the interfaces

`synthesise-interfaces` writes one OpenAPI document per service under
`01-interfaces/`, deriving each from the grouping the pass above judged and
reading `01-claims/` only to resolve the input schema an operation carries. It
is code rather than a prompt because a service's document is a pure function of
that grouping: two runs with identical groupings must produce byte-identical
documents. It is its own stage rather than part of the seal so that a reader who
corrects one grouping at gate 1 can re-derive that service alone.

```bash
rubrica synthesise-interfaces --run "$RUN"
rubrica validate --run "$RUN" --stage synthesise-interfaces
rubrica check-refs --run "$RUN"
```

## Seal the world model

`reconcile-seal` assembles the partials into `01-world-model.json`. It is code
for `emit`'s reason — two runs with identical partials must produce a
byte-identical world model — and nothing below the seal can tell the file was
assembled pass by pass rather than written in one dispatch.

```bash
rubrica reconcile-seal --run "$RUN"
rubrica validate --run "$RUN" --stage reconcile-seal
rubrica check-refs --run "$RUN"
rubrica claim-utilisation --run "$RUN"
```

## Gate 1: the world model

```bash
rubrica gate-brief --run "$RUN" --gate 1
rubrica target-brief --run "$RUN"   # the page written for the target's owners
```

`gate-brief --gate 1` composes the reconcile sweep, per-input claim
utilisation, per-pass read coverage, the capabilities the coverage denominator
excludes, the implied suite size, and one block per service.
`claim-utilisation` above surfaces each input's cited-over-total count for the
same reading. Both are reports, not gates: each exits `0` on a readable run,
and the ruling is yours.

`target-brief` is the odd one out and worth running here: it renders the run's
description of the *target* — not of the run — for the people who own that
target, so they can correct it. Nothing in the pipeline reads their answer; you
do.

## The propose and score round loop

Stages `02a` through `03b` are a loop bounded by the manifest's `max_rounds`,
and the whole of it repeats, not just `propose` and `score`.

`propose-seal` runs **twice per round** and takes no `--round`: once after
`propose`, so `score` has a document to read, and again after `score`, so
`instantiate` sees the statuses this round's rulings produced. It is a pure
function of the parts and the rulings and never reads its own output, so the
second run cannot disagree with the first.

```bash
ROUND=1

rubrica propose-batches --run "$RUN" --round "$ROUND"
rubrica validate --run "$RUN" --stage propose-batches

for batch_id in $(jq -r '.batches[].id' "$RUN"/02-batches/round-$ROUND.json); do
  ./scripts/dispatch-stage.sh propose "$RUN" "$batch_id"
done
rubrica validate --run "$RUN" --stage propose
rubrica check-refs --run "$RUN"   # only meaningful once every member has landed
rubrica record-stage --run "$RUN" --stage propose \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-propose/SKILL.md

rubrica propose-seal --run "$RUN"          # so score has a document to read
rubrica validate --run "$RUN" --stage propose-seal

./scripts/dispatch-stage.sh score "$RUN"
rubrica validate --run "$RUN" --stage score
rubrica record-stage --run "$RUN" --stage score \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-score/SKILL.md

rubrica propose-seal --run "$RUN"          # again, folding this round's rulings in
rubrica score-seal --run "$RUN" --round "$ROUND"
rubrica validate --run "$RUN" --stage score-seal
rubrica check-refs --run "$RUN"

jq -r '.verdict' "$RUN"/03-score/round-$ROUND.json
```

The verdict is one of `continue`, `converged`, `halted_no_progress`,
`halted_round_cap`. Only `continue` means another round: increment `ROUND` and
repeat the whole block above, `propose-batches` included. `score` computes the
verdict and `score-seal` composes the document carrying it; nothing in the
pipeline acts on it, so acting on it is the reader's job.

## Gate 2: coverage

```bash
rubrica gate-brief --run "$RUN" --gate 2
```

The coverage matrix, read once the loop has stopped. It is a report and not a
gate — it exits `0` on a readable run — so whether this coverage is worth what
instantiating it costs is a ruling you make from it.

## Instantiate, one dispatch per active scenario

`rb-instantiate` turns one scenario into a concrete instance under
`04-instances/` — a seed, a trajectory, and the oracles a suite can check.

```bash
for scenario_id in $(jq -r '.scenarios[] | select(.status=="active") | .id' \
                        "$RUN"/02-scenarios.json); do
  ./scripts/dispatch-stage.sh instantiate "$RUN" "$scenario_id"
done
rubrica validate --run "$RUN" --stage instantiate
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage instantiate \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-instantiate/SKILL.md
```

A scenario's `status` is one of `proposed`, `active`, `duplicate`, `rejected`,
and `active` is the set that gets instantiated — which is why the loop selects
on it rather than taking every id in the file.

## Challenge, one dispatch per instance

`rb-challenge` is the adversary: one dispatch per instance, each writing a
verdict into `05-verdicts/`. The loop reads the instance directory rather than
the scenario list, because the set to challenge is what `instantiate` actually
wrote.

```bash
for scenario_id in $(ls "$RUN"/04-instances); do
  ./scripts/dispatch-stage.sh challenge "$RUN" "$scenario_id"
done
rubrica validate --run "$RUN" --stage challenge
rubrica check-refs --run "$RUN"   # only meaningful once every member has landed
rubrica record-stage --run "$RUN" --stage challenge \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-challenge/SKILL.md
```

## Gate 3: the verdicts

```bash
rubrica gate-brief --run "$RUN" --gate 3
```

The verdict tally. A report again, exiting `0` whatever it says: which rejects
and which re-seeds to act on is yours to rule on, not something the pipeline
settles.

## Emit the suite

`emit` compiles the accepted instances into one package per accepted scenario
under `06-suite/`. It is code, not a prompt — two runs with identical stage-4
and stage-5 artifacts must produce byte-identical suites, or variance can no
longer be attributed to a stage — and `rb-emit` is a thin wrapper that invokes
`rubrica emit` and reports what it said.

```bash
./scripts/dispatch-stage.sh emit "$RUN"
rubrica validate --run "$RUN" --stage emit
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage emit \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-emit/SKILL.md
rubrica run-summary --run "$RUN"
```

Each `06-suite/<scenario_id>/` holds `task.toml`, `instruction.md`, `seed.json`,
`golden.json`, `provenance.md`, and a `tests/` directory with
`expected.json`, `verify.py` and `test.sh`. `emit` prints one task directory per
emitted scenario, and it owns `06-suite/`: a directory for a scenario this run
did not emit is pruned rather than left to read as current.

If `challenge` returned `re-seed` for any instance, `emit` refuses to compile
that instance and reports a finding no further stage can clear. The repair is a
single re-dispatch of `rb-instantiate` for that scenario carrying the
adversary's objection verbatim, and guide §9 is how that is done.

Running the suite is the next thing and this page does not take that detour:
`rubrica smoke --run "$RUN" --agents agents.json` needs a roster you author
yourself, which the pipeline never produces. See
[`docs/reference/cli.md`](reference/cli.md) for its shape.

## The hand-picked shortcut

`intake --input` reaches the same state the intake step above reaches, with no
corpus, no catalogue, no triage record and no gate 0 — you already decided which
files matter, so nothing reviews that decision. If you know which few files
carry the target's behaviour, this is the right call rather than a shortcut
around anything.

```bash
rubrica intake \
  --input tests/fixtures/toy/api.json \
  --input tests/fixtures/toy/notes.md \
  --input tests/fixtures/toy/trace.json \
  --runs-dir "$RUNS" \
  --target-name toy --target-interface mcp \
  --max-rounds 2 --max-scenarios 128
```

It prints the new run directory, so it is usually written `RUN=$(rubrica intake
…)`. From there, pick this page up at "Extract, one dispatch per input" — every
block from there on is unchanged.

## The same run in one step

The second way to run Rubrica, and a peer of the sequence above. Point a
`claude` session at the orchestrator skill with a run directory that has a
manifest:

```
You are the rubrica orchestrator.

Run directory: <absolute path to $RUN>
Your skill:    <absolute path>/src/rubrica/skills/rb-orchestrate/SKILL.md
```

It dispatches the prompt stages from `extract` through `emit`, gates every
artifact before the next stage sees it, holds the round loop, holds gates 1
through 3, spends at most one repair attempt per stage failure, and writes
`decisions.md` so the run explains itself afterwards. It never runs `survey`,
never dispatches a pass of the triage family, and never holds gate 0 — all
three are finished before it is handed a run at all. `rb-orchestrate` is a
skill and not a stage: it declares no `stage` and no `schemas`, so it has no
artifact of its own and no `validate --stage` to pass.

`--no-gate` goes in that prompt's text, not on any command line. It is
described in the skill as passed to the orchestrator when it was dispatched, so
it is an instruction to a model rather than a flag of any binary; it makes gates
1 through 3 skippable, which the reproducibility criterion needs: that criterion
measures this pipeline by running five identical runs and attributing the
variance, and five identical runs cannot exist if a human intervenes in each.
[`docs/concepts/pipeline.md`](concepts/pipeline.md) is where the flag is
documented, together with the cost of leaving it prompt-level.

**This is not `./scripts/dispatch-stage.sh orchestrate`.** The script takes
that invocation without complaint — `rb-orchestrate/SKILL.md` exists, so nothing
about it exits `2` — and what comes back is a crippled dispatch rather than a
refusal. That script grants no subagent capability — its
`permissions.allow` is `Read`/`Edit`/`Write` scoped to the run directory,
`Read` on one skill directory, and `Bash(rubrica *)` — and its deny list
enumerates every sibling `rb-*` skill directory one at a time. Both are
deliberate: they are what makes a single-stage dispatch measure that skill
rather than that skill plus a briefing. An orchestrator dispatched through it
could therefore neither read nor hand out the skills it exists to dispatch.
Guide §4 and §6 are the mechanics of that isolation and what only looks
enforced.

## Where to go next

- [`docs/guides/invoking-rubrica.md`](guides/invoking-rubrica.md) — the
  mechanics of both invocation types: every flag, every environment variable,
  what a dispatch is handed and what it is denied.
- [`docs/concepts/pipeline.md`](concepts/pipeline.md) — every stage, what it
  reads and writes, and the loop between propose and score.
- [`docs/reference/cli.md`](reference/cli.md) — every subcommand, its flags,
  and its own example.
- [`docs/reference/artifacts.md`](reference/artifacts.md) — every artifact
  kind, its schema, and what is worth knowing before you open one.
- [`docs/concepts/artifact-contract.md`](concepts/artifact-contract.md) — the
  one architectural rule, what a dispatch carries, and the two things an
  orchestrator may append to a *re*-dispatch.
- [`docs/concepts/glossary.md`](concepts/glossary.md) — terms used across the
  schemas and the CLI, defined from what actually produces or consumes them.
- [`docs/design/rationale.md`](design/rationale.md) — why the pipeline is
  shaped this way: the one architectural rule, the two check layers, the human
  gates.
- [`docs/design/limitations.md`](design/limitations.md) — what is known not to
  work yet, and why it was parked rather than fixed.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — the checks a change has to clear,
  and the commit conventions this repository holds to.
