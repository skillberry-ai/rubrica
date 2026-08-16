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
`scenario_id`). Never a sibling's.

The orchestrator may append exactly two things to a re-dispatch, both verbatim
machine text, never paraphrased: a repair's gate findings, and a re-seed's
verdict fields. A paraphrase is the orchestrator's conclusion wearing a
finding's clothes.

## The stages and their skills

`paths.STAGES` is the ordering and the on-disk numbering. `survey` and
`triage` precede `intake` and bracket the earliest gate:

| Dir | Stage | Runs as | Gate |
|---|---|---|---|
| — | survey | code — walks a corpus, writes `00-catalogue.json` | validate |
| — | triage | `rb-triage` | validate · check-refs · **human gate 0** |
| `00` | intake | code | validate |
| `01a` | extract | `rb-extract` — fan-out, one per input | validate |
| `01b` | reconcile | `rb-reconcile` — barrier | validate · check-refs · **human gate 1** |
| `02` | propose | `rb-propose` | validate |
| `03` | score | `rb-score` — barrier | validate · check-refs · **human gate 2** |
| `04` | instantiate | `rb-instantiate` — fan-out, one per active scenario | validate · check-refs |
| `05` | challenge | `rb-challenge` — fan-out, one per instance | validate · check-refs · **human gate 3** |
| `06` | emit | `rb-emit` — thin wrapper over `rubrica emit` | validate · check-refs |
| `07` | smoke | code | validate · check-refs |

Challenge's `check-refs` runs **only once every member has finished**:
`refs.check_verdicts` reports every instance without a verdict from the moment
`05-verdicts/` exists, so mid-fan-out most of them are missing by construction.
`refs.check_all` runs every checker the run has inputs for, so there is no such
thing as a stage-scoped `check-refs`.

`survey` and `triage` have no `0N` directory prefix of their own: `survey`
writes `00-catalogue.json` and `triage` writes `00-triage.json`, both ahead of
the `00-inputs/` and `manifest.json` that `intake` mints once gate 0 has
passed — the numbering stays intake's, not theirs, because intake is still what
fixes the run's identity.

Stages 02 and 03 are a loop bounded by `max_rounds`. Score *computes* the
coverage verdict (`continue` / `converged` / `halted_no_progress` /
`halted_round_cap`); only the orchestrator acts on it.

**Gate 0 is different in kind from the others.** Gates 1 through 3 review a
judgment made from evidence already in the run; a human overturning one of them
corrects an inference about the target. Gate 0 decides what the run can ever
know — nothing downstream of `intake` reads the corpus again, so a candidate
`rb-triage` declines is gone as completely as if the corpus never contained it.
That is why triage cannot also hold its own gate: the same party selecting the
inputs and ratifying the selection would make the whole run unfalsifiable.

`rb-orchestrate` is a skill and **is not a stage**: it declares no `stage` and no
`schemas`. It dispatches the prompt stages from `extract` through `emit`, holds
gates 1 through 3, and writes `decisions.md`. It never runs `survey`, never
dispatches `rb-triage`, and never holds gate 0 — all three are finished before it
is ever dispatched.

`intake`, `smoke`, and `survey` are code, so they have no skill and no
`manifest.stages` entry. Their absence there is not a finding.

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
- `dedupe-candidates` proposes pairs and never decides.
- `record-stage` hashes the skill file the run actually used, so a digest that no
  longer matches the file on disk means the file changed after the run — that is
  the hook working, not a defect.
- `claim-utilisation` and `gate-brief` are **reports, not gates**: each always
  exits clean on a readable run. `claim-utilisation` surfaces each input's
  cited/total claim count for a human to read at gate 1 — the zero-utilisation
  finding it shares its arithmetic with lives in `check-refs`, never here.
  `gate-brief` composes what already exists into the reading surface at each
  human gate: the objective verdict and grouped declines at gate 0, utilisation
  and implied size at gate 1, the coverage matrix at gate 2, the verdict tally
  at gate 3.
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

Most skills also carry an `exercise.md` beside the `SKILL.md`, recording what
**one** real dispatch measurably did — the only behavioural evidence this project
has, and one sample is one sample. `rb-triage` is the exception and carries
none, which is **not** explained by never having been dispatched; see
[`docs/design/limitations.md`](docs/design/limitations.md) for what those runs
produced and why the record is not in the repository. Two rules for an exercise
record:

- It states what **happened**. A reasoned number presented as an observed one
  corrupts the evidence; one such misattribution shipped and had to be
  retracted.
- Results belong in that file, not only in a review ledger elsewhere. Ledgers
  get deleted — a gitignored run directory most of all.

To run a stage by hand, follow
[`docs/guides/running-a-stage-by-hand.md`](docs/guides/running-a-stage-by-hand.md).

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

One of those documents is drawn rather than written:
[`docs/concepts/pipeline-diagram.html`](docs/concepts/pipeline-diagram.html) is
**generated**, by `scripts/render-pipeline-diagram.py`. Edit the script's `ROWS`
table and re-render; never hand-edit the page. The same test module checks both
halves — that `ROWS` draws `paths.STAGES` in order, and that the committed page
is byte-identical to a fresh render — so a stage added without a row, or a page
edited without its script, is a failure rather than a drawing that quietly
describes an older pipeline.
