# Rubrica

Builds agent test suites for a target system out of artifacts that describe it
(specs, captured trajectories, source), by chaining AI skills over a
schema-validated on-disk artifact contract.

**This is an experiment, and the question is falsifiable:** does prompt-carried
judgment survive a chain of artifact handoffs well enough to produce a suite
worth running? Keep that in mind when changing things — a change that makes the
pipeline more likely to produce output while making a stage's judgment less
observable is a loss, not a win.

Why the system is shaped this way, including the trade-offs made on purpose:
[`docs/design/rationale.md`](docs/design/rationale.md). What is known to be
wrong or missing, each entry with the ruling that parked it:
[`docs/design/limitations.md`](docs/design/limitations.md). **Read the second
before proposing a fix** — most "bugs you just found" are already in it, with a
ruling, and re-litigating one has cost this project two fix rounds.

## Setup and commands

Python 3.13+, `uv`. Console script `rubrica` (`rubrica.cli:main`).

```
make setup     # uv sync --python 3.13 --extra dev  (installs from uv.lock)
make test      # uv run pytest -q
make check     # ruff check + ruff format --check, no changes
make live      # RUBRICA_LIVE=1 pytest -m live  (see "Live tests" below)
make lint      # ruff check --fix
make format    # ruff format
```

`make test` green, `make check` clean, and `uv run rubrica check-skills` exiting
0 are the three gates; anything else means something broke. Do not write a test
count down anywhere — the number grows with every capability, and the prose that
used to reconcile it here, commit by commit, was still wrong by 299 when it was
deleted.

Commands in `README.md` assume the venv is on `PATH`; otherwise prefix `uv run`.
Four env overrides exist, and each is exercised by tests: `RUBRICA_SCHEMA_DIR`
(`validate.py`), `RUBRICA_SKILLS_DIR` (`skills.py`), `RUBRICA_SUITE_DIR`
(`emit.py`), and `RUBRICA_LIVE` (`tests/conftest.py`). Prefer them over editing
repo files when probing behaviour.

## The one architectural rule

**Artifacts on disk are the only channel between stages.** A stage is dispatched
with exactly three things — the run directory, the stage name, and its skill file
path. No conversational context is threaded through. If a stage needs a fact it
reads it from an artifact, or it does not have it.

Fan-out members get a fourth thing: the id of their own slice (`artifact_id`,
`subject_id`, `batch_id`, `scenario_id`). Never a sibling's, and never the
slice's *contents* — `rb-reconcile-contradict` gets a `subject_id` and reads that
subject's claim list out of `01-subjects.json` itself, and `rb-propose` gets a
`batch_id` and reads that batch's `hole_refs` out of `02-batches/round-N.json`.

The orchestrator may append exactly two things to a re-dispatch, both verbatim
machine text, never paraphrased: a repair's gate findings, and a re-seed's
verdict fields. A paraphrase is the orchestrator's conclusion wearing a
finding's clothes.

## The stages and their skills

`paths.STAGES` is the ordering and the on-disk numbering. `survey` and the
`triage-*` family precede `intake` and bracket the earliest gate:

| Dir | Stage | Runs as | Gate |
|---|---|---|---|
| — | survey | code — walks a corpus, writes `00-catalogue.json` | validate |
| — | triage-slices | code — partitions the catalogue, writes `00-slices.json` and its shards | validate |
| — | triage-objective | `rb-triage-objective` — barrier, reads the corpus map, never a digest | validate |
| — | triage-rule | `rb-triage-rule` — fan-out, one per slice | validate |
| — | triage-audit | `rb-triage-audit` — barrier, reads the parts, never a candidate | validate · check-refs |
| — | triage-seal | code — assembles `00-triage.json` from the staged parts | validate · **human gate 0** |
| `00` | intake | code | validate |
| `01a` | extract | `rb-extract` — fan-out, one per input | validate · check-refs |
| `01b` | reconcile-subjects | `rb-reconcile-subjects` — barrier | validate · check-refs |
| `01c` | reconcile-contradict | `rb-reconcile-contradict` — fan-out, one per subject | validate · check-refs |
| `01d` | reconcile-capabilities | `rb-reconcile-capabilities` | validate · check-refs |
| `01e` | reconcile-outcomes | `rb-reconcile-outcomes` | validate · check-refs |
| `01f` | reconcile-entities | `rb-reconcile-entities` | validate · check-refs |
| `01g` | reconcile-goals | `rb-reconcile-goals` | validate · check-refs |
| `01h` | reconcile-gaps | `rb-reconcile-gaps` | validate · check-refs |
| `01i` | reconcile-services | `rb-reconcile-services` — barrier | validate · check-refs |
| `01j` | synthesise-interfaces | code — derives one OpenAPI document per service | validate · check-refs |
| `01k` | reconcile-seal | code — `rubrica reconcile-seal` assembles the partials | validate · check-refs · **human gate 1** |
| `02a` | propose-batches | code — partitions the round's closable holes | validate |
| `02b` | propose | `rb-propose` — fan-out, one per batch | validate |
| `02c` | propose-seal | code — assembles the parts into `02-scenarios.json` | validate |
| `03a` | score | `rb-score` — barrier | validate |
| `03b` | score-seal | code — computes the matrices, composes the report | validate · check-refs · **human gate 2** |
| `04` | instantiate | `rb-instantiate` — fan-out, one per active scenario | validate · check-refs |
| `05` | challenge | `rb-challenge` — fan-out, one per instance | validate · check-refs · **human gate 3** |
| `06` | emit | `rb-emit` — thin wrapper over `rubrica emit` | validate · check-refs |
| `07` | smoke | code | validate · check-refs |

Rows `01b` through `01i`, and `01k`, are **one logical step engineered as
substeps.** Every pass reads all of `01-claims/` — the split is on *output*, not
on claims, so the barrier property is untouched and a contradiction between two
inputs is still visible to the pass that records it. They are separate stages
rather than one skill branching on a slice id because `check-skills` binds one
skill file to one stage name and `manifest.stages` records model, effort and
skill digest per stage, which is what lets a think-heavy pass carry a different
budget from a mechanical one.

**`01j` is not one of them**, and it is named here rather than folded into the
range: `synthesise-interfaces` merges no claims into a partial. It *derives* one
OpenAPI document per service from `01-services.json`, reading `01-claims/` solely
to resolve the input schema each operation carries, so the barrier property above
is not its property at all — its inputs were sealed by the pass before it. It is
in the band because it belongs to world-model construction and a human reads its
output at gate 1, not because it shares the band's shape. It is code for `emit`'s
reason, and it is its own stage rather than part of the seal so that a human who
corrects a grouping at gate 1 can re-derive one service's document without
re-running the seal over every partial.

`reconcile-seal` is code for the reason `emit` is: two runs with
identical partials must produce a byte-identical world model.
`01-world-model.json` keeps its path, schema and byte shape, so nothing below
the seal can tell it was assembled pass by pass rather than written in one
dispatch.

Challenge's and reconcile-contradict's `check-refs` run **only once every member
has finished**: `refs.check_verdicts` and `refs.check_contradiction_parts` each
report every missing slice from the moment their directory exists, so
mid-fan-out most of them are missing by construction. `refs.check_all` runs
every checker the run has inputs for, so there is no such thing as a
stage-scoped `check-refs`.

`survey` and the `triage-*` family have no `0N` directory prefix of their own:
`survey` writes `00-catalogue.json`, the family writes its staged parts, and
`triage-seal` writes the `00-triage.json` those parts assemble into — all of it
ahead of the `00-inputs/` and `manifest.json` that `intake` mints once gate 0
has passed. The numbering stays intake's, not theirs, because intake is still
what fixes the run's identity.

Stages 02a through 03b are a loop bounded by `max_rounds`, and the whole of it
repeats — not just `propose` and `score`. Score *computes* the coverage verdict
(`continue` / `converged` / `halted_no_progress` / `halted_round_cap`) and
`score-seal` composes the document that carries it; only the orchestrator acts on
it. `propose-seal` runs twice a round, and the repeat is load-bearing: it is a
pure function of the parts and the rulings, so the second run is what folds this
round's rulings in before `score-seal` reads the document for what each live
scenario credits.

**Gate 0 is different in kind from the others.** Gates 1 through 3 review a
judgment made from evidence already in the run; a human overturning one of them
corrects an inference about the target. Gate 0 decides what the run can ever
know — nothing downstream of `intake` reads the corpus again, so a candidate
the triage family declines is gone as completely as if the corpus never
contained it. That is why triage cannot also hold its own gate: the same party
selecting the
inputs and ratifying the selection would make the whole run unfalsifiable.

`rb-orchestrate` is a skill and **is not a stage**: it declares no `stage` and no
`schemas`. It dispatches the prompt stages from `extract` through `emit`, holds
gates 1 through 3, and writes `decisions.md`. It never runs `survey`, never
dispatches any pass of the triage family, and never holds gate 0 — all three are
finished before it is ever dispatched.

`intake`, `smoke`, `survey`, `triage-slices`, `triage-seal`, `reconcile-seal`,
`synthesise-interfaces`, `propose-batches`, `propose-seal`, and `score-seal` are
code, so they have no skill and no `manifest.stages` entry. Their absence there is
not a finding.

## The exit-code contract — load-bearing, do not weaken

| Code | Meaning |
|---|---|
| `0` | clean |
| `1` | findings, **one per line on stdout** |
| `2` | usage error, or an unreadable/misconfigured run |

The orchestrator branches on this: a `1` is a repairable stage defect worth one
retry, a `2` means retrying cannot help. Two invariants follow, and both have
been violated in this repo before:

- **A stage defect must never surface as `2`.**
- **A `1` must never have empty stdout.** An exception escaping the handler
  produces exactly that, and the whole class is what `cli.py`'s catch-all and
  `findings.py` exist to prevent.

A third rule learned the hard way: a `1` must name the *right* artifact.
`check-refs` over an unreadable `01-claims/` once reported four fabricated
`no such claim` findings against a correct world model.

When you touch `cli.py`, `validate.py`, `refs.py` or `paths.py`, test the
unreadable-input paths (`chmod 000`, `chmod 0444`, a bad `RUBRICA_SCHEMA_DIR`),
not just the happy path.

## Two check layers

- **Layer 1** — `rubrica validate --stage X`: JSON Schema, one per artifact
  kind. Schemas in `src/rubrica/schema/*.json`, shipped as package data.
  `validate.STAGE_ARTIFACTS` maps stage → artifact kinds.
- **Layer 2** — `rubrica check-refs`: cross-artifact references, seed
  conformance, reachability, invariant evaluation.

**Layer 2 checks that an element *references* a resolvable claim, never that the
claim *supports* it.** Support is semantic; do not invent a mechanical check for
it. Two real defects lived under that hole in the golden fixture itself.

## The skill contract

Every `src/rubrica/skills/rb-*/SKILL.md` carries a `## Contract` block (TOML,
exactly one fence) with `stage`, `reads`, `writes`, `schemas`, `invokes`, and
these five mandatory sections in order (`skills.SECTIONS`):

```
1. Inputs   2. Output   3. Method   4. Invariants   5. Refusal conditions
```

`rubrica check-skills` holds each contract to `paths.RunPaths` attribute names,
`validate.STAGE_ARTIFACTS`, and `cli.SUBCOMMANDS`. It validates the *names*,
never whether the set is *right* — a `reads` list can be complete, over-broad,
or missing something the prose needs, and only reading catches that.

The `rb-` prefix itself lives in `skills.SKILL_PREFIX` — one home, because it
was three before the rename and a partial update makes `check-skills` reject
every correctly named skill.

Section 5 is the most important prompt-level decision in the design —
[`docs/design/rationale.md`](docs/design/rationale.md) argues why. Treat a
refusal condition as decorative if its trigger has no stated action, its action
is one a model cannot take, or its condition is one a model cannot detect from
what it can read.

## The deterministic subcommands

Everything a prompt is not trusted to do. `cli.SUBCOMMANDS` is the list;
[`docs/reference/cli.md`](docs/reference/cli.md) documents each one, and
`tests/unit/test_docs_accuracy.py` fails if the two disagree. The rulings that
are judgments rather than list entries:

- `emit` is code, not a prompt, because two runs with identical stage-4 and
  stage-5 artifacts must produce byte-identical suites — otherwise variance can
  no longer be attributed to a stage.
- `synthesise-interfaces` is code on that same argument, one band earlier: a
  service's OpenAPI document is a pure function of the grouping
  `rb-reconcile-services` judged, so two runs with identical groupings must
  produce byte-identical documents. **Its failure surface splits across both exit
  codes, and the split is load-bearing.** A missing or non-object
  `01-services.json`, a service id that is not a usable filename, a tool name the
  harness would rewrite, and a `schema_claim` no claim in `01-claims/` has an id
  for are `1`s: re-dispatching `reconcile-services` repairs each. A `schema_claim`
  naming a claim that exists and carries no usable `payload` is a `1` too, but
  against `01-claims/<artifact_id>.json` and **not** repairable by that pass —
  which is instructed to cite such a claim anyway — so it is a finding a human
  rules on at gate 1. An unwritable
  `01-interfaces/` is a `2`, because no prompt re-dispatch fixes a directory
  permission and a `1` there would spend the run's one repair attempt on a stage
  whose output was never the problem. It is also all-or-nothing and owns its
  directory: a partial write, or a document left over from a superseded grouping,
  makes a later check report against a service whose only problem is a malformed
  sibling.
- `dedupe-candidates` proposes pairs and never decides.
- `record-stage` hashes the skill file the run actually used, so a digest that no
  longer matches the file on disk means the file changed after the run — that is
  the hook working, not a defect.
- `claim-utilisation` and `gate-brief` are **reports, not gates**: each always
  exits clean on a readable run. `claim-utilisation` surfaces each input's
  cited/total claim count for a human to read at gate 1 — the zero-utilisation
  finding it shares its arithmetic with lives in `check-refs`, never here.
  `gate-brief` composes what already exists into the reading surface at each
  human gate: at gate 0 the objective verdict, the predicted-vs-observed surface
  divergence, grouped declines, the slice table and every group the slicer split
  across more than one slice; the reconcile sweep plus per-input utilisation,
  per-pass read coverage, the capabilities the coverage denominator excludes,
  implied size and one block per service at gate 1; the coverage matrix at gate 2;
  the verdict tally at gate 3.
  Gate 1's sweep is an **aggregate, not a per-subject tally** — how many subjects
  cover how many claims, how many subjects were swept, how many contradictions
  were recorded, and, only when any were, the tally by `resolution` with
  `unresolved` first. Gate 1's read coverage is **per pass, not per input**: each
  owning pass's own-kind claims cited over total, and under it only the input rows
  that dropped a claim, each beside the `note` the drop required. Gate 1's services
  block is read from `01-services.json`, not from the assembled world model, so a
  reader correcting a grouping edits the file `synthesise-interfaces` re-derives
  from; **nothing in the run reads a decision about those services**, and the block
  says so rather than letting a recorded selection read as a narrowing.
  `target-brief` is a report too, and the one written for somebody outside the
  project: it renders a run's description of the *target* — not of the run — for the
  people who own that target, asking them to correct it. Three ranked asks lead, and
  the full description sits collapsed beneath — what it can do, what data it holds,
  who uses it — each of *its* statements carrying the file it was read from, which is
  the scope [`docs/reference/cli.md`](docs/reference/cli.md) states. The asks above it
  are not held to it and were never meant to be: a gap names no file by design, and
  where we could not work out which file something came from the page says so instead
  of guessing.
  Two things about it are load-bearing rather than stylistic: prose written by a stage
  is **selected and relabelled, never rewritten**, since an owner correcting a
  sentence we paraphrased would be correcting our paraphrase; and no stage, gate,
  artifact or mention of rubrica reaches the page *in this project's own wording*,
  which two tests enforce because a recipient reading about
  `01-world-model.json` has been handed the wrong question — a claim id inside a
  sentence we selected ships as written, which is that same rule seen from the other
  side. It exits **0** on an unreadable `01-claims/` where `claim-utilisation` and
  `gate-brief` exit 2 — it has no number to be quietly wrong, so it says at the top
  that it could not cite its sources and describes the target anyway. `run-summary`
  exits 0 there too, so this is a contrast with the two reports that compute a
  number, not a property unique to this one.
- `survey` is `intake`'s counterpart for the corpus path: it walks a corpus,
  digests each candidate, and mints the run, but writes `00-catalogue.json`
  instead of a manifest — there is nothing to extract from yet, because nothing
  has been admitted. `adopt-projection` admits a manufactured artifact into the
  catalogue structurally, without touching the corpus or the run's identity.
- `set-limit` changes a manifest limit — `max_scenarios` most often — with the
  reason recorded in `decisions.md`, so raising a ceiling is a decision on the
  record rather than a silent hand-edit.

## Testing prompts: the traps that actually recur here

Roughly nineteen assertions in this repo were *measured* satisfiable by
unrelated content. The cause is structural, so assume it applies to anything you
write:

- `skills.load()` sets `body` to the **entire file text**, and the five section
  headings are mandatory — so `"refusal" in body.lower()` is vacuous for every
  conforming skill.
- The frontmatter `description:` line and the contract block also satisfy naive
  substring checks.

**Use `skills.section_body(skill, "<heading>")`** to scope an assertion to the
section that owns the rule. Assert co-occurrence within that section, not
presence anywhere in the file.

**Measure every predicate in both directions before committing it.** Delete or
blank the prose it claims to check, in a `/tmp` copy under
`RUBRICA_SKILLS_DIR`, and confirm it goes red; then reword that prose
meaning-preservingly and confirm it stays green. A predicate nobody has watched
fail is not yet a guard — and the mirror failure is equally real here, where a
phrase pin broke on an innocuous reformat.

Two weakness shapes recur in text-level tests: **substring-of-message** and
**fixture-cannot-reach**. The third shape the design records,
*holds-identically*, has no prompt analogue — do not hunt for it.

What no test can reach: whether a dispatched model actually *followed* the
prompt. That is what the live exercises are for.

## Fixtures

- `tests/fixtures/toy/` — the golden two-capability world (`api.json`,
  `notes.md`, `trace.json`). **This is the model answer a skill imitates**, so a
  defect here teaches a skill the wrong thing. Treat edits to it as
  higher-risk than edits to source.
- `tests/toy.py` — builds a complete run from it. `build_toy_run(runs_dir,
  upto=...)` stops at any of `_UPTO_STAGES`; `SIDS` is the four *instantiated*
  scenarios, `ALL_SCENARIO_IDS` includes the folded duplicate. Check this module
  before adding a helper — nearly every request for a new checkpoint during the
  build turned out to be for one that already existed.
- `tests/fixtures/toy-contradiction/` and `tests/fixtures/toy-gap/` — negative
  fixtures, each the golden world with specific prose subtracted, proving the
  refusal conditions fire. `tests/unit/test_refusal_fixtures.py` guards that
  each still carries its defect *and* has not silently lost anything else. Both
  directions are needed: an over-subtraction once destroyed a capability fact
  while passing every forbidden-substring check.
- The gap fixture's forbidden-substring list **is its specification.** Do not
  relax it to make prose easier; if a word is truly unavoidable, remove it and
  say so.
- `tests/fixtures/<name>/recorded/01-world-model.json` — committed live model
  output, so a refusal observed once becomes a regression test. **Changing a
  skill obliges re-recording**, and that re-record is a reviewable diff rather
  than silent drift. `check-refs` exits 1 against a bare `recorded/` directory —
  expected, since a lone world model has no claims or manifest to resolve
  against.

## Live tests and exercise records

`make live` runs the `live`-marked tests, gated by `RUBRICA_LIVE`
(`tests/conftest.py`, which treats `0`/`false`/`no`/empty as off so
`RUBRICA_LIVE=0` cannot opt you in). They assert against committed recordings,
so running them is free; *producing* a recording dispatches a model and costs
money. They are not part of `make test`, and the skip message names the command
that runs them.

Most skills carry an `exercise.md` beside the `SKILL.md`, recording what **one**
real dispatch measurably did — the only behavioural evidence this project has,
and one sample is one sample. No pass of either staged family carries one, which
leaves both the earliest and the widest fan-out in the pipeline with no
behavioural evidence beside their skills at all: the `reconcile-*` passes because
they are new, and the `triage-*` passes for a different reason, which is **not**
that the monolithic stage they replaced was never dispatched; see
[`docs/design/limitations.md`](docs/design/limitations.md) for what those runs
produced and why the record is not in the repository.

**Counting `exercise.md` files on disk will not give you the number of skills
that have one, and that is deliberate.** `src/rubrica/skills/rb-reconcile/` holds
an `exercise.md` and no `SKILL.md`: it is the record of two real dispatches of
the single-pass stage the `reconcile-*` family replaced, kept where it was rather
than relocated into any new pass, because relocating it would assert that a
dispatch of *that* pass did what the superseded stage actually did. Its
`SUPERSEDED.md` says so. `skills.discover()` skips the directory, since
`_skill_dirs` keeps only children with a `SKILL.md`.

Two rules for an exercise record:

- It states what **happened**. A reasoned number presented as an observed one
  corrupts the evidence; one such misattribution shipped and had to be
  retracted.
- Results belong in that file, not only in a review ledger elsewhere. Ledgers
  get deleted — a gitignored run directory most of all.

To run a stage by hand, follow
[`docs/guides/invoking-rubrica.md`](docs/guides/invoking-rubrica.md).

## Conventions (non-negotiable)

[`CONTRIBUTING.md`](CONTRIBUTING.md) is the full set. The ones you will hit
first:

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags — `-s` is
  the `Signed-off-by` trailer, `-S` the cryptographic signature. If signing
  fails, **stop and report it**; never fall back to unsigned, never work around
  it.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with` — GitHub
  parses those as co-authorship.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. Ruff
  formats Python code blocks inside Markdown, so `extend-exclude` covers all of
  `docs/` — its code blocks are laid out for reading, and the dated build records
  in there must stay verbatim. `README.md` and `CLAUDE.md` are **not** excluded,
  so run `make check` after editing either.
- Comment density here is high and deliberate: comments explain *why* a choice
  was made, usually citing a measurement. Match that; do not strip them.

## Before raising a finding against a skill's output

**Check what the stage's `reads` actually gives it.** A finding that requires
knowledge outside the contract is a finding against the *contract or the
fixture*, never against the prompt. This is the mistake behind the two fix
rounds named at the top of this file — the same two, not another pair: a stage
was blamed for not knowing a fact that lived only in a claims file it is
forbidden to read, and one `grep` would have settled it.

The mirror question, for a proposed `reads` addition: **does a deterministic
gate already enforce the property?** If yes, the requirement belongs to the
gate, not to a declared read.

## Where documentation lives

[`docs/README.md`](docs/README.md) is the index, and everything it lists is
current. The dated build records that sit alongside those documents are
**recorded history**: they were accurate on their own date, they have been
superseded, and they **must not be cited as describing current behaviour** —
which is why this file no longer names that directory at all. Do not edit
anything inside it either; a record of what happened is falsified, not
corrected, by a later edit.

Adding or renaming a stage, skill, subcommand, or artifact kind means updating
[`docs/concepts/pipeline.md`](docs/concepts/pipeline.md),
[`docs/reference/cli.md`](docs/reference/cli.md), or
[`docs/reference/artifacts.md`](docs/reference/artifacts.md) as appropriate.
`tests/unit/test_docs_accuracy.py` fails until you do, and that failure is the
guard working — update the document, not the assertion. Three policies it also
enforces on this file and every other user-facing document: no hand-typed test
count; no heading that counts something that grows (stages, skills,
subcommands, gates); and no citation of the recorded-history tree, which
`docs/README.md` alone is allowed to link. `## Two check layers` is permitted
deliberately — there are exactly two by architecture, and a third would be a
design change rather than an increment.

Two of this project's drawings are generated rather than written, and neither
may be hand-edited.
[`docs/concepts/pipeline-diagram.html`](docs/concepts/pipeline-diagram.html) is
the detailed one, from `scripts/render-pipeline-diagram.py`. Edit the script's `ROWS`
table and re-render; never hand-edit the page. The same test module checks both
halves — that `ROWS` draws `paths.STAGES` in order, and that the committed page
is byte-identical to a fresh render — so a stage added without a row, or a page
edited without its script, is a failure rather than a drawing that quietly
describes an older pipeline.

The other is the pair of SVGs the README shows, `docs/assets/how-it-works.svg`
and its `-dark` twin, from `scripts/render-readme-diagram.py`. It draws the same
run at a newcomer's altitude — the stages collapsed into five phases, the human
gates kept, everything else dropped — and its `PHASES` table is checked to
partition `paths.STAGES` in order and to mark every `brief.GATES` entry. Two
files because GitHub's dark theme does not follow the OS `prefers-color-scheme`
an `<img>`-referenced SVG resolves against, so the README picks between them
with a `<picture>` element. Which phase a stage belongs to is editorial and no
test can rule on it; that judgment is yours to read.
