---
name: tg-score
description: Judge this round's scenarios -- folding the pairs that are one test, promoting the rest -- then compute the coverage matrices against the frozen denominator, justify every uncovered row with a hole, and report the verdict the orchestrator acts on.
---

# tg-score

You are dispatched once per round, after `tg-propose` has appended this
round's scenarios and before the orchestrator decides whether to run another
round. You are the second of this pipeline's two barrier stages: like
`tg-reconcile` you run alone, with every scenario in the run visible in one
context at once, because the two judgments this stage exists to make -- is
this pair of scenarios the same test, and is this row of the denominator
actually covered -- cannot be made from any single scenario's slice.

Two things make this the stage to get right. You are the only stage that may
change a scenario's `status`, so a promotion you skip is a test that never
gets built and a fold you get wrong is either a lost cell or a wasted
instantiate. And the numbers you write into `03-coverage/latest.json` are
what every later claim about this suite is measured against: a percentage
that disagrees with the matrix under it is not a cosmetic error, it is a run
reporting coverage of a surface it never touched, with both gates green.

## Contract

```toml
stage = "score"
reads = ["world_model", "scenarios"]
writes = ["scenarios", "coverage_round", "coverage_latest"]
schemas = ["coverage"]
invokes = ["dedupe-candidates", "validate", "check-refs"]
```

## 1. Inputs

You read exactly the two artifacts this skill's contract names under
`reads`: `01-world-model.json` (`world_model`) and `02-scenarios.json`
(`scenarios`). The world model is frozen input -- its `capabilities` with
their `outcome_classes`, its `goals` with their `expected_hop_depths`, its
`gaps`, and its `denominator` are the entire universe your matrices may
describe, and you never amend any of it. The scenarios file is the run's
whole scenario history, every round of it, and it is the one artifact you
both read and write, because the status transitions this stage owns are
edits to scenarios somebody else wrote.

Being the barrier means you legitimately see *every* scenario, not one
cluster's worth, and that is the design rather than a leak: judging whether
two scenarios are the same test is inherently cross-scenario work, and a
stage restricted to one slice could not do it at all. **That licence stops
at the scenarios.** It does not extend to `01-claims/`: the claims files are
not in your `reads`, and being a barrier does not make them yours the way it
makes them `tg-reconcile`'s. Reconciliation is the one stage that reads
claims, and everything that survived it is in the world model in front of
you. If you find yourself wanting to consult a claim -- to check what an
outcome class really means, to see whether a scenario's fact is supported --
stop: either the world model already says it, or it does not say it and that
absence is a `gaps` entry the world model records, and neither case is a
reason to open a file your contract does not name. The same holds for
`04-instances/`, `05-verdicts/`, and `07-report.json`: nothing has been
instantiated yet in this round, and a verdict from an earlier run is not
evidence about this one.

One number comes from outside those two files, and it is the only one:
`manifest.json`'s `limits.max_rounds`, which is this run's configuration
rather than knowledge about the target. You need it for exactly two
purposes -- the `halted_round_cap` verdict in Method step 9, and Invariant 8
-- and for nothing else. It is a bound, not a fact about the system under
test, and it does not open the door to anything else on disk.

You are dispatched with no memory of any conversation that came before you,
and nothing you write here carries forward as memory either. Whatever you
need has to be derivable from the two artifacts you read, from this
document, or from the command in Method step 1 -- and it is. In particular,
**nobody tells you which round this is**: the round you are scoring is the
highest `round` tag among the scenarios in `02-scenarios.json`, because
`tg-propose` tags every scenario it writes with the round that wrote it.
Every quantity in `progress` is derivable the same way, from those round
tags, which is why you never need to read back a coverage document from an
earlier round -- Method step 8 spells out the derivation. Deriving it beats
reading it: a stale `latest.json` from a round that was scored and then
re-proposed against would silently answer the wrong question.

There is a second boundary that is easier to miss: what you may *know*. A
fold, a promotion, and a hole reason may rest only on what the world model
declares and what the scenario documents in front of you actually say --
their `goal_id`, `user_intent`, `capability_refs`, `hop_depth`, and
`discriminating_fact`. Never on what a test suite for a system like this one
usually contains, and never on which of two scenarios "sounds like" the real
test. Two scenarios are the same test because their goal, their cells, and
the fact the agent has to determine coincide, not because one is phrased the
way a benchmark usually phrases it.

One specific version of that boundary is worth naming, because it is the
easiest place to reach past your inputs without noticing. The world model
records the *ids* that structure it -- capability ids, outcome-class ids,
goal ids, actor ids, entity and field names -- and it records field `type`s,
but it has **no representation for a field's value domain**: `entity.fields`
and `capability.params` carry a name and a type and nothing else, no enum
and no examples. So when a `discriminating_fact` names a concrete value --
a queue called `billing`, a ticket id, a count -- there is nothing anywhere
in your inputs to check that value against, by construction. A concrete
value there is a prescription to `tg-instantiate` about what to build, not a
claim about what the target already has. Do not fold, reject, or reopen a
scenario because a value in its fact looks invented, and do not treat two
scenarios as distinct merely because they picked different concrete values
for the same cell: decide on what the test asks the agent to determine. No
stage downstream of `tg-reconcile` can ground a value, and pretending
otherwise would have you making rulings on evidence you do not have.

## 2. Output

Two things, in three files.

**The updated `02-scenarios.json` (`scenarios`).** The same document you
read, with the same `schema_version`, the same `denominator_version`, and
the same scenarios in the same order. You never add a scenario -- creation
is `tg-propose`'s and only `tg-propose`'s -- and you never remove or
renumber one. The only fields that may differ from what you read are
`status` and the fields a status requires: `duplicate_of` on a scenario you
mark `duplicate`, and `rejected_reason` (one of `ambiguous`,
`not_derivable`, `wrong_label`, `out_of_scope`, `blocked_by_gap`) on one you
mark `rejected`. Both are schema-required for their status, so a fold
without a survivor named is a validation failure rather than a partial
ruling. A scenario an earlier round already judged keeps the judgment it
already has.

**One `coverage-0.1.json`-shaped document, written twice**: to
`03-coverage/round-<N>.json` (`coverage_round`) and to
`03-coverage/latest.json` (`coverage_latest`), with identical content. It
carries `schema_version: "0.1"`, `round`, `denominator_version`,
`capability_matrix`, `goal_matrix`, `holes`, `progress`, and `verdict` --
all eight required, an incomplete report being a validation failure rather
than a smaller report.

Note what that document has no room for: every object in the coverage schema
is `additionalProperties: false`, and the only free-text field anywhere in it
is a hole's `justification`. So the report cannot carry an essay explaining
itself, and it does not need to -- the `verdict` has to be *entailed* by the
matrices and the `holes` you wrote, so that a reader recomputes it from the
document rather than taking your word for it. Anything you need to say that
the schema has no field for -- an ambiguous pair you deliberately kept, a
cell the scenario list claims and the world model does not have -- belongs in
what you report back to the orchestrator, which records it in `decisions.md`.

## 3. Method

1. **Run `testgen dedupe-candidates --run <run>` and read the JSON it
   prints.** Each entry is a pair of scenarios that share a `goal_id` and
   claim at least one coverage cell in common, with the `shared_cells` and
   `identical_cells` evidence that raised it. That pairing is the cheap,
   deterministic half of dedupe; the expensive half is yours. A candidate is
   *a pair worth a judgment call, never a decision* -- the command has ruled
   nothing, and it excludes pairs already settled in an earlier round so a
   resolved fold is not reopened.

   Run it even when the scenario list is short enough to read at a glance. A
   stage that eyeballs a four-scenario list will eyeball a forty-scenario
   one, and the pairing rule you reconstruct by eye is not the rule this
   command applies -- so the same run scored twice would fold different
   pairs, which is exactly the inconsistency moving this half into code was
   meant to remove.

2. **For each candidate pair, decide whether they are the same test.** The
   question is what the agent has to determine, not how the sentence is
   worded: "find the oldest failing job on prod0" and "which prod0 job
   failed longest ago" are one test, asked twice. Two scenarios that differ
   only in *outcome class* -- one where the lookup succeeds and one where it
   finds nothing -- are not one test, no matter how similar the wording,
   because they are two different cells of the denominator and folding them
   deletes one. `identical_cells: true` on a pair whose
   `discriminating_fact` values pin down the same fact is the strongest
   signal you will get that a pair really is one test.

   Fold by marking one of the two `status: "duplicate"` with `duplicate_of`
   naming the survivor, and leave the survivor exactly as it is (it is
   promoted in step 3 like anything else you keep). Pick the survivor
   deliberately rather than arbitrarily: keep the scenario whose
   `discriminating_fact` pins its world down more tightly, and on a tie keep
   the one from the earlier round, so that the id which survives is stable
   across two scorings of the same state.

3. **Promote every scenario you are keeping from `proposed` to `active`.**
   That is the point of this stage's authority: `active` means you accepted
   it. A scenario left `proposed` is not instantiated, not emitted, and not
   counted as a test that exists -- and `refs.check_instances` reports one
   that was instantiated anyway, because the stage that built it acted on a
   ruling you never made. If you are turning a scenario down rather than
   keeping it, mark it `rejected` with a `rejected_reason`; do not leave a
   scenario `proposed` as a way of not deciding.

4. **Build `capability_matrix`: one cell per capability x outcome-class pair
   in the world model.** **Every** pair, none omitted and none invented --
   `refs.check_coverage` reports both directions by name, and the omission
   is the dangerous one, because a matrix holding only the cells some
   scenario happens to claim reports 100% of a denominator it shrank to fit.
   Enumerate from the world model's `capabilities` and their
   `outcome_classes`, never from the scenario list.

   For each cell, `scenario_ids` lists the scenarios claiming it -- the ones
   whose `capability_refs` name that capability and that outcome class --
   and `covered` is true if and only if at least one of them is `proposed`
   or `active`. A cell claimed only by scenarios you folded or turned down
   is not covered: no test will ship for it, so it is a hole again (step 7).

5. **Build `goal_matrix`: one row per goal in the world model**, again every
   one, none invented. `hop_depths_expected` is copied from that goal's
   `expected_hop_depths` -- copied, not re-derived and not trimmed to what
   the scenarios reached. `hop_depths_present` is the set of `hop_depth`
   values of the scenarios in that row's `scenario_ids`. `covered` is true if
   and only if the row has a live scenario **and** every expected depth is
   present.

   A goal exercised at one depth of two is a partial row, and calling it
   covered is how a goal denominator reaches 100% without ever testing the
   hard half of the goal -- the multi-hop half, which is the half the whole
   suite exists to probe. Because `hop_depths_present` is *derived from this
   row's membership*, a goal row's `scenario_ids` carries the scenarios that
   still count -- `proposed` or `active` -- and not the ones you folded or
   turned down: leaving a `duplicate` in a goal row credits the goal with a
   depth no shipped test reaches, and `refs.check_coverage` recomputes
   `hop_depths_present` from whatever ids it finds there.

6. **Compute `covered`, `total` and `pct` for both matrices from the rows
   themselves.** `total` is the number of rows, `covered` the number marked
   covered, `pct` their quotient (`0.0` when `total` is 0).
   `refs._check_matrix_arithmetic` recomputes all three from the rows you
   wrote and reports each disagreement separately, so these are a checkable
   claim about your own output rather than a summary you are trusted on.

7. **Justify every uncovered row with a hole, and give no hole for a covered
   row.** `refs.check_coverage` checks both directions: without the first, a
   report could show 60% and explain none of the missing 40%; without the
   second, a hole could contradict the matrix printed above it. Every hole
   names a `ref` (`cell:<capability_id>/<outcome_class_id>` or
   `goal:<goal_id>`), a `reason`, and a `justification` a reader can act on.

   The `reason` vocabulary is four values, and choosing among them is a real
   judgment because `tg-propose` reads it as a worklist:

   - `not_yet_attempted` -- nobody has proposed against this row yet, and a
     later round can close it. This is the only reason that tells the next
     round to try, so it is the only one that keeps the loop running.
   - `unreachable` -- no scenario could exercise this row against this
     target at all.
   - `out_of_scope` -- the row is real but deliberately outside what this
     suite is trying to cover.
   - `blocked_by_gap` -- the world model itself lacks the knowledge a
     scenario here would need. This one additionally requires `gap_id`,
     naming a real entry in the world model's `gaps`; `refs.check_coverage`
     reports a `gap_id` that resolves to nothing.

   When every row is covered, the honest `holes` is the empty array. Do not
   invent a hole to look thorough: a hole naming a covered row is a finding,
   and a fabricated one sends the next round to work on a cell that is
   already tested.

8. **Fill `progress`: `new_cells_this_round` and
   `rounds_without_progress`.** Both are derived from the round tags on the
   scenarios, which is why you need no earlier coverage document.
   `new_cells_this_round` is the number of capability cells that are covered
   now and were *not* covered before this round -- that is, no live scenario
   from an earlier round credits them. `rounds_without_progress` is the
   number of consecutive most-recent rounds that added no new cell by that
   same test; in round 1 it is 0, and `new_cells_this_round` is simply the
   count of covered cells. These two numbers are what `halted_no_progress`
   is computed from, so a `new_cells_this_round` inflated by counting cells
   an earlier round already covered is how a loop that has stopped making
   progress runs to the round cap anyway.

9. **Compute `verdict`.** It is *computed here* and *acted on by the
   orchestrator*: this stage does not decide to iterate, does not dispatch
   another `tg-propose`, and does not stop the run. It writes the state of
   the loop and hands it over. The four values, in the order you test them,
   so that the same state always produces the same verdict:

   - `converged` -- no closable hole remains. Every hole left is
     `unreachable`, `out_of_scope`, or `blocked_by_gap`, so no further round
     could close anything, whether or not the matrices read 100%.
   - `halted_no_progress` -- a closable hole remains but this round added no
     new cell (`new_cells_this_round` is 0). Proposing again against the
     same holes is what an unbounded loop looks like.
   - `halted_round_cap` -- the round you just scored is `max_rounds`, so
     there is no next round to run.
   - `continue` -- none of the above: closable holes remain, this round made
     progress, and the cap has room.

10. **Write the same document to `03-coverage/round-<N>.json` and to
    `03-coverage/latest.json`.** Both, with identical content -- not the
    round file with a symlink, not a summary in one and the full report in
    the other. `validate --stage score` requires `latest.json` **by name**,
    and `refs.check_limits` and `refs.check_coverage` both return no
    findings at all when it is absent: a score stage that wrote the round
    file and forgot the pointer used to pass both gates with every coverage
    check silently bypassed. Write the round file for the history and
    `latest.json` for every stage and gate that reads "the current
    coverage", and keep them byte-identical.

## 4. Invariants

1. `capability_matrix.cells` has exactly one cell per world-model capability
   x outcome-class pair -- no pair of the denominator missing, and no cell
   naming a capability or outcome class the world model does not declare.

2. `goal_matrix.rows` has exactly one row per world-model goal, on the same
   terms: none omitted, none invented.

3. `covered`, `total` and `pct` agree with the rows in both matrices.

4. Every `scenario_ids[]` entry, in either matrix, names a scenario that
   exists in `02-scenarios.json`.

5. A row marked `covered` is credited to at least one scenario that is still
   `proposed` or `active`. A rejection reopens the row, so a row whose every
   credit is `rejected` or `duplicate` must be recomputed as uncovered and
   justified as a hole -- including when the rejection came from
   `tg-challenge` after this round and you are re-scoring because of it.
   Leaving the old `covered: true` in place is coverage that is confidently
   wrong with both gates green, which is why `refs.check_coverage` reports
   it by name.

6. Every uncovered row has exactly one hole, and no covered row has one.

7. `denominator_version` equals the world model's `denominator.version`. If
   you believe that version is wrong, that is something to report, not
   something to fix by writing a different number.

8. `round` does not exceed `manifest.limits.max_rounds`.
   `refs.check_limits` reports a coverage document scored for a round past
   the cap.

9. Every scenario you mark `duplicate` carries `duplicate_of` naming a
   scenario that exists and that is not itself a `duplicate`. A chain of
   folds ends at a survivor, or the cell it claimed has no live credit at
   all.

10. `03-coverage/latest.json` and `03-coverage/round-<N>.json` have
    identical content.

Before you report done, run `testgen validate --stage score` and then
`testgen check-refs`. Either one reporting a finding against what you just
wrote is not a finding to pass along -- it is your own defect to fix. Repair
the artifact and run both again; report success only once
`testgen validate --stage score` and `testgen check-refs` both exit clean.

## 5. Refusal conditions

Every condition below is one where the correct output is not a tidier
report. The pull on this stage is arithmetical rather than narrative: the
tempting error is not an invented story, it is a number nudged into
agreement -- a cell dropped so the matrix balances, a percentage adjusted to
match a total, a hole labelled as closable so the loop keeps looking
productive. A report that shows a partial matrix honestly is worth more than
one that reads 100% against a denominator it quietly shrank, because every
later judgment in this pipeline is measured against these numbers and none
of them re-derives the denominator.

- **A candidate pair is genuinely ambiguous -- arguably the same test,
  arguably not.** Keep both `active`, and say why in the round file's hole
  justifications or in what you report for the orchestrator's decision.
  Folding a distinct test loses a cell for the whole run, and nothing
  downstream will ever notice it is missing; keeping a duplicate costs one
  wasted `tg-instantiate` fan-out that a later round can still fold. Prefer
  the cheaper error, and record that you made the call deliberately rather
  than leaving it to look like an oversight.

- **A cell cannot be covered because the world model has a gap.** Write the
  hole with `reason: "blocked_by_gap"` and the `gap_id` of the gap that
  blocks it. Never `not_yet_attempted` for such a cell: that reason says
  another round could close it, and no round can -- `tg-propose` reading it
  will spend a round designing a scenario that `tg-instantiate` cannot
  honestly seed, and the run will burn its cap without closing anything.

- **The scenario list claims a cell the world model does not have.** Do not
  invent the cell to make the matrix balance, and do not quietly drop the
  claim. Leave the matrix as the world model defines it and report the
  mismatch: `check-refs` layer 2 will name the scenario's dangling
  `capability_refs` entry, and the real finding is upstream -- the propose
  stage produced a scenario against a cell that does not exist, which no
  amount of arithmetic here can repair.

- **Your computed `pct` disagrees with the matrix you just wrote.**
  Recompute it from the rows rather than adjusting the number to match your
  expectation. A hand-adjusted total is the one defect that makes every
  downstream percentage meaningless, and it is invisible to any reader who
  does not recount the rows -- which is why `refs._check_matrix_arithmetic`
  recounts them and reports `covered`, `total`, and `pct` separately. The
  same holds for a `covered` flag: if the flag and the row's own
  `scenario_ids` disagree, fix the flag, never the count.
