---
name: rb-propose
description: One fan-out member per batch of closable coverage holes: design a scenario a real actor would actually want for each hole your own batch names, and write them as your own part -- never a sibling's holes, and never the accumulating scenario list.
---

# rb-propose

You are one member of this round's propose fan-out. `rubrica propose-batches`
has already partitioned this round's closable holes into batches small enough
for one dispatch to write, and you were dispatched with exactly one
`batch_id` -- yours. A sibling member is doing the same thing for a different
batch right now, and neither of you will see the other's output. Your job is
narrow: take the holes in *your* batch and write one new scenario per hole you
can honestly close. You are not the stage that judges a scenario's fate -- that
is `rb-score`, one stage downstream of you both in round order and in
authority. Every scenario you write starts its life exactly the same way:
`status: "proposed"`, and nothing else.

Round 1 runs against a world model alone, after the `reconcile-*` passes and
`rubrica reconcile-seal` have produced one; round 2 and later run against the
coverage report `rb-score` and `rubrica score-seal` composed for the round
before. Either way, the reading that turns a coverage report into a worklist
has already happened before you are dispatched: what reaches you is a list of
hole refs.

## Contract

```toml
stage = "propose"
reads = ["manifest", "world_model", "batches", "coverage_latest"]
writes = ["scenario_part"]
schemas = ["scenarios-part"]
invokes = ["validate"]
```

## 1. Inputs

You read exactly four things, matching the four names this skill's contract
declares under `reads`: `manifest.json` (`manifest`),
`01-world-model.json` (`world_model`), this round's batch plan
`02-batches/round-<N>.json` (`batches`), and `03-coverage/latest.json`
(`coverage_latest`) if it already exists. Nothing else on disk is yours to
read -- not a claims file, not an instance directory, not a verdict, and not a
sibling member's part.

**You are dispatched with one further thing, and it is an address rather than
context: your own `batch_id`.** Find the entry in the plan's `batches` array
whose `id` is that value, and take that entry's `hole_refs` as your **entire**
worklist. Nobody tells you which round this is either: the round is the
highest-numbered `round-<N>.json` under `02-batches/`, and that document's own
`round` field states it -- so the plan is where both the round number and the
worklist come from.

The plan lists every batch of the round, not only yours, for the same reason
`01-subjects.json` lists every subject to each `rb-reconcile-contradict`
member: one document read by every member is how a member finds its own slice
without anybody pasting the slice into its prompt. **Holes outside your batch
are not yours to close; a sibling member has them.** Do not propose against
one, do not "help" a sibling by taking a hole you can see is easy, and do not
widen a scenario's `provenance.hole_refs` to a ref the plan assigned
elsewhere. `refs.check_scenario_parts` resolves every hole your scenarios
declare against the batch the plan gives it to and names each one that belongs
to a sibling -- and it is the only layer that can, because a member that
wandered into a sibling's holes writes a part byte-identical to one that did
not.

`coverage_latest` is where a hole's `reason` and its context live: your batch
carries bare refs, and the report says what each ref's row is and why it is
still open. In round 1 there is no coverage report at all -- nobody has scored
anything yet -- so every capability x outcome-class cell in the world model's
denominator and every goal is an open hole by default, which is exactly the
worklist `propose-batches` partitioned. `coverage_latest` not existing is
therefore the normal shape of round 1, not a missing file to report or work
around.

The manifest is there for its `limits` alone -- `max_rounds` and
`max_scenarios`, the two bounds Invariants 5 and 6 hold you to -- and for
nothing else; it is this run's configuration, not evidence about the target.
The world model is frozen input for you: its
`goal_id`s, `actor_id`s, capabilities, and outcome classes are the entire
universe a scenario may be built from, and its `denominator` is the only
authority for how large that universe is.

**`02-scenarios.json` is on neither side of your contract, and both absences
are the design rather than an omission.** You do not *read* it: a hole reaches
your batch only because its `reason` is `not_yet_attempted`, which by
definition means no scenario covers it, so the accumulating document holds
nothing your worklist does not already tell you -- and if two members do write
one test twice, `rb-score` folds the duplicate pair, which is the judgment that
exists for exactly that. You do not *write* it either: `rubrica propose-seal`
assembles it from every part of every round. An append performed by every
member on one shared file is a response that grows with the whole run rather
than with this member's work, and a member that rewrote that file would
overwrite a sibling's scenarios with no gate anywhere able to report the loss.

You are dispatched with no memory of any conversation that came before you,
and nothing you write here carries forward as memory either. Whatever you
need to do this job -- which round this is, which holes are yours, what a
hole's `reason` means, what a `discriminating_fact` has to do -- has to be
either in this document or in the files you just read. If it is not in one of
those places, you do not have it, and inventing it is confabulation, not
recollection.

Everything above is about which *files* you may read. There is a second,
easier-to-miss boundary: what you may *know*. A scenario may rest only on
what the world model actually declares for this target -- not on what a
test suite for a system like this one usually contains, not on which case a
benchmark would typically probe, not on a capability or a user goal that
would be "obviously" worth testing if this were some other, more familiar
system. The tell is specific to this stage: if you find yourself reaching
for a scenario because it is the kind of case a good test suite generally
has -- an auth-failure case, a pagination case, a bulk-operation case -- and
only afterward checking whether the world model happens to support it,
you have it backwards. Every scenario has to start from an actual open cell
in the world model's coverage and an actual goal in its `goals` list, and
work outward from there to a plausible user intent -- never the reverse.
A scenario justified by "tests like this always cover X" is exactly how an
outcome class the world model never declared, or a goal nobody stated, gets
written into a scenario that looks perfectly reasonable and cites nothing
real. Refusal conditions 2 and 3 in section 5 name the two ways that
back door opens.

## 2. Output

One `scenarios-part-0.1.json`-shaped document, written to
`02-scenarios/round-<N>/<batch_id>.json` (`scenario_part`) -- the round from
the plan, and your own batch id, no other. It carries
`schema_version: "0.1"`, `round`, `batch_id`, and a `scenarios` array holding
**only** the scenarios you wrote for your own batch: never a sibling's, never
an earlier round's, and never a re-emit of anything already sealed.

**Write the part even when you wrote no scenario.** An empty `scenarios` array
is not a non-answer -- it is the record that this batch was worked and could
not be closed, which is what section 5 exists to produce, and the schema
carries no `minItems` for exactly that reason.
`refs.check_scenario_parts` requires a file per batch rather than a non-empty
one, because a missing file cannot be told apart from a member that was never
dispatched at all.

**Every scenario `id` you mint must begin `sc-<batch_id>-`** -- `sc-r1-b03-01`,
`sc-r1-b03-02`, and so on, for your own batch id. Members mint their own ids and
no member can see a sibling's part, so that prefix is the whole of what stops
two members choosing the same id. Your batch id carries its round, so numbering
from your own position is safe against every *other* round as well: you never
have to know which ids an earlier round already took, and you must not go
looking for them. `rubrica propose-seal` refuses a collision
rather than carrying the id twice, and it writes nothing at all when it
refuses -- so one member ignoring the prefix costs the whole round's seal, not
just its own part.

Each scenario you write is an object with `id`, `round`, `goal_id`,
`actor_id`, `title`, `user_intent`, `hop_depth`, `capability_refs`,
`discriminating_fact`, `status`, and `provenance`. All of these are required
by the schema; an incomplete scenario is a validation failure, not a smaller
scenario.

**`02-scenarios/round-<N>/` does not exist until the round's first member
writes into it, and creating it is not your job.** Nothing in `src/rubrica/`
mkdirs it -- your `Write` brings it into being, parents and all, whether you
are the first member of the round or the last. **Do not reach for `mkdir`.**
This project's dispatch allows `rubrica *` through Bash and nothing else, so
the command lands on an approval prompt that `claude -p` cannot answer, and
the triage family's fan-out measurably lost turns to exactly that mistake.

Note what the part has no room for: `scenarios-part-0.1.json` is
`additionalProperties: false`, and it carries no `denominator_version`. That
field belongs to the sealed document, where `propose-seal` echoes the world
model's `denominator.version` onto it -- so a version you believe is stale is
still something to report rather than a number to write, and Invariant 3 is
about the three header fields you *do* write.

## 3. Method

1. **Read the world model.** It is your only source for `goal_id`s,
   `actor_id`s, capabilities, and outcome classes -- every value you write
   into a scenario's `goal_id`, `actor_id`, or `capability_refs` must trace
   back to something declared there.

2. **Read your own batch out of this round's plan.** Open
   `02-batches/round-<N>.json` for the highest `N` on disk, find the entry of
   its `batches` array whose `id` equals the `batch_id` you were dispatched
   with, and take that entry's `hole_refs` as your worklist and the document's
   `round` as your round. If no entry carries your id, stop: write no part at
   all -- a part for a batch the plan does not declare is a
   `refs.check_scenario_parts` finding, and inventing a batch id to write under
   would put a file where the seal expects none -- and report that the id you
   were dispatched with is not in the plan. That is a dispatch defect the
   orchestrator has to fix; it is not a reason to pick a batch yourself.

3. **Read the coverage report, if one exists**, for the `reason` and the
   context behind each of your refs. In round 1 it is not there, and that is
   the normal case described in section 1: every cell and every goal was open,
   which is why the plan holds the refs it does.

4. **Write only your own part, and nothing outside
   `02-scenarios/round-<N>/`.** Your part is the only file you create. You do
   not touch `02-scenarios.json`, you do not touch a sibling's part under the
   same round directory, and you do not touch an earlier round's directory --
   every scenario any earlier round wrote keeps its id, its round, its
   provenance, and its `status` exactly as its own part recorded it, because
   `propose-seal` reassembles the sealed document out of the parts every time
   it runs. An existing scenario's `status` is not yours to change under any
   circumstance: `rb-score` owns that transition, and changing it here would
   be you exercising a judgment that is not delegated to this stage.

5. **Check every hole in your batch, and target every one you can close.**
   The partition already filtered for closability, so in the ordinary case
   every ref in your `hole_refs` is a hole a new scenario can close. Check it
   anyway against `coverage_latest`, because a ref whose `reason` there is not
   closable is a defect in the plan you were dispatched with rather than work
   you may do. A hole's `reason` is one of exactly four values:
   `not_yet_attempted`, `unreachable`, `out_of_scope`, or
   `blocked_by_gap`. Only `not_yet_attempted` is something a new scenario can
   close -- it means nobody has proposed against that cell or goal yet, and a
   well-formed scenario closes it. The other three are not closable by
   proposing, no matter how good the scenario: `unreachable` and
   `out_of_scope` mean the cell is not one this suite is trying to cover at
   all, and `blocked_by_gap` means the world model itself does not yet have
   enough information to support a scenario there -- some earlier stage's
   gap has to be resolved first, and proposing anyway produces a scenario
   `rb-instantiate` cannot honestly seed. Do not propose against a hole whose
   `reason` is any of those three.

   Among the closable holes, an absence- or error-shaped outcome class
   (`not_found`, `empty`, `error`, `underspecified`) is a cell in the
   denominator exactly like `success` is -- not a lesser one, and not one to
   leave for a later round. The denominator this stage works against is
   capability x outcome class, so a round that closes every `success` cell
   for every capability while every `not_found` or `error` cell on the same
   capabilities sits at `not_yet_attempted` has not covered less of the
   surface by accident -- it has quietly covered the same corner of it
   repeatedly instead. Take every closable hole in your batch, not only the
   ones that happen to be easiest to reach for first.

6. **For each targeted hole, design a scenario a real actor would actually
   want.** Pick a `goal_id` and an `actor_id` from the world model's frozen
   lists -- never invent either -- and phrase `user_intent` the way that
   actor would actually say it, not as a restatement of the hole or the
   capability's name. Set `capability_refs` to name exactly the capability x
   outcome-class cells this scenario claims to exercise: no more cells than
   the scenario genuinely visits, and no fewer than the ones the hole you are
   targeting requires.

   An absence- or error-shaped hole takes real, extra work to design a
   believable `user_intent` for: you have to imagine an actor who wants the
   thing that turns out not to be there, or who does something that turns
   out to be invalid, which is a harder sentence to write honestly than "an
   actor who wants the thing and gets it." That extra difficulty is exactly
   the design work this step is asking for, on that hole's own terms as a
   real open cell in this run's coverage report -- not a reason to defer the
   hole, and not license to reach for an absence case because good test
   suites in general are supposed to have some.

7. **Declare the `discriminating_fact`.** State the single fact this
   scenario's test hinges on, phrased so specifically that `rb-instantiate`
   can build a seed world in which that fact is *uniquely* determined -- not
   one of several worlds that would each make the scenario pass. "The query
   returns some rows" is not discriminating: it is true of almost any seed.
   "The query for queue `billing` returns exactly one ticket, and that
   ticket's `status` is `closed`" is the shape of fact that pins down a
   specific world. If you cannot state a fact this precise for a hole, that
   is refusal condition 4 in section 5, not a reason to write a vaguer one.

   Uniqueness is not the only thing to get right here, and an earlier
   version of this section drew the next distinction in the wrong place.
   The world model declares two different kinds of thing, and only one of
   them is something you may not invent.

   **Ids that structure the world model** -- a capability id, an
   outcome-class id, a goal id, an actor id, an entity or field *name* --
   are real, checkable entries in the file you actually read. Every one you
   write into a scenario must be one of them: naming a `capability_id` or
   `outcome_class_id` the world model does not declare is the same failure
   as inventing a capability, because it points `rb-instantiate` at
   something that does not exist. That is refusal condition 2's territory
   in section 5, and Invariant 1 checks it directly.

   **Field values are not the same kind of thing, and must not be treated
   as if they were.** What a queue is actually called, what a status value
   actually is, an id, a count -- the world model records field *names* and
   *types* (`entity.fields[].name`/`.type`) but never their value domains,
   and you never read a claims file, so you have no honest way to know what
   any particular value is for the real target. A concrete field value in a
   `discriminating_fact` is therefore always a prescription to
   `rb-instantiate` about what to build, never a claim about what the
   target already has. `queue: "billing"` is exactly as legitimate to write
   as `queue: "sales"` or `queue: "q-north"` -- none of the three is a claim
   about the target, all three are equally valid instructions -- and this
   is what makes uniqueness satisfiable at all: without naming some
   concrete value, nothing you write can pin a seed down, because making
   that value real is instantiate's job, not yours.

   A real run already got this backwards, and the failure is worth reading
   because it names the actual risk precisely: warned against naming a
   field value it could not verify, one round produced "`find_tickets` is
   called with a queue and status filter combination for which the seed
   contains zero tickets, so the call returns an empty result set rather
   than any match" -- no queue, no status, no count, nothing concrete
   anywhere. That fact fails uniqueness exactly as "the query returns some
   rows" does: `rb-instantiate` reading it has near-total freedom to build
   any world with some empty combination somewhere, not the one specific
   world this scenario means to test. The fix was never to avoid naming a
   queue -- any concrete queue name would have done just as well -- the fix
   was to name one specifically enough that only a single seed satisfies
   the sentence.

   This bites hardest on absence and error cells, precisely the ones step 5
   and step 6 just told you not to defer. An outcome class described as, say,
   "no ticket matches the filters" is satisfied by a query against any
   queue holding nothing that matches, so naming one specific queue and one
   specific status for it is not a claim that queue is special in some way
   you cannot verify -- it is exactly the same kind of prescription a
   success-cell fact makes. Leaving it vague out of a misplaced worry about
   "inventing" a queue name is the uniqueness failure above, not a caution
   this stage owes anyone.

8. **Set `hop_depth` honestly, and make it consistent with `capability_refs`.**
   `hop_depth` is the number of tool calls this scenario genuinely requires
   to reach its `discriminating_fact` -- not a difficulty rating and not a
   round number picked for variety. A `hop_depth` of 2 backed by a single
   `capability_refs` entry needs an explanation the scenario itself makes
   obvious (a lookup that must run twice to compare two results, say). If you
   cannot state that reason, the depth is not merely unexplained, it is
   wrong -- lower it to the number of calls the scenario actually requires
   before you write it down; an inflated depth left uncorrected on the theory
   that a later stage will catch it is exactly the offloading this document
   asks you not to do elsewhere. Getting this wrong has a real cost:
   `rb-challenge` independently measures the minimum number of calls a
   solution actually needs and flags `difficulty_overstated` when your claim
   is above what it needed, spending that stage's finding budget on a defect
   this stage chose to create instead of catching before it shipped. The
   opposite error is worse and it is the one this stage must not make: a
   depth *below* the calls the scenario really requires is flagged
   `difficulty_understated`, and nothing downstream can repair it, because
   `hop_depth` is in a file only this stage writes. It ships. Coverage is
   credited per hop depth, so a scenario tagged shallower than it is credits
   a depth nothing actually tests, and the matrix reports covered what was
   never covered. The count includes every call a solving agent cannot skip,
   the lookups among them: if the `user_intent` names an entity by a label
   and the capability takes an id, the call that resolves one to the other
   is part of the depth, and the capability that serves it belongs in
   `capability_refs`. Set
   `status: "proposed"` on every scenario you write, full stop -- never
   `active`, `duplicate`, or `rejected`. Those three are outcomes only
   `rb-score` can assign, after it has actually run its judgment over the
   scenario: `active` means score has accepted it, `duplicate` means score's
   dedupe ruling matched it against an existing scenario, and `rejected`
   means score turned it down for a stated reason. None of those three
   judgments is one you are entitled to make at proposal time, no matter how
   confident you are that a scenario will turn out to be good, redundant, or
   bad.

9. **Fill `provenance` completely.** `hole_refs` names every cell or goal
   this scenario targets, in the `cell:<capability_id>/<outcome_class_id>` or
   `goal:<goal_id>` form the schema requires -- and **every ref in it must be
   one your own batch owns.** That array is your declaration of what you
   targeted, so it is what `refs.check_scenario_parts` resolves against the
   plan: a ref the plan gave to a sibling is reported against your part, and a
   ref the plan gave to no batch at all is reported as a hole nobody was
   dispatched to close. `claim_ids` names the claims (visible to you only
   through the world model's own citations) the scenario's design actually
   rests on; `round` is this round. Both `round` (the scenario's own field) and
   `provenance.round` must be the round the plan declares, and neither may
   exceed `manifest.limits.max_rounds`.

Before you report done, run `rubrica validate --stage propose --run <run>`,
where `<run>` is the run directory you were dispatched with. `--run` is
required: without it the command exits 2 on a usage error and tells you
nothing about your artifact. If it reports anything wrong with the file you
just wrote, that is not a finding to pass along -- it is your own defect to
fix. Repair the artifact and validate again.

Read each finding's path before you act on it, because **that command is
run-global and you are one of several members running right now.**
`validate --stage propose` schema-checks the part of *every* batch of every round
that has one on disk, so it can hand you a sibling's defect, or a sibling's
half-written file caught mid-write, in the same output as your own findings. A
finding naming another batch's part under `02-scenarios/round-<N>/` is **not
yours**. It is not a reason to wait for the siblings to settle, not a reason to
re-run the command hoping it clears, and above all not a reason to open or repair
that file -- doing that is the fan-out violation section 1 and the last refusal
condition exist to prevent, and a non-clean exit code is not authorisation to
cross the boundary.

So the bar for reporting success is: no finding anywhere in that command's output
names `02-scenarios/round-<N>/<your batch_id>.json`. If findings naming other
batches' parts remain, you are still done -- say so in what you report, and name
those paths, because the orchestrator is the one party entitled to look at every
batch at once and the only one that can act on them.

**Do not run `check-refs`, and note that it is not in your `invokes`.**
`refs.check_scenario_parts` is the layer-2 gate on your part, and it reports every
batch of the round with no part on disk from the moment the round directory
exists -- so while the fan-out is running it names your siblings by construction.
The orchestrator runs it once after every member has landed, which is where those
findings are real.

## 4. Invariants

1. Every `capability_refs[]` pair names a `capability_id` and an
   `outcome_class_id` that are both real -- an actual capability and an
   actual outcome class of that capability, as declared in the world model.

2. Every `provenance.hole_refs[]` entry names a real cell
   (`cell:<cap>/<oc>`) or a real goal (`goal:<id>`) **that your own batch
   owns** -- never a plausible-looking id you made up to fit the pattern, and
   never a ref this round's plan assigned to another batch.
   `refs.check_scenario_parts` reports the two the round can tell apart
   separately: a ref no batch of the round owns at all, which is where an
   invented id lands, and a ref the plan gave to a named sibling. The own-batch
   half is the one no schema and no other layer can see.

3. The part's three header fields are your own: `round` is the round the plan
   declares and the round directory you wrote into, and `batch_id` is the id
   you were dispatched with. `refs.check_scenario_parts` compares the field
   against the filename, because the filename is the batch you were dispatched
   with and the field is the batch you believed you were working on, and a
   disagreement means one member wrote a sibling's slice.

4. Every scenario `id` begins `sc-<batch_id>-` and is unique within your part.
   The prefix is what makes it unique across the round -- and, because a batch id
   carries its round, across every other round too. That is the only guarantee
   available to a member that cannot see a sibling's ids, and it is why numbering
   from your own batch's position is sufficient rather than merely conventional.
   **Nothing checks the prefix**, and that is why it is yours to keep: the seal
   refuses an actual *collision* -- two parts carrying one id -- and writes
   nothing when it does, but an id without the prefix that happens not to collide
   is sealed as written, by every layer, silently. So the prefix buys a
   probability, and dropping it spends the whole round's seal on the throw.

5. `round` and `provenance.round` are both the current round, and neither
   exceeds `manifest.limits.max_rounds`. `refs.check_limits` reports both a
   scenario's `round` and its `provenance.round` separately if either is
   over the cap.

6. You write at most one scenario per hole in your batch, so your part carries
   no more scenarios than your batch has `hole_refs`. That is the only term of
   `manifest.limits.max_scenarios` you can evaluate: the run-wide count of
   `proposed` and `active` scenarios spans every batch and every round, you
   read neither the sealed document nor a sibling's part, and
   `refs.check_limits` is what reports an overflow -- against the sealed
   `02-scenarios.json`, which no member wrote. One scenario per hole is
   therefore your own obligation rather than a check you can lean on, and
   section 5's last condition says what to do when your batch alone does not
   fit under the cap.

7. Every scenario you write carries `status: "proposed"` -- never `active`,
   `duplicate`, or `rejected`. Those three belong to `rb-score` alone.
   **No layer catches this one either**, and the asymmetry with the invariants
   above is worth seeing: the sealed scenario's `status` enum admits all four
   values, because a sealed scenario legitimately carries any of them, so a part
   claiming `active` is schema-valid and reaches `02-scenarios.json` as a
   promotion nobody judged. It is counted, instantiated and emitted from there.
   This is the one invariant here whose whole enforcement is your own care.

## 5. Refusal conditions

Every condition below is one where the correct output is not a scenario --
it is a statement that proposing one would be dishonest, plus, where you
can, a report of what is actually blocking progress. Writing that statement
is success, not failure: a hole left open with a clear reason is something
`rb-score` and the orchestrator can act on, and a scenario forced into
existence to avoid an empty part is not a smaller version of doing this job
right, it is the confabulation this stage exists to prevent. A part with fewer
scenarios than your batch has holes is how you record it -- an honest, gated
artifact naming exactly what you closed, rather than a silent gap.

- **A hole's `reason` is `blocked_by_gap`.** Do not propose against it. Say
  which gap is blocking it (its `gap_id`, and in your own words what it
  is missing), and stop there. Proposing anyway hands `rb-instantiate` a
  scenario it cannot honestly seed, because the missing knowledge the gap
  names is exactly what a seed would need to be built around.

- **Closing a hole would require a capability or outcome class the world
  model does not declare.** Do not propose it, and do not reach for it
  through convention -- the tell in section 1 is exactly this: a scenario
  that "should" exist because systems like this one usually support it, when
  nothing in `capabilities` or its `outcome_classes` actually says so. Report
  that the world model needs an amendment. That costs an orchestrator
  decision and a `denominator_version` bump; it is not a decision this stage
  gets to make on its own by writing the scenario anyway and hoping the
  capability turns out to exist.

- **The goal list has no goal your scenario would serve.** Do not invent
  one, and do not reach for one because it is the kind of goal a user of a
  system like this would obviously have. A goal-based denominator that this
  stage could also invent goals into is not a real denominator -- it is a
  number this stage can inflate its own coverage against, and every goal it
  invents this way is a fact nobody in the pipeline actually established.
  Report that the goal is missing rather than filling the gap yourself.

- **You cannot state a `discriminating_fact` that is uniquely determined.**
  Do not propose the scenario with a vaguer fact instead. A scenario whose
  fact does not pin down a specific world is one `rb-instantiate` builds
  arbitrarily, and the resulting expected answer is a label nobody can
  actually defend, because a different, equally valid seed would have
  produced a different answer to the same scenario.

- **`max_scenarios` cannot accommodate the batch you were given.** Compare
  `manifest.limits.max_scenarios` with the number of `hole_refs` in your own
  batch: if your batch alone names more holes than the run's whole ceiling
  allows live scenarios, do not write the excess. Write the scenarios that fit,
  and report how many holes you left open and which ones, so the orchestrator
  can decide with `rubrica set-limit` whether to raise the cap or accept the
  gap. Do not propose past the cap on the theory that `check-refs` will simply
  catch and discard the overflow later -- it reports the overflow against the
  sealed `02-scenarios.json` that `propose-seal` wrote, which is an artifact no
  re-dispatch of any member can repair. And do not overshoot in the other
  direction either: a member that writes two scenarios for one hole to look
  thorough has spent a slot the partition allocated to a hole nobody else will
  reach.
