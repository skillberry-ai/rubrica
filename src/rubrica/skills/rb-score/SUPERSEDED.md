# `exercise.md` beside this file records a stage shape that no longer exists

`rb-score` wrote three files. It edited every promotion, fold and rejection
into `02-scenarios.json` in place, and it wrote one whole
`coverage-0.1.json`-shaped document **twice** -- to
`03-coverage/round-<N>.json` and to `03-coverage/latest.json`, byte-identical,
matrices and percentages and `progress` and all. It now writes one
`03-score/round-<N>.json` carrying judgments only: the `rulings`, the `holes`
with their reasons and justifications, and the `verdict`. `rubrica propose-seal`
folds the rulings into the scenario list and `rubrica score-seal` computes both
matrices, composes the report around score's holes and verdict, and publishes
`latest.json` as a byte copy.

**Why the shape changed.** The arithmetic was never judgment: this skill's own
Method already specified both matrices as pure functions of the world model and
the scenario list, and `refs._check_matrix_arithmetic` already recomputed every
number in them from the rows beneath. Measured on `run-20260825-094033`, the
part replaces a 24,613-byte scenario re-emit and a 61,342-byte coverage document
written out twice. A document composed in code also cannot report a percentage
that disagrees with the matrix under it, which was the one failure no gate could
catch from the document alone.

`exercise.md` records one real dispatch of the three-file shape, against the toy
fixture, and several of its observations are *about* that shape:
`03-coverage/round-1.json` and `latest.json` compared byte-identical with `cmp`,
the matrices carried 4/4 cells and 2/2 rows at `pct` 1.0, and the folded
scenario's membership of a capability cell versus a goal row was read off the
document the dispatch wrote. It is **not** an exercise record for the skill that
now sits beside it, and it was neither relocated nor rewritten: editing it to
read as if it described a judgments-only part would assert that a dispatch of
the *new* shape did what the superseded one actually did, which is the
misattribution this project has already retracted once. What survives on its own
terms is the dedupe judgment -- the fold of `scn-open-dup` onto `scn-open`, made
after actually running `dedupe-candidates` -- because that judgment is the same
one this stage still makes, even though it now records it as a ruling rather than
as an edit.

**So the judgments-only shape has no behavioural evidence beside it yet.** No
dispatch has been recorded that wrote a score part: none that recorded a fold as
a ruling rather than as a status edit, none that justified a hole for a row it
derived but never transcribed, and none that reached the Method step 8 reading
of "covered before this round" that the round-tag derivation now spells out.
That last one is the least protected of the three -- `score-seal` refuses a hole
that disagrees with the computed matrices, but nothing recomputes the verdict
score writes. `docs/design/limitations.md` carries what is unmeasured;
`docs/concepts/pipeline.md` carries the shape.

This directory still has a `SKILL.md`, so nothing here is dormant the way
`rb-reconcile/` is: `skills.discover()` finds this skill, `check-skills` holds
its contract, and no code in this repository reads an `exercise.md` at all.
