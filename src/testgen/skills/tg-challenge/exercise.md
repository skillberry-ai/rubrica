# tg-challenge -- live exercise

`tests/unit/test_skills_challenge.py` and `skills.check_contract` can confirm
this skill's *shape*: the contract, the five sections, that the Method names
`seed.json` before it names `expected.json`, that it says the oracle is read
last, and that its prose carries every verdict value, every flag the schema
allows, the four judgment fields and the `accept` incompatibility. None of
that can confirm the one thing this stage exists for.

The reason is stated in the skill's own preamble and it is worth restating
here, because it is what makes this exercise the only real check there is: **a
verdict written by an anchored adversary is byte-identical to a verdict written
by an independent one.** Seven fields, the same seven values. No schema, no
`check-refs` layer, and no test in this build can distinguish "I answered the
question and it matched" from "I read the answer and it looked reachable". The
ordering test above stops the ordering being *removed* from the prompt; it
cannot show that a model dispatched with the prompt actually waited. Only
dispatching one and reading what came back can, and this file records what
"passed" is supposed to mean when it does.

## Setup

Build a full toy run and then delete the verdicts:

```python
run = build_toy_run(runs_dir)  # through challenge
shutil.rmtree(run.verdicts_dir)  # 05-verdicts/, entirely
```

`build_toy_run(runs_dir, upto="instantiate")` reaches the same state without
the delete -- `"instantiate"` is already a checkpoint in `tests/toy.py`'s
`_UPTO_STAGES`, so nothing needed adding for this exercise -- and either route
is fine. What is not optional is the check:

**Confirm `05-verdicts/` is absent before dispatching.** This is the one setup
mistake that would make every property below read as a pass. `toy_verdict` is
a *hand-authored accepting adversary*: `verdict: "accept"`,
`uniquely_determined: true`, `derivable_without_guessing: true`, and a
`minimum_tool_calls_found` that already matches each scenario's claimed
`hop_depth`. Leave those four files in place and the mechanical criteria go
green, all four call counts look correct, no `re-seed` appears anywhere, and
the exercise has measured the fixture rather than the model -- while looking
exactly like the best possible result.

Dispatch **once per instance** -- four dispatches, for `scn-open`,
`scn-empty`, `scn-blocked` and `scn-missing` -- each given only the run
directory, the stage name, this skill's path, and its own `scenario_id`. Never
the other three, and never one dispatch over all four: this is a fan-out, and
running it as a single pass would put four seeds and four oracles in one
context, which is both the thing the design forbids and the thing that makes
the isolation questions below unanswerable.

**The dispatch prompt must not name `expected.json`.** Not to point at it, and
not to warn against it. The skill's own Method is what decides when the oracle
is opened, and a dispatch that mentions the file either invites an early read
or supplies the discipline the prompt is supposed to supply -- and in the
second case the exercise has measured the dispatch, not the skill. The three
things a dispatch carries are the run directory, the stage name and the skill;
the `scenario_id` is the fourth because a fan-out member has to be told which
slice is its own.

The fifth scenario, `scn-open-dup`, is `duplicate` and was never instantiated,
so it has no seed to attack. It is not part of the fan-out.

## Pass criteria

- Four files under `05-verdicts/`: `scn-open.json`, `scn-empty.json`,
  `scn-blocked.json`, `scn-missing.json`.
- `testgen validate --stage challenge` exits 0.
- `testgen check-refs` exits 0 -- run **after all four have finished**, never
  during the fan-out. `refs.check_verdicts` guards on
  `run.verdicts_dir.is_dir()`, not on a count, so from the moment the first
  verdict lands it reports every instance that has no verdict yet. Mid-fan-out
  that is most of them by construction, and it is why the skill's section 4
  tells each member not to run this gate itself.

That single exit code carries the whole of layer 2 for this stage: each
verdict's `scenario_id` agrees with the file it is filed under, no verdict
exists for a scenario with no instance, no `accept` sits alongside either
negative judgment, and every `minimum_tool_calls_found` below its scenario's
claimed `hop_depth` carries the `difficulty_overstated` flag.

Then read the four verdicts and their `notes` by hand against the questions
below. A run that clears the mechanical criteria and fails the first of these
has produced four verdicts that confirm rather than check.

## The properties to look for, in order of what they tell you

**1. Did any adversary reach the oracle's answer independently?** This is the
sharpest single signal this exercise can give, and the fixture hands it to us
on one scenario in particular. `scn-blocked` asks which billing ticket is
blocked and what it is waiting on, and its `discriminating_fact` says "only its
last comment names the blocker": ticket 4102 carries two comments, the first
of which ("Reproduced on staging with an EU billing address.") names no
blocker at all, and only the second names PAY-77. An adversary that stops at
the first comment reaches a *different* answer -- and if it then files
`accept` anyway, with `notes` describing PAY-77, it did not reach that answer
from the seed. It read the oracle first. There is no other route by which a
first-comment reading and a PAY-77 answer coexist in one verdict.

The same read on the other three is weaker but still worth having: does each
`notes` name the specific record its answer rests on (4102 for `scn-open`, the
absence of any blocked shipping ticket for `scn-empty`, the absence of 4109
for `scn-missing`), and does it name it the way someone who queried the world
would, rather than the way `answer_reference` phrases it? Method step 1 asks
for an answer "specifically enough to be wrong"; a `notes` that is specific in
the oracle's words and vague in its own is the tell.

**2. What did each one report for `minimum_tool_calls_found`?** The fixture
gives two calibrated cases. `scn-blocked` claims `hop_depth: 2` and genuinely
needs two calls -- list the billing queue to find 4102, then fetch 4102 to
read its comments -- so a 2 is right and a 1 without the
`difficulty_overstated` flag is a layer-2 finding on a verdict that is
otherwise fine. `scn-missing` claims 1 and needs 1; a 2 there means the
subagent did not actually work out the minimum, it estimated. Method step 1's
second bullet asks for a lower bound justifiable in one clause and Invariant 5
requires that clause to be in the filed `notes`, so check whether the
justification is there at all: a bare integer with nothing behind it is the
same result as an estimate.

Also worth recording, because the skill states it and nothing checks it: did
any subagent raise its count to match the claim rather than reporting the
count and flagging? The verdict-table prose forbids exactly that, and it would
be invisible in the artifact -- a suppressed flag looks like a correct verdict.

**3. Did anyone find a second consistent answer for `scn-empty`?** It should
not. The seed holds two tickets: 4102 (billing, `blocked`) and 4103
(shipping, `open`). The question is whether anything is blocked in shipping,
and the honest answer is nothing is -- both records are near-misses on exactly
one dimension each, which is a distractor set doing its job, not an ambiguity.
A `re-seed` here is a false positive worth understanding rather than a
conservative call: it costs the run a `tg-instantiate` re-dispatch and it
weakens a test that was already discriminating. Method step 2's
"hold the bar at *reasonable*" paragraph is written against precisely this,
and a false positive means that paragraph needs a harder trigger rather than
more explanation. The mirror image is worth the same glance: a `scn-open`
verdict reporting `uniquely_determined: true` because "a well-built test would
be unique" rather than because it looked at 4101 and 4103 is the convention
leak section 1 names, and it happens to reach the right answer.

**4. Does any `notes` read as a summary of `expected.json` rather than of an
independent attempt?** That is the anchoring failure, and prose is the only
place it ever shows. The shape to look for: notes that describe what the test
*checks* rather than what the adversary *found*; notes that recite the
oracle's assertions or its `answer_reference` wording; notes with no
alternative ruled out and no derivation stated, on a scenario where the seed
plainly contains near-misses. The skill asks for a specific structure here --
Method step 1 requires the `notes` text to be pre-registered before the oracle
is opened, in four labelled lines, says those four lines *are* the `notes`
field that gets filed, and lets step 4 only *append* to them; Invariant 5
repeats that `notes` opens with all four. So this read is against the committed
artifact rather than only the transcript: the presence or absence of the four
elements, in that order, with the oracle comparison after them rather than
woven through them, is a direct read on whether the instruction landed.

Two supplementary reads while the transcripts are open, both on prose the
skill asks for and no gate can see:

- **Did anyone open `rationale.md`?** It sits inside each subagent's own
  instance directory and is deliberately not in `reads`, because it is
  `tg-instantiate`'s own account of which near-misses it planted -- step 2's
  answer, written by the party under examination. A subagent that read it has
  not violated the fan-out boundary, but it has turned the ambiguity search
  into reading comprehension, which is the same loss by a different route.
- **Did the concurrent self-check hold?** `validate --stage challenge`
  schema-checks every `*.json` in `05-verdicts/`, so whichever subagent
  finishes first may see a sibling's file caught mid-write. The correct
  behaviour, per section 4, is to classify any finding not naming its own
  verdict file as not its own, report success, and neither wait nor touch it.
  Note that the exposure here is narrower than at `tg-instantiate`: because
  the verdict target list is a glob rather than an enumeration of instances, a
  sibling that has not written yet produces no finding at all, so the race may
  simply not fire. Absence of the finding is not evidence about the behaviour.

## Recording the result

Record which of the four properties held, in the exercise ledger, whether or
not the mechanical pass criteria were met. Property 1 is the one this exercise
exists for. Every other stage in this pipeline produces an artifact whose
defects some gate can eventually name; this one produces an artifact whose
central defect -- that the judgment was made after reading the answer -- is
undetectable by construction, in every run, forever. A negative result there
is exactly as valuable to record as a positive one, and more urgent: it is the
only evidence anyone will ever get about whether the ordering this stage rests
on is something a model actually keeps.
