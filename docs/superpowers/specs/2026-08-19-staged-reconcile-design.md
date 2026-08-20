# Staging reconcile into a sequence of bounded passes

**Date:** 2026-08-19
**Status:** design, approved in conversation; no implementation yet
**Supersedes nothing.** `reconcile` has been a single dispatch since the pipeline
existed.

---

## 1. The problem, root-caused

`reconcile` is dispatched once, reads every file under `01-claims/`, and emits
the whole world model in one turn. On a real corpus that is roughly 590 claims
across 29 inputs. Against the shared LiteLLM gateway that dispatch fails.

The cause is **not** output length and **not** input size. It was root-caused on
2026-08-19 with plain `urllib`, no Claude Code involved: something in the path
closes a streaming connection after ~300s **with no bytes on it**, and LiteLLM
1.85.5 emits no SSE keepalive, so a long silent think is indistinguishable from
a hang. Streams of 322s and 398s survived while producing bytes throughout; a
dispatch with a large thinking budget died at 301.0s with zero bytes, three
times, at the same second.

So the quantity that kills a dispatch is **how much it must think before it can
write its first token.**

Reconcile today is the worst possible shape for that: hold every claim in mind,
plan an eight-collection merge, then write. The reproduction case in the
root-cause record is almost a paraphrase of this stage's own prompt — "think
carefully about coverage before writing. Output only JSON."

Two fixes were considered and are not this design. Raising client timeouts was
measured ineffective, because the close is server-side. Capping the thinking
budget was measured effective, and is rejected on purpose: it caps thinking on
the highest-judgment barrier in the pipeline, the one stage where two dispatches
over near-identical claim sets already disagreed about which stages a gap
blocks — and `blocks` is what makes the orchestrator halt. Trading judgment
depth on that stage to survive a gateway timer trades exactly the thing this
experiment measures.

**This design reduces the thinking each dispatch must do before writing, without
reducing the thinking any dispatch is allowed to do.**

## 2. What changes, and what does not

Unchanged, deliberately:

- **`01-world-model.json` keeps its path, its schema, and its byte shape.** Every
  stage after reconcile is untouched. So are the committed
  `tests/fixtures/<name>/recorded/01-world-model.json` recordings, and the
  golden toy world.
- **Human gate 1 stays where it is** — after the world model exists, before
  `propose`.
- **The barrier property survives whole.** Every pass still reads all of
  `01-claims/`. Input size is a slowness cost on this gateway (~50k input tokens
  ≈ 98s), not a death cost — a 274KB body returned in 3.2s. Nothing here narrows
  which claims a pass may read.

Changed:

- `reconcile` is replaced by a sequence of stages, each writing one partial
  artifact, closed by a code-only stage that assembles the world model.
- The coverage denominator becomes arithmetic performed by code rather than by a
  prompt.
- Each pass carries its own row in `manifest.stages`, so model, effort and skill
  digest are recorded per pass.

## 3. Rejected: code-proposed contradiction neighbourhoods

An earlier draft of this design had a deterministic step ahead of contradiction
finding: group claims by subject/kind/target in code and emit candidate
contradiction *neighbourhoods*, the way `dedupe-candidates` proposes pairs and
never decides. It was withdrawn, and the reasoning is recorded here because it
is the reasoning that shapes §4.

It was defended as carrying the same cost `survey`'s digest already carries for
`triage`. That defence is wrong, and the difference is categorical:

| | triage's digest | neighbourhood narrowing |
|---|---|---|
| unit narrowed | a candidate file | a *pair* of claims |
| population | tens to a few hundred | ~n²/2 ≈ 174,000 |
| every unit represented on disk | yes, the catalogue lists all | no, only proposed pairs exist |
| the loss is a recorded decision | yes, with a reason | no, silent absence |
| the prompt can flag its own insufficiency | yes, `digest_insufficient` | it cannot know what it was not shown |
| a human can overrule it at a gate | yes, per candidate, at gate 0 | nothing to point at |

Triage's blind spot is enumerated, attributed and overrulable. A pair filter's
is none of those, because the population of pairs cannot be written down for a
human to review.

The decisive cost is **attribution**, and it compounds with triage rather than
merely sitting beside it. Today a thin contradiction set has four candidate
explanations: the corpus genuinely lacks disagreement; triage declined the wrong
inputs; extract missed claims; reconcile under-recorded. A heuristic pair filter
adds a fifth — the pair was never proposed — and the fifth is indistinguishable
from the first and the fourth. Two unattributable losses in series is much worse
than one, because a thin result can no longer be traced to a stage. For a
project whose value is falsifiability, that is a bad trade for a gateway timer.

## 4. The stage sequence

`paths.STAGES` loses `reconcile` and gains the following, in this order,
between `extract` and `propose`.

| Stage | Runs as | Writes | Think depth |
|---|---|---|---|
| `reconcile-subjects` | `rb-reconcile-subjects` | `01-subjects.json` | shallow — classification |
| `reconcile-contradict` | `rb-reconcile-contradict` — fan-out, one per subject | `01-contradictions/<subject_id>.json` | bounded by its subject |
| `reconcile-capabilities` | `rb-reconcile-capabilities` | `01-capabilities.json` | moderate — global grouping |
| `reconcile-outcomes` | `rb-reconcile-outcomes` | `01-outcomes.json` | shallow — per declared capability |
| `reconcile-entities` | `rb-reconcile-entities` | `01-entities.json` | shallow — per declared capability |
| `reconcile-goals` | `rb-reconcile-goals` | `01-goals.json` | shallow |
| `reconcile-gaps` | `rb-reconcile-gaps` | `01-gaps.json` | moderate — checking-shaped |
| `reconcile-seal` | code | `01-world-model.json` | none |

**Gates.** Every new stage is gated on `validate` for its own kind.
`reconcile-contradict` and `reconcile-seal` are additionally gated on
`check-refs`, the first only once every fan-out member has finished (§7). There
is exactly one human gate in this sequence and it is **gate 1, after
`reconcile-seal`** — no new human gate is introduced, because none of these
passes decides anything a human could not review better against the assembled
world model.

Compound names rather than six new verbs, and this is settled rather than open:
these are **one logical step, engineered as substeps**, and the names should say
so. The family stays visible in `paths.STAGES`, which is the pipeline's ordering
*and* its documentation; a reader sees at a glance that these replace one stage;
and the README drawing can fold them back into the single line a newcomer should
read (§9). All partials stay in
the `01-` band, so the band's meaning — world-model construction — is preserved.

### 4.1 The subject cover, and why it is a cover

`reconcile-subjects` does one thing: assign every claim in `01-claims/` to one
or more subjects. Its output is small, its think is shallow (classification, not
comparison), and it is **total** — a layer-2 check verifies that every claim id
under `01-claims/` appears in it.

It is a *cover*, not a partition: a claim may be assigned to several subjects,
and the skill instructs over-assignment when the subject is unclear.
Over-assignment is the safe direction, and §5 of every skill in this repository
already trades on that instinct.

This is still a narrowing — a contradiction between two claims filed under
different subjects can be missed. What makes it acceptable where the pair filter
was not: the loss is enumerable, mechanically checkable for totality,
over-assignable by instruction, and readable by a human at gate 1. It owes a
`limitations.md` entry, and that entry must state the difference from triage's
digest rather than claim kinship with it.

### 4.2 Contradiction finding fans out over subjects

Each member reads every claim in its own subject — **across all input files**, so
cross-artifact contradiction detection, the entire reason reconcile exists, is
preserved exactly. Each writes its own small file, so bytes flow and time to
first byte stays short by construction.

This buys a check that does not exist today: every subject in the cover must
have an output file, **even one recording that no disagreement was found there.**
"Was the sweep thorough?" is unobservable in today's single turn. "Did it visit
every subject?" is structural.

The fan-out obeys the gateway's other, unrelated failure: envoy returns
`upstream connect error ... reset reason: connection timeout` intermittently at
5+ concurrent streaming requests, so **at most 3 members run at a time.**

### 4.3 Why contradictions come before the modelling passes

A contradiction is claim-versus-claim and depends on nothing else, so it can run
first — and running it first makes its resolutions a **constraint** on the passes
that follow rather than something to be reconciled against them afterwards. The
modelling passes declare the contradiction parts under `reads`.

This is a mitigation, not a guarantee. Whether a modelled capability quietly
settles a disagreement recorded `unresolved` is a question about whether a claim
*supports* an element, which is the semantic hole layer 2 is forbidden to paper
over with an invented mechanical check. The instrument is gate 1's brief showing
the contradictions beside what was modelled.

### 4.4 Outcome classes are a join, not a collection

`outcome_classes` is nested **inside** the capability object in
`world-model-0.1.json`, `required`, with `minItems: 1`. So `reconcile-outcomes`
cannot write a sibling collection. It writes a join table keyed by
`capability_id`, and `reconcile-seal` folds each capability's outcome classes
into its object.

Keeping it a separate pass rather than folding it back into
`reconcile-capabilities` is the deliberate choice. The strongest measurement in
this repository says quantifying over a written-down capability list produced
every outcome-class cell a real run needed, while an unquantified instruction to
"group claims" dropped 45% of them. Splitting the pass makes that list a *file*
rather than a memory of having just written it — and it yields a completeness
check: every capability in `01-capabilities.json` must have an entry in
`01-outcomes.json`.

### 4.5 Gaps last, as the self-audit

`reconcile-gaps` reads every prior partial as well as every claim. That ordering
is deliberate: §5's refusal conditions overwhelmingly resolve to "record a gap
instead," so the pass that writes gaps is the right one to audit what its
predecessors declared — a capability with no supporting claim, an invariant
promoted to `machine:` on an inference, an outcome class nothing states.

## 5. Artifacts, kinds and schemas

Each new prompt stage needs an artifact kind and a schema, because layer 1 is
what stops a stage passing trivially: `validate.STAGE_ARTIFACTS` gains one entry
per stage, and a stage that produced none of its kinds fails.

New kinds: `subjects`, `contradictions-part`, `capabilities-part`,
`outcomes-part`, `entities-part`, `goals-part`, `gaps-part`.

New `paths.RunPaths` properties, following the existing naming: `subjects`,
`contradictions_dir`, `contradiction_part(subject_id)`, `capabilities_part`,
`outcomes_part`, `entities_part`, `goals_part`, `gaps_part`.

**Element definitions are not duplicated.** Every partial's elements are already
defined once, in `world-model-0.1.json`'s `$defs` (`capability`, `entity`,
`actor`, `goal`, `contradiction`, `gap`, `invariant`, `claim_refs`, `id`). The
part schemas `$ref` those definitions rather than restating them, which requires
one change in `validate.py`: `_validator_for` currently builds
`Draft202012Validator(schema)` with no registry, so a cross-file `$ref` would
attempt network resolution. It gains a `referencing` registry populated from the
schema directory, keyed on the same `(kind, schema_root)` cache key so
`RUBRICA_SCHEMA_DIR` still takes effect.

Considered and rejected: generating self-contained part schemas from the
world-model schema with a committed-output script, byte-compared by a test, the
way both diagrams work. It fits the house pattern, but it adds a generated file
and a build step to avoid a duplication a registry removes outright. "Derive, do
not restate" is already this repository's rule.

`validate.py` is on the list of modules whose unreadable-input paths must be
tested — a bad `RUBRICA_SCHEMA_DIR`, `chmod 000`, `chmod 0444` — because a
misconfigured run must exit 2 while a stage defect must exit 1.

## 6. `reconcile-seal`

A code stage, invoked as `rubrica reconcile-seal --run <run>`, added to
`cli.SUBCOMMANDS`, `skills.CODE_ONLY_STAGES` (beside `intake`, `smoke`,
`survey`) and documented in `docs/reference/cli.md`. Being code, it streams
nothing and cannot hit a 301s reset however large the assembled model is.

It does exactly three things:

1. Reads every partial and assembles `01-world-model.json` — including folding
   `01-outcomes.json` into each capability's `outcome_classes`.
2. Computes `denominator`: `version: 1`, `capability_cells` as the total count of
   capability × outcome-class pairs, `goals` as the count of goals.
3. Writes through `write_json`, so the canonical byte form holds and `diff-runs`
   does not report formatting as variance.

It assembles; it does not check. Cross-artifact checking is layer 2 and belongs
in `refs.py`.

**One observation is lost, and it should be recorded as a loss.** Reconcile's
invariant 2 — `denominator.capability_cells` equals what the stage actually
wrote, recomputed by `refs.check_world_model` — becomes an identity once code
writes the number. Arithmetic is not judgment, so this is the right trade, but
it is one fewer checkable claim about a prompt's output and belongs in
`limitations.md` as such.

## 7. New layer-2 checks

Added to `refs.py`, and reached by `check_all`, which runs every checker the run
has inputs for:

- `check_subjects` — every claim id under `01-claims/` appears in the cover;
  every subject has at least one claim.
- `check_contradiction_parts` — every subject in the cover has a file in
  `01-contradictions/`; every `claim_a` and `claim_b` resolves to a real claim id.
- `check_outcomes` — every capability in `01-capabilities.json` has an entry in
  `01-outcomes.json`, and every entry names a declared capability.
- `check_world_model` — unchanged in what it checks; it still recomputes the
  denominator, now against a number code wrote.

`check_contradiction_parts` carries the caveat `check_verdicts` already carries
and it must be documented the same way: it reports every subject without a part
from the moment `01-contradictions/` exists, so mid-fan-out most are missing by
construction. It is meaningful only once every member has finished. There is no
stage-scoped `check-refs`.

## 8. The skills

Each new stage gets `src/rubrica/skills/rb-<stage>/SKILL.md` with a `## Contract`
block and the five mandatory sections in order. `check-skills` holds each to
`paths.RunPaths` attribute names, `validate.STAGE_ARTIFACTS` and
`cli.SUBCOMMANDS`, and enforces `skill.name == f"rb-{stage}"` — which is why
these are stages rather than six skills sharing one stage name.

The existing `rb-reconcile/SKILL.md` is the source material, not something to
paraphrase: its §1 boundary argument (which *knowledge* may be brought to bear,
not which files may be opened), its §3 numbered method, its §4 invariants and its
§5 refusal conditions distribute across the new passes. Two prose facts must be
carried rather than dropped:

- The §1 rule that a resolution may rest only on what the claims establish, never
  on what a system "like this" usually does, belongs in `rb-reconcile-contradict`
  and in every modelling pass that could quietly settle a disagreement.
- The §1 prohibition on rereading one's own last answer needs rewriting rather
  than deleting. It was written against a single-pass stage; in a sequence, a
  later pass reading an earlier pass's partial is the design. What survives is
  the narrower rule: no pass may read `01-world-model.json`, and a
  re-dispatched pass may not read its own previous output.

Every new skill owes an `exercise.md` recording what one real dispatch
measurably did. Those cannot be written until the passes are dispatched, and
each must state what happened rather than what was reasoned.

**Yes, one `exercise.md` per pass, and no merged record.** Each pass is its own
dispatch with its own observable behaviour, and per-pass observability is the
entire justification for making these separate stages rather than one skill
branching on a slice id. A single record covering the family would undercut the
argument the split rests on.

**`rb-reconcile/exercise.md` stays exactly where it is.** It is behavioural
evidence — the record of two real dispatches, including the disagreement about
gap `blocks` that §1 rests on — and this repository's rule is that evidence lives
beside the skill and not only in a ledger, because ledgers get deleted.

It is *not* relocated into `rb-reconcile-subjects/exercise.md` or any other
pass's. That file would then assert that one dispatch of `rb-reconcile-subjects`
did what a dispatch of the superseded single-pass stage actually did, which is
the misattribution class this project has already shipped once and had to
retract. An exercise record states what happened, to the skill it sits beside.

So the directory `src/rubrica/skills/rb-reconcile/` survives its `SKILL.md`,
holding the record and a short note saying which stage it records and that the
stage no longer exists. This is inert to every tool, verified rather than
assumed: `skills._skill_dirs` keeps only children where `SKILL.md` `is_file()`
and, per its own comment, skips a subdirectory without one "rather than
reported"; `expected_skill_names` derives from `paths.STAGES`, which no longer
contains `reconcile`, so nothing is reported missing either; and nothing in
`src/`, `tests/` or `scripts/` reads an `exercise.md` at all.

## 9. What moves outside `src/rubrica`

- `docs/concepts/pipeline.md` — the stage list and what each does.
- `docs/reference/cli.md` — a `rubrica reconcile-seal` section.
- `docs/reference/artifacts.md` — each new kind named as its kind.
- `docs/concepts/glossary.md` — this design introduces terms the glossary does
  not carry. At minimum **subject** (what a claim is about, the unit the cover
  assigns to and the contradiction fan-out slices by), **subject cover** (the
  total, over-assignable assignment of every claim to one or more subjects, and
  why it is a cover rather than a partition), **partial** (a stage output that is
  one part of an artifact rather than an artifact downstream reads), and **seal**
  (the code step that assembles partials and computes the denominator). The
  glossary's standing question is what actually produces or consumes a term, so
  each entry names the pass that writes it.
- `scripts/render-pipeline-diagram.py` — one `ROWS` entry per new stage; re-render,
  never hand-edit the page.
- `scripts/render-readme-diagram.py` — **folded, not enumerated.** Listing eight
  stage lines in the `understand` box is the wrong altitude for a drawing whose
  whole job is a newcomer's view, and it does not fit: `phase()` draws one 14px
  line per entry in `spec["stages"]` from a fixed `BOX_H`, so eight would
  overflow the box rather than merely crowd it.

  But `stages` is also the coverage claim —
  `test_the_readme_diagram_covers_every_stage_in_contract_order` asserts that
  concatenating every phase's `stages` reproduces `paths.STAGES` *exactly*, and
  that partition is deliberately stronger than a presence check. So the two roles
  separate: `stages` stays complete, and the renderer **derives** the drawn
  labels from it by folding a prefix family into one starred line, `reconcile*`,
  with a footnote in `CAPTIONS` saying that it is one logical step engineered as
  substeps. One new per-phase key naming the prefix to fold, not a second
  hand-maintained list of labels — derive, do not restate.

  A test asserts the fold is total in both directions: every `reconcile-` stage
  in `stages` is covered by the folded label, and no unfolded stage is hidden.
  Without it the fold becomes a way to drop a stage from the drawing silently,
  which is the drift the partition test exists to catch.

  The phase count does not change, and none of these stages leaves `understand`.
- `CLAUDE.md` — the stage table, and the note about which gate brackets what.
- `tests/toy.py` — `_UPTO_STAGES` gains a checkpoint per new stage, and
  `build_toy_run` writes each partial. Check the module before adding a helper:
  nearly every request for a new checkpoint turned out to be for one that
  already existed.
- `brief.py` — gate 1's surface gains the cover's size, the per-subject
  contradiction tally and the unresolved count, beside the utilisation and
  implied size it already shows.
- `rb-orchestrate/SKILL.md` — dispatches the new sequence, holds the fan-out to
  three concurrent members, and still holds gates 1 through 3.

## 10. Risks, and what must be measured

1. **The central hypothesis is untested.** "A bounded job needs a shallower think,
   so time to first byte stays under 300s" is the premise of this whole design and
   it is a hypothesis. TTFB must be measured per pass on the first real run. If a
   pass still stalls, this design has narrowed the problem to one pass rather
   than solved it — which is progress, but it is not the same claim.
2. **The 45% measurement was taken with capabilities in the same turn.** Reading a
   capability list from a file is plausibly stronger than remembering having
   written it, but that is a hypothesis too. Re-measure; do not assume.
3. **Cross-pass incoherence is a new defect class.** Contradictions-first plus a
   declared `reads` is the structural mitigation. No mechanical check is claimed.
4. **A cross-subject contradiction can be missed.** Bounded by over-assignment,
   visible in an artifact, owed a `limitations.md` entry.
5. **Surface cost.** This replaces one skill with several, each owing prose, a
   contract, tests and an exercise record. The pipeline gets longer to read and a
   run makes more dispatches. That is the price of per-pass repair, per-pass
   model and effort, and per-pass observability — and it is the largest thing a
   reviewer might reasonably want to trade down.

## 11. Open points

- **Whether `reconcile-goals` and `reconcile-entities` should be one pass.** Both
  are shallow. They are separate here because `goals` is half the frozen
  denominator and deserves its own artifact and its own gate-1 visibility, while
  `entities` does not. This is editorial and no test can rule on it.
Two points that were open in the first draft are now decided and recorded where
they belong rather than here: the compound `reconcile-*` names (§4), and the home
of `rb-reconcile/exercise.md` together with whether each pass gets its own (§8).

## 12. Entries owed to `docs/design/limitations.md`

- The subject cover can file two disagreeing claims under different subjects, so
  a contradiction can be missed; how this differs from triage's digest, and why
  the pair-filter alternative was rejected as worse.
- `denominator` written by code is no longer a checkable claim about a prompt's
  output.
- Whether the gateway's contended connection pool is per-API-key or global is
  unknown, and it decides whether a fan-out degrades other people's runs.
