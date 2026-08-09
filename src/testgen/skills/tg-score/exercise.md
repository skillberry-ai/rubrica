# tg-score -- live exercise

`tests/unit/test_skills_score.py` and `skills.check_contract` can confirm
this skill's *shape*: the contract, the five sections, and that its prose
names every verdict, every hole reason, both matrices, and every status it
may set. None of that can confirm that a model dispatched with this prompt
actually makes the two judgments the stage exists for -- that it rules on a
duplicate pair instead of eyeballing the list, and that it enumerates the
denominator from the world model instead of from the scenarios it happens to
have. This file records what the live exercise checks instead, so the
controller running it -- and anyone reading its result later -- knows what
"passed" is supposed to mean.

## Setup

Build a toy run stopped after `propose`: `build_toy_run(runs_dir,
upto="propose")`. That checkpoint writes `02-scenarios.json` with every
scenario `proposed` and no `duplicate_of` anywhere, which is what makes the
promotion and the fold real work rather than something the fixture already
did (`tests/unit/test_toy_fixture.py::test_upto_propose_writes_every_scenario_proposed_with_no_duplicate_of`
pins that). `01-world-model.json` is on disk; `03-coverage/` is empty.

One dispatch, not a fan-out: `tg-score` is the barrier, so there is exactly
one subagent, given the run directory, the stage name, and this skill's path
-- no round number, no coverage report, and no memory of the propose stage
that just ran.

The state it starts from, verified against the real code rather than assumed:
four capability cells (`cap-find-tickets` x `oc-found`/`oc-none`,
`cap-get-ticket` x `oc-detail`/`oc-missing`), two goals (`goal-locate`
expecting hop depth 1, `goal-explain` expecting hop depth 2), no gaps,
`max_rounds: 2`, `max_scenarios: 8`, and five `proposed` scenarios.

## Pass criteria

- `03-coverage/round-1.json` and `03-coverage/latest.json` both exist and are
  byte-identical.
- `testgen validate --stage score` exits 0.
- `testgen check-refs` exits 0.
- Every scenario it kept is now `active` -- none left `proposed`. A leftover
  `proposed` scenario is not a smaller ruling, it is a test that will never
  be instantiated, and no gate reports it until something tries to
  instantiate it anyway.

Then read the round file and the scenarios file by hand against the
questions below. A run that clears the four mechanical checks above and
fails any of these has not scored anything -- it has produced numbers that
merely validate.

## Properties no automated test can check

**1. Is the matrix complete -- 4 cells and 2 rows -- or did it write only the
cells some scenario claims?** Method step 4 says to enumerate from the world
model's capabilities and their outcome classes, never from the scenario list,
and step 5 says the same for goals. `refs.check_coverage` does report an
omitted cell, so this one is not invisible to the gates -- but that is the
point of checking it here: a run that had to be repaired before `check-refs`
went green enumerated from the wrong source and got caught, which is a
different result from enumerating correctly the first time, and only the
transcript shows which happened. In the toy world the two counts are 4 and
2; a first draft holding three cells is the failure mode, and it looks
plausible because every scenario in the file is accounted for.

**2. With full coverage there are no holes -- does it write `holes: []`?**
Every one of the four cells and both goals are covered here once the fold is
made, so the honest `holes` is the empty array. Method step 7 says so
explicitly, in both directions. The failure to watch for is a hole invented
to look thorough: `check_coverage` does report a hole naming a covered row,
so again the question is whether it needed reporting. The subtler version is
a hole with `reason: "not_yet_attempted"` against a covered row, which reads
as diligence and would send the next round to work on a cell that already
has a test.

**3. Is the verdict `converged`, and is it entailed by the document rather
than only by the reply?** With no closable hole left, `converged` is the only
correct value of the four -- `continue` would spend a second round on
nothing, and `halted_round_cap` is wrong at round 1 of 2. The second half of
this question needs care, because the coverage schema is
`additionalProperties: false` throughout and its only free-text field is a
hole's `justification`: there is nowhere in the round file to write a
paragraph of reasoning, and with `holes: []` there is not even a
justification string. So "the reasoning appears in the round file" can only
mean *entailment* -- a reader recomputing the verdict from
`capability_matrix`, `goal_matrix`, `holes`, and `progress` alone must reach
`converged` -- and that is how §2 of `SKILL.md` states the requirement.
Check that: recompute the verdict from the document, and check that
`progress` reads `new_cells_this_round: 4` and `rounds_without_progress: 0`
rather than numbers that only make sense with the reply in hand. Anything
the subagent needed to say beyond that belongs in what it reports to the
orchestrator for `decisions.md`, not in a field the schema does not have.

**4. The dedupe judgment, which is the point of this exercise.** In the
pre-score state `testgen dedupe-candidates` returns exactly one pair --
`scn-open` and `scn-open-dup`, with `identical_cells: true` and
`shared_cells: ["cell:cap-find-tickets/oc-found"]`, verified by running it.
The two really are one test behind different wording: same `goal_id`, the
same single cell, the same `discriminating_fact`. So the correct ruling is to
fold one of them -- `status: "duplicate"` with `duplicate_of` naming the
survivor -- and leave the survivor `active`. Three failure modes, in
descending order of seriousness:

- **Both kept `active`.** The loop then pays for two `tg-instantiate`
  fan-outs for one test, and the matrix implies two tests cover a cell that
  has one. Nothing in either gate reports it: two live scenarios crediting
  one cell is a perfectly valid document.
- **Both marked `duplicate`.** The cell then has no live credit, which
  `check_coverage` does report -- a caught failure, but a failure.
- **`dedupe-candidates` skipped altogether** because five scenarios are
  short enough to eyeball. This is the one worth reading the transcript for
  even when the output is correct: a stage that skips the command when the
  list is short will skip it when the list is long, and this is the only run
  where the skip is cheap enough to see. Method step 1's second paragraph is
  written against exactly this, and the transcript is the only place it can
  be confirmed to have landed.

Also worth a glance, though the fixture cannot make it mechanical: Method
step 5 says a *goal* row's `scenario_ids` carries only the scenarios that
still count, so `goal-locate`'s row should not credit the folded
`scn-open-dup`. Here `scn-open-dup` has the same `hop_depth` as its
survivor, so leaving it in changes no derived number and `check_coverage`
stays green either way -- making this a read-by-hand check, and a fixture
whose duplicate sat at a different hop depth is what it would take to gate
it.

## Recording the result

Record which of the four properties held, in the exercise ledger, whether or
not the mechanical pass criteria were met -- and for properties 1 and 2, note
whether the gates had to catch anything, since "green after a repair" and
"right the first time" are different results about whether the prose landed.
Property 4 is the one this exercise exists for: it is the first place in the
pipeline where a skill has to act on a deterministic command's output rather
than substitute its own reading for it, and a negative result there is
exactly as valuable to record as a positive one.
