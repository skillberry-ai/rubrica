# Rubrica

Builds agent test suites for a target system out of artifacts that describe it
(specs, captured trajectories, source), by chaining AI skills over a
schema-validated on-disk artifact contract.

**This is an experiment, and the question is falsifiable:** does prompt-carried
judgment survive a chain of artifact handoffs well enough to produce a suite
worth running? Keep that in mind when changing things — a change that makes the
pipeline more likely to produce output while making a stage's judgment less
observable is a loss, not a win.

Design spec: `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md`.
Read §8's **Parked from the skills build** table before proposing a fix — it is
long, current, and most "bugs you just found" are in it with a ruling.

## Setup and commands

Python 3.13+, `uv`. Console script `rubrica` (`rubrica.cli:main`).

```
make setup     # uv venv --python 3.13; uv pip install -e '.[dev]'
make test      # uv run pytest -q
make check     # ruff check + ruff format --check, no changes
make live      # RUBRICA_LIVE=1 pytest -m live  (see "Live tests" below)
make lint      # ruff check --fix
make format    # ruff format
```

Baseline: **1162 passed, 4 skipped**; `make check` clean; `uv run rubrica
check-skills` exits 0. Anything else means you broke something. (It was 1126 as
of the skills build; the three added since are `f3b9d30`'s, and this line went
stale because it names a build rather than a commit. It was 1129 as of
`f3b9d30`; the eight added since are `test_trajectory_fixtures.py`'s, guarding
the reservation-service trajectory fixture (Task 3 of the
2026-08-12-reservation-service-trajectory-run). It was 1137 as of `373130b`;
the two added since are `test_trajectory_fixtures.py`'s trace-count and
prompt-order guards, closing findings 3 and 4 of the whole-branch review that
examined that fixture. It was 1139 as of `a31c4d0`; the seven added since are
`test_utilisation.py`'s five, plus two `test_cli.py` grows for free whenever
`cli.SUBCOMMANDS` gains an entry — its `parametrize("command",
sorted(subcommand_names()))` × `parametrize("breakage", ...)` picked up
`claim-utilisation` automatically. It was 1146 as of `c6a1020`; the two added
since are `e20726c`'s new phrase-pin assertions in `test_skills_extract.py`
and `test_skills_reconcile.py`, unchanged in count by `399dba5`'s
whitespace-normalisation fix to those same two. It was 1148 as of `399dba5`;
the two removed since are Task 3's deletion of
`test_the_recorded_world_model_keeps_its_pre_rubrica_spelling` (one
parametrized test, two ids), retired per spec §6's ruling that this file's
re-recording obligation wins its documented contradiction with that test. It
was 1146 as of `9dbf203`; the one added since is
`test_utilisation.py`'s `test_an_input_cited_only_through_a_contradiction_is_not_a_finding`,
proving finding 1's fix of a whole-branch review — `_cited_claim_ids` was
missing `contradictions[].claim_a`/`claim_b`, which `refs.check_world_model`
already treats as claim citations, so the gate fired on an input whose only
surviving contribution was a recorded contradiction. It was 1147 as of
`8f1ea7c`; the eight added since are `test_dispatch_harness.py`'s, holding
`scripts/dispatch-stage.sh`'s deny lists over the three run-local paths no
skill's `reads` names — they skip, rather than fail, on a machine without
`claude` or `jq` on `PATH`, so a green run there is not evidence. It was 1155 as
of `2644639`; the nine added since are `test_dispatch_harness.py`'s again,
covering the `RUBRICA_RESEED` append. It was 1164 as of `2f93726`; the two
removed since are that commit's stage-scoped `05-verdicts` deny test plus one
`OUT_OF_CONTRACT` parametrization, because **denying a path `check-refs` reads
makes a stage's own gate fabricate findings** — measured, and now guarded by
`test_nothing_check_refs_reads_is_ever_denied` — re-measure it here when you add
tests.)

Commands in `README.md` assume the venv is on `PATH`; otherwise prefix `uv run`.
Four env overrides exist: `RUBRICA_SCHEMA_DIR` (`validate.py`),
`RUBRICA_SKILLS_DIR` (`skills.py`), `RUBRICA_SUITE_DIR` (`emit.py`), and
`RUBRICA_LIVE` (`tests/conftest.py`). Three are exercised by tests —
`RUBRICA_SUITE_DIR` currently has no test referencing it — but all four are
fair game: prefer them over editing repo files when probing behaviour.

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

## Nine stages, eight skills

`paths.STAGES` is the ordering and the on-disk numbering:

| Dir | Stage | Runs as | Gate |
|---|---|---|---|
| `00` | intake | code | validate |
| `01a` | extract | `rb-extract` — fan-out, one per input | validate |
| `01b` | reconcile | `rb-reconcile` — barrier | validate · check-refs · **human gate 1** |
| `02` | propose | `rb-propose` | validate |
| `03` | score | `rb-score` — barrier | validate · check-refs · **human gate 2** |
| `04` | instantiate | `rb-instantiate` — fan-out, one per active scenario | validate · check-refs |
| `05` | challenge | `rb-challenge` — fan-out, one per instance | validate · **human gate 3** |
| `06` | emit | `rb-emit` — thin wrapper over `rubrica emit` | validate · check-refs |
| `07` | smoke | code | validate · check-refs |

Stages 02 and 03 are a loop bounded by `max_rounds`. Score *computes* the
coverage verdict (`continue` / `converged` / `halted_no_progress` /
`halted_round_cap`); only the orchestrator acts on it.

`rb-orchestrate` is the eighth skill and **is not a stage**: it declares no
`stage` and no `schemas`. It dispatches the seven, holds the gates, and writes
`decisions.md`.

`intake` and `smoke` are code, so they have no skill and no `manifest.stages`
entry. Their absence there is not a finding.

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

Section 5 is described in the spec as the most important prompt-level decision
in the design. Treat a refusal condition as decorative if its trigger has no
stated action, its action is one a model cannot take, or its condition is one a
model cannot detect from what it can read.

## Thirteen deterministic subcommands

Everything a prompt is not trusted to do:

`intake` · `validate` · `check-refs` · `check-skills` · `dedupe-candidates` ·
`record-stage` · `decide` · `emit` · `smoke` · `compare-gold` · `diff-runs` ·
`sample-for-review` · `claim-utilisation`

`emit` is code, not a prompt, because two runs with identical stage-4 and
stage-5 artifacts must produce byte-identical suites — otherwise variance can no
longer be attributed to a stage. `dedupe-candidates` proposes pairs and never
decides. `record-stage` hashes the skill file the run actually used, so a digest
that no longer matches the file on disk means the file changed after the run —
that is the hook working, not a defect. `claim-utilisation` is a report, not a
gate — it always exits clean on a readable run and surfaces each input's
cited/total claim count for a human to read at gate 1; the zero-utilisation
finding it shares its arithmetic with lives in `check-refs`, never here.

## Testing prompts: the traps that actually recur here

Roughly nineteen assertions in this repo were *measured* satisfiable by
unrelated content. The cause is structural, so assume it applies to anything you
write:

- `skills.load()` sets `body` to the **entire file text**, and the five section
  headings are mandatory — so `"refusal" in body.lower()` is vacuous for every
  conforming skill.
- The frontmatter `description:` line and the plan-mandated contract block also
  satisfy naive substring checks.

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
**fixture-cannot-reach**. The third shape the spec names,
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

## Live tests and exercises

`make live` runs the `live`-marked tests, gated by `RUBRICA_LIVE`
(`tests/conftest.py`, which treats `0`/`false`/`no`/empty as off so
`RUBRICA_LIVE=0` cannot opt you in). They assert against committed recordings,
so running them is free; *producing* a recording dispatches a model and costs
money. They are not part of `make test`, and the skip message names the command
that runs them.

Each skill also has an `exercise.md` beside it recording a real dispatch's
measured result — the only behavioural evidence this project has. Two rules:

- An exercise record states what **happened**. A reasoned number presented as an
  observed one corrupts the evidence; one such misattribution shipped and had to
  be corrected.
- Results belong in that file, not only in a review ledger elsewhere. Ledgers
  get deleted.

To run a stage by hand, follow `docs/running-a-stage-by-hand.md`.

## Conventions (non-negotiable)

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags — `-s` is
  the `Signed-off-by` trailer, `-S` the cryptographic signature. If signing
  fails, **stop and report it**; never fall back to unsigned, never work around
  it.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with` — GitHub
  parses those as co-authorship.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. `docs/` is
  excluded because committed design records must not be reformatted; `README.md`
  is **not** excluded, so run `make check` after editing it.
- Comment density here is high and deliberate: comments explain *why* a choice
  was made, usually citing a measurement. Match that; do not strip them.

## Known limitations worth knowing before you "fix" something

All are recorded in the spec's §8 with the reasoning that parked them. The three
that most often look like new bugs:

1. **The isolation rule is enforceable on artifacts inside a run and
   unenforceable on everything else a subagent can reach.** A member that read a
   sibling's seed produces a byte-identical artifact to one that did not. Both
   observed violations surfaced only because a subagent volunteered them in a
   report nobody obliged it to write. No schema, no `check-refs`, no digest can
   catch this; the only instrument is a transcript audit at dispatch time. This
   is the weakest link in the build.
2. **The world model has no representation for a field's value domain.**
   `capability.params` and `entity.fields` carry only name/type(/required), with
   `additionalProperties: false`. So a concrete value anywhere downstream of
   reconcile is a *prescription* to `rb-instantiate`, never an assertion about
   the target — every seed value is synthetic by construction. Do not raise
   findings that require a stage to ground a value against claims; no artifact
   carries the domains.
3. **Seed conformance is one-directional** (seed→world only), so a seed can drop
   a declared collection, or declare all of them empty, and pass both layers
   with zero findings. Whether *partial* seeds are legal is an open design
   question — it needs a ruling, not a patch.

Also open: golden `scn-empty`'s `answer_excludes` marks a correct,
more-informative answer wrong (assertions 0.5, reward 0.6 against the oracle's
1.0), parked because the reward means it feeds are pinned in three places.

## Before raising a finding against a skill's output

**Check what the stage's `reads` actually gives it.** A finding that requires
knowledge outside the contract is a finding against the *contract or the
fixture*, never against the prompt. This mistake once drove two wasted fix
rounds: a stage was blamed for not knowing a fact that lived only in a claims
file it is forbidden to read. One `grep` would have settled it.

The mirror question, for a proposed `reads` addition: **does a deterministic
gate already enforce the property?** If yes, the requirement belongs to the
gate, not to a declared read.
