# Phased trace deferral Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third triage disposition, `defer`, and the run-level `phase`
declaration that drives it, so a run can reach a sealed world model without
extracting its most expensive input kind.

**Architecture:** One operator flag on `triage-slices` declares the phase. It is
carried down the pipeline as an artifact field only — plan → triage record →
manifest → world model — with no conversational channel and no second
declaration site. Deferred candidates are subtracted from the dispatch shards, so
no prompt is asked to apply the policy and three of eleven fan-out members are
never dispatched at all. `triage-seal` synthesises the `defer` ruling for each so
every catalogue candidate is still ruled on the record.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `ruff`, JSON Schema (draft 2020-12,
`jsonschema` + `referencing`).

**Spec:** [`docs/superpowers/specs/2026-09-14-phased-trace-deferral-design.md`](../specs/2026-09-14-phased-trace-deferral-design.md)

---

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** If signing fails, stop
  and report it. Never fall back to unsigned, never work around it.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`. Never `Co-Authored-By` or `Made-with`. Order the
  trailers with `Assisted-By` **before** `Signed-off-by`.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. `docs/` is
  excluded; `README.md` and `CLAUDE.md` are **not**.
- The three gates, all of which must hold at the end of every task:
  `uv run pytest -q`, `uv run ruff check && uv run ruff format --check`, and
  `uv run rubrica check-skills` exiting 0.
- **Exit codes are load-bearing.** `0` clean; `1` findings, one per line on
  stdout, never empty; `2` usage error or an unreadable/misconfigured run. A
  stage defect must never surface as `2`; a `1` must never have empty stdout; a
  `1` must name the *right* artifact.
- **Artifacts on disk are the only channel between stages.** No new field may be
  threaded through a dispatch as conversational context.
- Comment density in this repo is high and deliberate: comments explain *why*,
  usually citing a measurement. Match it. Do not strip existing comments.
- Do not write a test count anywhere. Do not add a heading that counts something
  that grows. Do not cite the dated build-record tree.
- Never hand-edit `docs/concepts/pipeline-diagram.html` or
  `docs/assets/how-it-works*.svg`; they are generated.

---

## Three deviations from the spec, and why

These are resolved decisions, not open questions. Each was measured against the
code before this plan was written.

### 1. The phase is declared at `triage-slices`, not at `intake`

The spec says `rubrica intake ... --phase 1 --defer-kind trace` and names
`triage-slices` as a consumer of `manifest.phase`. That cannot work:
`paths.STAGES` puts `triage-slices` at index 1 and `intake` at index 6, and
`manifest.json` does not exist until `intake` mints it after gate 0. A consumer
cannot read a file written five stages later.

So the flags move to `triage-slices`, the first stage that needs them, and the
block propagates as an artifact field at each hand-off:

    triage-slices --phase 1 --defer-kind trace
      -> 00-slices.json      .phase                (rb-triage-objective reads it)
      -> 00-triage.json      .phase                (triage-seal carries it)
      -> manifest.json       .phase                (intake carries it, adds deferred_count)
      -> 01-world-model.json .phase                (reconcile-seal carries it)

One declaration site, four verbatim carries. `intake` gains no flags, which also
removes the failure mode of two declaration sites disagreeing about what the run
deferred. Re-running `triage-slices` with a different `--defer-kind` is how a
human at gate 0 reverses the decision — cheap, because it is code.

### 2. Two more call sites need changing than the spec's audit found

The spec's claim that **eight** `disposition == "admit"` call sites need no
change is correct as far as it goes; all eight were verified at
`intake.py:571`, `refs.py:1582`, `seal.py:444/472/514`, `brief.py:917/1224` and
`summary.py:564`. But three sites branch on an admit/decline *dichotomy* rather
than on `== "admit"`, and a third disposition falls through the crack:

- **`refs.py:1158` (`check_triage`) — a false finding, and a masked one.** The
  branch is `if disposition == "decline": ... else: admits += 1; if code:
  report("reason_code names a decline; an admit has none")`. A `defer` carrying
  `reason_code: deferred_to_phase` takes the `else`, so `check-refs` exits `1`
  with a fabricated finding against a correct record — the exit-code contract's
  third rule breached. It also counts every defer toward `admits`, which masks
  the empty-admitted-set scoping failure fifty lines below: a run that admitted
  nothing and deferred everything would read as clean. **Task 1 fixes this.**
- **`summary.py:564` and `brief.py:1224`/`1247` — silent omission.** Both bucket
  into admits and declines-by-reason-code and drop anything else. Sixty-eight
  deferred inputs would be absent from the gate-0 brief and the run-summary page
  with nothing saying so. The spec's own argument against collapsing `defer` into
  `decline` — that it would tell the operator 68 inputs were judged useless —
  applies at least as strongly to telling them nothing at all. **Task 6 fixes
  this.**

Two further checker clauses fire against deferred candidates and are handled in
Task 2: `refs.check_disposition_parts` clause 1 (every slice has a part on disk)
and clause 4 (the union of parts and adoptions covers the catalogue).

### 3. A synthesised `defer` carries no `priority`

The spec says a deferred candidate "keeps its `priority`, so phase 3 consumes
triage's ranking directly instead of recomputing it." Under this plan no
`rb-triage-rule` member ever sees a deferred candidate — they are subtracted from
the shards — so there is no ranking to keep. Inventing one in code would be a
reasoned number presented as an observed one, which this project forbids.

This is not a loss against the spec's own design, which delivers the promise for
at most the mixed slices: on the measured corpus, 15 of 68 deferred candidates
sit in `s04` and the other 53 are in slices no member is dispatched for at all.
Phase 3 re-slices the deferred population and dispatches `rb-triage-rule` over
it, which is the pass whose judgment ought to rank inputs. `priority` is optional
in `triage-0.1.json` and `seal._member_priority` already sorts an absent one at
a sentinel rank, so nothing needs to tolerate this specially. Task 9 records it
in `docs/design/limitations.md`.

### What this buys, beyond the spec

Because deferred candidates never reach a shard, **`rb-triage-rule` needs no
edit at all.** The spec gives it "one instruction, for mixed slices only." A
prompt instruction is a prompt-compliance risk on the pass that decides what the
run can ever know; subtraction makes the policy mechanical instead. It also makes
the mixed slice `s04` cheaper to dispatch (5 candidates, not 20), which the
spec's design does not.

---

## File Structure

**New:**

- `src/rubrica/phase.py` — the phase block's one reader and the one place a
  deferred candidate is resolved from a kind. Written by four stages and read by
  six; a second spelling of "is this candidate deferred" would let two of them
  disagree about what the run can know.
- `tests/unit/test_phase.py` — `phase.py` in isolation.
- `tests/unit/test_phase_pipeline.py` — the carry chain end to end: plan →
  triage record → manifest → world model, plus the checkers over each.

**Modified:**

| File | Responsibility of the change |
|---|---|
| `src/rubrica/schema/triage-0.1.json` | `defer` in the disposition enum; `deferred_to_phase` in `decline_reason`; `policy` in `authority`; `$defs/phase`; top-level `phase` |
| `src/rubrica/schema/slices-0.1.json` | top-level `phase`; per-slice `deferred_candidate_ids`; `bytes` re-described |
| `src/rubrica/schema/manifest-0.1.json` | top-level `phase` |
| `src/rubrica/schema/world-model-0.1.json` | top-level `phase` |
| `src/rubrica/validate.py` | `catalogue_candidate_kinds()`, `--defer-kind`'s argparse choices |
| `src/rubrica/slices.py` | `write_slices(..., phase=)`; subtract defers from shards; skip a fully-deferred shard |
| `src/rubrica/cli.py` | `--phase`/`--defer-kind` on `triage-slices` |
| `src/rubrica/refs.py` | `check_triage`'s third branch; `check_slices` clauses 4/5/6; `check_disposition_parts` clauses 1/4; `check_admitted_inputs`' deferred-count clause |
| `src/rubrica/seal.py` | synthesise the defer rulings; carry `phase` into `00-triage.json` |
| `src/rubrica/intake.py` | carry `phase` into `manifest.json`, adding `deferred_count` |
| `src/rubrica/reconcile.py` | carry `phase` into `01-world-model.json` |
| `src/rubrica/brief.py` | gate 0's defers block; gate 1's incompleteness note |
| `src/rubrica/summary.py`, `summary_html.py` | a third disposition bucket and its table |
| `src/rubrica/target_brief.py`, `target_brief_html.py` | the incompleteness banner, in the recipient's vocabulary |
| `src/rubrica/skills/rb-triage-objective/SKILL.md` | the objective pass learns deferred material is not absent material |
| `src/rubrica/skills/rb-orchestrate/SKILL.md` | skip the two passes under a phase |
| `docs/concepts/pipeline.md`, `docs/reference/cli.md`, `docs/reference/artifacts.md`, `docs/design/limitations.md`, `CLAUDE.md` | documentation the accuracy tests gate |

**Deliberately not modified:** `src/rubrica/skills/rb-triage-rule/SKILL.md` (see
deviation 3's closing note), `tests/fixtures/toy/` (the golden world is the model
answer a skill imitates; deferring `trace` there would break claims the toy world
model cites), and `tests/toy.py`'s `build_toy_run` signature (phase runs are
built by the new test modules from their own catalogues).

---
### Task 1: `phase.py`, the `defer` disposition, and `check_triage`'s third branch

The foundation: the schema learns the value, one module owns resolving it, and
the checker that would have fabricated a finding against it stops doing so.
Nothing writes a `defer` yet — this task's tests build the records by hand, which
is the only way to test the checker independently of the writer.

**Files:**
- Create: `src/rubrica/phase.py`
- Create: `tests/unit/test_phase.py`
- Modify: `src/rubrica/schema/triage-0.1.json` (`$defs` at lines 50-100, top-level `properties`)
- Modify: `src/rubrica/validate.py:192-219` (add `catalogue_candidate_kinds` beside `manifest_stage_efforts`)
- Modify: `src/rubrica/refs.py:1155-1192` (`check_triage`'s disposition branch)
- Test: `tests/unit/test_refs_triage.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `phase.DEFER = "defer"`, `phase.DEFER_REASON_CODE = "deferred_to_phase"`,
    `phase.POLICY_AUTHORITY = "policy"` — the three literals, one home each.
  - `phase.read(document: object) -> dict | None` — the `phase` block of any
    artifact that carries one, or `None`.
  - `phase.deferred_kinds(block: dict | None) -> frozenset[str]`
  - `phase.deferred_candidate_ids(candidates: list, block: dict | None) -> frozenset[str]`
  - `validate.catalogue_candidate_kinds() -> tuple[str, ...]`

- [ ] **Step 1: Write the failing test for `phase.py`**

Create `tests/unit/test_phase.py`:

```python
"""phase.py in isolation: the block reader and the kind resolver.

Every predicate here is measured in both directions, which is this repo's rule
for a guard. The negative controls are the second half of each test rather than
a separate module, because a resolver that returns everything and one that
returns nothing both pass a one-directional check.
"""

from __future__ import annotations

from rubrica import phase


def test_read_returns_none_for_every_shape_that_is_not_a_phase_block():
    """A run that declared no phase, and the malformed shapes an unvalidated
    artifact reaches this function with. `read` is called by six consumers before
    layer 1 has necessarily run over the document, so a non-dict document and a
    non-dict `phase` must both answer None rather than raising -- an exception
    escaping here would surface a missing optional field as exit 1 with empty
    stdout."""
    assert phase.read({}) is None
    assert phase.read(None) is None
    assert phase.read(7) is None
    assert phase.read("phase") is None
    assert phase.read([{"phase": {"number": 1}}]) is None
    assert phase.read({"phase": None}) is None
    assert phase.read({"phase": 1}) is None
    assert phase.read({"phase": ["trace"]}) is None


def test_read_returns_the_block_when_one_is_declared():
    block = {"number": 1, "deferred_kinds": ["trace"]}
    assert phase.read({"phase": block}) == block


def test_deferred_kinds_is_empty_without_a_block_and_ignores_non_strings():
    """The empty answer is what makes every consumer's no-phase path the
    behaviour the project had before phasing existed: an empty set defers
    nothing, so `deferred_candidate_ids` returns nothing and every writer's
    output is byte-identical to today's."""
    assert phase.deferred_kinds(None) == frozenset()
    assert phase.deferred_kinds({"number": 1}) == frozenset()
    assert phase.deferred_kinds({"number": 1, "deferred_kinds": []}) == frozenset()
    assert phase.deferred_kinds({"number": 1, "deferred_kinds": "trace"}) == frozenset()
    assert phase.deferred_kinds({"number": 1, "deferred_kinds": ["trace", 7, None]}) == frozenset(
        {"trace"}
    )


def test_deferred_candidate_ids_selects_by_kind_and_only_admissible_candidates():
    """Three populations in one catalogue, and the third is the one worth a test
    of its own. A container carrying a deferred kind is `admissible: false` -- its
    elements are the candidates -- so deferring it would hand phase 3 an input to
    admit that was never admissible in the first place. It is left for a member to
    decline instead, which is what happens today."""
    candidates = [
        {"candidate_id": "t1", "kind": "trace"},
        {"candidate_id": "t2", "kind": "trace", "admissible": True},
        {"candidate_id": "src", "kind": "source_code"},
        {"candidate_id": "bundle", "kind": "trace", "admissible": False},
    ]
    block = {"number": 1, "deferred_kinds": ["trace"]}
    assert phase.deferred_candidate_ids(candidates, block) == frozenset({"t1", "t2"})
    # The negative control: no block defers nothing, which is the pre-phasing
    # behaviour every writer falls back to.
    assert phase.deferred_candidate_ids(candidates, None) == frozenset()
    # And a kind no candidate carries selects nothing rather than raising.
    assert (
        phase.deferred_candidate_ids(candidates, {"number": 1, "deferred_kinds": ["design_doc"]})
        == frozenset()
    )


def test_deferred_candidate_ids_tolerates_a_candidates_list_that_is_not_one():
    """`slices.write_slices` guards the catalogue's shape before it calls this,
    but `brief` and `summary` read the same catalogue on the exit-0 report path
    where nothing has. A non-list, and a list of non-dicts, must answer empty."""
    block = {"number": 1, "deferred_kinds": ["trace"]}
    assert phase.deferred_candidate_ids(None, block) == frozenset()
    assert phase.deferred_candidate_ids("trace", block) == frozenset()
    assert phase.deferred_candidate_ids([None, 7, {"kind": "trace"}], block) == frozenset()
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_phase.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rubrica.phase'`

- [ ] **Step 3: Write `src/rubrica/phase.py`**

```python
"""The run's phase declaration, and the one place a deferred candidate is resolved.

Phasing exists so a benchmark-ready world model is reachable in hours rather than
a day: the corpus's most expensive input kind is deferred to a later phase instead
of dropped. The measurement is in
`docs/superpowers/specs/2026-09-14-phased-trace-deferral-design.md` -- on the run
that motivated it, `trace` inputs were 78% of the corpus by bytes and 12% cited,
and were the majority source for exactly the two world-model outputs the benchmark
never reads. Of the 113 capabilities carrying a tool binding -- the drivable ones
the coverage denominator counts -- zero depended on a trace.

One module because the block is written by four stages (`triage-slices`,
`triage-seal`, `intake`, `reconcile-seal`) and read by six more, and a second
spelling of "is this candidate deferred" would let two of them disagree about what
the run can ever know. Nothing downstream of `intake` reads the corpus again, so
that disagreement is unrecoverable rather than merely wrong.

Every function here answers rather than raises. Five of the readers are on the
exit-0 report path (`gate-brief`, `run-summary`, `target-brief`) or run before
layer 1 has necessarily validated the document, and an exception escaping this
module would turn a missing optional field into exit 1 with empty stdout -- the
exit-code contract's second rule, and the whole class `findings.py` exists to
prevent.
"""

from __future__ import annotations

# The three literals the disposition contract adds, one home each. `defer` was
# three separate string constants in the first draft of this work and a partial
# rename is what makes a checker accept a value no writer produces -- the same
# argument `skills.SKILL_PREFIX` carries for the `rb-` prefix.
DEFER = "defer"
DEFER_REASON_CODE = "deferred_to_phase"

# The authority a code-written ruling carries. `triage` would attribute a policy
# flag's mechanical consequence to a prompt's judgment, and `human` would claim a
# person ruled on each of 68 candidates one at a time; the whole point of a
# kind-level instrument is that nobody did.
POLICY_AUTHORITY = "policy"


def read(document: object) -> dict | None:
    """The `phase` block of an artifact that carries one, else None.

    Both container guards are load-bearing and both are reachable: a `document`
    that is not a mapping is every pre-phasing artifact read through
    `refs._load`, which returns whatever the file holds, and a `phase` that is
    not a mapping is a hand-edited run -- which gate 0 explicitly invites.
    """
    if not isinstance(document, dict):
        return None
    block = document.get("phase")
    return block if isinstance(block, dict) else None


def deferred_kinds(block: dict | None) -> frozenset[str]:
    """The kinds this phase defers, as a set of strings.

    Empty for `None`, which is what makes every consumer's no-phase path
    byte-identical to the behaviour this package had before phasing: an empty set
    defers no candidate, so every writer's output is unchanged. Non-string members
    are dropped rather than raised on, for the reason the module docstring gives --
    and dropping them is safe because a kind that is not a string cannot equal a
    candidate's `kind` anyway, so this narrows nothing layer 1 would have kept.
    """
    if not isinstance(block, dict):
        return frozenset()
    raw = block.get("deferred_kinds")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(k for k in raw if isinstance(k, str))


def deferred_candidate_ids(candidates: object, block: dict | None) -> frozenset[str]:
    """Which of `candidates` this phase defers.

    `admissible is False` candidates are excluded deliberately. Such a candidate
    is a container whose *elements* are the candidates, and `refs.check_triage`
    already reports an admit of one; deferring it instead would put a container on
    phase 3's list of inputs to admit, where the same finding would be waiting. A
    member declines it today and still does under a phase, because it stays in the
    shard.

    `admissible` absent means admissible -- the catalogue writes the key only to
    say False -- so the test is `is not False` rather than a truthiness check that
    would also exclude every candidate that omits it.
    """
    kinds = deferred_kinds(block)
    if not kinds or not isinstance(candidates, list):
        return frozenset()
    return frozenset(
        cid
        for c in candidates
        if isinstance(c, dict)
        and isinstance(cid := c.get("candidate_id"), str)
        and c.get("kind") in kinds
        and c.get("admissible") is not False
    )
```

- [ ] **Step 4: Run it to confirm it passes**

Run: `uv run pytest tests/unit/test_phase.py -q`
Expected: PASS

- [ ] **Step 5: Extend the triage schema**

In `src/rubrica/schema/triage-0.1.json`, make four edits.

The disposition enum and its reason code (currently lines 96-99):

```json
        "disposition": {"enum": ["admit", "decline", "defer"]},
        "reason_code": {"$ref": "#/$defs/decline_reason"},
```

`decline_reason` gains the defer code (currently lines 56-60). The `$defs` name is
left alone on purpose: renaming it would touch every `$ref` for a rename that buys
nothing, and the description below is where the widening is recorded.

```json
    "decline_reason": {
      "description": "Why a candidate was not admitted. Named for the decline case it was built for and deliberately not renamed -- every $ref to it would move for no gain -- but `deferred_to_phase` is a *defer*'s code and never a decline's, and refs.check_triage holds each disposition to its own half of this enum. The two make opposite promises: a decline says this input has no evidence value, a defer says it has value this phase cannot spend, and collapsing them would make triage-seal's counts and the gate-0 brief report that the deferred inputs were judged useless.",
      "enum": ["off_objective", "out_of_scope", "near_duplicate", "superseded",
               "implementation_detail", "no_evidence_value", "digest_insufficient",
               "needs_projection", "deferred_to_phase"]
    },
```

`authority` gains `policy` (inside `$defs/disposition`, currently line 101):

```json
        "authority": {
          "description": "Who ruled. `triage` is an rb-triage-rule member's judgment, `human` a person's at gate 0 or through adopt-projection, and `policy` the mechanical consequence of the run's own --defer-kind declaration: triage-seal writes those, and no member ever saw the candidate. Attributing a policy flag to `triage` would credit a prompt with a judgment it never made, and to `human` would claim somebody ruled on each deferred candidate one at a time -- which is exactly what a kind-level instrument exists to avoid paying for.",
          "enum": ["triage", "human", "policy"]
        }
```

A new `$defs/phase`, the one definition the other three artifacts `$ref`:

```json
    "phase": {
      "description": "The run's phase declaration: which numbered phase this is, and which candidate kinds it defers to a later one. Declared once on `triage-slices` and carried verbatim through 00-slices.json, 00-triage.json, manifest.json and 01-world-model.json, so a reader of any of the four learns what the run can never know without opening the other three. Defined here, in the artifact that owns the disposition it drives, and $ref'd by the other three rather than restated: `derive, do not restate` -- a duplicated block that fell behind would let the manifest and the world model disagree about which inputs the run read. Optional in all four documents, on max_scenario_part_bytes' precedent: making it required would invalidate every manifest already on disk, which diff-runs, run-summary and gate-brief all read. Absent means no phase was declared and the run behaves exactly as it did before phasing existed.",
      "type": "object",
      "required": ["number", "deferred_kinds"],
      "additionalProperties": false,
      "properties": {
        "number": {
          "type": "integer",
          "minimum": 1,
          "description": "Which phase this run is. A label, not an index into anything: phase 1 defers, phase 3 admits what phase 1 deferred, and nothing in the code branches on the number."
        },
        "deferred_kinds": {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": {"$ref": "#/$defs/kind"},
          "description": "The candidate kinds this phase defers, held to the catalogue's own kind enum so a declaration cannot name a kind no candidate can carry. minItems 1 because a phase deferring nothing is a phase nobody declared, and the absent block already says that."
        },
        "deferred_count": {
          "type": "integer",
          "minimum": 0,
          "description": "How many candidates were actually deferred. Written by `intake` into the manifest and carried into the world model; absent from 00-slices.json and 00-triage.json, where the deferred set is enumerated in full and a count beside it would be a second spelling of a length. refs.check_admitted_inputs recomputes it from 00-triage.json's own defer dispositions, so it is arithmetic a reader can check rather than testimony -- the discipline check_slices' `bytes` clause already holds."
        }
      }
    },
```

And the top-level `properties` gains the optional field (beside `projections`):

```json
    "phase": {"$ref": "#/$defs/phase"}
```

- [ ] **Step 6: Add `catalogue_candidate_kinds()` to `validate.py`**

> **Correction, made during execution.** As first written this step read
> `ARTIFACT_SCHEMAS["triage"]`'s `$defs/kind` and named the function
> `triage_candidate_kinds`. That was wrong: `--defer-kind` selects *catalogue*
> candidates by the `kind` that `catalogue-0.1.json` validates, and that file
> carries its own copy of the enum with nothing pinning the two equal. A kind
> added to the catalogue's copy alone would hand `--defer-kind` a choice list
> that rejects it — the "silently defers nothing while the run pays in full"
> failure this very function's docstring calls the worst available, reached
> through the restated copy that `derive, do not restate` exists to forbid.
> The shipped code reads the catalogue schema, `$defs/phase.deferred_kinds`
> `$ref`s `catalogue-0.1.json#/$defs/kind`, and triage's own `$defs/kind`
> stays for projections. The code block below shows the corrected form; the
> ruling is in the ledger.

Insert immediately after `manifest_stage_efforts` (after line 219), mirroring its
two-function cached shape exactly:

```python
@functools.cache
def _catalogue_candidate_kinds(schema_root: Path) -> tuple[str, ...]:
    """The cached half of catalogue_candidate_kinds, keyed on schema_root.

    Keyed on the root for _manifest_stage_efforts' reason: a zero-argument
    @functools.cache would pin the first schema the process ever read, and
    parser construction happens on every CLI invocation, so there always is an
    earlier call for a RUBRICA_SCHEMA_DIR override to lose to.
    """
    schema = read_json(schema_root / ARTIFACT_SCHEMAS["catalogue"])
    return tuple(schema["$defs"]["kind"]["enum"])


def catalogue_candidate_kinds() -> tuple[str, ...]:
    """The candidate kinds a catalogue can carry, read out of the active schema.

    The *catalogue's* copy of the enum, not triage's. Both files carry one and
    they are byte-identical today, but `--defer-kind` selects catalogue
    candidates by the `kind` catalogue-0.1.json validates, so that is the copy
    this must agree with: a kind added there alone would leave this choice list
    rejecting a kind real candidates carry.

    `triage-slices --defer-kind` uses this as its argparse choices, so the CLI
    cannot accept a kind the schema will reject -- and there is no second copy of
    the enum to keep in step. A hand-typed list here would accept a `--defer-kind`
    that silently deferred nothing, which is the worst available failure: the run
    would cost full price and report a phase.
    """
    return _catalogue_candidate_kinds(schema_dir())
```

- [ ] **Step 7: Write the failing test for `check_triage`'s third branch**

Append to `tests/unit/test_refs_triage.py`. Read the module's existing helpers
first and reuse whatever it already has for building a triage record; the record
below is written out in full only where that module has no helper for it.

```python
def test_a_defer_is_neither_an_admit_nor_a_decline(tmp_path):
    """The branch this repo shipped before `defer` existed was `if decline: ...
    else: admits += 1`, and both halves of that `else` were wrong about a defer.

    Measured on the record below before the fix: `check-refs` reported
    "reason_code names a decline; an admit has none" against a correct triage
    record -- exit 1 naming the wrong defect, the exit-code contract's third rule
    -- and counted the defer toward `admits`, so a record admitting nothing and
    deferring everything passed the empty-admitted-set scoping check that exists
    to catch exactly that.
    """
    run = _run_with_triage(
        tmp_path,
        dispositions=[
            {
                "candidate_id": "src",
                "disposition": "admit",
                "reason": "declares the tool surface",
                "priority": 1,
                "authority": "triage",
            },
            {
                "candidate_id": "trace-json",
                "disposition": "defer",
                "reason_code": "deferred_to_phase",
                "reason": "trace is deferred in phase 1",
                "authority": "policy",
            },
        ],
        candidates=["src", "trace-json"],
    )
    assert refs.check_triage(run) == []


def test_a_defer_without_the_defer_reason_code_is_a_finding(tmp_path):
    """The other direction, so the clause above is a guard and not a hole. A defer
    carrying a *decline's* code is the shape that would let a stage smuggle a
    judgment ("no_evidence_value") in under a policy's label, and the finding names
    the reason_code pointer rather than the disposition because the code is the
    field that is wrong."""
    run = _run_with_triage(
        tmp_path,
        dispositions=[
            {
                "candidate_id": "src",
                "disposition": "admit",
                "reason": "declares the tool surface",
                "priority": 1,
                "authority": "triage",
            },
            {
                "candidate_id": "trace-json",
                "disposition": "defer",
                "reason_code": "no_evidence_value",
                "reason": "trace is deferred in phase 1",
                "authority": "policy",
            },
        ],
        candidates=["src", "trace-json"],
    )
    findings = refs.check_triage(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/dispositions/1/reason_code"
    assert "deferred_to_phase" in findings[0].message


def test_a_run_that_defers_everything_and_admits_nothing_is_still_a_scoping_failure(tmp_path):
    """The masked check, unmasked. Before the third branch existed the defer below
    incremented `admits`, so this record -- which admits not one candidate -- read
    as clean."""
    run = _run_with_triage(
        tmp_path,
        dispositions=[
            {
                "candidate_id": "trace-json",
                "disposition": "defer",
                "reason_code": "deferred_to_phase",
                "reason": "trace is deferred in phase 1",
                "authority": "policy",
            },
        ],
        candidates=["trace-json"],
    )
    messages = [f.message for f in refs.check_triage(run)]
    assert any("no candidate was admitted" in m for m in messages)
```

If `tests/unit/test_refs_triage.py` has no `_run_with_triage`, add one at the top
of the module:

```python
def _run_with_triage(tmp_path, *, dispositions, candidates):
    """A run directory holding only 00-catalogue.json and 00-triage.json.

    check_triage reads exactly those two, so this is the whole fixture it needs --
    and building it by hand rather than through build_toy_run is what lets a
    disposition list no writer produces yet be checked at all.
    """
    run = RunPaths(tmp_path / "run-20260914-000000")
    run.root.mkdir(parents=True)
    write_json(
        run.catalogue,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "candidates": [{"candidate_id": cid, "kind": "other"} for cid in candidates],
        },
    )
    write_json(
        run.triage,
        {"schema_version": "0.1", "run_id": run.root.name, "dispositions": dispositions},
    )
    return run
```

- [ ] **Step 8: Run the tests to confirm the first and third fail**

Run: `uv run pytest tests/unit/test_refs_triage.py -q -k defer or scoping`
Expected: FAIL — the false `reason_code names a decline` finding on the first
test, and no `no candidate was admitted` finding on the third.

- [ ] **Step 9: Add the third branch to `check_triage`**

In `src/rubrica/refs.py`, replace the `else:` at line 1185 with an explicit
three-way branch. The trailing `else` keeps its current meaning — an unrecognised
disposition string still counts as an admit, which is layer 1's to reject and not
a behaviour this task changes.

```python
        code = entry.get("reason_code")
        disposition = entry.get("disposition")
        if disposition == "decline":
            # ... unchanged: the three existing clauses ...
        elif disposition == phase.DEFER:
            # A defer is neither an admit nor a decline, and the branches either
            # side of this one were each wrong about it. Before this clause
            # existed a defer took the `else` below, which fabricated
            # "reason_code names a decline; an admit has none" against a correct
            # record -- exit 1 naming the wrong defect -- and counted the defer
            # toward `admits`, masking the empty-admitted-set scoping check
            # fifty lines down. Sending it to the decline branch instead would
            # demand one of the decline codes for a ruling that is not one.
            #
            # Deliberately *not* also checked here: `admissible is False`. A
            # container of a deferred kind is never deferred --
            # phase.deferred_candidate_ids excludes it, so it stays in the shard
            # for a member to decline -- and a second guard here would report a
            # shape no writer in this package can produce.
            if code != phase.DEFER_REASON_CODE:
                report(
                    f"{pointer}/reason_code",
                    f"a defer must carry reason_code {phase.DEFER_REASON_CODE!r}, not {code!r}; "
                    "a decline says this input has no evidence value and a defer says it has "
                    "value this phase cannot spend, and only the second is a deferral",
                )
        else:
            admits += 1
            # ... unchanged ...
```

Add `from rubrica import phase` to `refs.py`'s imports, in the existing
`from rubrica...` group so ruff's `I` rule stays satisfied.

- [ ] **Step 10: Run the full suite and the other two gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS, `check-skills` exits 0.

- [ ] **Step 11: Commit**

```bash
git add src/rubrica/phase.py src/rubrica/schema/triage-0.1.json src/rubrica/validate.py \
        src/rubrica/refs.py tests/unit/test_phase.py tests/unit/test_refs_triage.py
git commit -S -s -m "$(cat <<'MSG'
feat(triage): Add the defer disposition and the phase block it belongs to

`defer` is a third disposition rather than a decline with a special reason code
because the two make opposite promises: a decline says an input has no evidence
value, a defer says it has value this phase cannot spend. Collapsing them would
make triage-seal's counts and the gate-0 brief report that 68 deferred inputs
were judged useless.

check_triage branched on `if decline: ... else: admits += 1`, so a defer both
fabricated a "reason_code names a decline" finding against a correct record and
counted toward `admits` -- masking the empty-admitted-set scoping check for a run
that admitted nothing at all. Both were measured before the third branch landed.

phase.py is one home for the three literals and the kind resolver because the
block is written by four stages and read by six, and nothing downstream of intake
reads the corpus again: two of them disagreeing about what was deferred is
unrecoverable rather than merely wrong.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---
### Task 2: `triage-slices` declares the phase, and the two checkers that read the plan

The operator flag, the plan and shard changes it drives, and — in the same task,
because splitting them would leave `make test` red — the four checker clauses that
would otherwise fire against a deferred candidate.

Scope note: this task's tests stop at the plan, the shards and the checkers. A
*sealed* phase run is Task 3's, because until `triage-seal` synthesises the defer
rulings, `check_triage`'s "every candidate must be ruled on" clause correctly
reports the deferred candidates as unruled. Runs with no phase are unaffected
throughout, which is what keeps the suite green.

**Files:**
- Modify: `src/rubrica/schema/slices-0.1.json`
- Modify: `src/rubrica/slices.py:613-780` (`write_slices`)
- Modify: `src/rubrica/cli.py:232-233` (`p_slices`), and its `triage-slices` handler at `cli.py:583`
- Modify: `src/rubrica/refs.py:414-600` (`check_slices`), `refs.py:665-847` (`check_disposition_parts`)
- Create: `tests/unit/test_phase_pipeline.py`
- Test: `tests/unit/test_refs_slices.py`, `tests/unit/test_refs_triage_parts.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `phase.read`, `phase.deferred_candidate_ids`, `validate.catalogue_candidate_kinds` (Task 1).
- Produces:
  - `slices.write_slices(run, *, cap=DEFAULT_SLICE_BYTES, phase_block=None) -> tuple[Path, list[Slice]]`
    — `phase_block` is the `{number, deferred_kinds}` dict or `None`.
  - `00-slices.json` top-level `phase`, and per-slice `deferred_candidate_ids`.
  - `tests/unit/test_phase_pipeline.py::phase_run(tmp_path, *, number=1, kinds=("trace",), extra_candidates=())`
    — a run sliced under a phase, used by Tasks 3-7.

- [ ] **Step 1: Write the failing test for the plan and the shards**

Create `tests/unit/test_phase_pipeline.py`. The toy catalogue gives a genuinely
mixed slice for free — its three candidates are `api-json` (`mcp_tool_schema`),
`notes-md` (`design_doc`) and `trace-json` (`trace`), all in `s01` — so the mixed
path needs no synthetic fixture. The fully-deferred path does, and this module owns
it.

```python
"""The phase block's carry chain, from the operator flag to the world model.

One module for the whole chain rather than one per stage, because what is being
tested is that four writers and six readers agree about a single fact, and a
per-stage module cannot see a disagreement between two stages.

The toy catalogue is a mixed slice by construction -- `trace-json` sits in `s01`
alongside a `mcp_tool_schema` and a `design_doc` -- so `--defer-kind trace` over it
exercises subtraction without a synthetic fixture. A *fully* deferred slice needs
more than one slice to exist, so `_multi_slice_catalogue` below builds one, and it
is this module's own rather than an addition to tests/toy.py: the golden toy is the
model answer a skill imitates, and a fixture that deferred one of its three inputs
would teach a skill that the golden world has two.
"""

from __future__ import annotations

import json

import pytest

from rubrica import phase, refs, slices
from rubrica.artifacts import write_json
from rubrica.paths import RunPaths
from tests.toy import build_toy_run


def phase_run(tmp_path, *, number=1, kinds=("trace",)):
    """A toy run sliced under a phase, stopping at triage-slices.

    Re-slices rather than building a second corpus: `write_slices` is idempotent
    and safe to re-run by design (a human adopting a projection at gate 0 changes
    the catalogue), so calling it again with a phase is exactly what an operator
    reversing a gate-0 decision does.
    """
    run = build_toy_run(tmp_path, upto="triage-slices")
    slices.write_slices(run, phase_block={"number": number, "deferred_kinds": list(kinds)})
    return run


def _plan(run: RunPaths) -> dict:
    return json.loads(run.slices.read_text())


def test_the_plan_records_the_phase_and_the_deferred_candidates(tmp_path):
    run = phase_run(tmp_path)
    plan = _plan(run)
    assert plan["phase"] == {"number": 1, "deferred_kinds": ["trace"]}
    entry = plan["slices"][0]
    assert entry["deferred_candidate_ids"] == ["trace-json"]
    # The partition stays total: the deferred candidate is still in the slice it
    # belongs to, so check_slices' "every catalogue candidate lands in exactly one
    # slice" clause is untouched and phase 3 reads the same boundaries.
    assert set(entry["candidate_ids"]) == {"api-json", "notes-md", "trace-json"}


def test_a_run_with_no_phase_declares_neither_field(tmp_path):
    """The negative control, and the compatibility guarantee: absent means the
    package behaves exactly as it did before phasing. Both keys absent rather than
    null or empty, so a reader cannot tell this plan from one written before the
    field existed."""
    run = build_toy_run(tmp_path, upto="triage-slices")
    plan = _plan(run)
    assert "phase" not in plan
    assert "deferred_candidate_ids" not in plan["slices"][0]


def test_the_shard_omits_the_deferred_candidate_and_bytes_follows_it(tmp_path):
    """Subtraction is what makes rb-triage-rule need no edit: a member never sees a
    deferred candidate, so no prompt is asked to apply the policy and the mixed
    slice is cheaper to dispatch as well as correct.

    `bytes` tracks the shard rather than the slice because check_slices recomputes
    it from the shard's own candidates -- it is the dispatch's read cost, which is
    what the cap is a cap on."""
    run = phase_run(tmp_path)
    shard = json.loads(run.slice_shard("s01").read_text())
    assert [c["candidate_id"] for c in shard["candidates"]] == ["api-json", "notes-md"]
    entry = _plan(run)["slices"][0]
    assert entry["bytes"] == sum(slices.row_bytes(c) for c in shard["candidates"])
    # The positive control: the trace row really does have weight, so the equality
    # above is subtraction and not two numbers that happen to match.
    catalogue = json.loads(run.catalogue.read_text())
    trace = next(c for c in catalogue["candidates"] if c["candidate_id"] == "trace-json")
    assert slices.row_bytes(trace) > 0


def test_check_slices_and_check_disposition_parts_are_clean_over_a_phase_plan(tmp_path):
    """Both checkers read the plan, and both had a clause that fired against a
    deferred candidate: check_slices' shard/bytes comparison, and
    check_disposition_parts' totality clause 4."""
    run = phase_run(tmp_path)
    assert refs.check_slices(run) == []


def _multi_slice_catalogue(run: RunPaths, *, trace_count: int) -> None:
    """Overwrite the run's catalogue with one whose traces cannot share a slice.

    `plan_slices` splits by kind before it splits by bytes, so a catalogue whose
    trace rows exceed the cap on their own is what produces a slice holding nothing
    but traces -- the shape three of the eleven slices had on the corpus this design
    was measured against.
    """
    ...  # see step 3 for the body


def test_a_fully_deferred_slice_gets_no_shard_and_no_part_is_expected(tmp_path):
    """Three of eleven dispatches became empty on the measured corpus, and that is
    the whole of the gate-0 saving. Two clauses had to learn it: check_slices'
    "slice has no shard on disk" and check_disposition_parts' "slice has no
    disposition part on disk"."""
    run = phase_run(tmp_path)  # replaced below by the multi-slice catalogue
    ...  # see step 3
```

The two `...` bodies are written in step 3, once the writer exists to be tested
against; leaving them unwritten here would be a plan placeholder, so step 3 gives
them in full.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_phase_pipeline.py -q`
Expected: FAIL — `TypeError: write_slices() got an unexpected keyword argument 'phase_block'`

- [ ] **Step 3: Complete the two fixture bodies in the test module**

Replace `_multi_slice_catalogue`'s `...` with:

```python
    catalogue = json.loads(run.catalogue.read_text())
    kept = [c for c in catalogue["candidates"] if c["kind"] != "trace"]
    # Each synthetic trace carries a digest heavy enough that the kind's rows
    # cannot share one slice with the rest at the cap this test packs against.
    # Built from the real trace candidate so every field the packer reads is
    # present and only the weight differs.
    template = next(c for c in catalogue["candidates"] if c["kind"] == "trace")
    traces = []
    for i in range(trace_count):
        row = dict(template)
        row["candidate_id"] = f"trace-{i:02d}"
        row["digest"] = {**template.get("digest", {}), "filler": "x" * 400}
        traces.append(row)
    catalogue["candidates"] = kept + traces
    write_json(run.catalogue, catalogue)
```

Replace the last test's body with:

```python
    run = build_toy_run(tmp_path, upto="triage-slices")
    _multi_slice_catalogue(run, trace_count=6)
    # A cap small enough that the kind split cannot pack traces beside the rest.
    slices.write_slices(
        run, cap=1400, phase_block={"number": 1, "deferred_kinds": ["trace"]}
    )
    plan = _plan(run)
    fully_deferred = [
        s["id"]
        for s in plan["slices"]
        if set(s.get("deferred_candidate_ids", ())) == set(s["candidate_ids"])
    ]
    assert fully_deferred, "the fixture must produce at least one all-trace slice"
    for sid in fully_deferred:
        assert not run.slice_shard(sid).is_file()
    # Neither checker objects: the shard is absent by declaration and so is the
    # part that a shard would have been dispatched to produce.
    assert refs.check_slices(run) == []
    run.dispositions_dir.mkdir(parents=True, exist_ok=True)
    missing = [f.message for f in refs.check_disposition_parts(run)]
    for sid in fully_deferred:
        assert not any(f"slice {sid} has no disposition part" in m for m in missing)
    # The positive control, and it is the half that makes the loop above a guard:
    # a slice that is NOT fully deferred still owes both a shard and a part.
    partial = [s["id"] for s in plan["slices"] if s["id"] not in fully_deferred]
    assert partial
    for sid in partial:
        assert run.slice_shard(sid).is_file()
    assert any(
        f"slice {sid} has no disposition part" in m for sid in partial for m in missing
    )
```

Also replace `test_a_fully_deferred_slice...`'s first line (`run = phase_run(...)`)
— it is superseded by the body above.

- [ ] **Step 4: Extend the slices schema**

In `src/rubrica/schema/slices-0.1.json`:

Add to the top-level `properties` (beside `catalogue_facts`):

```json
    "phase": {"$ref": "triage-0.1.json#/$defs/phase"},
```

Replace the per-slice `bytes` description, because its meaning is now the shard's
rather than the slice's:

```json
   "bytes": {
    "type": "integer",
    "minimum": 0,
    "description": "Total digest bytes of the candidates this slice's SHARD carries -- which is the slice's own candidates minus any in deferred_candidate_ids, since a deferred candidate is subtracted from the shard rather than from the partition. refs.check_slices recomputes this from the shard and checks it matches, so a slice cannot silently drift from its own header, and it is the dispatch's actual read cost, which is what cap_bytes is a cap on. Zero for a fully deferred slice, which has no shard at all."
   },
```

Add the per-slice field, after `candidate_ids`:

```json
   "deferred_candidate_ids": {
    "type": "array",
    "minItems": 1,
    "uniqueItems": true,
    "items": {"$ref": "triage-0.1.json#/$defs/id"},
    "description": "The subset of this slice's candidate_ids that the run's declared phase defers, omitted entirely when it is empty. These stay in candidate_ids -- the partition is total and phase-independent, so slice boundaries mean the same thing in phase 1 and phase 3 -- but are absent from the shard, so no rb-triage-rule member ever sees one and no prompt is asked to apply the policy. A slice whose whole candidate_ids set appears here is fully deferred: no shard is written for it and no disposition part is expected, which is where three of eleven dispatches went on the corpus this was measured against. triage-seal synthesises the defer disposition for every id named here, so the candidate is still ruled on the record."
   },
```

- [ ] **Step 5: Teach `write_slices` the phase**

In `src/rubrica/slices.py`, change the signature and add the subtraction. Add
`from rubrica import phase as phase_mod` to the imports (aliased, because
`slices.py` has no local `phase` name to shadow but the module reads better with
the writer's intent explicit).

```python
def write_slices(
    run: RunPaths,
    *,
    cap: int = DEFAULT_SLICE_BYTES,
    phase_block: dict | None = None,
) -> tuple[Path, list[Slice]]:
```

Extend the docstring with a paragraph on the subtraction — the module's existing
docstrings carry the argument for every choice, so this one must too:

```python
    A declared `phase_block` defers every candidate of its `deferred_kinds`, and the
    subtraction happens *after* planning rather than before it, deliberately. The
    partition is phase-independent: slice s04 holds the same candidates whether or
    not traces are deferred, so a human comparing a phase-1 plan against a phase-3
    one is comparing the same boundaries, and the slice ids mean one thing rather
    than two. What the phase changes is the *shards* -- a deferred candidate is
    absent from the one it would have been dispatched in, so no rb-triage-rule
    member ever sees it and no prompt is asked to apply a kind-level policy.
    A slice whose every candidate is deferred gets no shard at all, which is where
    three of the measured corpus's eleven dispatches went; the stale-shard removal
    below is what deletes one left over from a plan minted before the phase was
    declared.
```

Then, after `plan = plan_slices(candidates, cap=cap)` and
`candidates_by_id = ...`:

```python
    # Resolved once from the full catalogue, not per slice: phase.deferred_candidate_ids
    # is the one place a kind becomes a candidate set, and a second resolution here
    # would be a second answer to the question the whole module is downstream of.
    deferred = phase_mod.deferred_candidate_ids(candidates, phase_block)
```

Change the `slices` list comprehension so `bytes` counts only what the shard will
carry, and the deferred subset is recorded when it is non-empty:

```python
        "slices": [
            {
                "id": s.id,
                "label": s.label,
                "groups": list(s.groups),
                "bytes": sum(
                    row_bytes(candidates_by_id[cid])
                    for cid in s.candidate_ids
                    if cid not in deferred
                ),
                "candidate_ids": list(s.candidate_ids),
                "provenance": [dict(p) for p in s.provenance],
                # Omitted rather than written empty, so a plan for a run that
                # declared no phase is byte-identical to one written before this
                # field existed -- the same rule the phase block itself follows.
                **(
                    {"deferred_candidate_ids": [c for c in s.candidate_ids if c in deferred]}
                    if any(c in deferred for c in s.candidate_ids)
                    else {}
                ),
            }
            for s in plan
        ],
```

Add the phase block to the same document, beside `catalogue_facts`:

```python
    if phase_block is not None:
        document["phase"] = phase_block
```

And in the shard loop, subtract and skip:

```python
    for s in plan:
        kept = [cid for cid in s.candidate_ids if cid not in deferred]
        # A fully deferred slice gets no shard: there is nothing for a member to
        # rule, and writing an empty one would put a dispatch on the driver's list
        # whose whole output would be an empty dispositions array -- which
        # dispositions-part-0.1.json's minItems: 1 refuses anyway, so the member
        # could not even produce a valid part.
        if not kept:
            continue
        shard = {
            "schema_version": "0.1",
            "run_id": catalogue["run_id"],
            "slice_id": s.id,
            "request": catalogue["request"],
            "policy": catalogue["policy"],
            "provenance": [dict(p) for p in s.provenance],
            "candidates": [candidates_by_id[cid] for cid in kept],
        }
```

The shard deliberately gains **no** phase block. `rb-triage-rule` rules what it is
handed, and it is handed nothing deferred; a block there would be a fact the
member has no action to take on, which this project calls a decorative input.

- [ ] **Step 6: Add the CLI flags**

In `src/rubrica/cli.py`, replace `p_slices`' single argument:

```python
    p_slices = parsers["triage-slices"]
    p_slices.add_argument("--run", required=True)
    # Declared here rather than on `intake`, where the design that motivated this
    # first put it: paths.STAGES puts triage-slices at index 1 and intake at index
    # 6, so manifest.json does not exist yet and a consumer cannot read a file five
    # stages downstream. This is the first stage that needs the declaration, and
    # putting it here also means there is exactly one declaration site to disagree
    # with itself -- the block is carried verbatim from the plan through
    # 00-triage.json and manifest.json to the world model.
    #
    # Re-running this command with a different --defer-kind is how a human at gate
    # 0 reverses the decision, which is affordable precisely because triage-slices
    # is code.
    p_slices.add_argument("--phase", type=int, default=None, metavar="N")
    # choices from the schema, not a literal: a --defer-kind naming a kind no
    # candidate can carry would defer nothing and still report a phase, so the run
    # would cost full price and claim a saving.
    p_slices.add_argument(
        "--defer-kind",
        action="append",
        default=[],
        metavar="KIND",
        choices=list(validate.catalogue_candidate_kinds()),
    )
```

In the `triage-slices` handler at `cli.py:583`, build the block and refuse a
half-declaration. Both halves must arrive together: a `--phase` with nothing
deferred is a run that pays full price and reports a saving, and a `--defer-kind`
with no number is a deferral with no phase to defer *to*.

```python
        if args.command == "triage-slices":
            run = _run_dir(args.run)
            # A usage error, exit 2, not a finding: argv is where this came from,
            # and no stage re-dispatch fixes a flag. argparse cannot express
            # "these two are required together", so it is checked here.
            if (args.phase is None) != (not args.defer_kind):
                raise UsageError(
                    "--phase and --defer-kind are declared together or not at all: a phase "
                    "deferring nothing pays full price and reports a saving, and a deferred "
                    "kind with no phase number has no phase to be deferred to"
                )
            phase_block = None
            if args.phase is not None:
                # Sorted and de-duplicated so two invocations naming the same kinds
                # in different order produce byte-identical plans -- the same
                # determinism argument reconcile-seal and emit rest on.
                phase_block = {
                    "number": args.phase,
                    "deferred_kinds": sorted(set(args.defer_kind)),
                }
            path, _ = slices.write_slices(run, phase_block=phase_block)
            print(path)
            return CLEAN
```

Preserve whatever the existing handler body does around `write_slices`; the block
above shows the added lines in place, not a wholesale replacement of a block whose
surrounding comment explains its exit codes.

- [ ] **Step 7: Teach `check_slices` the deferred subset**

Three clauses in `src/rubrica/refs.py`'s `check_slices` change. Read the deferred
set per entry, immediately after `candidate_ids` is built at line 489:

```python
        # The plan's own record of what its phase deferred. Read from the entry
        # rather than recomputed from the catalogue and the phase block: what the
        # three clauses below must agree with is the shard the *writer* produced,
        # and recomputing would check the catalogue against itself while leaving a
        # writer that ignored its own declaration undetected.
        deferred_ids = [c for c in _as_list(entry.get("deferred_candidate_ids")) if isinstance(c, str)]
        expected_shard_ids = [c for c in candidate_ids if c not in set(deferred_ids)]
```

Check 4's missing half (line ~521) gains the fully-deferred exemption:

```python
        shard_path = run.slice_shard(sid)
        if not shard_path.is_file():
            # A fully deferred slice has no shard by declaration, not by omission:
            # every candidate it owns is deferred, so there is nothing for a member
            # to rule and dispositions-part-0.1.json's minItems: 1 would refuse the
            # empty part anyway. Reported only when the plan does NOT account for
            # the absence.
            if not expected_shard_ids:
                continue
            out.append(Finding(run.slices_dir, "refs", "", f"slice {sid} has no shard on disk"))
            continue
```

Check 6 compares against the expected set rather than the full one:

```python
        shard_ids = [c.get("candidate_id") for c in shard_candidates]
        if shard_ids != expected_shard_ids:
            out.append(
                Finding(
                    shard_path,
                    "refs",
                    "/candidates",
                    f"shard candidates do not match slice {sid}'s candidate_ids minus its "
                    "deferred_candidate_ids, in order",
                )
            )
```

Check 5 needs no change: it already recomputes `bytes` from the shard's own
candidates, and the writer now produces exactly that number. Add a sentence to
its comment saying so, since the number's *meaning* moved even though the
arithmetic did not:

```python
        # Check 5: bytes is arithmetic, not testimony -- recomputed from the
        # shard's own candidates via slices.row_bytes, the same function
        # write_slices used to produce the number in the first place. Unchanged by
        # phasing, and the reason is worth stating: a deferred candidate is absent
        # from the shard, so recomputing from the shard already yields the
        # undeferred sum the writer declares. The number's meaning moved with the
        # subtraction; its check did not.
```

Add two clauses at the end of the per-entry loop, so the new field is held to the
same discipline as every other id in the plan:

```python
        # Check 10: a deferred id must be one this slice actually owns. A plan
        # naming a sibling's candidate here would subtract a row from the wrong
        # shard, and check 6 above would then report the *shard* as wrong when the
        # defect is in the plan.
        for j, cid in enumerate(deferred_ids):
            if cid not in candidate_ids:
                report(
                    f"{pointer}/deferred_candidate_ids/{j}",
                    f"{cid!r} is deferred by slice {sid!r} but is not one of its candidate_ids",
                )
```

- [ ] **Step 8: Teach `check_disposition_parts` the deferred population**

Two clauses in `check_disposition_parts`. After `slice_candidates` is built
(line ~715), collect the deferred sets from the same entries:

```python
    slice_deferred: dict[str, set[str]] = {}
    for entry in slice_entries:
        if not isinstance(entry, dict):
            continue
        sid = _str_or_none(entry.get("id"))
        if sid is not None:
            slice_deferred[sid] = {
                c for c in _as_list(entry.get("deferred_candidate_ids")) if isinstance(c, str)
            }
```

Clause 1 skips a fully-deferred slice:

```python
    # Clause 1: every slice the plan declares has a part written for it -- except
    # one the plan declares fully deferred, which is never dispatched at all. Its
    # rulings are triage-seal's to synthesise from the plan, so the absence here is
    # accounted for rather than missing.
    expected_parts = {
        sid
        for sid, ids in slice_candidates.items()
        if ids - slice_deferred.get(sid, set())
    }
    missing_slices = sorted(expected_parts - have_parts)
```

Clause 4 excludes deferred candidates from the checkable population:

```python
        # Deferred candidates are excluded for the reason a missing slice's are:
        # no staged part can be responsible for them. Unlike a missing slice this
        # is a declaration rather than a defect -- the plan says these were never
        # dispatched -- and triage-seal is what puts a ruling on the record for
        # each. Reporting them here would name 00-dispositions/ for a decision
        # taken in 00-slices.json.
        deferred_everywhere = {cid for ids in slice_deferred.values() for cid in ids}
        uncheckable |= deferred_everywhere
```

Insert that block beside the existing `uncheckable` accumulation, before
`checkable = catalogue_ids - uncheckable`.

- [ ] **Step 9: Add the negative-control tests for both checkers**

Append to `tests/unit/test_refs_slices.py`:

```python
def test_a_deferred_id_outside_the_slice_is_a_finding(tmp_path):
    """The plan's new field is held to the same resolution every other id in it is.
    Measured in both directions: the clean case is
    test_phase_pipeline's check_slices assertion, and this is the shape that would
    subtract a row from the wrong shard and make check 6 blame the shard for it."""
    run = build_toy_run(tmp_path, upto="triage-slices")
    plan = json.loads(run.slices.read_text())
    plan["slices"][0]["deferred_candidate_ids"] = ["not-in-this-slice"]
    write_json(run.slices, plan)
    messages = [f.message for f in refs.check_slices(run)]
    assert any("is not one of its candidate_ids" in m for m in messages)


def test_a_missing_shard_is_still_a_finding_when_the_slice_is_only_partly_deferred(tmp_path):
    """The exemption in check 4 is exactly one slice shape wide. A slice with one
    undeferred candidate left still owes a shard, and deleting it must still be
    reported -- otherwise `deferred_candidate_ids` becomes a way to make any
    missing shard disappear."""
    run = build_toy_run(tmp_path, upto="triage-slices")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["trace"]})
    run.slice_shard("s01").unlink()
    messages = [f.message for f in refs.check_slices(run)]
    assert any("has no shard on disk" in m for m in messages)
```

Append to `tests/unit/test_refs_triage_parts.py`:

```python
def test_a_deferred_candidate_is_not_reported_as_uncovered_by_the_staged_parts(tmp_path):
    """Clause 4's population. Before the exemption, every deferred candidate was
    reported as "has no disposition in any staged part or adoption" -- a finding
    naming 00-dispositions/ for a decision recorded in 00-slices.json, which is the
    wrong-artifact failure the module docstring's 01-claims/ incident is about."""
    run = build_toy_run(tmp_path, upto="triage-rule")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["trace"]})
    messages = [f.message for f in refs.check_disposition_parts(run)]
    assert not any("trace-json" in m for m in messages)
    # The positive control: an undeferred candidate removed from its part IS still
    # reported, so the exemption is scoped to the declaration and not to the clause.
    part = json.loads(run.disposition_part("s01").read_text())
    part["dispositions"] = [
        d for d in part["dispositions"] if d["candidate_id"] != "notes-md"
    ]
    write_json(run.disposition_part("s01"), part)
    messages = [f.message for f in refs.check_disposition_parts(run)]
    assert any("notes-md" in m and "no disposition" in m for m in messages)
```

Append to `tests/unit/test_cli.py` (follow the module's existing convention for
invoking `main`):

```python
def test_triage_slices_refuses_half_a_phase_declaration(tmp_path, capsys):
    """Exit 2, both directions. A --phase with nothing deferred pays full price and
    reports a saving; a --defer-kind with no number is a deferral with no phase to
    defer to. argparse cannot express "required together", so main() does."""
    run = build_toy_run(tmp_path, upto="survey")
    for argv in (
        ["triage-slices", "--run", str(run.root), "--phase", "1"],
        ["triage-slices", "--run", str(run.root), "--defer-kind", "trace"],
    ):
        assert cli.main(argv) == 2


def test_triage_slices_refuses_a_defer_kind_the_schema_does_not_declare(tmp_path):
    """argparse's own usage error, which main() maps to 2. The choices come from
    triage-0.1.json's $defs/kind, so this cannot drift from what a candidate can
    carry."""
    run = build_toy_run(tmp_path, upto="survey")
    assert (
        cli.main(
            ["triage-slices", "--run", str(run.root), "--phase", "1", "--defer-kind", "traces"]
        )
        == 2
    )
```

- [ ] **Step 10: Run the tests**

Run: `uv run pytest tests/unit/test_phase_pipeline.py tests/unit/test_refs_slices.py tests/unit/test_refs_triage_parts.py tests/unit/test_cli.py -q`
Expected: PASS

- [ ] **Step 11: Run the full suite and the other two gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS. If `check_slices`' `bytes` clause reddens an existing test, the
test is asserting the old meaning of the field — update the expectation, and say so
in the commit body.

- [ ] **Step 12: Commit**

```bash
git add src/rubrica/schema/slices-0.1.json src/rubrica/slices.py src/rubrica/cli.py \
        src/rubrica/refs.py tests/unit/test_phase_pipeline.py tests/unit/test_refs_slices.py \
        tests/unit/test_refs_triage_parts.py tests/unit/test_cli.py
git commit -S -s -m "$(cat <<'MSG'
feat(triage-slices): Declare the phase, and subtract deferred candidates from the shards

The flag goes here rather than on `intake`, where the design first put it:
paths.STAGES puts triage-slices at index 1 and intake at index 6, so manifest.json
does not exist yet and a consumer cannot read a file five stages downstream. One
declaration site also means there is only one to disagree with itself.

Deferred candidates are subtracted from the shards after planning, not before, so
the partition stays phase-independent and a slice id means the same thing in phase
1 and phase 3. The consequence worth naming: rb-triage-rule needs no edit at all,
because no member is ever handed a deferred candidate. The design asked for one
prompt instruction on the pass that decides what the run can ever know; making the
policy mechanical removes that compliance risk, and makes the mixed slice cheaper
to dispatch as well.

Four checker clauses learned the deferred population -- check_slices' shard
presence and shard/id comparison, and check_disposition_parts' part presence and
catalogue totality. All four would otherwise have named 00-dispositions/ or a
shard for a decision recorded in 00-slices.json.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---
### Task 3: `triage-seal` synthesises the defer rulings and records the phase

Every catalogue candidate must be ruled on the record — that is the property gate 0
rests on, and the reason `rb-triage-rule` records a reason for every candidate
rather than a list of the ones it kept. No member saw the deferred candidates, so
the seal is what rules them, from the plan.

**Files:**
- Modify: `src/rubrica/seal.py:316-543` (`seal`)
- Test: `tests/unit/test_phase_pipeline.py`, `tests/unit/test_refs_triage.py`

**Interfaces:**
- Consumes: `00-slices.json`'s `phase` and `deferred_candidate_ids` (Task 2);
  `phase.DEFER`, `phase.DEFER_REASON_CODE`, `phase.POLICY_AUTHORITY` (Task 1).
- Produces: `00-triage.json` carrying a `defer` disposition per deferred candidate
  and the run's `phase` block.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_phase_pipeline.py`:

```python
def _sealed_phase_run(tmp_path, *, kinds=("trace",)):
    """A toy run sealed under a phase. Re-slices before triage-rule has run, so the
    parts the fan-out writes never mention a deferred candidate -- which is the
    real dispatch order, not a convenience."""
    run = build_toy_run(tmp_path, upto="survey")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": list(kinds)})
    return run


def test_the_sealed_record_rules_every_deferred_candidate(tmp_path):
    """Gate 0's property: a candidate the run will never read must still be visible
    as a decision, because a human can only overturn a decision they can see. No
    member saw these, so the seal rules them from the plan."""
    run = build_toy_run(tmp_path, upto="triage-rule")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["trace"]})
    # Drop the deferred candidate from the part, which is what a member dispatched
    # against a subtracted shard would have written.
    part = json.loads(run.disposition_part("s01").read_text())
    part["dispositions"] = [
        d for d in part["dispositions"] if d["candidate_id"] != "trace-json"
    ]
    write_json(run.disposition_part("s01"), part)
    path, findings = seal.seal(run)
    assert findings == []
    assert path == run.triage
    record = json.loads(run.triage.read_text())
    deferred = [d for d in record["dispositions"] if d["disposition"] == phase.DEFER]
    assert [d["candidate_id"] for d in deferred] == ["trace-json"]
    entry = deferred[0]
    assert entry["reason_code"] == phase.DEFER_REASON_CODE
    assert entry["authority"] == phase.POLICY_AUTHORITY
    # No priority: no member ranked it, and a code-invented rank would be a
    # reasoned number wearing an observed one's clothes.
    assert "priority" not in entry
    # The reason names the kind and the phase, because those are the two facts a
    # human at gate 0 needs to overturn the deferral.
    assert "trace" in entry["reason"] and "1" in entry["reason"]


def test_the_sealed_record_carries_the_phase_block_verbatim(tmp_path):
    run = build_toy_run(tmp_path, upto="triage-rule")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["trace"]})
    part = json.loads(run.disposition_part("s01").read_text())
    part["dispositions"] = [
        d for d in part["dispositions"] if d["candidate_id"] != "trace-json"
    ]
    write_json(run.disposition_part("s01"), part)
    seal.seal(run)
    record = json.loads(run.triage.read_text())
    assert record["phase"] == {"number": 1, "deferred_kinds": ["trace"]}


def test_a_sealed_record_with_no_phase_carries_neither_the_block_nor_a_defer(tmp_path):
    """The compatibility control: the golden toy run seals byte-for-byte as it did
    before phasing."""
    run = build_toy_run(tmp_path, upto="triage-rule")
    before = run.triage.read_text() if run.triage.is_file() else None
    seal.seal(run)
    record = json.loads(run.triage.read_text())
    assert "phase" not in record
    assert all(d["disposition"] != phase.DEFER for d in record["dispositions"])
    if before is not None:
        assert run.triage.read_text() == before


def test_a_part_that_rules_a_deferred_candidate_is_a_conflict_the_seal_refuses(tmp_path):
    """A hand-written part cannot both be dispatched for a candidate the plan says
    was never dispatched. Refused rather than resolved by precedence, because either
    precedence would silently discard a real ruling -- and the finding names the
    plan, since that is the artifact declaring the candidate deferred."""
    run = build_toy_run(tmp_path, upto="triage-rule")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["trace"]})
    # The part built before the re-slice still rules trace-json, so this is the
    # conflict as it would actually arise: a plan re-minted under a phase over parts
    # written without one.
    path, findings = seal.seal(run)
    assert path is None
    assert any("trace-json" in f.message for f in findings)
    assert all(f.path == run.slices for f in findings)


def test_check_refs_is_clean_over_the_sealed_phase_record(tmp_path):
    """The end of the chain this task closes: check_triage's "every candidate must
    be ruled on" clause is satisfied by the synthesised rulings, and its third
    branch (Task 1) accepts them."""
    run = build_toy_run(tmp_path, upto="triage-rule")
    slices.write_slices(run, phase_block={"number": 1, "deferred_kinds": ["trace"]})
    part = json.loads(run.disposition_part("s01").read_text())
    part["dispositions"] = [
        d for d in part["dispositions"] if d["candidate_id"] != "trace-json"
    ]
    write_json(run.disposition_part("s01"), part)
    seal.seal(run)
    assert refs.check_triage(run) == []
    assert refs.check_disposition_parts(run) == []
```

Add `from rubrica import seal` to the module's imports.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_phase_pipeline.py -q -k sealed or deferred_candidate`
Expected: FAIL — the record carries no `defer` disposition and no `phase`, and
`check_triage` reports `candidate 'trace-json' has no disposition`.

- [ ] **Step 3: Read the plan in `seal.seal`**

In `src/rubrica/seal.py`, after the existing reads of `objective`, `audit` and
`adoptions` and before the `rulings` dict is folded, add the plan read. A malformed
plan is exit 2, not a finding: `triage-slices` is code, so no prompt re-dispatch
repairs it, and spending the orchestrator's one repair attempt on a stage whose
output was never the problem is the failure `synthesise-interfaces`' own split
records.

```python
    # 00-slices.json, for the phase declaration and the candidates it defers. Read
    # here rather than passed in, because the architectural rule is that artifacts
    # on disk are the only channel between stages and the seal's caller is a CLI
    # handler holding nothing but a run directory.
    #
    # Absent is not a finding and cannot hide a deferral: no plan means nothing was
    # sliced, and nothing sliced means no candidate could have been deferred. That
    # is also what keeps a run minted through `intake --input` -- which never slices
    # at all -- sealing exactly as it did before phasing.
    #
    # Malformed IS exit 2 rather than a finding, on synthesise-interfaces' ruling:
    # triage-slices is code, so no prompt re-dispatch repairs its output, and a 1
    # here would spend the orchestrator's one repair attempt on a stage whose output
    # was never the problem.
    plan: dict = {}
    if run.slices.is_file():
        plan_document = read_json(run.slices)
        if not isinstance(plan_document, dict):
            raise UsageError(
                f"{run.slices} is not a JSON object: found {plan_document!r}; the plan cannot "
                "say which candidates this run's phase defers"
            )
        plan = plan_document
    phase_block = phase.read(plan)
    deferred_by_slice = {
        entry.get("id"): [
            cid
            for cid in (entry.get("deferred_candidate_ids") or [])
            if isinstance(cid, str)
        ]
        for entry in (plan.get("slices") or [])
        if isinstance(entry, dict)
    }
    deferred_ids = sorted({cid for ids in deferred_by_slice.values() for cid in ids})
```

Add `from rubrica import phase` and, if not already imported, `UsageError` and
`read_json`, to `seal.py`'s existing import groups.

- [ ] **Step 4: Refuse the conflict, then synthesise**

Insert immediately after the parts and adoptions have been folded into `rulings`
and **before** item 2's duplicate check, so a conflict is reported once rather than
compounding into a duplicate finding:

```python
    # A candidate the plan defers that some staged part or adoption also ruled. The
    # plan says no member was dispatched for it; a part says one was. Refused rather
    # than resolved by precedence, because either precedence discards a real ruling
    # silently: preferring the part would ignore a declared deferral and admit an
    # input the operator excluded, and preferring the plan would throw away a
    # human's adoption. The finding names the plan, which is the artifact making the
    # claim that nothing ruled these.
    #
    # The realistic way this arises is a plan re-minted under a phase over parts
    # written before it -- which is exactly what a human reversing a gate-0 decision
    # does, so the message says what to do about it.
    conflicting = sorted(set(deferred_ids) & set(rulings))
    for cid in conflicting:
        findings.append(
            Finding(
                run.slices,
                "seal",
                "",
                f"candidate {cid!r} is deferred by the plan but also ruled by a staged part or "
                f"adoption; re-dispatch the slice whose shard changed, or re-mint the plan "
                f"without deferring {cid!r}",
            )
        )
```

Then, after the existing item 4 (`no admit anywhere`) and before the assembly's
`surfaces` line, synthesise the rulings. `rulings` maps a candidate id to a list of
`(path, entry)` pairs, so the synthesised entries join it in the same shape and
flow through the existing ordering and assembly untouched.

```python
    # The deferred candidates' own rulings, synthesised from the plan because no
    # member ever saw them. Gate 0's whole property is that every candidate is a
    # decision on the record -- a human can only overturn a decision they can see --
    # and a deferred candidate is the one the property matters most for, since
    # nothing downstream of intake reads the corpus again.
    #
    # Placed after item 4 deliberately: a run whose only non-declines are defers has
    # admitted nothing, and that is a scoping failure the check above must still
    # catch. Folding these in earlier would give it an empty-admit set dressed as a
    # populated one.
    #
    # No `priority`. The design this implements expected a deferred candidate to
    # keep the one its member assigned, but under shard subtraction no member ranked
    # it, and inventing a rank in code would be a reasoned number presented as an
    # observed one. `priority` is optional in triage-0.1.json and _member_priority
    # sorts an absent one at the lowest-rank sentinel, so nothing has to tolerate
    # this specially. Phase 3 re-slices the deferred population and dispatches
    # rb-triage-rule over it, which is the pass whose judgment ought to rank inputs.
    catalogue_kinds = {}
    if run.catalogue.is_file():
        catalogue_document = read_json(run.catalogue)
        if isinstance(catalogue_document, dict):
            catalogue_kinds = {
                c["candidate_id"]: c.get("kind")
                for c in (catalogue_document.get("candidates") or [])
                if isinstance(c, dict) and isinstance(c.get("candidate_id"), str)
            }
    number = phase_block.get("number") if phase_block else None
    for cid in deferred_ids:
        kind = catalogue_kinds.get(cid)
        # The kind and the number are the two facts a human at gate 0 needs to
        # overturn this: which declaration caught the candidate, and which phase it
        # is waiting for. A kind the catalogue could not supply renders as its
        # absence rather than being omitted, so the reason never reads as a
        # judgment about the candidate itself.
        kind_text = repr(kind) if kind is not None else "an unrecorded kind"
        rulings[cid] = [
            (
                run.slices,
                {
                    "candidate_id": cid,
                    "disposition": phase.DEFER,
                    "reason_code": phase.DEFER_REASON_CODE,
                    "reason": (
                        f"{kind_text} is deferred in phase {number}: this input has evidence "
                        "value that this phase cannot spend, and it is held for a later one "
                        "rather than declined"
                    ),
                    "authority": phase.POLICY_AUTHORITY,
                },
            )
        ]
```

- [ ] **Step 5: Carry the phase into the record**

Find where `triage_record` is built before `write_json(run.triage, triage_record)`
at line 542, and add the block on the same conditional pattern the plan uses:

```python
    # Carried verbatim, never recomputed. The plan is where the operator declared
    # it and this record is what intake reads, so a second derivation here would be
    # a second answer to the question gate 0 already ratified.
    if phase_block is not None:
        triage_record["phase"] = phase_block
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit/test_phase_pipeline.py -q`
Expected: PASS

- [ ] **Step 7: Run the full suite and the other two gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/seal.py tests/unit/test_phase_pipeline.py
git commit -S -s -m "$(cat <<'MSG'
feat(triage-seal): Rule every deferred candidate on the record, and carry the phase

Gate 0's property is that every candidate is a decision a human can see and
overturn, and a deferred candidate is the one it matters most for: nothing
downstream of intake reads the corpus again, so a candidate the run drops is gone
as completely as if the corpus never held it. No member saw the deferred ones, so
the seal rules them from the plan.

The synthesised ruling carries no `priority`. The design expected a deferred
candidate to keep its member-assigned rank, but under shard subtraction no member
ranked it and inventing one in code would be a reasoned number presented as an
observed one. Phase 3's own triage-rule is the pass whose judgment ought to rank
these.

A plan that defers a candidate some staged part also ruled is refused rather than
resolved by precedence: preferring the part would admit an input the operator
excluded, and preferring the plan would discard a human's adoption. A malformed
plan is exit 2, on synthesise-interfaces' ruling -- triage-slices is code, so no
prompt re-dispatch repairs it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 4: `intake` carries the phase into the manifest

The manifest is what every stage from `extract` on reads, and the phase is what
tells `reconcile-seal` two passes are not required and the world model that it is
incomplete. `intake` is also the one stage that knows the deferred *count* exactly,
because it counted the dispositions.

**Files:**
- Modify: `src/rubrica/schema/manifest-0.1.json`
- Modify: `src/rubrica/intake.py:560-600` (`admit_from_triage`)
- Modify: `src/rubrica/refs.py:1549-1620` (`check_admitted_inputs`)
- Test: `tests/unit/test_phase_pipeline.py`, `tests/unit/test_refs_admitted.py`

**Interfaces:**
- Consumes: `00-triage.json`'s `phase` and its `defer` dispositions (Task 3).
- Produces: `manifest.json` `phase` = `{number, deferred_kinds, deferred_count}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_phase_pipeline.py`:

```python
def test_the_manifest_carries_the_phase_and_counts_the_deferrals(tmp_path):
    """`deferred_count` is added here rather than at the seal because intake is the
    stage that knows it exactly -- it read the dispositions -- and reconcile-seal
    reads the manifest and never 00-triage.json, so the count has to travel this
    way to reach the world model."""
    run = build_toy_run(tmp_path, upto="intake")  # see step 3 for why this works
    manifest = json.loads(run.manifest.read_text())
    assert manifest["phase"] == {
        "number": 1,
        "deferred_kinds": ["trace"],
        "deferred_count": 1,
    }
    # And the deferred input is not registered: `defer` is not `admit`, so intake
    # does not materialise it and no claims file is ever expected for it.
    assert all("trace" not in entry["artifact_id"] for entry in manifest["inputs"])


def test_a_manifest_from_a_phaseless_run_has_no_phase_key(tmp_path):
    run = build_toy_run(tmp_path, upto="intake")
    manifest = json.loads(run.manifest.read_text())
    assert "phase" not in manifest


def test_check_refs_is_clean_through_intake_on_a_phase_run(tmp_path):
    """check_manifest holds every registered input to a claims file and every
    admitted candidate to a manifest entry, both directions. A deferred candidate is
    in neither population, which is the property the design rests on -- and this is
    the assertion that it actually holds rather than being argued."""
    run = ...  # the phase run built through intake; see step 3
    assert refs.check_admitted_inputs(run) == []
```

The `...` is completed in step 3, once the test module has a helper that builds a
phase run through `intake`.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_phase_pipeline.py -q -k manifest`
Expected: FAIL — `KeyError: 'phase'`

- [ ] **Step 3: Add the phase-run-through-intake helper to the test module**

`build_toy_run` does not take a phase, and it must not: the golden toy is the model
answer a skill imitates. So the helper re-slices, re-seals and re-intakes, which is
also the real order an operator declaring a phase at gate 0 goes through.

```python
def phase_run_through_intake(tmp_path, *, number=1, kinds=("trace",)):
    """A toy run carried under a phase as far as the manifest.

    Built by re-slicing at triage-rule and re-sealing rather than by threading a
    phase through build_toy_run: tests/toy.py builds the golden world, and a
    checkpoint that deferred one of its three inputs would be a second, quietly
    different golden world for every later test to pick up by accident.
    """
    run = build_toy_run(tmp_path, upto="triage-rule")
    slices.write_slices(
        run, phase_block={"number": number, "deferred_kinds": list(kinds)}
    )
    for sid in run.slice_ids_with_parts():
        part = json.loads(run.disposition_part(sid).read_text())
        deferred = set(
            json.loads(run.slices.read_text())["slices"][0].get(
                "deferred_candidate_ids", []
            )
        )
        part["dispositions"] = [
            d for d in part["dispositions"] if d["candidate_id"] not in deferred
        ]
        write_json(run.disposition_part(sid), part)
    path, findings = seal.seal(run)
    assert findings == [], findings
    findings = intake.admit_from_triage(run)
    assert findings == [], findings
    return run
```

Then replace the two `build_toy_run(tmp_path, upto="intake")` calls in the first
test and the `...` in the third with `phase_run_through_intake(tmp_path)`. The
second test keeps `build_toy_run(tmp_path, upto="intake")` — it is the negative
control. Add `from rubrica import intake` to the imports.

- [ ] **Step 4: Add `phase` to the manifest schema**

In `src/rubrica/schema/manifest-0.1.json`, add to `properties` (beside `limits`):

```json
    "phase": {"$ref": "triage-0.1.json#/$defs/phase"},
```

Optional, not required, for `max_scenario_part_bytes`' documented reason: making it
required would invalidate every manifest already on disk, and `diff-runs`,
`run-summary` and `gate-brief` all read those.

- [ ] **Step 5: Carry the block in `admit_from_triage`**

In `src/rubrica/intake.py`, where the manifest document is built, add:

```python
    # The phase, carried from the sealed triage record with the one number this
    # stage is the right place to compute. `deferred_kinds` and `number` are copied
    # verbatim -- gate 0 ratified them and a re-derivation here would be a second
    # answer -- while `deferred_count` is added because reconcile-seal reads the
    # manifest and never 00-triage.json, so the count has no other way to reach the
    # world model that reports it.
    #
    # Counted from the record's own dispositions rather than from the plan, so the
    # number describes what was actually sealed. refs.check_admitted_inputs
    # recomputes it, which makes it arithmetic a reader can check rather than
    # testimony -- check_slices' `bytes` discipline, one artifact later.
    phase_block = phase.read(triage)
    if phase_block is not None:
        manifest["phase"] = {
            "number": phase_block.get("number"),
            "deferred_kinds": list(phase_block.get("deferred_kinds") or []),
            "deferred_count": sum(
                1
                for d in triage.get("dispositions") or []
                if isinstance(d, dict) and d.get("disposition") == phase.DEFER
            ),
        }
```

Add `from rubrica import phase` to `intake.py`'s imports.

- [ ] **Step 6: Recompute the count in `check_admitted_inputs`**

That checker already reads both `00-triage.json` and `manifest.json`, so the clause
costs no new plumbing. Append it before the existing `return out`:

```python
    # The deferred count, recomputed. It is the only number in the phase block that
    # intake derives rather than copies, so it is the only one that can be wrong
    # without the plan being wrong too -- and a world model reporting that 68 inputs
    # were deferred when the record shows 4 would misstate the analysis to the
    # people the target-brief is written for.
    #
    # Silent when the manifest declares no phase: a run without one has nothing to
    # recompute, and a finding there would fire on every pre-phasing run on disk.
    manifest_phase = phase.read(manifest)
    if manifest_phase is not None:
        declared = manifest_phase.get("deferred_count")
        actual = sum(
            1
            for entry in _as_list(triage.get("dispositions"))
            if isinstance(entry, dict) and entry.get("disposition") == phase.DEFER
        )
        if declared != actual:
            out.append(
                Finding(
                    run.manifest,
                    "refs",
                    "/phase/deferred_count",
                    f"the manifest declares deferred_count={declared} but {run.triage.name} "
                    f"carries {actual} defer disposition(s)",
                )
            )
```

- [ ] **Step 7: Add the negative control**

Append to `tests/unit/test_refs_admitted.py`:

```python
def test_a_wrong_deferred_count_in_the_manifest_is_a_finding(tmp_path):
    """The direction that makes the clause a guard. Measured the other way by
    test_phase_pipeline's clean assertion over the same run."""
    run = phase_run_through_intake(tmp_path)
    manifest = json.loads(run.manifest.read_text())
    manifest["phase"]["deferred_count"] = 68
    write_json(run.manifest, manifest)
    findings = refs.check_admitted_inputs(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/phase/deferred_count"
    assert findings[0].path == run.manifest
```

Import `phase_run_through_intake` from `tests.unit.test_phase_pipeline`, or move it
to `tests/toy.py` if that module already hosts cross-module helpers — check
`tests/toy.py` first, as CLAUDE.md warns that nearly every request for a new
checkpoint turned out to be for one that already existed.

- [ ] **Step 8: Run the tests, then the full suite and the other two gates**

Run: `uv run pytest tests/unit/test_phase_pipeline.py tests/unit/test_refs_admitted.py -q`
Expected: PASS

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/rubrica/schema/manifest-0.1.json src/rubrica/intake.py src/rubrica/refs.py \
        tests/unit/test_phase_pipeline.py tests/unit/test_refs_admitted.py
git commit -S -s -m "$(cat <<'MSG'
feat(intake): Carry the phase into the manifest and count the deferrals

`number` and `deferred_kinds` are copied verbatim -- gate 0 ratified them, and a
re-derivation would be a second answer to a question already settled.
`deferred_count` is added here because intake is the stage that knows it exactly
and reconcile-seal reads the manifest and never 00-triage.json, so the count has
no other route to the world model that reports it.

check_admitted_inputs recomputes the count, which makes it arithmetic a reader can
check rather than testimony -- check_slices' `bytes` discipline one artifact later.
The number matters beyond tidiness: a world model claiming 68 inputs were deferred
when the record shows 4 would misstate the analysis to the people target-brief is
written for.

`phase` is optional in the manifest schema on max_scenario_part_bytes' precedent:
requiring it would invalidate every manifest already on disk, and diff-runs,
run-summary and gate-brief all read those.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---
### Task 5: `reconcile-seal` records the world model's own incompleteness

The world model is the interface to the benchmark half, and the artifact
`target-brief` renders for the people who own the target. A phase-1 model showing
85 contradictions without stating that 119 more are unread would misrepresent the
analysis, and the tool currently has no way to say it.

The two skipped passes need no code: `reconcile.seal` reads
`list_json(run.contradictions_dir)`, which yields nothing for an absent directory,
and never reads `01-subjects.json` at all; `refs.check_subjects` returns `[]` when
the cover is absent, `refs.check_contradiction_parts` returns `[]` when either the
cover or the directory is; `refs.PASS_OWN_KINDS` has no row for either pass; and
`refs.check_readable` skips a path that is not a file. All five were verified
against the code. What this task adds is the **assertion** that they hold, so a
later change that breaks the skip reddens here.

**Files:**
- Modify: `src/rubrica/schema/world-model-0.1.json`
- Modify: `src/rubrica/reconcile.py:181-390` (`seal`)
- Test: `tests/unit/test_phase_pipeline.py`, `tests/unit/test_reconcile_seal.py`

**Interfaces:**
- Consumes: `manifest.json`'s `phase` (Task 4).
- Produces: `01-world-model.json` `phase` = the manifest's block, verbatim.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_phase_pipeline.py`:

```python
def test_the_world_model_records_its_own_incompleteness(tmp_path):
    """Load-bearing rather than informational: target_brief and run-summary both read
    this to say on the page that part of the corpus is unread. Without it a reader is
    shown a contradiction count with no way to know it is a floor."""
    run = phase_run_through_seal(tmp_path)  # see step 3
    world = json.loads(run.world_model.read_text())
    assert world["phase"] == {
        "number": 1,
        "deferred_kinds": ["trace"],
        "deferred_count": 1,
    }


def test_a_world_model_from_a_phaseless_run_has_no_phase_key(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert "phase" not in json.loads(run.world_model.read_text())


def test_the_two_forensic_passes_can_be_skipped_entirely(tmp_path):
    """The saving this whole design is for: subjects and contradict were 91 and 81
    minutes and $73.40 together, and with traces deferred they would have had roughly
    half their material.

    Nothing in reconcile.seal or in layer 2 needed a change to allow this -- the seal
    never reads 01-subjects.json and iterates an absent 01-contradictions/ to nothing,
    and both layer-2 checkers over them return early on an absent cover. This test is
    what turns those five verified facts into a guard, so a later change that makes
    either pass required reddens here rather than at a $70 dispatch.
    """
    run = phase_run_through_seal(tmp_path)
    assert not run.subjects.is_file()
    assert not run.contradictions_dir.exists()
    world = json.loads(run.world_model.read_text())
    # `contradictions` is required by world-model-0.1.json, so it must be present
    # and empty rather than absent -- an empty list is the honest record of a sweep
    # that did not run, and the phase block above is what says why.
    assert world["contradictions"] == []
    assert refs.check_subjects(run) == []
    assert refs.check_contradiction_parts(run) == []
    assert refs.check_readable(run) == []
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_phase_pipeline.py -q -k world_model or forensic`
Expected: FAIL — `NameError: name 'phase_run_through_seal' is not defined`

- [ ] **Step 3: Add the through-seal helper to the test module**

```python
def phase_run_through_seal(tmp_path, *, number=1, kinds=("trace",)):
    """A phase run carried to a sealed world model, with the two forensic passes
    never run.

    Built from the toy's own reconcile checkpoint and then stripped of the two
    artifacts a phase-1 run would never have produced, rather than by re-running the
    01 band: what is under test is the seal and the checkers, not the toy's ability
    to build a claims directory. Stripping rather than skipping is honest here
    because the artifacts' *absence* is the whole input -- a run that skipped the
    passes and one whose outputs were removed are the same run on disk.
    """
    run = phase_run_through_intake(tmp_path)
    # Carry the toy's own claims and partials into the phase run: extract and the
    # six kept reconcile passes are unaffected by phasing, and re-deriving them here
    # would test tests/toy.py rather than this feature.
    donor = build_toy_run(tmp_path / "donor", upto="reconcile-services")
    for source, destination in (
        (donor.claims_dir, run.claims_dir),
        (donor.capabilities_part, run.capabilities_part),
        (donor.outcomes_part, run.outcomes_part),
        (donor.entities_part, run.entities_part),
        (donor.goals_part, run.goals_part),
        (donor.gaps_part, run.gaps_part),
        (donor.services_part, run.services_part),
    ):
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    # The two a phase-1 run never produces. Removed rather than never created,
    # because the donor built them.
    run.subjects.unlink(missing_ok=True)
    shutil.rmtree(run.contradictions_dir, ignore_errors=True)
    path, findings = reconcile.seal(run)
    assert findings == [], findings
    assert path == run.world_model
    return run
```

Add `import shutil` and `from rubrica import reconcile` to the module's imports.

If the copied claims name artifact ids the phase run's manifest does not register —
the donor admitted `trace-json` and the phase run did not — delete that claims file
and the citations to it, or build the donor from a catalogue with the trace already
absent. Resolve it whichever way keeps `refs.check_manifest` clean, and add an
assertion that it is:

```python
    assert refs.check_manifest(run) == []
```

- [ ] **Step 4: Add `phase` to the world-model schema**

In `src/rubrica/schema/world-model-0.1.json`, add to `properties` (beside
`denominator`):

```json
    "phase": {"$ref": "triage-0.1.json#/$defs/phase"},
```

Optional and absent on a run that declared none, so a full run's world model is
byte-identical to one written before this field existed. This is the only one of
the four carries where the block's *presence* is read by a report rather than by a
stage: `target-brief` and `run-summary` both render it, and that is what makes it
load-bearing rather than informational.

- [ ] **Step 5: Carry the block in `reconcile.seal`**

The seal already reads the manifest for `target`. Where the world-model document is
assembled, add:

```python
    # Carried verbatim from the manifest, which is the only artifact in this band
    # that holds it -- the seal reads no triage record and no plan. Verbatim rather
    # than recomputed for the reason every other carry in this chain is: the
    # declaration was ratified at gate 0, and a re-derivation five stages later is a
    # second answer to a settled question.
    #
    # Load-bearing rather than informational. A phase-1 model showing 85
    # contradictions without stating that 119 more are unread would misrepresent the
    # analysis to the people target-brief is written for, and until this field
    # existed the tool had no way to say it. run-summary renders it for the same
    # reason.
    phase_block = phase.read(manifest)
    if phase_block is not None:
        world_model["phase"] = phase_block
```

Add `from rubrica import phase` to `reconcile.py`'s imports.

- [ ] **Step 6: Assert the byte-shape guarantee still holds**

Append to `tests/unit/test_reconcile_seal.py`:

```python
def test_two_seals_of_the_same_phase_partials_are_byte_identical(tmp_path):
    """reconcile-seal is code for one reason: two runs with identical partials must
    produce a byte-identical world model, or variance can no longer be attributed to
    a stage. The phase block is a verbatim carry, so it cannot weaken that -- and
    this is where "cannot" is measured rather than argued."""
    run = phase_run_through_seal(tmp_path)
    first = run.world_model.read_bytes()
    run.world_model.unlink()
    path, findings = reconcile.seal(run)
    assert findings == []
    assert run.world_model.read_bytes() == first
```

- [ ] **Step 7: Run the tests, then the full suite and the other two gates**

Run: `uv run pytest tests/unit/test_phase_pipeline.py tests/unit/test_reconcile_seal.py -q`
Expected: PASS

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/schema/world-model-0.1.json src/rubrica/reconcile.py \
        tests/unit/test_phase_pipeline.py tests/unit/test_reconcile_seal.py
git commit -S -s -m "$(cat <<'MSG'
feat(reconcile-seal): Record the world model's own incompleteness

A phase-1 model showing 85 contradictions without stating that 119 more are unread
would misrepresent the analysis to the people target-brief is written for, and the
tool had no way to say it. The block is a verbatim carry from the manifest, so the
seal's byte-identity guarantee is untouched -- and a test now measures that rather
than arguing it.

Skipping reconcile-subjects and reconcile-contradict needed no code. The seal never
reads 01-subjects.json and iterates an absent 01-contradictions/ to nothing;
check_subjects and check_contradiction_parts both return early on an absent cover;
PASS_OWN_KINDS has no row for either pass; and check_readable skips a path that is
not a file. All five were verified against the code, and this commit turns them into
a guard so a later change that makes either pass required reddens in the suite
rather than at a $70 dispatch.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 6: `gate-brief` and `run-summary` show the deferrals

Both currently bucket dispositions into admits and declines-by-reason-code and drop
anything else, so 68 deferred inputs would be absent from the gate-0 reading surface
and the run-summary page with nothing saying so. Both are reports, not gates: each
must still exit 0 on any readable run.

**Files:**
- Modify: `src/rubrica/brief.py` (`_gate_0` around 1215-1265, `_gate_1`)
- Modify: `src/rubrica/summary.py:555-590` (`_dispositions` and its `Dispositions` dataclass)
- Modify: `src/rubrica/summary_html.py:478-511` (the disposition tables)
- Test: `tests/unit/test_brief.py`, `tests/unit/test_summary.py` (or the module the repo already uses for `_dispositions`)

**Interfaces:**
- Consumes: `00-triage.json`'s `phase` and defers; `manifest.json`'s `phase`.
- Produces:
  - `brief.DEFERRED_HEADER = "Deferred to a later phase"` — a named constant, on
    the existing gate-0 header pattern, because it is the anchor a test scopes to.
  - `summary.Dispositions` gains `defers: list[dict]` and `defer_count: int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_brief.py`:

```python
def test_gate_0_reports_the_deferrals_as_their_own_group(tmp_path):
    """The design's own argument, applied to the surface that carries it: collapsing
    defer into decline would tell the operator 68 inputs were judged useless, and
    showing neither tells them nothing at all. The group is separate from the
    declines and says which phase and which kinds."""
    run = phase_run_through_intake(tmp_path)
    page = brief.compose(run, 0)
    assert brief.DEFERRED_HEADER in page
    section = page[page.index(brief.DEFERRED_HEADER) :]
    assert "trace-json" in section
    # The two facts a human needs to overturn the deferral, on the page.
    assert "trace" in section and "phase 1" in section
    # And it is not filed under a decline reason code, which is what the design
    # forbids: the deferred candidate must not appear in the declines group.
    declines = page[page.index("Declines, by reason code") : page.index(brief.DEFERRED_HEADER)]
    assert "trace-json" not in declines


def test_gate_0_omits_the_deferred_group_when_nothing_was_deferred(tmp_path):
    """The negative control. A header with an empty body on every phaseless run
    would train a reader to skip it, which is how the one run that does defer
    something gets skipped too."""
    run = build_toy_run(tmp_path, upto="intake")
    assert brief.DEFERRED_HEADER not in brief.compose(run, 0)


def test_gate_1_says_the_world_model_is_incomplete_by_declaration(tmp_path):
    """Gate 1 reviews an inference about the target, and a reader ratifying a
    contradiction tally needs to know it is a floor rather than a count."""
    run = phase_run_through_seal(tmp_path)
    page = brief.compose(run, 1)
    assert "phase 1" in page
    assert "trace" in page


def test_gate_brief_still_exits_zero_on_a_phase_run_with_a_malformed_phase_block(tmp_path):
    """A report is never a gate. Gate 0 explicitly invites a hand-edited record, so a
    phase block that is not an object -- or one whose deferred_kinds is a string --
    must render as its own absence rather than raising."""
    run = phase_run_through_intake(tmp_path)
    triage = json.loads(run.triage.read_text())
    triage["phase"] = "one"
    write_json(run.triage, triage)
    page = brief.compose(run, 0)
    assert isinstance(page, str) and page
```

Append the summary tests to whichever module owns `summary._dispositions`:

```python
def test_the_disposition_bucket_counts_defers_separately(tmp_path):
    """summary.py bucketed on `if admit ... elif decline ...`, so a defer fell out of
    both and 68 inputs would have been absent from the page with nothing saying so."""
    run = phase_run_through_intake(tmp_path)
    result = summary._dispositions(run)
    assert result.defer_count == 1
    assert [d["candidate_id"] for d in result.defers] == ["trace-json"]
    # Neither of the other two buckets absorbed it.
    assert all(d["candidate_id"] != "trace-json" for d in result.admits)
    assert all(
        d["candidate_id"] != "trace-json"
        for group in result.declines_by_reason.values()
        for d in group
    )


def test_the_page_renders_the_deferred_table_only_when_there_are_defers(tmp_path):
    run = phase_run_through_intake(tmp_path)
    assert "trace-json" in summary_html.render(run)
    plain = build_toy_run(tmp_path / "plain", upto="intake")
    # The negative control is the *table*, not the id: a phaseless run has no
    # deferred section at all rather than an empty one.
    assert "Deferred" not in summary_html.render(plain)
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/unit/test_brief.py tests/unit/test_summary.py -q -k defer or phase`
Expected: FAIL — `AttributeError: module 'rubrica.brief' has no attribute 'DEFERRED_HEADER'`,
and `Dispositions` has no `defer_count`.

- [ ] **Step 3: Add gate 0's deferred group**

In `src/rubrica/brief.py`, add the header constant beside the existing four
(after `READ_COST_HEADER` at line 182):

```python
# Gate 0's deferred group. Named here with its three siblings for the reason the
# comment above them gives: it is the anchor a reader and a test both scope to, and
# a rewording landing in only one of two places would silently unscope an assertion
# to the whole document.
DEFERRED_HEADER = "Deferred to a later phase"
```

In `_gate_0`, after the declines group is rendered, add the deferred group. It is
rendered only when the record actually defers something — a header with an empty
body on every phaseless run trains a reader to skip it, which is how the one run
that does defer something gets skipped too.

```python
    defers = [d for d in dispositions if d.get("disposition") == phase.DEFER]
    if defers:
        block = phase.read(triage)
        number = block.get("number") if block else None
        kinds = sorted(phase.deferred_kinds(block))
        lines.append(DEFERRED_HEADER)
        # The declaration first, then the candidates it caught. A reader deciding
        # whether to overturn the deferral needs the flag, not 68 rows: the rows are
        # the consequence, and the two facts that make it reversible are the kind
        # list and the phase number.
        #
        # `str()` on the number and a plain join on the kinds, both for gate 0's own
        # reason: the block is read from a hand-editable record without validating
        # it, so a number that is not one renders as itself rather than raising out
        # of a report whose whole ruling is that it exits 0.
        lines.append(
            f"  declared: phase {number}, deferring "
            f"{_and_join(kinds) if kinds else '(no kind recorded)'}"
        )
        lines.append(
            f"  {len(defers)} candidate(s) held for a later phase, not declined: these carry "
            "evidence value this phase cannot spend, and nothing downstream of intake will "
            "read them."
        )
        for d in defers:
            cid = d.get("candidate_id")
            candidate = candidates.get(cid) if isinstance(cid, str) else None
            raw = candidate.get("bytes") if candidate is not None else None
            bytes_note = f" ({raw} bytes)" if isinstance(raw, int) and not isinstance(raw, bool) else ""
            lines.append(f"  - {cid if cid is not None else '?'}{bytes_note}: {d.get('reason', '')}")
        lines.append("")
```

Add `from rubrica import phase` to `brief.py`'s imports.

- [ ] **Step 4: Add gate 1's incompleteness note**

In `_gate_1`, before the reconcile sweep block, add:

```python
    # Gates 1 through 3 review a judgment made from evidence already in the run, and
    # a reader ratifying this one needs to know the evidence was bounded by
    # declaration rather than by what the corpus held. Without this the contradiction
    # tally below reads as a count when it is a floor.
    block = phase.read(_quietly(run.world_model))
    if block is not None:
        kinds = sorted(phase.deferred_kinds(block))
        count = block.get("deferred_count")
        lines.append(
            f"This run declared phase {block.get('number')} and deferred "
            f"{_and_join(kinds) if kinds else '(no kind recorded)'}: "
            f"{count} admitted-eligible candidate(s) were never extracted, so every tally "
            "below is a floor rather than a count. The contradiction sweep and the subject "
            "cover were not run at all."
        )
        lines.append("")
```

- [ ] **Step 5: Add summary's third bucket**

In `src/rubrica/summary.py`, extend the `Dispositions` dataclass with
`defers: list[dict]` and `defer_count: int`, and add the branch in `_dispositions`:

```python
    defers: list[dict] = []
    for member in _dicts(payload.get("dispositions")):
        if member.get("disposition") == "admit":
            admits.append(member)
        elif member.get("disposition") == "decline":
            ...  # unchanged
        elif member.get("disposition") == phase.DEFER:
            # A third bucket rather than a third reason code group. The branch above
            # was an `elif decline` with no `else`, so a defer fell out of both and
            # every deferred input was absent from the page -- which for the corpus
            # this was measured on is 68 of 149 inputs vanishing with nothing saying
            # so. Grouping them under a decline code instead would report them as
            # judged useless, which is what the disposition split exists to prevent.
            defers.append(member)
```

Sort them for the same reason the decline groups are sorted — two runs of the same
pipeline must render the same table for the page to be diffable:

```python
    defers.sort(key=admit_sort_key)
```

`admit_sort_key` is documented total and coerces an absent `priority` to the
sentinel, so it does not raise on the synthesised rulings, which carry none.

Add `defers=defers, defer_count=len(defers)` to the `Dispositions(...)` return, and
`from rubrica import phase` to the imports.

- [ ] **Step 6: Render the third table**

In `src/rubrica/summary_html.py`, add a table beside the existing two at 495-511,
using the same column tuple shape. `authority` is worth a column here in a way it is
not for the admits: every deferred row carries `policy`, which is what tells a
reader nobody ruled on these one at a time.

```python
        # Rendered only when there are defers, matching the gate-0 brief: an empty
        # section on every phaseless run trains a reader to skip the one place it
        # matters.
        ("candidate_id", "authority", "reason"),
```

- [ ] **Step 7: Run the tests, then the full suite and the other two gates**

Run: `uv run pytest tests/unit/test_brief.py tests/unit/test_summary.py -q`
Expected: PASS

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/brief.py src/rubrica/summary.py src/rubrica/summary_html.py \
        tests/unit/test_brief.py tests/unit/test_summary.py
git commit -S -s -m "$(cat <<'MSG'
feat(reports): Show the deferrals at gate 0 and on the run-summary page

Both surfaces bucketed dispositions into admits and declines-by-reason-code with no
third branch, so every deferred input was absent from the gate-0 reading surface and
the summary page with nothing saying so -- 68 of 149 inputs on the corpus this was
measured against. The design's argument against collapsing defer into decline (it
would report those inputs as judged useless) applies at least as strongly to
reporting nothing.

Gate 0 leads with the declaration rather than the rows: a reader deciding whether to
overturn a deferral needs the flag and the kind list, and the candidates are the
consequence. Gate 1 says the tallies below it are floors rather than counts, because
a reader ratifying an inference needs to know its evidence was bounded by
declaration and not by what the corpus held.

Both stay reports rather than gates: each renders a malformed phase block as its own
absence and still exits 0, which gate 0 invites by design.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---
### Task 7: `target-brief` discloses the deferral, in the recipient's own words

The page written for the people who own the target. The spec calls this the reason
the world model's `phase` block is load-bearing: "a brief that shows the parsec team
85 contradictions without stating that 119 more are unread would misrepresent the
analysis, and the current tool has no way to say it."

**This task has a hard constraint no other task has.** Two tests enforce that no
heading, label or sentence the renderer writes names a stage, a gate, an artifact or
rubrica itself. The banned list is literal, in
`tests/unit/test_target_brief_html.py:578-587`: `reconcile`, `extract`, `triage`,
`world model`, `claim`, `artifact`, `gate`, `manifest`, `rubrica`, `scenario`. It is
checked against the lower-cased page with `_LEGEND` subtracted. So the disclosure
cannot say "we deferred trace inputs at triage" — it must say what was not read, in
the vocabulary the page already uses for input kinds. `_KIND_LABELS` at
`target_brief_html.py:278-286` maps `trace` to **"Recorded interactions"**, and that
is the phrase to build on.

`target-brief` also exits **0** on an unreadable `01-claims/`, where
`claim-utilisation` and `gate-brief` exit 2 — it has no number to be quietly wrong,
so it says at the top that it could not cite its sources and describes the target
anyway. The disclosure must follow that discipline: it is a statement about
completeness, so a malformed phase block renders as no disclosure rather than as a
false reassurance.

**Files:**
- Modify: `src/rubrica/target_brief.py` (a `completeness(run)` reader beside `headline`)
- Modify: `src/rubrica/target_brief_html.py` (render it above the collapsed description)
- Test: `tests/unit/test_target_brief.py`, `tests/unit/test_target_brief_html.py`

**Interfaces:**
- Consumes: `01-world-model.json`'s `phase` (Task 5); `target_brief_html._KIND_LABELS`.
- Produces: `target_brief.completeness(run) -> Completeness | None`, a frozen
  dataclass carrying `kind_labels: tuple[str, ...]` and `count: int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_target_brief.py`:

```python
def test_completeness_is_none_without_a_phase_and_reports_the_labels_with_one(tmp_path):
    """The reader half. It returns the *recipient's* labels rather than the kinds,
    because the renderer must not be the place a kind is translated -- a second
    translation site is how one page ends up saying `trace` and another
    `Recorded interactions`."""
    plain = build_toy_run(tmp_path / "plain", upto="reconcile-seal")
    assert target_brief.completeness(plain) is None
    phased = phase_run_through_seal(tmp_path / "phased")
    result = target_brief.completeness(phased)
    assert result.kind_labels == ("Recorded interactions",)
    assert result.count == 1


def test_completeness_is_none_for_a_malformed_phase_block(tmp_path):
    """target-brief exits 0 on inputs the other two reports exit 2 on, because it has
    no number to be quietly wrong. A phase block it cannot read is no disclosure --
    never a claim that everything was read, which would be the one wrong answer."""
    run = phase_run_through_seal(tmp_path)
    world = json.loads(run.world_model.read_text())
    world["phase"] = {"number": 1, "deferred_kinds": "trace"}
    run.world_model.write_text(json.dumps(world))
    assert target_brief.completeness(run) is None


def test_completeness_falls_back_to_the_raw_kind_when_no_label_exists(tmp_path):
    """A kind the label map does not cover must render as itself rather than
    vanishing: a disclosure that silently dropped one of two deferred kinds would
    understate what went unread, which is the failure the disclosure exists to
    prevent."""
    run = phase_run_through_seal(tmp_path)
    world = json.loads(run.world_model.read_text())
    world["phase"] = {"number": 1, "deferred_kinds": ["trace", "not_a_kind"], "deferred_count": 2}
    run.world_model.write_text(json.dumps(world))
    result = target_brief.completeness(run)
    assert result.kind_labels == ("Recorded interactions", "not_a_kind")
```

Append to `tests/unit/test_target_brief_html.py`:

```python
def test_the_page_states_what_was_not_read_when_the_run_deferred_something(tmp_path):
    """The spec's own case: showing an owner a disagreement count without saying that
    a whole class of material went unread misrepresents the analysis. The sentence
    leads the page rather than sitting in the collapsed description, because it
    changes how every number below it should be read."""
    run = phase_run_through_seal(tmp_path)
    page = target_brief_html.render(run)
    assert "Recorded interactions" in page
    assert "have not read" in page
    # Above the collapsed description, so it is not something a reader has to expand
    # to find.
    assert page.index("Recorded interactions") < page.index("<details")


def test_the_page_says_nothing_about_completeness_on_a_full_run(tmp_path):
    """The negative control. A page that always carried a caveat would make the
    caveat invisible on the run that needs it."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert "have not read" not in page


def test_the_completeness_sentence_carries_none_of_this_projects_vocabulary(tmp_path):
    """The constraint that makes this task different from the other six. The
    existing whole-page test measures the renderer's chrome on a corpus whose prose
    carries none of the banned words; this one is scoped to the new sentence, so a
    reword that reintroduces `trace` or `world model` reddens here with the offending
    word named rather than somewhere in a 40-line page comparison.

    `phase` is deliberately absent from the assertion below and from the sentence: it
    is this project's word for its own process, and an owner reading "phase 1" has
    been handed a question about our schedule instead of about their system."""
    run = phase_run_through_seal(tmp_path)
    sentence = target_brief_html._completeness_lines(target_brief.completeness(run))
    text = " ".join(sentence).lower()
    for word in (
        "reconcile",
        "extract",
        "triage",
        "world model",
        "claim",
        "artifact",
        "gate",
        "manifest",
        "rubrica",
        "scenario",
        "phase",
        "defer",
        "trace",
    ):
        assert word not in text, word
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/unit/test_target_brief.py tests/unit/test_target_brief_html.py -q -k completeness`
Expected: FAIL — `AttributeError: module 'rubrica.target_brief' has no attribute 'completeness'`

- [ ] **Step 3: Add the reader to `target_brief.py`**

Follow the module's existing `Marker`/dataclass conventions — read `headline` and
`inputs_read` first and match them. The label map lives in `target_brief_html`, so
import it rather than restating it; if that creates a cycle, move `_KIND_LABELS` into
`target_brief.py` and have the HTML module import it from there, which is the
direction the data already flows.

```python
@dataclass(frozen=True)
class Completeness:
    """What we did not read, in the labels the recipient's page already uses.

    Holds labels rather than kinds deliberately: the renderer must not be a second
    place a kind is translated, or one page ends up saying `trace` where another says
    `Recorded interactions`. The count is carried alongside because "we did not read
    some of it" and "we did not read 68 files of it" are different statements, and the
    second is the one an owner can act on.
    """

    kind_labels: tuple[str, ...]
    count: int


def completeness(run: RunPaths) -> Completeness | None:
    """What this run declared it would not read, or None.

    None on three shapes and the difference matters: a run that declared no phase, a
    run whose world model could not be read, and a run whose phase block is
    malformed. All three produce no disclosure, and none of them produces a statement
    that everything *was* read -- which is the one wrong answer available here, and
    the reason this returns None rather than an empty Completeness.

    Exits nothing and raises nothing, following this module's rule: `target-brief`
    exits 0 where claim-utilisation and gate-brief exit 2, because it has no number to
    be quietly wrong. A page missing this sentence is a page that says less; a page
    asserting completeness it cannot support is a page that misleads the people who
    own the target.
    """
    block = phase.read(_world(run) if isinstance(_world(run), dict) else None)
    if block is None:
        return None
    kinds = sorted(phase.deferred_kinds(block))
    if not kinds:
        return None
    count = block.get("deferred_count")
    if not isinstance(count, int) or isinstance(count, bool):
        # A count we cannot read is dropped to 0 rather than dropping the whole
        # sentence: "we have not read your recorded interactions" is true and useful
        # without a number, and suppressing it because the number is malformed would
        # trade a complete disclosure for a missing one.
        count = 0
    # A kind with no label renders as itself. Dropping it would understate what went
    # unread, which is the failure this whole sentence exists to prevent.
    labels = tuple(_KIND_LABELS.get(kind, kind) for kind in kinds)
    return Completeness(kind_labels=labels, count=count)
```

- [ ] **Step 4: Render it in `target_brief_html.py`**

Add a named function so the vocabulary test can scope to it, and call it above the
collapsed `<details>` description. The wording below carries none of the banned words
and none of `phase`, `defer` or `trace`; keep it that way if you reword it.

```python
def _completeness_lines(completeness) -> list[str]:
    """The sentence that says what we did not read, or nothing.

    Its own function so a test can scope to the sentence rather than diffing a whole
    page, and so the wording sits in one place: every word here is checked against
    this project's own vocabulary, because a recipient reading about our process has
    been handed the wrong question. `phase`, `defer` and the raw kind names are
    excluded along with the stage and artifact words -- an owner asked to correct a
    description should not have to learn our schedule to do it.

    Placed above the collapsed description rather than inside it, because it changes
    how every number below should be read, and a caveat a reader has to expand to
    find is a caveat for the reader who already knew.
    """
    if completeness is None:
        return []
    what = _and_join(list(completeness.kind_labels))
    how_many = (
        f" We set aside {completeness.count} such file(s)."
        if completeness.count
        else ""
    )
    return [
        '<p class="completeness">',
        f"We have not read this system's {what.lower()} yet.{how_many} Everything below "
        "comes from its written material and its code, so where those disagree we have "
        "said so -- but anything only visible in how the system actually behaves is not "
        "yet part of this description.",
        "</p>",
    ]
```

Reuse whatever join helper the module already has instead of `_and_join` if the name
differs; check `target_brief_html.py` for its existing prose helpers first.

- [ ] **Step 5: Run the tests, then the full suite and the other two gates**

Run: `uv run pytest tests/unit/test_target_brief.py tests/unit/test_target_brief_html.py -q`
Expected: PASS — including
`test_the_pages_own_prose_never_names_a_stage_a_gate_or_an_artifact`, which now
renders a page the new sentence is absent from (the toy declares no phase) and is
therefore unaffected. If it reddens, the sentence has leaked a banned word.

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/target_brief.py src/rubrica/target_brief_html.py \
        tests/unit/test_target_brief.py tests/unit/test_target_brief_html.py
git commit -S -s -m "$(cat <<'MSG'
feat(target-brief): Say what we did not read, in the recipient's own words

This is the case the world model's phase block was made load-bearing for: showing an
owner 85 disagreements without stating that 119 more went unread misrepresents the
analysis, and the tool had no way to say it.

The sentence carries none of this project's vocabulary -- not the stage, gate and
artifact words two tests already ban, and not `phase`, `defer` or the raw kind names
either. An owner asked to correct a description of their own system should not have
to learn our schedule to do it, so the disclosure speaks in the labels the page
already uses for input kinds. A third test scopes to the sentence itself, so a
reword that reintroduces a banned word reddens with the word named rather than
somewhere in a whole-page comparison.

It sits above the collapsed description because it changes how every number below
should be read, and a caveat a reader has to expand to find is a caveat for the
reader who already knew. A malformed block renders as no disclosure and never as a
claim that everything was read, which is the one wrong answer available here.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 8: the two prompts that need to know

Two skills read an artifact that now carries the phase and would act wrongly without
noticing it. Neither needs a contract change: `rb-triage-objective` already declares
`reads = ["slices"]` and `rb-orchestrate` already declares `manifest`.

`rb-triage-rule` is deliberately **not** edited — deferred candidates never reach a
shard, so it has nothing to know. `rb-triage-audit` is deliberately not edited
either; see Task 9's limitations entry for the ruling.

**Files:**
- Modify: `src/rubrica/skills/rb-triage-objective/SKILL.md`
- Modify: `src/rubrica/skills/rb-orchestrate/SKILL.md`
- Test: `tests/unit/test_skills*.py` (whichever module holds the section-scoped
  prompt assertions — find it with `grep -rl section_body tests/`)

**Interfaces:**
- Consumes: `00-slices.json`'s `phase` (Task 2); `manifest.json`'s `phase` (Task 4).
- Produces: no code interface. The assertions below are the deliverable.

- [ ] **Step 1: Write the failing tests**

Use `skills.section_body(skill, "<heading>")` for every assertion, never a
whole-file substring: `skills.load()` sets `body` to the entire file text and the
five section headings are mandatory, so `"phase" in body.lower()` is vacuous for a
conforming skill, and the frontmatter `description:` line plus the contract block
satisfy naive substring checks too.

```python
def test_the_objective_pass_is_told_deferred_material_is_not_absent_material():
    """rb-triage-objective rules whether the declared objective can be met at all,
    from the corpus map alone. Under a phase that map's slices carry
    deferred_candidate_ids, and a pass that read those as *missing* would either
    declare a meetable objective unmeetable or, worse, rule it meetable on the
    strength of material this phase will never read.

    Scoped to Inputs co-occurrence rather than presence anywhere in the file, which
    is this repo's rule: the contract block already contains the word `slices`.
    """
    skill = skills.load("rb-triage-objective")
    section = skills.section_body(skill, "1. Inputs").lower()
    assert "deferred_candidate_ids" in section
    assert "later phase" in section


def test_the_orchestrator_is_told_which_passes_a_phase_skips():
    """rb-orchestrate dispatches extract through emit and is the only party that can
    decline to dispatch a pass. The two it must skip are named in its Method section
    beside the manifest field that says so."""
    skill = skills.load("rb-orchestrate")
    section = skills.section_body(skill, "3. Method").lower()
    assert "phase" in section
    assert "reconcile-subjects" in section and "reconcile-contradict" in section


def test_the_orchestrator_refuses_to_declare_a_phase_itself():
    """Gate 0's argument, one stage further out. The party that selects the inputs
    must not also ratify the selection, and rb-orchestrate holds gates 1 through 3 --
    so an orchestrator that could declare a deferral would be narrowing the run's
    evidence and then reviewing the result of its own narrowing."""
    skill = skills.load("rb-orchestrate")
    section = skills.section_body(skill, "5. Refusal conditions").lower()
    assert "defer" in section
    assert "triage-slices" in section
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest -q -k objective_pass_is_told or orchestrator_is_told or refuses_to_declare`
Expected: FAIL — the strings are absent.

- [ ] **Step 3: Measure each predicate in both directions before committing it**

This is a required step, not a suggestion: roughly nineteen assertions in this repo
were *measured* satisfiable by unrelated content, and a predicate nobody has watched
fail is not yet a guard.

For each of the three tests, in a `/tmp` copy under `RUBRICA_SKILLS_DIR`:

```bash
cp -r src/rubrica/skills /tmp/skills-probe
# delete the paragraph the predicate claims to check, then:
RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run pytest -q -k <the test>   # must be RED
# restore it, reword it meaning-preservingly, then:
RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run pytest -q -k <the test>   # must be GREEN
```

Record the outcome in the commit body. If a predicate stays green with the prose
deleted, it is scoped to the wrong section or satisfied by the contract block — fix
the predicate, not the prose.

- [ ] **Step 4: Edit `rb-triage-objective`'s Inputs section**

Add a paragraph. It must state a *condition the pass can detect* and an *action it
can take*, or it is decorative:

```markdown
A slice entry may carry `deferred_candidate_ids`, and the plan may carry a
`phase` block naming the kinds this run defers. Those candidates are **held for a
later phase, not missing**: they were catalogued, they are recorded in the plan, and
a later run admits them. They are absent from the shards, so no member will rule on
them and nothing this run produces will cite them.

That distinction changes your ruling in one direction only. Judge whether the
objective can be met **by the material this phase will actually read** -- the
candidates that are not deferred. Do not rule an objective unmeetable on the ground
that deferred material is missing, and do not rule it meetable on the strength of
material this phase will never open. If the objective can only be met with the
deferred kinds, say exactly that in your verdict: it is the finding a human at gate 0
needs in order to reverse the deferral, and reversing it costs one re-run of a code
stage.
```

- [ ] **Step 5: Edit `rb-orchestrate`'s Method and Refusal sections**

In the Method section, beside the dispatch list at lines 227-228, add the branch:

```markdown
**If `manifest.json` carries a `phase` block**, do not dispatch
`rb-reconcile-subjects` or fan out `rb-reconcile-contradict`. Both are the forensic
half of the world model, both are the two slowest passes in the run, and with the
declared kinds deferred they would sweep roughly half their material for the full
price. `reconcile-seal` assembles a complete world model without them: it never reads
`01-subjects.json`, and it iterates an absent `01-contradictions/` to an empty
contradictions list. `check-refs` is clean over that run -- `check_subjects` and
`check_contradiction_parts` both return nothing when the cover is absent -- so a
finding against either is a defect to report, not a pass to go back and run.

Record the skip in `decisions.md` with the phase number and the deferred kinds, and
record no `manifest.stages` entry for either pass: a stage that was not dispatched has
no model, effort or skill digest to hash, and an entry claiming otherwise would make
`diff-runs` compare a pass that ran against one that did not.
```

In the Refusal conditions section, add:

```markdown
**You are asked to declare, change, or reverse a phase.** Refuse, and say where the
decision lives: `--phase` and `--defer-kind` are `triage-slices`' arguments, the
operator's to pass before gate 0, and reversing a deferral is a re-run of that code
stage. Deferring an input kind decides what the run can ever know -- nothing
downstream of `intake` reads the corpus again -- and you hold gates 1 through 3. An
orchestrator that could narrow the evidence and then review the result of its own
narrowing would make those three gates unfalsifiable, which is gate 0's argument
applied to you.
```

- [ ] **Step 6: Run the tests, then all three gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run rubrica check-skills`
Expected: all PASS. `check-skills` holds each contract to `paths.RunPaths` attribute
names, `validate.STAGE_ARTIFACTS` and `cli.SUBCOMMANDS`; neither contract block
changed, so it should stay 0. If it does not, a `reads` name was edited by accident.

- [ ] **Step 7: Commit**

```bash
git add src/rubrica/skills/rb-triage-objective/SKILL.md \
        src/rubrica/skills/rb-orchestrate/SKILL.md tests/unit/test_skills.py
git commit -S -s -m "$(cat <<'MSG'
feat(skills): Tell the objective pass and the orchestrator about the phase

Neither contract changed: rb-triage-objective already reads `slices` and
rb-orchestrate already reads `manifest`, so both facts arrive through a declared read
rather than through a widened one.

The objective pass needed the distinction between deferred and missing. It rules
whether the declared objective can be met at all, and a pass reading
deferred_candidate_ids as absence would either call a meetable objective unmeetable
or call it meetable on the strength of material this phase will never open. Its
instruction states the one action it can take -- judge against what this phase will
read, and say so in the verdict if the objective needs the deferred kinds, which is
what a human at gate 0 needs to reverse the deferral.

rb-orchestrate gets the skip and a refusal condition. The refusal is gate 0's
argument applied one stage out: an orchestrator that could declare a deferral would
narrow the run's evidence and then hold three gates reviewing the result of its own
narrowing.

Each of the three new predicates was measured in both directions under
RUBRICA_SKILLS_DIR -- red with the prose deleted, green after a meaning-preserving
reword -- because a predicate nobody has watched fail is not yet a guard.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---
### Task 9: documentation, and the limitations this design accepts

`tests/unit/test_docs_accuracy.py` gates most of this and its failure is the guard
working — update the document, never the assertion.

**Files:**
- Modify: `docs/reference/cli.md` (the `rubrica triage-slices` section)
- Modify: `docs/reference/artifacts.md` (the `phase` block on four kinds)
- Modify: `docs/concepts/pipeline.md` (the disposition set, and the two skippable passes)
- Modify: `docs/design/limitations.md` (five entries)
- Modify: `CLAUDE.md` (the exit-code and disposition prose it already carries)
- Test: `tests/unit/test_docs_accuracy.py`

**Interfaces:**
- Consumes: everything Tasks 1-8 produced.
- Produces: no code interface.

- [ ] **Step 1: Confirm which doc assertions are already red**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -q`
Expected: PASS at this point — no subcommand, stage or artifact *kind* was added, so
none of the parametrised presence checks fire. The documentation below is therefore
owed on the repo's own convention rather than forced by a red test, which makes it
easier to skip and no less required. `test_no_user_facing_document_carries_a_hand_typed_test_count`,
`test_no_heading_counts_something_that_grows` and
`test_no_shipped_markdown_cites_recorded_history` **do** gate the prose below, so run
this again at the end.

- [ ] **Step 2: Document the flags in `docs/reference/cli.md`**

In the `rubrica triage-slices` section, add `--phase N` and `--defer-kind KIND`
(repeatable). State the four things a reader needs and nothing more: that they are
declared together or not at all, that the kind list comes from the catalogue's own
kind enum, that the block is carried verbatim into `00-triage.json`,
`manifest.json` and `01-world-model.json`, and that re-running the command is how a
gate-0 decision is reversed. Name the exit codes: `2` for half a declaration or an
unknown kind, since both arrive from argv.

- [ ] **Step 3: Document the block in `docs/reference/artifacts.md`**

`phase` is not a new artifact *kind*, so no parametrised test demands an entry — but
four documented artifacts gain an optional field and a reader of any one of them
needs to know the other three carry it. Add it under `slices`, `triage`, `manifest`
and `world-model`, each entry saying who writes it and that it is a verbatim carry,
and state once that `deferred_count` is present only on the last two because the
first two enumerate the deferred set in full.

- [ ] **Step 4: Document the disposition in `docs/concepts/pipeline.md`**

Two additions. The disposition set gains `defer` with the promise it makes — value
this phase cannot spend, as against a decline's no evidence value — and a note that
`triage-seal` synthesises those rulings from the plan because no member ever sees a
deferred candidate. And the `01b`/`01c` rows gain a sentence: both are skipped under
a declared phase, `reconcile-seal` assembles a complete world model without them, and
`rb-orchestrate` is what declines to dispatch them.

Do **not** touch `docs/concepts/pipeline-diagram.html`: no stage was added or
renamed, so `ROWS` and the committed render are both still correct, and the page is
generated.

- [ ] **Step 5: Record the five limitations in `docs/design/limitations.md`**

Each with the ruling that parked it, matching the file's existing entry shape.

1. **A synthesised defer carries no `priority`.** The spec expected a deferred
   candidate to keep its member-assigned rank so phase 3 could consume triage's
   ranking directly. Under shard subtraction no member sees a deferred candidate, so
   there is no rank to keep, and inventing one in code would be a reasoned number
   presented as an observed one. Not a regression against the spec's own design,
   which delivers the promise for the mixed slices only — 15 of 68 deferred
   candidates on the measured corpus, with the other 53 in slices no member is
   dispatched for. Ruling: phase 3 re-slices the deferred population and dispatches
   `rb-triage-rule` over it, which is the pass whose judgment ought to rank inputs.

2. **`rb-triage-audit` cannot tell deferred material from absent material.** Its
   `reads` is `objective` and `dispositions_dir`, and the synthesised defer rulings
   are in neither — they are minted by `triage-seal`, after the audit runs. So the
   audit may raise a deficiency, and even propose a projection, for evidence a later
   phase will supply. Ruling: the contract is **not** widened. A `reads` addition
   needs to answer "does a deterministic gate already enforce this?", and the honest
   answer here is that no gate can — but the human at gate 0 reads both the audit's
   deficiencies and the deferred group `gate-brief` now renders, and is the right
   party to rule that one explains the other. Widening the audit's reads to
   `slices` was measured as the alternative and rejected: it would give the pass that
   audits the selection a view of the policy that shaped it.

3. **A phase-1 world model is not comparable to a full one** through
   `stability.diff-runs`. `_STAGE_FIELDS` compares `model`, `effort` and
   `skill_sha256` and does not read `phase`, so `diff-runs` will not itself object.
   The `phase` block is what makes the incomparability detectable rather than silent.
   Ruling: recorded, not fixed — widening `stability.py` is out of this design's
   scope.

4. **`deferred_kinds` is a kind-level instrument, so a valuable input is deferred
   along with the rest.** On the measured corpus that costs 23 goals, 1 gap, 4
   entities, 16 invariants and 85 of 204 contradictions. A per-candidate override is
   deliberately not designed: it would reintroduce the per-input judgment the whole
   design exists to avoid paying for.

5. **The 12%-cited figure for traces is a fact about one corpus at one objective.**
   A `depth` run, or a target whose behaviour is only observable in trajectories,
   could invert it. `--defer-kind` is per-run for that reason and has no default; a
   run that does not pass it behaves exactly as before.

Also record what phase 1 does **not** fix, since it is the thing most likely to be
misread as fixed: implied suite size at denominator v1 is 448 cells + 118 hop slots =
566, still far above the `max_scenarios` ceiling of 128. The target still needs
narrowing or the ceiling raising. What changes is the price of iterating on that
decision.

- [ ] **Step 6: Update `CLAUDE.md`**

Three small edits, and no new heading — `test_no_heading_counts_something_that_grows`
forbids one that counts stages, skills, subcommands or gates, and a "Phases" heading
would be one more thing to keep in step.

- In the `triage-rule` row's vicinity, note that a candidate of a deferred kind never
  reaches a shard, so `rb-triage-rule` has no phase branch.
- Beside the `reconcile-subjects`/`reconcile-contradict` rows, note that both are
  skipped under a declared phase and that their absence is not a finding — the same
  sentence form the file already uses for the code stages' missing
  `manifest.stages` entries.
- In the deterministic-subcommands list, add the ruling for `triage-slices`' new
  flags: the phase is declared there rather than at `intake` because `intake` mints
  `manifest.json` five stages later, and one declaration site is what stops two from
  disagreeing about what the run can know.

Run `make check` after editing — `CLAUDE.md` is not in ruff's `extend-exclude`.

- [ ] **Step 7: Run every gate**

```bash
uv run pytest -q
uv run ruff check && uv run ruff format --check
uv run rubrica check-skills
```

Expected: all PASS, `check-skills` exits 0.

- [ ] **Step 8: Commit**

```bash
git add docs/reference/cli.md docs/reference/artifacts.md docs/concepts/pipeline.md \
        docs/design/limitations.md CLAUDE.md
git commit -S -s -m "$(cat <<'MSG'
docs: Document the phase declaration and the five limitations it accepts

No subcommand, stage or artifact kind was added, so none of test_docs_accuracy's
parametrised presence checks forced this -- which is exactly why it is written down
now rather than owed.

Two of the five limitations are new findings from implementing the design rather than
restatements of it. A synthesised defer carries no `priority`, because under shard
subtraction no member ever ranked the candidate and a code-invented rank would be a
reasoned number wearing an observed one's clothes. And rb-triage-audit cannot tell
deferred material from absent material: the synthesised rulings are minted after it
runs, so it may raise a deficiency for evidence a later phase supplies. The audit's
contract is deliberately not widened -- giving the pass that audits the selection a
view of the policy that shaped it is the wrong remedy, and the human at gate 0 reads
both surfaces and is the right party to rule that one explains the other.

Also recorded: what phase 1 does not fix. Implied suite size stays 566 against a
max_scenarios ceiling of 128, so the target still needs narrowing or the ceiling
raising. What changes is the price of iterating on that decision.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

## Self-review

Run against the spec with fresh eyes after the plan was written.

**Spec coverage.** Every section maps to a task:

| Spec section | Task |
|---|---|
| `defer`, a third disposition | 1 |
| `decline_reason` gains `deferred_to_phase` | 1 |
| Eight `admit` call sites need no change | verified; two more do — Tasks 1 and 6 |
| Where deferral is decided (triage, not survey or extract) | 2 — `survey` is untouched |
| The manifest carries the phase | 4, with the declaration site moved to Task 2 |
| `triage-slices` marks fully-deferred slices | 2 |
| `rb-triage-rule` gains one instruction | **not needed** — subtraction removes it |
| `reconcile-seal` marks two passes not-required | 5 |
| The world model records its own incompleteness | 5 |
| `target_brief` and `summary` read it | 6, 7 |
| Phase 1 skips two passes | 5 (code), 8 (the orchestrator that declines to dispatch) |
| Phase 3's boundary | out of scope by the spec's own statement; Task 9 records it |
| Follow-ups (`rb-validate-traces`, repo split, effort tiering) | out of scope, unchanged |
| Limitations this design accepts | 9, plus two the spec did not have |

Two spec statements are contradicted rather than implemented, both argued in
**Three deviations** above and both load-bearing: the declaration site (the manifest
does not exist when `triage-slices` runs) and the retained `priority` (no member ranks
a candidate it never sees). One spec statement — `rb-triage-rule`'s instruction — is
made unnecessary rather than skipped.

**Placeholder scan.** Two `...` markers appear in Task 2 step 1 and one in Task 4
step 1; each is explicitly completed in a later step of its own task, and the plan
says so at the point of use. No other TBDs, no "add appropriate error handling", no
"similar to Task N", no test described without its code.

**Type consistency.** Checked across tasks:

- `phase.read`, `phase.deferred_kinds`, `phase.deferred_candidate_ids`, `phase.DEFER`,
  `phase.DEFER_REASON_CODE`, `phase.POLICY_AUTHORITY` — defined in Task 1, spelled
  identically in Tasks 2-7.
- `write_slices(run, *, cap, phase_block)` — the keyword is `phase_block`, not
  `phase`, in Task 2's definition and in every call in Tasks 3-7.
- `phase_run`, `phase_run_through_intake`, `phase_run_through_seal` — each defined in
  the task that first needs it (2, 4, 5) and reused by name afterwards.
- `brief.DEFERRED_HEADER`, `summary.Dispositions.defers`/`.defer_count`,
  `target_brief.completeness`/`Completeness.kind_labels`/`.count`,
  `target_brief_html._completeness_lines`, `validate.catalogue_candidate_kinds` — each
  named once and used consistently.
- `$defs/phase` lives in `triage-0.1.json` and is `$ref`'d by three other schemas;
  `deferred_count` is optional there so the plan and triage record may omit it while
  the manifest and world model carry it.

**One risk the executor should expect.** Task 5's `phase_run_through_seal` copies the
toy's claims and partials into a run whose manifest does not register `trace-json`.
`refs.check_manifest` holds that relation in both directions, so the donor's
`01-claims/trace-json.json` and every citation of its claims must go, or the donor
must be built from a catalogue without the trace. Task 5 step 3 names this and
requires a `check_manifest` assertion; it is the one step likely to need more than
five minutes.
