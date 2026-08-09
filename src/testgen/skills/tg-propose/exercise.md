# tg-propose -- live exercise

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
- `testgen validate --stage propose` exits 0.
- `testgen check-refs` exits 0.
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
not pin down any specific seed world for `tg-instantiate` to build. A real
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
`tg-propose` never reads a claims file in the first place, so there was
never anything for a queue name to be checked against. A concrete field
value in a `discriminating_fact` is a prescription to `tg-instantiate`
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
anti-example) with the polarity flipped: `tg-instantiate` reading it has
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
