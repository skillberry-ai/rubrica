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

## Run record: round 2, re-record after the entity-modelling change

Task 2 of the claim-utilisation-and-observable-judgment plan added Method step
4: for every declared capability, if any claim spells out the shape of what
that capability returns, that shape becomes an entity -- because
`refs.check_world_model` only checks that cited claims resolve, never that a
described response shape got modelled. This round re-records the exercise
against the changed prompt.

Setup per this file's own instructions: a fresh toy run stopped after
`extract` (`build_toy_run(runs_dir, upto="extract")`), one dispatch, no
`artifact_id` restriction. Dispatched via `scripts/dispatch-stage.sh`,
isolated instance, model `sonnet`, effort `medium` (harness defaults; neither
`RUBRICA_MODEL` nor `RUBRICA_EFFORT` was set). 11 turns, `total_cost_usd`
`0.5544891` from the transcript's `result` event.

**Both gates clean:** `rubrica validate --stage reconcile` and `rubrica
check-refs`, run directly against the written `01-world-model.json`, each
exited 0.

**The new Method step fired.** The world model now declares **`ent-comment`**
alongside `ent-ticket` -- a second entity that round 1's recording (above)
does not have. `ent-comment` carries `comment_id`/`ticket_id`/`position`/`body`
fields and cites `clm-api-004`, the claim describing what `get_ticket`'s
success response contains. This is exactly the gap round 1 flagged as a golden-
fixture defect ("`oc-detail` describes returning comments but no entity models
them") -- on a live claim set that actually states the shape, the changed
prompt modelled it instead of leaving it implicit.

**`ent-ticket` carries both required `machine:` invariant forms** (property 3):
`inv-ticket-comment_count` (`form: count`, tying `tickets.comment_count` to the
`comments` collection via `ticket_id`) and `inv-ticket-id-unique` (`form:
unique` on `tickets.ticket_id`). Both filed as `machine`, not `prose`.

**Property 1 (contradiction recorded) -- PASS.** `ctr-get_ticket-unknown-id`
stayed `unresolved`, `claim_a: clm-notes-004`, `claim_b: clm-trace-002`,
rationale: "Only one claim supports each side... nothing here breaks the tie,
so the honest resolution is unresolved rather than a preference for either."
This reads the corroboration the same way round 1's tension (above) worried
about -- one claim per side, not two -- so `unresolved` is what property 4
grounded-in-the-claim-set actually asks for on this reading, and the rationale
names the claim ids rather than appealing to convention.

**Property 2 (denominator) -- 6 capability cells**, down from round 1's 7 on
the same fixture claims (three outcome classes for `find_tickets`, three for
`get_ticket`) -- a different split than round 1's 3+4, not a like-for-like
regression; nothing here isolates whether the new entity-modelling step (which
does not touch outcome-class enumeration) or ordinary model variance moved
that number, and this file will not overclaim which.

**Two gaps, both blocking `propose`:** `gap-find_tickets-bad-filter` ("find_tickets
behaviour on an invalid filter value") and `gap-get_ticket-missing-id`
("get_ticket behaviour on a missing or malformed ticket_id"). One fewer than
round 1's three -- again recorded as observed, not diagnosed, since this round
did not isolate the cause.

**Read audit (`scripts/audit-reads.sh`, cross-checked against raw `.input.command`
because the script's `sort -u` on multi-line bash strings visually interleaves
them with unrelated SKILL.md content read out by a `Read` call earlier in the
same transcript -- a display artifact of the audit script, not a violation),
against the contract's `reads = ["manifest", "claims_dir"]`:** `Read` calls were
`SKILL.md`, `src/rubrica/schema/world-model-0.1.json`, and the run's three
`01-claims/*.json` files; the only `Write` was `01-world-model.json`. All four
`Bash` lines were `cat manifest.json`/`ls 01-claims/`, one `find` locating the
schema file, and two `rubrica validate`/`check-refs` invocations. The schema
read is the same one noted as expected in round 1's context; no sibling run, no
`docs/`, `tests/`, or other skill was read. `permission_denials` was empty and
no tool call returned an error. Nothing out-of-contract.

## Observation: a self-describing-absent outcome class, from the toy-contradiction re-record

Not from the round-2 dispatch above -- from the same task's re-record of
`tests/fixtures/toy-contradiction/recorded/01-world-model.json`, also live
`rb-reconcile` output, also worth recording here rather than only in a review
thread. `cap-find-tickets` now carries:

```
id: oc-find-error   kind: error
description: query_tickets never errors on a read: every call, including
  find_tickets, returns a value and nothing about a lookup raises partway
  through -- so there is no error path for find_tickets to enumerate.
```

An outcome class filed under `kind: error` whose own `description` states that
no error path exists. `git show 399dba5:tests/fixtures/toy-contradiction/recorded/01-world-model.json`
-- the recording this task replaced -- has no `error`-kind outcome class under
`find_tickets` at all, only `success`, `empty`, and `underspecified`. So this
is new in this re-record, not a carry-over from the previous one.

**Declining to attribute a cause, deliberately, the same way the denominator
and gap-count deltas above are recorded as observed rather than diagnosed.**
Two candidates, named without choosing between them:

1. Ordinary model variance on a second live dispatch against the same claim
   set -- the same kind of run-to-run difference the denominator and gap
   counts above already show, with no reason to expect outcome-class kinds to
   be exempt from it.
2. Method step 3's instruction to "enumerate its outcome classes: `success`,
   `empty`, `not_found`, `error`, `underspecified`" naming `error` as one of a
   fixed list to check off per capability, which can create pressure to fill
   that slot even when the claim set states the opposite -- in which case this
   is not model variance but a **quantifier-satisfaction artefact**: the same
   shape of failure this plan's own fix quantified capability enumeration to
   *solve* (Task 2's Method step 3/step 4 changes), now possibly showing up one
   level down, on the outcome-class enumeration the same paragraph names. That
   would make this directly relevant to the technique this plan applied, not
   an unrelated defect.

No test or gate covers this. `test_the_gap_fixture_did_not_acquire_invented_outcome_classes`
in `tests/unit/test_refusals_live.py` only reads `GAP_DIR`
(`tests/fixtures/toy-gap/`); the contradiction fixture's outcome classes are
unguarded. This file records the observation; it does not fix the recording
(editing committed live output would fabricate evidence) and does not widen
that test (a new guard needs its own design, and end-of-change-pressure
predicates are exactly what this repo's §8 warns become the next vacuous
ones).
