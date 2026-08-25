---
name: rb-triage-objective
description: Rule on whether the declared objective is supported by the corpus map -- before any candidate is judged, and before the per-slice dispositions fan-out is ever dispatched.
---

# rb-triage-objective

You run first in the staged-triage family, ahead of every per-slice
dispositions member. Your question is narrower than the monolithic `rb-triage`
this pass was split out of ever asked in one breath: not *which candidates
survive*, but *can the corpus this survey found even carry the objective it
was told to chase* -- `breadth` across many surfaces, or `depth` on one. That
question does not need a single candidate's digest to answer, and answering
it before the fan-out is dispatched is the reason this pass exists as its own
stage rather than as a first paragraph inside a bigger one.

The failure this whole family exists to prevent has been measured, and it is
still the standard you are held to even though your slice of it is narrower:
on 2026-08-13 a run selected sixteen inputs by hand and excluded the files
that declared what each of the target's thirteen tools returns. Six scenarios
later died because no artifact carried those shapes. Your part of preventing
a repeat is naming, before anything else runs, whether the objective the run
was told to chase can be met from what the corpus actually holds -- and
handing a human the surfaces to look at if it cannot.

## Contract

```toml
stage = "triage-objective"
reads = ["slices"]
writes = ["objective"]
schemas = ["objective"]
invokes = ["validate"]
```

## 1. Inputs

You read exactly one file: `00-slices.json`. **A shard under `00-slices/` is
never yours to open, and neither is `00-catalogue.json`.** Both sit in the
same run directory, one ordinary `Read` away. A shard holds every candidate's
full `digest`, and the shards of a real corpus together come to very nearly
what the catalogue itself weighs -- so opening one is both a sibling member's
slice and precisely the unbounded read this pass exists not to perform. A read
audit sees it either way.

`00-slices.json` is the corpus map: every slice's `label`, the `groups` it
draws from, its total `bytes` and `candidate_ids`, and each group's
`provenance` -- how many of that group's candidates landed in this slice
versus how many exist in total, and which other slices hold the rest. This is
what lets you see the corpus's shape -- how many coherent regions it falls
into, and roughly how much evidence backs each one -- without opening what any
one candidate contains.

`00-slices.json`'s `catalogue_facts` block is everything about the catalogue
you may know, and it is there so that you never have to open the catalogue to
learn it:

- `request` -- the target's name and interface, the declared `objective`, and
  optionally an `objective_note` and a `scope_note`. Read it before anything
  else (§3, Step 1).
- `policy` -- the rules that shaped the candidate set.
- `excluded` -- what `survey` dropped mechanically, as a `total`, a
  `by_reason` tally, and the individual `entries` for those exclusion reasons
  an operator could reasonably dispute. `entries_truncated` says whether that
  entry list was cut short by its byte budget; when it is `true`, the tally is
  still complete and the paths are not.
- `candidate_bytes` -- one entry per catalogue candidate, giving that
  candidate's own **source size on disk**. This is what lets `weight.bytes`
  (§2) be arithmetic over real evidential weight rather than a guess.

**The point is not that a digest is forbidden information -- it is that a pass
which reads the corpus to size the corpus grows with it.** Everything above is
bounded by how many candidates the run admitted, rather than by how large they
are, which is why this pass can run in one dispatch ahead of the fan-out and
let the members that *do* open digests grow with the corpus instead. Firming up
a surface judgment by opening a shard would spend exactly that property.

`excluded` is worth reading for the reason it always was: a mechanical
exclusion you believe was wrong is a fact worth recording.
This pass does not write `deficiencies[]` -- that block does not exist in
`objective-0.1.json`, because closing a corpus gap is `rb-triage-audit`'s job,
run after every slice has reported what it actually observed. What you can do
here is name the concern in `objective_review.notes` and say plainly that
`rb-triage-audit` should look at it -- a pointer forward, not a decision you
are making in its place.

**The honest limitation, stated because a pass that does not know its own
blind spot cannot flag it:** `supported` is ruled from a map of labels, groups
and counts, never from a reading of the digests those counts summarize. A map
can be wrong in ways a reading of the digests would not have been -- a slice
labelled by one group name can still hold candidates that, read individually,
turn out to describe nothing the objective needs, or a corpus that looks
thin by candidate count can turn out to carry one enormous file that alone
answers the objective. This pass's `supported` verdict inherits that
blindness; §2's `predicted_surface_count` exists in part to give the members
that *do* read digests something concrete to check your map against.

You are dispatched with no memory of any conversation before you, and nothing
you write carries forward as memory. What you need is in this one file.

## 2. Output

One file: `00-objective.json`, validating against `objective-0.1.json`. It
carries `schema_version: "0.1"`, the `run_id` of the run you are working in
(read it from `00-slices.json`'s `run_id` -- never invent it, and never derive
it from the directory name), `predicted_surface_count`, and
`objective_review`.

**`objective_review`** -- the surfaces the corpus map shows, and whether the
objective the run was given is supported by them. It has the same shape
`rb-triage`'s monolithic record once carried inline, restated here as this
pass's whole output rather than one section of a larger one.

**Its three required keys are `declared_objective`, `supported`, and
`surfaces`** -- the surface list is the one called `surfaces`, and
`objective_review` is `additionalProperties: false`, so a synonym for any of
the three fails layer 1 rather than reading as a near miss. `notes` and
`recommended_objective` are the two optional ones. That is stated here because
your own output shape appears nowhere in what you read: `00-slices.json`
carries no `objective_review` to copy, so a key you have to infer is a key you
can invent, and one such invention downstream cost three dispatches and an
empty gate-0 ruling at exit 0.

A *surface* is a coherent region of the target's behaviour that a suite could
be built about: a persona, an API area, a workflow, a subsystem. At this
stage you are grouping the corpus map's own groups and slice labels by what
they appear to be evidence *about* -- one surface can span several of
`00-slices.json`'s `groups`, and one group can be a surface on its own. Each
entry in `surfaces` carries a `name`, the `evidence` (every `candidate_id` the
map assigns to it, gathered across every slice that group appears in via
`provenance`), and a `weight` of `{candidates, bytes}`.

**`weight.bytes` sums each evidence candidate's entry in
`catalogue_facts.candidate_bytes` -- the source file's size on disk.** The
file you are reading carries a second byte number, and it is the wrong one:
`slices[].bytes` is a slice's *serialized row* size, and `triage-slices`'
digest skeleton is clamped at 128 nodes, so a source file many times the size
of another can serialize to a nearly identical row once both are past the cap.
A metric that saturates cannot express which of two surfaces actually carries
more evidence. `candidate_bytes` does not saturate; `slices[].bytes` does, and
it is not a per-candidate number in the first place. `refs.check_objective`
recomputes both `weight.candidates` and `weight.bytes` from the catalogue and
rejects a value that does not match, so treat this as arithmetic to get right
rather than an impression to estimate.

`declared_objective` echoes `request.objective`. `supported` is your judgment
on whether the corpus map, read this coarsely, can carry it: `depth` on a
corpus map that shows one thin surface is not supported, and neither is
`breadth` when most of the map's surfaces show only a handful of candidates
each. If you would have chosen differently, say so in `recommended_objective`
with a `reason`. **You may not act on that recommendation.** You rule against
the objective you were given regardless of what you would have picked, and a
human at gate 0 decides whether to change it -- a re-scope this pass performed
itself would be invisible, and it would produce a selection that looks
coherent while answering a question the run was never actually given.

**`predicted_surface_count` is a prediction, not a report.** It is how many
surfaces you expect the later per-slice dispositions members to observe once
they read every candidate's digest, made from the map alone before any of
them has run. A member reporting far fewer or far more surfaces than this
number is a fact about how well this map-level pass predicted the corpus a
digest-level reading actually finds -- **not, on its own, proof that either
reading was wrong.** The map and the digests are different instruments looking
at the same corpus; treat a divergence as a signal worth a human's attention
at the gate, not as an error to silently reconcile in either direction.

## 3. Method

**Step 1 -- read `catalogue_facts.request` first, before the corpus map.** The
objective decides every subsequent call, and a reading that starts from the
corpus map's groups and slices and arrives at a scope only afterward
rationalises the objective to fit what it already found, rather than judging
the map against what it was actually asked for.

**Step 2 -- read the corpus map.** Walk `00-slices.json`'s `slices[]`: their
`label`s, their `groups`, and each group's `provenance` across every slice it
appears in. This is the whole shape of the corpus available to you -- how many
distinct regions it falls into, and how each region's evidence is
distributed.

**Step 3 -- group the map's groups into surfaces.** A surface can be one
group or several, judged by what they are evidence *about* rather than by
where `survey` happened to draw a boundary. Every `candidate_id` the map
assigns to a group you fold into a surface becomes that surface's evidence.

**Step 4 -- weigh each surface and rule on the objective.** For each surface,
sum `weight.candidates` (distinct evidence ids) and `weight.bytes` (each
evidence candidate's entry in `catalogue_facts.candidate_bytes`, per §2). Then
answer: can
the declared objective be met from a corpus shaped like this? Write
`supported`, and `recommended_objective` if you disagree -- see §2's
invariant on acting on it.

**Step 5 -- predict how many surfaces a digest-level reading will find.**
Write `predicted_surface_count` from the surfaces you just built. It is a
prediction against a later, finer-grained reading, not a claim that your
count is the true one -- see §2.

**Step 6 -- note any mechanical-exclusion concern for the audit.** If
`excluded` dropped something you believe should have stayed, say so in
`objective_review.notes` and name `rb-triage-audit` as the pass that will
turn a real gap into a recorded deficiency once the slices have reported
what they actually saw.

**Step 7 -- run your gate.** `rubrica validate --stage triage-objective --run
<RUN>`. Fix what it reports and run it again.

## 4. Invariants

1. **You read `00-slices.json`, and nothing else.** Not `00-catalogue.json`,
   not a shard under `00-slices/`, no `00-dispositions/` part, no
   `decisions.md`, no artifact from another run.
2. **`weight` is arithmetic over `catalogue_facts.candidate_bytes`**, never
   over `slices[].bytes`, never over a serialized row's size, and never an
   impression. A reader recomputes it.
3. **`recommended_objective` is a recommendation.** Your `supported` verdict
   and every surface you write judge `request.objective` as declared; you
   never substitute a different objective for the one you were given.
4. **`predicted_surface_count` is a prediction, not a report.** A later
   member's divergent, digest-level surface count is a fact about this map's
   adequacy, not evidence that either reading made an error.
5. **`run_id` is read from `00-slices.json`, never invented and never derived
   from the run directory's name.**

## 5. Refusal conditions

Each of these means: write no `00-objective.json`, and report what you found
and why you stopped.

**Refuse if `request.objective` is absent, or contradicts `scope_note`.** A
pass with no declared objective to check has nothing to rule on, and this
stage exists specifically to catch that before the dispositions fan-out is
ever dispatched -- refusing here is the whole point of running first. If the
objective says `breadth` and `scope_note` confines the run to one surface,
those are two different runs; say so and stop, rather than letting every
downstream slice inherit a contradiction nobody named.

**Do not refuse when the declared objective is unsupported.** Write the
record, set `objective_review.supported` to `false`, explain why in
`objective_review.notes`, and let the human at gate 0 rule. Refusing here
would leave the human with nothing to rule *on*, which is the opposite of the
help an unsupported-objective finding is supposed to give them -- the same
reasoning `rb-triage` itself was held to before it split into passes.

**Refuse if `00-slices.json` is missing, empty of slices, or not readable as
its schema describes.** That is a `survey` or `triage-slices` defect or a
broken run, and producing an objective ruling against it would attribute a
scoping decision to a pass that never actually read a corpus.

**Refuse if any `candidate_id` named in `slices[]` has no entry in
`catalogue_facts.candidate_bytes`.** You cannot weigh a surface whose evidence
includes a candidate you have no size for, and the alternative -- treating the
missing entry as zero -- would silently understate the one number a human reads
at gate 0 to compare one surface against another. This is a `triage-slices`
defect; say which ids are missing and stop.
