---
name: rb-score
description: Judge this round's scenarios -- folding the pairs that are one test, promoting the rest -- then justify every row the frozen denominator will show uncovered with a hole, and report the verdict the orchestrator acts on. Judgments only: score-seal computes the matrices.
---

# rb-score

You are dispatched once per round, after this round's `rb-propose` members
have written their parts and `rubrica propose-seal` has assembled them into
`02-scenarios.json`, and before the orchestrator decides whether to run
another round. You are the second of this pipeline's two barriers: like
`rb-reconcile-subjects` you run alone, with every scenario in the run visible in one
context at once, because the two judgments this stage exists to make -- is
this pair of scenarios the same test, and is this row of the denominator
actually covered -- cannot be made from any single scenario's slice.

Two things make this the stage to get right. You are the only stage that may
promote a scenario out of `proposed`, or fold one, so a promotion you skip is
a test that never gets built and a fold you get wrong is either a lost cell
or a wasted instantiate. And the coverage document every later claim about
this suite is measured against is computed from exactly two things -- the rows
the world model declares, and the statuses your rulings leave behind -- so a
promotion or a fold you get wrong does not merely mislabel one scenario, it
moves those numbers, in a document that will agree with itself either way.

## Contract

```toml
stage = "score"
reads = ["manifest", "world_model", "scenarios", "batches"]
writes = ["score_part"]
schemas = ["score-part"]
invokes = ["dedupe-candidates", "validate"]
```

## 1. Inputs

You read exactly the four artifacts this skill's contract names under
`reads`: `manifest.json` (`manifest`), `01-world-model.json` (`world_model`),
`02-scenarios.json` (`scenarios`) and this round's batch plan
`02-batches/round-<N>.json` (`batches`). The world model is frozen input -- its
`capabilities` with their `outcome_classes`, its `goals` with their
`expected_hop_depths`, its
`gaps`, and its `denominator` are the entire universe the coverage matrices
may describe, and you never amend any of it. The scenarios file is the run's
whole scenario history, every round of it, and `rubrica propose-seal`
assembled it out of the propose members' parts. You read it and you do not
write it: the status transitions this stage owns are recorded as *rulings* in
your own part, and `propose-seal` folds each one onto the scenario it names the
next time it runs.

Being the barrier means you legitimately see *every* scenario, not one
cluster's worth, and that is the design rather than a leak: judging whether
two scenarios are the same test is inherently cross-scenario work, and a
stage restricted to one slice could not do it at all. **That licence stops
at the scenarios.** It does not extend to `01-claims/`: the claims files are
not in your `reads`, and being a barrier does not make them yours the way it
makes them the reconcile passes'. Reconciliation is the one step that reads
claims, and everything that survived it is in the world model in front of
you. If you find yourself wanting to consult a claim -- to check what an
outcome class really means, to see whether a scenario's fact is supported --
stop: either the world model already says it, or it does not say it and that
absence is a `gaps` entry the world model records, and neither case is a
reason to open a file your contract does not name. The same holds for
`04-instances/`, `05-verdicts/`, and `07-report.json`: on an ordinary scoring
dispatch nothing has been instantiated yet in this round, and a verdict from an
earlier *run* is not evidence about this one.

**There is one exception, and it is a whole kind of dispatch rather than an edge
case.** You can be re-dispatched *after* `rb-challenge` has judged this round's
instances, to record a rejection the adversary found and reopen the rows it
credited. When that happens the orchestrator appends to your prompt each
rejected `scenario_id` together with that verdict's `uniquely_determined` and
`derivable_without_guessing` values and its `notes`, quoted from the verdict file.
That appended text **is** evidence about this run, and acting on it is the work
of the dispatch -- Method step 3 says what to do with it. What does not change is
your `reads`: you still never open `05-verdicts/`, because the quoted fields are
what you were given and the rest of that file is not yours to read. If the notice
names a rejection whose reason you cannot determine from the quoted fields, that
is a gap in the notice to report back, not a licence to go reading.

The manifest is in your `reads` for one number: `limits.max_rounds`, which
you need for exactly two purposes -- the `halted_round_cap` verdict in Method
step 9, and Invariant 8 -- and for nothing else. It is this run's
configuration, a bound on the loop rather than a fact about the system under
test, so nothing you write may treat it as evidence about the target the way
the world model is evidence about the target.

The batch plan is in your `reads` for one thing too, and it is an **address**
rather than context: which round this dispatch is scoring. It is the same thing
each `rb-propose` member takes from it, and the reason a plan is a legitimate
read for a stage that closes no hole -- the round a plan is filed under is not a
judgment about the target, so nothing in it can reach a ruling of yours. Its
`batches` array and every `hole_refs` in it belong to the members that were
dispatched against them; you neither work a batch nor check that one was worked,
and a hole you write is justified from the matrices you derive, never from a
batch's roster.

You are dispatched with no memory of any conversation that came before you,
and nothing you write here carries forward as memory either. Whatever you
need has to be derivable from the four artifacts you read, from this
document, from the command in Method step 1, or from a notice the orchestrator
appended to *this* dispatch -- those four and nothing else. On an ordinary
scoring dispatch the first three are the whole of it. The fourth is there
because of the one thing you may be asked to do that your artifacts genuinely
cannot tell you: a `rb-challenge` rejection lives in a file you do not read, so
it reaches you as appended text or it does not reach you at all. In particular,
**nobody tells you which round this is**: the round you are scoring is the
highest-numbered `round-<N>.json` under `02-batches/`, and that document's own
`round` field states it. That is the rule each `rb-propose` member follows for
the same question, and it is the rule for the same reason -- the plan is the
round's own address, filed once per round by code before any member ran.

**Do not derive the round from the scenarios' `round` tags instead**, and the
reason is a state this pipeline sanctions rather than a hypothetical one. When
every propose member of a round honestly declines its batch -- which is exactly
what `rb-propose`'s refusal conditions exist to produce -- the seal writes a
scenario list carrying no scenario tagged with that round. The highest tag on
disk is then an earlier round's, or on a first round there is none at all.
Scoring by tag would
write your part into `03-score/round-<N-1>.json`, overwriting rulings that round
already carries, and `rubrica score-seal --round N` would then refuse a part it
cannot find -- reporting a defect against you for writing exactly where you were
told to. The plan exists for every round that was dispatched, declined or not,
so the derivation above holds in that state and in every other.

Whether this round made progress is a *different* derivation, and that one does
run over the round tags and the statuses beside them, which is what Method
step 8 spells out and why no coverage document is in your `reads`. You do not
write the `progress` numbers -- `rubrica score-seal` computes them, and it reads
the previous
round's own `03-coverage/round-<N-1>.json` rather than `latest.json`, because
`latest.json` is rewritten by every re-score and would silently answer for a
round that was scored and then re-proposed against. What you need the
derivation for is the verdict in Method step 9, which turns on whether this
round added a cell.

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
value there is a prescription to `rb-instantiate` about what to build, not a
claim about what the target already has. Do not fold, reject, or reopen a
scenario because a value in its fact looks invented, and do not treat two
scenarios as distinct merely because they picked different concrete values
for the same cell: decide on what the test asks the agent to determine. No
stage downstream of the reconcile passes can ground a value, and pretending
otherwise would have you making rulings on evidence you do not have.

## 2. Output

One `score-part-0.1.json`-shaped document, written to
`03-score/round-<N>.json` (`score_part`) for the round you derived in
section 1. It carries `schema_version: "0.1"`, `round`, `rulings`, `holes` and
`verdict` -- all five required, an incomplete part being a validation failure
rather than a smaller one. Everything in it is a judgment; nothing in it is a
number that could be computed from the artifacts you read.

**`rulings`: one entry per scenario whose status changes.** Each names a
`scenario_id`, the `status` you are giving it -- `active`, `duplicate` or
`rejected`, and those three only -- plus the field that status requires:
`duplicate_of` on a fold, naming the survivor, and `rejected_reason` (one of
`ambiguous`, `not_derivable`, `wrong_label`, `out_of_scope`, `blocked_by_gap`)
on a rejection. Both are schema-required for their status, so a fold without a
survivor named is a validation failure rather than a partial ruling.

A scenario you rule on nothing about is absent from `rulings` and keeps the
status its propose member gave it, which is `proposed`. `proposed` is
deliberately not one of the three values a ruling may carry: a ruling exists to
*change* a status, so one naming `proposed` would be a no-op that still had to
be honoured. An empty `rulings` array is a real record -- it says you promoted
nothing and folded nothing -- and it is a bad one to write by accident, because
a scenario left `proposed` is not instantiated, not emitted, and not counted as
a test that exists.

**One ruling per scenario in one part.** `propose-seal` refuses a part that
rules on the same `scenario_id` twice: one dispatch contradicting itself is a
defect, and the sealed document would carry only the last of the two, silently.
The refusal is scoped to a single part on purpose -- a *later round's* part
overturning an earlier ruling is exactly what the paragraph below sanctions, so
a run-wide register would refuse the supported case along with the defect.

**`holes`: one entry per row the matrices will show uncovered**, each naming a
`ref` (`cell:<capability_id>/<outcome_class_id>` or `goal:<goal_id>`), a
`reason` and a `justification`. This is the half of the report no code can
compute, which is why it is here and the matrices are not: whether a row is
covered is arithmetic over the statuses, but *why* an uncovered row is
uncovered, and whether a later round could close it, is the judgment
`rb-propose` then reads as its worklist.

**`verdict`: the state of the loop**, computed in Method step 9 and acted on by
the orchestrator. `rubrica score-seal` copies it into the coverage document
untouched, so what you write is what the orchestrator branches on.

**What this part does *not* carry, and why that is not a demotion.** No
`capability_matrix`, no `goal_matrix`, no `covered`/`total`/`pct`, no
`progress`, and no `denominator_version`: `rubrica score-seal` computes all of
them from the world model's rows and the statuses your rulings leave, composes
`03-coverage/round-<N>.json` around your holes and your verdict, and publishes
`latest.json` as a byte copy of it. None of that arithmetic was ever judgment --
`refs._check_matrix_arithmetic` already recomputed every one of those numbers
from the rows beneath them -- and a document composed in code cannot report a
percentage that disagrees with the matrix under it, which is the one failure no
gate could catch from the document alone. What is left in your part is judgment
only, and Method steps 4 through 6 are still yours to *derive*, because step 7
cannot justify a row you have not worked out is uncovered.

A scenario an earlier round already judged keeps the judgment it
already has -- **unless this dispatch carries a rejection notice naming it**,
in which case changing that judgment is precisely what you are here to do. Read
the rule as "do not re-open a ruling that nothing new bears on", never as
"statuses are frozen after the round that set them".

**A re-dispatch rewrites this round's part rather than adding to it, and that is
the one place this stage can lose work it has already done.**
`03-score/round-<N>.json` is one document per round, and `propose-seal`
reassembles `02-scenarios.json` out of the propose parts and the score parts
alone -- no status survives anywhere else. So a re-dispatch that writes only the
new rejection un-promotes everything that round had promoted: those scenarios
fall back to `proposed`, and a `proposed` scenario is not instantiated, not
emitted and not counted, with nothing reporting the loss as a loss. Reconstruct
what is still in force from the statuses in front of you -- every scenario
`02-scenarios.json` carries as `active`, `duplicate` or `rejected` is one some
dispatch ruled on -- and restate each as a ruling in the part you are writing,
with the notice's rejections replacing the ruling for the ids they name rather
than joining it, since Invariant 4 allows each scenario exactly one ruling per
part. Restating a ruling costs nothing: `propose-seal` writes the status
straight onto the scenario, so applying the same one twice is the same
document. Omitting one costs the promotion.

**`03-score/` does not exist on round 1, and creating it is not your job.**
Nothing in `src/rubrica/` mkdirs it -- your `Write` creates it, parents and
all, on the first round and re-uses it on every later one. **Do
not reach for `mkdir`.** This project's dispatch allows `rubrica *` through
Bash and nothing else, so the command lands on an approval prompt that
`claude -p` cannot answer.

Note what your part has no room for: every object in the score-part schema is
`additionalProperties: false`, and the only free-text field anywhere in it is a
hole's `justification`. So it cannot carry an essay explaining
itself, and it does not need to -- the `verdict` has to be *entailed* by the
holes you wrote and the rows they leave, so that a reader recomputes it from
the composed document rather than taking your word for it. Anything you need to
say that the schema has no field for -- an ambiguous pair you deliberately
kept, a cell the scenario list claims and the world model does not have --
belongs in what you report back to the orchestrator, which records it in
`decisions.md`.

## 3. Method

1. **Run `rubrica dedupe-candidates --run <run>` and read the JSON it
   prints.** Each entry is a pair of scenarios that share a `goal_id` and
   claim at least one coverage cell in common, with the `shared_cells` and
   `identical_cells` evidence that raised it. That pairing is the cheap,
   deterministic half of dedupe; the expensive half is yours. A candidate is
   *a pair worth a judgment call, never a decision* -- the command has ruled
   nothing. It excludes scenarios already marked `duplicate` or `rejected`, so a
   fold that was *carried out* is not reopened.

   **It does not exclude pairs you settled by keeping both.** The filter is on
   status, and the first refusal condition in §5 tells you to keep both members
   of a genuinely ambiguous pair `active` -- which leaves both open, so that pair
   is raised again here in every later round. **A re-raise is not evidence the
   pair was never judged.** If a pair looks familiar and you cannot tell from the
   scenarios in front of you why it was left standing, keep both standing: the
   deliberate non-fold is invisible in `02-scenarios.json` by construction, and
   folding a distinct test because the command offered the pair a second time
   deletes a cell for the whole run -- the error §5 ranks as strictly worse than
   a wasted fan-out.

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

   **If this dispatch carries a rejection notice from `rb-challenge`, the status
   edit is step 3's work and there is no gate that will ask you for it.** For
   each `scenario_id` in the notice, set `status: "rejected"` and choose the
   `rejected_reason` yourself from the quoted evidence: `uniquely_determined:
   false` is `ambiguous` (a second world-consistent answer exists), and
   `derivable_without_guessing: false` is `not_derivable`. The `notes` can point
   somewhere else instead -- an oracle that is simply wrong about its own seed is
   `wrong_label` -- so read them rather than mapping the booleans mechanically.
   The notice will not name the reason for you, and it must not: the enum is
   yours, and a notice that had already picked from it would be the
   conclusion-passing the orchestrator's own rules forbid.

   Settle the rulings **before** you work out which rows come out uncovered,
   because steps 4 through 7 read the statuses your rulings leave and Invariant
   5 depends on it. Both halves belong to this one part: the ruling that
   rejects a scenario, and the hole that justifies the row the rejection
   reopens. `rubrica score-seal` refuses to compose the report when it has one
   without the other -- "`cell:x/y` is uncovered and no hole justifies it", or
   "hole names `cell:x/y`, which the computed matrices show as covered" -- and
   it writes nothing when it refuses, so the omission stops the round instead of
   shipping a number. That is what the split bought: the same omission used to
   leave `covered: true` on the strength of a test that will never ship, with
   `emit` pruning the package silently, `check-refs` exiting 0, and this stage
   reporting success.

4. **Work out `capability_matrix`: one cell per capability x outcome-class
   pair the target can be driven on.** You do not write it -- `rubrica
   score-seal` computes both matrices and every summary number beneath them --
   and that is not a demotion: the arithmetic was never judgment, and
   `refs._check_matrix_arithmetic` already recomputed all of it from the rows.
   You still have to derive it, because step 7 asks you to justify every row
   that comes out uncovered and you cannot name those rows without working out
   which they are. **Every** such pair, none omitted and none invented --
   `refs.check_coverage` reports both directions by name, and the omission
   is the dangerous one, because a matrix holding only the cells some
   scenario happens to claim reports 100% of a denominator it shrank to fit.
   Enumerate from the world model's `capabilities` and their
   `outcome_classes`, never from the scenario list.

   "Can be driven on" is a judgment with a mechanical basis you can read off
   the same file: `emit` turns a capability's `binding.tool` into the tool call
   a test makes, so a capability declaring no `binding.tool` gives every
   scenario on it nothing to call. Those cells are real -- the world model
   declares them, and some are genuine surfaces nobody can reach through this
   interface -- but they are not rows to score. `score-seal` writes one computed
   `unreachable` hole for each of them, so the report still accounts for every
   cell the world model declares. A hole of your own on the same cell wins over
   the computed one, which is exactly why `unreachable` is the only honest
   reason to give there: `not_yet_attempted` on such a cell hands the next round
   a row no scenario can close. `refs.check_coverage` reports a matrix row on
   one by name -- "matrix scores undrivable cell `cell:x/y`; it belongs in the
   holes". Read the capability in front of you and decide; do not try to
   reproduce `denominator.capability_cells`, which is not yours to compute and
   which `check-refs` already recomputes for the human at gate 1.

   For each cell, `scenario_ids` lists the scenarios claiming it -- the ones
   whose `capability_refs` name that capability and that outcome class --
   and `covered` is true if and only if at least one of them is `proposed`
   or `active`. A cell claimed only by scenarios you folded or turned down
   is not covered: no test will ship for it, so it is a hole again (step 7).

5. **Work out `goal_matrix`: one row per goal in the world model**, again
   every one, none invented -- and again `score-seal` is what writes it, from the
   same two inputs, so every rule below is a rule about the derivation you make
   rather than about a document you produce. `hop_depths_expected` comes from
   that goal's `expected_hop_depths` unchanged -- not re-derived and not trimmed
   to what the scenarios reached. `hop_depths_present` is the set of `hop_depth`
   values of the scenarios in that row's `scenario_ids`. `covered` comes out
   true if and only if the row has a live scenario **and** every expected depth
   is present.

   A goal exercised at one depth of two is a partial row, and calling it
   covered is how a goal denominator reaches 100% without ever testing the
   hard half of the goal -- the multi-hop half, which is the half the whole
   suite exists to probe. Because `hop_depths_present` is *derived from this
   row's membership*, a goal row's `scenario_ids` carries the scenarios that
   still count -- `proposed` or `active` -- and not the ones your rulings folded
   or turned down: a `duplicate` left in a goal row credits the goal with a
   depth no shipped test reaches, and `refs.check_coverage` recomputes
   `hop_depths_present` from whatever ids it finds there. That rule is one your
   *rulings* have to satisfy, since they are the only input to it you control:
   the seal builds each row's membership from the statuses they leave.

6. **Know what `covered`, `total` and `pct` will come to, from the rows
   themselves.** `total` is the number of rows, `covered` the number marked
   covered, `pct` their quotient (`0.0` when `total` is 0).
   `refs._check_matrix_arithmetic` recomputes all three from the rows of the
   composed document and reports each disagreement separately -- which is
   exactly why this arithmetic is the seal's to write rather than yours: a
   claim nobody has to be trusted on does not need a prompt behind it. What you
   need from it is the row count that tells you how much of the surface your
   holes have to account for.

7. **Justify every uncovered row with a hole, and give no hole for a covered
   row.** `refs.check_coverage` checks both directions: without the first, a
   report could show 60% and explain none of the missing 40%; without the
   second, a hole could contradict the matrix printed above it. Every hole
   names a `ref` (`cell:<capability_id>/<outcome_class_id>` or
   `goal:<goal_id>`), a `reason`, and a `justification` a reader can act on.

   The `reason` vocabulary is four values, and choosing among them is a real
   judgment because `rb-propose` reads it as a worklist:

   - `not_yet_attempted` -- nobody has proposed against this row yet, and a
     later round can close it. This is the only reason that tells the next
     round to try, so it is the only one that keeps the loop running.
   - `unreachable` -- no scenario could exercise this row against this
     target at all. One case of it is mechanical rather than a matter of
     taste: the row's capability declares no `binding.tool`, so `emit` has no
     call to make and no shipped test could ever reach the cell.
     `not_yet_attempted` is the one wrong answer on such a row, because it tells
     the next round to work a cell no scenario can close. `rounds.closable_holes`
     filters such a hole out of the worklist, so the cost is not a wasted batch
     -- it is a document that tells the human at gate 2 the round is still
     working a cell nobody can work.
   - `out_of_scope` -- the row is real but deliberately outside what this
     suite is trying to cover.
   - `blocked_by_gap` -- the world model itself lacks the knowledge a
     scenario here would need. This one additionally requires `gap_id`,
     naming a real entry in the world model's `gaps`; `refs.check_coverage`
     reports a `gap_id` that resolves to nothing.

   When every row is covered, the honest `holes` is the empty array. Do not
   invent a hole to look thorough: a hole naming a covered row is a finding,
   and a fabricated one sends the next round to work on a cell that is
   already tested. `score-seal` copies each hole's `reason` and `justification`
   through untouched, so the words you write here are the words `rb-propose`
   reads next round -- and it checks the pairing both ways before it composes
   anything, which is Invariant 6.

8. **Work out whether this round added a cell, because step 9's verdict turns
   on it.** `new_cells_this_round` is the number of capability cells that are
   covered now and were *not* covered before this round;
   `rounds_without_progress` is the number of consecutive most-recent rounds
   that added no new cell by that same test. **You write neither number** --
   `rubrica score-seal` computes both, taking the baseline from the previous
   round's own `03-coverage/round-<N-1>.json` -- but `halted_no_progress` is
   yours to compute, so you have to reach the same reading it does, and it is
   derivable from the round tags and statuses in front of you.

   The derivation has one subtlety, and it is the whole of the rule: read
   "covered before this round" against the statuses **as you found them**,
   before your own rulings. A cell was already covered if some scenario tagged
   with an earlier round credits it and is still `proposed` or `active` in
   `02-scenarios.json` as you read it. Take the reading *after* your own
   rulings instead and it goes wrong in exactly the case this loop exists to
   handle: fold an earlier round's scenario into one of this round's claiming
   the same cell, and no *live* earlier-round scenario credits that cell any
   more, so the cell reads as new -- when it was covered when the earlier round
   was scored and nothing about the tested surface changed. That is the
   inflation this step has always warned about, arriving through the evaluation
   point rather than through the count.

   Read as you found it, the round-tag derivation and the seal's baseline agree,
   including after a rejection. A scenario some earlier dispatch already marked
   `rejected` is not live in the document you read; the row it credited was
   reopened when that rejection was recorded, and the seal's baseline document
   was recomputed then too -- so a scenario closing that row now is genuinely
   new by both readings.

   Round 1 has nothing earlier: every covered capability cell is new, and
   `rounds_without_progress` is 0 if this round covered a cell and 1 if it
   covered none. Goal rows are not cells and do not count here.
   `new_cells_this_round` inflated by counting cells an earlier round already
   covered is how a loop that has stopped making progress runs to the round cap
   anyway, which is what the evaluation point above protects.

9. **Compute `verdict`.** It is *computed here* and *acted on by the
   orchestrator*: this stage does not decide to iterate, does not dispatch
   another `rb-propose`, and does not stop the run. It writes the state of
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

   `score-seal` copies this value into the coverage document untouched and
   nothing downstream recomputes it, so the verdict the orchestrator branches
   on is the one you wrote. It has to be entailed by your own `holes` and the
   rows they leave: `continue` with no `not_yet_attempted` hole among them, or
   `converged` with one, is a single part contradicting itself.

10. **Write your part to `03-score/round-<N>.json`.** One document, carrying
    the `rulings`, the `holes` and the `verdict` -- and nothing you derived on
    the way to them. `<N>` is the round you derived in section 1, and
    `refs.check_score_parts` compares the `round` field against the filename,
    so a part cannot sit in one round and claim another. You do not write
    `02-scenarios.json`, `03-coverage/round-<N>.json` or
    `03-coverage/latest.json`: `propose-seal` folds your rulings into the first,
    and `score-seal` composes the other two, publishing `latest.json` as a byte
    copy of the round file rather than as a second composition that could drift
    from it.

## 4. Invariants

1. The capability rows you reason over are exactly the world model's drivable
   pairs: one per capability x outcome-class pair it declares whose capability
   also declares a `binding.tool` -- no pair of the denominator missing, none
   naming a capability or outcome class the world model does not declare, and
   none naming a cell no tool call can reach. Enumerate them from
   `capabilities` and their `outcome_classes`, never from the scenario list:
   `score-seal` enumerates that same drivable subset from the same file, so a
   hole set derived from the scenarios instead -- or a row set that scores the
   pairs no `binding.tool` can reach -- disagrees with the matrices it has to
   pair up with, and `refs.check_coverage` reports every direction by name. The
   cells you leave out here are not dropped: `score-seal` writes a computed
   `unreachable` hole for each one, which is what keeps the narrowed surface an
   honest denominator rather than a silent cap.

2. The goal rows are exactly the world model's `goals`, on the same terms:
   none omitted, none invented.

3. Your reading of `covered`, `total` and `pct` agrees with the rows you
   derived it from. You write none of the three -- they are what tells you how
   much of the surface your holes have to account for --
   and `refs._check_matrix_arithmetic` recomputes all three from the rows of
   the composed document.

4. Every ruling names a `scenario_id` that `02-scenarios.json` actually
   carries, and **no two rulings in one part name the same scenario.**
   `refs.check_score_parts` reports a ruling on a scenario the sealed document
   does not carry; `propose-seal` refuses a part that rules on one scenario
   twice, because a single dispatch contradicting itself is a defect and the
   sealed document would otherwise carry only the last of the two. Across two
   *rounds* the same pair is legitimate -- that is a later round overturning an
   earlier ruling, which section 2 sanctions outright.

5. A row the matrices will mark `covered` is credited to at least one scenario
   that is still `proposed` or `active` once your rulings are folded in. A
   rejection reopens the row, so a row whose every credit is `rejected` or
   `duplicate` is recomputed as uncovered and must be justified as a hole in
   this same part -- including when the rejection came from
   `rb-challenge` after this round and you are re-scoring because of it. The
   ruling without the hole is coverage that would be confidently wrong, which
   is why `refs.check_coverage` reports it by name and `score-seal` refuses to
   compose the report at all.

6. Every row the matrices will show uncovered has exactly one hole, and no hole
   names a row they will show covered. This is the invariant that decides
   whether the round produces a coverage document at all: `score-seal` checks
   both directions against the matrices it just computed and writes nothing
   when either fails, naming the ref it could not reconcile.

7. `denominator_version` is not a field of your part, and there is therefore no
   number here for you to get wrong: `score-seal` echoes the world model's
   `denominator.version` onto the report it composes. If you believe that
   version is wrong, that is still something to report rather than something to
   fix by writing a different one.

8. `round` does not exceed `manifest.limits.max_rounds`.
   `refs.check_limits` reports a coverage document scored for a round past
   the cap.

9. Every scenario you rule `duplicate` carries `duplicate_of` naming a
   scenario that exists and that is not itself a `duplicate` or a `rejected`
   one. `refs.check_score_parts` reports a fold onto a scenario the sealed
   document does not carry, a fold onto the scenario itself, and a fold onto
   one that is already discarded: a chain of
   folds ends at a survivor, or the cell it claimed has no live credit at
   all.

Before you report done, run `rubrica validate --stage score --run <run>`,
where `<run>` is the run directory you were dispatched with. `--run` is
required: without it the command exits 2 on a usage error and tells you
nothing about your artifact. If it reports a finding against what you just
wrote, that is not a finding to pass along -- it is your own defect to fix.
Repair the part and validate again; report success only once
`rubrica validate --stage score --run <run>` exits clean.

**Do not run `check-refs`, and note that it is not in your `invokes`.** Your
part alone cannot be checked against a coverage document `score-seal` has not
composed yet, and its rulings resolve against a `02-scenarios.json` that will
not carry them until `propose-seal` runs again -- so every checker that bears
on your output is reporting on artifacts that do not exist at the moment you
finish. A stage invoking a checker over artifacts it has not produced is the
shape that generated fabricated findings before. The orchestrator runs
`check-refs` after the seals, which is where those findings are real.

## 5. Refusal conditions

Every condition below is one where the correct output is not a tidier
report. The pull on this stage is arithmetical rather than narrative: the
tempting error is not an invented story, it is a judgment nudged until the
numbers come out better -- a row dropped from the derivation so the surface
looks smaller, a fold made so a cell stops needing a hole, a hole labelled as
closable so the loop keeps looking productive. Moving the arithmetic into
`score-seal` took the *transcription* of a wrong number away from you; it did
not take away the rulings that produce one, and a part whose holes honestly
account for a partial surface is worth more than one whose rulings were chosen
to make that surface read 100%, because every later judgment in this pipeline
is measured against the document composed from your part and none of them
re-derives the denominator.

- **A candidate pair is genuinely ambiguous -- arguably the same test,
  arguably not.** Keep both `active`, and say why in what you report for the
  orchestrator's decision -- not in a hole, because keeping both makes the
  shared cell covered, and step 7 and Invariant 6 both forbid a hole on a
  covered row. Folding a distinct test loses a cell for the whole run, and
  nothing downstream will ever notice it is missing; keeping a duplicate
  costs one wasted `rb-instantiate` fan-out. Prefer the cheaper error, and
  record that you made the call deliberately rather than leaving it to look
  like an oversight.

- **A cell cannot be covered because the world model has a gap.** Write the
  hole with `reason: "blocked_by_gap"` and the `gap_id` of the gap that
  blocks it. Never `not_yet_attempted` for such a cell: that reason says
  another round could close it, and no round can -- `rb-propose` reading it
  will spend a round designing a scenario that `rb-instantiate` cannot
  honestly seed, and the run will burn its cap without closing anything.

- **The scenario list claims a cell the world model does not have.** Do not
  write a hole for that cell to make the accounting balance, and do not
  quietly drop the claim either. The rows are the world model's, so reason
  over them as it defines them and report the mismatch: `check-refs` layer 2
  will name the scenario's dangling `capability_refs` entry, and the real
  finding is upstream -- a propose member produced a scenario against a cell
  that does not exist, which no ruling of yours can repair. `score-seal`
  refuses a hole naming a ref the world model does not declare, so writing one
  would stop the round while still pointing at the wrong stage.

- **Your `holes` or your `verdict` disagrees with the rows you derived.** A
  row you know will come out uncovered with no hole beside it, a hole on a row
  your own rulings leave covered, or a `verdict` the hole set does not entail:
  in every case redo the derivation from the world model's rows and the
  statuses your rulings leave, and never adjust the hole set or the verdict to
  match the answer you expected. This is the last place in the loop where such
  a disagreement is still repairable by a judgment: `score-seal` refuses to
  compose a report from a part that carries one, and it names the ref rather
  than guessing which half you meant. What you must not do is pick the reading
  that produces the tidier number -- your rulings and your holes go into a
  document that will agree with itself either way, and
  `refs._check_matrix_arithmetic` recounting `covered`, `total` and `pct`
  cannot tell that a fold should never have been made.
