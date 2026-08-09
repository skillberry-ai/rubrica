---
name: tg-propose
description: Read the reconciled world model and the latest coverage report, then append scenarios that target real, closable holes in the coverage denominator -- never rewriting or renumbering what an earlier round already proposed.
---

# tg-propose

You are dispatched once per round, after `tg-reconcile` has produced a world
model (round 1) or after `tg-score` has produced a coverage report against
the scenarios already on file (round 2 and later). Your job is narrow: find
the holes in that coverage report that proposing a scenario can actually
close, and write one new scenario per hole you target. You are not the stage
that judges a scenario's fate -- that is `tg-score`, one stage downstream of
you both in round order and in authority. Every scenario you write starts its
life exactly the same way: `status: "proposed"`, and nothing else.

## Contract

```toml
stage = "propose"
reads = ["world_model", "scenarios", "coverage_latest"]
writes = ["scenarios"]
schemas = ["scenarios"]
invokes = ["validate"]
```

## 1. Inputs

You read exactly three things, matching the three names this skill's
contract declares under `reads`: `01-world-model.json` (`world_model`), the
existing `02-scenarios.json` (`scenarios`) if one already exists, and
`03-coverage/latest.json` (`coverage_latest`) if it already exists. Nothing
else on disk is yours to read -- not a claims file, not an instance
directory, not a verdict. The world model is frozen input for you: its
`goal_id`s, `actor_id`s, capabilities, and outcome classes are the entire
universe a scenario may be built from, and its `denominator` is the only
authority for how large that universe is.

`coverage_latest` not existing is not an error. In round 1 there is no prior
coverage report at all -- nobody has scored anything yet -- so treat every
capability x outcome-class cell in the world model's denominator, and every
goal, as an open hole by default and proceed exactly as if a coverage report
had listed all of them. This is the normal shape of round 1, not a missing
file to report or work around.

`scenarios` appears in your `reads` and your `writes` for the same reason:
`02-scenarios.json` is append-only across the whole run. If it already
exists, round 2 is reading round 1's scenarios, not starting over, and every
id already in that file -- including any `duplicate` or `rejected` one --
stays exactly as written. You add to the file; you do not rewrite it, you do
not renumber it, and you do not touch any field of a scenario you did not
just create. In particular, an existing scenario's `status` is never yours
to change: that transition belongs entirely to `tg-score`, described in
Method step 7 and Invariant 7 below.

You are dispatched with no memory of any conversation that came before you,
and nothing you write here carries forward as memory either. Whatever you
need to do this job -- which round this is, what a hole's `reason` means,
what a `discriminating_fact` has to do -- has to be either in this document
or in the three files you just read. If it is not in one of those four
places, you do not have it, and inventing it is confabulation, not
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

One `scenarios-0.1.json`-shaped document, written to `02-scenarios.json`
(`scenarios`). It carries `schema_version: "0.1"`, a `denominator_version`,
and a `scenarios` array holding every scenario written in every round so
far, including the ones you add now. If the file already exists, you are
extending its `scenarios` array in place -- read it, keep every entry
exactly as it is, and append your new entries after it; you never emit a
file with fewer entries than the one you read, and never emit one where an
existing entry's fields differ from what you read.

Each scenario you write is an object with `id`, `round`, `goal_id`,
`actor_id`, `title`, `user_intent`, `hop_depth`, `capability_refs`,
`discriminating_fact`, `status`, and `provenance`. All of these are required
by the schema; an incomplete scenario is a validation failure, not a smaller
scenario.

## 3. Method

1. **Read the world model.** It is your only source for `goal_id`s,
   `actor_id`s, capabilities, and outcome classes -- every value you write
   into a scenario's `goal_id`, `actor_id`, or `capability_refs` must trace
   back to something declared there.

2. **Read the coverage report, if one exists.** Read `03-coverage/latest.json`
   if it is present. In round 1 it is not, and that is the normal case
   described in section 1: treat every capability x outcome-class cell and
   every goal as an open hole. When it does exist, its `holes` array is your
   worklist -- each hole names a `ref` (a cell or a goal) and a `reason` for
   why it is still open.

3. **Read the existing scenarios file, if one exists, and append -- never
   rewrite or renumber.** Every scenario already in `02-scenarios.json` keeps
   its id, its round, its provenance, and its `status` exactly as written.
   An existing scenario's `status` is not yours to change under any
   circumstance: `tg-score` owns that transition, and changing it here would
   be you exercising a judgment that is not delegated to this stage.

4. **Pick the holes you will target.** A hole's `reason` is one of exactly
   four values: `not_yet_attempted`, `unreachable`, `out_of_scope`, or
   `blocked_by_gap`. Only `not_yet_attempted` is something a new scenario can
   close -- it means nobody has proposed against that cell or goal yet, and a
   well-formed scenario closes it. The other three are not closable by
   proposing, no matter how good the scenario: `unreachable` and
   `out_of_scope` mean the cell is not one this suite is trying to cover at
   all, and `blocked_by_gap` means the world model itself does not yet have
   enough information to support a scenario there -- some earlier stage's
   gap has to be resolved first, and proposing anyway produces a scenario
   `tg-instantiate` cannot honestly seed. Do not propose against a hole whose
   `reason` is any of those three.

   Among the closable holes, an absence- or error-shaped outcome class
   (`not_found`, `empty`, `error`, `underspecified`) is a cell in the
   denominator exactly like `success` is -- not a lesser one, and not one to
   leave for a later round. The denominator this stage works against is
   capability x outcome class, so a round that closes every `success` cell
   for every capability while every `not_found` or `error` cell on the same
   capabilities sits at `not_yet_attempted` has not covered less of the
   surface by accident -- it has quietly covered the same corner of it
   repeatedly instead. Take every closable hole in front of you, not only the
   ones that happen to be easiest to reach for first.

5. **For each targeted hole, design a scenario a real actor would actually
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

6. **Declare the `discriminating_fact`.** State the single fact this
   scenario's test hinges on, phrased so specifically that `tg-instantiate`
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
   as inventing a capability, because it points `tg-instantiate` at
   something that does not exist. That is refusal condition 2's territory
   in section 5, and Invariant 1 checks it directly.

   **Field values are not the same kind of thing, and must not be treated
   as if they were.** What a queue is actually called, what a status value
   actually is, an id, a count -- the world model records field *names* and
   *types* (`entity.fields[].name`/`.type`) but never their value domains,
   and you never read a claims file, so you have no honest way to know what
   any particular value is for the real target. A concrete field value in a
   `discriminating_fact` is therefore always a prescription to
   `tg-instantiate` about what to build, never a claim about what the
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
   rows" does: `tg-instantiate` reading it has near-total freedom to build
   any world with some empty combination somewhere, not the one specific
   world this scenario means to test. The fix was never to avoid naming a
   queue -- any concrete queue name would have done just as well -- the fix
   was to name one specifically enough that only a single seed satisfies
   the sentence.

   This bites hardest on absence and error cells, precisely the ones step 4
   and step 5 just told you not to defer. An outcome class described as, say,
   "no ticket matches the filters" is satisfied by a query against any
   queue holding nothing that matches, so naming one specific queue and one
   specific status for it is not a claim that queue is special in some way
   you cannot verify -- it is exactly the same kind of prescription a
   success-cell fact makes. Leaving it vague out of a misplaced worry about
   "inventing" a queue name is the uniqueness failure above, not a caution
   this stage owes anyone.

7. **Set `hop_depth` honestly, and make it consistent with `capability_refs`.**
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
   `tg-challenge` independently measures the minimum number of calls a
   solution actually needs and flags `difficulty_overstated` when your claim
   does not match, spending that stage's finding budget on a defect this
   stage chose to create instead of catching before it shipped. Set
   `status: "proposed"` on every scenario you write, full stop -- never
   `active`, `duplicate`, or `rejected`. Those three are outcomes only
   `tg-score` can assign, after it has actually run its judgment over the
   scenario: `active` means score has accepted it, `duplicate` means score's
   dedupe ruling matched it against an existing scenario, and `rejected`
   means score turned it down for a stated reason. None of those three
   judgments is one you are entitled to make at proposal time, no matter how
   confident you are that a scenario will turn out to be good, redundant, or
   bad.

8. **Fill `provenance` completely.** `hole_refs` names every cell or goal
   this scenario targets, in the `cell:<capability_id>/<outcome_class_id>` or
   `goal:<goal_id>` form the schema requires; `claim_ids` names the claims
   (visible to you only through the world model's own citations) the
   scenario's design actually rests on; `round` is the current round. Both
   `round` (the scenario's own field) and `provenance.round` must be the
   current round, and neither may exceed `manifest.limits.max_rounds`.

## 4. Invariants

1. Every `capability_refs[]` pair names a `capability_id` and an
   `outcome_class_id` that are both real -- an actual capability and an
   actual outcome class of that capability, as declared in the world model.

2. Every `provenance.hole_refs[]` entry names a real cell (`cell:<cap>/<oc>`)
   or a real goal (`goal:<id>`) -- something the world model or the coverage
   report actually names, never a plausible-looking id you made up to fit
   the pattern.

3. `denominator_version` equals the world model's `denominator.version`,
   exactly. If you believe that version is wrong or stale, that belief is a
   refusal condition (section 5) to report, not something you may fix by
   writing a different number.

4. Every scenario `id` is unique across the *entire* file -- including every
   scenario an earlier round wrote, not only the ones you are adding now.

5. `round` and `provenance.round` are both the current round, and neither
   exceeds `manifest.limits.max_rounds`. `refs.check_limits` reports both a
   scenario's `round` and its `provenance.round` separately if either is
   over the cap.

6. The count of scenarios whose `status` is `proposed` or `active`, across
   the whole file, does not exceed `manifest.limits.max_scenarios`.
   `duplicate` and `rejected` scenarios never count against this cap.

7. Every scenario you write carries `status: "proposed"` -- never `active`,
   `duplicate`, or `rejected`. Those three belong to `tg-score` alone.

Before you report done, run `testgen validate --stage propose`. If it
reports anything wrong with the file you just wrote, that is not a finding
to pass along -- it is your own defect to fix. Repair the artifact and
validate again; report success only once `testgen validate --stage propose`
exits clean.

## 5. Refusal conditions

Every condition below is one where the correct output is not a scenario --
it is a statement that proposing one would be dishonest, plus, where you
can, a report of what is actually blocking progress. Writing that statement
is success, not failure: a hole left open with a clear reason is something
`tg-score` and the orchestrator can act on, and a scenario forced into
existence to avoid an empty round is not a smaller version of doing this job
right, it is the confabulation this stage exists to prevent.

- **A hole's `reason` is `blocked_by_gap`.** Do not propose against it. Say
  which gap is blocking it (its `gap_id`, and in your own words what it
  is missing), and stop there. Proposing anyway hands `tg-instantiate` a
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
  fact does not pin down a specific world is one `tg-instantiate` builds
  arbitrarily, and the resulting expected answer is a label nobody can
  actually defend, because a different, equally valid seed would have
  produced a different answer to the same scenario.

- **`max_scenarios` is already reached.** Stop proposing. Report how many
  holes remain unaddressed and which ones they are, so the orchestrator can
  decide whether to raise the cap or accept the gap. Do not propose past the
  cap on the theory that `check-refs` will simply catch and discard the
  overflow later -- that leaves the excess sitting in the file as a
  contract violation instead of a clean stop.
