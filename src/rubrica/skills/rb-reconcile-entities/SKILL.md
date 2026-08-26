---
name: rb-reconcile-entities
description: Model the data the declared capabilities return -- one entity per shape a claim spells out -- with invariants written machine: only where they fit an implemented form and prose: everywhere else.
---

# rb-reconcile-entities

You are dispatched once, after `rb-reconcile-outcomes` and before
`rb-reconcile-goals`. You write the part of the world model that
`rb-instantiate` seeds a world from: every collection it fills, every field it
fills in, and every invariant it must respect while doing so. That last one is
the reason this pass carries the sharpest asymmetry in the family -- an
invariant written in the wrong form does not merely go unchecked, it can fail
every correct seed the pipeline ever produces.

## Contract

```toml
stage = "reconcile-entities"
reads = ["manifest", "claims_dir", "contradictions_dir", "capabilities_part"]
writes = ["entities_part"]
schemas = ["entities-part"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read the four things this skill's contract names under `reads`:
`manifest.json`, every file under `01-claims/` (`claims_dir`) -- not one of
them, all of them -- every file under `01-contradictions/`
(`contradictions_dir`), and `01-capabilities.json` (`capabilities_part`). Every
pass in this family reads all of the claims; the family is split on *output*,
not on claims, which is what keeps the barrier property the single-dispatch
stage had.

`01-capabilities.json` is the list §3 step 1 quantifies over. The
contradictions are a constraint, not background: where two claims disagree
about a field, a type or a rule and the disagreement is recorded `unresolved`,
you may not settle it by writing one of them into an entity. An entity field is
a place with no `rationale` and no `resolution`, so a disagreement resolved
here is resolved invisibly.

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
the contradictions, in the capability list, or in this document.

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
front of you actually supports it, stop -- model only what the claims
establish, and write the inference as `prose:` with the inference stated
plainly. §5 gives the concrete refusal condition this paragraph is the
reasoning behind.

## 2. Output

One `entities-part-0.1.json`-shaped document, written to `01-entities.json`
(`entities_part`). It carries `schema_version: "0.1"` and an `entities` array;
each entity has an `id`, a `name`, the `collection` it lives in, its `fields`,
its `relations`, its `invariants`, and a `claims` array naming the claim ids it
rests on.

`rb-instantiate` reads this through the sealed world model and seeds a world
from it: your `collection` names are the collections it fills, and your
`machine:` invariants are re-evaluated against what it wrote. That is the
consumer to keep in mind while writing -- not a reader.

**The document also carries `inputs_seen`: one row per input, for every input
`manifest.json` names.** Each row is `{artifact_id, own_kind_total, cited,
dropped}`, plus a `note` whenever `dropped` is not zero. `own_kind_total` is
how many `entity`-kind **and** `invariant`-kind claims that artifact's claims
file holds -- the two kinds this pass is accountable for, counted together,
because both come out of the same read -- `cited` is how many of them appear
in a `claims` array you wrote, whether that array sits on the entity or on one
of its invariants, and `dropped` is the rest.

Total over `manifest.inputs`, which means **a row for every input including
the ones holding no `entity` or `invariant` claim at all.** Those rows read
`0/0/0` and need no note, so saying "this file held nothing of mine" costs one
line. An input with no row is not a claim about that input; it is a gap in the
accounting, and `check-refs` reports it as one.

The `note` is where a drop stops being a number. "The disputed side of a
contradiction recorded `unresolved`" and "restated by a claim I cited from
another artifact" are both good reasons to drop a claim; a human reads them at
gate 1, and they are the only record that the drop was a decision rather than
an oversight.

## 3. Method

1. **For every capability declared in `01-capabilities.json`, if any claim
   describes the shape of what that capability returns, that shape becomes an
   entity.** A capability whose success payload a claim spells out field by
   field, with no entity modelling it, is a response nothing downstream can
   assert against -- and no gate reports it, because `refs.check_world_model`
   only checks that the claims you *did* cite resolve.

   Quantified over the capabilities in that file, deliberately, and not over
   claims. Measured: "for every capability" produced every outcome-class cell a
   real run needed, while an unquantified instruction to "group claims" dropped
   45% of them. A pass can check itself against five capabilities it can
   reread in a file; it cannot check itself against every statement in a
   document.

2. **Cite the claims each entity, field and invariant rests on.** An entity
   you write with no supporting claim is not a merge of what the claims said,
   it is an invention wearing a world-model shape, and every seed built from it
   describes a target that does not exist.

3. **Add `machine:` invariants where an entity invariant fits one of the
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

4. **Fill in one `inputs_seen` row as you finish each claims file, not at the
   end.** A row assembled at the end from what you remember is a recollection
   of having read, and the difference between those two things is exactly what
   this accounting exists to measure. Write the row while the file is in front
   of you: the count of its claims of your kind, how many you cited, and -- if
   you dropped any -- why, in one sentence. `manifest.json` names every input,
   so you know how many rows there will be before you open the first one.

## 4. Invariants

1. Every entity carries at least one `claims[]` entry, and every entry
   resolves to a claim id that actually exists in `01-claims/`. Layer 1
   enforces the first (`claim_refs` carries `minItems: 1`);
   `refs.check_world_model` enforces the second, after the seal -- which means
   a dangling citation here surfaces at gate 1 against
   `01-world-model.json`, a repair round spent on a pass that finished long
   before.

2. Every `relation.target_entity_id` names an entity you declared in this same
   file. A relation pointing at an entity that does not exist resolves to
   nothing downstream.

3. Every `machine:` invariant's `collection` and, where the form has one, `of`
   name a `collection` some entity here actually declares. An invariant that
   references `tickets` when no entity declares that collection cannot be
   evaluated against any seed, ever.

4. An invariant carries `machine:` or `prose:`, never both -- the schema's
   `oneOf` enforces this, but hold yourself to it while writing rather than
   relying on validation to catch a case you could have avoided by choosing
   one form deliberately.

5. Entity `id`s and `collection` names are unique, and stable enough to be
   cited: `rb-instantiate` fills collections by name and `check-refs`
   evaluates invariants against them.

6. `inputs_seen` has one row per input in `manifest.json`, and in every row
   `cited + dropped == own_kind_total`. `rubrica check-refs` **recomputes**
   both `own_kind_total` (from `01-claims/`) and `cited` (from the `claims`
   arrays in this document), so neither is taken on your word: a count that
   does not match is a finding naming this file, and a missing row is a
   finding too. Nothing here judges *how much* you dropped -- that is a
   human's reading at gate 1 -- only that the arithmetic is true.

Before you report done, run
`rubrica validate --stage reconcile-entities --run <run>` and then
`rubrica check-refs --run <run>`, where `<run>` is the run directory you were
dispatched with. `--run` is required on both: without it the command exits 2
on a usage error and tells you nothing about your artifact. `check-refs` runs
every checker the run has inputs for, so it may also name an artifact an
earlier pass wrote; the findings that are yours name `01-entities.json`, and
those are your own defect to fix rather than findings to pass along. Repair the
artifact and run both again; report success only once both exit clean.

## 5. Refusal conditions

Every condition below is one where the honest entity model is thinner, or its
invariants weaker, than one you could have written. The instinct to make a data
model look complete is exactly wrong here: an invented field costs a wrong
seed, and an invented `machine:` invariant costs every correct one.

- **An entity's invariants are implied but not stated outright.** Record
  them as `prose:`, with the inference itself made visible in the
  `statement` (say that you inferred it, and from what), or leave it out
  entirely if even an inference is not honestly supportable -- a silence worth
  recording is a gap, and `rb-reconcile-gaps` reads the same claims you do.
  Do not promote a guess to `machine:` to make it checkable -- a wrong
  `machine:` invariant does not fail only bad seeds, it fails every seed that
  is actually correct, because `check-refs` treats it as ground truth about
  the target.

- **A capability returns something, but no claim spells out its shape.** Do
  not model an entity for it from the operation's name. An entity invented
  from a plausible response shape is asserted against by every expected answer
  built on that capability, and nothing downstream can tell an invented field
  from a real one.

- **A field's type or requiredness is disputed, and `01-contradictions/`
  records the disagreement `unresolved`.** Model what both claims agree on and
  leave the disputed part out, or state it in a `prose:` invariant that names
  the disagreement. Writing one side into the field list settles a
  disagreement that `rb-reconcile-contradict` was accountable for and recorded
  as unsettled, in a place with no room to say so.

- **You are about to add a field, a relation or an invariant because a store
  like this one usually has it** -- a `created_at`, a unique id, a foreign key.
  Stop. That reasoning is convention knowledge standing in for evidence the
  claims do not contain, and it would produce the same model whether or not any
  input had ever been extracted. If the rule is a real one you inferred, write
  it as `prose:` and say what you inferred it from; if you cannot say, do not
  write it at all.

- **A claims file you could not read.** Do not guess its `own_kind_total` to
  complete the accounting: refuse, saying which file and what happened, and
  stop. A guessed count is a number nobody measured presented as one somebody
  did, and it defeats the whole point of the row -- a row you filled in
  without opening the file is indistinguishable, in the artifact, from one you
  filled in after reading it. A refusal here is recoverable; a fabricated
  count is not, because nothing downstream can tell it from a real one.
