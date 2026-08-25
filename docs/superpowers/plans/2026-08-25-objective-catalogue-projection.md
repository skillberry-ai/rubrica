# Objective Catalogue Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move everything `rb-triage-objective` needs out of `00-catalogue.json` into a `catalogue_facts` block on `00-slices.json`, so the pass reads 51,792 bytes instead of 472,799 and its `reads` no longer names the catalogue at all.

**Architecture:** Three new public functions in `src/rubrica/slices.py` build the block from a catalogue; `write_slices` embeds it in the plan document. `refs.check_slices` gains two checks that recompute the block's two derived fields by calling those same functions — the precedent check 5 already sets with `row_bytes`. `rb-triage-objective`'s contract drops `catalogue` from `reads`, and its prose moves the boundedness prohibition from "never a digest in the catalogue" to "never a shard".

**Tech Stack:** Python 3.13+, standard library only. No new dependency. Tests are pytest against `tests/fixtures/toy/` via `survey.survey`, plus `tests/builders.py`'s `minimal_slices`.

**Spec:** `docs/superpowers/specs/2026-08-25-objective-catalogue-projection-design.md`

## Global Constraints

- **The field is named `catalogue_facts`, not `catalogue_projection`.** The spec (§4.1) specs the latter; it was changed during planning because `projection` already means *a manufactured artifact admitted to close a deficiency* in this exact subsystem — 90 occurrences in `triage.py`, 34 in `refs.py`, 23 in `artifacts.md`, plus `$defs/projection`, `projection_id` and `adopt-projection`. **The spec is not edited to match.** `docs/superpowers/` is recorded history: a record of what was decided is falsified, not corrected, by a later edit. This constraint is the record of the change.
- **Every commit uses both flags: `git commit -S -s`.** `-s` is the DCO trailer, `-S` the cryptographic signature. If signing fails, **stop and report it** — never fall back to unsigned, never work around it.
- **Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`.** Never `Co-Authored-By` or `Made-with`.
- **`schema_version` stays `"0.1"`.** No committed slices plan exists anywhere in the repository; every plan is code-generated and `build_toy_run` regenerates. A required field therefore costs no migration.
- **The exit-code contract is load-bearing.** `0` clean; `1` findings, one per line on stdout, never empty; `2` usage error or an unreadable/misconfigured run. A stage defect must never surface as `2`, and a `1` must name the right artifact.
- **`refs` shares the projection's builders, never mirrors them.** `check_slices`' check 5 recomputes `slices[].bytes` "via `slices.row_bytes`, the same function `write_slices` used to produce the number in the first place". The two new checks follow that exactly, which is why the builders are public names rather than `_`-prefixed.
- **Partitioning must not change.** `slices[]`, the shard files and their bytes are byte-identical before and after this change. Nothing here touches `plan_slices`.
- **ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`.** `make check` runs `ruff check .` and `ruff format --check .`. `docs/` is excluded; `tests/` and `src/` are not.
- **Comment density is high and deliberate.** Comments explain *why*, citing a measurement. Match that; do not strip existing ones.
- **The three gates:** `make test` green, `make check` clean, `uv run rubrica check-skills` exiting 0. Run all three before every commit.

---

## File Structure

| File | Responsibility in this change |
|---|---|
| `src/rubrica/slices.py` | Three public builders + two module constants; `write_slices` embeds the block and guards `excluded` |
| `src/rubrica/schema/slices-0.1.json` | `catalogue_facts` in `properties` and `required`, `additionalProperties: false` throughout |
| `src/rubrica/refs.py` | `check_slices` gains two checks, importing the builders from `slices` |
| `src/rubrica/skills/rb-triage-objective/SKILL.md` | `reads = ["slices"]`; §1, §2, Invariants 1/2/5, one new §5 refusal |
| `tests/builders.py` | `minimal_slices` gains a valid `catalogue_facts` |
| `tests/unit/test_slices.py` | Builder unit tests and writer integration tests |
| `tests/unit/test_refs_slices.py` | The two new checks, each measured in both directions, plus the unreadable-catalogue skip |
| `tests/unit/test_skills_triage_family.py` | Two existing pins move |
| `docs/concepts/pipeline.md`, `docs/reference/artifacts.md`, `docs/design/limitations.md` | Prose kept true; `test_docs_accuracy.py` enforces |

Nothing is created. Five source/test files and three documents are modified.

**Not touched, deliberately:** `00-slices/<id>.json` shards (they already carry `request`/`policy`, and their members read full candidate records including digests, so they need no `candidate_bytes`); `refs.check_objective` (it keeps recomputing `weight.bytes` from the catalogue, which is the source of truth); `scripts/dispatch-stage.sh` (spec ruling 3 — no per-stage `denyRead`).

---
## Task 1: The exclusion summary and its byte budget

The subtlest logic in the change, isolated so a reviewer can reject it on its own. Pure function, no schema, no wiring.

**Files:**
- Modify: `src/rubrica/slices.py` (add two constants and one function after `oversized_rows`, which ends at line 121)
- Test: `tests/unit/test_slices.py`

**Interfaces:**
- Consumes: `rubrica.artifacts.canonical_bytes` (already imported at `slices.py:44`)
- Produces: `slices.DISPUTABLE_EXCLUSION_REASONS: tuple[str, ...]`; `slices.MAX_EXCLUDED_ENTRY_BYTES: int`; `slices.excluded_summary(excluded: list) -> dict` returning exactly the keys `total: int`, `by_reason: dict[str, int]`, `entries: list[dict]`, `entries_truncated: bool`. Task 2 calls it; Task 3's `check_slices` imports it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_slices.py`. `canonical_bytes` is already imported at the top of that file.

```python
def _excl(reason, *, path_len=20):
    """One catalogue exclusion, padded to a known byte cost."""
    return {"path": "/corpus/" + "p" * path_len, "reason": reason}


def test_the_tally_counts_every_exclusion_including_ones_whose_paths_are_dropped():
    """`total` and `by_reason` describe the whole array, not the kept subset.

    The tally is the only thing a human at gate 0 has to tell "the corpus had
    123 binaries" from "the corpus had none", and `binary` is precisely a
    reason whose paths this function drops. A tally computed over `entries`
    would report zero binaries for a corpus full of them.
    """
    summary = slices.excluded_summary(
        [_excl("binary") for _ in range(123)] + [_excl("duplicate") for _ in range(11)]
    )
    assert summary["total"] == 134
    assert summary["by_reason"] == {"binary": 123, "duplicate": 11}
    assert len(summary["entries"]) == 11
    assert {e["reason"] for e in summary["entries"]} == {"duplicate"}


def test_only_reasons_carrying_a_judgment_keep_their_paths():
    """The four disputable reasons keep paths; the four mechanical ones do not.

    Asserted as set equality over both halves rather than "duplicate is kept",
    so adding a ninth exclusion_reason without ruling on which side it falls
    fails here instead of silently defaulting to dropped.
    """
    every = [
        "duplicate", "operator_excluded", "unreadable", "vendored",
        "gitignored", "vcs_metadata", "binary", "lockfile",
    ]
    summary = slices.excluded_summary([_excl(r) for r in every])
    assert summary["total"] == 8
    assert {e["reason"] for e in summary["entries"]} == set(slices.DISPUTABLE_EXCLUSION_REASONS)
    assert set(slices.DISPUTABLE_EXCLUSION_REASONS) == {
        "duplicate", "operator_excluded", "unreadable", "vendored",
    }


def test_by_reason_is_sorted_so_two_runs_produce_one_byte_shape():
    """Insertion order must not reach the document: the plan is byte-compared."""
    summary = slices.excluded_summary(
        [_excl("vendored"), _excl("binary"), _excl("duplicate"), _excl("binary")]
    )
    assert list(summary["by_reason"]) == ["binary", "duplicate", "vendored"]


def test_an_empty_exclusion_list_produces_the_zero_shape_not_absent_keys():
    """Every key is present at zero, because the toy fixture excludes nothing.

    `tests/fixtures/toy/` surveys to `excluded: []`, so this is the shape every
    toy-based test in the suite sees. Absent keys here would make the schema's
    `required` list unsatisfiable on the fixture the whole suite is built on.
    """
    assert slices.excluded_summary([]) == {
        "total": 0,
        "by_reason": {},
        "entries": [],
        "entries_truncated": False,
    }


def test_the_entry_block_is_bounded_by_bytes_and_says_so_when_it_bit():
    """The budget stops filling before it is exceeded, and records that it did.

    A count cap is what issue #8 is open about: `digest`'s `names` is capped at
    64 entries and unbounded in characters, so a verbose value makes `survey`
    exit 2 on a row that used to be small. Paths vary in length far more than
    tool names do, so this block is bounded in bytes.
    """
    many = [_excl("duplicate", path_len=400) for _ in range(40)]
    summary = slices.excluded_summary(many)

    assert summary["entries_truncated"] is True
    assert summary["total"] == 40, "the tally still describes all forty"
    assert summary["by_reason"] == {"duplicate": 40}
    kept = summary["entries"]
    assert 0 < len(kept) < 40
    # The invariant is "the longest prefix that fits", so the block is under
    # the budget and one more entry would have broken it.
    assert len(canonical_bytes(kept)) <= slices.MAX_EXCLUDED_ENTRY_BYTES
    assert len(canonical_bytes([*kept, many[len(kept)]])) > slices.MAX_EXCLUDED_ENTRY_BYTES


def test_truncation_stops_filling_rather_than_skipping_to_smaller_entries():
    """Once the budget bites the block ends, even if a later entry would fit.

    Fill-what-fits would make the kept set depend on the size of entries the
    operator never sees, so two corpora differing only in one long path would
    produce entry lists that are not prefixes of each other. A prefix is
    explainable at gate 0; a subset chosen by size is not.
    """
    entries = [_excl("duplicate", path_len=9000), _excl("duplicate", path_len=10)]
    summary = slices.excluded_summary(entries)
    assert summary["entries"] == [], "the first entry alone exceeds the budget"
    assert summary["entries_truncated"] is True


def test_a_malformed_exclusion_entry_does_not_raise():
    """`excluded` is schema-required to hold objects, but this runs before validate.

    `write_slices` is reached with whatever is on disk. A non-object entry
    counts toward `total` — it is an exclusion the catalogue records — and
    contributes no reason, rather than crashing a code stage into the exit 2
    that means "no retry can help".
    """
    summary = slices.excluded_summary(["nonsense", 7, None, _excl("duplicate")])
    assert summary["total"] == 4
    assert summary["by_reason"] == {"duplicate": 1}
    assert len(summary["entries"]) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_slices.py -k excl -v`

Expected: every test FAILS with `AttributeError: module 'rubrica.slices' has no attribute 'excluded_summary'`. Confirm the count is 7 failures — a test that errors at collection instead is a typo, not a red test.

- [ ] **Step 3: Implement the constants and the function**

In `src/rubrica/slices.py`, after `oversized_rows` (ends line 121) and before `_str_tuple`:

```python
# Four of the eight exclusion_reason values embed a judgment that could be
# wrong, and those are the ones an operator could dispute at gate 0: an
# --exclude that over-reached, a permissions failure, a near-duplicate that is
# not one, a heuristic vendored-detection. The other four -- gitignored,
# vcs_metadata, binary, lockfile -- are mechanical facts about a file with no
# scoping decision in them. Measured on the tau2 catalogue: keeping these four
# kept all 11 `duplicate` entries and dropped 123 `binary` paths, 1,062 bytes
# against 12,914 for the whole array.
DISPUTABLE_EXCLUSION_REASONS = ("duplicate", "operator_excluded", "unreadable", "vendored")

# A byte budget rather than an entry count, and the reason is a defect open
# against this repository right now: digest's `names` is capped at 64 entries
# and unbounded in characters, so one verbose tool name makes survey exit 2 on
# a row that used to be small. Paths vary in length far more than tool names
# do, so a count cap here would reproduce that defect in a new place.
# Truncating a path is not the alternative -- a mangled path cannot be
# disputed at a gate -- so the block is bounded rather than its contents.
MAX_EXCLUDED_ENTRY_BYTES = 8192


def excluded_summary(excluded: list) -> dict:
    """`excluded` compressed to a tally plus the paths an operator could dispute.

    Shared with refs.check_slices rather than mirrored there, the same way
    check 5 recomputes a slice's bytes through row_bytes: what the check is
    for is drift between the plan and the catalogue -- a plan minted before a
    human adopted a projection at gate 0 -- not whether this arithmetic is
    right. A second implementation would let a defect in this one pass both.

    `total` counts every element of the array, including entries this function
    keeps no path for and entries too malformed to carry a reason, because it
    is the only thing at gate 0 that separates "the corpus had 123 binaries"
    from "the corpus had none".
    """
    tally: Counter[str] = Counter()
    entries: list[dict] = []
    truncated = False
    for entry in excluded:
        if isinstance(entry, dict) and isinstance(reason := entry.get("reason"), str):
            tally[reason] += 1
        else:
            continue
        if truncated or reason not in DISPUTABLE_EXCLUSION_REASONS:
            continue
        # Stop filling rather than skip to whatever still fits: the kept list
        # must be a prefix, so two corpora differing in one long path produce
        # entry lists one of which is a prefix of the other. A prefix is
        # explainable at a gate; a subset chosen by size is not.
        if len(canonical_bytes([*entries, entry])) > MAX_EXCLUDED_ENTRY_BYTES:
            truncated = True
            continue
        entries.append(entry)
    return {
        "total": len(excluded),
        "by_reason": dict(sorted(tally.items())),
        "entries": entries,
        "entries_truncated": truncated,
    }
```

`Counter` is already imported at `slices.py:41` (`from collections import Counter, defaultdict`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_slices.py -k excl -v`
Expected: 7 passed.

Then the whole file, because Step 3 inserted into a module the rest of the suite imports:

Run: `uv run pytest tests/unit/test_slices.py -q`
Expected: all pass, no change in count other than the 7 added.

- [ ] **Step 5: Run the three gates**

```sh
make test && make check && uv run rubrica check-skills
```

Expected: all green. `make check` is the one that catches a line over 100 columns in the block above.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/slices.py tests/unit/test_slices.py
git commit -S -s -m "feat: Summarise a catalogue's exclusions under a byte budget

excluded_summary compresses the catalogue's excluded array to a tally plus
the paths for the four exclusion reasons that embed a judgment an operator
could dispute at gate 0. Measured on the tau2 catalogue: 1,062 bytes
against 12,914 whole, keeping all 11 duplicate entries and dropping 123
binary paths.

Bounded in bytes rather than entries, because a count cap without a
character bound is exactly the defect open against digest's names: one
verbose value there makes survey exit 2 on a row that used to be small.
Truncation ends the block rather than skipping to smaller entries, so the
kept list is always a prefix -- explainable at a gate, where a subset
chosen by size is not.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
## Task 2: The `catalogue_facts` block, in the schema and on disk

**Files:**
- Modify: `src/rubrica/slices.py` (add two functions after `excluded_summary`; extend `write_slices`' guard and document)
- Modify: `src/rubrica/schema/slices-0.1.json:7-9` (required list and properties)
- Modify: `tests/builders.py:566-591` (`minimal_slices`)
- Test: `tests/unit/test_slices.py`

**Interfaces:**
- Consumes: `slices.excluded_summary` from Task 1.
- Produces: `slices.candidate_bytes_index(candidates: list[dict]) -> dict[str, int]`; `slices.catalogue_facts(catalogue: dict) -> dict` returning exactly `request`, `policy`, `excluded`, `candidate_bytes`. Task 3's `check_slices` imports `candidate_bytes_index` and `excluded_summary`. Task 4's skill prose names the on-disk field `catalogue_facts` and its child `candidate_bytes`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_slices.py`. `_toy_run` is already defined at line 262; `read_json`, `write_json`, `canonical_bytes`, `UsageError`, `pytest`, `slices` and `validate` are already imported.

```python
def test_candidate_bytes_indexes_every_candidate_by_its_own_source_size():
    """The map is source `bytes`, never `row_bytes`, and covers inadmissible rows.

    Source size is the metric `weight.bytes` needs: digest.py clamps a skeleton
    at 128 nodes, so a 2.7MB file and a 20KB one serialize to nearly the same
    row once both are past the cap, and a metric that saturates cannot say
    which of two surfaces carries more evidence. Inadmissible candidates are
    included because plan_slices partitions every candidate and a surface's
    evidence may name any of them.
    """
    rows = [_cand("c1", pad=1000), _cand("c2", pad=2000) | {"admissible": False}]
    index = slices.candidate_bytes_index(rows)
    assert index == {"c1": 1000, "c2": 2000}
    assert index["c2"] != slices.row_bytes(rows[1]), "source bytes, not serialized row bytes"


def test_catalogue_facts_carries_exactly_four_fields():
    """Pinned as set equality: a fifth field is a schema change, not a detail.

    `additionalProperties: false` would reject an unknown key at layer 1, but
    this asserts the *producer* stays in shape, so a field added here without
    the schema fails in this file rather than in every validate call.
    """
    catalogue = {
        "run_id": "run-20260825-120000",
        "request": {"objective": "breadth"},
        "policy": {"max_candidates": 500},
        "excluded": [],
        "candidates": [_cand("c1", pad=11)],
    }
    facts = slices.catalogue_facts(catalogue)
    assert set(facts) == {"request", "policy", "excluded", "candidate_bytes"}
    assert facts["request"] == {"objective": "breadth"}, "verbatim, not reshaped"
    assert facts["policy"] == {"max_candidates": 500}, "verbatim, not reshaped"
    assert facts["candidate_bytes"] == {"c1": 11}
    assert facts["excluded"]["total"] == 0


def test_the_written_plan_carries_catalogue_facts_agreeing_with_the_catalogue(tmp_path):
    """The whole point, end to end on the real fixture."""
    run = _toy_run(tmp_path)
    slices.write_slices(run, cap=2500)

    catalogue = read_json(run.catalogue)
    facts = read_json(run.slices)["catalogue_facts"]

    assert facts["request"] == catalogue["request"]
    assert facts["policy"] == catalogue["policy"]
    assert facts["candidate_bytes"] == {
        c["candidate_id"]: c["bytes"] for c in catalogue["candidates"]
    }
    assert facts["excluded"] == {
        "total": 0, "by_reason": {}, "entries": [], "entries_truncated": False,
    }


def test_catalogue_facts_sorts_ahead_of_the_slices_array_on_disk(tmp_path):
    """The head lands in the first bytes, which is the seek issue #3 filed.

    canonical_bytes sorts keys, so `catalogue_facts` and `run_id` both precede
    `slices`. On the 472,799-byte tau2 catalogue `run_id` sat at byte 470,054
    and a dispatch had to seek the whole file for it; this asserts the plan
    does not repeat that. Asserted on byte offsets rather than on key order,
    because a reader pays for offsets.
    """
    run = _toy_run(tmp_path)
    slices.write_slices(run, cap=2500)
    text = run.slices.read_text(encoding="utf-8")
    assert text.index('"catalogue_facts"') < text.index('"slices"')
    assert text.index('"run_id"') < text.index('"slices"')


def test_a_catalogue_with_no_excluded_field_is_refused_at_exit_two(tmp_path):
    """`excluded` joins the three fields write_slices reads bare.

    It is `required` in catalogue-0.1.json, so its absence is a broken
    catalogue rather than a shape this stage should tolerate. UsageError, so
    cli.py maps it to exit 2: no retry of triage-slices can fix a catalogue.
    The message must name the catalogue, because that is where the operator
    looks next -- naming this stage would send them to the wrong file.
    """
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    del catalogue["excluded"]
    write_json(run.catalogue, catalogue)
    with pytest.raises(UsageError) as caught:
        slices.write_slices(run, cap=2500)
    assert str(run.catalogue) in str(caught.value)
    assert "excluded" in str(caught.value)


def test_a_populated_exclusion_list_reaches_the_plan_summarised(tmp_path):
    """The toy fixture excludes nothing, so the populated path needs injecting."""
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["excluded"] = [
        {"path": "/corpus/a.png", "reason": "binary"},
        {"path": "/corpus/b.png", "reason": "binary"},
        {"path": "/corpus/c.json", "reason": "duplicate"},
    ]
    write_json(run.catalogue, catalogue)
    slices.write_slices(run, cap=2500)

    excluded = read_json(run.slices)["catalogue_facts"]["excluded"]
    assert excluded["total"] == 3
    assert excluded["by_reason"] == {"binary": 2, "duplicate": 1}
    assert [e["path"] for e in excluded["entries"]] == ["/corpus/c.json"]
    assert excluded["entries_truncated"] is False


def test_the_plan_still_validates_against_its_schema(tmp_path):
    """Layer 1, on the real writer's output rather than on a builder."""
    run = _toy_run(tmp_path)
    slices.write_slices(run, cap=2500)
    assert validate.validate_stage(run, "triage-slices") == []


def test_adding_catalogue_facts_left_the_partition_byte_identical(tmp_path):
    """`slices[]` and every shard are untouched by this change.

    The spec's Global Constraint: nothing here touches plan_slices. Compared
    against plan_slices' own output rather than a recorded fixture, so the
    assertion cannot rot into agreeing with a regression.
    """
    run = _toy_run(tmp_path)
    _, plan = slices.write_slices(run, cap=2500)
    document = read_json(run.slices)
    expected = slices.plan_slices(read_json(run.catalogue)["candidates"], cap=2500)

    assert [s["id"] for s in document["slices"]] == [s.id for s in expected]
    assert [s["candidate_ids"] for s in document["slices"]] == [
        list(s.candidate_ids) for s in expected
    ]
    assert [s.id for s in plan] == [s.id for s in expected]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_slices.py -k "catalogue_facts or candidate_bytes or excluded_field or populated_exclusion or partition_byte or still_validates" -v`

Expected: FAIL. The first two on `AttributeError` for the missing functions; the writer tests on `KeyError: 'catalogue_facts'`; the guard test on `pytest.raises(UsageError)` not being raised.

- [ ] **Step 3: Implement the two builders**

In `src/rubrica/slices.py`, immediately after `excluded_summary`:

```python
def candidate_bytes_index(candidates: list[dict]) -> dict[str, int]:
    """`candidate_id` -> that candidate's own catalogue `bytes`, for every candidate.

    Source file size, never row_bytes' serialized size. digest.py clamps a
    skeleton at 128 nodes, so two candidates of very different evidential size
    serialize to nearly the same row once both are past the cap -- a metric
    that saturates stops discriminating exactly where rb-triage-objective's
    weight.bytes needs it to.

    Every candidate, admissible or not: plan_slices partitions all of them and
    a surface's `evidence` may name any. A map rather than a list of objects
    because it measured 41.1 bytes per candidate against 80.1 for the list
    form, on a field the whole point of which is to be small.

    Shared with refs.check_slices for the reason excluded_summary is.
    """
    return {
        cid: b
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance(cid := candidate.get("candidate_id"), str)
        and isinstance(b := candidate.get("bytes"), int)
        and not isinstance(b, bool)
    }


def catalogue_facts(catalogue: dict) -> dict:
    """Everything rb-triage-objective may know about the catalogue, without opening it.

    Named `catalogue_facts` and not `catalogue_projection`: `projection`
    already means "a manufactured artifact admitted to close a deficiency"
    throughout this subsystem, and a second sense of the word in the most
    projection-dense part of the codebase is a readability cost with no
    upside. The design spec specs the other name; it is recorded history and
    is not edited to match.

    `request` and `policy` are copied verbatim, which is not a new pattern:
    write_slices' docstring already argues for the shards carrying both rather
    than each member seeking a sorted-keys catalogue for two small fields.
    """
    return {
        "request": catalogue["request"],
        "policy": catalogue["policy"],
        "excluded": excluded_summary(catalogue["excluded"]),
        "candidate_bytes": candidate_bytes_index(catalogue.get("candidates", [])),
    }
```

The `not isinstance(b, bool)` clause is the repo's standing guard, present at `triage.py:450`, `manifest.py:149`, `intake.py:239` and `seal.py:307`: `isinstance(True, int)` is `True` in Python, so a `bytes: true` would otherwise index as the integer 1.

- [ ] **Step 4: Wire it into `write_slices`**

Two edits inside `write_slices`.

The missing-field guard — add `"excluded"`:

```python
    missing_top = [
        key for key in ("run_id", "request", "policy", "excluded") if key not in catalogue
    ]
```

And the document, adding one key to the dict literal that currently starts `"schema_version": "0.1",`:

```python
    document = {
        "schema_version": "0.1",
        "run_id": catalogue["run_id"],
        "cap_bytes": cap,
        "catalogue_facts": catalogue_facts(catalogue),
        "slices": [
```

Leave the rest of the literal, the shard loop and the stale-shard removal exactly as they are.

Then extend `write_slices`' docstring. After the existing paragraph beginning "Every shard carries the run's `request` and `policy` verbatim", add:

```
    The plan carries a `catalogue_facts` block for the same reason one step
    further out: it is everything rb-triage-objective needs, so that pass's
    `reads` no longer names the catalogue at all. Measured on the tau2
    catalogue, that took the objective dispatch's input from 472,799 bytes to
    51,792 -- inside the harness's 256KB whole-file Read refusal, where the
    catalogue was not -- and bounded it by max_candidates, since the block
    costs 41.1 bytes per candidate. canonical_bytes sorts keys, so the block
    and run_id both land ahead of the slices array: the 470KB seek for run_id
    that chunk-reading dispatches used to pay is gone as a consequence of the
    sort rather than as a special case.
```

- [ ] **Step 5: Extend the schema**

In `src/rubrica/schema/slices-0.1.json`, add `"catalogue_facts"` to the `required` array on line 7:

```json
  "required": ["schema_version", "run_id", "slices", "cap_bytes", "catalogue_facts"],
```

Then add this property inside the top-level `properties` object, after `cap_bytes`' entry and before `slices`':

```json
    "catalogue_facts": {
      "description": "Everything rb-triage-objective may know about 00-catalogue.json without opening it, so that pass's reads does not name the catalogue and its dispatch is bounded by max_candidates rather than by corpus size. request and policy are verbatim copies; the other two are derived, and refs.check_slices recomputes both from the catalogue through the same functions that wrote them.",
      "type": "object",
      "required": ["request", "policy", "excluded", "candidate_bytes"],
      "additionalProperties": false,
      "properties": {
        "request": {"type": "object"},
        "policy": {"type": "object"},
        "excluded": {
          "description": "The catalogue's excluded array as a tally plus the paths for the four exclusion reasons that embed a disputable judgment. Bounded in bytes, not entries: a count cap without a character bound is the defect open against digest's names.",
          "type": "object",
          "required": ["total", "by_reason", "entries", "entries_truncated"],
          "additionalProperties": false,
          "properties": {
            "total": {"description": "Length of the catalogue's excluded array, including entries no path is kept for -- the only thing at gate 0 separating a corpus with 123 binaries from one with none.", "type": "integer", "minimum": 0},
            "by_reason": {"description": "One key per exclusion_reason that occurs, sorted. Reasons that did not occur are absent rather than zero.", "type": "object", "additionalProperties": {"type": "integer", "minimum": 1}},
            "entries": {"type": "array", "items": {"$ref": "catalogue-0.1.json#/properties/excluded/items"}},
            "entries_truncated": {"description": "Whether the byte budget stopped the entries list short. An unconditional sibling of entries, present as false when it did not bite, following keys_truncated and skeleton_nodes_truncated: a truncation a prompt can see is a fact about the input, and one it cannot see is a lie about it.", "type": "boolean"}
          }
        },
        "candidate_bytes": {
          "description": "candidate_id -> that candidate's own source bytes, for every catalogue candidate including inadmissible ones. Source size, never a serialized row's size, which saturates once the digest skeleton hits its 128-node clamp.",
          "type": "object",
          "additionalProperties": {"type": "integer", "minimum": 0}
        }
      }
    },
```

The `entries` `$ref` reuses the catalogue schema's own exclusion shape rather than restating `path`/`reason`/`detail`. That is the pattern `test_validate_registry_triage.py` exists to keep honest, and the registry it describes already resolves cross-file `$ref`s from every schema in `schema_dir()`.

- [ ] **Step 6: Update `minimal_slices`**

In `tests/builders.py`, inside `minimal_slices`' payload dict, after `"cap_bytes": 1_048_576,`:

```python
        "catalogue_facts": {
            "request": minimal_catalogue()["request"],
            "policy": minimal_catalogue()["policy"],
            "excluded": {
                "total": 0,
                "by_reason": {},
                "entries": [],
                "entries_truncated": False,
            },
            "candidate_bytes": {candidate_id: 37},
        },
```

`minimal_catalogue` is defined at line 446 of the same module, above `minimal_slices` at 566, so no import or reordering is needed. Reusing its `request`/`policy` rather than restating them is deliberate: `catalogue_facts` copies those two verbatim, so a builder that drifted from `minimal_catalogue` would let a test pass against a pair the writer could never produce.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_slices.py tests/unit/test_validate.py tests/unit/test_validate_registry_triage.py -q`

Expected: all pass. `test_validate.py:98` round-trips `minimal_slices` through the schema, so Step 6 landing wrong fails there rather than in `test_slices.py`.

Then the reference checks and the toy checkpoints, which build real plans:

Run: `uv run pytest tests/unit/test_refs_slices.py tests/unit/test_toy_triage_checkpoints.py tests/unit/test_brief.py -q`
Expected: all pass. Nothing in Task 2 changes `check_slices`, so a failure here means the schema or the document shape is wrong, not the gates.

- [ ] **Step 8: Run the three gates**

```sh
make test && make check && uv run rubrica check-skills
```

Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add src/rubrica/slices.py src/rubrica/schema/slices-0.1.json tests/builders.py tests/unit/test_slices.py
git commit -S -s -m "feat: Carry the catalogue facts rb-triage-objective needs on the plan

00-slices.json gains a catalogue_facts block: request and policy verbatim,
the exclusions summarised, and every candidate's own source bytes as a map.
It is everything the objective pass reads the catalogue for, which is what
lets its reads drop the catalogue in a later commit.

Measured on the tau2 catalogue: 51,792 bytes against 472,799, inside the
harness's 256KB whole-file Read refusal where the catalogue was not, and
bounded by max_candidates at 41.1 bytes per candidate. canonical_bytes
sorts keys, so the block and run_id both land ahead of the slices array --
the 470KB seek a chunk-reading dispatch paid for run_id is gone as a
consequence of the sort rather than a special case.

candidate_bytes is source size, never row_bytes: the skeleton's 128-node
clamp makes serialized row size saturate, and a metric that saturates
cannot say which of two surfaces carries more evidence.

Named catalogue_facts, not the design spec's catalogue_projection:
projection already means a manufactured artifact admitted to close a
deficiency throughout this subsystem. The spec is recorded history and is
not edited to match.

Partitioning is untouched -- slices[] and every shard are byte-identical.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
## Task 3: `check_slices` recomputes the block's two derived fields

**Files:**
- Modify: `src/rubrica/refs.py:34` (import) and `check_slices` (new checks before its `return out`)
- Test: `tests/unit/test_refs_slices.py`

**Interfaces:**
- Consumes: `slices.candidate_bytes_index` and `slices.excluded_summary` from Tasks 1-2; `check_slices`' existing locals `catalogue`, `catalogue_candidates`, `plan`, and the `report(pointer, message)` closure defined at `refs.py:317`.
- Produces: nothing new. `check_slices(run) -> list[Finding]` keeps its signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_refs_slices.py`. `_sliced_run`, `read_json`, `write_json` and `check_slices` are already imported there.

```python
def _mutate_facts(run, mutate):
    """Edit only 00-slices.json's catalogue_facts, leaving the partition alone.

    The module's discipline: a mutation must be visible to exactly one check.
    catalogue_facts is read by nothing else in check_slices, so editing it
    cannot trip the partition, shard or cap checks -- which is why every test
    below can assert its finding is the only one.
    """
    plan = read_json(run.slices)
    mutate(plan["catalogue_facts"])
    write_json(run.slices, plan)


def test_a_clean_run_reports_no_catalogue_facts_findings(tmp_path):
    run = _sliced_run(tmp_path)
    assert check_slices(run) == []


def test_a_candidate_bytes_value_disagreeing_with_the_catalogue_is_reported(tmp_path):
    """The check that makes the whole block safe to read.

    rb-triage-objective sums weight.bytes from candidate_bytes while
    check_objective recomputes it from the catalogue. Without this check a
    drifted block would surface the objective pass's *correct* arithmetic as a
    finding against 00-objective.json -- a 1 naming the wrong artifact.
    """
    run = _sliced_run(tmp_path)
    catalogue = read_json(run.catalogue)
    victim = catalogue["candidates"][0]["candidate_id"]
    real = catalogue["candidates"][0]["bytes"]

    def bump(facts):
        facts["candidate_bytes"][victim] = real + 1

    _mutate_facts(run, bump)
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == f"/catalogue_facts/candidate_bytes/{victim}"
    assert str(real) in findings[0].message
    assert str(run.slices) == str(findings[0].path), "the plan is at fault, not the catalogue"


def test_a_candidate_missing_from_candidate_bytes_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    victim = read_json(run.catalogue)["candidates"][0]["candidate_id"]
    _mutate_facts(run, lambda facts: facts["candidate_bytes"].pop(victim))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == f"/catalogue_facts/candidate_bytes/{victim}"
    assert "no candidate_bytes entry" in findings[0].message


def test_candidate_bytes_naming_a_candidate_the_catalogue_does_not_have_is_reported(tmp_path):
    """An extra id is drift too: a plan minted before the catalogue shrank."""
    run = _sliced_run(tmp_path)
    _mutate_facts(run, lambda facts: facts["candidate_bytes"].update({"ghost-1": 10}))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/catalogue_facts/candidate_bytes/ghost-1"
    assert "not a catalogue candidate" in findings[0].message


def test_an_exclusion_total_disagreeing_with_the_catalogue_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    _mutate_facts(run, lambda facts: facts["excluded"].update({"total": 7}))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/catalogue_facts/excluded/total"


def test_an_exclusion_tally_disagreeing_with_the_catalogue_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    _mutate_facts(run, lambda facts: facts["excluded"].update({"by_reason": {"binary": 3}}))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/catalogue_facts/excluded/by_reason"


def test_an_unreadable_catalogue_reports_no_catalogue_facts_findings(tmp_path):
    """Silence, not one finding per candidate against a plan that is fine.

    This is the 01-claims/ incident: check-refs over an unreadable directory
    once reported four fabricated `no such claim` findings against a correct
    world model. An unreadable catalogue is check_readable's finding, and
    resolving candidate_bytes against candidates that were never parsed would
    blame the plan for the catalogue being broken.
    """
    run = _sliced_run(tmp_path)
    run.catalogue.write_text("{not json", encoding="utf-8")
    findings = check_slices(run)
    assert [f for f in findings if "catalogue_facts" in f.pointer] == []


def test_a_catalogue_whose_candidates_are_not_an_array_reports_no_bytes_findings(tmp_path):
    """The same skip, through the branch that already sets known_ids to None."""
    run = _sliced_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"] = "not an array"
    write_json(run.catalogue, catalogue)
    findings = check_slices(run)
    assert [f for f in findings if "candidate_bytes" in f.pointer] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_slices.py -q`

Expected: the six mutation tests FAIL with `assert len(findings) == 1` seeing `0` — the block is on disk from Task 2 but nothing checks it yet. The clean-run and two skip tests PASS already; that is correct and expected, because they assert an absence. Note which are which before Step 3: a skip test that was already green is only proof of the guard once the checks exist, so it is re-run in Step 4.

- [ ] **Step 3: Implement the two checks**

Extend the import at `src/rubrica/refs.py:34`:

```python
from rubrica.slices import candidate_bytes_index, excluded_summary, row_bytes
```

Then, inside `check_slices`, immediately before its final `return out` (after the orphan-shard scan):

```python
    # Checks 8 and 9: the catalogue_facts block's two *derived* fields,
    # recomputed from the catalogue through the same functions write_slices
    # used to produce them -- check 5's discipline, for check 5's reason. What
    # this catches is drift between the plan and the catalogue, the realistic
    # case being a plan minted before a human adopted a projection at gate 0,
    # rather than arithmetic this module could get wrong twice identically.
    #
    # `request`, `policy` and `excluded.entries` are deliberately *not*
    # checked: they are verbatim copies, and nothing verifies the shards' own
    # copies of request/policy either. Derived numbers are arithmetic a reader
    # recomputes; verbatim copies are not testimony to begin with.
    #
    # Mandatory rather than tidiness. rb-triage-objective sums weight.bytes
    # from candidate_bytes, while check_objective recomputes the same number
    # from the catalogue -- so an unchecked drift here would surface that
    # pass's *correct* arithmetic as a finding against 00-objective.json. That
    # is the exit-code contract's third rule, and it is what four fabricated
    # `no such claim` findings against a correct world model once cost.
    facts = plan.get("catalogue_facts")
    if isinstance(facts, dict) and isinstance(catalogue, dict):
        # Both halves skip on an unreadable or wrong-shaped catalogue rather
        # than reporting every entry, reusing the same reasoning that leaves
        # known_ids None above.
        if isinstance(catalogue_candidates, list):
            expected_bytes = candidate_bytes_index(catalogue_candidates)
            declared = facts.get("candidate_bytes")
            declared = declared if isinstance(declared, dict) else {}
            for cid in sorted(expected_bytes):
                pointer = f"/catalogue_facts/candidate_bytes/{cid}"
                if cid not in declared:
                    report(pointer, f"catalogue_facts has no candidate_bytes entry for {cid!r}")
                elif declared[cid] != expected_bytes[cid]:
                    report(
                        pointer,
                        f"catalogue_facts records {cid!r} at {declared[cid]!r} bytes but "
                        f"the catalogue says {expected_bytes[cid]}",
                    )
            for cid in sorted(set(declared) - set(expected_bytes)):
                report(
                    f"/catalogue_facts/candidate_bytes/{cid}",
                    f"catalogue_facts records candidate_bytes for {cid!r}, which is not "
                    "a catalogue candidate",
                )
        catalogue_excluded = catalogue.get("excluded")
        if isinstance(catalogue_excluded, list):
            expected_excluded = excluded_summary(catalogue_excluded)
            declared_excluded = facts.get("excluded")
            declared_excluded = declared_excluded if isinstance(declared_excluded, dict) else {}
            for key in ("total", "by_reason"):
                if declared_excluded.get(key) != expected_excluded[key]:
                    report(
                        f"/catalogue_facts/excluded/{key}",
                        f"catalogue_facts records excluded.{key}={declared_excluded.get(key)!r} "
                        f"but the catalogue's exclusions give {expected_excluded[key]!r}",
                    )
    return out
```

`catalogue`, `catalogue_candidates` and `report` are existing locals — `catalogue` and `catalogue_candidates` are set around `refs.py:335-336`, `report` at `:317`. Do not re-load the catalogue; `_load` returning `None` on failure is exactly what makes the `isinstance(catalogue, dict)` guard work.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_refs_slices.py -v`
Expected: all pass, including the two skip tests, which are now meaningful rather than vacuous.

Then the check-refs suite as a whole, because `check_all` runs every checker:

Run: `uv run pytest tests/unit/ -k refs -q`
Expected: all pass. A failure in `test_refs_triage.py` or `test_refs_triage_parts.py` means the new findings are firing on a run they should not.

- [ ] **Step 5: Verify the exit-code contract by hand**

The rule that a `1` never has empty stdout, and names the right artifact, is not something the unit tests reach — they call `check_slices` directly rather than through the CLI.

```sh
rm -rf /tmp/t3 && mkdir -p /tmp/t3
uv run rubrica survey --corpus tests/fixtures/toy --runs-dir /tmp/t3/runs \
  --target-name toy --target-interface http --objective breadth
RUN=$(ls -d /tmp/t3/runs/run-*)
uv run rubrica triage-slices --run "$RUN"
uv run rubrica check-refs --run "$RUN"; echo "clean exit: $?"

uv run python - "$RUN" <<'PY'
import json, sys
from pathlib import Path
plan = json.loads((Path(sys.argv[1]) / "00-slices.json").read_text())
first = next(iter(plan["catalogue_facts"]["candidate_bytes"]))
plan["catalogue_facts"]["candidate_bytes"][first] = 999999
(Path(sys.argv[1]) / "00-slices.json").write_text(json.dumps(plan, indent=2, sort_keys=True))
PY
uv run rubrica check-refs --run "$RUN"; echo "drifted exit: $?"
```

Expected: `clean exit: 0`; `drifted exit: 1` with at least one non-empty stdout line naming `00-slices.json` and the pointer `/catalogue_facts/candidate_bytes/<id>`. If the drifted run exits `2`, the checker is raising rather than reporting and the task is not done.

- [ ] **Step 6: Run the three gates**

```sh
make test && make check && uv run rubrica check-skills
```

- [ ] **Step 7: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs_slices.py
git commit -S -s -m "feat: Recompute catalogue_facts' derived fields in check_slices

candidate_bytes and the exclusion tally are recomputed from the catalogue
through the same functions write_slices used, which is check 5's discipline
applied to the new block: what it catches is drift between the plan and the
catalogue -- a plan minted before a human adopted a projection at gate 0 --
not arithmetic that could go wrong twice identically.

Mandatory rather than tidiness. rb-triage-objective will sum weight.bytes
from candidate_bytes while check_objective recomputes it from the
catalogue, so unchecked drift would surface that pass's correct arithmetic
as a finding against 00-objective.json: a 1 naming the wrong artifact,
which is what four fabricated `no such claim` findings against a correct
world model once cost this repository.

request, policy and excluded.entries stay unchecked. They are verbatim
copies, and nothing verifies the shards' own copies either -- derived
numbers are arithmetic a reader recomputes, verbatim copies are not
testimony to begin with.

Both halves skip on an unreadable or wrong-shaped catalogue rather than
reporting every candidate against a plan that is fine.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
## Task 4: The skill contract and prose

The behavioural half. Nothing here changes code the gates run, so the whole task's evidence is `check-skills`, the text-level predicates, and reading it.

**Files:**
- Modify: `src/rubrica/skills/rb-triage-objective/SKILL.md` (Contract, §1, §2, §4 Invariants 1/2/5, §5)
- Test: `tests/unit/test_skills_triage_family.py:132` and `:896`, plus the predicate at `:138`

**Interfaces:**
- Consumes: the on-disk field names Task 2 fixed — `catalogue_facts`, and its children `request`, `policy`, `excluded` (`total`, `by_reason`, `entries`, `entries_truncated`), `candidate_bytes`.
- Produces: nothing code reads. `skills.load()`'s contract dict changes shape for this one skill.

- [ ] **Step 1: Move the two failing pins**

In `tests/unit/test_skills_triage_family.py`, at `:132`:

```python
    assert skill.contract["reads"] == ["slices"]
```

and update that test's docstring, which currently says "slices and catalogue":

```python
    """The brief's contract, verbatim: the plan alone -- never the catalogue,
    the shards, or a per-slice dispositions part. The catalogue left this list
    when 00-slices.json started carrying the facts this pass needs: reading
    472,799 bytes for the 21KB it used was the residual half of issue #3."""
```

At `:896`, in the parametrize table:

```python
        ("rb-triage-objective", "00-slices.json"),
```

- [ ] **Step 2: Replace the vacuous digest predicate with a windowed shard one**

At `:138` the predicate is `assert "digest" in body and ("not" in body or "never" in body)`. `limitations.md` records this exact predicate measured vacuous: inverting the skill's prose to *may read every digest* left it green. It also records the remedy — a window — measured red on the same inversion.

The prohibition it was written for now lives on the shards, so replace it rather than delete it:

```python
def test_the_objective_pass_forbids_reading_a_shard():
    """The pass's bounding constraint, on the artifact that now holds the digests.

    `00-slices.json` carries no candidate digest at all, so the old form of
    this predicate -- "digest" and a prohibition word both somewhere in the
    section -- no longer even has a subject. What can still make this pass
    unbounded is a shard: seven of them hold every candidate's full digest and
    on the tau2 corpus total 470,455 bytes against the catalogue's 472,799.

    Windowed rather than section-wide, because the unwindowed form of this
    predicate was measured vacuous: inverting the skill to grant the opposite
    permission left it green. radius=300 against a measured distance of well
    under 150 characters from each `shard` mention to its prohibition word.
    """
    body = _norm(skills.section_body(_objective(), "1. Inputs"))
    indices = _occurrences(body, "shard")
    assert indices, "the Inputs section never names a shard"
    assert any(
        any(word in _window_around(body, at, radius=300) for word in ("never", "not yours", "do not"))
        for at in indices
    ), "no `shard` mention sits near a prohibition"
```

- [ ] **Step 3: Run the three tests to verify they fail**

Run: `uv run pytest tests/unit/test_skills_triage_family.py -k "exact_contract or forbids_reading_a_shard or where_it_reads_run_id" -v`

Expected: `exact_contract` FAILS (`["slices", "catalogue"] != ["slices"]`), `forbids_reading_a_shard` FAILS on the assert message `the Inputs section never names a shard` or the prohibition assert, and the `rb-triage-objective` parametrisation of `where_it_reads_run_id` FAILS. The `rb-triage-rule` and `rb-triage-audit` parametrisations must still PASS — if they fail, the table edit hit the wrong row.

- [ ] **Step 4: Change the contract block**

In `src/rubrica/skills/rb-triage-objective/SKILL.md`'s `## Contract` fence:

```toml
reads = ["slices"]
```

Leave `stage`, `writes`, `schemas` and `invokes` exactly as they are.

- [ ] **Step 5: Rewrite §1 Inputs**

Replace the section's **first paragraph** — currently "You read exactly two files: `00-slices.json` and `00-catalogue.json`. **Not a single candidate `digest`, from either one.**" — with:

```markdown
You read exactly one file: `00-slices.json`. **Not a shard under
`00-slices/`, and not `00-catalogue.json`.** Both sit in the same run
directory and neither is yours. A shard holds every candidate's full
`digest`, and the shards of a real corpus together come to very nearly what
the catalogue itself weighs -- so opening one is both a sibling member's
slice and precisely the unbounded read this pass exists not to perform. A
read audit sees it either way.
```

Keep the next paragraph ("`00-slices.json` is the corpus map: ...") unchanged.

Replace the paragraph beginning "`00-catalogue.json` gives you `request`" — through the end of the "**The prohibition is on opening a digest**" paragraph — with:

```markdown
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
bounded by how many candidates the run admitted, never by how large they are,
which is why this pass can run in one dispatch ahead of the fan-out and let
the members that *do* open digests grow with the corpus instead. Firming up a
surface judgment by opening a shard would spend exactly that property.

`excluded` is worth reading for the reason it always was: a mechanical
exclusion you believe was wrong is a fact worth recording. This pass does not
write `deficiencies[]` -- that block does not exist in `objective-0.1.json`,
because closing a corpus gap is `rb-triage-audit`'s job, run after every slice
has reported what it actually observed. What you can do here is name the
concern in `objective_review.notes` and say plainly that `rb-triage-audit`
should look at it -- a pointer forward, not a decision you are making in its
place.
```

Keep the "**The honest limitation**" paragraph and the closing "You are dispatched with no memory" paragraph, changing only "these two files" to "this one file" in the latter.

- [ ] **Step 6: Sharpen §2's two byte metrics**

§2 currently reads `run_id` from the catalogue and describes `weight.bytes` against "the catalogue `bytes` field". Two edits.

In the paragraph beginning "One file: `00-objective.json`", change the parenthetical to:

```markdown
(read it from `00-slices.json`'s `run_id` -- never invent it, and never derive
it from the directory name)
```

Then replace the `weight.bytes` paragraph with the version that names both metrics, because they now sit in the same file:

```markdown
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
```

That paragraph must keep the tokens `weight.bytes`, `bytes`, `row`/`serialized` and `saturat`, because `test_the_objective_pass_states_which_bytes_weight_sums` asserts all four in §2. It does.

- [ ] **Step 7: Update §4 Invariants 1, 2 and 5**

```markdown
1. **You read `00-slices.json`, and nothing else.** Not `00-catalogue.json`,
   not a shard under `00-slices/`, no `00-dispositions/` part, no
   `decisions.md`, no artifact from another run.
2. **`weight` is arithmetic over `catalogue_facts.candidate_bytes`**, never
   over `slices[].bytes`, never over a serialized row's size, and never an
   impression. A reader recomputes it.
```

and

```markdown
5. **`run_id` is read from `00-slices.json`, never invented and never derived
   from the run directory's name.**
```

Leave Invariants 3 and 4 untouched.

- [ ] **Step 8: Update §5's third refusal and add the new one**

Replace the third refusal condition with:

```markdown
**Refuse if `00-slices.json` is missing, empty of slices, or not readable as
its schema describes.** That is a `survey` or `triage-slices` defect or a
broken run, and producing an objective ruling against it would attribute a
scoping decision to a pass that never actually read a corpus.
```

Then add a fourth:

```markdown
**Refuse if any `candidate_id` named in `slices[]` has no entry in
`catalogue_facts.candidate_bytes`.** You cannot weigh a surface whose evidence
includes a candidate you have no size for, and the alternative -- treating the
missing entry as zero -- would silently understate the one number a human
reads at gate 0 to compare one surface against another. This is a
`triage-slices` defect; say which ids are missing and stop.
```

Leave the first two refusals — the absent/contradicted `objective` one, and the do-not-refuse-when-unsupported one — exactly as they are. The second is the family's worked example of a non-decorative do-not-refuse and must not be touched.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_skills_triage_family.py -v`
Expected: all pass, all three parametrisations of the run_id test included.

Run: `uv run rubrica check-skills; echo "exit: $?"`
Expected: `exit: 0`. This is what validates `reads = ["slices"]` against `paths.RunPaths` attribute names — a typo like `slice` fails here.

- [ ] **Step 10: Measure the new predicate in both directions**

Required by `CLAUDE.md` and not optional: a predicate nobody has watched fail is not yet a guard. Both directions, in a `/tmp` copy so the tree is never edited.

```sh
rm -rf /tmp/skills4 && cp -r src/rubrica/skills /tmp/skills4
S=/tmp/skills4/rb-triage-objective/SKILL.md

# Direction 1 -- INVERT the prohibition (stronger than deleting it: the tokens
# stay and the prose now says the opposite). Expect RED.
python - "$S" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text()
before = t
t = t.replace(
    "**Not a shard under\n`00-slices/`, and not `00-catalogue.json`.**",
    "**You may open any shard under `00-slices/` freely.**",
)
assert t != before, "the replacement matched nothing -- fix the string, do not proceed"
p.write_text(t)
PY
RUBRICA_SKILLS_DIR=/tmp/skills4 uv run pytest \
  tests/unit/test_skills_triage_family.py -k forbids_reading_a_shard -q
echo "direction 1 (expect failure): $?"
```

A non-zero exit is the pass. **If it exits 0 the predicate is vacuous and the task is not done** — widen the window or anchor differently, do not accept it.

```sh
# Direction 2 -- REWORD meaning-preservingly. Expect GREEN.
rm -rf /tmp/skills4 && cp -r src/rubrica/skills /tmp/skills4
python - "$S" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text()
before = t
t = t.replace(
    "**Not a shard under\n`00-slices/`, and not `00-catalogue.json`.**",
    "**A shard under `00-slices/` is never yours to open, and neither is\n`00-catalogue.json`.**",
)
assert t != before, "the replacement matched nothing -- fix the string, do not proceed"
p.write_text(t)
PY
RUBRICA_SKILLS_DIR=/tmp/skills4 uv run pytest \
  tests/unit/test_skills_triage_family.py -k forbids_reading_a_shard -q
echo "direction 2 (expect pass): $?"
rm -rf /tmp/skills4
```

Both `python` blocks assert their replacement matched. That assertion is the point: four verification steps in an earlier plan in this repository passed for free because each one perturbed nothing and nobody checked.

- [ ] **Step 11: Run the three gates**

```sh
make test && make check && uv run rubrica check-skills
```

- [ ] **Step 12: Commit**

```bash
git add src/rubrica/skills/rb-triage-objective/SKILL.md tests/unit/test_skills_triage_family.py
git commit -S -s -m "feat: Drop the catalogue from rb-triage-objective's reads

The pass now reads 00-slices.json alone. Its input is bounded by
max_candidates rather than by corpus size, which is the residual half of
issue #3: the objective dispatch was reading 472,799 bytes for the ~21KB it
was told to use, paging past 238,973 bytes of digest it is forbidden to
touch, because a chunked Read cannot project columns.

The prohibition moves rather than disappearing, and the prose follows it.
00-slices.json carries no digest, so what can still make this pass unbounded
is a shard -- seven of them hold every candidate's full digest and come to
nearly what the catalogue weighs. Section 1 says so, Invariant 1 lists the
catalogue among what must not be read, and the predicate that used to guard
this is now windowed: limitations.md records the unwindowed form measured
vacuous, green against prose granting the opposite permission.

Section 2 gets sharper rather than merely updated. slices[].bytes and
candidate_bytes now sit in the same file, so the paragraph names both and
says which saturates under the skeleton's 128-node clamp.

One new refusal condition: a candidate_id in slices[] with no
candidate_bytes entry cannot be weighed, and treating it as zero would
understate the one number a human reads at gate 0 to compare surfaces.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
## Task 5: The documents

`tests/unit/test_docs_accuracy.py` fails until these agree with the code. That failure is the guard working — update the document, never the assertion.

**Files:**
- Modify: `docs/concepts/pipeline.md:29`
- Modify: `docs/reference/artifacts.md` (the `slices` section and the `objective` section)
- Modify: `docs/design/limitations.md:953-954`, the entry at `:1649`, and one new entry

**Interfaces:**
- Consumes: everything Tasks 2-4 landed. No code.
- Produces: nothing.

**Do not edit `CLAUDE.md`.** Its stage-table row at `:71` reads "`rb-triage-objective` — barrier, reads the corpus map, never a digest". Both halves stay true: the plan *is* the corpus map, and the pass still reads no digest. A change there would be churn, and `CLAUDE.md` is not ruff-excluded so it would also mean re-running `make check` for nothing.

**Do not edit the design spec.** `docs/superpowers/` is recorded history. The `catalogue_projection` → `catalogue_facts` rename is recorded in this plan's Global Constraints and in `catalogue_facts`' own docstring, which is where a reader will be standing when the question occurs to them.

- [ ] **Step 1: `pipeline.md`**

Line 29's input column currently reads ``00-slices.json`, `00-catalogue.json` — never a candidate digest`. Replace that cell's contents with:

```
`00-slices.json` only — its `catalogue_facts` block, never a shard's digests
```

- [ ] **Step 2: `artifacts.md`, the `slices` section**

Replace the first "Read by" bullet:

```markdown
- **Read by:** `rb-triage-objective` (this file alone — `slices[]`'s labels,
  groups and counts, plus the `catalogue_facts` block; never a shard's
  candidate digests, and never `00-catalogue.json`); `rb-triage-rule`
  (one dispatch per slice, each reading only its own `00-slices/<id>.json`
  shard whole — never a sibling's)
```

Then extend the "Fields worth knowing" paragraph, appending after the
`other_slices` clause:

```markdown
; and `catalogue_facts`, which is everything `rb-triage-objective` may know
about `00-catalogue.json` without opening it — `request` and `policy`
verbatim, `excluded` as a tally plus the paths for the exclusion reasons an
operator could dispute, and `candidate_bytes` giving each candidate's own source
size. Sorted keys put it and `run_id` ahead of `slices[]`, so the head a
reader needs is in the first bytes rather than 470KB in, which is what a
chunk-reading dispatch used to pay for. `refs.check_slices` recomputes the two
derived fields from the catalogue through the same functions that wrote them.
```

- [ ] **Step 3: `artifacts.md`, the `objective` section**

Replace "It is built from `00-slices.json` and `00-catalogue.json` alone — never a candidate `digest` — so this pass's dispatch is sized to the corpus map, not to the corpus." with:

```markdown
It is built from `00-slices.json` alone — never a candidate `digest`, and
never `00-catalogue.json` — so this pass's dispatch is sized to the corpus
map, not to the corpus.
```

Then, in "Fields worth knowing", change the `weight.bytes` gloss's source:

```markdown
Fields worth knowing: `objective_review.surfaces[].weight.bytes` (the sum of
each evidence candidate's entry in the plan's `catalogue_facts.candidate_bytes`
— the source file's size — never `slices[].bytes` or any other serialized
row's size, which saturates once the digest skeleton hits its 128-node cap);
```

- [ ] **Step 4: `limitations.md:953-954`**

The entry "### `supported` is ruled from a corpus map, not from the digests" currently says its input "is `request` plus a code-computed corpus map: the directory tree, kind and byte counts per subtree, the slice labels and their sizes. It reads no digest at all."

That last sentence was aspirational — the pass read the whole catalogue, digests included, and was merely told not to look. Replace those two sentences with:

```markdown
is `00-slices.json` alone: the slice labels and their sizes, each group's
provenance, and the `catalogue_facts` block's `request`, `policy`, exclusion
tally and per-candidate source bytes. It reads no digest, and as of the
`catalogue_facts` change that is structural rather than instructed — the file
it reads contains none.
```

- [ ] **Step 5: `limitations.md`, the fourteen-predicates entry at `:1649`**

Two edits inside it.

In the table of five inversions, the `…forbids_reading_candidate_digests` row is now historical — that predicate no longer exists. Append to that row's cell, inside the same table:

```
(replaced by a windowed `…forbids_reading_a_shard`; see below)
```

Then, after the paragraph ending "The design's bounding constraint is prose that nothing checks.", add:

```markdown
**The first one is now closed, and not by fixing the predicate.**
`rb-triage-objective`'s `reads` no longer names `catalogue`, and
`00-slices.json` carries no candidate digest, so the permission that inversion
granted has nothing left to grant. What remains reachable is a *shard*: seven
of them hold every candidate's full digest and on the tau2 corpus total
470,455 bytes against the catalogue's 472,799. So the prohibition moved rather
than resolved, and its replacement is windowed and measured in both
directions. Its status improved as well as its guard: reading the catalogue
was *in contract*, so nothing could call it a violation, whereas reading a
sibling's shard breaks the fan-out isolation rule and a read audit catches it.
Auditable is not the same as impossible, and the remaining thirteen are
untouched.
```

- [ ] **Step 6: `limitations.md`, one new entry**

Add it immediately after the "### The staged triage family has never been dispatched" entry, so the two sit together — this one is a consequence of that one:

```markdown
### Issue #3 was closed on arithmetic, and the run that would confirm it has not happened

The death issue #3 reports is real and was observed twice: the monolithic
`rb-triage` stage died on a 595KB / 351-candidate catalogue, once in context
compaction and once by exhausting its whole dollar budget. What closed the
issue is not a run that survived it. It is a partition whose shards measure
small enough to hold, plus a `catalogue_facts` block that takes the one
remaining unbounded pass from 472,799 bytes to 51,792 — both arithmetic over
catalogues that already existed, which is the entry above this one restated
about a specific issue.

The gap is narrow and worth naming precisely. That the objective pass's input
now fits one `Read` is measured and not in doubt. That a dispatch which *fits*
produces a better **judgment** than one that died is the claim the whole design
rests on, and it is the claim nothing here measures.

Recorded rather than parked-with-a-fix because the fix is a dispatch, not a
change: run the staged family against a parsec-class corpus and write what
happened into the passes' `exercise.md` files. Until then, a reader who finds
#3 closed should not infer that anyone watched `00-triage.json` get written on
the corpus that killed the monolith.
```

- [ ] **Step 7: Run the docs gate**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -v`

Expected: all pass. This module also enforces three policies on every user-facing document — no hand-typed test count, no heading that counts something that grows, and no citation of the recorded-history tree. The new `limitations.md` heading names an issue number, not a count of anything, so it is fine; a heading like "Four remaining gaps" would not be.

- [ ] **Step 8: Run the three gates**

```sh
make test && make check && uv run rubrica check-skills
```

`make check` matters here even though `docs/` is ruff-excluded: it is what catches an accidental edit to a non-excluded file.

- [ ] **Step 9: Commit**

```bash
git add docs/concepts/pipeline.md docs/reference/artifacts.md docs/design/limitations.md
git commit -S -s -m "docs: Record that the objective pass reads the plan alone

pipeline.md and artifacts.md follow the contract change. limitations.md gets
three edits.

The entry saying the objective pass 'reads no digest at all' was
aspirational: the pass read the whole catalogue, digests included, and was
merely told not to look. It is now structural -- the file it reads contains
none.

The fourteen-predicates entry records its first and most consequential
inversion as closed, and says how: not by fixing the predicate but by
removing what the inverted permission had to grant. The prohibition moved to
the shards, where its replacement is windowed and measured both ways, and
its status improved from in-contract to auditable. Auditable is not
impossible, and the other thirteen are untouched.

A new entry records that #3 closed on arithmetic. That the objective pass's
input now fits one Read is measured; that a dispatch which fits produces a
better judgment than one that died is the claim the design rests on and the
one nothing here measures.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
## Final verification

Run after Task 5 commits. This is the plan's actual claim, and it is measured on a real catalogue rather than on the toy fixture — the toy's three candidates cannot show a 9× reduction.

- [ ] **The three gates**

```sh
make test && make check && uv run rubrica check-skills
```

- [ ] **End to end on a real corpus**

Substitute any corpus of a few hundred files. The figures below are the tau2 ones from the spec; a different corpus gives different numbers and the same *shape*.

```sh
rm -rf /tmp/verify && mkdir -p /tmp/verify
uv run rubrica survey \
  --corpus ~/work/kaegis/tau2-bench/src/tau2 \
  --corpus ~/work/kaegis/tau2-bench/data/tau2/trajectories \
  --runs-dir /tmp/verify/runs --target-name tau2 --target-interface python \
  --objective breadth
RUN=$(ls -d /tmp/verify/runs/run-*)
uv run rubrica triage-slices --run "$RUN"
uv run rubrica validate --run "$RUN" --stage triage-slices; echo "validate: $?"
uv run rubrica check-refs --run "$RUN"; echo "check-refs: $?"

uv run python - "$RUN" <<'PY'
import json, sys
from pathlib import Path
run = Path(sys.argv[1])
cat = json.loads((run / "00-catalogue.json").read_bytes())
plan = json.loads((run / "00-slices.json").read_bytes())
cat_size = (run / "00-catalogue.json").stat().st_size
plan_size = (run / "00-slices.json").stat().st_size
facts = plan["catalogue_facts"]

print(f"catalogue        {cat_size:>9,}")
print(f"plan             {plan_size:>9,}   ratio {cat_size / plan_size:.2f}x")
print(f"Read ceiling     {262144:>9,}   plan {'FITS' if plan_size < 262144 else 'REFUSED'}")

assert facts["candidate_bytes"] == {c["candidate_id"]: c["bytes"] for c in cat["candidates"]}
assert facts["request"] == cat["request"] and facts["policy"] == cat["policy"]
assert facts["excluded"]["total"] == len(cat["excluded"])
print(f"candidate_bytes  {len(facts['candidate_bytes']):>9,} entries, all agreeing")
print(f"excluded         total {facts['excluded']['total']}, "
      f"by_reason {facts['excluded']['by_reason']}, "
      f"{len(facts['excluded']['entries'])} entries, "
      f"truncated {facts['excluded']['entries_truncated']}")

text = (run / "00-slices.json").read_text()
assert text.index('"catalogue_facts"') < text.index('"slices"')
assert text.index('"run_id"') < text.index('"slices"')
print("head-before-array: OK")
PY
```

Expected, asserted rather than eyeballed:

- `validate: 0` and `check-refs: 0`.
- The plan is well under 262,144 bytes and roughly an order of magnitude smaller than the catalogue. On tau2: **51,792 against 472,799, a 9.13× reduction.**
- `candidate_bytes` has one entry per catalogue candidate — 443 on tau2 — every one equal to that candidate's own `bytes`.
- `catalogue_facts` and `run_id` both precede `slices` in the file.

- [ ] **Nothing about the partition moved**

```sh
uv run python - "$RUN" <<'PY'
import json, sys
from pathlib import Path
run = Path(sys.argv[1])
from rubrica.slices import plan_slices
cat = json.loads((run / "00-catalogue.json").read_bytes())
plan = json.loads((run / "00-slices.json").read_bytes())
expected = plan_slices(cat["candidates"])
assert [s["id"] for s in plan["slices"]] == [s.id for s in expected]
assert [s["candidate_ids"] for s in plan["slices"]] == [list(s.candidate_ids) for s in expected]
shards = sorted((run / "00-slices").iterdir())
print(f"{len(plan['slices'])} slices, {len(shards)} shards, "
      f"largest slice {max(s['bytes'] for s in plan['slices']):,} bytes")
PY
```

Expected on tau2: **7 slices, 7 shards, largest 64,913 bytes** — the same figures as before this change, because nothing here touches `plan_slices`.

- [ ] **The pass's own contract**

```sh
uv run python -c "
from rubrica.skills import discover
o = next(s for s in discover() if s.name == 'rb-triage-objective')
print('reads:', o.contract['reads'])
assert o.contract['reads'] == ['slices']
"
uv run rubrica check-skills; echo "check-skills: $?"
```

- [ ] **Close issue #3**

Only after everything above is green. The comment must state what the fix rests on, per spec ruling 1 and the new `limitations.md` entry: the objective pass's input is measured to fit, and no staged run has been observed writing `00-triage.json` on the corpus that killed the monolith. A reader must not be left inferring the death was watched to be fixed.

---

## Self-Review

Run against the spec after writing, recorded here because a plan's own review is evidence about the plan.

**1. Spec coverage.** Every section maps to a task: §4.1's shape → Tasks 1-2; §4.2's writer → Task 2 Steps 4-5; §4.3's two gates and the shared-builder ruling → Task 3; §4.4's contract and prose → Task 4; §5's "what this does not fix" → Task 5 Steps 5-6; §6's tests → distributed across Tasks 1-4, with the both-directions obligation as Task 4 Step 10; §7's docs → Task 5; §8's rejected alternatives → nothing to implement; §9's verification → Final verification. **One deliberate divergence:** the field is `catalogue_facts`, not the spec's `catalogue_projection`, recorded in Global Constraints with the reason.

**2. Placeholder scan.** No "TBD", no "add appropriate error handling", no "similar to Task N". Every code step carries the code. Every prose step carries the prose to write, not a description of it. Two steps deliberately carry *no* code because their content is a single value — Task 4 Step 4's `reads = ["slices"]` and Task 5 Step 1's table cell.

**3. Type consistency.** `excluded_summary(excluded: list) -> dict` is defined in Task 1 and called in Task 2 (`catalogue_facts`) and Task 3 (`check_slices`) under that exact name. `candidate_bytes_index(candidates: list[dict]) -> dict[str, int]` likewise. Both are public because Task 3 imports them, which is stated in Task 1's Interfaces block before Task 3 needs it. The on-disk key is `catalogue_facts` in the schema (Task 2 Step 5), the builder (Task 2 Step 3), the checks (Task 3 Step 3), the skill prose (Task 4 Steps 5-8), the builders fixture (Task 2 Step 6) and every document (Task 5) — checked by grep, not by memory.

**4. Ordering.** Tasks 1→2→3 are strictly dependent: Task 2 calls Task 1's function, Task 3 imports both. Task 4 is independent of Task 3 and could run in parallel, but is sequenced after it so `check-refs` is already enforcing the block when the skill starts promising it exists. Task 5 must be last: `test_docs_accuracy.py` compares documents against code that Tasks 2-4 change.

**5. What no test in this plan reaches.** Whether a dispatched model actually reads only `00-slices.json`. That is what `scripts/audit-reads.sh` is for on a real dispatch, and it is the reason Task 4's prose spends a paragraph on the shards rather than trusting the contract alone.

**6. The plan's own code was run before the plan shipped.** Two things in it were prototyped rather than reasoned about, because a plan whose expected values are wrong costs an executor a whole task:

- **Task 1's seven assertions** were run against the exact implementation Task 1 Step 3 specifies. All seven hold. The byte-budget test keeps **17 of 40** entries at **7,806 bytes** — comfortably inside the 8,192 budget with the next entry breaking it, so the "longest prefix that fits" invariant is real and not an artifact of the padding chosen.
- **Task 2 Step 5's schema** was applied to a copy of `src/rubrica/schema/` under `RUBRICA_SCHEMA_DIR` and exercised six ways. A valid block validates; an absent one reports `'catalogue_facts' is a required property`; an unknown key inside the block is rejected; a non-integer byte value is rejected. Most importantly **the cross-file `$ref` resolves and constrains** — an entry missing `path` reports `'path' is a required property`, and a bad reason reports the catalogue schema's own eight-value enum. That `$ref` was the single most likely thing in this plan to be quietly wrong.

What was *not* prototyped, and where an executor should therefore expect to do real work: Task 3's findings (the pointer strings and messages are specified but unrun), and all of Task 4, whose subject is prose.
