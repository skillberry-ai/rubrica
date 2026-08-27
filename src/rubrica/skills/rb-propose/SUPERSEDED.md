# `exercise.md` beside this file records a stage shape that no longer exists

`rb-propose` was one dispatch per round. It read `02-scenarios.json`, appended
that round's new scenarios to whatever every earlier round had put there, and
wrote the whole accumulating document back -- which is why `scenarios` appeared
under both `reads` and `writes` in the contract it carried then. It is now a
**fan-out member**: dispatched once per batch with a `batch_id`, it takes that
batch's `hole_refs` out of `02-batches/round-N.json` as its entire worklist and
writes only `02-scenarios/round-N/<batch_id>.json`. `rubrica propose-seal`
assembles the scenario list from the parts, in code.

**Why the shape had to change, measured on `run-20260825-094033`** (the full
byte-level figures are in `rounds.py`'s `MEASURED` header, which is where they
belong):

- Round 1 succeeded: 18 scenarios, $2.69, 23 minutes.
- Round 2 had to re-emit those 18 verbatim plus one new scenario per closable
  hole, of which the coverage report listed 86. It hit the harness output cap
  and **wrote nothing at all**, for $3.57 over 31 minutes.

`exercise.md` records two real dispatches of the single-document shape, against
the toy fixture. It is **not** an exercise record for the skill that now sits
beside it, and it was neither relocated nor rewritten: editing it to read as if
it described a batch member would assert that a dispatch of the *new* shape did
what the superseded one actually did, which is the misattribution this project
has already retracted once. Two things in it are still worth reading on their
own terms, and neither is behavioural evidence about the current stage: the
`discriminating_fact` uniqueness failure, which is a requirement this skill
carried before and after the split, and the controller error at the end of the
file, whose generalizable rule ("check what the stage's `reads` actually gives
it") is binding on anyone raising a finding against the current prompt.

**So the batch member has no behavioural evidence beside it yet.** No dispatch
of a member has been recorded -- not one that read a batch plan, not one that
minted `sc-<batch_id>-` ids, and not one that stopped at its own batch's holes
when a sibling's were visible in the same plan. `refs.check_scenario_parts` is
the only thing that would catch the last of those, and a checker firing is not
the same evidence as a member choosing correctly. `docs/design/limitations.md`
carries what is unmeasured; `docs/concepts/pipeline.md` carries the shape.

This directory still has a `SKILL.md`, so nothing here is dormant the way
`rb-reconcile/` is: `skills.discover()` finds this skill, `check-skills` holds
its contract, and no code in this repository reads an `exercise.md` at all.
