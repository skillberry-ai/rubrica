# Forcing reconcile read coverage: `inputs_seen` on the partials, and `claims` on three child elements

**Date:** 2026-08-26
**Issue:** [#6](https://github.ibm.com/kaegis/rubrica/issues/6) — "A reconcile
pass's claim-file read coverage varies 3/23 to 23/23 across identical dispatches"
**Status:** design approved, plan not yet written

## 1. The problem

Issue #6 is the clean same-input variance measurement the register says has never
been taken: three reconcile passes re-dispatched over a byte-identical run
directory, same skill, same model, same effort, nothing appended. Read coverage of
`01-claims/` came out 12/23 → 23/23 for `rb-reconcile-capabilities`, 10/23 →
13/23 for `rb-reconcile-entities`, and 9/23 → **3/23** for
`rb-reconcile-goals`. One pass improved to full coverage and one got materially
worse, which is what rules out a systematic cause — a schema barrier, a
permission block or a size cap could not do both on identical input.

Claim utilisation moved 80/434 (18.4%) → 146/434 (33.6%) with it, and the
correlation is exact: claims in files a citing pass opened were cited at ~38%,
claims in files it never opened at **0/167**. Both runs reported `subtype:
success`, both passed `rubrica validate` at exit 0, and the world model's element
counts were identical — same five capabilities, same eight gaps — so the two runs
are indistinguishable to any check that counts elements rather than citations.

### 1.1 The cause is not the prompt

`rb-reconcile-capabilities` §1 already says the pass reads every file under
`01-claims/` — "not one of them, all of them" — and §3 step 1 already names this
exact failure mode: "a merge built from a skim will drop the claim that only
shows up once, in the file you read fastest." The instruction was correct and was
not followed. All four passes also already read `manifest`, so the issue's own
suggestion 3 rests on a false premise: `manifest.inputs[].artifact_id` names
every input, and a pass does not need to list the directory to know N.

The cause is that **a reconcile pass's output shape does not require having read
every input**, so a skimmed read produces an artifact that is clean at both
layers.

### 1.2 One pass in the family is immune, and that is the design to copy

`rb-reconcile-subjects` must name every claim id, and `refs.check_subjects`
enforces totality. On the measured run its cover carries **434 ids spanning 23 of
23 artifacts** — full read coverage, in the same dispatch conditions where the
goals pass read 3 of 23. Totality of the *output* forces the read. Exhortation in
the *prose* did not.

### 1.3 The detector's defect: it aggregates across passes

The six claim kinds partition onto the passes that own them, and per-kind
citation tracks the issue's measured read coverage:

| owning pass | read coverage (run 2, per issue #6) | own-kind claims cited (measured) |
|---|---|---|
| `rb-reconcile-capabilities` | 23/23 | capability **110/135 = 81%** |
| `rb-reconcile-entities` | 13/23 | entity **22/117 = 19%** |
| `rb-reconcile-goals` | 3/23 | goal **2/38 = 5%**, actor 5/27 |
| `rb-reconcile-outcomes` | not measured | outcome_class **7/62**, plus 24 prose-only |

The aggregate 33.6% is the average of an 81% pass and a 5% pass, which is why it
reads as merely low rather than as one pass having skipped twenty files. Worse,
`refs.check_claim_utilisation`'s zero rule keys on the *artifact* alone, so one
diligent pass masks another's total miss on the same file:
`trajectories-json-9` shows 13 claims cited, every one of them a capability
claim, while the goals pass never opened it. On this run the rule fired **once**,
against `pyproject-toml`.

Re-keying the same zero rule on (owning pass, artifact) fires **31 times** on the
same run — 1 against capabilities, 14 against entities, 16 against goals — which
is the read-coverage ranking. That is the localisation the aggregate destroys.

### 1.4 Two of the six kinds cannot be cited at all

`world-model-0.1.json` gives `$defs/capability`, `$defs/entity`, `$defs/actor`
and `$defs/goal` a required `claims` array. It gives **`$defs/invariant`,
`$defs/outcome_class` and `$defs/gap` none**, all three
`additionalProperties: false`. Measured on the run: `invariant` **0 of 55**
structured citations, `outcome_class` **7 of 62** with 24 more appearing only
inside `description` prose — 117 of 434 claims, **27% of the corpus**, whose
provenance has nowhere structured to go.

`gap` is the third and issue #6 does not name it, but it is where the damage was
visible at the gate a human holds: the run-1 gate-1 brief reported
`trajectories2-json-14: 0/19 claims cited (0%)` while `gap-search-tool-error-
response`, in the same brief, rested its argument on
`clm-trajectories2-json-14-019` in prose.

So the metric that is supposed to detect the variance is itself depressed by a
schema hole over a quarter of the corpus. The hole is a prerequisite, not an
adjacent defect.

## 2. Rulings taken

1. **`claims` is required, `minItems: 1`, on all three child defs** — not
   optional. It matches the four defs that require it already, and an optional
   field leaves the instrument a report forever.
2. **The disposition is per artifact with a required prose note**, not per
   dropped claim and not an enum. Per-claim reasons would have the goals pass
   writing 36 of them, against an output cap issue #9 already reports a pass
   hitting. An enum would invite a pass to pick the nearest label for a drop that
   fits none — the move the register already criticises `rejected_reason` for.
3. **The disposition lives on the part, not in a separate artifact.** The
   accounting and the output are then one document that validates together, and a
   repair that rewrites the part cannot leave a stale disposition beside it.
4. **The existing "read all of them" prose is not strengthened.** It already
   names this failure mode and did not prevent it; a longer exhortation is the
   change with the worst measured odds.
5. **The fan-out-incomplete finding class (issue #6's suggestion 2) is out of
   scope.** It is a good three-line fix — `Finding` already carries `layer` — but
   it is independent, and bundling it makes one commit answer two defects.

## 3. Design

### 3.1 `claims` on the three child defs

The change is to `world-model-0.1.json` alone — the parts `$ref` its `$defs`
rather than restating them, so one edit reaches every pass that writes one.
`$defs/invariant`, `$defs/outcome_class` and `$defs/gap` each gain

```json
"claims": { "$ref": "#/$defs/claim_refs" }
```

added to `required`. `claim_refs` already carries `minItems: 1`, so layer 1
enforces "at least one" without a new constraint.

`utilisation._cited_claim_ids` gains three walks: `entities[].invariants[].claims`,
`capabilities[].outcome_classes[].claims`, and `gaps[].claims`. No prose parsing
— the ids move from `description` text into structure, which is the whole point.
`refs.check_world_model` must resolve the new references too, on the same
one-directional rule it already applies: that the id exists, never that the claim
supports the element.

The seal needs no change. It copies `capabilities` items wholesale
(`reconcile.py:217`) and reads named arrays for the rest
(`reconcile.py:233,292-296`), so nested `claims` arrive in the assembled model by
the path they already travel.

### 3.2 `inputs_seen` on four partials

A new schema file `inputs-seen-0.1.json` holds one `$defs/row`:

```json
{
  "artifact_id":    { "$ref": "world-model-0.1.json#/$defs/id" },
  "own_kind_total": { "type": "integer", "minimum": 0 },
  "cited":          { "type": "integer", "minimum": 0 },
  "dropped":        { "type": "integer", "minimum": 0 },
  "note":           { "type": "string", "minLength": 1 }
}
```

`additionalProperties: false`; `artifact_id`, `own_kind_total`, `cited` and
`dropped` required. One rule layer 1 can express and therefore owns:

```json
"if":   { "properties": { "dropped": { "minimum": 1 } } },
"then": { "required": ["note"] }
```

`capabilities-part-0.1.json`, `entities-part-0.1.json`,
`outcomes-part-0.1.json` and `goals-part-0.1.json` each gain a required
document-level `inputs_seen` array `$ref`-ing that row.

**This is the first schema file that is not an artifact kind.** The registry
globs `*.json` under the schema root (`validate._schema_registry`), so the
cross-file `$ref` resolves without registration, and no test enumerates
files → kinds. `ARTIFACT_SCHEMAS` omits it deliberately and needs a comment
saying so, or someone will register a kind no stage produces.

**Rows are total over `manifest.inputs[].artifact_id`,** including inputs holding
zero claims of the pass's own kind. That is the forcing function: a pass cannot
state `own_kind_total: 0` for a file it never opened, and a `0/0/0` row needs no
note, so totality costs nothing where there was nothing to say.

Which kinds each pass owns:

| pass | own kinds |
|---|---|
| `rb-reconcile-capabilities` | `capability` |
| `rb-reconcile-entities` | `entity`, `invariant` |
| `rb-reconcile-outcomes` | `outcome_class` |
| `rb-reconcile-goals` | `actor`, `goal` |

**Two passes own two kinds, and their row merges them** — one
`own_kind_total` per artifact, not one per kind. The row is an accounting of
whether the file was read and what came of it, and both of that pass's kinds come
out of the same read; splitting the column would double the rows to say the same
thing. `cited` is then counted over every `claims[]` array in that pass's own
part, nested ones included: `entities[].claims` **and**
`entities[].invariants[].claims` for the entities pass, `capabilities[].claims`
for capabilities, `capabilities[].outcome_classes[].claims` in the outcomes
part's `outcomes[]` records, `actors[].claims` and `goals[].claims` for goals.
This is why §3.1 lands first — before it, two of the four passes have no
structured place to put a citation and their `cited` column could only ever read
low.

**A claim cited only as a contradiction side counts as dropped here**, because
`01-contradictions/` is not this pass's part and the checker recomputes `cited`
from the part alone. That is the right answer rather than a wrinkle to file off:
the claim genuinely did not enter this pass's output, and the note the row then
requires — "the disputed side of a contradiction recorded `unresolved`" — is
precisely what a human at gate 1 wants to read. It also keeps this checker's
arithmetic independent of `utilisation._cited_claim_ids`, which counts
contradiction sides for its own stated reason.

### 3.3 The checker

A new `refs.check_input_dispositions`, in `check_all` after `check_outcomes` and
before `check_world_model` — after the partials are readable, before anything
reasons about the assembled model. Five findings, every one mechanical:

| finding | what it closes |
|---|---|
| no row for an artifact `manifest.inputs` names | the denominator is the manifest, not the rows |
| a row naming an artifact the manifest does not | an invented row |
| `own_kind_total` ≠ that kind's count in that artifact's claims file | **the forcing function** — the number requires the read |
| `cited` ≠ that artifact's claim ids appearing in this part's own `claims[]` | a flattering count |
| `cited + dropped` ≠ `own_kind_total` | the arithmetic |

A claims file that is missing or unreadable counts as 0 here and stays the
finding of the checker that owns it. This is the `1`-must-name-the-right-artifact
rule: `check-refs` over an unreadable `01-claims/` once produced four fabricated
`no such claim` findings against a correct world model, and a second checker
reporting the same defect against a different artifact is how that happens again.

**`own_kind_total > 0 and cited == 0` is deliberately not a finding.** Such a row
already carries a required note, so the drop is on the record; making it a
finding would fail a repair round that cannot repair anything, and would put a
coverage judgment behind an exit code. It goes to gate 1 instead. This keeps
`check_claim_utilisation`'s ruling intact — zero, never a percentage — and that
ruling's own measurement still holds: on run-20260812-130056, 130 of 287 claims
were uncited and almost all of those drops were correct.

### 3.4 The skill contract and prose

Each of the four passes gains, in its own sections:

- **§2 Output** — what `inputs_seen` is, that it is total over `manifest.inputs`,
  and that a `0/0/0` row is the honest record for an input holding none of its
  kind.
- **§3 Method** — record the row as you finish each claims file rather than
  reconstructing it at the end. A row reconstructed from memory at the end is a
  recollection of having read, which is the thing being measured.
- **§4 Invariants** — the arithmetic, and that `check-refs` recomputes both
  counts from `01-claims/` and from the part itself.
- **§5 Refusal conditions** — one new condition: **a claims file you could not
  read is a refusal, not a guessed count.** Stating a number you did not measure
  is the failure this whole change exists to make impossible, and a pass that
  guesses to satisfy the schema has defeated it.

`writes` and `schemas` are unchanged — the field is on an artifact each pass
already writes — so `check-skills` needs nothing new.

### 3.5 `rb-reconcile-gaps` gets no `inputs_seen`

It owns no claim kind, and a gap asserts what no input contains, so no output
shape can force its read coverage: a pass that read three files can write a
well-formed gap about the other twenty's silence. What it gets is the `claims`
requirement on `$defs/gap` — a gap must cite the claims that make the absence
matter, which is exactly the evidence the run-1 brief had in prose and the
counter could not see.

That its read coverage remains unmeasurable is a real hole and gets its own
register entry rather than being glossed. `rb-reconcile-subjects` and
`rb-reconcile-contradict` need nothing: subjects is already total by
`check_subjects`, and contradict's slice is bounded by that cover.

### 3.6 `gate-brief` at gate 1

The brief gains a per-pass block: for each of the four passes, own-kind claims
cited over total, and every row with `dropped > 0` with its note. It stays a
report on the ruling `claim-utilisation` and `gate-brief` already share — always
exit 0 on a readable run.

This is where run 1 would have been unmissable. The brief today reports
utilisation per input, aggregated across passes, which is the number that read
33.6% while one pass sat at 5%.

## 4. What this does not fix

1. **Read coverage of `rb-reconcile-gaps`** — unmeasurable by construction, per
   §3.5. Register entry, not a fix.
2. **Whether a citation is *apt*.** `inputs_seen` measures that a file was read
   and what was done with its claims. Layer 2 checks that an element references a
   resolvable claim, never that the claim supports it, and nothing here changes
   that — support is gate 1's, and mechanising it is a position the register
   holds deliberately.
3. **The variance itself.** Nothing here makes a dispatch read every file; it
   makes a dispatch that did not read every file produce a *reportable* artifact.
   Whether the obligation changes behaviour is a question only a dispatch can
   answer, and §6 says what would count as an answer.
4. **The two `recorded/` world models.** `test_refusals_live.py` reads them with
   `read_json` and never schema-validates them, so the requirement does not turn
   them red — they become recordings that predate it. Re-recording is a dispatch,
   and hand-writing `claims` arrays into committed model output would fabricate
   the only behavioural evidence this project has. Owed, on the record, not
   forged.
5. **The fan-out-incomplete finding class**, per ruling 5.

## 5. Fixtures

`tests/toy.py` is the model answer a skill imitates, so it must be *correct*
here, not merely valid. Measured on the current fixture: it is at **19/19
claims cited, 100% utilisation**, and it reaches that by citing child-element
claims on the *parent* — `ent-ticket` cites `clm-notes-005` and `clm-notes-006`,
both `invariant`-kind, and `cap-find-tickets` cites `clm-api-005` and
`clm-trace-001`, both `outcome_class`-kind.

**So the golden fixture already models the workaround, and the schema never
required it.** That is the sharpest single piece of evidence for §3.1: the toy
teaches parent-citation, and two real dispatches did not infer it — `invariant`
came out 0/55 and `outcome_class` 7/62.

The fixture edit therefore moves those citations down to the elements they are
about: each invariant cites the claim it came from, each outcome class cites
the claims describing that outcome, and each parent keeps the claims
establishing the parent. Which claim belongs to which child is a semantic
judgment on the fixture's own two capabilities and two entities, and it is the
highest-risk item in the plan — an edit to the toy teaches every skill.

`inputs_seen` rows for the toy's three inputs are then computed from what the
fixture actually cites, not written as literals. Current own-kind spread:
capabilities `api-json` 5/5; entities `api-json` 2/2 and `notes-md` 2/2;
outcomes `api-json` 2/2, `notes-md` 1/1, `trace-json` 2/2; goals `notes-md` 5/5.
Every input that holds none of a pass's kind needs an explicit `0/0/0` row —
which is also the fixture demonstrating the totality rule rather than only
stating it.

The negative fixtures' forbidden-substring lists are their specification and are
not relaxed. `tests/fixtures/toy-contradiction/recorded/` carries 8 outcome
classes, 4 invariants and 3 gaps; `toy-gap/recorded/` carries 10, 4 and 5 — 34
elements that a re-record would give `claims` arrays, per §4 item 4.

## 6. Tests

1. **Schema, both directions.** Each of the three child defs rejects an element
   with no `claims` and with an empty `claims`, and accepts one with a resolvable
   id. Each of the four parts rejects a document with no `inputs_seen`, and the
   `if/then` rejects `dropped: 2` with no note while accepting `dropped: 0`
   without one.
2. **The checker, one test per finding shape**, each built by mutating one field
   of a clean `build_toy_run`, and each asserted to produce exactly its own
   finding and no other — the five shapes in §3.3 are close enough together that
   a mutation reaching two of them is the likely bug.
3. **`own_kind_total` cannot be satisfied without the file.** Delete a claims
   file from a toy run and confirm the row that named its count becomes a
   finding; the point is that the count is recomputed rather than trusted.
4. **`_cited_claim_ids` counts the three new sites**, asserted by moving one
   citation from a parent to its child and confirming the total does not move.
   This is the regression test for the 38 prose-only citations.
5. **Prose predicates, measured in both directions** and scoped with
   `skills.section_body` to the section that owns the rule. Roughly nineteen
   assertions in this repo were measured satisfiable by unrelated content
   because `skills.load()` sets `body` to the whole file; every predicate here is
   deleted-then-reworded before it is committed.
6. **`gate-brief` renders the per-pass block** on a run that has partials, and
   still exits 0 on a run that does not.

What no test can reach: whether a dispatched pass actually fills `inputs_seen`
honestly rather than guessing four numbers per row. That is what §7 is for.

## 7. Verification — the dispatch, and what would falsify this

`make test` green, `make check` clean and `rubrica check-skills` exiting 0 are
necessary and prove nothing about the premise. The premise is that **an output
obligation changes read behaviour where an exhortation did not**, and the
evidence for it is one measurement: `rb-reconcile-goals` dispatched against the
reservation-service run with the obligation in place, read coverage taken from
the transcript with `scripts/audit-reads.sh`, against its measured 3/23 and 9/23.

Falsification is a pass that satisfies `inputs_seen` and still reads three
files — by guessing counts, or by reading each file's first bytes only. Both are
visible in the transcript and neither is visible in the artifact, so the read
audit is the instrument, exactly as it is for the isolation rule. Record the
result in that pass's `exercise.md`, which does not exist yet for any
`reconcile-*` pass, and state what happened rather than what was expected: one
misattribution of a reasoned number as an observed one has already shipped in
this repository and had to be retracted.

## 8. Rejected alternatives

**A separate `01-dispositions/<pass>.json` per pass.** Keeps the partials purely
about the world model, and costs four `RunPaths` attributes, four
`STAGE_ARTIFACTS` entries and a second `writes` entry per skill. Rejected on one
argument: two documents can drift, and a repair that rewrites a part would leave
a stale disposition beside it that still validates. The name also collides in
meaning with triage's `00-dispositions/`, which holds admit/decline rulings on
candidates.

**A percentage floor on utilisation.** Rejected by measurement, not by taste:
33.6% is a healthy run for this corpus, so any floor above it fails run 2 as
well as run 1, and `check_claim_utilisation`'s docstring records the run where a
threshold would have failed a run whose reconcile was behaving.

**A `read_artifacts[]` self-report** — issue #6's own suggestion 1 in its
weakest form. A bare list of ids a pass claims to have read is prose about its
own compliance, the weakness the register already records for
`objective_review`. `own_kind_total` is the same idea with the one property that
makes it an instrument: the number is recomputable from the file it describes.

**Per-dropped-claim reasons.** Ruling 2. Strongest record, and the granularity a
human could actually overturn a drop at — reconsider it if gate 1 finds the
per-artifact note too coarse to rule on, which is a real possibility this design
accepts.

**Piloting on `rb-reconcile-goals` alone.** Considered seriously: goals is the
worst-measured pass, so one dispatch would test the design before four schemas
carry it. Rejected because the instrument then covers one pass of four while the
register gains an entry saying so, and the schema change in §3.1 has to land
across all of them regardless.

**Strengthening the read instruction.** Ruling 4.

## 9. Docs

- `docs/reference/artifacts.md` — `inputs_seen` on the four partials, `claims` on
  the three child elements.
- `docs/reference/cli.md` — `gate-brief`'s gate-1 surface gains the per-pass
  block; `tests/unit/test_docs_accuracy.py` fails until it agrees.
- `docs/design/limitations.md` — fold issue #6's measurement into the two
  variance entries, whose shared premise "nobody has yet run the same inputs
  twice and diffed the result" no longer holds for this family; add an entry for
  `rb-reconcile-gaps`' unmeasurable read coverage, and one for the two owed
  re-records.
- **No document under `docs/design/`, `docs/concepts/` or `docs/reference/` may
  cite this file.** `test_docs_accuracy.py` treats `docs/superpowers/` as
  recorded history and allows only `docs/README.md` to link it, so the register
  entries cite issue #6 and the code, never this spec.
