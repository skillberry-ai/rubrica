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

**4. Do the discriminating facts turn on values the claims support, or on
values invented to make the fact land?** Uniqueness (property 2) and
groundedness are different properties, and a fact can have the first
without the second: "queue `sales` has zero matching tickets" pins down a
seed as precisely as any fact in this file, but nothing in the claim set
establishes a `sales` queue. `clm-notes-001` names exactly two queues,
`billing` and `shipping`; a fact built around a third, invented one is
grounded in nothing, and `tg-instantiate` will build a seed containing that
invented queue with no way for anyone downstream to tell it apart from a
real one -- `validate` and `check-refs` cannot catch this, because a
capability's `params` are open strings with no enum to check a queue name
against. For each `discriminating_fact` in the file, trace every entity
value it names -- queue, status, id, count, any field value -- back to the
world model or a cited claim, and flag any fact that depends on a value
that trace does not reach. Also check, for every absence- or error-shaped
fact, whether the claims already establish a grounded mechanism for
producing that outcome class (a real queue with no matching tickets,
`clm-trace-001`'s worked case) that the scenario passed over in favor of an
invented value instead -- that is the sharper failure, because it shows the
grounded route was available and unused, not merely unknown. A worked
example a real run produced: `sc-0002`'s discriminating fact is "`find_tickets`
with queue `sales` and status `open` returns zero tickets" -- `sales` is not
one of the two queues any claim names, and `clm-trace-001` already
establishes the grounded way to reach the same zero-result outcome on a
queue that actually exists.

## Recording the result

Record which of the four properties above held, in the exercise ledger,
whether or not the mechanical pass criteria were met. A run that passes
`validate`, `check-refs`, and the status check but only ever targets success
cells, writes facts that are not actually discriminating, or grounds a fact
in an invented value, is a failure this exercise exists to catch precisely
because those mechanical gates cannot see it.
