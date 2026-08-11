# rb-reconcile -- live exercise

`tests/unit/test_skills_reconcile.py` and `skills.check_contract` can confirm
this skill's *shape*: the contract, the five sections, and that its prose at
least mentions every enum value the world-model schema and `invariants.py`
know about. Neither can confirm that a model actually dispatched with this
prompt merges a real claim set the way the design intends -- that a genuine
disagreement gets recorded rather than quietly settled, that the outcome-class
enumeration is not trivially small, that a checkable invariant actually gets
written as one. This file records what the live exercise checks instead, so
the controller running it -- and anyone reading its result later -- knows
what "passed" is supposed to mean.

## Setup

Build a toy run stopped after `extract`: `build_toy_run(runs_dir,
upto="extract")`. This leaves `00-inputs/` and a complete `01-claims/`
(`api-json.json`, `notes-md.json`, `trace-json.json`) on disk, with nothing
under `01-world-model.json` yet.

One dispatch, not a fan-out: unlike `rb-extract`, `rb-reconcile` is the
barrier, so there is exactly one subagent, given the run directory, the stage
name, and this skill's path -- and, unlike `rb-extract`'s dispatch, no single
`artifact_id` to restrict it to, because reading every claims file is the
whole point of this stage.

## Pass criteria

- `01-world-model.json` exists and is schema-valid.
- `rubrica validate --stage reconcile` exits 0.
- `rubrica check-refs` exits 0.

Then read the world model by hand against the questions below. A run that
clears the three mechanical checks above and fails any of these has not
actually reconciled anything -- it has produced a document that merely looks
finished.

## Properties no automated test can check

**1. Did it record the contradiction?** `notes.md` states plainly that
`get_ticket` on an unknown id is an error; `trace.json` shows one captured
call to `get_ticket(9999)` returning `{}`. A world model with zero
`contradictions` here has silently resolved a real disagreement between two
input artifacts, and that is the exact failure §3's extract/reconcile split
exists to prevent. **This is the single most important thing the exercise
measures** -- everything else below is checking the quality of a reconciled
world model; this is checking whether reconciliation happened at all.

**2. Did it enumerate more than the success outcome class per capability?**
The toy world has two capabilities, `find_tickets` and `get_ticket`, each with
two outcome classes claims actually support (`find_tickets`: a match, and a
legitimately empty result; `get_ticket`: a found ticket, and an unknown id,
which is the same contradiction from question 1 filed as an outcome class
regardless of how it resolves). That is a `capability_cells` denominator of
4. A world model reporting 2 -- one outcome class per capability, the success
path only -- has quietly halved the surface every later coverage percentage
is measured against, without a schema error or a `check-refs` finding ever
naming it. Also check: did the get-ticket contradiction's error semantics
make it into an outcome class at all, given that one of the two claims
stating it was filed under `kind: invariant` rather than `kind:
outcome_class`? A world model that only harvested `outcome_class`-labelled
claims would still find the fact (`api-json` states it under the right
label), but a fixture without that redundancy would lose the cell silently --
worth checking that the reconciliation reasoning does not depend on the
redundancy holding.

**3. Did it write both `machine:` invariants?** `notes.md` states the
comment-count rule and the ticket-id-uniqueness rule explicitly -- both
`stated`, not inferred or reverse-engineered -- and both fit implemented
forms (`count` and `unique`). A world model that files either as `prose:`
has left the reachability gate with nothing mechanical to check for that
invariant, and a seed that silently violates it will not be caught before
`rb-challenge`, if it is caught at all.

**4. Does the contradiction's `rationale` name what in the claim set actually
licenses its resolution, or does it read like an appeal to convention?** Two
independent claims files (`api.json`, `notes.md`) state the error behaviour;
one trace span shows the empty-object behaviour. `preferred_a` is defensible
here, but only because that corroboration exists in the claims -- a rationale
that says "APIs typically error on bad ids" instead of "two independent
artifacts state the error behaviour, against one uncorroborated trace span"
would reach the same `resolution` value for the wrong reason, and would have
reached it identically even if `notes.md` and `api.json` had never been
extracted at all. That is the tell §1's epistemic-boundary paragraph and §5's
last refusal condition are written against, and no schema or `check-refs`
check can read a `rationale` string for *why* it says what it says --
this is the one property in this list that is not just "count something in
the output," and it is the one most worth reading closely by hand.

## Recording the result

Record which of the four it got, in the exercise ledger, whether or not the
mechanical pass criteria above were met. A run that passes `validate` and
`check-refs` but silently resolved the contradiction (question 1) or filed a
convention-based rationale (question 4) is a failure this exercise exists to
catch precisely because those two gates cannot see it. This is the first real
measurement of whether the judgment carried in this skill's prose survives a
handoff to a dispatched model -- the hypothesis the whole project exists to
test -- so a negative result here is exactly as valuable to record as a
positive one, and belongs in this file (or a `## Run record` section appended
below it) rather than only in a review ledger elsewhere.

## Run record: round 1 of the live exercise

Transcribed from the exercise ledger, which is where this result lived until
now -- the section above requires it to live *here*, and the ledger's workspace
is deleted when this branch finishes.

One dispatch against a run stopped after `extract`, on the hand-authored fixture
claims: one subagent, the run directory, the stage name and this skill's path,
with no `artifact_id` restriction because reading every claims file is the point
of this stage. **Both gates clean** -- `rubrica validate --run <run> --stage
reconcile` 0 and `rubrica check-refs --run <run>` 0.

**The headline result is a success, and it is §5's own stated test of gap
detection: a real reconcile HALTS the pipeline on the toy world.** It recorded
three gaps, all blocking `propose` -- no capability retrieves Comment content,
and neither capability has any claim describing bad- or missing-argument
behaviour. §5 says "halting on a blocking gap is the payoff for first-class
gaps... if this never fires on a real run, gap detection is not working." It
fired on the first real run. The consequence for the chained whole-pipeline
exercise was recorded at the same time: that run will halt at reconcile, and
that is correct behaviour to record rather than a blocker to work around.

**Property 1 (did it record the contradiction?) -- PASS.** It left
`ctr-get-ticket-unknown-id` `unresolved`, with the reasoning that there is only
one claim per side and nothing else in the claim set breaks the tie. Correct for
the claim set it was given, and exactly what this skill asks for: the
disagreement is recorded rather than settled by whichever artifact was read last.

**Property 2 (more than the success outcome class?) -- PASS, and it moved the
number the other way.** It enumerated **7 capability cells** -- three outcome
classes for `find_tickets`, four for `get_ticket` -- against the hand-authored
fixture's 4. The opposite of the shrinking failure this property was written to
catch: a real run *expanded* the denominator. Read that figure next to
`rb-orchestrate/exercise.md`'s run record, where the same skill on the same
target measured **6** from real `rb-extract` claims: 7 from fixture claims and 6
from real ones are two measurements of two inputs, which makes the denominator
this stage freezes sensitive to upstream claim quality.

**One tension inside that pass, recorded because the ledger does not resolve it.**
The run's stated reason was "only one claim per side", while property 4 above --
and the fixture note at the end of this record -- say the error behaviour is
stated by *two* independent claims files against one trace span. So either the
run counted the corroboration differently than the fixture's author does, or it
miscounted, and nothing measured that round tells them apart. Its `unresolved`
answer is defensible on the second reading and questionable on the first: with
one side corroborated, `preferred_a` with the corroboration cited is what
property 4 asks for. Worth re-measuring on a fixture where nothing licenses
either side, which is a different question from the one this round answered.

**Two defects in the golden fixture, both surfaced by this run, both confirmed by
reading `tests/toy.py`.** Neither is a defect in the skill:

1. The fixture world model's contradiction rationale cites "the trace is one
   captured call that PREDATES it" -- a fact no claim in the set supplies. That
   is precisely the extrinsic-knowledge leak §5 forbids, sitting in the golden
   fixture as the model answer. `check_world_model` cannot see it: it verifies
   that `claim_a` and `claim_b` resolve, never that the rationale rests on the
   claim set. The defensible in-set tie-breaker is the derivation/confidence
   asymmetry (`stated`/high against `reverse_engineered`/medium).
2. `oc-detail`'s description says "the ticket and its comments, ordered by
   position", but no claim states that any capability returns comments -- the
   claims carry a Comment entity and a `comment_count` invariant and nothing
   more. So the hand-authored world model asserts capability behaviour its own
   claim set does not support, and the live reconcile correctly reported that as
   a gap. `api.json` the *file* does state it, so the fixture's *claims* are
   impoverished relative to the input they were supposedly extracted from.

**A fixture note that weakens what property 4 can measure here.** The toy world's
contradiction is stronger than the exercise's own setup describes: `api.json`
*and* `notes.md` both state the error behaviour and only `trace.json` disagrees,
so reconcile sees one side corroborated -- which is what makes `preferred_a`
genuinely defensible on this input, and it is also why this run's `unresolved`
answer is not the same question. A contradiction where nothing licenses
preferring either side needs its own fixture; that is what the negative fixtures
added later exist for.
