---
name: rb-reconcile-outcomes
description: For every capability already declared, enumerate its outcome classes -- success, empty, not_found, error, underspecified -- harvested from claims of every kind, not only the ones labelled outcome_class.
---

# rb-reconcile-outcomes

You are dispatched once, after `rb-reconcile-capabilities` has written the
capability list and before `rb-reconcile-entities`. You write the other half of
the coverage denominator's first factor: `reconcile-seal` counts capability x
outcome-class cells, so a capability you leave at one outcome class has quietly
shrunk the surface every later percentage is measured against, and a run can
reach high coverage that way without ever testing anything hard.

Your output is a join table, not a collection. `outcome_classes` lives nested
inside the capability object in the world model, so you write one entry per
capability id and `reconcile-seal` folds each entry into its capability.

## Contract

```toml
stage = "reconcile-outcomes"
reads = ["manifest", "claims_dir", "contradictions_dir", "capabilities_part"]
writes = ["outcomes_part"]
schemas = ["outcomes-part"]
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

`01-capabilities.json` is the list you quantify over, and reading it as a file
rather than remembering having written it is the point of splitting the two
passes: §3 opens with "for each capability in `01-capabilities.json`", and that
quantification is measurable. The contradictions are a constraint, not
background: a disagreement recorded `unresolved` may not be settled by which
outcome classes you enumerate. If the two claims disagree about whether a bad
id errors or returns empty, that is not a licence to pick one -- it is a reason
to enumerate both classes, or to record neither and leave the silence to
`rb-reconcile-gaps`.

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
front of you actually supports it, stop -- enumerate what the claims support
and let `underspecified` or a gap carry the rest. §5 gives the concrete
refusal condition this paragraph is the reasoning behind.

## 2. Output

One `outcomes-part-0.1.json`-shaped document, written to `01-outcomes.json`
(`outcomes_part`). It carries `schema_version: "0.1"` and an `outcomes` array;
each entry is one `capability_id` and the `outcome_classes` for it, each class
with an `id`, a `kind` from `success`, `empty`, `not_found`, `error` and
`underspecified`, a `description`, and its own `claims`.

**An `underspecified` class carries `claims` like every other one, and what it
cites is the operation, not the outcome.** Layer 1 requires at least one entry
(`claim_refs` carries `minItems: 1`), and no claim states the behaviour you are
recording as unstated -- so cite the claim or claims that establish the
operation the class belongs to. They are not evidence *for* the outcome; they
are the evidence that this outcome is expected of that operation and nowhere
recorded. `rb-reconcile-gaps` makes the same move one granularity up, where a
gap's claims are not evidence for the unknown but the claims that make the
absence matter.

**One entry per capability, and exactly one.** `refs.check_outcomes` reports
any declared capability with no entry -- an unswept capability shrinks the
denominator, and nothing checked that while both halves lived in one turn. It
also reports an entry naming a capability nobody declared. Two entries for the
same capability it cannot see at all, because it compares sets of capability
ids and two entries collapse to one member; `reconcile-seal` refuses to write a
world model in that case, and it is the only place a duplicate is ever caught.

**The document also carries `inputs_seen`: one row per input, for every input
`manifest.json` names.** Each row is `{artifact_id, own_kind_total, cited,
dropped}`, plus a `note` whenever `dropped` is not zero. `own_kind_total` is
how many `outcome_class`-kind claims that artifact's claims file holds -- the
kind this pass is accountable for -- `cited` is how many of them appear in a
`claims` array you wrote, on an outcome class inside an `outcomes` record, and
`dropped` is the rest.

**Only claims of your own kind count toward `cited`, wherever else you
legitimately cite.** §3 step 2 has you harvest outcome-class information from
claims of every `kind`, and an `underspecified` class cites the claims that
establish its operation rather than the outcome; both of those citations are
right, and neither belongs in this number. `check-refs` recomputes `cited` by
intersecting the ids you cited with the named artifact's `outcome_class`-kind
claims only, so a cross-kind citation counted here is a disagreement you will
have to repair. It is not lost, either: the pass that owns that claim's kind
accounts for it, and drops it with a note saying you modelled it.

Total over `manifest.inputs`, which means **a row for every input including
the ones holding no `outcome_class` claim at all.** Those rows read `0/0/0`
and need no note, so saying "this file held nothing of mine" costs one line.
An input with no row is not a claim about that input; it is a gap in the
accounting, and `check-refs` reports it as one.

The `note` is where a drop stops being a number. "The disputed side of a
contradiction recorded `unresolved`" and "restated by a claim I cited from
another artifact" are both good reasons to drop a claim; a human reads them at
gate 1, and they are the only record that the drop was a decision rather than
an oversight.

## 3. Method

**Read each claims file once, in bounded slices, and never re-open one you
have finished.** This is a budget instruction, not a matter of style. Measured on a real dispatch of **this pass**, against a 22-input, 403 KB `01-claims/`:
the dispatch died with `Prompt is too long` after 84 turns and 80 `Read` calls,
**none** of which passed `offset` or `limit`, and the same eight claim files were
re-read three times each as the member ran out of room. It wrote nothing, so the
round cost a whole pass and produced no partial to repair.

Concretely: work through `manifest.inputs` in order, so you can always say which
files you have not opened yet; read a large claims file in slices with `offset`
and `limit` rather than whole; and when you have taken what a file offers, write
down the claim ids you are carrying forward instead of planning to re-read it. A
re-read is the one behaviour that turns a bounded read into an unbounded one, and
it does not feel like one at the time -- it feels like checking.

If you cannot take everything a claims file offers, `inputs_seen`'s `note` is the channel for saying so -- layer 1 rejects a dropped claim with no note, so a partial read recorded there is a fact the next reader has, and a partial read not recorded there is one nobody has.

1. **For each capability in `01-capabilities.json`, enumerate its outcome
   classes: `success`, `empty`, `not_found`, `error`, `underspecified`.** Ask,
   for every capability in that file, what happens on the success path, what
   happens when the result set is legitimately empty, what happens when the
   target of a lookup does not exist, what happens on a bad or missing
   argument, and whether any of those is simply never addressed by anything
   you read (`underspecified`, not silence).

   The quantification is over the capability list, deliberately, and not over
   claims. Measured: "for every capability" produced every outcome-class cell
   a real run needed, while an unquantified instruction to "group claims"
   dropped 45% of them. A pass can check itself against five capabilities it
   can reread in a file; it cannot check itself against every statement in a
   document.

2. **Do not expect this information to arrive labelled `kind:
   outcome_class`.** A real run of `rb-extract` filed "`get_ticket` errors when
   called with an id no ticket has" correctly as `outcome_class` from one input
   artifact, and filed the identical fact as `invariant`, twice, from another
   -- because a claim about what an operation *returns for a class of input*
   and a claim about a *data rule the store maintains* look similar out of
   context, and nothing in the claims schema forces the right label. Harvest
   outcome-class information from claims of every `kind`, not only the ones
   already tagged `outcome_class`: read an `invariant` claim, a `capability`
   claim, even an `actor` or `goal` claim, for whether it is actually
   describing what an operation does for some class of input, and if it is, it
   feeds this enumeration regardless of the `kind` its author chose. The two
   conflicting `kind` labels for the same underlying fact are themselves worth
   folding into one outcome class citing both claims, not two outcome classes
   and not a contradiction -- they agree on the fact and disagree only on a
   bookkeeping label that is `rb-extract`'s mistake to have made, not a real
   disagreement about the target.

3. **Write `underspecified` where nothing addresses a class at all.** It is a
   real outcome class with a real cell in the denominator, and it is the
   honest record that this behaviour is unknown. Leaving the class out
   entirely says the opposite -- that the capability has no such case -- and
   nothing downstream can tell the two apart. Cite claims on it as you would on
   any other class: the ones that establish the operation, per §2. Never an id
   you invented to satisfy the requirement -- `refs.check_world_model` resolves
   every citation after the seal, so a fabricated one costs a repair round at
   gate 1 against an artifact you finished long before.

4. **Fill in one `inputs_seen` row as you finish each claims file, not at the
   end.** A row assembled at the end from what you remember is a recollection
   of having read, and the difference between those two things is exactly what
   this accounting exists to measure. Write the row while the file is in front
   of you: the count of its claims of your kind, how many you cited, and -- if
   you dropped any -- why, in one sentence. `manifest.json` names every input,
   so you know how many rows there will be before you open the first one.

## 4. Invariants

1. Every capability declared in `01-capabilities.json` has exactly one entry
   here. `refs.check_outcomes` reports each one that does not, and names the
   reason: a capability with no outcome classes names no cells at all, so a
   capability the target can be driven against leaves the surface every later
   percentage is measured against smaller than it should be, and one it cannot
   leaves nothing for the report's `unreachable` holes to account for.

2. No entry names a capability `01-capabilities.json` does not declare.
   `check_outcomes` reports that direction too, and `reconcile-seal` refuses
   to assemble a world model at all rather than dropping the entry, because a
   dropped entry produces a coherent-looking world model missing cells an
   artifact declared.

3. No capability has two entries. Neither layer sees this -- `check_outcomes`
   compares sets -- so `reconcile-seal`'s refusal is the only thing between a
   duplicate and a silently halved outcome list.

4. Outcome-class `id`s are unique within their capability, and stable: every
   coverage cell downstream is named `cell:<capability_id>/<outcome_class_id>`,
   and `rb-propose` targets holes by that name.

5. `inputs_seen` has one row per input in `manifest.json`, and in every row
   `cited + dropped == own_kind_total`. `rubrica check-refs` **recomputes**
   both `own_kind_total` (from `01-claims/`) and `cited` (from the `claims`
   arrays in this document), so neither is taken on your word: a count that
   does not match is a finding naming this file, and a missing row is a
   finding too. Nothing here judges *how much* you dropped -- that is a
   human's reading at gate 1 -- only that the arithmetic is true.

Before you report done, run
`rubrica validate --stage reconcile-outcomes --run <run>` and then
`rubrica check-refs --run <run>`, where `<run>` is the run directory you were
dispatched with. `--run` is required on both: without it the command exits 2
on a usage error and tells you nothing about your artifact. `check-refs` runs
every checker the run has inputs for, so it may also name an artifact an
earlier pass wrote; the findings that are yours name `01-outcomes.json`, and
those are your own defect to fix rather than findings to pass along. Repair the
artifact and run both again; report success only once both exit clean.

## 5. Refusal conditions

Every condition below is one where the honest enumeration looks less complete,
or less confident, than one you could have written. The failure this pass is
most exposed to is the opposite of a missing cell: a full five-class
enumeration for a capability the claims describe in one sentence, every
description plausible and none of it stated anywhere.

- **A capability's error or empty behaviour is described nowhere.** Write the
  class with `kind: underspecified` and say in the `description` that no input
  addresses it. Do not invent the behaviour, and do not silently omit the
  class: the first is a fact nobody stated, the second is a claim that the
  case does not exist. If the missing semantics would stop `rb-propose` from
  designing a meaningful scenario against that capability, that is a gap for
  `rb-reconcile-gaps` to record with `propose` in its `blocks` list -- you
  read the same claims it does, but you have nowhere to write a gap.

- **Two claims disagree about what a class of input returns, and
  `01-contradictions/` records the disagreement `unresolved`.** Enumerate both
  classes and say in each `description` which claim it rests on, or write
  `underspecified` if you cannot state either honestly. Do not pick the side
  you find more convincing: `rb-reconcile-contradict` was accountable for that
  decision and recorded that the claims did not settle it, and an outcome
  class has no `rationale` field in which you could disagree on the record.

- **You are about to fill a silence because one answer matches what a system
  like this usually does.** Stop. That reasoning is convention knowledge
  standing in for evidence the claims do not contain, and it would produce the
  same answer whether or not the input had ever been extracted at all -- which
  is the tell that nothing in front of you settled it. `underspecified` is the
  honest class, and its `description` should say plainly that no claim
  addressed the case.

- **A capability in `01-capabilities.json` is one you would not have
  declared.** Write its entry anyway. Skipping it is a finding
  `refs.check_outcomes` reports against your artifact, and it is not the
  channel for disagreeing with the previous pass: a capability with no
  supporting claim is a gap `rb-reconcile-gaps` audits for and records.

- **A claims file you could not read.** Do not guess its `own_kind_total` to
  complete the accounting: refuse, saying which file and what happened, and
  stop. A guessed count is a number nobody measured presented as one somebody
  did, and it defeats the whole point of the row -- a row you filled in
  without opening the file is indistinguishable, in the artifact, from one you
  filled in after reading it. A refusal here is recoverable; a fabricated
  count is not, because nothing downstream can tell it from a real one.
