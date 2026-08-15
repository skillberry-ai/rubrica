# MVP readiness: documentation, licensing, and a guard against staleness

**Date:** 2026-08-15
**Status:** design, approved in conversation, pending implementation plan

Rubrica is being moved from an experiment recorded in build documents to an
emerging MVP that an IBM colleague can clone, read, and run without having
watched it get built. This spec covers what has to change for that to be true,
and — because the audit that produced it found the same defect four times over —
what has to be made mechanical so it stays true.

Nothing in this spec changes what Rubrica does. No stage, skill, schema, check
layer, or exit code is touched. The pipeline is the eleven stages and nine
skills it already was.

## 1. Why now, and what "ready" means

The repository is in good technical order: `make test` is green, `make check` is
clean, `rubrica check-skills` exits 0. What is not in order is everything a
reader meets before the code — the README leads with "This is an experiment", the
overview document opens with a "**For team review**" banner, the runbook tells
its reader it is "followed by two readers — the controller, after each of Tasks
7–13's skill implementations", and there is no LICENSE at all.

"Ready" here means four things, in descending order of how badly the absence
hurts:

1. **Legally shareable.** Apache-2.0, copyright IBM Corp. No LICENSE today.
2. **Accurate.** Every claim a document makes about the system is true of the
   system. §2a lists the ones that are not.
3. **Readable cold.** A colleague with no build context can install it, run it,
   and understand why it is shaped this way — without reading a 5,622-line plan.
4. **Hard to re-break.** The staleness that produced most of finding class §2
   below fails a test instead of surviving until the next audit.

### The audience decision

The project keeps its falsifiable question — *does prompt-carried judgment
survive a chain of artifact handoffs well enough to produce a suite worth
running?* — but stops leading with it. The front door becomes what the tool does
and how to run it; the experiment moves to `docs/design/rationale.md`, referenced
prominently and not buried.

This is a repositioning of emphasis, not a retreat from the claim. `CLAUDE.md`
uses that question as the yardstick for judging changes ("a change that makes the
pipeline more likely to produce output while making a stage's judgment less
observable is a loss, not a win") and it keeps doing so. What changes is that a
first-time reader is not asked to evaluate an epistemics argument before they
learn what the thing is.

## 2. The defects this spec closes

Every item below was measured against the working tree at `6390df0`, not
inferred. They are grouped by what kind of mistake each is, because the fix
differs.

### 2a. Claims that are false

| Where | Claims | Measured |
|---|---|---|
| `CLAUDE.md:30` | Baseline `1378 passed, 4 skipped` | 1677 passed, 4 skipped |
| `docs/pipeline-overview.md:228` | "1126 tests passing" | 1677 |
| `docs/pipeline-overview.md:197` | "twelve subcommands" | 17 in `cli.SUBCOMMANDS` |
| `docs/pipeline-overview.md:199-212` | subcommand table, 12 rows | missing `survey`, `adopt-projection`, `gate-brief`, `set-limit`, `claim-utilisation` |
| `docs/pipeline-overview.md:3` | "All eight skills now exist" | nine, including `rb-triage` |
| `docs/pipeline-overview.md:222` | "All eight skills — extract … orchestrate" | same |
| `docs/pipeline-overview.md:77` | "### Three human gates" | four; gate 0 is absent from the section |
| `docs/pipeline-overview.md:100-109` | skill table | `rb-triage` missing entirely |
| `docs/pipeline-overview.md:169-192` | run-directory tree | no `00-catalogue.json`, no `00-triage.json` |
| `docs/pipeline-overview.md:32` | `check-skills` "fails in CI, not at run time" | there is no CI; no `.github/` exists |
| `docs/pipeline-overview.md:221` | toy world "run end to end in CI" | same |
| `README.md:181` | "Two more, neither one a gate itself" | three follow — `gate-brief`, `set-limit`, `adopt-projection` |
| `README.md:42-59` | "The code" table | omits `brief.py`, `cli.py`, `digest.py`, `emit.py`, `findings.py`, `sizing.py`, `survey.py`, `triage.py`, `utilisation.py`, and `suite/` |

`claim-utilisation` appears in no user-facing document at all — not in
`README.md`, not in either `docs/*.md`.

`docs/pipeline-overview.html` is a 642-line hand-styled twin of
`pipeline-overview.md` and carries a second copy of every number above.

### 2b. Framing only legible from inside the build

- `docs/pipeline-overview.md:3` — "**For team review.**" banner.
- `docs/pipeline-overview.md:214-229` — "Where the build is", a done/pending
  status table that dates the moment it is written.
- `docs/running-a-stage-by-hand.md:5` — "followed by two readers — the
  controller, after each of Tasks 7–13's skill implementations passes review".
  Also `:83` ("Task 13's"), `:190` ("Tasks 7–13"), `:236` ("Task 14 adds the
  first"), `:248` ("the controller"). No external reader can resolve a task
  number in an unnamed plan.
- `README.md:12` — section titled "What is here so far".
- `README.md:200-204` — "### The two writers the orchestrator uses … had no
  writer until this build."
- `CLAUDE.md:30-70` — a single parenthetical of roughly 800 words reconciling
  the test-count baseline commit by commit. It is the most conscientious piece
  of prose in the repository and it is still wrong by 299 tests, which is the
  argument for deleting the genre rather than correcting the number.

### 2c. Missing for any shared repository

- No `LICENSE`, no `NOTICE`.
- `pyproject.toml` declares no `license`, `authors`, `readme`, `urls`,
  `classifiers`, or `keywords`.
- No `CONTRIBUTING.md`. The mandatory `git commit -S -s` convention exists only
  as `CLAUDE.md` prose, where a human contributor will not look for it.
- No CI, which two documents already assert exists.

### 2d. Terms that stop being defined

`Harbor` is the format `rubrica emit` targets. It appears in `rubrica --help`
("compile accepted instances into Harbor packages", `cli.py:95`), in
`emit.py`'s pinned `HARBOR_SCHEMA_VERSION = "1.3"`, in `paths.py:255`, and in
`suite/test.sh`'s `/logs/verifier/reward.txt` contract. Every definition of what
Harbor *is* lives in `docs/superpowers/`. Under §4's rule that the historical
tree is no longer a source of truth, the term becomes undefined in everything
authoritative — a reader who runs `--help` has nothing to look up.

### 2e. A fixture nobody else can re-capture

`tests/fixtures/reservation-trajectories/capture_harness.py:38-39` hardcodes
`/home/bnayahu/work/rossoctl/examples/...`. That file is a capture harness, not a
test, and it sits in `tests/fixtures/`.

Two facts constrain the fix, both verified rather than assumed:

- `tests/unit/test_trajectory_fixtures.py:27` reads the harness and
  `ast.literal_eval`s its `PROMPTS` list to derive the expected trace ids and
  their order. It parses the file as text — it does not import it — so a move
  and a kebab-case rename cost exactly one constant, and the module's guards
  keep working. **Moving the harness does not cost the provenance record.**
- `trajectories.json` embeds that same absolute path ten times in MLflow
  `mlflow.source.name` fields. It is a committed recording, and this project's
  rule is that a recording is evidence of what happened. Editing one to look
  tidier corrupts the evidence. **Those ten strings stay.**

## 3. Decisions taken

Recorded so the plan does not re-litigate them.

| Decision | Ruling |
|---|---|
| Positioning | Lead as an early working tool. The experiment becomes `docs/design/rationale.md` — referenced, not front-page. |
| Design records | `docs/superpowers/` stays tracked, as recorded history only. Fresh `docs/design/rationale.md` and `docs/design/limitations.md` become the authority. |
| Scope | Documentation, plus LICENSE/NOTICE, CI, packaging metadata, and `CONTRIBUTING.md`. No PyPI publishing. |
| License | Apache-2.0, `Copyright IBM Corp.` Internal repository initially. |
| License headers | `LICENSE` + `NOTICE` + the pyproject SPDX field. **No per-file headers** — no churn across ~90 source and test files. |
| CI platform | GitHub Actions, `.github/workflows/`. |
| Capture harness | Move out of `tests/`. |
| `pipeline-overview.html` | Delete. Markdown is the single source; GitHub renders it. |
| Test counts | **Removed from every document, not corrected.** They grow with every capability; a number no test derives will go stale again. |
| Version | Stays `0.1.0`. Nothing has been released, so a bump communicates nothing. |
| Provenance citations in `tests/` | Permitted. A fixture may record where it came from. §4's rule scopes to the user-facing set. |

## 4. The rule this spec introduces

**`docs/superpowers/` is recorded history and is not a source of truth for any
user-facing document or for `CLAUDE.md`.**

It stays tracked — every byte of it — because a dated build record is worth
keeping and the four existing references to it are provenance worth preserving.
What it stops being is authority. Concretely:

- **The user-facing set**, used throughout this spec, is `README.md`,
  `CONTRIBUTING.md`, `CLAUDE.md`, and `docs/**/*.md` excluding
  `docs/superpowers/**`. Within it, exactly one file may mention
  `docs/superpowers`: `docs/README.md`, which links it as history. `CLAUDE.md`
  may not mention it at all. The preamble below names its own tree, but lives
  inside `docs/superpowers/` and so is not in the set.
- Files under `tests/` and `src/` may cite a historical record as provenance
  (`tests/fixtures/reservation-trajectories/README.md:4`,
  `tests/unit/test_cli.py:340`). That is what history is for.
- `docs/superpowers/README.md` is new: a short preamble stating that these are
  dated build records, accurate as of their own date, superseded by `docs/`, and
  not to be cited as current. Without it a newcomer meets a 5,622-line plan and
  a 1,358-line spec and reasonably mistakes them for the documentation.

Two retargets follow, and both are load-bearing rather than cosmetic:

- `CLAUDE.md:13` — "Design spec: `docs/superpowers/specs/2026-08-06-…`" →
  `docs/design/rationale.md`.
- `CLAUDE.md:15-17` — "Read §8's **Parked from the skills build** table before
  proposing a fix — it is long, current, and most 'bugs you just found' are in it
  with a ruling" → `docs/design/limitations.md`.

The second is the instruction every agent working in this repository follows, and
it currently sends them into a build record. **`docs/design/limitations.md` must
therefore carry those rulings in full, not gesture at them.** It is the largest
single writing task in the plan, and the one where an under-delivery is a real
regression: a contributor who cannot find the ruling re-reports the bug.

## 5. The target document set

```
README.md                               front door: what it does, install, quickstart, where next
CONTRIBUTING.md                         dev loop, -S -s, CI gates, how to add a stage or skill
LICENSE                                 Apache-2.0, verbatim
NOTICE                                  Rubrica / Copyright IBM Corp.
CLAUDE.md                               agent instructions — rewritten, counts gone
docs/README.md                          index; links docs/superpowers/ as history
docs/getting-started.md                 install → survey → triage → gate 0 → intake → orchestrate
docs/concepts/pipeline.md               the stages, the skills, the four gates, the 02↔03 loop, fan-out isolation
docs/concepts/artifact-contract.md      the one architectural rule, run layout, two check layers, exit codes
docs/concepts/glossary.md               Harbor, claim, world model, denominator, seed, oracle, distractor, projection
docs/reference/cli.md                   every subcommand, one section each
docs/reference/artifacts.md             one entry per schema kind, with its stage
docs/guides/running-a-stage-by-hand.md  moved, de-internalised
docs/design/rationale.md                the experiment, the falsifiable question, why artifacts-only
docs/design/limitations.md              the parked ledger, distilled from the spec's §8
docs/superpowers/README.md              preamble: dated records, superseded, not current
docs/superpowers/{specs,plans}/         unchanged, every byte
```

Deleted: `docs/pipeline-overview.md`, `docs/pipeline-overview.html`.

### What each document owns, and where its content comes from

| Document | Owns | Sourced from |
|---|---|---|
| `README.md` | What Rubrica does in five lines, install, a quickstart that runs, and links out. Nothing else. | current `README.md` §Setup, §Usage — heavily cut |
| `docs/getting-started.md` | One worked run, end to end, against the toy fixture | current `README.md` §"Running the pipeline", §Usage |
| `concepts/pipeline.md` | Stage table, which stages are code, gate 0's difference in kind, the round loop, fan-out isolation | `pipeline-overview.md:36-92`, `:94-109` + a new `rb-triage` row |
| `concepts/artifact-contract.md` | Artifacts-as-only-channel, the run directory, layer 1 and layer 2, the exit-code contract and its invariants, the reachability and denominator checks | `pipeline-overview.md:16-34`, `:164-192`; `README.md:106-129`, `:360-428` |
| `concepts/glossary.md` | Harbor and the emitted package layout; claim, derivation grade, world model, denominator, hole, gap, contradiction, seed, distractor, oracle, verdict, projection, objective | new prose; Harbor from `emit.py`, `paths.py:255`, `suite/test.sh` |
| `reference/cli.md` | Every subcommand: synopsis, what it writes, its exit codes, worked example | `README.md:131-335` plus the five commands it never covered |
| `reference/artifacts.md` | Each schema kind, the stage that writes it, the stage that reads it | `src/rubrica/schema/*.json`, `validate.STAGE_ARTIFACTS` |
| `guides/running-a-stage-by-hand.md` | The hand-dispatch runbook, isolated dispatch, re-dispatching a re-seed | current file, with §2b's task numbers rewritten |
| `design/rationale.md` | The falsifiable question, why artifacts-only, why emit is code, why gate 0 cannot be triage's own, what the fan-out buys | `pipeline-overview.md:12-34`, `:70-92`; spec §1-3 as raw material |
| `design/limitations.md` | Every parked ruling, each with the reasoning that parked it | spec §8's parked table, `CLAUDE.md:350-372`, `pipeline-overview.md:237-266` |

Content that is **dropped rather than moved**: `pipeline-overview.md:111-162`
("What a real run produced", "Both refusal conditions fire") and `:214-229`
("Where the build is"). The measured run results are build evidence tied to one
commit; the refusal-fixture facts are already asserted by
`tests/unit/test_refusal_fixtures.py` and `test_refusals_live.py`, which is a
better home for them than prose. `design/rationale.md` keeps one short paragraph
noting the pipeline has run end to end with a model at every stage against the
toy world, without the numbers.

## 6. Repo hygiene

| Add / change | Content |
|---|---|
| `LICENSE` | Apache-2.0, verbatim |
| `NOTICE` | `Rubrica` / `Copyright IBM Corp.` |
| `pyproject.toml` | `license = "Apache-2.0"`, `license-files`, `authors`, `readme = "README.md"`, `[project.urls]`, `classifiers`, `keywords` |
| `pyproject.toml` build-system | `setuptools>=75` → `>=77`. The SPDX-string `license` form is PEP 639, implemented by setuptools from 77.0. Without the bump the field is read as legacy free text. |
| `pyproject.toml:33-37` | The ruff-exclusion comment justifies excluding `docs/` because "committed design records must not be reformatted". That reason expires when `docs/` becomes documentation. The exclusion stays — illustrative code blocks are laid out for reading — the comment is rewritten to say so. |
| `CONTRIBUTING.md` | Setup, the make targets, **both** commit flags (`-S -s`; if signing fails, stop and report — never fall back to unsigned), the `Assisted-By` trailer rule and why `Co-Authored-By` is forbidden, the three CI gates, the comment-density convention, and the both-directions rule for new predicates |
| `.github/workflows/ci.yml` | push + pull_request; ubuntu-latest; Python 3.13 via `astral-sh/setup-uv`; then `make check` → `make test` → `uv run rubrica check-skills`. **Never `make live`** — it needs credentials and costs money |
| `.gitignore` | `+ .claude/.cc-writes/` |
| move | `tests/fixtures/reservation-trajectories/capture_harness.py` → `scripts/capture-reservation-trajectories.py`; update `test_trajectory_fixtures.py:27`'s constant and that fixture's README |
| `tests/fixtures/reservation-trajectories/README.md` | Reworded so its spec citation reads as provenance; a note that the harness's absolute paths and `trajectories.json`'s ten `mlflow.source.name` strings are captured provenance and are deliberately not sanitised |

## 7. The staleness guard

`tests/unit/test_docs_accuracy.py`. Every predicate asserts on **a set the code
already owns**, never on a phrase, so a meaning-preserving reword stays green
while a genuinely absent command goes red. This is the direct application of
`CLAUDE.md`'s warning about the *substring-of-message* weakness shape: a test
that pins prose breaks on reformatting, and this repository has already had a
phrase pin break on an innocuous reflow.

1. Every name in `cli.SUBCOMMANDS` appears in `docs/reference/cli.md`.
2. Every `src/rubrica/skills/rb-*/` directory name appears in
   `docs/concepts/pipeline.md`.
3. Every entry in `paths.STAGES` appears in `docs/concepts/pipeline.md`.
4. Every artifact kind in `validate.STAGE_ARTIFACTS` appears in
   `docs/reference/artifacts.md`.
5. No hand-typed test count in the user-facing set: a search for
   `\d{3,4}\s+(tests?|passed)` finds nothing. Scoped to that set deliberately —
   `docs/superpowers/` is full of such counts and every one of them is a correct
   record of what was true on its own date.
6. No heading in the user-facing set carries a cardinal count of stages, skills,
   subcommands, or gates — neither a digit nor a number word. This retires
   `## Eleven stages, nine skills` and `## Seventeen deterministic subcommands`
   as a genre rather than as two instances.

   The rule targets counts of sets that **grow**. It does not target counts of
   sets closed by design: `## Two check layers` stays, because there are exactly
   two by architecture and a third would be a design change rather than an
   increment. A plan task that "fixes" that heading has over-applied the rule.
7. Within the user-facing set, only `docs/README.md` mentions
   `docs/superpowers`; `CLAUDE.md` does not mention it at all. This is §4's
   rule, made mechanical.

**Each predicate is measured in both directions before it counts as a guard.**
Delete or blank the prose it claims to check — in a `/tmp` copy where the
predicate reads a path, or via a temporary edit reverted immediately — and
confirm red; then reword that prose meaning-preservingly and confirm green. A
predicate nobody has watched fail is not yet a guard.

Predicates 5 and 6 are the two that encode a *policy* rather than a fact, and
they are the reason the counts do not come back. They are also the two most
likely to be felt as friction by a future author, so each carries a comment
naming the measurement that motivated it: four counts stale simultaneously, and
an 800-word hand reconciliation that was still off by 299.

## 8. Verification

The suite is necessary and not sufficient here, because most of what this spec
changes is prose that no test reads.

1. `make check`, `make test`, `uv run rubrica check-skills` — all green.
2. **Link check.** Every relative link in every tracked `.md` resolves to a file
   that exists. Run over the whole tree, including `docs/superpowers/`, since
   deleting `pipeline-overview.md` may break an inbound link from a historical
   record — and if it does, the historical record is left alone and the link is
   accepted as broken-by-history, because a dated record is not edited to track
   a rename.
3. **The rename sweep, done carefully rather than once.** `pipeline-overview`,
   `docs/running-a-stage-by-hand`, `capture_harness`, `docs/superpowers`. This
   repository has already had a stale name survive six tasks' worth of sweeps
   because an `&nbsp;` split it, so the sweep runs against raw bytes and a
   single clean grep is not accepted as evidence.
4. **Fresh-clone walkthrough.** Every command block in `README.md` and
   `docs/getting-started.md` executed against a scratch runs directory. Stale
   example commands surface no other way.
5. **The CI claim is true.** `.github/workflows/ci.yml` exists and its three
   gates are the three named in `CONTRIBUTING.md`.
6. **The historical tree lost nothing.**
   `git diff --stat 6390df0 -- docs/superpowers/` shows exactly two additions and
   no modifications: this spec, and `docs/superpowers/README.md`. Any other line
   in that diff is a violation of §9.

## 9. Out of scope

- **PyPI publishing.** No release workflow, no version policy, no package-name
  claim.
- **Per-file license headers.** Ruled out; `LICENSE` + `NOTICE` + SPDX field.
- **Any change to a stage, skill, schema, check layer, or exit code.** If a
  documentation task appears to require one, that is a finding against this spec
  and stops the task.
- **Sanitising `trajectories.json`.** It is a recording. See §2e.
- **Editing any file under `docs/superpowers/`** except adding `README.md`. The
  records stay verbatim, which is the same ruling the rename build made and for
  the same reason.
- **Re-recording any live fixture.** No skill changes, so nothing obliges a
  re-record.

## 10. Assumptions stated, not verified

- The internal repository runs GitHub Actions. If it does not, `ci.yml` is dead
  weight and the fallback is a `make ci` target plus a documented CI contract;
  the three gates are unchanged either way.
- `Copyright IBM Corp.` is the correct NOTICE wording for this repository. If
  legal review prefers a different form, only `NOTICE` changes.
- Version stays `0.1.0`.
