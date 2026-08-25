# Bounding `rb-triage-objective`: a catalogue projection in `00-slices.json`

**Date:** 2026-08-25
**Issue:** [#3](https://github.com/kaegis/rubrica/issues/3) — "A 351-candidate
catalogue is not triageable"
**Status:** design approved, plan not yet written

## 1. The problem

Issue #3 reports a real death: the monolithic `rb-triage` stage was dispatched
three times against the 595KB / 351-candidate `parsec` catalogue and never wrote
`00-triage.json` — once dying in context compaction, once exhausting its entire
dollar budget. The `triage-*` family was built in response, and for three of its
four passes the death is closed by construction.

**One pass still carries the whole mechanism.** `rb-triage-objective` is the only
skill in the repository whose `reads` names `catalogue`. Measured on a real
catalogue this session (tau2 + trajectories, the corpus from issue #4; `parsec`
itself lives on another machine, so these are the same shape at a smaller
scale):

| Issue #3's finding | Status on `triage-objective` |
|---|---|
| `Read` refuses the file whole at 256KB | **unchanged** — 472,799 > 262,144 |
| tail metadata sits in the last fraction of the file | **unchanged** — `run_id` at byte 470,054 of 472,799 |
| chunked reads do not help; every chunk lands in context | **unchanged for this pass** |
| 351 candidates in one dispatch | **closed** — 7 shards, largest 64,913 bytes |

The pass is instructed to use `request`, `policy`, `excluded`, `run_id`, and only
`candidate_id` + `bytes` per candidate. As the catalogue encodes them that is
**53,853 bytes, 11.4% of the file.** It must page through the other **418,946
(88.6%)**, of which **238,973 (50.5% of the file)** are candidate digests it is
explicitly forbidden to use — because a chunked `Read` cannot project columns,
and the dispatch harness grants only `Read` and `Bash(rubrica *)`.

So the issue changed shape. It was "the dispatch cannot hold the catalogue." It
is now "one pass reads 9× the bytes it needs, and the prohibition keeping it
bounded is prose nothing checks." The second half is not inference:
[`limitations.md`](../../design/limitations.md) records that inverting the
never-a-digest rule to *may read every digest* left the entire unit suite green
and `rubrica check-skills` exiting 0.

## 2. Rulings taken

Four decisions were made during brainstorming and are binding on the plan.

1. **Scope is the structural fix, and #3 closes on it.** The design makes the
   objective pass's input bounded and catalogue-free. It does **not** include
   dispatching the family. The close comment must say plainly that the fix is
   argued from arithmetic and shard measurement, not from an observed staged
   run — see §6.
2. **`excluded` crosses as a tally plus capped disputable paths**, not whole and
   not as a bare tally. §4.1 gives the rule.
3. **Contract enforcement only.** `catalogue` leaves `rb-triage-objective`'s
   `reads`. No per-stage `denyRead` is added to `scripts/dispatch-stage.sh`; its
   uniform-deny invariant and `test_dispatch_harness.py`'s derivation from
   `refs._readable_targets` are untouched.
4. **The projection lives in `00-slices.json`**, not in a new artifact kind.
   §8 records the two rejected alternatives and why.

## 3. Measured baseline and target

One consistent encoding throughout — what `write_json` puts on disk, verified
against the actual file:

| | bytes |
|---|---|
| `00-catalogue.json` | 472,799 |
| `00-slices.json` today (7 slices, 443 candidates) | 29,658 |
| `00-slices.json` with the projection | **51,792** |
| the projection's own share | 22,134 |
| all seven shards together | 470,455 |

**9.13× less for the objective dispatch to read, and it fits one `Read`.**

Projection components:

| field | bytes | note |
|---|---|---|
| `candidate_bytes` | 18,204 | 41.1 b/candidate over 443 candidates |
| `excluded` (summarised) | 1,062 | against 12,914 whole; 11 of 134 entries kept |
| `request` | 303 | verbatim |
| `policy` | 349 | verbatim |

At `DEFAULT_MAX_CANDIDATES = 500`, `candidate_bytes` is ~20,550 bytes. With the
`excluded.entries` budget of §4.1 full, the projection's ceiling is ~30KB. The
pass's input is therefore bounded by `max_candidates` — the count guard issue #3
correctly called useless as a context guard becomes sufficient once digests are
out of reach.

## 4. Design

### 4.1 The projection's shape

`00-slices.json` gains exactly one top-level key. `canonical_bytes` sorts keys,
so the document's order becomes `cap_bytes`, `catalogue_projection`, `run_id`,
`schema_version`, `slices` — the projection and `run_id` both land in the first
bytes and the large array stays last. Issue #3's tail-metadata seek is eliminated
as a consequence of the existing sort, not as a special case.

```json
"catalogue_projection": {
  "request": { },
  "policy":  { },
  "excluded": {
    "total": 134,
    "by_reason": {"binary": 123, "duplicate": 11},
    "entries": [{"path": "...", "reason": "duplicate", "detail": "..."}],
    "entries_truncated": false
  },
  "candidate_bytes": {"<candidate_id>": 12345}
}
```

**Name.** `catalogue_projection`, because it is a projection and must not read as
a claim to *be* the catalogue. `catalogue_head` — issue #3's own word — was
rejected because `candidate_bytes` is per-candidate and "head" would undersell
it. Verbose-and-exact matches the house style (`skeleton_nodes_truncated`,
`predicted_surface_count`, `check_contradiction_parts`).

**`request` and `policy`** are copied verbatim from the catalogue. This is not a
new pattern: `write_slices`' docstring already argues at length for the shards
carrying `request`/`policy` verbatim rather than each member re-seeking a
sorted-keys catalogue for two small fields. The projection extends that argument
one document over.

**`candidate_bytes`** maps `candidate_id` to that candidate's own catalogue
`bytes` — the source file's size on disk. It covers **every** catalogue
candidate, admissible or not, because `plan_slices` partitions every candidate
and a surface's `evidence` may name any of them. A map rather than a list of
objects: measured at 41.1 b/candidate against 80.1 for the list form.

**`excluded`** is summarised, and the rule has three parts.

*The tally.* `total` is the length of the catalogue's `excluded`. `by_reason`
carries one key per reason that actually occurs, sorted — not all eight enum
values — so a corpus with one exclusion reason does not carry seven zeroes.

*Which entries keep their paths.* Four of the eight `exclusion_reason` values
embed a judgment that could be wrong, and those are the ones an operator could
plausibly dispute at gate 0: `operator_excluded` (a `--exclude` may have
over-reached), `unreadable` (permissions), `duplicate` (a near-duplicate that is
not one), `vendored` (heuristic detection). The other four — `gitignored`,
`vcs_metadata`, `binary`, `lockfile` — are mechanical facts about a file with no
scoping decision in them. On tau2 this keeps all 11 `duplicate` entries and drops
123 `binary` paths: 1,062 bytes against 12,914.

*The cap is a byte budget, not a count.* Entries are taken in catalogue order and
the block stops before the entry that would push `canonical_bytes(entries)` past
**8,192 bytes**. `entries_truncated` is then `true`.

The budget is a byte budget deliberately, and the reason is a defect currently
open against this repository. Issue #8 is exactly a count cap without a character
bound: `digest`'s `names` is capped at 64 entries and unbounded in characters, so
a verbose tool name makes `survey` exit 2 on a row that used to be small. Paths
vary in length far more than tool names do, so a count cap here would reproduce
that defect in a new place. Truncating a path is not an alternative — a mangled
path cannot be disputed — so the block is bounded rather than its contents.

`entries_truncated` is an **unconditional sibling** of `entries`, present as
`false` when the budget did not bite, following `role_keys_truncated` and
`skeleton_nodes_truncated`. The convention those follow is the reason: a
truncation a prompt can see is a fact about the input, and one it cannot see is a
lie about it.

An empty `excluded` yields `total: 0`, `by_reason: {}`, `entries: []`,
`entries_truncated: false`.

**Not in scope:** the shards. They already carry `request` and `policy`, and
their members read full candidate records including digests, so they need no
`candidate_bytes`. `00-slices/<id>.json` is unchanged by this design.

**Schema.** `slices-0.1.json` gains `catalogue_projection` in `properties` and in
`required`, with `additionalProperties: false` preserved at every level.
`schema_version` stays `"0.1"`: there is no committed slices plan anywhere in the
repository, every plan is generated by code, and `build_toy_run` regenerates, so
a required field costs no migration.

### 4.2 The writer

`slices.write_slices` already reads the whole catalogue with no dispatch budget
and already validates the three top-level fields it reads bare. It gains the
projection.

`excluded` joins `run_id`, `request` and `policy` in the missing-field guard.
That guard raises `UsageError` — exit 2 — because a malformed catalogue cannot be
fixed by retrying the stage, and the message must name the catalogue rather than
this stage: the defect is in the artifact `triage-slices` was handed. `excluded`
is already `required` in `catalogue-0.1.json`, so this is a precondition on a
field the schema guarantees, exactly as the other three are.

Idempotence is unchanged and remains load-bearing: a human adopting a projection
at gate 0 mutates the catalogue and the plan must be mintable again from scratch,
byte-identically for identical input.

### 4.3 The gates

The precedent already in `refs.check_slices` is sharp, and both halves were
verified: **derived numbers are recomputed** (check 5 recomputes `slices[].bytes`
from the shard via `row_bytes`), and **verbatim copies are not** (nothing
verifies the shards' existing `request`/`policy` against the catalogue). The
projection follows that same line rather than inventing a second standard.

`check_slices` gains two checks.

**`candidate_bytes` has exactly one entry per catalogue candidate, each equal to
that candidate's `bytes`.** This is mandatory, not tidiness. `check_objective`
recomputes `weight.bytes` from `00-catalogue.json`; a drifted projection would
make the objective pass's *correct* arithmetic surface as a finding against
`00-objective.json`. That is the exit-code contract's third rule — a `1` naming
the wrong artifact — and it is the failure this repository already took over an
unreadable `01-claims/`, where four fabricated `no such claim` findings were
reported against a correct world model.

**`excluded.total` and `excluded.by_reason` are recomputed** from the catalogue's
`excluded`.

Not verified: `request`, `policy`, and `excluded.entries` — verbatim copies, the
same standing the shards' copies already have.

Both new checks **skip** when the catalogue is absent or unreadable, reusing the
existing `known_ids is None` branch rather than reporting every entry as wrong.
This is not a new guard; it is the same one, and it is the `01-claims/` lesson.

`check_objective` is **unchanged**. It keeps recomputing `weight.bytes` from the
catalogue, which is the source of truth about the corpus, and `refs.py` is code
with no dispatch budget so reading the catalogue costs it nothing.

One consequence is stated rather than hidden: a drifted projection produces
findings against *both* artifacts — `check_slices` naming `00-slices.json` and
`check_objective` naming `00-objective.json`. Both statements are true.
`check_slices`' is the actionable root cause. Coupling the two checkers to
suppress the second was considered and rejected as over-engineering for a state
that only a `triage-slices` defect can produce.

### 4.4 The skill contract and prose

`rb-triage-objective/SKILL.md`:

**Contract:** `reads = ["slices"]`.

**§1 Inputs** is rewritten around one file. The paragraph explaining that
`candidates[]` is read for two scalar fields is replaced by the projection. The
argument carrying the boundedness case — *"a pass that reads the corpus to size
the corpus grows with it"* — survives verbatim in meaning, because it is the
reason the projection exists. What changes is that the contract now backs it.

**The prohibition is restated where it now lives.** Invariant 1 becomes "You read
`00-slices.json` and nothing else", and `00-catalogue.json` moves from the list of
what the pass reads into the list of what it must not. The shard prohibition,
which Invariant 1 already carries, becomes the load-bearing one, and §1 states
why in terms that keep it from being decorative: the seven shards total 470,455
bytes, reading one is reading a sibling's slice, and `scripts/audit-reads.sh`
sees it.

**One new risk the move creates.** `slices[].bytes` is row bytes — the metric
that saturates under `digest.py`'s 128-node skeleton clamp — and
`catalogue_projection.candidate_bytes` is source bytes, which is what
`weight.bytes` requires. Those two now sit **in the same file**, where before the
wrong metric was in the plan and the right one was in the catalogue. §2 and
Invariant 2 therefore name both fields explicitly, say which is which, and say
why the wrong one is wrong. `refs.check_objective` still gates this
deterministically, so the prose is belt-and-braces — but the belt became easier
to grab by the wrong end, so it gets sharpened rather than merely preserved.

**§2** reads `run_id` from `00-slices.json`'s `run_id`, which sits ahead of
`slices[]` under sorted keys.

**§5 gains one refusal condition:** *refuse if any `candidate_id` in `slices[]`
has no entry in `candidate_bytes`.* It earns its place by this repository's own
three-part test — its trigger is detectable from what the pass reads, its action
is one a model can take (write nothing, report what was found), and it is not
covered elsewhere from the pass's point of view. It is a `triage-slices` defect,
and computing a surface weight with a silently-missing term would understate
evidential weight in the one field a human reads to compare surfaces.

The honest-limitation paragraph — `supported` ruled from a map, never from the
digests those counts summarize — survives unchanged in meaning and becomes
stronger: the pass now cannot reach a digest without leaving its contract.

## 5. What this does not fix

Recorded here because the issue comment and `limitations.md` must both say it.

**The escape hatch moves; it does not close.** `00-slices.json` carries no
digests, but the shards under `00-slices/` carry full candidate records totalling
470,455 bytes — essentially the whole catalogue. A dispatch that read all seven
would be as unbounded as today's. What improves is the *status* of that read, not
its availability: reading the catalogue is in-contract today, so nothing can call
it a violation, whereas reading a sibling's shard is out-of-contract, breaks the
fan-out isolation rule, and a read audit catches it. "Auditable violation" is a
real gain over "in-contract expense" and it is not the same as "impossible."

**The family still has no dispatch.** `limitations.md` records that every number
the staged design was argued from is arithmetic over catalogues that already
existed, and this design adds more arithmetic to that pile. Nobody has watched a
staged run write `00-triage.json` on the corpus that killed the monolith. Ruling
1 closes #3 anyway, on the grounds that the validation gap has its own recorded
home and is not lost by closing the issue — but the close comment states it.

**`supported` is still ruled from a map.** Unchanged by this design and still a
real blind spot. `predicted_surface_count` remains the instrument.

## 6. Tests

Two existing pins move: `test_skills_triage_family.py:132` (`reads`
set-equality) and `:896` (the run_id source, `00-catalogue.json` →
`00-slices.json`).

New coverage by file:

- **`test_slices.py`** — the projection is present; `candidate_bytes` covers
  every catalogue candidate at the right value, including inadmissible ones;
  `by_reason` carries only reasons that occur; `entries` holds exactly the four
  disputable reasons and no others; the 8,192-byte budget stops filling and sets
  `entries_truncated`; an empty `excluded` produces the zero shape; the plan is
  byte-identical on re-run.
- **`test_refs_slices.py`** — both new checks, **each measured in both
  directions**, plus its own test that an absent or unreadable catalogue leaves
  them silent. That last one is the `01-claims/` guard and it must be watched
  failing before it is trusted.
- **`test_schemas_triage.py`** — `catalogue_projection` required under
  `additionalProperties: false`; a plan without it fails layer 1.
- **`tests/toy.py`** — no fixture edits. `build_toy_run` regenerates plans
  through code; `test_toy_triage_checkpoints.py` must stay green unchanged.

Every new predicate is measured in both directions before commit, per
`CLAUDE.md`: blank or invert the thing it checks in a `/tmp` copy under
`RUBRICA_SKILLS_DIR` and confirm red, then restate meaning-preservingly and
confirm green.

Any new **text-level** predicate about the skill's prose uses the **windowed
co-occurrence** form scoped by `skills.section_body`, never a bare substring.
This is not a style preference: `limitations.md` records fourteen predicates in
this exact module measured vacuous by inversion, and records that windowing was
the shape that went red where its unwindowed twin stayed green.

## 7. Docs

Four places, all enforced by `tests/unit/test_docs_accuracy.py`:

- `docs/concepts/pipeline.md:29` — the `triage-objective` stage-table row, whose
  input column reads `00-slices.json`, `00-catalogue.json`.
- `docs/reference/artifacts.md`, the `slices` section — "Read by", and
  "Fields worth knowing" gains the projection.
- `docs/reference/artifacts.md`, the `objective` section — states today that the
  record is "built from `00-slices.json` and `00-catalogue.json` alone", and its
  `weight.bytes` note points at the catalogue field.

`docs/design/limitations.md` gets three edits:

- **"`supported` is ruled from a corpus map, not from the digests"** asserts the
  pass "reads no digest at all" — aspirational today, true after this change.
- **The unchecked-prohibition entry** gets the honest update from §5: the
  prohibition moved to the shards and its status improved from in-contract to
  auditable, rather than being resolved.
- **A new entry** records what closing #3 on this leaves owed — that the family
  still has no dispatch, so this fix too is argued from arithmetic.

## 8. Rejected alternatives

**A separate `00-catalogue-head.json`** — issue #3's own direction 1. Cleaner
separation, but it adds an artifact *kind*: a `paths.RunPaths` attribute, a
`validate.STAGE_ARTIFACTS` entry, a schema file, a `check-skills` name, an
`artifacts.md` section and a `test_docs_accuracy.py` update — for a projection of
22KB that the pass reads alongside the plan anyway.

**Reordering the catalogue's own keys** so the head sits at byte 0 — also
direction 1. Rejected on measurement before the risk even applies: it fixes the
*seek*, which is 0.5% of the file, and does nothing about the 88.6% of bytes the
pass must page through, because `candidates` is 455KB in the middle either way.
The risk is real too — `canonical_bytes` is what `survey` and `intake` hash
exploded elements with, and two spellings of the canonical form would make every
exploded input's sha256 mismatch after materialisation — but the arithmetic alone
disqualifies it.

**A sandbox `denyRead` on the catalogue for the objective dispatch.** Would make
boundedness OS-enforced rather than auditable, and is safe by the harness's own
rule: `dispatch-stage.sh:191` permits denying only what `check-refs` never looks
at, and this dispatch invokes `validate` alone, whose `triage-objective` entry
reads `00-objective.json`. Excluded by ruling 3 to keep this change out of the
dispatch harness. Available later as its own change.

## 9. Verification

The three gates:

```sh
make test && make check && uv run rubrica check-skills
```

Then the end-to-end measurement, which is the actual claim. Against a real
catalogue:

```sh
uv run rubrica triage-slices --run "$RUN"
uv run rubrica validate --run "$RUN" --stage triage-slices   # exit 0
uv run rubrica check-refs --run "$RUN"                       # exit 0
```

Asserted rather than eyeballed, on the tau2 catalogue of §3:

- `00-slices.json` is ~51,792 bytes, **under the 262,144-byte whole-file `Read`
  ceiling**, against 472,799 for the catalogue — a 9.13× reduction in what the
  objective dispatch reads.
- `catalogue_projection.candidate_bytes` has 443 entries, one per catalogue
  candidate, each equal to that candidate's `bytes`.
- `catalogue_projection.excluded` is `{total: 134, by_reason: {binary: 123,
  duplicate: 11}, entries: <11 duplicate entries>, entries_truncated: false}`.
- The seven slices and their shards are **unchanged** from before this design —
  `slices[]`, the shard files and their bytes are byte-identical, because nothing
  here touches partitioning.
- `rb-triage-objective`'s contract `reads` is exactly `["slices"]`, and
  `rubrica check-skills` exits 0.
