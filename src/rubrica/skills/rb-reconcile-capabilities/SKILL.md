---
name: rb-reconcile-capabilities
description: Declare the target's capabilities from every claim in the run -- each one identified, parameterised, bound to the tool a transcript will show, and citing the claims it rests on. Outcome classes belong to the next pass.
---

# rb-reconcile-capabilities

You are dispatched once, after the contradiction sweep has finished and before
`rb-reconcile-outcomes`. Your output is the list every pass below you
quantifies over: outcome classes are enumerated per capability, entities are
derived from what capabilities return, and the coverage denominator is counted
in capability x outcome-class cells. A capability you leave out is one nothing
downstream can test, and no gate reports its absence -- nothing can check a
list against a target it cannot read.

## Contract

```toml
stage = "reconcile-capabilities"
reads = ["manifest", "claims_dir", "contradictions_dir"]
writes = ["capabilities_part"]
schemas = ["capabilities-part"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read the three things this skill's contract names under `reads`:
`manifest.json`, every file under `01-claims/` (`claims_dir`) -- not one of
them, all of them -- and every file under `01-contradictions/`
(`contradictions_dir`). Every pass in this family reads all of the claims; the
family is split on *output*, not on claims, which is what keeps the barrier
property the single-dispatch stage had.

**The contradictions are a constraint on you, not background reading.** Each
one names two claims and carries a `resolution` that
`rb-reconcile-contradict` was accountable for. A disagreement recorded
`unresolved` may not be quietly settled by how you model the capability:
declaring the capability as though the winning side were established is a
resolution, written in a place with no `rationale` field and no record that a
choice was made at all. Where a resolution is `preferred_a` or `preferred_b`,
model the preferred side. Where it is `unresolved` or `both_possible`, model
what both sides agree on and leave the disputed part out of the capability's
identity -- `rb-reconcile-outcomes` and `rb-reconcile-gaps` both read the same
contradictions and will have to reckon with the same disagreement.

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
the contradictions, or in this document.

Seeing every claim at once means you legitimately see more than any single
`rb-extract` subagent did, and that is not a leak -- it is the design. Merging
claim sets is inherently cross-artifact work; a pass forbidden from seeing
every claim could not merge them at all. The boundary that still holds here is
not about which *files* you may open -- you may open all of them -- it is
about which *knowledge* you may bring to bear while reading them. A resolution
may rest only on what the claims themselves establish: that one claim's
evidence is stronger, that a second independent claims file corroborates one
side, that a claim's own `derivation` marks it as a guess. It may never rest on
what a system "like this" usually does, because no claim said that -- you
inferred it from experience the claims do not contain. Concretely: if
`notes.md`'s claims say `get_ticket` on an unknown id is an error and
`trace.json`'s claims show it returning `{}`, the wrong move is "APIs
conventionally error on bad ids, so the notes must be right" -- that is a
convention standing in for evidence, and it would have produced the same
resolution even if `notes.md` had never been extracted at all. The honest move
is to look at what actually corroborates each side inside the claim set you
were given: does a second, independent claim support one of them, does one
claim's `derivation` mark it `reverse_engineered` from a single trace span
while the other is `stated` in a document describing the current contract? If
you catch yourself resolving a disagreement because one side "sounds like" the
normal, expected, or textbook answer rather than because some other claim in
front of you actually supports it, stop -- model only what both sides agree on
and leave the rest to the passes that can record a gap. §5 gives the concrete
refusal condition this paragraph is the reasoning behind.

## 2. Output

One `capabilities-part-0.1.json`-shaped document, written to
`01-capabilities.json` (`capabilities_part`). It carries `schema_version:
"0.1"` and a `capabilities` array; each capability has an `id`, an
`operation`, its `params`, a `confidence`, a `claims` array naming the claim
ids it rests on, and a `binding`.

**Do not write `outcome_classes`.** They are `rb-reconcile-outcomes`' output,
quantified over the list you write here, and `reconcile-seal` folds them back
into each capability. The schema forbids the key outright, so writing one is a
layer-1 failure rather than a stylistic preference -- but the reason it is
forbidden matters more than the rule: making the capability list a *file* the
next pass reads, rather than a memory of having just written one, is what lets
that pass quantify over it. §3 step 3's measurement below is what that buys.

**The document also carries `inputs_seen`: one row per input, for every input
`manifest.json` names.** Each row is `{artifact_id, own_kind_total, cited,
dropped}`, plus a `note` whenever `dropped` is not zero. `own_kind_total` is
how many `capability`-kind claims that artifact's claims file holds -- the
kind this pass is accountable for -- `cited` is how many of them appear in a
`claims` array you wrote, and `dropped` is the rest.

Total over `manifest.inputs`, which means **a row for every input including
the ones holding no `capability` claim at all.** Those rows read `0/0/0` and
need no note, so saying "this file held nothing of mine" costs one line. An
input with no row is not a claim about that input; it is a gap in the
accounting, and `check-refs` reports it as one.

The `note` is where a drop stops being a number. "The disputed side of a
contradiction recorded `unresolved`" and "restated by a claim I cited from
another artifact" are both good reasons to drop a claim; a human reads them at
gate 1, and they are the only record that the drop was a decision rather than
an oversight.

## 3. Method

1. **Read every file under `01-claims/`.** Skim first for scope, then read
   closely -- a merge built from a skim will drop the claim that only shows up
   once, in the file you read fastest. Read `01-contradictions/` too, before
   you write anything: a capability drafted from one side of a disagreement is
   harder to unwind than one drafted with the disagreement in view.

2. **Group claims into capabilities, citing the claim ids each grouping rests
   on.** A capability you write with no supporting claim is not a merge of
   what the claims said, it is an invention wearing a world-model shape.
   Where two or more claims describe the same capability -- from different
   input artifacts, or from the same one under a different `kind` -- fold them
   into one capability and cite every claim that supports it, not just the
   first one you read. Nothing checks your citations until the seal: a claim
   id that was never extracted is reported by `refs.check_world_model`
   against `01-world-model.json`, which is a repair round spent at gate 1 on a
   pass that finished long before.

3. **Give each capability a `binding`: the tool name a transcript will show,
   plus the `fixed_args` that distinguish it from a sibling capability
   sharing the same tool.** `emit` reports a finding for an accepted
   scenario whose capability has no `binding`, which costs a shipped test,
   so this is not optional decoration on top of the capability's identity --
   it is how a later stage will ever recognize that this capability is the
   one a trace or a live call actually invoked.

4. **Set `confidence` from the claims, not from how sure you feel.** A
   capability resting on one `reverse_engineered` claim from a single trace
   span is not `high` because you find it plausible.

5. **Fill in one `inputs_seen` row as you finish each claims file, not at the
   end.** A row assembled at the end from what you remember is a recollection
   of having read, and the difference between those two things is exactly what
   this accounting exists to measure. Write the row while the file is in front
   of you: the count of its claims of your kind, how many you cited, and -- if
   you dropped any -- why, in one sentence. `manifest.json` names every input,
   so you know how many rows there will be before you open the first one.

## 4. Invariants

1. Every capability carries at least one `claims[]` entry, and every entry
   resolves to a claim id that actually exists in `01-claims/`. Layer 1
   enforces the first (`claim_refs` carries `minItems: 1`);
   `refs.check_world_model` enforces the second, after the seal.

2. Capability `id`s are unique, and each one is stable enough to be cited:
   `rb-reconcile-outcomes` keys its entire output on them,
   `rb-reconcile-entities` quantifies over them, and every coverage cell
   downstream is named `cell:<capability_id>/<outcome_class_id>`.

3. No capability carries `outcome_classes`. The schema forbids the key.

4. Every capability the claims support is here. `refs.check_outcomes` reports
   a declared capability that the next pass left without outcome classes, but
   nothing anywhere reports a capability you never declared -- which is why
   completeness at this pass is a judgment nothing downstream can restore.

5. `inputs_seen` has one row per input in `manifest.json`, and in every row
   `cited + dropped == own_kind_total`. `rubrica check-refs` **recomputes**
   both `own_kind_total` (from `01-claims/`) and `cited` (from the `claims`
   arrays in this document), so neither is taken on your word: a count that
   does not match is a finding naming this file, and a missing row is a
   finding too. Nothing here judges *how much* you dropped -- that is a
   human's reading at gate 1 -- only that the arithmetic is true.

Before you report done, run
`rubrica validate --stage reconcile-capabilities --run <run>` and then
`rubrica check-refs --run <run>`, where `<run>` is the run directory you were
dispatched with. `--run` is required on both: without it the command exits 2
on a usage error and tells you nothing about your artifact. `check-refs` runs
every checker the run has inputs for, so it may also name an artifact an
earlier pass wrote; the findings that are yours name `01-capabilities.json`,
and those are your own defect to fix rather than findings to pass along.
Repair the artifact and run both again; report success only once both exit
clean.

## 5. Refusal conditions

Every condition below is one where the honest capability list is smaller, or
less definite, than one you could have written. A list that reads as a complete
API for the target, built from claims that only describe part of one, is not a
merge -- it is a plausible invention that every stage after you will treat as
ground truth, because none of them read the claims closely enough to tell the
difference.

- **You are tempted to add a capability the target "obviously" has** -- a
  delete beside the create, a list beside the get -- because no claim mentions
  it. Do not. Confabulation under under-specification is the characteristic
  failure of a prompt pipeline: an invented capability arrives downstream
  indistinguishable from a real one, and it takes a coverage cell,
  a scenario and a shipped test with it.

- **A capability's identity depends on a disagreement recorded
  `unresolved`.** Declare only the part both sides agree on, and leave the
  disputed part out. Modelling the side you find more convincing is a
  resolution written where no `rationale` can accompany it, which is worse
  than the disagreement it tidies away: `rb-reconcile-contradict` recorded
  that it could not be settled, and you have no evidence it did not have.

- **You are about to declare a capability, or fix its identity, because one
  reading matches what a system like this usually does.** Stop. That
  reasoning is convention knowledge standing in for evidence the claims do
  not contain, and it would produce the same answer whether or not the losing
  claim had ever been extracted at all -- which is the tell that nothing in
  front of you settled it. Model what the claims agree on; the silence is
  `rb-reconcile-gaps`' to record.

- **A claim describes an operation but nothing tells you the tool a
  transcript would show.** Declare the capability, cite the claim, and leave
  `binding` off rather than guessing a tool name. A guessed `binding` is
  worse than a missing one: a missing binding is a finding `emit` reports by
  name, while a wrong one silently matches nothing in any transcript and
  makes every scenario built on that capability unverifiable.

- **You cannot support a `params` entry from any claim.** Leave it out. An
  invented required parameter propagates into every seed and every expected
  answer built on the capability, and no gate can tell an invented parameter
  from a real one.

- **A claims file you could not read.** Do not guess its `own_kind_total` to
  complete the accounting: refuse, saying which file and what happened, and
  stop. A guessed count is a number nobody measured presented as one somebody
  did, and it defeats the whole point of the row -- a row you filled in
  without opening the file is indistinguishable, in the artifact, from one you
  filled in after reading it. A refusal here is recoverable; a fabricated
  count is not, because nothing downstream can tell it from a real one.
