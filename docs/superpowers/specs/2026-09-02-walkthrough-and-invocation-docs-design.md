# Restructuring the two walkthrough documents

Date: 2026-09-02

## The problem

Two documents describe how to run Rubrica, and neither answers the question a
reader actually arrives with.

`docs/getting-started.md` walks install → survey → triage → gate 0 → intake and
stops. Everything from `extract` to `emit` — seventeen prompt stages, ten
deterministic subcommands, five fan-outs and three human gates — is delegated to
"what `docs/concepts/pipeline.md` describes, and what runs it is the next
section", and that next section names `rb-orchestrate` without showing a single
command. A reader who wants to drive the pipeline from a shell has no page that
tells them what to type.

`docs/guides/running-a-stage-by-hand.md` is a runbook for exercising *one* skill
against a toy checkpoint. It has grown, correctly, into the only place that
documents `scripts/dispatch-stage.sh` — its environment variables, its isolation
mechanisms, the two settings scopes, the sandbox probe, the re-seed path. But it
documents none of the `uv run rubrica` half of the interface, and its name
promises a narrower document than it now is.

So neither document can be read alone to run Rubrica end to end, and the
`dispatch-stage.sh` reference is filed under a title that hides it.

## What we are building

Two documents with a hard boundary between them, and one code fix the walkthrough
needs in order to be complete.

- **`docs/getting-started.md`** becomes the single linear walkthrough: install to
  `emit`, every command in order, nothing explained that is not an ordering
  concern.
- **`docs/guides/running-a-stage-by-hand.md`** is renamed to
  **`docs/guides/invoking-rubrica.md`** and becomes the reference for the two
  invocation types — `uv run rubrica …` and `scripts/dispatch-stage.sh …` — their
  arguments, their shared setup, and the isolation that only the second one gets.
- **`scripts/dispatch-stage.sh`** gains the `propose` fan-out it currently
  refuses.

**The rule that keeps them from drifting:** the walkthrough never explains an
option, and the invocation document never implies an order. Where a walkthrough
step needs a flag's semantics, it links to the invocation document or to
`docs/reference/cli.md` rather than restating them.

### The two ways to run Rubrica

Both are CLI invocations, and the walkthrough covers both. There is no third
way, and the walkthrough names no future one — a document that describes an
interface nobody can use sends readers looking for something that is not there.

1. **Step by step.** A sequence of `uv run rubrica …` commands for the
   deterministic stages and `./scripts/dispatch-stage.sh …` commands for the
   prompt stages, five of the latter wrapped in `for` loops over a fan-out's
   slice ids. Every gate is yours to read, every stage's artifact is on disk
   before the next one runs, and a failure stops where it happened. This is the
   walkthrough's main body.
2. **One step, through the orchestrator.** Hand an agent
   `src/rubrica/skills/rb-orchestrate/SKILL.md` and a run directory, and it
   dispatches `extract` through `emit` itself — gating every artifact, holding
   the round loop, holding gates 1 through 3, spending at most one repair per
   stage failure, and writing `decisions.md`. It is the only way the one
   end-to-end run on record was produced
   (`src/rubrica/skills/rb-orchestrate/exercise.md`).

**The one-step path is not `dispatch-stage.sh orchestrate`, and the walkthrough
says so rather than leaving a reader to discover it.** That script is
single-stage by construction, and two of its own mechanisms prevent it:

- Its `permissions.allow` grants `Read`/`Edit`/`Write` on the run directory,
  `Read` on the one dispatched skill's directory, and `Bash(rubrica *)`. **No
  subagent capability is granted**, so an orchestrator dispatched through it
  cannot dispatch anything.
- Its `DENY` list enumerates every sibling `rb-*` skill directory
  (`scripts/dispatch-stage.sh:352-354`), so the orchestrator could not read the
  skills it exists to hand out.

Both are deliberate — they are what makes a single-stage dispatch measure the
skill rather than the skill plus a briefing — so the one-step path is a `claude`
invocation carrying the run directory and the orchestrator skill's path, not a
`dispatch-stage.sh` one. `--no-gate` belongs in that prompt text, not on a
command line: `rb-orchestrate/SKILL.md:468` describes it as "passed to you",
making it an instruction to the orchestrator rather than a flag of any binary.

## Decisions taken before drafting

Five, each settled deliberately and each changing what gets written.

### 1. The executed-commands claim is dropped, not qualified

`getting-started.md` currently opens with "Every command below was run against
this repository before this page was committed", and hedges the three sections
that were not. A document that runs the whole pipeline cannot make that claim:
the walkthrough contains roughly twenty model dispatches, which cost money, are
non-deterministic, and have never been run as a pure CLI sequence in the current
pipeline shape — the one end-to-end record predates the staged reconcile and
shows `reconcile` as a single stage.

The sentence goes, and no per-block provenance markers replace it. The page is a
prescription derived from the code, and it does not claim to be a transcript.

**This does not license unverified commands.** Every command that does not
dispatch a model is still executed before the page is committed (see
Verification), and every `jq` expression is checked against a real run directory.
What is dropped is the *claim*, not the practice behind the parts that can hold
it.

### 2. `scripts/dispatch-stage.sh` learns the `propose` fan-out

`rb-propose` is a fan-out, one member per batch, each given a `batch_id` it uses
to read its own `hole_refs` out of `02-batches/round-N.json`. The script's
slice-id `case` (`scripts/dispatch-stage.sh:85-91`) does not have a `propose`
arm, so today:

- `./scripts/dispatch-stage.sh propose "$RUN" b01` exits 2 with "propose is a
  single dispatch over everything; it takes no slice id" — which is false.
- `./scripts/dispatch-stage.sh propose "$RUN"` dispatches with no address line
  at all, so the member cannot find its batch.

A walkthrough that has to abandon its own tooling for one stage in the middle of
its only loop is the defect this restructure exists to remove, so the script is
fixed as part of this work.

### 3. `record-stage` appears in every dispatch block

Not once with a rule. The page's value is that it can be followed literally, and
`record-stage` is what makes a run explain itself afterwards — it hashes the
skill file the run actually used. Fourteen extra lines is the price of a page
that is complete.

For a fan-out it goes *after* the loop, once: `record-stage` takes a `--stage`,
never a slice.

### 4. The walkthrough stops at `emit`

`06-suite/` on disk is the end. `smoke` needs an agent roster
(`agents-0.1.json`) whose three scripted members live in `tests/toy.py`'s
`_SCRIPTS`, and building one is a detour from the sequence. `smoke` is named as
the next thing with a pointer to `docs/reference/cli.md`.

### 5. The id-field asymmetry is documented, not normalised

Writing the fan-out loops surfaced what looked like an inconsistency worth
fixing: four of the five loops read `.id` while `extract` reads
`.inputs[].artifact_id`. It was investigated as a candidate fix and **the
schemas are not changing.** The reasoning is recorded here because the same
observation will recur, and because the obvious fix is the wrong one.

**There is no exception.** There is a convention, applied consistently, with two
outliers that are not the ones the loops expose:

| Kind | Definition site | Referenced from another artifact as |
|---|---|---|
| slice | `.slices[].id` | `slice_id` (`dispositions-part`) |
| subject | `.subjects[].id` | `subject_id` (`contradictions-part`) |
| batch | `.batches[].id` | `batch_id` (`scenarios-part`) |
| scenario | `.scenarios[].id` | `scenario_id` (`expected`, `score-part`, `suite-expected`, `report`, `verdict`) |
| candidate | `.candidates[].candidate_id` — **qualified** | `candidate_id` (`adoptions`, `dispositions-part`, `triage`) |
| artifact | `.inputs[].artifact_id` — **qualified** | `artifact_id` (`claims`, `inputs-seen`, `world-model`) |

Bare `id` where a thing is defined, `<thing>_id` where another artifact points at
it — the qualified name carries the information that you are holding a foreign
key. The two definition sites that qualify anyway are the catalogue's and the
manifest's, which are the two artifacts that mint a run from outside the system.

**Normalising on bare `id` would make the trap worse.** The trap is not
schema-internal: the *dispatch address label* is always qualified (`Your
subject_id:`, `Your batch_id:`, `Your artifact_id:`), so `extract` is the only
fan-out whose label and field already agree, and it agrees *because* the manifest
qualifies. Bare `id` everywhere puts all five loops in disagreement with their
own label, and leaves `artifact_id` as the reference name in three other schemas
— the same word meaning two things.

**The direction that would remove the trap is the opposite one**, qualifying the
four definition sites so every label matches its field. Its measured cost, for
zero behavioural change: four breaking schema versions cascading into
`validate.py`'s mapping; roughly 109 sites in `src/` and 122 in `tests/`; 36 in
`tests/toy.py`, the golden-fixture builder this repository flags as higher-risk
than source because it is the model answer a skill imitates; and edits to skill
`Output` prose that models imitate — `rb-reconcile-subjects/SKILL.md:67` names
the field as `id` in the sentence that tells the stage what to write.

**So: the documents absorb the asymmetry instead of the schemas.** The
walkthrough carries the label-to-jq-path table, and
`docs/design/limitations.md` gains an entry under `## Before you file a bug
against the check layers or the CLI` — stating the convention, naming both
outliers, and recording that both normalisation directions were priced and
declined. There is no entry there today, so a reader who notices this currently
re-derives it; that is what the entry removes.

## `docs/getting-started.md`

### Shape

Every stage block has the same four parts, in the same order: one or two
sentences on what the stage does, the command, the gate that checks it, and —
where a model was dispatched — the `record-stage` that records it. No block
explains a flag.

`$RUN` is captured once from `survey`'s stdout and used throughout, as the
current page already does: `survey` prints the run directory and nothing else,
and `ls -d "$RUNS"/run-*` stops being unambiguous the moment a second run
exists.

### The sequence

| § | Stage | Commands |
|---|---|---|
| Install | — | `make setup`; the `PATH` note and the `uv run` fallback |
| 1 | `survey` | `rubrica survey --corpus tests/fixtures/corpus-toy --runs-dir "$RUNS" --target-name toy --target-interface mcp --objective breadth` → `$RUN`; `validate --stage survey` |
| 2 | `triage-slices` | `rubrica triage-slices --run "$RUN"`; `validate --stage triage-slices` |
| 3 | `triage-objective` | `dispatch-stage.sh triage-objective "$RUN"` (barrier, no slice); `validate`; `record-stage` deferred — see below |
| 4 | `triage-rule` | loop over `jq -r '.slices[].id' "$RUN"/00-slices.json`; `validate` |
| 5 | `triage-audit` | `dispatch-stage.sh triage-audit "$RUN"`; `validate`; `check-refs` |
| 6 | `triage-seal` | `rubrica triage-seal --run "$RUN"`; `validate`; `check-refs` |
| 7 | **gate 0** | `rubrica gate-brief --run "$RUN" --gate 0` |
| 8 | `intake` | `rubrica intake --run "$RUN"`; `validate --stage intake`; then the three deferred triage `record-stage` calls |
| 9 | `extract` | loop over `jq -r '.inputs[].artifact_id' "$RUN"/manifest.json`; `validate`; `record-stage` |
| 10 | `reconcile-subjects` | barrier; `validate`; `check-refs`; `record-stage` |
| 11 | `reconcile-contradict` | loop over `jq -r '.subjects[].id' "$RUN"/01-subjects.json`; `check-refs` **after every member**; `record-stage` |
| 12 | the six remaining passes | `reconcile-capabilities`, `-outcomes`, `-entities`, `-goals`, `-gaps`, `-services` in `paths.STAGES` order, each with `validate`, `check-refs`, `record-stage` |
| 13 | `synthesise-interfaces` | `rubrica synthesise-interfaces --run "$RUN"`; `validate`; `check-refs` |
| 14 | `reconcile-seal` | `rubrica reconcile-seal --run "$RUN"`; `validate`; `check-refs`; `rubrica claim-utilisation --run "$RUN"` |
| 15 | **gate 1** | `gate-brief --gate 1`; `rubrica target-brief` named as the page written for the target's owners |
| 16 | the round loop | `propose-batches --round N` → loop `propose` over `jq -r '.batches[].id' "$RUN"/02-batches/round-N.json` → `propose-seal` → `dispatch-stage.sh score` → `score-seal --round N` → read `jq -r '.verdict' "$RUN"/03-score/round-N.json` and branch |
| 17 | **gate 2** | `gate-brief --gate 2` |
| 18 | `instantiate` | loop over `jq -r '.scenarios[] \| select(.status=="active") \| .id' "$RUN"/02-scenarios.json`; `validate`; `check-refs`; `record-stage` |
| 19 | `challenge` | loop over the same set; `check-refs` **after every member**; `record-stage` |
| 20 | **gate 3** | `gate-brief --gate 3` |
| 21 | `emit` | `rubrica emit --run "$RUN"`; `validate`; `check-refs`; `record-stage`; what lands in `06-suite/`; `rubrica run-summary` |

Then three closing sections:

- **The hand-picked shortcut** — `intake --input` reaching the same state as §8
  with no corpus, no catalogue, no triage record and no gate 0. Kept from the
  current page.
- **The same run in one step** — `rb-orchestrate` over a run that has reached
  §8: the `claude` invocation that starts it, what it does and does not do (it
  never runs `survey`, never dispatches a triage pass, never holds gate 0), that
  it holds gates 1 through 3 itself, and why `dispatch-stage.sh` is not the
  vehicle. This is way 2, so it is a peer of the sequence above rather than an
  appendix to it.
- **Where to go next** — the current list, with the renamed guide.

### The reconcile band stays eight blocks

§§10–12 are eight near-identical sections, and compressing the six non-fan-out
passes into one `for` loop was considered and **declined.** Each pass has its own
`validate --stage`, its own `check-refs`, and its own `record-stage` entry
carrying that pass's model and effort — which is the whole reason the band is
eight stages rather than one skill branching on a slice id. A loop would either
drop those per-pass lines or hide them inside a body that no longer reads as a
sequence, and the walkthrough's one job is to be accurate about the order.

Repetition on the page is the honest shape of a pipeline that really does gate
eight times.

### Facts the sequence depends on, all verified

Verified against a toy run built to `challenge` and one built to
`triage-slices` with `slice_cap=4096`.

**The fan-out id fields are not named after the address they fill.** This is the
trap the walkthrough exists to remove, and it would have shipped silently:

| Fan-out | Prompt line | jq path |
|---|---|---|
| `extract` | `Your artifact_id:` | `.inputs[].artifact_id` — the manifest is the exception |
| `triage-rule` | `Your slice_id:` | `.slices[].id` |
| `reconcile-contradict` | `Your subject_id:` | `.subjects[].id` |
| `propose` | `Your batch_id:` | `.batches[].id` |
| `instantiate`, `challenge` | `Your scenario_id:` | `.scenarios[] \| select(.status=="active") \| .id` |

`jq -r '.subjects[].subject_id'` prints six `null`s against the toy world.
Every loop reads `.id` except `extract`, whose source is `manifest.json`.

Other confirmed shapes:

- `00-slices.json` (the map) and `00-slices/<id>.json` (the shards) coexist; the
  toy corpus is a single slice at the default cap, so the walkthrough's loop is
  correct but degenerate there.
- `status` on a scenario is one of `proposed`, `active`, `duplicate`,
  `rejected` (`src/rubrica/schema/scenarios-0.1.json:52`). `active` is the
  instantiate set; the toy world has four active and one duplicate.
- `04-instances/` holds exactly the active scenarios, so `challenge` can loop
  over either that directory or the same `select`.
- `03-score/round-N.json` carries `verdict`, one of `continue`, `converged`,
  `halted_no_progress`, `halted_round_cap`. The toy round 1 is `converged`.
- `gate-brief --gate` takes `{0,1,2,3}`; `record-stage` takes `--run --stage
  --model --effort {low,medium,high,xhigh,max} --skill PATH`.
- `validate --stage` accepts every one of `paths.STAGES`, so a walkthrough block
  can always name its own stage.

**`record-stage` for the four triage passes runs late, and the walkthrough says
so where it happens rather than in a footnote.** `record-stage` merges into
`manifest.json`, and a run minted by `survey` has no manifest until `intake
--run` writes it after gate 0. So §§3–5 note the deferral and §8 carries the
three calls -- `triage-objective`, `triage-rule` and `triage-audit`. `triage-slices`
and `triage-seal` are code, have no skill file, and take no `record-stage` entry
at all; their absence from `manifest.stages` is not a finding. This is already documented in the current guide; the walkthrough
inherits it.

## `docs/guides/invoking-rubrica.md`

Renamed from `docs/guides/running-a-stage-by-hand.md`. **Nothing in the current
file is deleted** — every measurement, every ruling, every "this was tried and
broke" paragraph survives. It gains the `uv run rubrica` half and a shared-setup
section, and its material is regrouped so a reader looking up an environment
variable does not have to read a runbook to find it.

| § | Content | Source |
|---|---|---|
| 1 | The two invocation types, and a table of stage → code or prompt → invocation | new |
| 2 | Setup they share: venv on `PATH` vs. the `uv run` prefix; the exit-code contract (`0`/`1`/`2`) and how to route each; the four `RUBRICA_*` overrides (`SCHEMA_DIR`, `SKILLS_DIR`, `SUITE_DIR`, `LIVE`) | new, plus the `PATH` measurement from current §7 |
| 3 | `uv run rubrica …`: the `--run`/`--stage`/`--round` conventions, stdout vs. findings, pointer to `docs/reference/cli.md` per subcommand | new |
| 4 | `scripts/dispatch-stage.sh …`: `claude` and `jq` as prerequisites `make setup` does not install; positional arguments; the slice-id table **including the new `propose` row and the `id`-vs-address note**; the full environment table (`MODEL`, `EFFORT`, `LAB`, `BUDGET`, `NO_SANDBOX`, `REQUIRE_SANDBOX`, `RESEED`, `REJECT`, `FINDINGS_FILE`, `PRINT_SETTINGS`, `PRINT_TRANSCRIPT`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`); transcripts, their never-overwrite naming, and `scripts/audit-reads.sh`; the closing summary's `cost` line and the two transcript shapes that report `unread` | current §7, regrouped and completed from the script's own header |
| 5 | What a dispatch carries: the three things, the slice id as an address not context, the two things an orchestrator may append | current §§1–2 |
| 6 | Isolation: why it is not tidiness; the three mechanisms; the two settings scopes and the measurement behind them; the sandbox probe and both observations; never deny a run path `check-refs` reads | current §7, kept whole |
| 7 | Exercising one stage against a checkpoint: the prompt template, the `upto=` table, `toy-run-to.py` | current §§2–3 |
| 8 | Verification, reading a failure, the live exercise suite | current §§4–6 |
| 9 | Re-dispatching a `re-seed` | current §8 |

The renamed file also gains one cross-reference the current one cannot have: §1
points at `docs/getting-started.md` for the order, closing the loop the boundary
rule opens.

## The code change

`scripts/dispatch-stage.sh`, one arm in the slice-id `case`:

```sh
case "$STAGE" in
  extract)               SLICE_LINE="Your artifact_id:  $SLICE" ;;
  reconcile-contradict)  SLICE_LINE="Your subject_id:   $SLICE" ;;
  propose)               SLICE_LINE="Your batch_id:     $SLICE" ;;
  instantiate|challenge) SLICE_LINE="Your scenario_id:  $SLICE" ;;
  triage-rule)           SLICE_LINE="Your slice_id:     $SLICE" ;;
  *) echo "$STAGE is a single dispatch over everything; it takes no slice id" >&2; exit 2 ;;
esac
```

The label is `Your batch_id:`, matching `rb-propose`'s contract and the §2
prompt template, and the column alignment matches the existing arms.

A test in `tests/unit/test_dispatch_harness.py` asserts it, using
`RUBRICA_PRINT_SETTINGS=1` to read the composed prompt without dispatching —
the mechanism the existing tests in that module already use. **Measured in both
directions before it is committed:** it fails against the unpatched script, and
it survives a meaning-preserving reword of the arm's spacing.

## Files touched

**Rewritten:**

- `docs/getting-started.md`
- `docs/guides/running-a-stage-by-hand.md` → `docs/guides/invoking-rubrica.md`
  (`git mv`, then rewritten)

**Modified for the rename** — every user-facing pointer, `docs/superpowers/`
excluded because it is recorded history and a record is falsified by a later
edit:

- `docs/README.md` — **both** index lines, since both documents' answers change.
  The current `getting-started.md` line asks "How do I get from a clone of this
  repository to a minted run I can inspect?", which describes the page's old
  scope; it becomes a question about reaching an emitted suite. The guide's line
  asks "How do I dispatch one skill for real…"; it becomes a question about the
  two ways to invoke a stage, their arguments, and the setup they share. The
  index groups by the question each document answers, so leaving either line as
  it stands would file the new documents under the old ones' questions
- `README.md` (3 references)
- `CLAUDE.md` (1)
- `docs/concepts/artifact-contract.md` (1)
- `docs/reference/artifacts.md` (1)
- `docs/design/limitations.md` (1 reference, plus the new id-naming entry from
  decision 5)
- `scripts/dispatch-stage.sh` (2 header comments, plus the `case` arm)
- `tests/unit/test_refusals_live.py` (2, one of them inside a skip message)
- `tests/unit/test_toy_fixture.py` (1, a comment citing "the table")

**Modified for the code change:**

- `tests/unit/test_dispatch_harness.py`

## Verification

1. `make test`, `make check`, `uv run rubrica check-skills` — the three gates.
2. **Every non-dispatch command in the walkthrough executed** against a scratch
   runs directory: `survey`, `triage-slices`, `triage-seal`, `intake`,
   `synthesise-interfaces`, `reconcile-seal`, `claim-utilisation`,
   `propose-batches`, `propose-seal`, `score-seal`, `emit`, `run-summary`, every
   `validate --stage`, every `check-refs`, every `gate-brief --gate`. Where a
   command needs artifacts a dispatch would have written, it runs against a
   `tests/toy.py` checkpoint.
3. **Every `jq` expression executed** against a real run directory, and its
   output checked to be the id set the loop needs — the `.subjects[].id` trap is
   what this step exists to catch.
4. `RUBRICA_PRINT_SETTINGS=1 ./scripts/dispatch-stage.sh propose "$RUN" b01`
   composes a prompt whose address line reads `Your batch_id: b01`.
5. The old path grepped to zero outside `docs/superpowers/`, in both
   directions — the new path resolves everywhere it is now cited, and no file
   still names the old one. Both greps run, because a one-directional sweep is
   how a stale pointer survives.
6. `tests/unit/test_docs_accuracy.py` passes: both documents are in
   `_user_facing()`, so no hand-typed test count, no heading that counts
   something that grows, and no citation of `docs/superpowers/`.

   **The heading predicate is the one that will actually bite while drafting.**
   `_COUNTED_HEADING` fires on a heading carrying a number — digits or the words
   `one` through `twenty` — followed within one word by `stages`, `skills`,
   `subcommands` or `gates`. So `## The three human gates` fails and
   `## The human gates` passes; `### 4. Triage rules on every candidate` is
   safe, because the numeral is followed by `.` rather than whitespace. Numbers
   in body prose are not checked, only headings, and fenced blocks are blanked
   before the check — but a count typed into prose still goes stale, so the
   drafts keep them out of both.

## Out of scope

- **Running the pipeline end to end for real.** Decision 1 settles this: the
  walkthrough is a prescription, and producing a transcript is a separate,
  costed exercise.
- **An `exercise.md` for any `triage-*` or `reconcile-*` pass.** Still owed,
  still recorded in `docs/design/limitations.md`, unaffected by this work.
- **Any change to a `SKILL.md`.** The contracts are correct; only the harness
  and the documents around them change.
- **Any id-field rename, in either direction.** Decision 5 prices both and
  declines both. No schema version is bumped by this work.
