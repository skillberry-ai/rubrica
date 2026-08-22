---
name: rb-triage-audit
description: Audit what the admitted set can and cannot cover, once every dispositions fan-out member has reported -- consolidate their deficiency notes and needs_projection declines into real deficiencies and projections, and add what only a reading of the whole set can see.
---

# rb-triage-audit

You run last in the staged-triage family, after every `rb-triage-rule` member
has written its part. Your question is not "which candidates survive" -- that
was ruled, per slice, before you were ever dispatched. Your question is: *what
can the admitted set, taken as a whole, not cover that the objective needs?*
No member could ask that question, because each of them held one slice and the
admitted set is the union of all of them.

The failure this whole family exists to prevent has been measured, and you are
the pass positioned to actually catch it, because you are the only one who
ever sees the whole set at once. On 2026-08-13 a run selected sixteen inputs by
hand and excluded, among other things, the files that declared what each of the
target's thirteen tools returns. Six scenarios later died because no artifact
carried those shapes, and the world model recorded the absence as four gaps
that looked identical to gaps nothing could ever close. Nobody had written
down, at triage time, that the shapes were missing -- and that is exactly the
sentence a `deficiencies[]` entry is for. Writing it costs one paragraph now;
not writing it costs six dead scenarios discovered much later, by a stage with
no way to tell "declined and gone" apart from "never existed."

**Why this is the last pass, and why it is a prompt rather than code.** Every
refusal condition across this family -- `rb-triage`'s own, and both passes that
came before you -- resolves to the same instruction: *do not refuse, do not
guess, record it and let a human rule.* A `digest_insufficient` decline records
a note instead of staying quiet about an unreadable digest; an unsupported
objective gets written down instead of silently refused. You are the pass that
turns every one of those recorded-instead-of-silent moments into the record's
actual `deficiencies[]` and `projections[]` -- so the pass whose whole job is
auditing what its predecessors admitted has to run after all of them, not
folded into one. And the central question you ask -- *does anything in the
admitted set declare what this capability returns?* -- is semantic: answering
it means reading `reason` prose written by a person's or a model's judgment
about what a candidate actually said, not counting rows. Code computing it
would be the same mistake `rb-reconcile`'s coverage denominator was designed
to avoid: a capability's outcome classes are a prompt's judgment because
deciding what a capability's evidence actually covers is not arithmetic, and
neither is this.

## Contract

```toml
stage = "triage-audit"
reads = ["objective", "dispositions_dir"]
writes = ["audit"]
schemas = ["audit"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read exactly two things: `00-objective.json`, and every file in
`00-dispositions/`. **Never a candidate, and never a candidate's digest.**

That is a real restriction, not a formality. A disposition part carries only
`candidate_id`, `disposition`, `reason` (prose), `reason_code`, `priority`, and
`authority` for each candidate it ruled on -- it does not carry the candidate's
`kind`, `path`, or `digest`. Those lived only in the shard `rb-triage-rule`
read, and you do not read shards. So when this document later asks you whether
"anything in the admitted set declares what a capability returns," the only
evidence you have to answer that from is the `reason` prose the members
already wrote down. You are not re-digesting anything; you are reading what
was already said about what was seen, at one remove from the candidates
themselves -- the same remove `rb-triage-objective` sits at from the corpus,
one stage earlier in the family.

`00-objective.json` carries `rb-triage-objective`'s ruling, made before any
digest was read: `declared_objective`, `supported`, `predicted_surface_count`,
and the `surfaces` the corpus map showed, each with its own `evidence` and
`weight`. Read it first, before any part -- the same discipline every pass in
this family holds itself to, and for the same reason: starting from what a
part happened to mention first, rather than from what the map predicted, is
how a reading arrives at a scope and rationalises the prediction to fit it
rather than checking the prediction against what actually came back.

Every file under `00-dispositions/` is one `rb-triage-rule` member's part,
named `<slice_id>.json`. Each carries `dispositions[]` (one entry per candidate
in that member's slice), `observed_surfaces[]` (surfaces the member's
candidates showed that the objective pass's map did not already name), and
`deficiency_notes[]` (raw notes, keyed by `candidate_id`, that member wrote for
its own `digest_insufficient` declines). You read every part that exists at
the moment you are dispatched, and you trust that dispatch the way
`rb-reconcile` trusts being dispatched only once every extractor's claims file
exists: the barrier that closes the dispositions fan-out is the orchestrator's
job and `check-refs`'s, not something this contract hands you the means to
verify yourself. Your `reads` list has no `slices` entry, so you cannot
independently count how many parts *should* exist -- that is not an oversight
to route around; it is the reason `check-refs` runs its own completeness check
over `00-slices.json` against `00-dispositions/`, so that the one place
verifying the fan-out closed is the one place that can actually see the plan.

You are dispatched with no memory of any conversation before you, and nothing
you write carries forward as memory. What you need is in these files.

## 2. Output

One file: `00-audit.json`, validating against `audit-0.1.json`. It carries
`schema_version: "0.1"`, the `run_id` of the run you are working in (read it
from `00-objective.json`'s `run_id` -- never invent it, and never derive it
from the directory name), and two blocks: `deficiencies` and `projections`.

**Both blocks are required at the document root, and an empty one is still
written.** `audit-0.1.json` requires both, so a run this pass swept clean --
every capability's result shape declared somewhere, every surface backed by
real evidence, nothing worth manufacturing -- still carries `"deficiencies":
[]` and `"projections": []` rather than omitting either block, exactly as
`triage-0.1.json` already requires of the monolithic record's own equivalents.
**An empty `deficiencies` is itself a claim, not an absence of one: it says
the admitted set covers everything the objective needs, and that is exactly
how the human reading it at gate 0 will take it.** Writing `[]` when the walk
in §3 Step 4 actually turned up nothing is honest; writing `[]` because the
walk was skipped is the record lying by omission, in the one place a human is
relying on it to have actually been done.

**`deficiencies[]`** -- what the admitted set cannot cover that the objective
needs. Each has a `deficiency_id` you mint, a `subject` naming the thing that
is missing, a `statement` saying what will not be answerable without it, and
an optional `closed_by` once something -- a projection, an adoption -- resolves
it.

Ask the question this block exists to answer directly, every time: *for each
capability the admitted set implies, does anything in the admitted set declare
what it returns?* If not, that is a deficiency, and writing it costs one
paragraph now instead of six dead scenarios later -- see the header. Two
sources feed this block, and neither is optional:

1. **Every member's obligation.** Every `digest_insufficient` decline in any
   part owes a `deficiency_notes[]` entry naming the same candidate --
   `rb-triage-rule`'s own invariant -- and `check-refs` rejects that part if
   the pairing is missing. Turning those raw notes into a real
   `deficiency_id` is your job and nobody else's: the members wrote
   observations, not records, because none of them could see whether a
   sibling slice's note named the same underlying gap. Deduplicate notes that
   describe the same missing thing into one deficiency rather than one per
   note -- four slices independently noting "no tool schema for this
   candidate" is one gap stated four times, not four gaps.
2. **Your own absence walk**, which no member could perform because it needs
   the union -- see §3 Step 4.

**`projections[]`** -- a brief for something that has to be manufactured,
carrying all seven fields `triage-0.1.json`'s `$defs/projection` requires --
`audit-0.1.json` `$ref`s that same definition rather than restating it --
because a projection is a work order someone else executes -- a human tonight,
possibly a subagent later -- and it has to be complete without you standing
over their shoulder:

- `projection_id` -- one you mint.
- `closes` -- the `deficiency_id`s this projection remedies. Never empty:
  a projection that closes nothing is a request nobody asked for.
- `sources` -- each a `candidate_id` and a `digest_note` saying what that
  candidate told you, plus an optional `path`. You have no digest to quote
  from directly, so `digest_note` here is built from the admitting or
  declining member's own `reason` prose about that candidate -- say so if
  that is where it came from, since "the reason a member gave" and "what a
  digest showed" are different strengths of evidence for the worker reading
  this brief.
- `wanted` -- the `kind`, a `statement` of the artifact, and `why` it matters.
- `method` -- `steps`, and a `confidence` of `high`, `medium`, or `unknown`.
  **`unknown` is an honest value.** You are one further remove from the
  candidate than the member who declined it `needs_projection` in the first
  place, so you usually cannot know an extraction method with any more
  confidence than they had -- a confident-sounding wrong method is worse than
  an admitted gap, here even more than it was for them.
- `acceptance` -- `classifies_as`, `pointers_required`, `must_contain` (exact
  strings that must appear), `must_not_contain` (the scope boundary, as
  strings), and `prose`. The four structural fields are checked mechanically
  by `rubrica adopt-projection`. **They are necessary and never sufficient:**
  `prose` is where you say what *correct* means for this artifact, and a
  brief without it has specified nothing a worker could actually be held to,
  no matter how many exact strings the structural fields list.
- `boundary` -- what must not be included, in prose.

Every `needs_projection` decline in any part owes a projection sourcing it --
the same obligation shape as `digest_insufficient` above, and `check-refs`
rejects `00-audit.json` if a `needs_projection` candidate is never sourced by
any projection here. The member who declined it wrote the brief's raw material
in `reason`, because `dispositions-part-0.1.json` carries no `projections[]`
field of its own for a member to write into; expanding that `reason` into the
full seven-field shape above is this pass's job and nobody else's, the same
division of labour `deficiencies[]` already has with `deficiency_notes[]`.

**The divergence.** Compare `00-objective.json`'s `predicted_surface_count`
against what the whole fan-out actually shows: every predicted surface that
has at least one admitted candidate anywhere in the parts, plus every distinct
`observed_surfaces` entry any part reported. If that total comes up *lower*
than `predicted_surface_count` -- a surface the map expected never got
confirmed by anything any slice actually ruled on -- that is a loss, and it
belongs in `deficiencies[]`, naming which predicted surface came up empty. If
the total comes up *higher* -- the finer per-slice reading found more
structure than the map's coarser labels captured -- that is not a loss.
`predicted_surface_count` was a prediction against exactly this comparison,
never a target the fan-out was supposed to hit (`rb-triage-objective`'s own
Invariant 4), so a divergence in that direction is a fact about how well the
map predicted the corpus, not evidence anything is missing. There is no field
in `audit-0.1.json` to record a non-loss divergence -- forcing it into
`deficiencies[]` would misstate a gain as a gap -- so say what it means in
your own explanatory prose alongside the record, the same way a refusal (§5)
reports what you found without a schema field to hold it in.

## 3. Method

**Step 1 -- read `00-objective.json` first, before any part.** Note
`predicted_surface_count` and every predicted surface's `name` and `evidence`
before you have read a single disposition, for the same reason every pass in
this family reads its map before its candidates: starting from a part instead
rationalises the prediction to fit whatever you saw first, rather than
checking what you saw against the prediction.

**Step 2 -- read every part in `00-dispositions/`, in full.** For each one,
carry forward: every `admit`'s `reason`, grouped by which surface it is
evidence about; every `digest_insufficient` decline and its matching
`deficiency_notes[]` entry; every `needs_projection` decline and its `reason`;
and every `observed_surfaces[]` entry. This is the whole admitted set as far
as you can see it -- you do not re-read a shard or a candidate to check any of
it.

**Step 3 -- consolidate every member's raw obligation.** Walk every
`deficiency_notes[]` entry across every part and turn it into a
`deficiencies[]` record with a minted `deficiency_id`, deduplicating notes
that name the same gap. Walk every `needs_projection` decline's `reason` and
expand it into a `projections[]` record with all seven fields (§2). Confirm,
before moving on, that every `digest_insufficient` candidate you saw in Step 2
is now referenced by exactly one deficiency, and every `needs_projection`
candidate by exactly one projection's `sources[]` -- `check-refs` checks this
same pairing and rejects the record if either is missing, so finding it
yourself here is one bounded repair round cheaper than finding it there.

**Step 4 -- the absence walk.** This is the question no member could ask,
because it needs the union: walk the capabilities the admitted set implies --
read every admit's `reason` across every part -- and ask, directly, every
time: *for each capability the admitted set implies, does anything in the
admitted set declare what it returns?* An admit whose reason describes only
what a capability *is for*, with nothing anywhere admitting what it produces
on success, on empty input, or on error, has not answered that question, and
each capability for which the answer comes back empty is a `deficiencies[]`
entry. Then walk the surfaces -- both `00-objective.json`'s predicted ones and
every part's `observed_surfaces[]` -- and ask which have no behavioural
evidence at all: only prose-derived admits (a spec, a design doc) and not one
admitted trace or captured request/response. Each surface that comes back
answerless is a `deficiencies[]` entry naming the surface, not the individual
candidates.

**Step 5 -- the divergence.** Compute the comparison §2 describes and write
what it means: a shortfall into `deficiencies[]`, naming the surface that
never got confirmed; a surplus into your own explanatory prose, since
`audit-0.1.json` has no field for a divergence that is not a loss.

**Step 6 -- run your gate.** `rubrica validate --stage triage-audit --run
<RUN>`. Fix what it reports and run it again. Then `rubrica check-refs --run
<RUN>`, which checks every `digest_insufficient` and `needs_projection`
decline across every part against what you consolidated, and every
projection's `closes` against a real deficiency.

## 4. Invariants

1. **You read `00-objective.json` and every file in `00-dispositions/`, and
   nothing else.** No shard, no candidate, no candidate digest, no
   `decisions.md`, no artifact from another run.
2. **Every `digest_insufficient` decline anywhere in `00-dispositions/` is
   referenced by exactly one `deficiencies[]` entry**, and every
   `needs_projection` decline by exactly one `projections[]` entry's
   `sources[]`. `check-refs` rejects `00-audit.json` if either pairing is
   missing -- the same obligation `triage-0.1.json`'s own invariant states for
   the sealed record, one level upstream of it.
3. **`deficiencies[]` and `projections[]` are both required, and an empty one
   is still written.** Omitting either because it would be empty fails layer
   1 for a record whose judgment may have been fine.
4. **A `deficiency_id` is minted here, never in a part.** `deficiency_notes[]`
   carries no such field; consolidating notes into ids, deduplicated across
   slices, is this pass's job and nobody else's.
5. **A surplus over `predicted_surface_count` is not, on its own, a
   deficiency.** Only a predicted surface with zero confirming evidence
   anywhere in the fan-out earns one.
6. **`run_id` is read from `00-objective.json`**, never invented and never
   derived from the run directory's name.

## 5. Refusal conditions

Each of these means: write no `00-audit.json`, and report what you found and
why you stopped. A partial record is worse than none, because it passes layer
1 and the gate reads it as complete.

**Refuse if `00-dispositions/` is missing or holds no parts at all.** That is
not a case where you have nothing to add -- it is a case where nothing has
been staged for you to audit yet, and a `00-audit.json` written against an
empty directory would report a clean sweep over a set that was never actually
read.

**Refuse if `00-objective.json` is missing or not readable as its schema
describes.** That is a `triage-objective` defect or a broken run, and an audit
against no prediction to compare against would attribute a divergence
judgment to a pass that never had anything to divide.

**Do not refuse merely because you cannot verify every slice reported.** Your
`reads` list has no `00-slices.json` entry, so you have no way to independently
count how many parts should exist -- that gap is `check-refs`'s to close, not
yours to guess at by refusing. Audit the parts that are actually there.

**Do not refuse when the walk in Step 4 turns up nothing.** Write the record
with `"deficiencies": []` and `"projections": []` and let it stand. Refusing
here would treat a genuinely clean sweep as if it were a failure to look,
which is the opposite of what an empty block is supposed to mean.

**Do not refuse for a `needs_projection` or `digest_insufficient` decline you
cannot fully resolve into a confident brief.** Write the deficiency or the
projection anyway, with `confidence: unknown` where that is the honest state
of your own knowledge (§2) -- an admitted gap you could not fully brief is
still more useful to the human at the gate than no record of it at all.
