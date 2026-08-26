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
from until the `triage-*` family has ruled on the catalogue and a human holds
gate 0.

Required: `--corpus PATH` (repeatable), `--runs-dir RUNS_DIR`, `--target-name
TARGET_NAME`, `--target-interface TARGET_INTERFACE`, `--objective
{breadth,depth}`.

Optional: `--objective-note OBJECTIVE_NOTE`, `--scope-note SCOPE_NOTE`,
`--exclude GLOB` (repeatable), `--max-rounds MAX_ROUNDS`, `--max-scenarios
MAX_SCENARIOS`, `--max-candidates MAX_CANDIDATES`, `--max-catalogue-bytes
MAX_CATALOGUE_BYTES`.

**`--target-interface` is free text: how the target is spoken to, in whatever
word names that.** Unlike `--objective` beside it, it carries no `choices=` and
no schema `enum` — the three artifacts that hold it (`00-catalogue.json`,
`manifest.json`, `01-world-model.json`) all type it as a non-empty string, and
`survey` rejects only a blank or a non-string. Conventional values in this
repo are `mcp`, `http`, `http-sse` and `a2a`; a value outside that set is
accepted, by design, because a target's interface is target-specific.

Its consumers are prompt stages, not code paths. No Python reads
`target.interface` after writing it — it is copied into the manifest and the
world model and validated for non-blankness, and nothing branches on its
value. It reaches models as context: `rb-triage-objective` is told that
`00-slices.json`'s `catalogue_facts` gives it `request` — "the target's name and
interface, the declared `objective`" — every `rb-triage-rule` member sees that
same `request` copied verbatim into its own shard, and the value rides in
`manifest.json` and `01-world-model.json` for whatever later pass reads them.
**So a typo here is invisible** — nothing rejects it, and the only reader is a
model that will do its best with an unfamiliar word.
Intake is code and no repair prompt can rewrite a manifest, so the value a run
is minted with is the value it keeps.

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
`--target-interface` means what it means under `survey` above, and is
free text here for the same reason.

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
touching the corpus or the run's identity. Appends the admission to
`00-adoptions.json` — never to `00-triage.json`, which this command only
reads: that record is `triage-seal`'s own derived output, and editing it
here would be erased the next time `triage-seal` runs.

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

Required: `--run RUN`, `--stage`, one of `survey`, `triage-slices`,
`triage-objective`, `triage-rule`, `triage-audit`, `triage-seal`, `intake`,
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

### `rubrica triage-slices`

Partitions a catalogue's admissible candidates into byte-bounded slices — a
reading unit, never a decision unit, so nothing here overrules a candidate a
human can still act on at gate 0. Every shard carries the run's `request` and
`policy` verbatim alongside that slice's own candidates, so a later dispatch
reading its own slice never has to seek across the catalogue for a head field.

The plan itself carries a `catalogue_facts` block for the same reason one step
further out: `request` and `policy` verbatim, the catalogue's `excluded` array
as a tally plus the paths for the exclusion reasons that embed a disputable
judgment, and every candidate's own source `bytes` as a map. That is
everything `rb-triage-objective` needs from the catalogue, so that pass does
not read the catalogue at all and its dispatch is bounded by `max_candidates`
rather than by corpus size. `canonical_bytes` sorts keys, so the block and
`run_id` both land ahead of the `slices` array.

Required: `--run RUN`.

Reports no findings, so it never exits 1: a catalogue with no admissible
candidates, one that cannot be read at all, or one missing `run_id`,
`request`, `policy`, `excluded`, or a candidate's `candidate_id` — every field
this command or a shard reads verbatim, checked before that read happens — is
exit 2, a survey defect or a broken run, not a repairable stage output. An
`excluded` that is present but is not an array is exit 2 for the same reason:
its exclusions cannot be summarised onto the plan. A single candidate too
large for any slice is exit 2 for the same reason: no splitter here can
shrink one row. Re-running replans and removes any shard the new plan no
longer names, so a human adopting a projection at gate 0 can re-mint the
plan safely.

Prints one line per slice — id, byte size, candidate count, label — then
exits 0.

```bash
rubrica triage-slices --run runs/run-20260806-123005
# s01  61234  42  corpus:0:src/handlers (42 candidates)
```

### `rubrica triage-seal`

Assembles `00-triage.json` from the staged parts — `00-objective.json`,
`00-slices.json`, every `00-dispositions/<slice>.json` part, `00-audit.json`,
and `00-adoptions.json` (optional; a missing file folds in as no
adoptions). This module assembles; it does not check — cross-artifact
checking is layer 2 and lives in `check-refs`, which runs over the sealed
record after this writes it.

Required: `--run RUN`.

Reports findings rather than raising: a part absent, unparseable, or missing
its declared payload keys; a candidate with no disposition anywhere or with
more than one; a disposition naming a candidate outside the slice its own
part rules on; no `admit` anywhere across every part and adoption; or a
`digest_insufficient`/`needs_projection` decline referencing nothing
`00-audit.json` carries. Writes nothing at all when it reports any of
them — a half-assembled record would clear layer 1 for the fields it did
manage to fill, and read as a complete triage decision to a human at gate 0.

Re-running is idempotent: nothing this reads is itself the sealed record, so
sealing an already-sealed run re-derives the identical record from the same
parts, and an adoption made since the last seal survives the next one.

Prints the path to `00-triage.json` on a clean assembly, then exits 0; on
findings, exits 1 with one finding per line and writes nothing.

```bash
rubrica triage-seal --run runs/run-20260806-123005
# runs/run-20260806-123005/00-triage.json
```

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

Required: `--run RUN`, `--stage` (the same choices as `validate` above),
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

A few subcommands serve the human holding a gate rather than a stage. Most of
them — `gate-brief`, `claim-utilisation` and `run-summary` — only compose or
report what the run already contains; `set-limit` is the odd one out and
*writes*, changing a manifest limit and appending its reason to `decisions.md`.
None of them is itself a gate: none can turn a readable run into a defect
finding.

### `rubrica gate-brief`

Composes the existing reports into the reading surface at one of the four
human gates: the objective verdict and grouped declines at gate 0; the reconcile
sweep, utilisation and implied size at gate 1; the coverage matrix at gate 2; the
verdict tally at gate 3.

Gate 0 renders more than the others because it is the one gate held before any
downstream stage has read the corpus: the objective verdict, then the
predicted-vs-observed surface divergence (`00-objective.json`'s
`predicted_surface_count` against the surfaces the disposition parts confirmed
or added), then admits by priority, declines grouped by reason code, and every
open deficiency beside the projection that would close it — and last, the
mechanics of how the fan-out read the corpus: the slice table (candidates and
bytes per slice) and every group `triage-slices` split across more than one
slice. That final summary is where the near-duplicate residue lives, and gate 0
is the only place a human can act on it.

Gate 1's brief leads with the **reconcile sweep**, and it is an aggregate rather
than a per-subject listing: how many subjects cover how many claims, how many
subjects were swept for contradictions, how many contradictions were recorded,
and — only when that count is non-zero — the tally by `resolution`, `unresolved`
first and shown even at zero. Both sweep numbers print either way: "12 subjects
swept, 0 contradictions" is a strong claim about the corpus and has to be legible
as one rather than rendered as silence. The sweep reports counts, not the
contradictions themselves, so a non-zero `unresolved` is the cue to open
`01-contradictions/`. The world model's gaps and triage's open deficiencies
follow, each listed by its id and its prose statement, since pairing them is a
human's call and no mechanical check exists for it.

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

### `rubrica run-summary`

Renders one run directory as a single self-contained HTML page: the stage spine,
the manifest's inputs and per-stage record, the objective verdict and grouped
dispositions, world-model counts and claim utilisation, the coverage
progression with both of `latest.json`'s matrices &mdash; capability cells, and
goals by hop depth &mdash; one line per scenario joined to its verdict and
emitted package, and the rule-based flags.

Required: `--run RUN`. Optional: `-o PATH` / `--output PATH` — where to write
the page, defaulting to `<run>/run-summary.html`.

**A report, not a gate: it always exits clean on a readable run.** Every
artifact it reads is optional, so a run that stopped at `extract` produces a page
saying so rather than an error. Absence and malformation are stated separately,
because the stage spine tests whether an artifact *exists* and each section tests
whether it can be *read*: an artifact that is not there renders as `Not present`,
and one that is there and unreadable — bad JSON, a document of the wrong shape,
a permission, bytes that are not UTF-8 — renders as `Present but unreadable`, with
the reason. That second case is a defect `validate --stage X` will name; it is
still exit 0 here, and a stage bolded in the spine above such a section is the two
tests disagreeing about one artifact on purpose. The output is derived rather than
an artifact: no schema, outside the numbered contract, and read by no stage.

The page is self-contained — inline CSS and JS, no external asset, no network
— so it still reads when the run is archived. Links to sibling artifacts are
relative, so the page travels with the run: written to the default destination
they resolve, and written elsewhere with `-o` the page still reads while its
links do not resolve. The page says so at the top rather than leaving an
operator to discover it, since `-o` is exactly the flag reached for on a
read-only run directory.

```bash
rubrica run-summary --run runs/run-20260806-123005
```

### `rubrica set-limit`

Changes a manifest limit — `max_scenarios` most often — with the reason
recorded in `decisions.md`, so raising a ceiling is a decision on the record
rather than a silent hand-edit.

Required: `--run RUN`, `--reason REASON`. Optional: `--max-rounds
MAX_ROUNDS`, `--max-scenarios MAX_SCENARIOS`, `--max-scenario-part-bytes
MAX_SCENARIO_PART_BYTES` — but **at least one of the optional flags is required
in practice.** Passing none of them is a usage error (`set_limit needs at least
one of max_rounds, max_scenarios or max_scenario_part_bytes`, exit 2), since
a change with nothing to change would append a `decisions.md` line announcing
a decision that was never made. `--help` cannot show this: argparse has no way
to express "at least one of these", so the rule lives in `set_limit` and
surfaces only when you trip it.

`--max-scenario-part-bytes` is the propose/score loop's per-member output
budget, and it is the one limit a manifest may omit: a third *required* key
under `limits` would have made every manifest already on disk schema-invalid,
and `diff-runs`, `run-summary` and `gate-brief` all read those. Absent means the
default the batch partition uses, so setting it here is how a smaller budget for
a probe run gets onto the record rather than into an argument nobody kept.

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
