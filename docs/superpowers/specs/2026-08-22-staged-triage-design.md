# Staging triage into a code-sliced fan-out

**Date:** 2026-08-22
**Status:** design, approved in conversation; no implementation yet
**Issue:** #3. Filed alongside it from the same investigation: #4.
**Supersedes nothing.** `triage` has been a single dispatch since the stage
existed.

---

## 1. The problem, root-caused

`rb-triage` is dispatched once and must rule on every candidate in
`00-catalogue.json`. On the `parsec` corpus that catalogue is 595KB / 351
candidates, and the dispatch does not finish. Two observed outcomes, one cause:
one run died during context compaction, another exhausted its whole dollar
budget over 34 turns and ~2.0M cache-read tokens, neither writing an artifact.

The cause is **input volume**, and it is not the byte cap.
`DEFAULT_MAX_CATALOGUE_BYTES` was set to 1MiB deliberately, with headroom above
the then-measured 476KB rather than to bind on the corpus we had, and it is
doing exactly that. The dispatch reads the file in chunked `offset`/`limit`
reads — the correct workaround for the harness's 256KB whole-file refusal — and
every chunk still lands in context and stays there. Reading 595KB in thirty
pieces is still having read 595KB.

Two things make it worse than "the file is large", and both are recorded in #3:
`canonical_bytes` sorts keys, so `candidates` sorts first and everything the
stage needs to situate itself (`request`, `policy`, `run_id`) lands in the last
0.1% of the file, which a chunk reader has to hunt for; and 130 of the 351
candidates are elements exploded out of a single trace capture.

**Neither cap is protective.** The observed death is at 351 candidates / 595KB;
`DEFAULT_MAX_CANDIDATES` is 500 and `DEFAULT_MAX_CATALOGUE_BYTES` is 1MiB. A
corpus that kills the stage has already passed both guards. This is the same
shape as `limitations.md`'s entry on `max_rounds`' default being binding rather
than protective.

`limitations.md` predicted this and named the fix class: "If real corpora
routinely exceed it, triage needs a clustering pass, and that is a redesign
rather than a parameter." This is that trigger firing.

That entry's arithmetic is also 3x optimistic and should be corrected when this
lands. It sizes the barrier at "roughly 400 bytes of digest each"; measured on
the same corpus, the mean candidate row is 1,645 bytes and the mean digest 1,186,
with digests 72% of the candidates array.

### 1.1 Why the staged-reconcile design does not transfer directly

`reconcile` was split for a different reason. Its dispatch dies on **time to
first byte** — a server-side close at ~300s with no bytes on the stream — so
that design reduces how much each pass must think before writing, while
deliberately keeping **every pass reading all of `01-claims/`**. Its §2 records
the barrier property surviving whole, and its §3 rejects a code-proposed pair
filter at length.

Triage cannot copy that. Passes that each re-read the whole catalogue buy it
nothing, because the catalogue is what does not fit. **Triage has to split on
input**, which is the one thing the reconcile family refused to do.

The reconcile design's own reasoning is nevertheless what licenses this one. Its
`limitations.md` entry on the subject cover uses triage as the *good* example,
and the distinction it draws is the argument for slicing candidates:

> Triage's loss is a *decision*: the catalogue lists every candidate, a decline
> names one and carries a reason, `rb-triage` has a `digest_insufficient`
> disposition for the case where it knows the digest was not enough to judge,
> and a human at gate 0 can overrule any of it per candidate. A cross-subject
> pair is an **absence**.

Slicing candidates preserves every one of those properties. Each slice member
still writes a reasoned, human-overrulable disposition for every candidate it
holds, and totality is mechanically checkable because the catalogue enumerates
the population. What slicing costs is one thing, named in §12.

## 2. What changes, and what does not

Unchanged, deliberately:

- **`00-triage.json` keeps its path, its schema and its byte shape.** `intake`
  is untouched, and so is everything downstream of it. `triage-0.1.json` is not
  revised.
- **Human gate 0 stays exactly where it is** — after the triage record exists,
  before `intake`. No new human gate is introduced: none of these passes decides
  anything a human could not review better against the assembled record.
- **Gate 0 remains different in kind.** It still decides what the run can ever
  know, and it is still held by someone other than the party that selected the
  inputs. Splitting the selecting party into four passes does not change who
  ratifies.
- **The digest stays the unit of judgment.** No pass opens a candidate file.
  §1's cost argument and its comparability argument both survive; §6 is what
  keeps the second one true.

Changed:

- `triage` is replaced by a sequence: a code slicer, three prompt passes (one of
  them a fan-out), and a code seal.
- **No dispatch's input grows with the corpus.** A slice's bytes are bounded by a
  cap code enforces.
- Each pass carries its own row in `manifest.stages`, so model, effort and skill
  digest are recorded per pass.
- `adopt-projection` stops editing a sealed artifact in place (§8.1).

## 3. Rejected alternatives

### 3.1 Tuning the caps down

Converts a mid-dispatch death into an up-front `UsageError`, which is a better
failure mode and is worth doing anyway (§6). But it rejects the corpus rather
than triaging it, so it is a stopgap. It is also the parameter change
`limitations.md` already ruled insufficient.

### 3.2 A prompt cuts the slices

The obvious mirror of `rb-reconcile-subjects`, and it is unavailable. Cutting
requires seeing every candidate, and any single-dispatch view of every candidate
grows with the corpus — a thin index included. Under a hard bound the first cut
has to be code, or it has to be a fold of folds, which is a great deal of
machinery to buy the same partition.

### 3.3 Code computes the surfaces

Rejected. `objective_review`'s surfaces are described in the current skill as the
part of the record "that lets a human see that the objective they declared
excludes something they wanted." Making them arithmetic would take the highest
judgment in gate 0's reading surface away from a prompt, which is the mistake
`limitations.md` already records once for the coverage denominator. Code groups
candidates for *reading*; it does not name what they are evidence about.

### 3.4 Bottom-up roll-up of the directory tree

Measured and rejected. Rolling each directory's candidates into its parent while
the subtree fits produced, on the parsec catalogue at a 64KB cap, **20 slices
with both failure modes at once**: kind-split mega-slices (85 source files from
all over the tree, because `parsec/` rolled up and then split by kind) and eight
1-candidate orphans under `parsec/tests/skills_fixtures/*` whose siblings could
not roll up. Top-down recursion (§5) yields 11 coherent slices on the same input.

### 3.5 First-fit-decreasing packing

Measured and rejected. FFD packs by size alone, so it fills a 64KB slice with
`parsec/tests` plus `parsec/scripts` plus whatever else fits — spending exactly
the coherence the slice key exists to buy. Packing is restricted to **adjacent
siblings** in the recursion's own order (§5).

### 3.6 Kind-first slicing

Rejected without needing a measurement. Grouping all traces, then all source,
then all design docs makes near-duplicate detection strong within a slice, but it
splits every surface across slices *by construction*, since a surface is usually
evidenced by a trace and a document and some source at once.

### 3.7 Slice boundaries the member may renegotiate

Rejected. A member handing back candidates it judges belong elsewhere, with a
second round re-cutting, is more faithful to judgment — at the cost of a
convergence question and a totality check that no longer reduces to a partition.

## 4. The stage sequence

`paths.STAGES` loses `triage` and gains the following, in this order, between
`survey` and `intake`.

| Stage | Runs as | Writes | Bounded by |
|---|---|---|---|
| `triage-slices` | code | `00-slices.json` | streams; nothing in context |
| `triage-objective` | `rb-triage-objective` | `00-objective.json` | a code-computed corpus map |
| `triage-rule` | `rb-triage-rule` — fan-out, one per slice | `00-dispositions/<slice_id>.json` | the per-slice byte cap |
| `triage-audit` | `rb-triage-audit` | `00-audit.json` | the parts, never the candidates |
| `triage-seal` | code | `00-triage.json` | streams |

**Gates.** Every stage is gated on `validate` for its own kind. `triage-rule`
and `triage-seal` are additionally gated on `check-refs`, the first only once
every fan-out member has finished — `refs.check_disposition_parts` reports every
slice without a part from the moment `00-dispositions/` exists, so mid-fan-out
most are missing by construction. This is the caveat `check_verdicts` already
carries and it must be documented the same way. There is no stage-scoped
`check-refs`.

**Human gate 0 sits after `triage-seal`**, unchanged.

**Concurrency.** The `triage-rule` fan-out runs **at most 3 members at a time**,
for the unrelated gateway failure the reconcile design also obeys: envoy returns
`upstream connect error ... connection timeout` intermittently at 5+ concurrent
streaming requests.

Compound names rather than four new verbs, for the reason the reconcile family
settled: these are **one logical step engineered as substeps**, and
`paths.STAGES` is the pipeline's ordering and its documentation at once. All
artifacts stay in the `00-` band, whose meaning — what this run will be allowed
to know — is preserved.

### 4.1 Why the objective is ruled first

The current skill's method opens: "read `request` first, before any candidate.
The objective decides every subsequent call, and a reading that starts from the
candidates arrives at a scope and then rationalises the objective to fit it."

A design that ruled the objective *after* the per-candidate passes would move
exactly that rationalisation from inside one context to across stages, where it
is harder to see rather than absent. So `rb-triage-objective` runs first and
reads `request` plus a code-computed corpus map — the directory tree, kind and
byte counts per subtree, the slice labels and sizes. No candidate digests, so its
input does not grow with the corpus.

This buys an observable the single dispatch never had. The objective pass
**predicts** surfaces from the corpus map; the members **observe** surfaces in
their slices; the seal carries both. "Predicted 7, observed 11" is a legible
divergence a human reads at gate 0, and it is a fact about the corpus map's
adequacy that nothing in the pipeline could previously state.

It also costs something, and §12 records it: a surface ruling made from a map of
directory names and byte counts can be wrong in ways a reading of the digests
would not have been. `supported` is set from that thinner view.

### 4.2 Why the audit runs last

`rb-triage-audit` reads `00-objective.json` and every disposition part — not the
candidates. It writes the record's `deficiencies` and `projections`.

This is `reconcile-gaps`' position and its justification. The current skill's
refusal conditions overwhelmingly resolve to "record it rather than stay quiet,"
and its Step 5 is explicitly a check for **absence**: "Walk the capabilities the
admitted set implies and ask what each one's result shape is declared in." That
question cannot be asked by a member holding one slice, because the admitted set
is the union of all of them. The pass that writes deficiencies is therefore the
right one to audit what its predecessors admitted.

Deficiencies stay a prompt's judgment rather than the seal's arithmetic. "Does
anything in the admitted set declare what this capability returns" is semantic,
and the seal computing it would be the coverage-denominator mistake again.

## 5. The slicing algorithm

`triage-slices` is code, invoked as `rubrica triage-slices --run <run>`. It reads
the catalogue and writes `00-slices.json`: an ordered list of slices, each with an
`id`, a `label`, the `groups` it covers, its `bytes`, and its `candidates`.

It also writes one shard per slice under `00-slices/<slice_id>.json`, carrying the
run's `request` and `policy` and that slice's full candidate records. A member
reads its own shard and nothing else, so **its whole input is one `Read` under the
harness's 256KB refusal** and the tail-metadata hunt #3 measured disappears — the
head fields are in every shard by construction. The catalogue stays on disk
unchanged as the run's record; a shard is a derived projection of it, not a second
spelling.

The key, in order:

1. **Container elements group by their container.** They are the real candidates
   a container was exploded into, and their near-duplicates are each other.
2. **Corpus files group by `(root_index, directory)`.** `root_index`, not
   directory alone: two corpus roots may each hold a `src/`, and every real
   catalogue measured for this design happens to be single-root, so nothing on
   disk would have caught the merge. The slice `label` carries the root too — two
   slices came out labelled `.` on both multi-root corpora before that was fixed.
3. **Oversized groups recurse.** A subtree whose total fits the cap is one unit.
   Otherwise the recursion descends into its children, keeping each child's whole
   subtree together, and only children that still exceed the cap recurse again.
4. **The leaf fallback is kind, then bytes.** A single directory too large to
   split further — a flat corpus of 400 files — splits by kind and then by
   candidate id.
5. **Oversized containers cluster on a digest signature** before splitting: see
   §5.1.
6. **Packing is adjacent siblings only**, in the recursion's own order, never
   best-fit across the tree (§3.5).

### 5.1 Signature clustering, and the one trace it protects

For a container too large for one slice, elements are clustered on
`(heuristics_fired, names)` from the trace digest — a fact already on disk,
computed by code, deterministic — so near-duplicates land in one member's slice.
Measured on the parsec capture: **44 distinct signatures across 130 elements**,
and the large clusters are exactly the near-duplicate families a human would
name — 18 AAP2-investigation, 10+9+8+4+4 icinga-streaming variants, 9+3 babylon,
9 provisions-db.

The measurement that decides it: **`error_markers` fires on exactly one of the
130 elements.** That is the failing trace the current skill's Step 4 calls the
run's only evidence of what the target does when something goes wrong, under the
instruction that "a failing trace is almost never a near-duplicate of a
successful one." Signature clustering makes it a **singleton by construction** —
it cannot be swallowed as a duplicate by a member that never saw its peers. Code
clustering here does not dilute the skill's most emphatic judgment; it enforces
it.

This is a conditional mitigation and §12 states the condition. It works when
families exist. It does nothing when every element's signature is unique, and
nothing when all of them are identical.

### 5.2 Each slice states what it is a part of

Every slice record carries provenance: for each group it covers, how many of that
group's candidates are in this slice and how many exist in total, and which other
slice ids hold the rest.

This is the answer to the near-duplicate objection in the worst case. A member
holding 42 of 500 elements that share one signature cannot otherwise know it is
holding a twelfth of an identical family; code knows, cheaply and
deterministically. Stating it takes no judgment away — it lets the member name
the situation in a `reason` and lets a human read it at gate 0, which converts an
invisible absence into a recorded one. That is the property the reconcile design's
rejected pair filter could not have.

### 5.3 Measured across corpus shapes

Four real catalogues and ten synthetic shapes, at a 64KB cap. Every candidate
accounted for in all fourteen; the cap held in thirteen.

| corpus | roots | candidates | catalogue | slices | max slice |
|---|---|---|---|---|---|
| parsec | 1 | 351 | 595KB | 11 | 63KB |
| appworld (`src/appworld` + `experiments/code`) | 2 | 202 | 219KB | 5 | 57KB |
| tau2 (`src/tau2` + `data/simulations`) | 2 | 248 | 296KB | 5 | 56KB |
| tau2 + 200 trajectory files | 2 | 443 | 428KB | 7 | 63KB |

Slice labels came out legible on the real corpora — `apps/splitwise +spotify
+supervisor +todoist +venmo`, `domains +environment +evaluator +gym`, `voice`.

| synthetic shape | n | slices | verdict |
|---|---|---|---|
| flat, 400 files in one directory | 400 | 9 | falls through to kind-then-bytes |
| one dominant subtree, 380/400 | 400 | 10 | recursion drills in |
| deep narrow tree, depth 12 | 300 | 7 | fine |
| 40 containers x 15 elements | 600 | 20 | needs cross-container packing |
| homogeneous container, 500 identical signatures | 500 | 12 | clustering degenerates; §5.2 mitigates |
| unique-signature container, 500 distinct | 500 | 12 | clustering degenerates; packing arbitrary |
| multi-root, 3 roots x src/+tests/ | 300 | 9 | correct once keyed on `root_index` |
| 20 candidates x 40KB | 20 | 20 | correctly one per slice |
| tiny corpus, 5 candidates | 5 | 1 | fine |
| **one 200KB row + 50 normal** | 51 | 3 | **cap violated — see §6** |

Two of those became design changes rather than notes: cross-container packing
(40 slices of 21KB became 20, since whole small containers may share a slice),
and §6.

The prototype these came from is throwaway and is not part of the
implementation; the implementation owes its own tests, and §5.3's shapes are the
list they should cover.

## 6. The per-candidate row cap is a precondition, not a companion fix

The only cap violation in §5.3 is a single candidate whose row exceeds the slice
cap. No slicing scheme can fix that: a slice holding one candidate is already
minimal. **Boundedness by construction therefore depends on `survey`
guaranteeing that no candidate row exceeds the slice cap**, which is why this
lands with the design rather than after it.

Today it does not. `digest.py` caps skeleton breadth
(`_SKELETON_MAX_CHILDREN = 32`) and depth (`_SKELETON_DEPTH = 3`) but nothing
caps the total number of nodes, and `_skeleton` writes one entry per pointer into
a flat dict. Measured: `ec2-pricing-json`, a 2.7MB pricing file, yields **261
skeleton nodes / 39,162 bytes in one candidate row** — 6.8% of the parsec
candidates array in a single entry.

Two changes, and both belong to `survey`/`digest` rather than to any new stage:

1. **A total-size clamp on the digest**, recorded in the digest itself the way
   `keys_truncated` already records the breadth cap — a truncation a prompt can
   see is a fact about the digest, and one it cannot see is a lie about the
   candidate. The existing `keys_truncated` precedent is the model, and the
   current skill already teaches how to read it.
2. **A `survey`-time check that no candidate row exceeds the slice cap**, exiting
   2 with both numbers named, in the same shape as the existing candidate and
   byte guards. It is a misconfigured run rather than a stage defect.

Note what this does *not* license. Lowering `digest_body_chars` to make catalogues
smaller is a narrowing of the single point of failure `limitations.md` already
names, and it is not proposed here. The clamp exists to make a bound enforceable,
not to make digests thinner across the board.

## 7. Artifacts, kinds and schemas

New kinds, one per stage, because layer 1 is what stops a stage passing
trivially: `slices`, `objective`, `dispositions-part`, `audit`.
`validate.STAGE_ARTIFACTS` gains one entry per stage.

New `paths.RunPaths` members, following the existing naming:

```
slices              -> 00-slices.json
slices_dir          -> 00-slices/
slice_shard(id)     -> 00-slices/<id>.json
objective           -> 00-objective.json
dispositions_dir    -> 00-dispositions/
disposition_part(id)-> 00-dispositions/<id>.json
audit               -> 00-audit.json
adoptions           -> 00-adoptions.json      (see 8.1)
```

`slice_shard` and `disposition_part` go through `safe_segment`, as
`contradiction_part` does, and a slice `id` must be a usable path segment —
which layer 1 refuses outright, so it is not the slicer's to check twice. Slice
ids are code-minted, short and stable (`s01`, `s02`, …), with the prose in
`label`; §5's packing concatenated group names into unreadable strings when the
label was the identity.

**Element definitions are not duplicated, but they are not yet shareable
either.** `triage-0.1.json`'s `$defs` carries only `id`, `kind` and
`decline_reason`; a disposition, a surface, a deficiency and a projection are
defined **inline** under `properties`, so nothing can `$ref` them as they stand.
Promoting those four to `$defs` is therefore a required first step — a
refactor with no semantic change, and one a byte-comparison test on a validated
document can hold to that claim. `$ref`-ing an inline subschema by JSON pointer
(`#/properties/dispositions/items`) is valid and is rejected here: it couples
every part schema to the sealed schema's *layout* rather than to a named
definition, and a later reshuffle of `properties` would break four files
silently.

With that done the part schemas `$ref` those definitions rather than restating
them, which needs the `referencing` registry in `validate._validator_for` — the same
change the staged-reconcile branch already makes for its part schemas, keyed on
the same `(kind, schema_root)` cache key so `RUBRICA_SCHEMA_DIR` still takes
effect. If that branch lands first this is free; if not, it is a shared
prerequisite rather than a second implementation.

`validate.py` is on the list of modules whose unreadable-input paths must be
tested — a bad `RUBRICA_SCHEMA_DIR`, `chmod 000`, `chmod 0444` — because a
misconfigured run must exit 2 while a stage defect must exit 1.

## 8. `triage-seal`

Code, invoked as `rubrica triage-seal --run <run>`, added to `cli.SUBCOMMANDS`,
to `skills.CODE_ONLY_STAGES` beside `intake`, `smoke`, `survey` and
`triage-slices`, and documented in `docs/reference/cli.md`.

It assembles `00-triage.json` from `00-objective.json`, every disposition part,
`00-audit.json` and `00-adoptions.json`, writing through `write_json` so the
canonical byte form holds and `diff-runs` does not report formatting as variance.

It assembles; it does not check. Cross-artifact checking is layer 2. Following
`reconcile.py`'s pattern it **writes nothing at all** when it reports anything —
a half-assembled record would clear layer 1 for the blocks it did manage to fill,
and gate 0 would read it as complete, which is the failure the current skill's §5
opens by naming. The narrow class it refuses on:

1. a part absent, unparseable, or not an object carrying its declared payload
   keys;
2. a candidate with no disposition, or with more than one — invariant 1, now
   across parts;
3. a disposition naming a candidate that is not in the part's own slice;
4. **no `admit` anywhere across all parts** — see §10.2;
5. a `digest_insufficient` decline with no deficiency, or a `needs_projection`
   decline with no projection, where the two now sit in different artifacts.

Items 2, 3 and 5 overlap layer 2 deliberately, for the reason `reconcile.py`
records: `check-refs` owns the after-the-fact report over any run, while the seal
refuses *before the write*, because assembly is perfectly possible in each case
and the resulting record would look coherent to a human and to every checker
that recomputes from it.

**`priority` becomes lexicographic**, and this is a gain rather than a
concession. A member ranks within its own slice; `00-objective.json` ranks the
surfaces; the seal composes the two into the global order the schema already
carries. A global 1..351 rank minted in one context was never calibrated against
anything a reader could check, and ranks minted independently in eleven slices
would not be comparable at all. Rank-within-surface, ordered by surface, is both.

### 8.1 `adopt-projection` stops editing a sealed artifact

`adopt_projection` today appends a candidate to `00-catalogue.json` and an
`admit` disposition with `authority: "human"` to `00-triage.json`, and sets
`closed_by` and `satisfied_by`. Under a seal that is two hazards: a re-seal
would erase the human's admission, and a new catalogue candidate makes the slice
plan stale.

So adoption appends to its own part, `00-adoptions.json`, which the seal folds
in. Three consequences, all improvements:

- Re-sealing is idempotent and cannot destroy a gate-0 admission.
- `authority: "human"` becomes a property of *which artifact* a disposition came
  from as well as a field on it, so the distinction the current skill insists on
  is structural rather than only stated.
- Totality is defined over the union: every catalogue candidate is covered by a
  slice member's part **or** by an adoption. `triage-slices` stays re-runnable
  and idempotent, and an adopted candidate needs no member to rule on it because
  a human already did.

`adopt-projection` still writes the catalogue candidate, since the catalogue is
the enumeration of the population and an adopted artifact is part of it.

## 9. New layer-2 checks

Added to `refs.py`, reached by `check_all`:

- `check_slices` — every catalogue candidate is in exactly one slice; every slice
  candidate resolves to a real candidate id; slice ids are unique; every slice
  has a shard on disk; each slice's recorded `bytes` matches its shard.
- `check_disposition_parts` — every slice has a part; every disposition names a
  candidate in that slice; no candidate is ruled twice across parts; the union of
  parts and adoptions covers the catalogue. Carries the `check_verdicts` caveat
  (§4).
- `check_objective` — every surface's `evidence` resolves to real candidate ids;
  `weight` is arithmetic a reader recomputes, checked against the catalogue.
- `check_audit` — every `digest_insufficient` decline in any part is referenced
  by a deficiency; every `needs_projection` decline by a projection; every
  `closes` names a real deficiency.

The existing triage checks keep working against the sealed record and are not
revised; what changes is that invariant 1 is now checkable *before* the record
exists, over the parts.

## 10. The skills

Each new prompt stage gets `src/rubrica/skills/rb-<stage>/SKILL.md` with a
`## Contract` block and the five mandatory sections in order. `check-skills`
holds each to `paths.RunPaths` attribute names, `validate.STAGE_ARTIFACTS` and
`cli.SUBCOMMANDS`, and enforces `skill.name == f"rb-{stage}"` — which is why
these are stages rather than three skills sharing one stage name.

`dispatch-stage.sh` gains a `SLICE_LINE` case for `triage-rule`
(`Your slice_id: <id>`), beside the existing `extract` and
`instantiate|challenge` cases. A member is handed the run directory, the stage
name, its skill path and its own slice id — never a sibling's.

The existing `rb-triage/SKILL.md` is the source material, not something to
paraphrase. Its header — the measured 2026-08-13 failure where six scenarios
died because the reason for an exclusion existed only in a conversation — belongs
in `rb-triage-rule`, which is the pass that declines things. Its §1 cost and
comparability arguments belong in every pass. Its Step 4 near-duplicate rule and
its "a failing trace is almost never a near-duplicate" measurement belong in
`rb-triage-rule` beside §5.2's provenance, which is what makes them actionable
from inside one slice.

**`src/rubrica/skills/rb-triage/` is deleted outright**, and this differs from
the reconcile family on purpose. That directory survived its `SKILL.md` because
it holds `rb-reconcile/exercise.md` — behavioural evidence, and this project's
rule is that evidence lives beside the skill. `rb-triage` carries no
`exercise.md`; `limitations.md` records that, and records that the evidence it
would hold is not in the repository. There is nothing to preserve, so a
`SUPERSEDED.md` would assert a stage's history without holding any of it.

Every new skill owes an `exercise.md` recording what **one** real dispatch
measurably did, stating what happened rather than what was reasoned. Those
cannot be written until the passes are dispatched. One per pass and no merged
record: per-pass observability is the entire justification for making these
separate stages.

### 10.1 The comparability argument, and how §6 answers it

The current §1 says the digests are the same width for every candidate, so
reasons are comparable — "declined, no tool schema in the digest" means the same
thing said about candidate 3 and candidate 300 — and warns that once some
candidates have been read in full and others only as digests, the record no
longer says what it appears to say.

Slicing does not create two reading depths: every candidate is still judged from
its digest, and no pass opens a candidate file. What could create them is a
digest whose width varies by *how large the underlying file happened to be*,
which is what the uncapped skeleton does today — a 39KB row beside a 600-byte
one. §6's clamp, recorded in the digest where a prompt can see it, makes the
widths comparable in fact rather than by assumption. The argument survives, and
this design tightens it.

### 10.2 The refusal conditions redistribute, and one inverts

This is the most consequential prose change, and it must not be done by
paraphrase.

- **"Refuse if you would decline every candidate"** inverts for a member. A
  `parsec/tests` slice may legitimately be all declines, and a member that
  refused would strand the run. The member **writes the part**; the condition
  becomes a **seal** refusal over the union (§8, item 4), where "zero admits
  anywhere" still means the corpus, the objective or the scope is wrong.
- **"Refuse if `request.objective` is absent, or contradicts `scope_note`"**
  belongs to `rb-triage-objective`, which is the pass holding the objective, and
  it must refuse before the fan-out is dispatched rather than after.
- **"Refuse if the catalogue has no candidates at all"** becomes a
  `triage-slices` exit-2 condition: it is a `survey` defect or a broken run, and
  code detects it without a dispatch.
- **"Do not refuse when the declared objective is unsupported"** stays with
  `rb-triage-objective`, unchanged in force. Writing `supported: false` and
  letting the gate rule is the whole point.
- **"Do not refuse for a candidate you cannot judge"** stays with
  `rb-triage-rule`: decline `digest_insufficient`, name the field you needed.
  The obligation it creates now lands in a different artifact, so the member
  states the need and `rb-triage-audit` writes the deficiency — which is why
  §8's item 5 and §9's `check_audit` both exist.

Each redistribution is a rule moving to the pass that can act on it. A condition
whose trigger a pass cannot detect from what it reads is decorative, which is the
test `rationale.md` sets for section 5.

## 11. What moves outside `src/rubrica`

- `docs/concepts/pipeline.md` — the stage list and what each does.
- `docs/reference/cli.md` — `rubrica triage-slices` and `rubrica triage-seal`
  sections. `tests/unit/test_docs_accuracy.py` fails until they exist.
- `docs/reference/artifacts.md` — each new kind named as its kind.
- `docs/concepts/glossary.md` — at minimum **slice** (the bounded reading unit
  code mints, and the fan-out's slicing key), **shard** (the per-slice
  projection of the catalogue a member reads), **slice provenance** (what §5.2
  states about the group a slice is part of), **surface** (already in the triage
  schema, not yet in the glossary as the thing the objective pass predicts and
  the members observe), and **seal** — which the reconcile work also adds, so
  whichever lands first writes it and the second checks the entry covers both
  code steps. Each entry names the pass that writes it.
- `scripts/render-pipeline-diagram.py` — one `ROWS` entry per new stage;
  re-render, never hand-edit the page.
- `scripts/render-readme-diagram.py` — **folded, not enumerated**, by the same
  derived-prefix mechanism the reconcile work adds: `triage*` on one starred
  line with a `CAPTIONS` footnote. `stages` stays the complete coverage claim, so
  the partition test still reproduces `paths.STAGES` exactly, and a test asserts
  the fold is total in both directions. None of these stages leaves the first
  phase, and the phase count does not change.
- `brief.py` — gate 0's brief gains the slice table (how many slices, how many
  candidates and bytes each), the **predicted-vs-observed surface divergence**
  from §4.1, and the per-slice provenance summary from §5.2. The grouped declines
  and objective verdict it already reports stay. `brief.GATES` does not change.
- `CLAUDE.md` — the stage table, the sentence on which gate brackets what, and
  the note that `survey` and `triage` have no `0N` prefix of their own, which now
  covers four stages' artifacts rather than one.
- `tests/toy.py` — `_UPTO_STAGES` gains a checkpoint per new stage and
  `build_toy_run` writes each part. Check the module before adding a helper.
- The golden fixture's catalogue is small enough to be one slice, which is the
  right default but leaves the fan-out unexercised by the toy world. A
  multi-slice fixture is owed: either a second toy corpus or a `triage-slices`
  cap override in the builder. The latter is preferable — it exercises the real
  slicer rather than a hand-written slice plan, and `RUBRICA_*` env overrides are
  already this repository's way of probing behaviour without editing repo files.

## 12. Limitations owed

Each of these belongs in `docs/design/limitations.md` when this lands, with the
measurements rather than a gesture at them.

1. **Two near-duplicate candidates in different slices are both admitted.** The
   residue of slicing, and the one thing it costs. It is *over*-admission, which
   spends extraction budget and is visible downstream in `claim-utilisation` —
   materially gentler than the cross-subject contradiction's invisible absence,
   and the entry must say why rather than claim kinship. Mitigated by §5.1's
   clustering and §5.2's provenance, neither of which eliminates it.
2. **Signature clustering is conditional, and trace-specific.** It keys on
   `heuristics_fired` and `names`, which only a `trace` digest carries. Measured:
   44 signatures over 130 real elements (works); 500 identical signatures
   (degenerates to byte-splitting); 500 unique signatures (degenerates to
   arbitrary packing). On a corpus whose elements classify as `other` it does not
   apply at all — see #4.
3. **`supported` is ruled from a corpus map, not from digests.** §4.1's trade.
   The instrument is the predicted-vs-observed divergence at gate 0, which is
   new; the loss is that a surface ruling can be wrong in a way a reading of the
   digests would not have been.
4. **Slice coherence is a code judgment no test can rule on.** Whether
   `parsec/tests` is one surface or three is editorial. `check_slices` verifies
   the partition is total and disjoint; nothing verifies it is *meaningful*, and
   the only instrument is the slice labels a human reads at gate 0.
5. **The digest clamp is a second truncation.** §6 adds one, recorded in the
   digest. It sits under the existing "catalogue digest is the single point of
   failure for triage" entry rather than beside it, and that entry's 400-byte
   figure is corrected to the measured 1,186 at the same time.
6. **One prototype, four corpora, ten synthetic shapes — and no dispatch.**
   Everything in §5.3 is arithmetic over catalogues. Whether a member dispatched
   over a 64KB shard produces a *better* record than one dispatched over 595KB is
   unmeasured, and it is the claim the whole design rests on. The first
   `exercise.md` per pass is where that stops being an assumption.

## 13. Relationship to #4

They are in series, and this design is the prerequisite.

#4 records that OpenAI-style chat trajectories neither explode
(`EXPLODE_MIN_COMMON_KEYS = 3` against a `{role, content}` intersection of one)
nor classify as traces (`classify_payload` wants `spans` or `trace_id`), so 200
tau2 trajectory files reach triage as 200 skeleton-only rows.

Fixing that without this design in place would make things worse rather than
better: the same corpus becomes roughly 5,425 candidates and ~2.9MB, some 11x
the candidate cap and 2.8x the byte cap. A corpus that triages badly would become
one that cannot be surveyed.

It also bounds what §5.1 can promise, which is limitation 2 above: elements that
explode as `other` cluster only on skeleton shape, and on that corpus every
skeleton is identical.

## 14. Order of work

1. §6's digest clamp and `survey`-time row check. Independently useful, and
   nothing below is bounded without it.
2. `triage-slices`, `00-slices.json`, the shards, `check_slices`. Testable with
   no dispatch, against all four real catalogues.
3. Promote `triage-0.1.json`'s four inline element definitions to `$defs`
   (§7). No semantic change, and nothing else in this list can `$ref` them
   until it is done.
4. `paths`, the four kinds, the part schemas and the `referencing` registry
   (shared with the reconcile work — coordinate rather than duplicate).
5. `triage-seal` and its refusal class, plus §8.1's `00-adoptions.json` move.
6. The three skills, `dispatch-stage.sh`'s slice line, and the §10.2
   redistribution.
7. `refs.py`'s remaining checks, `brief.py`'s gate-0 additions.
8. Docs, glossary, both diagrams, `tests/toy.py`, the multi-slice fixture.
9. Dispatch each pass once against parsec; write one `exercise.md` per pass;
   correct anything §12 turns out to have guessed.
