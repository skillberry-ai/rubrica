# tg-reconcile -- live exercise

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

One dispatch, not a fan-out: unlike `tg-extract`, `tg-reconcile` is the
barrier, so there is exactly one subagent, given the run directory, the stage
name, and this skill's path -- and, unlike `tg-extract`'s dispatch, no single
`artifact_id` to restrict it to, because reading every claims file is the
whole point of this stage.

## Pass criteria

- `01-world-model.json` exists and is schema-valid.
- `testgen validate --stage reconcile` exits 0.
- `testgen check-refs` exits 0.

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
`tg-challenge`, if it is caught at all.

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
