---
name: rb-reconcile-gaps
description: Record what no input says and reasoning cannot supply, naming honestly every stage each gap blocks -- and audit every earlier partial for what it modelled without evidence.
---

# rb-reconcile-gaps

You are dispatched once, after every other prompt pass in this family and
before `reconcile-seal` assembles their partials into the world model. Two
jobs, and the second one is new to this pass: record the gaps, and audit what
the passes above you wrote. You read all of the claims and every partial those
passes wrote, which makes you the last pass that reads the claims closely -- after
you, nothing in the pipeline compares the world model against the evidence it
was supposed to come from.

## Contract

```toml
stage = "reconcile-gaps"
reads = ["manifest", "claims_dir", "subjects", "contradictions_dir", "capabilities_part", "outcomes_part", "entities_part", "goals_part"]
writes = ["gaps_part"]
schemas = ["gaps-part"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read the eight things this skill's contract names under `reads`:
`manifest.json`, every file under `01-claims/` (`claims_dir`) -- not one of
them, all of them -- `01-subjects.json` (`subjects`), every file under
`01-contradictions/` (`contradictions_dir`), and the four partials
`01-capabilities.json`, `01-outcomes.json`, `01-entities.json` and
`01-goals.json`. Every pass in this family reads all of the claims; the family
is split on *output*, not on claims, which is what keeps the barrier property
the single-dispatch stage had.

You read more of the run than any other pass because your second job is to
audit it. The contradictions are also a constraint on you, as they are on every
pass below the sweep: a disagreement recorded `unresolved` is not one you may
settle, and where a gap exists *because* two claims disagree and nothing breaks
the tie, the gap is the honest record of it.

Nothing else on disk is yours to read. In particular, no pass reads
`01-world-model.json`: it does not exist yet when you run, and on a re-run of
this family it is an answer some earlier run assembled rather than evidence
about the target. A later pass reading an earlier pass's partial *is* the
design here -- that is what each pass's `reads` list is for -- but a
re-dispatched pass does not read its own previous output: a repair hands you
findings about the artifact you wrote, not permission to reread it instead of
the claims. You are dispatched with no memory of any conversation that came
before you, and nothing you write here carries forward as memory either:
whatever you need to do this job has to be in the manifest, in the claims, in
the partials named above, or in this document.

## 2. Output

One `gaps-part-0.1.json`-shaped document, written to `01-gaps.json`
(`gaps_part`). It carries `schema_version: "0.1"` and a `gaps` array; each gap
has an `id`, a `subject`, what is `unknown`, `why_it_matters`, a `blocks` list,
its own `claims`, and optionally a `suggested_input` naming what would close it.

An empty `gaps` array is permitted by the schema and is a strong claim: it says
every input was complete enough that nothing about the target is unknown. Write
it only if you believe that. A world model with zero gaps, built from claims
that actually leave things unstated, has not reconciled anything -- it has
erased the silence before anyone downstream got to see it.

**Each gap also carries a `claims` array, and what it cites is not what you
might expect.** A gap records what no input contains, so its claims cannot be
evidence *for* the unknown -- there is none, which is the point. They are the
claims that make the absence **matter**: the capability whose error behaviour
nothing describes, the goal that needs a hop no claim supports. That is the
`why_it_matters` field's evidence, made resolvable. Until this array existed a
gap's evidence went into prose, and a run was measured whose gate-1 brief
reported an input at 0 claims cited while a gap in the same brief rested its
argument on one of that input's claims.

`blocks` is the field with consequences. A gap that blocks nothing is
informational; a gap whose `blocks` list contains `propose` is what makes the
orchestrator halt before the round loop and ask for the missing artifact, and
that halt is the only mechanism this pipeline has for refusing to invent
knowledge it does not have.

## 3. Method

1. **Record every gap: knowledge about the target that no input contains
   and that reasoning cannot supply.** Give it a `subject`, what is
   `unknown`, `why_it_matters`, and a `blocks` list naming every stage among
   `propose`, `score`, `instantiate`, `challenge`, `emit`, and `smoke` that
   cannot proceed soundly without it. A gap that blocks nothing is
   informational; a gap that blocks `propose` is what makes the
   orchestrator halt and ask for the missing artifact instead of letting
   the pipeline invent the missing knowledge and run on. If a blocking gap
   never actually stops a real run, gap detection in this pipeline is not
   doing its job -- so name `blocks` honestly rather than narrowly, and
   never leave it empty just to avoid triggering a halt.

2. **Sweep the same silences the earlier passes had to leave.** For each
   capability in `01-capabilities.json`, an outcome class written
   `underspecified` in `01-outcomes.json` is a silence somebody has already
   found: decide whether it is a gap, and if it would stop `rb-propose` from
   designing a meaningful scenario against that capability, say so in
   `blocks`. The same for an entity whose invariants `01-entities.json` could
   only state as `prose:` because nothing stated them outright, and for a
   contradiction recorded `unresolved` whose resolution a scenario would need.

3. **Audit every earlier partial, and record what you find as a gap.** No
   other pass reads them all against the claims, and no gate can do this
   work: layer 2 checks that an element *references* a resolvable claim,
   never that the claim *supports* it, because support is semantic. So read
   for the things a reference check cannot see:

   - a capability in `01-capabilities.json` whose cited claims do not
     actually establish it -- or that has no supporting claim at all;
   - an invariant in `01-entities.json` promoted to `machine:` on something
     the claims only imply, which will fail every seed that is actually
     correct because `check-refs` evaluates it as ground truth;
   - an outcome class in `01-outcomes.json` that nothing in the claims
     states, or a capability there whose enumeration stops at one class;
   - an entity modelling a response shape no claim spells out;
   - a goal in `01-goals.json` that no declared capability could advance, or
     an actor no claim names;
   - a subject in `01-subjects.json` that swept two claims you can see
     disagree, whose part records no contradiction.

   Record each as a gap whose `subject` names the artifact and element, whose
   `unknown` says what evidence is missing, and whose `blocks` reflects what
   it actually costs. You are not editing another pass's artifact -- you have
   no write access to one and no authority over it. You are making the defect
   visible to the human at gate 1, who does.

## 4. Invariants

1. Every gap carries a non-empty `blocks` list. Layer 1 enforces it
   (`minItems: 1`, `uniqueItems`), and every value must be one of `propose`,
   `score`, `instantiate`, `challenge`, `emit`, `smoke`.

2. Gap `id`s are unique.

3. `why_it_matters` says what breaks downstream, not that something is
   missing. "No claim describes the error payload" is the `unknown`; "a
   scenario targeting the error class would have no expected answer to assert"
   is why it matters.

4. Nothing you write claims to resolve anything. Gaps record; they do not
   settle. A gap whose `unknown` reads as a decision is a resolution written
   in the one artifact that exists to record the absence of one.

5. Every gap carries at least one `claims` entry, and every entry resolves to a
   claim id that exists in `01-claims/`. Layer 1 enforces the first
   (`claim_refs` carries `minItems: 1`); `refs.check_world_model` enforces the
   second, after the seal.

Before you report done, run
`rubrica validate --stage reconcile-gaps --run <run>` and then
`rubrica check-refs --run <run>`, where `<run>` is the run directory you were
dispatched with. `--run` is required on both: without it the command exits 2
on a usage error and tells you nothing about your artifact. `check-refs` runs
every checker the run has inputs for, so it will also report on the earlier
partials -- and by this point in the run it can report on all of them. A
finding it raises against a pass above you is not yours to repair and not a
substitute for the audit in §3 step 3: the two see different things, and the
things it cannot see are the ones that reach a shipped test.

## 5. Refusal conditions

Every condition below is one where the correct output is not a tidy, complete
picture of the target -- it is one that honestly shows where the inputs are
silent and what that silence costs. You default to being helpful and to
producing something that looks finished; every trigger below is a case where
that instinct is the wrong one, and recording the hole honestly is what is
actually correct.

- **A capability's error or empty behaviour is described nowhere.** Record
  a gap, not an invented outcome class. If the missing semantics would stop
  `rb-propose` from designing a meaningful scenario against that capability,
  the gap's `blocks` list must include `propose` -- that is what turns a
  silent hole into a halt the orchestrator actually has to act on.

- **You are tempted to leave `blocks` narrow, or to leave `propose` out of
  it, because a halt would be inconvenient.** Do not. A gap that blocks
  `propose` is what makes the orchestrator halt, so name `blocks` honestly
  rather than narrowly, and never leave it empty to avoid triggering a halt.
  If a blocking gap never actually stops a real run, gap detection in this
  pipeline is not doing its job.

- **You are tempted to record no gaps because the earlier partials look
  complete.** Check that against the claims rather than against how the
  partials read. A capability list can be internally coherent and still rest
  on nothing: the passes above you were each looking at one slice of the
  output, and you are the only one looking at all of it beside the evidence.

- **You are tempted to describe a capability, entity, outcome class or goal
  that no claim supports because the target "obviously" has it.** Do not.
  Confabulation under under-specification is the characteristic failure of a
  prompt pipeline: a plausible invention here is indistinguishable from a
  real fact to every stage after you, and none of them read the claims
  closely enough to catch it -- you are the last pass that reads the claims
  closely.

- **The audit in §3 step 3 finds a defect in an earlier pass's artifact.**
  Record it as a gap. Do not edit that artifact -- it is not yours to write
  and a silent correction destroys the record of which pass made the mistake,
  which is the only thing that makes a bad run evidence rather than an
  anecdote. Do not stay quiet about it either: nothing else in this pipeline
  looks for it.
