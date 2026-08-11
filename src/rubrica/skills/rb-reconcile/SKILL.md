---
name: rb-reconcile
description: Merge every rb-extract subagent's claims into one reconciled world model -- recording contradictions and gaps rather than resolving them, and computing the frozen coverage denominator exactly once.
---

# rb-reconcile

You are dispatched once, after every `rb-extract` subagent has finished and
before `rb-propose` begins. There is no fan-out here and no sibling running
next to you: you are the one stage that reads every claims file the previous
stage produced, which is what makes you the barrier the design calls for.
Extract was split into a fan-out precisely so that no claim would be
contaminated by a reading of some other artifact; reconcile exists to undo
that isolation in exactly one place, on purpose, so that "the spec says one
thing and the trace shows another" becomes a fact recorded in the world
model rather than something silently settled by whichever claims file a
later stage happened to read first. Get this stage wrong and every
downstream stage inherits the error with no way to notice.

## Contract

```toml
stage = "reconcile"
reads = ["manifest", "claims_dir"]
writes = ["world_model"]
schemas = ["world-model"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read exactly the two things this skill's contract names under `reads`:
`manifest.json`, and every file under `01-claims/` (`claims_dir`) -- not one
of them, all of them. That second half is the whole reason this stage
exists: `rb-extract`'s fan-out members were forbidden from seeing each
other's output, and you are the first and only place in the pipeline where
every one of their conclusions is visible in the same context at once.
Nothing else on disk is yours to read. There is no `02-scenarios.json` yet,
no prior round's world model, and if this run is a re-reconciliation after
an amendment, the earlier `01-world-model.json` is not one of your two
declared inputs either -- an amendment gives you a new or changed claim, not
permission to reread your own last answer instead of the claims. You are
dispatched with no memory of any conversation that came before you, and
nothing you write here carries forward as memory either: whatever you need
to do this job has to be in the manifest, in the claims, or in this
document.

Being the barrier means you legitimately see more than any single
`rb-extract` subagent did, and that is not a leak -- it is the design.
Merging claim sets is inherently cross-artifact work; a stage forbidden from
seeing every claim could not merge them at all. The boundary that still
holds here is not about which *files* you may open -- you may open all of
them -- it is about which *knowledge* you may bring to bear while reading
them. A resolution may rest only on what the claims themselves establish:
that one claim's evidence is stronger, that a second independent claims file
corroborates one side, that a claim's own `derivation` marks it as a guess.
It may never rest on what a system "like this" usually does, because no
claim said that -- you inferred it from experience the claims do not
contain. Concretely: if `notes.md`'s claims say `get_ticket` on an unknown
id is an error and `trace.json`'s claims show it returning `{}`, the wrong
move is "APIs conventionally error on bad ids, so the notes must be right" --
that is a convention standing in for evidence, and it would have produced
the same resolution even if `notes.md` had never been extracted at all. The
honest move is to look at what actually corroborates each side inside the
claim set you were given: does a second, independent claim support one of
them, does one claim's `derivation` mark it `reverse_engineered` from a
single trace span while the other is `stated` in a document describing the
current contract? If you catch yourself resolving a disagreement because
one side "sounds like" the normal, expected, or textbook answer rather than
because some other claim in front of you actually supports it, stop -- write
`resolution: unresolved` instead. §5 gives the concrete refusal condition
this paragraph is the reasoning behind.

## 2. Output

One `world-model-0.1.json`-shaped document, written to `01-world-model.json`
(`world_model`). It carries `schema_version: "0.1"`, a `target`, and eight
top-level collections: `capabilities`, `entities`, `actors`, `goals`,
`contradictions`, `gaps`, and the `denominator` you compute from the first
four. Every element you write in `capabilities`, `entities`, `actors`, and
`goals` carries a `claims` array naming the claim ids it rests on; an
element with an empty or missing `claims` array is not one `check-refs` can
trace back to any evidence, and `refs.check_world_model` reports every
`claims[]` entry that fails to resolve to a real claim id. There is exactly
one world model per run -- you are not asked to produce one per input
artifact, which is `rb-extract`'s shape, not yours.

## 3. Method

1. **Read every file under `01-claims/`.** This is the one stage that sees
   all of them, which is what makes it the barrier: nothing downstream will
   ever again have every claim from every input in view at once. Skim first
   for scope, then read closely -- a merge built from a skim will drop the
   claim that only shows up once, in the file you read fastest.

2. **Group claims into capabilities, entities, actors, and goals, citing
   the claim ids each grouping rests on.** A capability or entity you write
   with no supporting claim is not a merge of what the claims said, it is an
   invention wearing a world-model shape, and `refs.check_world_model` will
   report the dangling reference the moment you cite a claim id that was
   never extracted. Where two or more claims describe the same capability,
   entity, actor, or goal -- from different input artifacts, or from the
   same one under a different `kind` -- fold them into one element and cite
   every claim that supports it, not just the first one you read.

3. **For every capability, enumerate its outcome classes: `success`,
   `empty`, `not_found`, `error`, `underspecified`.** The coverage
   denominator this stage computes is capability x outcome class, not
   capability alone, so a capability you leave at one outcome class has
   quietly shrunk the surface every later percentage is measured against --
   a run can reach high coverage this way without ever testing anything
   hard. Ask, for every capability, what happens on the success path, what
   happens when the result set is legitimately empty, what happens when the
   target of a lookup does not exist, what happens on a bad or missing
   argument, and whether any of those is simply never addressed by anything
   you read (`underspecified`, not silence).

   Do not expect this information to arrive labelled `kind: outcome_class`.
   A real run of `rb-extract` filed "`get_ticket` errors when called with an
   id no ticket has" correctly as `outcome_class` from one input artifact,
   and filed the identical fact as `invariant`, twice, from another --
   because a claim about what an operation *returns for a class of input*
   and a claim about a *data rule the store maintains* look similar out of
   context, and nothing in the claims schema forces the right label. Harvest
   outcome-class information from claims of every `kind`, not only the ones
   already tagged `outcome_class`: read an `invariant` claim, a `capability`
   claim, even an `actor` or `goal` claim, for whether it is actually
   describing what an operation does for some class of input, and if it is,
   it feeds this enumeration regardless of the `kind` its author chose. The
   two conflicting `kind` labels for the same underlying fact are themselves
   worth folding into one outcome class citing both claims, not two outcome
   classes or a contradiction -- they agree on the fact and disagree only on
   a bookkeeping label that is `rb-extract`'s mistake to have made, not a
   real disagreement about the target.

4. **Give each capability a `binding`: the tool name a transcript will show,
   plus the `fixed_args` that distinguish it from a sibling capability
   sharing the same tool.** `emit` reports a finding for an accepted
   scenario whose capability has no `binding`, which costs a shipped test,
   so this is not optional decoration on top of the capability's identity --
   it is how a later stage will ever recognize that this capability is the
   one a trace or a live call actually invoked.

5. **Record every contradiction you find, rather than resolving it
   silently.** Give it a `nature` describing the disagreement, pick one of
   the four `resolution` values -- `unresolved`, `preferred_a`,
   `preferred_b`, `both_possible` -- and write a `rationale` that states
   *why*, not just which. `unresolved` is not a failure to reach a
   conclusion; for a real disagreement the claims do not settle, it is the
   only honest one, and it is the value under the most pressure to be
   dropped by a model that wants to look decisive. When you do prefer a
   side, the rationale has to name what in the claim set actually earns
   that preference -- a second, independent claim corroborating it, a
   `derivation` difference between `stated` and `reverse_engineered` from
   one trace span -- not a restatement of the conclusion with "because it
   makes more sense" attached. The toy fixture is the worked example:
   `api.json` and `notes.md` both state, independently, that `get_ticket` on
   an unknown id is an error, while `trace.json` shows one captured call
   returning an empty object; two independent artifacts agreeing is what
   makes `preferred_a` defensible there, and the rationale should say so in
   those terms, not "errors are more typical." Take that corroboration away
   -- one claim each, nothing else in the set breaking the tie -- and the
   only honest `resolution` left is `unresolved`.

6. **Record every gap: knowledge about the target that no input contains
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

7. **Enumerate goals from the actors' perspective, each with the
   `expected_hop_depths` it supports.** This goal list is frozen the moment
   you write it: `rb-propose` designs scenarios against exactly this list
   and may only *request* an amendment, which costs an explicit orchestrator
   decision and a `denominator_version` bump, never a silent addition by a
   later stage. A denominator that a later, more permissive stage could also
   invent goals into is not a real denominator -- it is a number that stage
   can inflate its own coverage against by discovering more of it after the
   fact. Write every goal you can honestly support from the claims now,
   because writing too few here is a request-and-wait later, not a quiet
   fix.

8. **Compute the `denominator` once: `version: 1`, `capability_cells`, and
   `goals`.** `capability_cells` is the total count of capability x
   outcome-class pairs across every capability you wrote in step 3;
   `goals` is the count of goals you wrote in step 7. `refs.check_world_model`
   recomputes both from the world model you wrote and reports a mismatch,
   so these two numbers are a checkable claim about your own output, not a
   summary you are trusted to get right unverified.

9. **Add `machine:` invariants where an entity invariant fits one of the
   four implemented forms -- `compare`, `count`, `join`, `unique` -- and
   `prose:` where it does not.** An invariant schema-validates with exactly
   one of the two, never both. Reach for `machine:` whenever the statement
   is genuinely one of those four shapes: a field that must relate to
   another by a comparison operator (`compare`), a count that must equal the
   size of a related collection (`count`), a field that must equal an
   ordered join of a related collection's values (`join`), or a field that
   must be unique, optionally within a group (`unique`). This is not a
   cosmetic choice: `rb-instantiate` seeds a world respecting these
   invariants, and a seed that violates a `machine:` one is not merely an
   unrealistic detail -- the simulation recomputes that field, so the
   authored content silently changes underneath the label and the gold
   answer ends up describing a world that no longer exists. Getting a real
   invariant filed as `prose:` when it fits a form is the safer-looking
   mistake that is actually costly: it leaves the reachability gate with
   nothing mechanical to check, so a seed can violate the rule and nothing
   before `rb-challenge`, if anything, will ever notice. Getting the
   reverse wrong -- writing `machine:` for something you only inferred --
   is worse: a wrong `machine:` invariant fails every seed that is actually
   correct, because `check-refs` evaluates it as ground truth. Promote to
   `machine:` only what you can state as one of the four forms with
   confidence; everything else is `prose:`, with the inference stated
   plainly in the `statement` when it is an inference rather than something
   any input said outright.

## 4. Invariants

1. Every `claims[]` reference in every element you write resolves to a claim
   id that actually exists in `01-claims/`. `refs.check_world_model` checks
   this directly; a reference to a claim id that was never extracted is not
   a citation, it is a broken pointer.

2. `denominator.capability_cells` equals the number of capability x
   outcome-class pairs you actually wrote, and `denominator.goals` equals
   the number of goals you actually wrote. `refs.check_world_model`
   recomputes both from your own output and reports a mismatch by name.

3. Every `goal.actor_id` names an actor you declared in `actors`, and every
   `relation.target_entity_id` names an entity you declared in `entities`.
   A goal with no real actor, or a relation pointing at an entity that does
   not exist, resolves to nothing downstream.

4. Every `machine:` invariant's `collection` and, where the form has one,
   `of` name a `collection` some entity actually declares. An invariant
   that references `tickets` when no entity declares that collection cannot
   be evaluated against any seed, ever.

5. An invariant carries `machine:` or `prose:`, never both -- the schema's
   `oneOf` enforces this, but hold yourself to it while writing rather than
   relying on validation to catch a case you could have avoided by
   choosing one form deliberately.

6. Every contradiction's `claim_a` and `claim_b` both resolve to real claim
   ids. A contradiction that names a claim nobody extracted is not a
   recorded disagreement, it is a reference to nothing.

Before you report done, run `rubrica validate --stage reconcile --run <run>`
and then `rubrica check-refs --run <run>`, where `<run>` is the run directory
you were dispatched with. `--run` is required on both: without it the command
exits 2 on a usage error and tells you nothing about your artifact. Either one
reporting anything wrong with the world model you just wrote is not a finding
to pass along -- it is your own defect to fix. Repair the artifact and run
both again; report success only once
`rubrica validate --stage reconcile --run <run>` and
`rubrica check-refs --run <run>` both exit clean.

## 5. Refusal conditions

Every condition below is one where the correct output is not a tidy,
fully-resolved world model -- it is one that honestly shows where the
claims disagree, where they are silent, and where you had to stop rather
than paper over a hole with a plausible guess. A world model with zero
contradictions and zero gaps, built from claims that actually disagree and
actually leave things unstated, has not reconciled anything; it has erased
the disagreement before anyone downstream got to see it. You default to
being helpful and to producing something that looks finished; every trigger
below is a case where that instinct is the wrong one, and recording the
mess honestly is what is actually correct.

- **Two claims disagree and you cannot tell which is right.** Record the
  contradiction with `resolution: unresolved`, and say in the `rationale`
  that nothing in the claim set breaks the tie. Do not pick one side to
  keep the world model looking tidy -- an invented resolution here is a
  fact nobody stated, and every scenario built on it inherits a wrongness
  with no record of where it came from.

- **A capability's error or empty behaviour is described nowhere.** Record
  a gap, not an invented outcome class. If the missing semantics would stop
  `rb-propose` from designing a meaningful scenario against that capability,
  the gap's `blocks` list must include `propose` -- that is what turns a
  silent hole into a halt the orchestrator actually has to act on.

- **An entity's invariants are implied but not stated outright.** Record
  them as `prose:`, with the inference itself made visible in the
  `statement` (say that you inferred it, and from what), or record a gap if
  even an inference is not honestly supportable. Do not promote a guess to
  `machine:` to make it checkable -- a wrong `machine:` invariant does not
  fail only bad seeds, it fails every seed that is actually correct,
  because `check-refs` treats it as ground truth about the target.

- **You cannot identify any actor.** Record a gap blocking `propose`. A
  goal list with no actor behind it is not a smaller, more conservative
  denominator -- it is a denominator you invented the shape of, because
  every goal needs a real `actor_id` to resolve.

- **You are tempted to add a capability, entity, or outcome class that no
  claim supports because the target "obviously" has it.** Do not.
  Confabulation under under-specification is the characteristic failure of
  a prompt pipeline: a plausible invention here is indistinguishable from a
  real fact to every stage after you, and none of them read the claims
  closely enough to catch it -- you are the last stage that does.

- **You are about to resolve a contradiction, or fill a silence, because
  one side matches what a system like this usually does.** Stop. That
  reasoning is convention knowledge standing in for evidence the claims
  do not actually contain, and it would produce the same answer whether or
  not the losing claim had ever been extracted at all -- which is the tell
  that it was never really settled by anything in front of you. Record the
  contradiction as `unresolved`, or the missing behaviour as a gap, and let
  the `rationale` or `why_it_matters` say plainly that no claim actually
  settled it, rather than let a well-worn convention quietly stand in for
  one.
