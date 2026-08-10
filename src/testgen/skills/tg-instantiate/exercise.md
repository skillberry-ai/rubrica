# tg-instantiate -- live exercise

`tests/unit/test_skills_instantiate.py` and `skills.check_contract` can
confirm this skill's *shape*: the contract, the five sections, and that its
prose names every assertion kind, both grounding rules, the inverted
exclusion check, the absence-scenario invariant and the six method steps in
order. None of that can confirm the one thing this stage exists for -- that a
model dispatched with this prompt actually builds a world with near-misses in
it, rather than a world holding exactly the record the answer names. That
failure passes every gate in the pipeline: the seed conforms, the invariants
hold, the label is correct, and the test measures nothing. This file records
what the live exercise checks instead, so the controller running it -- and
anyone reading its result later -- knows what "passed" is supposed to mean.

## Setup

Build a toy run stopped after `score`:

```python
build_toy_run(runs_dir, upto="score")
```

That checkpoint writes `01-world-model.json`, `02-scenarios.json` with every
kept scenario `active` and `scn-open-dup` folded to `duplicate`, and both
`03-coverage/round-1.json` and `03-coverage/latest.json`.

**Confirm `04-instances/` is absent before dispatching**, and delete it if it
is not: a run that already holds the fixture's hand-authored seeds measures
the fixture rather than the model. At this checkpoint the directory is not
written at all -- `build_toy_run` returns before its instantiate block, and
nothing else in the fixture creates the run's stage directories eagerly, so
the check is a safeguard rather than a step with work to do. It is worth
performing anyway, because it is the one setup mistake that would make every
property below read as a pass.

Dispatch **once per active scenario** -- four dispatches, for `scn-open`,
`scn-empty`, `scn-blocked` and `scn-missing` -- each given only the run
directory, the stage name, this skill's path, and its own `scenario_id`.
Never the other three, and never one dispatch over all four: this stage is a
fan-out, and running it as a single pass would test something the design
forbids and would make the isolation questions below unanswerable.

The fifth scenario, `scn-open-dup`, is `duplicate` and must not be
instantiated. It is not part of the fan-out.

## Pass criteria

- Four instance directories exist under `04-instances/`, one per active
  scenario, each holding `seed.json`, `expected.json` and `rationale.md`.
  The third file is the one to check for explicitly: no schema gates it, so a
  subagent that skipped it fails no automated check.
- `testgen validate --stage instantiate` exits 0.
- `testgen check-refs` exits 0. That single exit code carries three separate
  results: the reachability gate passed (every data assertion's
  `seed_pointer` resolves in its own seed, and every exclusion's resolves to
  nothing), seed conformance passed (declared collections, declared fields,
  declared types), and both of the toy world's `machine:` invariants --
  `inv-comment-count` and `inv-ticket-id-unique` -- hold on all four seeds.

Then read the four seeds and oracles by hand against the questions below. A
run that clears the mechanical criteria and fails the first of these has
produced four tests that cannot fail.

## The properties to look for, in order of what they tell you

**1. Did every seed get distractors? Count the records.** This is the single
most informative thing this exercise measures. A `scn-open` seed holding one
ticket -- the open billing one -- is the all-pass failure mode arriving in
the very first real run: an agent that calls `find_tickets` once with no
filters at all reads back the only row and answers correctly, and every gate
stays green. The question for each of the four is whether the seed contains
at least one record that misses on exactly one dimension of the scenario's
`discriminating_fact`, and whether a solution that dropped one filter, or
read only the first comment, would land on a different answer. Method step 2
is written against precisely this, and a negative result here means the step
needs a harder trigger rather than more explanation.

Note what the mechanical criteria cannot see: a one-record seed satisfies
seed conformance, satisfies both invariants, grounds its pointers fine, and
`check-refs` reports nothing. The count has to be read.

**2. Did `scn-missing` get an assertion a refusal cannot satisfy?** It is
the absence-shaped scenario in this fixture -- no ticket with the requested
id exists -- so it is the one where an oracle made entirely of
`answer_excludes` would be substantially passable by an agent that answers
"I do not have enough information": `verify.score_assertions` scores an
exclusion satisfied by absence as a point, by design. Check its
`assertions` array for a `tool_called` on `cap-get-ticket`, or a positive
`answer_contains` on something the seed does contain. If it is all
exclusions, Invariant 7 was not followed, and the prompt needs to state it
harder rather than at greater length. `scn-empty` is the second, milder case
of the same shape and worth the same glance.

**3. Did any `comment_count` disagree with the comment records?**
`inv-comment-count` is a `machine:` invariant of `ent-ticket`, and a seed
that attaches two comments to a ticket whose `comment_count` reads 1 violates
it. `check-refs` will name it, so this one is not invisible -- which is why
the thing to record is *whether the subagent caught it itself before
writing*, from its transcript. Method step 3 tells it to check the invariants
before going on and section 4 tells it to run both gates before reporting
done; "green after a repair the subagent made unprompted", "green after
`check-refs` caught it", and "right the first time" are three different
results about whether that instruction landed.

**4. Did the fan-out hold?** Two checks, neither of which any gate performs.
First, resolve each `seed_pointer` against its *own* seed -- `check-refs`
already does exactly this, so a clean run establishes it, and the value here
is confirming no subagent even attempted a pointer that would only make sense
against a sibling's world. Second, and the one that has to be read: does any
`rationale.md` mention another scenario, reuse a sibling's ticket ids or
summaries in a way that suggests coordination, or explain a distractor by
reference to what a neighbouring test covers? Cross-contamination is what the
fan-out was chosen to prevent, and it is invisible unless you look. Section
1's fan-out paragraph and the last refusal condition are written against this
specific leak, which here cannot be prevented by the file boundary at all:
`02-scenarios.json` necessarily puts all five scenarios in every subagent's
context, so the only boundary available is the one on what each subagent
*uses*.

A related read while you are in the four seeds: values invented
independently are the expected result, not a finding. Four seeds that each
pick their own ticket ids are four separate worlds behaving correctly; four
seeds that agree suspiciously closely on ids and summaries are the thing to
look at, since nothing in the prompt asks for consistency across seeds and
reaching for it is the leak.

## Recording the result

Record which of the four properties held, in the exercise ledger, whether or
not the mechanical pass criteria were met. Property 1 is the one this
exercise exists for: it is the first point in the pipeline where a model has
to invent difficulty rather than transform an artifact, and it is the one
property whose failure is completely invisible to every automated check this
build has. A negative result there is exactly as valuable to record as a
positive one, and more urgent.

## Run record: round 1 of the live exercise

Four fresh subagents dispatched concurrently, one per active scenario, each
given only the run directory, the stage name, this skill's path and its own
`scenario_id`. `scn-open-dup` was not dispatched. The run was built with
`build_toy_run(runs_dir, upto="score")`; `04-instances/` was confirmed absent
before dispatch.

**All pass criteria met.** Four instance directories, each holding all three
files including the schema-less `rationale.md`. `testgen validate --stage
instantiate` 0 and `testgen check-refs` 0 after all four finished -- so
reachability, seed conformance, and both `machine:` invariants hold on every
seed.

**Property 1 (distractors) -- PASS, and stronger than the criterion asks.**
Record counts were 4, 3, 3 and 2, and in every case dropping one dimension of
the `discriminating_fact` lands on a different answer:

- `scn-open` (4 tickets): a status near-miss (billing/`closed`), a queue
  near-miss (shipping/`open`), and a text trap -- a billing/`pending` ticket
  summarised "Open question about refund timing", which a keyword search for
  "open" returns. Querying either filter alone yields an ambiguous set.
- `scn-blocked` (3 tickets, 5 comments): the two single-dimension near-misses,
  plus the sibling shipping/`blocked` ticket whose comment opens with the same
  "Blocked pending" phrase as the answer's -- and, the best distractor of the
  run, a *within-record* ordering trap: comment 2 of the answer ticket mentions
  legal review and explicitly disclaims being the holdup, so an agent that stops
  at the first blocker-sounding comment instead of the last one answers wrong.
  Nothing in the prompt asks for a within-record trap; step 2's "read only the
  first comment" framing was enough to produce one.
- `scn-empty` (3 tickets): a shipping ticket summarised "Shipment appears
  blocked awaiting customs clearance" while its status is `open` -- the exact
  trap for an agent that greps for the word instead of filtering the field.
- `scn-missing` (2 tickets): ids 4108 and 4110, straddling the absent 4109, one
  per queue. The thinnest set of the four by count, but the right shape for an
  id-absence fact: the near-miss dimension is identity, and an off-by-one on
  either side is the plausible wrong answer.

**Property 2 (an absence oracle a refusal cannot satisfy) -- PASS on both
cases.** `scn-missing` carries `tool_called` on `cap-get-ticket` alongside its
two exclusions; `scn-empty` carries `tool_called` on `cap-find-tickets`
alongside one. Neither is all-exclusions, so "I do not have enough information"
scores no free points on either. Invariant 7 landed.

**Property 3 (`comment_count` vs comment records) -- right the first time, all
four.** No subagent needed a repair and `check-refs` had nothing to catch:
`scn-blocked`'s three tickets read 3/1/1 against exactly that many comment
records. `scn-open` went further and reported its reasoning explicitly --
`comment_count: 0` on every ticket with an empty `comments` collection,
satisfying `inv-comment-count` trivially -- which is the invariant being checked
before writing rather than after being caught.

**Property 4 (did the fan-out hold?) -- PASS, and it produced a false positive
worth keeping.** Every `rationale.md` names only its own scenario id, and the
four seeds chose fully independent ticket ids (5001-5004, 3101-3103,
5201/5202/6100, 4108/4110) -- four separate worlds, which is the expected
result.

But three of the four seeds independently used the summary string "Package
delayed at customs" for a shipping ticket. That trips this section's own
heuristic ("seeds that agree suspiciously closely on ids and summaries are the
thing to look at"), and it is **not** a leak. The proof is stronger than the
heuristic: the phrase appears nowhere in the run outside `04-instances/` -- not
in the world model or scenarios that all four legitimately read, and not in
`00-inputs/` or `01-claims/` either, which would have been evidence of a
forbidden read. The world model in fact carries no shipping prose at all. A
leaked value must exist in the artifact it leaked from; a converged value
exists nowhere upstream. Three instances of one base model, each asked for a
shipping-queue ticket, reached for the same natural phrase.

**Record this as the discriminator, because the heuristic alone would have
produced an isolation finding against a stage that did nothing wrong** -- the
same error class as holding a stage to knowledge its contract denies it. When
two slices agree on a value, grep the readable artifacts *and* the forbidden
ones before calling it contamination: absent from both means shared prior,
present in a forbidden one means a real leak, and present in a readable one
means it was never a leak at all.

**The headline result, which this round got for free.** `scn-open` finished
first and hit exactly the race the scoped self-check was rewritten for: its
`validate --stage instantiate` returned two `missing artifact` findings for
`scn-blocked/expected.json` and `scn-missing/expected.json`, siblings that had
not written yet. It classified both as not naming its own instance directory,
reported success, and neither blocked waiting for them nor opened the sibling
directories. The concurrent-fan-out scoping is therefore confirmed
behaviourally, by the first real run after it landed, rather than only by
reading.
