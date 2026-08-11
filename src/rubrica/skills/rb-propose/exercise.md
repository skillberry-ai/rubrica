# rb-propose -- live exercise

`tests/unit/test_skills_propose.py` and `skills.check_contract` can confirm
this skill's *shape*: the contract, the five sections, and that its prose
names every hole reason and every status it must not write. Neither can
confirm that a model actually dispatched with this prompt designs scenarios
that are worth the round they cost -- that it targets the holes a helpful
generator is tempted to skip, that its `discriminating_fact` values actually
pin down a world instead of restating the `user_intent`, and that it stops
at the cap instead of running past it. This file records what the live
exercise checks instead, so the controller running it -- and anyone reading
its result later -- knows what "passed" is supposed to mean.

## Setup

Build a toy run stopped after `reconcile`: `build_toy_run(runs_dir,
upto="reconcile")`. This leaves `01-world-model.json` on disk and nothing
under `02-scenarios.json` or `03-coverage/` -- round 1 from a blank page,
with `coverage_latest` legitimately absent.

One dispatch, given the run directory, the stage name, and this skill's
path -- no `coverage_latest` to hand it, since none exists yet, and no
memory of any other stage's run.

## Pass criteria

- `02-scenarios.json` exists and is schema-valid.
- `rubrica validate --stage propose` exits 0.
- `rubrica check-refs` exits 0.
- Every scenario in the file has `status: "proposed"`. A single `active`,
  `duplicate`, or `rejected` scenario is a boundary crossed that no schema
  or `check-refs` check flags on its own -- `active` is a perfectly valid
  status for the schema to see, just not one this stage is allowed to write.

Then read the scenarios by hand against the questions below. A run that
clears the four mechanical checks above and fails any of these has not
actually proposed a useful round of tests -- it has produced a file that
merely validates.

## Properties no automated test can check

**1. Does it propose against the `not_found` cell, or only the success
cells?** The toy world's capabilities each have more than one outcome
class -- a success path and at least one absence- or error-shaped one
(`not_found`, `empty`, or similar). A helpful generator's default instinct
is to write the scenario that is easiest to imagine a user wanting, which is
almost always the success path; the absence-shaped cells are the ones that
take actual work to design a believable `user_intent` around, and they are
exactly the ones a generator under time pressure skips. A round that covers
every success cell and leaves every `not_found` cell as
`not_yet_attempted` has technically produced scenarios without actually
closing the holes that matter most for a real test suite. Read the
`capability_refs` across all scenarios written and check which outcome
classes never appear in any of them.

**2. Are the `discriminating_fact` values actually discriminating, or are
they restatements of the `user_intent`?** A fact like "the customer's query
returns the ticket they were looking for" is not a discriminating fact --
it is the `user_intent` with the subject and verb rearranged, and it does
not pin down any specific seed world for `rb-instantiate` to build. A real
discriminating fact names a specific value or count that only one seed can
satisfy -- "queue `billing` has exactly one open ticket, and its `status`
is `escalated`," say. Read every `discriminating_fact` next to its own
scenario's `user_intent` and check whether the fact adds any information
the intent did not already carry.

**3. Does it stay at or under `max_scenarios` (8)?** Count the scenarios
whose `status` is `proposed` after this round (all of them, since this is
round 1 and nothing has been scored yet) and compare against the toy
manifest's `max_scenarios`. A round that proposes nine or more scenarios
against an eight-scenario cap has produced a file `refs.check_limits`
reports a finding against -- and check whether the skill's own report
mentions running into the cap and stopping, versus proposing past it
silently and leaving `check-refs` to be the one to notice.

**4. Do the discriminating facts name concrete ids, counts, and field values
that pin a seed down, or do they stay abstract to avoid committing to
one?** This property was rewritten after a controller error: an earlier
version of it asked whether facts were "grounded" against the world model
or a cited claim, on the theory that a field value like a queue name had to
trace to something the claims establish. That theory was wrong for this
stage -- the world model this fixture builds contains no queue name at all,
the schema has nowhere to record a field's value domain even if it did, and
`rb-propose` never reads a claims file in the first place, so there was
never anything for a queue name to be checked against. A concrete field
value in a `discriminating_fact` is a prescription to `rb-instantiate`
about what to build, not a claim about what the target already has, and
picking one is exactly what makes a fact discriminating. Property 4 is
uniqueness-only from here on; do not resurrect the groundedness half.

The real defect this property exists to catch is the opposite one: a fact
that names no concrete value at all, out of an unnecessary worry about
"inventing" one. `scn-003`'s fact, from a real run, is the worked example:
*"find_tickets is called with a queue and status filter combination for
which the seed contains zero tickets, so the call returns an empty result
set rather than any match."* No queue, no status, no count, nothing
concrete anywhere. That is "the query returns some rows" (property 2's own
anti-example) with the polarity flipped: `rb-instantiate` reading it has
near-total freedom to build any world with some empty combination
somewhere, not the one specific world the scenario means to test. A correct
version would have named any concrete queue and status -- `billing`,
`sales`, `q-north`, it does not matter which, since none of them is a claim
about the target -- specifically enough that only one seed satisfies the
sentence. For each `discriminating_fact`, especially on absence- and
error-shaped cells, check that it commits to a specific value rather than
describing the shape of a value without ever naming one.

## Recording the result

Record which of the four properties above held, in the exercise ledger,
whether or not the mechanical pass criteria were met. A run that passes
`validate`, `check-refs`, and the status check but only ever targets success
cells, writes facts that are not actually discriminating, or avoids naming
a concrete value out of an unfounded groundedness worry, is a failure this
exercise exists to catch precisely because those mechanical gates cannot
see it.

## Run record: two rounds of the live exercise

Transcribed from the exercise ledger, whose workspace is deleted when this branch
finishes. Two dispatches, each against a run stopped after `reconcile`, each
given only the run directory, the stage name and this skill's path. **Both gates
clean on both rounds** (`rubrica validate --stage propose` 0, `rubrica check-refs`
0), every scenario `proposed`, and both rounds under the cap.

**Round 1, against the text as first delivered.** Four scenarios closing all four
capability cells and both goal rows.

- **Property 1 (absence-shaped cells) -- PASS, and it was the point of the
  round.** This was the implementer's own least-confident prediction, and the
  prose it needed had just landed: the absence-cell requirement was measured by
  this file but never *asked for* by the `SKILL.md`, so it was written into Method
  steps 4 and 5 first. The run then proposed against both absence-shaped cells
  (`oc-none`, `oc-missing`) with genuinely believable intents, on the first
  dispatch after the prose landed. Behavioural confirmation, not a reading.
- **Property 3 (the cap) -- PASS.** Four against a `max_scenarios` of 8.
- It also wrote `hop_depth: 2` with two `capability_refs` on the one multi-hop
  scenario, which confirms the round-1 fix to Method step 7 behaved as intended:
  an unexplainable depth is the scenario's own defect to fix before writing it
  down, not a finding to offload onto `rb-challenge`.
- No conflation appeared between §1's knowledge-leak tell ("do not reach for a
  scenario because it is the kind of case tests usually have") and the new
  absence-cell prose ("do not skip a cell because it is harder to design") --
  which is the one question that resolution was written to answer, and the reason
  an optional polish repeating §1's disclaimer in step 4 was declined.

**Round 2, against the revised text.** Three scenarios, again closing all four
cells and both goals. `scn-002` cited the world model's own recorded
contradiction to defend its error semantics -- "the operator notes' contracted
behavior, which this world model prefers over the single captured trace." That is
the extract/reconcile split paying off two stages downstream, unprompted: a
recorded contradiction being *used* as evidence rather than being invisible.

**Property 4's failure, which is real and is what property 4 above now says.**
`scn-003`'s fact in full: *"find_tickets is called with a queue and status filter
combination for which the seed contains zero tickets, so the call returns an empty
result set rather than any match."* No queue, no status, no count. `scn-001` did
the same in miniature -- "filtering by a queue and status combination matches
exactly one ticket", where an earlier run had said "queue `billing` and status
`open` returns exactly one ticket, and that ticket's `ticket_id` is 4231". A
`rb-instantiate` reading either has near-total freedom to build any world with
some empty combination somewhere, rather than the one world the scenario means to
test.

### The controller error this exercise produced, retracted after three fix rounds

The most instructive thing in this record, and it is a failure of the *controller*
reading the run, not of the run:

Round 1's `sc-0002` wrote the discriminating fact "`find_tickets` with queue
`sales` and status `open` returns zero tickets." I raised it as Important -- the
fact turns on a `sales` queue no claim establishes, where `clm-notes-001` names
only `billing` and `shipping`, and `clm-trace-001` already supplied a *grounded*
mechanism for the identical empty-result outcome on a queue that exists. Two fix
rounds were driven off that finding, adding a groundedness requirement to Method
step 6. **It was wrong, and it was retracted at round 4.** Three checks, all run
only after round 3 had landed:

1. The world model contains no queue name at all -- grep count zero.
2. The world-model schema has nowhere to record a field's value domain, so there
   is no artifact in which a queue name *could* be established for this stage.
3. `oc-none`'s own description is "no ticket matches the filters", which a queue
   holding no tickets satisfies literally.

**Root cause: I reasoned from `clm-notes-001`, a claims-file statement
`rb-propose` is forbidden to read.** I held the stage to knowledge its own
contract denies it -- the controller's version of the isolation failure this
whole design exists to prevent. One `grep` over the stage's declared `reads`
would have settled it before the first round instead of after the third.

Round 3 compounded it. The corrected worked example I had written into the prompt
-- "queue `billing` and status `open`" -- is unachievable from this stage's
epistemic position for exactly the same reason: naming `billing` is inventing it
as much as naming `sales`, since `rb-propose` never reads the file that says which
queue names are real. I put an example in a prompt that the prompt's own reader
cannot follow.

What survived the retraction is the half that was always independently true:
`scn-003`'s valueless fact fails **uniqueness**, a requirement this skill carried
before any of it, and fails it fixably -- prescribing a concrete value is an
instruction to `rb-instantiate`, never a claim about the target. Every seed value
is synthetic by construction, which is why property 4 above is uniqueness-only
and says not to resurrect the groundedness half.

**The generalizable rule, which became binding on the tasks that followed:**
before raising a finding against a skill's output, check what the stage's `reads`
actually gives it. A finding that requires knowledge outside the contract is a
finding against the *contract or the fixture*, never against the prompt.
