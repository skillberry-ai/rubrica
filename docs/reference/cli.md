# CLI reference

Every `rubrica` subcommand, one section each, written from its own `--help`
output rather than from memory. Commands below assume the venv is on your
`PATH` (`make setup` creates it); otherwise prefix each with `uv run`.

Exit codes are the same across every subcommand:
`0` clean, `1` findings (one per line on stdout), `2` usage error or an
unreadable/misconfigured run. See
[`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md) for
what that split means and why it matters to a caller — this document does not
restate it.

## Minting a run

### `rubrica survey`

Walks a corpus, digests each candidate, and mints a run — `intake`'s
counterpart for the corpus path. Writes `00-catalogue.json` rather than a
manifest, because nothing has been admitted yet; there is nothing to extract
from until `rb-triage` rules on the catalogue and a human holds gate 0.

Required: `--corpus PATH` (repeatable), `--runs-dir RUNS_DIR`, `--target-name
TARGET_NAME`, `--target-interface TARGET_INTERFACE`, `--objective
{breadth,depth}`.

Optional: `--objective-note OBJECTIVE_NOTE`, `--scope-note SCOPE_NOTE`,
`--exclude GLOB` (repeatable), `--max-rounds MAX_ROUNDS`, `--max-scenarios
MAX_SCENARIOS`, `--max-candidates MAX_CANDIDATES`, `--max-catalogue-bytes
MAX_CATALOGUE_BYTES`.

Prints the new run directory.

```bash
rubrica survey \
  --corpus path/to/corpus \
  --runs-dir runs \
  --target-name aap2 \
  --target-interface mcp \
  --objective breadth
# runs/run-20260806-123005
```

### `rubrica intake`

Mints a run directly from hand-picked inputs, or admits whatever a triage
record at an existing survey run already ruled on. `--input` and `--run` are
mutually exclusive.

`--input PATH` (repeatable) path: also takes `--runs-dir RUNS_DIR`,
`--target-name TARGET_NAME`, `--target-interface TARGET_INTERFACE`, and the
optional `--max-rounds MAX_ROUNDS` / `--max-scenarios MAX_SCENARIOS` (default
2 and 128). No corpus, no catalogue, no triage record, no gate 0.

`--run PATH` path: mints the manifest from the catalogue and triage record at
that run instead — the five flags above are illegal alongside it, since the
catalogue already carries their equivalents.

Prints the run directory on success; on the `--run` path, a non-empty result
from checking the triage record against the catalogue prints as findings on
exit 1 instead.

```bash
rubrica intake \
  --input path/to/api.json \
  --input path/to/schema.json \
  --runs-dir runs \
  --target-name aap2 \
  --target-interface mcp \
  --max-rounds 2 \
  --max-scenarios 128
# runs/run-20260806-123005

# Once 00-triage.json exists and human gate 0 has held:
rubrica intake --run runs/run-20260806-123005
```

### `rubrica adopt-projection`

Admits a manufactured artifact into the catalogue structurally, without
touching the corpus or the run's identity.

Required: `--run RUN`, `--projection ID`, `--file PATH`. Optional:
`--check-only` (checks acceptance without writing).

Prints `structural acceptance passed; the prose criterion is still a human's
to judge` on a clean pass, or findings on exit 1 — structural acceptance is
necessary and never sufficient; whether the file means what the projection
asked for is still a human's call.

```bash
rubrica adopt-projection --run runs/run-20260806-123005 \
  --projection proj-001 --file path/to/manufactured-tool-schema.json
```

## Checking

### `rubrica validate`

Layer 1: schema-validates one stage's output.

Required: `--run RUN`, `--stage`, one of `survey`, `triage`, `intake`,
`extract`, `reconcile-subjects`, `reconcile-contradict`,
`reconcile-capabilities`, `reconcile-outcomes`, `reconcile-entities`,
`reconcile-goals`, `reconcile-gaps`, `reconcile-seal`, `propose`, `score`,
`instantiate`, `challenge`, `emit`, `smoke` — `paths.STAGES`, in order.

Exits 0 clean, or 1 with one finding per line on stdout.

```bash
rubrica validate --run runs/run-20260806-123005 --stage reconcile-seal
```

### `rubrica check-refs`

Layer 2: cross-artifact references, seed conformance, reachability, and
invariant evaluation over the whole run so far.

Required: `--run RUN`. Exits 0 clean, or 1 with findings.

```bash
rubrica check-refs --run runs/run-20260806-123005
```

### `rubrica check-skills`

Checks every skill's `## Contract` block against the code that owns each
name it declares — `reads`/`writes` against `paths.RunPaths` attributes,
`schemas` against `validate.STAGE_ARTIFACTS`, `invokes` against real `rubrica`
subcommands.

Optional: `--skills-dir PATH` (defaults to the packaged skills directory).

Takes no `--run`: it checks the skill files themselves, not a run's output.
Exits 0 clean, or 1 with findings.

```bash
rubrica check-skills
```

## Assembling the world model

### `rubrica reconcile-seal`

Assembles the reconcile partials into `01-world-model.json`: it folds
`01-outcomes.json` back into each capability's `outcome_classes` — the
capabilities partial omits that property, because a schema cannot express
"`capability` minus one property" under `additionalProperties: false` — joins the
per-subject contradiction parts into one list, takes `target` from the manifest
rather than from any partial, and computes the coverage `denominator`.

Required: `--run RUN`. Optional: `--denominator-version N` (default `1`), passed
rather than inferred so an amendment to the frozen goal list costs an explicit
orchestrator decision recorded in `decisions.md` instead of a number the command
quietly incremented.

Reads `manifest.json`, the five singleton partials — `01-capabilities.json`,
`01-outcomes.json`, `01-entities.json`, `01-goals.json`, `01-gaps.json` — and
every `01-contradictions/*.json`. It does **not** read `01-subjects.json`: the
world model has no subjects field, so the cover is an input to the contradiction
passes and to `check-refs`, not to the seal. Writes `01-world-model.json` and
prints its path.

Code rather than a prompt, for the reason `emit` is code: two runs with identical
partials must produce a byte-identical world model, or variance can no longer be
attributed to a pass. A code step also streams nothing, so it cannot be killed by
the idle reset that splitting reconcile into passes exists to avoid, however large
the assembled model gets.

**It assembles; it does not check.** Cross-artifact checking is layer 2, so run
`rubrica check-refs` afterwards. What this command does report is the narrow class
where assembly cannot faithfully represent what it was handed, and it is exactly
four items long:

1. an artifact absent, unparseable, or not a JSON object carrying its payload keys
   (`capabilities`, `outcomes`, `entities`, `actors` and `goals`, `gaps`,
   `contradictions`, and `target` for the manifest);
2. a declared capability with no outcome classes;
3. an outcome record naming a capability nobody declared;
4. two outcome records for one capability.

It **writes nothing at all** when it reports any of them, because a half-assembled
world model would clear layer 1 for the collections it did manage to fill.

Presence, parseability and payload-key presence are the whole of item 1 — not the
*type* of what a payload key holds. `{"capabilities": 5}` still reaches the
assembly and raises out of it, by design: layer 1 is the rejection point for a
wrong-typed value (`rubrica validate --stage reconcile-<pass>`, one schema per
partial),
and duplicating that here would put one rule in two places with two messages.

Items 2 and 3 overlap layer 2's `check_outcomes` on purpose — item 2 is its first
clause (every declared capability has a record), item 3 its second (every record
names a declared capability). That check owns the after-the-fact report and runs
over any run, including one that was never sealed; the branches here refuse
**before the write**, because assembly is perfectly possible in both cases: the
entry is simply dropped, and the world model then reaches gate 1 missing cells an
artifact declared, agreeing with its own recomputed `denominator` and reading as
coherent.

Item 4 overlaps **nothing**, in any layer, which is the strongest of the four
reasons to refuse rather than drop: `check_outcomes` compares *sets* of capability
ids, so two records for one capability collapse to one member and neither
direction of that comparison sees anything. The seal is the only place a duplicate
outcomes record is ever caught.

Exits 0 clean, 1 with one finding per line on stdout, or 2 if the run directory
itself cannot be read. A missing **singleton** partial is a repairable stage defect
and so is a 1, naming that partial; several missing ones are listed with the
earliest pass first, the one a repair should start from. An absent
`01-contradictions/` directory is *not* reported here — it assembles to an empty
`contradictions` list and exits 0, because the seal cannot tell "no contradictions
were found" from "no pass ran". Whether every subject in `01-subjects.json` has a
part is a question about the cover, which layer 2's `check_contradiction_parts`
owns — not the seal.

```bash
rubrica reconcile-seal --run runs/run-20260806-123005
```

## Feeding a stage

### `rubrica dedupe-candidates`

Proposes candidate duplicate scenario pairs as JSON for the scoring stage to
weigh — it never decides which pair is actually a duplicate.

Required: `--run RUN`. Prints a JSON array of candidate pairs on stdout.

```bash
rubrica dedupe-candidates --run runs/run-20260806-123005
```

## The orchestrator's writers

`manifest.stages` and `decisions.md` are declared by the design and have no
other writer; `rb-orchestrate` is their only caller in a real run.

### `rubrica record-stage`

Records a stage's model, effort, and skill hash into `manifest.json`.

Required: `--run RUN`, `--stage` (same eleven choices as `validate` above),
`--model MODEL`, `--effort {low,medium,high,xhigh,max}`, `--skill PATH`.

The digest is computed here from `--skill` rather than accepted as a string —
a caller that can pass a digest can pass the wrong one — and it hashes the
whole file, prose included. A recorded `skill_sha256` that no longer matches
the file on disk means the skill was edited after that stage ran; that is the
hook working, not a defect.

Prints the manifest path.

```bash
rubrica record-stage --run runs/run-20260806-123005 \
  --stage extract \
  --model claude-opus-5 \
  --effort medium \
  --skill src/rubrica/skills/rb-extract/SKILL.md
# runs/run-20260806-123005/manifest.json, with
#   "extract": {"model": "claude-opus-5", "effort": "medium",
#               "skill_sha256": "<sha256 of that SKILL.md>"}
# merged into manifest.stages
```

### `rubrica decide`

Appends one timestamped decision to the run's `decisions.md`.

Required: `--run RUN`, `--note NOTE`.

A note that is empty, whitespace-only, or contains a newline is refused at
exit 2: a blank entry records that a decision was made and not what it was,
and an embedded newline would corrupt a format every reader parses one line
per entry.

Prints the `decisions.md` path.

```bash
rubrica decide --run runs/run-20260806-123005 \
  --note "human gate 1: gap-bad-argument-behavior ruled non-blocking for propose as a whole"
# runs/run-20260806-123005/decisions.md, with
#   - 2026-08-10T21:58:07Z human gate 1: gap-bad-argument-behavior ruled ...
# appended
```

## The human's own reports

Three subcommands serve the human holding a gate rather than a stage. Two of
them — `gate-brief` and `claim-utilisation` — only compose or report what the
run already contains; `set-limit` is the odd one out and *writes*, changing a
manifest limit and appending its reason to `decisions.md`. None of the three
is itself a gate: none can turn a readable run into a defect finding.

### `rubrica gate-brief`

Composes the existing reports into the reading surface at one of the four
human gates: the objective verdict and grouped declines at gate 0,
utilisation and implied size at gate 1, the coverage matrix at gate 2, the
verdict tally at gate 3.

Required: `--run RUN`, `--gate {0,1,2,3}`.

Like `claim-utilisation` below, it always exits clean on a readable run — it
renders what it finds, including a stated absence, rather than raising, and
is never the thing that turns a readable run into a defect finding. A run
directory that cannot be read at all is a different failure and still exits
2, on the same shared catch every other subcommand uses.

```bash
rubrica gate-brief --run runs/run-20260806-123005 --gate 1
```

### `rubrica claim-utilisation`

Reports each input artifact's share of claims the world model actually
cites — cited count, total count, and percent, per artifact.

Required: `--run RUN`.

**A report, not a gate: it always exits clean on a readable run.** The
zero-utilisation *finding* that shares this module's arithmetic lives in
`check-refs`, never here — this command surfaces the numbers for a human to
read at gate 1, and an orchestrator reading its exit code can never mistake
data for a defect.

```bash
rubrica claim-utilisation --run runs/run-20260806-123005
```

### `rubrica set-limit`

Changes a manifest limit — `max_scenarios` most often — with the reason
recorded in `decisions.md`, so raising a ceiling is a decision on the record
rather than a silent hand-edit.

Required: `--run RUN`, `--reason REASON`. Optional: `--max-rounds
MAX_ROUNDS`, `--max-scenarios MAX_SCENARIOS` — but **at least one of the two
optional flags is required in practice.** Passing neither is a usage error
(`set_limit needs at least one of max_rounds or max_scenarios`, exit 2), since
a change with nothing to change would append a `decisions.md` line announcing
a decision that was never made. `--help` cannot show this: argparse has no way
to express "at least one of these two", so the rule lives in `set_limit` and
surfaces only when you trip it.

Prints the manifest path.

```bash
rubrica set-limit --run runs/run-20260806-123005 --max-scenarios 200 \
  --reason "breadth objective under-covered the tool surface at 128"
```

## Emitting and smoke-testing

The two commands below are **pipeline stages, not measurement tools.** `emit`
*creates* `06-suite/` and `smoke` writes `07-report.json` at the run root, and
`validate.STAGE_ARTIFACTS` names an artifact
kind for each (`suite-expected` for `emit`, `report` for `smoke`) — so the
artifact contract does expect their output, and `validate --stage emit` and
`validate --stage smoke` gate it exactly as every other stage's output is
gated. Neither is left to a human to remember, either: `rb-emit` is dispatched
as stage 6 and invokes `rubrica emit`, and `rb-orchestrate`'s own `invokes`
list names both commands — it runs `rubrica smoke` itself, since there is no
`rb-smoke` skill.

### `rubrica emit`

Compiles accepted instances into [Harbor](../concepts/glossary.md#harbor)
packages, one `06-suite/<sid>/` directory per accepted scenario.

Required: `--run RUN`.

Code rather than a prompt, deliberately: two runs with identical stage-4 and
stage-5 artifacts must produce byte-identical suites, or variance can no
longer be attributed to a stage.

Prints one task directory per emitted scenario, then findings (if any) on
exit 1.

```bash
rubrica emit --run runs/run-20260806-123005
```

### `rubrica smoke`

Runs the emitted suite against an agent roster and writes
`07-report.json`.

Required: `--run RUN`, `--agents PATH` — a human-authored roster the pipeline
itself never produces. Each entry's `command` is a script that reads the task
on stdin (or its own arguments) and writes a stream-json transcript, the same
shape `suite/verify.py` already parses. A minimal roster:

```json
{
  "schema_version": "0.1",
  "agents": [
    {
      "role": "weak_baseline",
      "model": "no-tools-stub",
      "command": ["/path/to/agents/weak_baseline.sh"],
      "notes": "no tools"
    },
    {
      "role": "under_test",
      "model": "claude-sonnet-5",
      "command": ["/path/to/agents/under_test.sh"]
    },
    {
      "role": "oracle",
      "model": "claude-sonnet-5",
      "command": ["/path/to/agents/oracle.sh"],
      "notes": "handed the reference answer"
    }
  ]
}
```

```bash
rubrica smoke --run runs/run-20260806-123005 --agents agents.json
# runs/run-20260806-123005/07-report.json
```

The report renders one of four verdicts:

- **`healthy`** — the spread looks like a real test: the weak baseline mostly
  fails, the oracle mostly passes, the agent under test lands somewhere
  between.
- **`degenerate_trivial`** — the weak baseline's mean is above the ceiling.
  The tests are too easy to discriminate anything; this indicts the *suite*,
  not the agent under test.
- **`broken_labels`** — the oracle's mean is below the floor. **This indicts
  the gold labels or the verifier, not the agent** — an agent handed the
  reference answer that still cannot pass proves the scoring path is wrong.
  `broken_labels` outranks `degenerate_trivial` when a report could earn
  either: a suite that cannot even pass its own oracle is not trustworthy
  evidence about triviality either.
- **`inconclusive`** — not enough comparable data to render a verdict at all
  (a required role never scored, or too few tasks had every role score
  together). A statement about the run, not the suite.

**`smoke` is a gate, not only a reporter.** Any verdict other than `healthy`
comes back as a finding, so the command writes `07-report.json` *and* exits 1
with that finding on stdout — it does not exit 0 and leave the bad news inside
the JSON, because "exit 0 with `broken_labels` printed in a file nobody opened"
is how a broken suite gets shipped. The repair is never a re-run of `smoke`:
`degenerate_trivial` indicts the scenarios and `broken_labels` indicts the gold
labels or the verifier.

## Measuring what a run produced

The three commands below are the measurement tools, and they are the ones
nothing in the pipeline dispatches: no stage runs them, no `invokes` list names
them, and nothing in the artifact contract expects their output. None writes
inside a numbered stage directory — `compare-gold` and `sample-for-review`
write under `measurement/`, and `diff-runs` writes nothing at all, printing its
report to stdout. Each of the first two takes a run that already has a
`06-suite/`; `diff-runs` takes two runs and compares them stage by stage.

### `rubrica compare-gold`

Measures recall and novelty against a hand-authored gold benchmark the
pipeline itself never produces.

Required: `--run RUN`, `--gold PATH`. An example two-task benchmark:

```json
{
  "schema_version": "0.1",
  "target": "aap2",
  "tasks": [
    {
      "id": "bench-001",
      "goal_id": "goal-triage",
      "hop_depth": 2,
      "capability_refs": [
        {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-success"}
      ],
      "notes": "the hand-authored triage task scn-001 should match"
    },
    {
      "id": "bench-002",
      "goal_id": "goal-triage",
      "hop_depth": 1,
      "capability_refs": [
        {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-empty"}
      ],
      "notes": "an empty-result triage task the generated suite never produced"
    }
  ]
}
```

Writes `measurement/recall.json` and `measurement/recall.md`. Prints only the
`recall.md` path on stdout, because stdout is the findings channel; the
rendered markdown goes to stderr, where a human reads it and no machine
parser is affected. Exits 1 if any gold task went unmatched.

```bash
rubrica compare-gold --run runs/run-20260806-123005 --gold gold.json
# runs/run-20260806-123005/measurement/recall.md
# [recall] .../measurement/recall.json#/unmatched_gold: 1 authored task(s) ...
```

**Recall is a smoke signal, not a metric to optimize.** With a small
denominator, one task is a large percentage swing — noise, not improvement.

### `rubrica diff-runs`

Per-stage stability across two runs.

Required: `--a A`, `--b B` (two run directories).

Prints a JSON report with a `comparable` boolean, `incomparable_reasons`, and
a per-stage `stages` breakdown. Incomparability is reported as data in the
JSON plus a `warning:` line on stderr — never mixed into stdout, since stdout
is the findings channel and a JSON document mixed with finding lines would
break a line-oriented parser.

```bash
rubrica diff-runs --a runs/run-A --b runs/run-B
# {"comparable": true, "incomparable_reasons": [], "stages": {...}}
```

### `rubrica sample-for-review`

Writes a stratified human-review packet over the emitted suite.

Required: `--run RUN`. Optional: `--size SIZE` (default 3).

Prints the packet path.

```bash
rubrica sample-for-review --run runs/run-20260806-123005
# runs/run-20260806-123005/measurement/review/packet.md
```
