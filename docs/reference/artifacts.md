# Artifact reference

One entry per artifact kind Rubrica's schemas define, plus the two
human-authored config files no stage produces. Each stage-produced entry
states its schema under `src/rubrica/schema/`, the stage that writes it
(`validate.STAGE_ARTIFACTS`), which stages read it, its on-disk path within a
run (`paths.py`), what it is for, and the fields worth knowing before you open
one. Entries are ordered the way a run produces them, not alphabetically.

See [`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md)
for the rule that these files are the only channel between stages, and
[`docs/concepts/pipeline.md`](../concepts/pipeline.md) for the stage order
that writes them.

## `catalogue`

- **Schema:** `src/rubrica/schema/catalogue-0.1.json`
- **Written by:** `survey` (code)
- **Read by:** `triage-slices` (code — the whole file, to partition it, and to
  project `request`, `policy`, `excluded` and `candidates[].bytes` onto the
  plan's `catalogue_facts`, which is why `rb-triage-objective` reads the plan
  and not this file); `intake` (the `--run` path, admitting whatever triage
  already ruled on)
- **Path:** `00-catalogue.json`

Every candidate a survey found in a corpus, each with a bounded digest rather
than its own bytes — `sha256`, `bytes`, `kind`, and a `digest` object, never a
copy of the source content. It also carries the survey `request` (target,
objective, corpus roots, limits) and the `policy` that governed digesting and
exclusion, so a later reader can see what the survey was told to look for
without re-deriving it. `excluded` records every path the survey chose not to
catalogue, with a `reason` (`gitignored`, `binary`, `duplicate`, and the like).

Fields worth knowing: `candidates[].origin` (`corpus`, `container_element`, or
`projection` — a candidate exploded out of a container file, or manufactured
by `adopt-projection`, still gets its own entry here); `candidates[].kind`
(the same seven-value enum `manifest.inputs[].kind` uses); `candidates[].
admissible` (a structural flag, not triage's disposition — a candidate can be
admissible and still be declined).

## `triage`

- **Schema:** `src/rubrica/schema/triage-0.1.json`
- **Written by:** `triage-seal` (code), assembling the parts the rest of the
  `triage-*` family writes
- **Read by:** `intake` (the `--run` path)
- **Path:** `00-triage.json`

One disposition per catalogued candidate — `admit` or `decline`, each with a
`reason` and an `authority` (`triage` or `human`, so an override at gate 0 is
distinguishable from triage's own ruling) — plus `objective_review` (whether
the corpus actually supports the survey's declared `breadth`/`depth`
objective), `deficiencies` (named gaps in the corpus itself), and
`projections` (proposed manufactured artifacts closing a deficiency, each with
a `method`, an `acceptance` criterion, and a `boundary` statement of what it
does not cover). Gate 0 reads this record, never the corpus again — a
candidate declined here is gone as completely as if the corpus never
contained it, because nothing downstream of `intake` re-reads the corpus.

This file is purely derived: `triage-seal` assembles it from `00-objective.json`,
`00-slices.json`, every `00-dispositions/<slice>.json` part, `00-audit.json`,
and `00-adoptions.json`, and re-running it re-derives the identical record
from the same parts. `adopt-projection` no longer writes here at all — it
appends to `00-adoptions.json` instead, because editing this record directly
would be erased the next time `triage-seal` runs.

Fields worth knowing: `dispositions[].reason_code` (`off_objective`,
`near_duplicate`, `needs_projection`, and five more — a fixed vocabulary, not
free text); `projections[].closes` (the `deficiency_id`s a projection is
supposed to resolve — `adopt-projection` checks structural acceptance against
this, never the prose criterion, which stays a human's call).

## `slices`

- **Schema:** `src/rubrica/schema/slices-0.1.json`
- **Written by:** `triage-slices` (code)
- **Read by:** `rb-triage-objective` (this file alone — `slices[]`'s labels,
  groups and counts, plus the `catalogue_facts` block; never a shard's
  candidate digests, and never `00-catalogue.json`); `rb-triage-rule`
  (one dispatch per slice, each reading only its own `00-slices/<id>.json`
  shard whole — never a sibling's)
- **Path:** `00-slices.json`, one shard per slice at `00-slices/<id>.json`

The catalogue's admissible candidates packed into byte-bounded slices, so a
single dispatch can hold one slice whole: the fix for a real 595KB/351
candidate catalogue that killed three dispatches before this module existed,
one in context compaction and one by exhausting its whole dollar budget.
`00-slices.json` is the plan — one entry per slice, its `groups`,
`candidate_ids`, and `provenance` — and is schema-validated. The shard at
`00-slices/<id>.json` is not: instead it carries the run's `request` and
`policy` verbatim alongside that slice's own full candidate records, so a
member's entire input is one `Read` under the harness's 256KB refusal, with
no chunk-reading seek for a head field the way `run_id` sitting 608KB into a
sorted-keys catalogue once forced. A slice is a reading unit, never a decision
unit — every candidate it holds still reaches a member and is still
overrulable by a human at gate 0.

Fields worth knowing: `slices[].bytes` (the slice's total digest bytes,
recomputed from the shard by a later reference check so a slice cannot
silently drift from its own header); `slices[].provenance[].other_slices`
(empty exactly when the group it names was not split across slices); and
`catalogue_facts`, which is everything `rb-triage-objective` may know
about `00-catalogue.json` without opening it — `request` and `policy`
verbatim, `excluded` as a tally plus the paths for the exclusion reasons an
operator could dispute, and `candidate_bytes` giving each candidate's own source
size. Sorted keys put it and `run_id` ahead of `slices[]`, so the head a
reader needs is in the first bytes rather than 470KB in, which is what a
chunk-reading dispatch used to pay for. `refs.check_slices` recomputes the two
derived fields from the catalogue through the same functions that wrote them.

## `objective`

- **Schema:** `src/rubrica/schema/objective-0.1.json`
- **Written by:** `triage-objective`, run as `rb-triage-objective`
- **Read by:** `triage-seal` (code), which copies `objective_review` into
  `00-triage.json`'s own field of the same name verbatim
- **Path:** `00-objective.json`

The first staged-triage prompt pass's whole output, written before any
per-slice dispositions member has read a candidate digest: `objective_review`
(the surfaces the corpus map shows, whether the declared `breadth`/`depth`
objective is `supported`, and an optional `recommended_objective` the pass may
not act on itself) and `predicted_surface_count`, a prediction against what
the digest-reading members will later observe. It is built from
`00-slices.json` alone — never a candidate `digest`, and never
`00-catalogue.json` — so this pass's dispatch is sized to the corpus map, not
to the corpus.

Fields worth knowing: `objective_review.surfaces[].weight.bytes` (the sum of
each evidence candidate's entry in the plan's `catalogue_facts.candidate_bytes`
— the source file's size — never `slices[].bytes` or any other serialized
row's size, which saturates once the digest skeleton hits its 128-node cap);
`predicted_surface_count` (a prediction, not a report — a later member
observing a different surface count is a fact about this map's adequacy, not
proof either reading erred).

## `dispositions-part`

- **Schema:** `src/rubrica/schema/dispositions-part-0.1.json`
- **Written by:** `triage-rule`, run as `rb-triage-rule` — fan-out, one file
  per slice
- **Read by:** `triage-seal` (code, assembles every part into
  `00-triage.json`); `rb-triage-audit`, dispatched once every part has
  landed, reading each part's `deficiency_notes` and `needs_projection`
  declines' `reason` prose to consolidate into `00-audit.json`
- **Path:** `00-dispositions/<slice_id>.json`, one file per slice

The staged-triage family's ruling: one dispatch per slice, admitting or
declining every candidate the slice's own `00-slices/<slice_id>.json` shard
holds — never a sibling's. `dispositions` carries one entry per candidate in
that slice, exactly once, including inadmissible container candidates,
each with `authority: "triage"`; an `admit` carries a `reason` and a
`priority` ranked within the slice only, never a global rank the member
cannot see. A slice that would decline every candidate in it still writes
its part — only `triage-seal`, once every slice has reported, is positioned
to say the corpus, objective, or scope itself is wrong. `observed_surfaces`
names surfaces the member noticed that `00-objective.json`'s prediction did
not already name; `deficiency_notes` are the raw material `rb-triage-audit`
later mints real `deficiency_id`s from — this pass writes neither a
`deficiency_id` nor a projection object itself.

Fields worth knowing: `dispositions[].reason_code` (optional on a decline,
one of eight values — `off_objective`, `out_of_scope`, `near_duplicate`,
`superseded`, `implementation_detail`, `no_evidence_value`,
`digest_insufficient`, `needs_projection`); a `digest_insufficient` decline's
`candidate_id` must also appear in this same part's own `deficiency_notes`,
or `check-refs` rejects the record — the pairing is checked against the
part that wrote it, not the consolidated audit.

## `audit`

- **Schema:** `src/rubrica/schema/audit-0.1.json`
- **Written by:** `triage-audit`, run as `rb-triage-audit` — dispatched once
  every `triage-rule` member has landed
- **Read by:** `triage-seal` (code), which folds both blocks into
  `00-triage.json`'s own `deficiencies`/`projections`
- **Path:** `00-audit.json`

The last of the staged-triage family's prompt passes: the one reading that
reaches every part at once, rather than one slice of the admitted set at a
time. `deficiencies[]` and `projections[]` are both required even when
empty — an empty `deficiencies` is itself a claim that the admitted set
covers everything the objective needs, not the absence of one. Both blocks'
`$defs` are `$ref`s into `triage-0.1.json` rather than restated here, the
same reason `slices-0.1.json` and `dispositions-part-0.1.json` `$ref` that
file's other `$defs`: a duplicated definition that fell behind would let this
part accept a shape the seal then rejects.

Two obligations feed `deficiencies[]` and `projections[]` respectively, and
`check-refs` rejects the record if either is missing: every
`digest_insufficient` decline in any `00-dispositions/<slice_id>.json` part
must be referenced by exactly one `deficiencies[]` entry, and every
`needs_projection` decline by exactly one `projections[]` entry's `sources[]`.
Turning a member's raw `deficiency_notes` into a minted `deficiency_id`, and a
member's `reason` on a `needs_projection` decline into a full seven-field
projection brief, is this pass's job and nobody else's — no single
`triage-rule` member could deduplicate across slices, because none of them
ever sees a sibling's part.

Fields worth knowing: `projections[].method.confidence` (`high`, `medium`, or
`unknown` — `unknown` is an honest value here, since this pass is one further
remove from the candidate than the member who declined it in the first
place); `projections[].acceptance` (`classifies_as`, `pointers_required`,
`must_contain`, `must_not_contain` are checked mechanically by `rubrica
adopt-projection`, but are necessary and never sufficient — `prose` is where
*correct* actually gets defined).

## `manifest`

- **Schema:** `src/rubrica/schema/manifest-0.1.json`
- **Written by:** `intake` (code); amended by `rb-orchestrate`'s
  `record-stage` and `set-limit` calls
- **Read by:** `rb-extract`, every `rb-reconcile-*` pass, `reconcile-seal`
  (code), `rb-propose`, `rb-score`, `rb-orchestrate`
- **Path:** `manifest.json`

The run's identity: `run_id`, `target` (name and interface), the registered
`inputs` (each with its `artifact_id`, `source_path`, `stored_as` name,
`sha256`, `kind`, and `bytes`), the current `limits` (`max_rounds`,
`max_scenarios`, and the optional `max_scenario_part_bytes` — absent means
`rounds.DEFAULT_SCENARIO_PART_BYTES`), and `stages` — one entry per stage that
has actually run,
recording the `model`, `effort`, and `skill_sha256` `record-stage` computed
from the skill file used. `stages` gains one entry per prompt stage
between `extract` and `emit`, plus `triage` — which is recorded **after** gate
0 rather than when it ran, because a run minted by `survey` has no manifest to
merge into until `intake --run` writes one
([`docs/guides/invoking-rubrica.md`](../guides/invoking-rubrica.md)
§8 has the command). `intake`, `smoke`, `survey`, `triage-slices`,
`triage-seal`, `synthesise-interfaces`, `reconcile-seal`, `propose-batches`,
`propose-seal` and `score-seal` — `skills.CODE_ONLY_STAGES`, in full — are code:
they have no skill file for
`record-stage` to hash, so they never appear there, and their absence is not a
finding. The schema's `propertyNames` enum permits exactly `paths.STAGES` —
`tests/unit/test_manifest_stages.py` holds the two equal, in order — so it
constrains the vocabulary, not which of them a real run records.

Fields worth knowing: `inputs[].provenance` (present only for an input that
came from inside a container file or from a projection — `container_sha256`
+ `json_pointer`, or `projection_id` + `source_candidate_ids`); a recorded
`skill_sha256` that no longer matches the file on disk on re-inspection means
the skill was edited after that stage ran — the hook working, not a defect.

## `claims`

- **Schema:** `src/rubrica/schema/claims-0.1.json`
- **Written by:** `extract`, run as `rb-extract` (fan-out, one file per input)
- **Read by:** every `rb-reconcile-*` pass — all of them read all of
  `01-claims/`, because the family is split on output, not on claims;
  `check-refs`
- **Path:** `01-claims/<artifact_id>.json`

One atomic, evidence-backed statement per claim, extracted from exactly one
input artifact — `rb-extract` is dispatched once per registered input and
never sees a sibling's file, so every claims document names only the
`artifact_id` it was extracted from. Nothing later fabricates a claim without
tracing back to one.

Fields worth knowing: `claims[].kind` (`capability`, `entity`, `invariant`,
`actor`, `goal`, `outcome_class`, or `tool`); `claims[].derivation` (`stated`,
`inferred`, or `reverse_engineered` — a claim's honesty grade, carried forward
into the world model); `claims[].evidence[].locator` (required on every claim,
so a claim with no way to find where it came from cannot exist); and
`claims[].payload` (optional, and free-form by design — on a `tool` claim it
carries that tool's input schema verbatim, with `evidence[0].locator` the JSON
pointer it was copied from. "Verbatim" is checked rather than trusted: for every
payload a service names as its `schema_claim`, `check-refs` re-reads the registered
input at that pointer and compares the decoded values, which is the one thing that
makes a prompt's transcription of a schema falsifiable. Decoded, not bytes — a
reformatted schema is not a fidelity defect. A locator that is a heading anchor
rather than a pointer, or an input that is not JSON, is not comparable and is not
reported).

## The reconcile partials

The entries below are one logical step — building the world model —
engineered as bounded passes, each writing its own slice into the `01-` band
and none of them reading `01-world-model.json`. `reconcile-seal` assembles them
into that file, which is unchanged: nothing downstream of the seal knows the
partials exist. It reads every one of them but one. `01-subjects.json` is the
exception — the world model has no subjects field, so the cover is an input to the
contradiction fan-out, to `reconcile-gaps`, and to `check-refs`, not to the seal.
`01-services.json` it reads on a different footing from the rest: the seal folds
it into the world model's `services` field **when the file exists**, and omits
that key entirely when it does not, so it is the one input whose absence is not a
finding. Each pass is a stage in `paths.STAGES`, so
`rubrica validate --stage reconcile-<pass>` gates exactly one of these kinds.

One entry below is **not** a partial and not a pass: `interface`. It is derived
from `01-services.json` by `synthesise-interfaces`, which merges no claims into
anything, and it is gated as `rubrica validate --stage synthesise-interfaces`. It
is documented here because it is written in the same band and read at the same
gate, not because it shares the shape of the entries around it.

Every one of these schemas resolves its element definitions against
`world-model-0.1.json#/$defs/...` through `validate._schema_registry`, rather
than restating them — a duplicated `$defs/entity` that fell behind would make a
partial accept an element the sealed world model then rejects.
`capabilities-part` is the single exception and says so in its own entry.

The passes that own a claim kind — `capabilities-part`, `outcomes-part`,
`entities-part`, `goals-part`, `services-part` — each carry an **`inputs_seen`
accounting** on top of their elements: one row per input `manifest.json`
registers, each `{artifact_id, own_kind_total, cited, dropped}` plus a `note`
whenever `dropped` is not zero. The row shape lives once, in
`src/rubrica/schema/inputs-seen-0.1.json`, which each of them `$ref`s and which
is **not an artifact kind** — no stage writes a document of that shape, so it is
the one schema in the package with no entry in `validate.ARTIFACT_SCHEMAS` and
nothing `rubrica validate --stage X` ever looks for on its own.

`own_kind_total` is how many claims of *that pass's* kinds the named input's
claims file holds. `check-refs` **recomputes** it from `01-claims/` and
recomputes `cited` from the `claims` arrays in the partial itself, so neither is
taken on the pass's word: a wrong number is a finding. That is recomputability,
not proof of a read — a row is legitimately all-zero wherever the input holds no
claim of the pass's kinds, and `docs/design/limitations.md` records the other two
routes to a right number without a read, together with what the accounting does
deliver instead. The accounting is **total over `manifest.inputs`** — a registered input with no row is a finding, because a
pass that never opened a claims file is otherwise indistinguishable from one that
opened it and cited nothing. Issue #6 is what that measures: read coverage of
`01-claims/` varied from three files of twenty-three to all twenty-three across
byte-identical dispatches, and both check layers accepted the skimmed run,
because a skimmed read still produces a well-formed partial.

The drops themselves are **nobody's finding**. Every row with a non-zero
`dropped` carries the `note` layer 1 requires of it, which is what makes the drop
a decision on the record rather than an oversight — and `check-refs` deliberately
does not report even the sharpest case, a positive `own_kind_total` cited zero
times. Ruling on that is the human's job at gate 1, where `gate-brief --gate 1`
prints each pass's own-kind rate and every row that dropped something beside its
note. Making it an exit code would put a coverage judgment behind a repair round
that cannot repair anything.

One shape of drop a reader at that gate should expect is a **cross-pass** one: a
claim of one pass's kind that a different pass legitimately modelled, which
`rb-reconcile-outcomes` produces by design — its method harvests outcome-class
information from claims of every `kind`, so an `invariant` claim folded into an
outcome class is `dropped` in `entities-part`'s row while the world model rests
on it. The note is the only thing that distinguishes that from a claim nobody
used.

The other three partials carry no accounting, for two different reasons.
`subjects` and `contradictions-part` need none: `check-refs` already holds the
subject cover to totality over every claim in the run, so the cover is the
accounting. `gaps-part` cannot be given one — its pass owns none of the seven
claim kinds, and a gap asserts what no input *contains*, so no output shape can
force its read coverage. See
[`docs/design/limitations.md`](../design/limitations.md).

## `subjects`

- **Schema:** `src/rubrica/schema/subjects-0.1.json`
- **Written by:** `reconcile-subjects`, run as `rb-reconcile-subjects`
- **Read by:** `rb-reconcile-contradict` (which is fanned out over it),
  `rb-reconcile-gaps`; `check-refs`
- **Path:** `01-subjects.json`

A cover of every claim in `01-claims/`, grouping them into subjects so the
contradiction sweep can be fanned out without any member losing sight of a
claim it needs to compare against. A **cover, not a partition**: a claim may
appear under several subjects, and the pass is instructed to over-assign when
the subject is unclear, because a claim in no subject is never compared against
anything. That is what a heuristic pair filter could not give — `check-refs`
holds the cover to totality, so every claim id in the run appears here.

Fields worth knowing: `subjects[].claims` (a `claim_refs` array, so it can
never be empty); `subjects[].note` (optional, for why a claim was assigned
where a reader would not expect it).

## `contradictions-part`

- **Schema:** `src/rubrica/schema/contradictions-part-0.1.json`
- **Written by:** `reconcile-contradict`, run as `rb-reconcile-contradict`
  (fan-out, one file per subject)
- **Read by:** `rb-reconcile-capabilities`, `rb-reconcile-outcomes`,
  `rb-reconcile-entities`, `rb-reconcile-goals`, `rb-reconcile-gaps`,
  `rb-reconcile-services`, `reconcile-seal` (code); `check-refs`
- **Path:** `01-contradictions/<subject_id>.json`

What one fan-out member found within its own subject, reading every claim in
that subject **across all input files** — which is what preserves
cross-artifact contradiction detection through the fan-out. Each part names the
`subject_id` it was dispatched with, and a member never sees a sibling's file.

An **empty `contradictions` array is a real record**, not a missing one: it
says this member swept this subject and found no disagreement. That is why the
array carries no `minItems`, and why the layer-2 check requires a file per
subject rather than a non-empty one. The contradictions recorded here are a
constraint on every later pass — a disagreement recorded `unresolved` may not
be quietly settled by how a later pass chooses to model the thing.

Fields worth knowing: `contradictions[]` is
`world-model-0.1.json#/$defs/contradiction` itself, so `resolution` is the same
four-value enum (`unresolved`, `preferred_a`, `preferred_b`, `both_possible`)
the sealed world model carries.

## `capabilities-part`

- **Schema:** `src/rubrica/schema/capabilities-part-0.1.json`
- **Written by:** `reconcile-capabilities`, run as `rb-reconcile-capabilities`
- **Read by:** `rb-reconcile-outcomes`, `rb-reconcile-entities`,
  `rb-reconcile-goals`, `rb-reconcile-gaps`, `reconcile-seal` (code)
- **Path:** `01-capabilities.json`

Each capability's identity, `operation`, `params` and `binding` — and **no
`outcome_classes`**, which are the next pass's output. Writing the capability
list to a file is the point of splitting the two: `rb-reconcile-outcomes` then
quantifies over a list it can read, rather than over a memory of having just
written one.

The one place in this family where a definition is restated rather than
`$ref`'d. `$defs/capability_core` is `world-model-0.1.json#/$defs/capability`
minus `outcome_classes`, and JSON Schema cannot express that subtraction while
`additionalProperties: false` holds — a `$ref` plus an override does not
compose under it. Four of `capability_core`'s properties (`id`, `binding`,
`params`, `claims`) still `$ref` the world model and cannot drift; `operation`
and `confidence` are genuinely copied.
`tests/unit/test_schema_part_sharing.py` is the compensating control, and it
compares the two definitions **element for element** — every property shape
with refs normalised, plus the `required` list — not just their names, because a
fourth value added to the world model's `confidence` enum would pass a name
check while making `capabilities-part` reject a document `reconcile-seal`
accepts. Measured red in both directions, so the duplication cannot drift
silently.

Fields worth knowing: `capabilities[].binding` (optional in the schema and
required by `emit`, which reports a finding for an accepted scenario whose
capability has none — so a capability without one is a defect deferred, not
avoided); `inputs_seen[].own_kind_total` (how many `capability`-kind claims the
named input holds — the one kind this pass is accountable for).

## `outcomes-part`

- **Schema:** `src/rubrica/schema/outcomes-part-0.1.json`
- **Written by:** `reconcile-outcomes`, run as `rb-reconcile-outcomes`
- **Read by:** `rb-reconcile-gaps`, `reconcile-seal` (code); `check-refs`
- **Path:** `01-outcomes.json`

A **join table, not a collection**: `outcome_classes` is nested inside the
capability object in the world model, so this pass cannot write a sibling
array. Each entry names a `capability_id` from `01-capabilities.json` and the
outcome classes for it, and `reconcile-seal` folds each entry into its
capability.

Fields worth knowing: `outcomes[].outcome_classes[].kind` (the same five-value
enum the world model uses — `success`, `empty`, `not_found`, `error`,
`underspecified`; `underspecified` is the one that records "nothing addresses
this", which is not the same as silence, and dropping it costs the coverage
denominator a column for every capability the target can be driven on);
`outcomes[].outcome_classes[].claims` (required and non-empty, as on every other
element — and for an `underspecified` class it is the claims that establish the
*operation* the class belongs to, since evidence for an outcome nothing states
does not exist);
`inputs_seen[].own_kind_total` (how many `outcome_class`-kind claims the named
input holds — this pass's own kind).

## `entities-part`

- **Schema:** `src/rubrica/schema/entities-part-0.1.json`
- **Written by:** `reconcile-entities`, run as `rb-reconcile-entities`
- **Read by:** `rb-reconcile-goals`, `rb-reconcile-gaps`, `reconcile-seal`
  (code)
- **Path:** `01-entities.json`

The entities, with their fields, relations and invariants, quantified over the
capabilities already declared in `01-capabilities.json`: if a claim spells out
the shape a capability returns, that shape becomes an entity here. Elements are
`world-model-0.1.json#/$defs/entity`, so the sealed world model accepts exactly
what this file carries.

Fields worth knowing: `entities[].invariants[].machine` versus `.prose` — the
same distinction the `world-model` entry describes, and the same consequence:
`prose` leaves the reachability gate nothing to evaluate, while a `machine`
invariant promoted from an inference fails every seed that is actually correct;
`entities[].invariants[].claims` (required and non-empty, so an invariant's
provenance sits on the invariant rather than on its parent entity);
`inputs_seen[].own_kind_total` (how many claims of this pass's two kinds —
`entity` and `invariant` — the named input holds).

## `goals-part`

- **Schema:** `src/rubrica/schema/goals-part-0.1.json`
- **Written by:** `reconcile-goals`, run as `rb-reconcile-goals`
- **Read by:** `rb-reconcile-gaps`, `reconcile-seal` (code)
- **Path:** `01-goals.json`

Actors and the goals they hold. Its own pass rather than folded into entities
because goals are half the frozen denominator: `reconcile-seal` counts them,
`rb-propose` designs against exactly this list, and a later stage may only
*request* an amendment — which costs an explicit orchestrator decision and a
`denominator_version` bump. Actors travel with goals in the same file because
every goal needs a real `actor_id` to resolve.

Fields worth knowing: `goals[].expected_hop_depths` (as in the world model, the
multi-hop depths a goal is expected to be tested at);
`inputs_seen[].own_kind_total` (how many claims of this pass's two kinds —
`actor` and `goal` — the named input holds); both element arrays lack `minItems`,
because a corpus that establishes no actor is a fact for `rb-reconcile-gaps` to
record rather than one for the schema to forbid.

## `gaps-part`

- **Schema:** `src/rubrica/schema/gaps-part-0.1.json`
- **Written by:** `reconcile-gaps`, run as `rb-reconcile-gaps`
- **Read by:** `reconcile-seal` (code)
- **Path:** `01-gaps.json`

Last of the prompt passes on purpose. It reads every prior partial as well as
every claim, because the refusal conditions of every pass before it resolve to
"record a gap instead" — so the pass that writes gaps is the one positioned to
audit what its predecessors declared: a capability with no supporting claim, an
invariant promoted to `machine` on an inference, an outcome class nothing
states.

An empty `gaps` array is legal and is a strong claim: a world model with no
gaps, built from claims that leave things unstated, has erased the silence
rather than recorded it.

Fields worth knowing: `gaps[].blocks` (the later stages a gap makes
unsafe — a gap blocking `propose` is what makes the orchestrator halt, so it is
named honestly rather than narrowly, and never left empty to avoid a halt);
`gaps[].claims` (required and non-empty, and **not** evidence for the unknown,
which by definition nothing states — the claims that make the absence *matter*,
so a gap's provenance is resolvable rather than sitting in prose).

## `services-part`

- **Schema:** `src/rubrica/schema/services-part-0.1.json`
- **Written by:** `reconcile-services`, run as `rb-reconcile-services`
- **Read by:** `check-refs`; the interface synthesis below it; `reconcile-seal`,
  which folds it into the world model's optional `services` field; and
  `gate-brief`, which renders one block per service at gate 1 — from this file
  rather than from the assembled model, because a reader whose next action is to
  correct a grouping edits the part
- **Path:** `01-services.json`

The tools the target declares, grouped into the services one simulator each
would stand in for. Its own pass because the grouping is a judgment with
evidence rather than a string match, and because it decides how many simulators
exist: tools split across two services get disjoint databases, so an entity
created through one is invisible to the other. Splitting when unsure is the
instructed direction — two services that should be one are two simulators a
human can merge at gate 1, while one service that should be two is a database
the tools silently disagree about, and nothing downstream detects it.

**The one optional input to `reconcile-seal`,** which is what distinguishes it
from every partial above. The seal folds its `services` array into the world model
verbatim when this file exists — the grouping is a judgment a human ratifies at
gate 1, and a seal that rebuilt the records would be ratifying the seal's — and
omits the `services` key entirely when it does not, rather than writing `[]`: an
empty array asserts that a pass looked and found no tools, which is a different
claim about the target from "no pass ran". Its absence is therefore not a finding,
unlike every other partial's. Being optional does not make it unchecked: a `null`
or list-shaped document here is a finding naming this file.

Fields worth knowing: `services[].grouping_evidence` (what makes two tools one
backend — a shared base URL, client construction, credential or MCP server entry
— with `sole_service_in_run` the honest value for a group of one, so a run with a
single tool has no reason to invent shared evidence); `services[].signals` (one
per piece of evidence about whether the service reaches outside the process, each
with a `locator`, and **never a containment verdict** — there is no `contained`
field anywhere, because a tool that looks self-contained but holds a hidden call
produces a suite that passes in the lab and fails in production, so uncertainty
must not read as contained; `no_outward_evidence_found` is absence of evidence
and its locator names what was read, not where something was seen);
`services[].tools[].schema_claim` (the one claim whose `payload` becomes the
operation's request body, named by the pass because synthesis is deterministic
and a code rule for picking a winner would bury the judgment, with
`schema_disagreement` recording what the losing claim said);
`inputs_seen[].own_kind_total` (how many `tool`-kind claims the named input holds
— the one kind this pass is accountable for); and `services[].id`, which must be
unique across the array although the schema cannot say so — the document path is
derived from it, so two services sharing an id collapse onto one file and the
groupings after the first are lost. `check-refs` reports that here and nowhere
else: it holds the shared document to neither grouping, because that document is
byte-for-byte what synthesis wrote from the last of them and a finding against it
would send a repair at a file with no defect in it. One line, in the file the
repair belongs in.

## `interface`

- **Schema:** `src/rubrica/schema/interface-0.1.json`
- **Written by:** `synthesise-interfaces` (code), via `rubrica
  synthesise-interfaces`, from `01-services.json` and the claim payload each
  tool's `schema_claim` names
- **Read by:** `check-refs`, which holds each document to the service it was
  derived from: one document per service and nothing else in the directory, and
  each document's `operationId` set equal to its service's tool names — with one
  exception, a document two services with the same id collapsed onto, which is held
  to neither grouping because the finding belongs to `01-services.json`. Also
  `gate-brief`, whose gate-1 services block names each document's path, or states
  that none was written: it asks `is_file` per service rather than trusting the
  directory, since synthesis creates `01-interfaces/` even for an empty service
  list
- **Path:** `01-interfaces/<service_id>.json`, one per service — derivable from
  the service id, so there is no path field anywhere to drift out of agreement
  with the directory

One service's OpenAPI document, synthesised backwards from the tool contract the
agent under test already has: `operationId` is the tool's own name and the request
body is that tool's input schema, copied from the claim payload rather than derived
from it. Method `post` and path `/<tool name>` are fixed carriers, because only
`operationId` is contractually significant — it is what a simulator turns back into
a tool name — so the other two are chosen to be stable rather than pretty.

Not folded into the world model, and that is a ruling rather than a convenience: an
inlined document would bloat an artifact whose byte-identity is load-bearing, and
the harness this feeds consumes a file.

The schema pins the carrier convention and the provenance, and is **not** an
OpenAPI validator — whether a document is acceptable is the harness's test, not
ours. `responses` is deliberately not required: inferring one needs observed tool
results, which is a later step, and a request-only document is what a tool-style
spec that declares no `components.schemas` looks like on purpose.

Fields worth knowing: `paths` (one entry per tool, keyed `/<tool name>`, whose
`operationId` set is the service's tool names byte for byte — contract preservation
made mechanical, and `check-refs` holds the document to it, naming the difference in
both directions so a rename is not read as one defect when it is two. Checked
rather than merely written, because a document hand-corrected at gate 1 reaches
`check-refs` without passing through synthesis again);
`x-rubrica.service_id` and `x-rubrica.tools` (the provenance, carried inside the
document because the document is what a human reads at gate 1 and what a later step
hands the harness, under an `x-` key so it stays a legal OpenAPI extension).

## `world-model`

- **Schema:** `src/rubrica/schema/world-model-0.1.json`
- **Written by:** `reconcile-seal` (code), via `rubrica reconcile-seal`, from
  the partials above — every one of them but `01-subjects.json`, which has no
  counterpart field here. `01-services.json` is the one optional input: its
  `services` array is folded in verbatim when that file exists, and the `services`
  key is omitted entirely when it does not
- **Read by:** `rb-propose`, `rb-score`, `rb-instantiate`, `emit` (code),
  `rb-orchestrate`; `check-refs`
- **Path:** `01-world-model.json`

The single reconciled picture of the target system, assembled from the
partials the `reconcile-*` passes wrote out of every claim `rb-extract`
produced: `capabilities`, `entities`, `actors`, `goals`, recorded
`contradictions` (disagreements carried forward rather than silently
resolved), recorded `gaps` (things no input says anything about, each naming
which later stages it `blocks`), an optional `services` (the tool groupings a
simulator would stand in for, present only when `01-services.json` was written),
and a `denominator` frozen at a `version` for the rest of the run. Every element
carries a `claims` array of the claim ids
that support it — **including the nested ones**: an outcome class, an invariant
and a gap each require their own non-empty array, and until issue #6 none of the
three could carry one at all, so an invariant's provenance went onto its parent
entity and an outcome class's into `description` prose. Measured on the run that
issue reports: `invariant` claims were cited 0 of 55 times and `outcome_class` 7
of 62, with 24 more appearing only inside prose — 117 of 434 claims with nowhere
structured to record where they came from, and none of them visible to
`claim-utilisation` or to `check-refs`. As everywhere else here, resolving a
citation means the claim *exists*, never that it supports the element.

**No representation for a field's value domain.** `capability.params` and
`entity.fields` carry only a name and a type, with `additionalProperties:
false` on both — a param must additionally state whether it is `required`,
and a field cannot state that at all — and neither has anywhere in the schema
to record that a field's value must be, say, one of three enumerated strings.
So every concrete value anywhere downstream of the seal is a prescription
`rb-instantiate` invents, never an assertion grounded in a claim. See
[`docs/design/limitations.md`](../design/limitations.md) for what this rules
out checking.

Fields worth knowing: `entities[].invariants[].machine` (one of four typed
forms — `compare`, `count`, `join`, `unique` — evaluated mechanically by
`check-refs` against a seed; an invariant may instead carry `prose` and no
`machine`, which no check layer evaluates); `goals[].expected_hop_depths`
(the multi-hop depths a goal is expected to be tested at, read by `rb-score`'s
goal matrix).

## The propose/score loop's parts

The three entries below are the per-round, per-batch slices the two sealed
documents that follow them — `scenarios` and `coverage` — are assembled from.
They exist for one reason: **no prompt should write a document that grows with
the world model's denominator.** A single `rb-propose` dispatch used to re-emit
every scenario of every previous round, and a single `rb-score` dispatch used to
re-emit that list plus both coverage matrices, so the response a model had to
produce grew with the run rather than with the round's work — and on a real
target it exceeded the harness's output cap, which truncates rather than fails.
Each part below is bounded by its own batch instead, and code composes the whole.

Each of the three is now its own stage's layer-1 gate:
`validate --stage propose-batches` gates `batches`, `--stage propose` gates
`scenarios-part`, and `--stage score` gates `score-part`. The sealed documents
moved with them — `scenarios` is `propose-seal`'s gate and `coverage` is
`score-seal`'s — so no prompt stage is gated on a document that grows with the
denominator any more. `batches` resolves by *iterating* the rounds that have a
plan rather than always returning a path: `propose-batches` legitimately writes
nothing when no hole is closable, and that absence is how the loop learns it is
over.

Like the reconcile partials above, none of these schemas restates an element it
shares with a sealed document: `scenarios-part` resolves
`scenarios-0.1.json#/$defs/scenario`, and `score-part` resolves
`coverage-0.1.json#/$defs/hole`, that schema's own `verdict` enum, and the
scenario's `rejected_reason` enum, through `validate._schema_registry`. Two of
those refs point at a *property* subschema rather than a `$defs` entry, which is
a legal target and the one that was available here — the alternative was a copied
enum that `score-seal` would carry onto a sealed scenario, so a sixth value added
on one side alone would make the ruling unrecordable or the sealed document
invalid.

The **one** deliberate non-`$ref` is `score-part`'s `status`, and it is a
subtraction rather than a copy: the sealed scenario's enum also admits
`proposed`, which a ruling may not name, so sharing the definition would widen
the part back to the value it exists to exclude. Its own `description` says so,
beside the shared `rejected_reason` it sits next to.

## `batches`

- **Schema:** `src/rubrica/schema/batches-0.1.json`
- **Written by:** `propose-batches` (code, `rubrica propose-batches`), from the
  round's coverage report — not a prompt, for the same reason `emit` is code: the
  partition must be reproducible, or a change in a round's output cannot be
  attributed to the model that wrote it
- **Read by:** the `propose` fan-out (each member is dispatched with one batch
  id and reads its own entry), `score` (for the **round number only** — the
  highest-numbered plan on disk is the round being scored, which stays derivable
  in the round every member declined and left no scenario tagged with it),
  `check-refs`
- **Path:** `02-batches/round-<N>.json` (`paths.RunPaths.batches`)

One round's closable holes, partitioned into batches whose projected output
keeps a single `rb-propose` dispatch inside the harness output cap. A batch is a
**writing unit, not a decision unit** — every closable hole reaches exactly one
member, and which holes are closable is `rb-score`'s ruling rather than this
partition's, so the partition can never quietly drop work.

**One plan per round, not one per run.** The plan is what says which batch ids a
round's parts are allowed to name, so a singleton file the next round overwrote
would have the part checker validate round 1's parts against round 2's
assignment — reporting correct parts as unexplained, and naming the wrong
artifact while doing it. Every sibling artifact in this loop is per-round for the
same reason, and `paths.RunPaths.batches_rounds()` is the listing that walks
them.

Fields worth knowing: `cap_bytes` (the per-member budget every batch was packed
against, echoed here as `slices` echoes its own so a reader auditing one
projection need not open the manifest); `bytes_per_scenario` (the estimate the
projection used — a default until a sealed `02-scenarios.json` exists, the mean
over that file afterwards, which is what makes the partition self-calibrating,
and what a reader comparing two rounds' batch sizes needs to tell a changed
estimate from a changed hole count);
`batches[].projected_bytes` (`hole_refs` length times `bytes_per_scenario`,
recomputed by `check-refs` so a batch cannot drift from its own header);
`batches[].id` (code-minted, short and stable, because it is both a path segment
and the prefix on the scenario ids its member mints). `batches` carries
`minItems: 1` — a round with no closable hole produces no document at all, so an
empty array here is a partition defect rather than a quiet round.

## `scenarios-part`

- **Schema:** `src/rubrica/schema/scenarios-part-0.1.json`
- **Written by:** the `propose` fan-out, run as `rb-propose`, one part per batch
- **Read by:** `propose-seal` (code), which seals `02-scenarios.json` from every
  part; `check-refs`
- **Path:** `02-scenarios/round-<N>/<batch-id>.json`
  (`paths.RunPaths.scenario_part`)

What one `propose` member wrote for its own batch, and nothing else — never a
sibling's scenarios and never an earlier round's. This is the whole point: the
part is bounded by its batch, while the document it is assembled into is not.

Fields worth knowing: `batch_id` (which `02-batches/round-<N>.json` entry this
part answers, so the seal can hold every batch to exactly one part);
`scenarios[]` (each the same `$defs/scenario` the sealed document carries). The
array has **no** `minItems`, deliberately: an empty one is a real record saying
this member read its batch and could close none of it, which is what a refusal
condition exists to produce.

## `score-part`

- **Schema:** `src/rubrica/schema/score-part-0.1.json`
- **Written by:** `score`, run as `rb-score`, one part per round
- **Read by:** `score-seal` (code), which composes
  `03-coverage/round-<N>.json` from it, and `propose-seal` (code), which folds its
  `rulings` into `02-scenarios.json`; `check-refs`
- **Path:** `03-score/round-<N>.json` (`paths.RunPaths.score_part`)

Everything `rb-score` decides and nothing it can compute. The coverage matrices
are **absent on purpose**: `rb-score`'s own Method already specifies both as
pure functions of the world model and the scenario list, and `check-refs`
recomputes them in checker form, so the seal computes them and this part carries
only the judgment — the folds, the rejections, the hole reasons and the verdict.

Fields worth knowing: `rulings[]` (one entry per scenario whose status *changes*
this round — a scenario absent from every round's rulings keeps the `proposed`
status its propose member gave it, which is why `status` here admits only
`active`, `duplicate` and `rejected`; a ruling naming `proposed` would be a
no-op that still had to be honoured); `duplicate_of` and `rejected_reason`
(required with their respective statuses, the same conditional the `scenarios`
schema applies); `holes[]` (the same `$defs/hole` the sealed report carries,
each with the `reason` and `justification` that are judgment and cannot be
computed); `verdict` (the same four values `coverage` defines, and still only
`rb-orchestrate` acts on it).

## `scenarios`

- **Schema:** `src/rubrica/schema/scenarios-0.1.json`
- **Written by:** `propose-seal` (code, `rubrica propose-seal`), which assembles
  it from every `scenarios-part` and folds in every `score-part`'s rulings. It
  runs twice a round — once so `score` has a document to read, again so the
  statuses are folded before `score-seal` reads it — and it never reads its own
  output, which is what lets the second run agree with the first by construction
- **Read by:** `rb-score`, `rb-instantiate`, `rb-challenge`, `emit` (code),
  `rb-orchestrate`, `score-seal` (code); `dedupe-candidates`, `compare-gold`.
  **Not** by `rb-propose`: a member's worklist is its batch, and a
  `not_yet_attempted` hole is by definition one no scenario covers
- **Path:** `02-scenarios.json`

Every proposed test across every round of the propose/score loop, each with a
`status` (`proposed`, `active`, `duplicate`, or `rejected`) and a `provenance`
block naming the `hole_refs` and `claim_ids` that motivated it. A scenario's
`id` is permanent even once a later round marks it `duplicate` or `rejected` —
the round history stays legible rather than being overwritten.

Fields worth knowing: `capability_refs[]` (each pairs a `capability_id` with
an `outcome_class_id` — the coverage cell this scenario is meant to close);
`duplicate_of` (required when `status` is `duplicate`); `rejected_reason`
(required when `status` is `rejected` — one of five fixed values, including
`blocked_by_gap`).

## `coverage`

- **Schema:** `src/rubrica/schema/coverage-0.1.json`
- **Written by:** `score-seal` (code, `rubrica score-seal`), one `round-N.json`
  per round plus a byte-identical `latest.json`. The matrices are computed there
  rather than copied out of the score part, so a percentage cannot disagree with
  the matrix beneath it
- **Read by:** `propose-batches` (code) and `rb-propose` (via `latest.json`),
  `rb-orchestrate`, `score-seal`'s own progress baseline (via `round-(N-1).json`)
- **Path:** `03-coverage/round-<N>.json`, `03-coverage/latest.json`

One round's coverage report against the frozen `denominator`: a
`capability_matrix` (the **drivable** capability × outcome-class cells — those
whose capability declares a `binding.tool` — each `covered` or not, with the
`scenario_ids` that cover it), a `goal_matrix` (same shape, per goal), a list of
uncovered `holes` (each with a `reason` — `not_yet_
attempted`, `unreachable`, `out_of_scope`, or `blocked_by_gap`, the last
requiring a `gap_id`), `progress` counters, and the round's `verdict`.

Matrix and holes together account for every cell the world model declares, not
just the scored ones: `score-seal` writes one computed `unreachable` hole for each
declared cell the target cannot be driven on, so a narrowed matrix is a narrowed
denominator rather than a silent cap. A hole `rb-score` wrote for the same cell
wins over the computed one.

Fields worth knowing: `verdict` (`continue`, `converged`, `halted_no_progress`,
or `halted_round_cap` — *computed* by `rb-score` and copied through here; only
`rb-orchestrate` acts on it, by running another round of the loop or stopping);
`denominator_version` (must match the world model's frozen value, or the
percentages this round reports are meaningless).

## `seed`

- **Schema:** `src/rubrica/schema/seed-0.1.json`
- **Written by:** `instantiate`, run as `rb-instantiate` (fan-out, one per
  active scenario)
- **Read by:** `rb-challenge`, `emit` (code); `check-refs` (seed conformance,
  invariant evaluation, the reachability gate)
- **Path:** `04-instances/<scenario_id>/seed.json`

The concrete world one scenario's test runs against, distractors included.
The schema constrains only the envelope — `schema_version` and a `collections`
object of arrays of objects — because a seed's real shape comes from the
world model's entities, which `refs.py` checks it against rather than a
second copy of the schema.

**Seed conformance is one-directional.** `check-refs` verifies every
collection, field, and type a seed *does* declare against the world model
(seed→world), but never that a seed supplies everything the world model
*declares* (world→seed) — a seed can drop an entire declared collection, or
declare all of them empty, and pass both check layers with zero findings.
Whether partial seeds are legal is an open design question. See
[`docs/design/limitations.md`](../design/limitations.md).

## `expected`

- **Schema:** `src/rubrica/schema/expected-0.1.json`
- **Written by:** `instantiate`, run as `rb-instantiate`
- **Read by:** `rb-challenge`, `emit` (code); `check-refs` (the reachability
  gate)
- **Path:** `04-instances/<scenario_id>/expected.json`

The oracle for one instantiated scenario, derived from its own `seed.json`
rather than the seed being built to fit a pre-chosen answer. Carries the
`discriminating_fact` that makes the scenario answerable only one way, an
`answer_reference`, one or more `assertions`, a `trajectory` (the tool calls
expected, under a `match` mode of `subset`, `exact-set`, or `exact-sequence`),
and a `completion` status.

Fields worth knowing: `assertions[].kind` — `answer_contains`,
`answer_excludes`, and `value_equals` each require a `grounded_in.
seed_pointer` (a JSON Pointer into this scenario's own seed, and only this
scenario's — the reachability gate cannot resolve a pointer into a sibling's
seed); `tool_called` and `tool_not_called` instead require a `capability_id`
and forbid `grounded_in`.

## `verdict`

- **Schema:** `src/rubrica/schema/verdict-0.1.json`
- **Written by:** `challenge`, run as `rb-challenge` (fan-out, one per
  instance)
- **Read by:** `emit` (code); `rb-orchestrate` (a `re-seed` verdict's fields
  are appended verbatim, never paraphrased, to the re-dispatch they provoke)
- **Path:** `05-verdicts/<scenario_id>.json`

`rb-challenge`'s adversarial ruling on one instantiated scenario: `accept`,
`re-seed`, or `reject`, plus `uniquely_determined`, `derivable_without_
guessing`, and `minimum_tool_calls_found`. A `false` `uniquely_determined`
requires at least one `alternative_answers` entry with its own
`world_consistent_reason` — a verdict claiming ambiguity must show the
ambiguity it found, not merely assert it.

Fields worth knowing: `flags` (currently only `difficulty_overstated`);
`notes` (required on every verdict — the field `rb-orchestrate` quotes
verbatim on a `re-seed` re-dispatch, so its wording is what the next attempt
actually receives).

## `suite-expected`

- **Schema:** `src/rubrica/schema/suite-expected-0.1.json`
- **Written by:** `emit`, run as `rb-emit` (a thin wrapper over the code in
  `emit.py`)
- **Read by:** the verifier `smoke` runs inside each task container
  (`src/rubrica/suite/verify.py`) — not itself a pipeline stage
- **Path:** `06-suite/<scenario_id>/tests/expected.json`

A projection of the matching `04-instances/<sid>/expected.json` onto tool
names a transcript will actually show, plus fixed scoring `weights`
(`assertions: 0.8`, `trajectory: 0.2`, both `const`). `grounded_in` is
deliberately absent from this schema — the emitted task container carries no
`seed.json` for a verifier to resolve a pointer against, so the projection
drops what it cannot check at that point.

Fields worth knowing: `contract` (always the literal string `rubrica/v1` —
the value `suite/verify.py` checks before trusting anything else in the
file); `trajectory.operations[].tool`/`args` (the capability's `binding.tool`
and `binding.fixed_args` merged with the scenario's own call arguments, not
the world model's `capability_id` — a transcript never shows a capability id).

## `report`

- **Schema:** `src/rubrica/schema/report-0.1.json`
- **Written by:** `smoke` (code)
- **Read by:** `check-refs` (cross-checked against `manifest.json`'s `run_id`
  and the emitted suite); otherwise the terminal artifact — nothing downstream
  reads it
- **Path:** `07-report.json`

The result of running the emitted suite against three agent roles — a
`weak_baseline` that should fail nearly everything, the `under_test` agent,
and an `oracle` handed the reference answer that should pass nearly
everything — with one `tasks[]` entry per emitted scenario and a `summary`
rolling up `mean_reward_by_role`. `tasks[]` requires at least one entry: an
empty report would otherwise validate cleanly and describe a suite nobody ran.

Fields worth knowing: `verdict` — `healthy` (a real spread), `degenerate_
trivial` (the weak baseline passes too much, indicting the suite), `broken_
labels` (the oracle fails too much, indicting the labels or the verifier —
never the agent under test — and outranking `degenerate_trivial` when both
could apply), or `inconclusive` (too few scoreable tasks to say anything).

## Human-authored configs

Two more schemas exist under `src/rubrica/schema/` for files no stage ever
writes — a person authors them, and they are handed to a subcommand as a
flag, not read by any pipeline stage. **A config that fails its own schema is
a usage error (exit 2), not a finding (exit 1): there is no stage to hand a
repair prompt to**, so the same defect that would be a repairable `1` in a
stage's own output is unrecoverable here.

### `agents-0.1.json`

- **Schema:** `src/rubrica/schema/agents-0.1.json`
- **Consumed by:** `rubrica smoke --agents PATH`

The agent roster for a smoke run: one entry per role (`weak_baseline`,
`under_test`, `oracle`), each with a `model` label and a `command` argv list.
`smoke` substitutes `{task_dir}`, `{logs_dir}`, and `{scenario_id}` into each
argv element and resolves the executable *before* any agent runs — a bad
command fails the whole roster at exit 2, never partway through a run.

### `gold-0.1.json`

- **Schema:** `src/rubrica/schema/gold-0.1.json`
- **Consumed by:** `rubrica compare-gold --gold PATH`

A hand-authored benchmark — the roughly ten hand-written bench tasks
`compare-gold` measures a generated suite's recall and novelty against. Its
`goal_id` and `capability_refs` are world-model ids, so a gold file has to
name the same goals, capabilities, and outcome classes the run's own
`01-world-model.json` declares, or nothing in it can match.
