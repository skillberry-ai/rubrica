# Staged Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `triage` dispatch with a code-sliced fan-out whose every dispatch reads a slice bounded by a cap code enforces, so no corpus size can kill the stage.

**Architecture:** `triage-slices` (code) partitions `00-catalogue.json` into byte-bounded shards keyed on `(root_index, directory)` with containers grouped by container; `rb-triage-objective` rules the objective from a code-computed corpus map; `rb-triage-rule` fans out one member per slice; `rb-triage-audit` writes deficiencies and projections from the parts; `triage-seal` (code) assembles `00-triage.json`, which keeps its path, schema and byte shape so nothing downstream of `intake` moves. Human gate 0 stays after the seal.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `jsonschema` + `referencing`, `ruff` (line-length 100, `select = ["E","F","I","UP","B","SIM"]`).

**Spec:** [`docs/superpowers/specs/2026-08-22-staged-triage-design.md`](../specs/2026-08-22-staged-triage-design.md) — read it before Task 1. Every task below cites the section it implements. Where this plan and the spec disagree, the spec is right and the plan is a bug.

## Global Constraints

- **Every commit is signed and DCO'd: `git commit -S -s`.** Both flags. If signing fails, **stop and report it** — never fall back to unsigned, never work around it.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with`.
- The three gates, all of which must pass before any commit: `make test`, `make check`, `uv run rubrica check-skills` (exit 0).
- **Never write a test count anywhere.** Not in a doc, not in a commit message, not in a comment.
- **No heading in any user-facing document may count something that grows** (stages, skills, subcommands, gates).
- **Never cite or edit the dated build-record tree.** `docs/README.md` alone may link it.
- The exit-code contract is load-bearing: `0` clean, `1` findings one per line on stdout, `2` usage error or unreadable/misconfigured run. **A stage defect must never surface as `2`. A `1` must never have empty stdout.**
- Comment density here is high and deliberate: comments explain *why*, usually citing a measurement. Match it; do not strip existing comments.
- `docs/` is `extend-exclude`d from ruff. `README.md` and `CLAUDE.md` are **not** — run `make check` after editing either.
- Work on branch `staged-triage`. Do not merge or push unless asked.
- Fan-out dispatches (Tasks 18+, not in this plan) cap at **3 concurrent** — the shared LiteLLM gateway returns envoy `503 upstream connect error` at 5+ concurrent streaming requests.

## Sequencing note: why `paths.STAGES` grows before it shrinks

Tasks 7–13 **add** the five new stages to `paths.STAGES` while `triage` is still there, and Task 14 removes `triage`. This transitional state is deliberate. `skills.expected_skill_names` derives from `paths.STAGES`, so removing `triage` before the three new skills exist makes `check-skills` reject the tree, and adding the new stages before their skills exist does the same. Growing first, then shrinking, is the only ordering where **every task ends with all three gates green**. Nothing releases from this branch mid-sequence, and `rb-orchestrate` never dispatched `triage` anyway, so no orchestrator can act on the transient duplicate.

## File Structure

**New source:**
- `src/rubrica/slices.py` — the slicing algorithm and the write side. One responsibility: turn a catalogue into a bounded partition and its shards. Owns `DEFAULT_SLICE_BYTES`.
- `src/rubrica/seal.py` — assemble `00-triage.json` from the parts. Mirrors `reconcile.py`'s pattern on the `staged-reconcile` branch: assembles, does not check, and writes nothing when it reports anything.
- `src/rubrica/schema/slices-0.1.json`, `objective-0.1.json`, `dispositions-part-0.1.json`, `audit-0.1.json`, `adoptions-0.1.json`.
- `src/rubrica/skills/rb-triage-objective/SKILL.md`, `rb-triage-rule/SKILL.md`, `rb-triage-audit/SKILL.md`.

**Modified source:**
- `src/rubrica/digest.py` — a total-node clamp on `_skeleton` (Task 1).
- `src/rubrica/survey.py` — a row-size guard (Task 3).
- `src/rubrica/schema/triage-0.1.json` — promote four inline definitions to `$defs` (Task 4).
- `src/rubrica/validate.py` — `ARTIFACT_SCHEMAS`, `STAGE_ARTIFACTS`, a `referencing` registry in `_validator_for` (Tasks 5, 7–13).
- `src/rubrica/paths.py` — `STAGES` and the new `RunPaths` members (Tasks 6–14).
- `src/rubrica/refs.py` — four new checkers plus `check_all` wiring (Tasks 8, 10).
- `src/rubrica/cli.py` — `triage-slices` and `triage-seal` subcommands (Tasks 7, 9).
- `src/rubrica/triage.py` — `adopt_projection` writes `00-adoptions.json` (Task 9).
- `src/rubrica/skills.py` — `CODE_ONLY_STAGES` (Task 7).
- `src/rubrica/brief.py` — gate 0's additions (Task 15).
- `scripts/render-pipeline-diagram.py`, `scripts/render-readme-diagram.py` — one `ROWS` entry per stage; the README fold (Tasks 7–14).
- `scripts/dispatch-stage.sh` — a `SLICE_LINE` case for `triage-rule` (Task 12).
- `tests/toy.py` — checkpoints and a multi-slice fixture (Task 16).
- Docs: `docs/concepts/pipeline.md`, `docs/reference/cli.md`, `docs/reference/artifacts.md`, `docs/concepts/glossary.md`, `docs/design/limitations.md`, `CLAUDE.md`.

---

### Task 1: Clamp the skeleton's total node count

Implements spec §6 item 1. **This is the precondition for boundedness** — a per-slice byte cap is unenforceable if one candidate row can exceed it.

**Files:**
- Modify: `src/rubrica/digest.py` (`_skeleton` at :178, `digest_for_payload`'s tail at ~:305)
- Test: `tests/unit/test_digest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `digest.py` module constant `_SKELETON_MAX_NODES = 128`. Digests of non-prose, non-source payloads gain a sibling key `skeleton_nodes_truncated: bool` beside `skeleton`.

**Why 128:** measured across every skeleton digest in four real catalogues (parsec, appworld, tau2, tau2+trajectories): median 4 nodes, 5 over 64, and exactly **1 over 128** — `ec2-pricing-json`, a 2.7MB pricing file yielding 261 nodes / 39,162 bytes in one candidate row. tau2's `results.json` digests are 69 nodes and must stay whole. So 128 binds on the outlier that motivated it and on nothing else.

- [ ] **Step 1: Write the failing tests**

```python
def test_skeleton_stops_at_the_node_cap_and_says_so():
    # A wide, deep payload: 32 keys at each of three levels is 32^3 pointers
    # if nothing bounds the total, which is the shape that produced a 39KB
    # candidate row on the real corpus.
    leaf = {f"k{i}": 1 for i in range(32)}
    mid = {f"m{i}": dict(leaf) for i in range(32)}
    payload = {f"t{i}": dict(mid) for i in range(32)}
    result = digest.digest_for_payload(payload, "other", body_chars=2000)
    assert len(result["skeleton"]) <= 128
    assert result["skeleton_nodes_truncated"] is True


def test_a_small_skeleton_is_not_marked_truncated():
    result = digest.digest_for_payload({"a": {"b": 1}}, "other", body_chars=2000)
    assert result["skeleton_nodes_truncated"] is False
    assert result["skeleton"]  # and it still has content


def test_the_clamp_does_not_touch_a_sixty_nine_node_skeleton():
    # tau2's results.json digests measure 69 nodes; the cap must not bind on
    # them, or a real trajectory capture loses shape to a fix aimed at a
    # pricing table.
    payload = {f"k{i}": {"a": 1, "b": 2} for i in range(23)}
    result = digest.digest_for_payload(payload, "other", body_chars=2000)
    assert result["skeleton_nodes_truncated"] is False
    assert len(result["skeleton"]) == 69


def test_trace_digests_carry_no_skeleton_key_at_all():
    # The clamp is a skeleton concern. A trace digest has no skeleton, so it
    # must not grow a truncation flag about one.
    result = digest.digest_for_payload({"trace_id": "t", "spans": []}, "trace", body_chars=2000)
    assert "skeleton" not in result
    assert "skeleton_nodes_truncated" not in result
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_digest.py -k "skeleton_stops or not_marked_truncated or sixty_nine or no_skeleton_key" -v`
Expected: FAIL — `KeyError: 'skeleton_nodes_truncated'` on the first three.

- [ ] **Step 3: Implement the clamp**

Add the constant beside `_SKELETON_MAX_CHILDREN` (~:55) with a comment carrying the measurement:

```python
# Total pointers a skeleton may hold, not just children per node. _SKELETON_DEPTH
# and _SKELETON_MAX_CHILDREN bound breadth and depth *per node*, which leaves the
# product unbounded: measured, a 2.7MB pricing table yielded 261 pointers and a
# 39,162-byte candidate row -- 6.8% of the parsec candidates array in one entry.
# A slice's byte cap cannot be enforced if a single row can exceed it, so this is
# a precondition for the fan-out and not a tidying. 128 binds on exactly one of
# the 209 skeleton digests measured across four real catalogues (that pricing
# file) and leaves tau2's 69-pointer trajectory digests whole.
_SKELETON_MAX_NODES = 128
```

Change `_skeleton` to stop once the budget is spent. It writes into `out`, so `len(out)` *is* the budget check — no extra parameter:

```python
def _skeleton(node: Any, pointer: str, depth: int, out: dict) -> None:
    # The total-node budget is checked here rather than by the callers because
    # recursion is where pointers are minted. Stopping mid-walk leaves a
    # *prefix* of the skeleton, which is why the flag below is written by the
    # caller: a reader must be able to tell a small object from a clamped one.
    if depth < 0 or len(out) >= _SKELETON_MAX_NODES:
        return
    ...  # body unchanged
```

Then in `digest_for_payload`'s tail, replace the two-line skeleton return with:

```python
    skeleton: dict[str, Any] = {}
    _skeleton(payload, "", _SKELETON_DEPTH, skeleton)
    # Stated rather than implied, for the reason keys_truncated is stated: a
    # truncation a prompt can see is a fact about the digest, and one it cannot
    # see is a lie about the candidate.
    return {"skeleton": skeleton, "skeleton_nodes_truncated": len(skeleton) >= _SKELETON_MAX_NODES}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_digest.py -v`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Check the catalogue schema still accepts the new key**

Run: `uv run pytest tests/unit -k "catalogue or schema" -q`
Expected: PASS. If `catalogue-0.1.json` sets `additionalProperties: false` on the digest object, add `skeleton_nodes_truncated` (type boolean) to its properties in the same commit — the schema is the reason to check rather than assume.

- [ ] **Step 6: Run all three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all pass, `check-skills` exits 0.

- [ ] **Step 7: Commit**

```bash
git add src/rubrica/digest.py tests/unit/test_digest.py src/rubrica/schema/catalogue-0.1.json
git commit -S -s -m "fix: Clamp a skeleton's total pointers, since breadth and depth leave the product unbounded

_SKELETON_DEPTH and _SKELETON_MAX_CHILDREN bound each node; nothing bounded the
total. Measured, a 2.7MB pricing table yielded 261 pointers and a 39,162-byte
candidate row -- 6.8% of the parsec candidates array in one entry. A per-slice
byte cap cannot be enforced while one row can exceed it, so this is the
precondition for staging triage rather than a tidying.

128 binds on exactly one of the 209 skeleton digests measured across four real
catalogues and leaves tau2's 69-pointer trajectory digests whole. The clamp is
recorded in the digest as skeleton_nodes_truncated, for the reason
keys_truncated is recorded: a truncation a prompt can see is a fact about the
digest, one it cannot see is a lie about the candidate.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: `slices.py` — the slicing algorithm

Implements spec §5, §5.1, §5.2. Pure functions over a candidates list; no filesystem, no CLI. Task 7 adds the write side.

**Files:**
- Create: `src/rubrica/slices.py`
- Test: `tests/unit/test_slices.py`

**Interfaces:**
- Consumes: `digest.py`'s output shape only as data (`candidate["digest"]["heuristics_fired"]`, `["names"]`).
- Produces:
  - `DEFAULT_SLICE_BYTES: int = 65536`
  - `@dataclass(frozen=True) class Slice: id: str; label: str; groups: tuple[str, ...]; candidate_ids: tuple[str, ...]; provenance: tuple[dict, ...]`
  - `def plan_slices(candidates: list[dict], *, cap: int = DEFAULT_SLICE_BYTES) -> list[Slice]`
  - `def row_bytes(candidate: dict) -> int` — a candidate's canonical byte cost, via `artifacts.canonical_bytes`.
  - `def oversized_rows(candidates: list[dict], *, cap: int = DEFAULT_SLICE_BYTES) -> list[tuple[str, int]]` — `(candidate_id, bytes)` for every row over the cap. Task 3 consumes this.

**Why 65536:** the harness refuses a whole-file `Read` at 256KB, and a member's shard must be one `Read`. 64KB leaves room for the `request`/`policy` head every shard carries plus indentation, and it produced 11 slices on parsec, 5 on appworld, 5 on tau2, 7 on tau2+trajectories.

**The algorithm, in order (spec §5):**
1. Container elements group by `container.candidate_id`; corpus files group by `(root_index, dirname(path))`. `root_index` is load-bearing: two roots may each hold `src/`, and every real catalogue measured is single-root so nothing on disk would catch the merge.
2. A group whose total fits `cap` is one unit.
3. An oversized corpus subtree recurses **top-down**: descend into children, keeping each child's whole subtree together, recursing only into children still over cap. Bottom-up roll-up is rejected — measured, it produced 20 slices on parsec with both failure modes at once (an 85-file kind-split mega-slice and eight 1-candidate orphans).
4. Leaf fallback for a single directory still over cap: split by `kind`, then by `candidate_id`.
5. An oversized container clusters on `(tuple(sorted(digest["heuristics_fired"])), tuple(sorted(digest["names"][:6])))` before splitting. Measured: 44 signatures over parsec's 130 elements, and `error_markers` fires on exactly **one** of them — the run's only failure evidence — which clustering makes a singleton by construction.
6. Packing is **adjacent siblings only**, in the recursion's own order. First-fit-decreasing is rejected: it fills a slice by size alone and spends the coherence the key buys.
7. Whole small containers may share a slice with each other (measured: 40 containers × 15 elements went from 40 slices of 21KB to 20).
8. Ids are `s01`, `s02`, … in plan order — short, stable, and valid path segments. The prose goes in `label`; packing concatenated group names into unreadable strings when the label was the identity.

- [ ] **Step 1: Write the failing tests**

```python
import json
from rubrica import slices
from rubrica.artifacts import canonical_bytes


def _cand(cid, *, path=None, kind="source_code", root=0, container=None, pad=1000, sig=None):
    """One catalogue candidate, padded to a known byte cost."""
    row = {"candidate_id": cid, "kind": kind, "bytes": pad, "sha256": "0" * 64,
           "admissible": True}
    if container:
        row |= {"origin": "container_element",
                "container": {"candidate_id": container, "json_pointer": f"/{cid}"}}
    else:
        row |= {"origin": "corpus", "path": path, "root_index": root}
    digest = {"_pad": "p" * pad}
    if sig:
        digest |= {"heuristics_fired": sig[0], "names": sig[1]}
    row["digest"] = digest
    return row


def test_every_candidate_lands_in_exactly_one_slice():
    cands = [_cand(f"c{i}", path=f"src/m{i}.py") for i in range(80)]
    plan = slices.plan_slices(cands, cap=16384)
    seen = [cid for s in plan for cid in s.candidate_ids]
    assert sorted(seen) == sorted(c["candidate_id"] for c in cands)
    assert len(seen) == len(set(seen))


def test_no_slice_exceeds_the_cap():
    cands = [_cand(f"c{i}", path=f"src/a/b/m{i}.py") for i in range(200)]
    plan = slices.plan_slices(cands, cap=16384)
    by_id = {c["candidate_id"]: c for c in cands}
    for s in plan:
        assert sum(slices.row_bytes(by_id[cid]) for cid in s.candidate_ids) <= 16384


def test_two_roots_with_the_same_directory_do_not_merge():
    # The bug real data caught: every measured catalogue is single-root, so a
    # key on `path` alone would merge two corpora's src/ and nothing on disk
    # would show it.
    cands = ([_cand(f"a{i}", path=f"src/m{i}.py", root=0) for i in range(4)]
             + [_cand(f"b{i}", path=f"src/m{i}.py", root=1) for i in range(4)])
    plan = slices.plan_slices(cands, cap=200)   # small cap: forces separate slices
    for s in plan:
        roots = {next(c for c in cands if c["candidate_id"] == cid)["root_index"]
                 for cid in s.candidate_ids}
        assert len(roots) == 1, f"slice {s.id} mixes roots {roots}"


def test_slice_labels_are_unique():
    cands = ([_cand(f"a{i}", path=f"m{i}.py", root=0) for i in range(3)]
             + [_cand(f"b{i}", path=f"m{i}.py", root=1) for i in range(3)])
    plan = slices.plan_slices(cands, cap=200)
    labels = [s.label for s in plan]
    assert len(labels) == len(set(labels)), labels


def test_slice_ids_are_safe_path_segments_in_order():
    from rubrica.paths import safe_segment
    plan = slices.plan_slices([_cand(f"c{i}", path=f"src/m{i}.py") for i in range(40)], cap=8192)
    assert [s.id for s in plan] == [f"s{i:02d}" for i in range(1, len(plan) + 1)]
    for s in plan:
        assert safe_segment(s.id) == s.id


def test_a_container_clusters_near_duplicates_into_one_slice():
    # 30 elements of one signature and 1 of another, with a cap that forces a
    # split: the singleton must not be packed into the middle of the family it
    # is not part of, and the family must not be scattered.
    family = [_cand(f"f{i}", kind="trace", container="cap",
                    sig=(["names", "status"], ["op_a"]), pad=900) for i in range(30)]
    odd = [_cand("odd", kind="trace", container="cap",
                 sig=(["names", "status", "error_markers"], ["op_b"]), pad=900)]
    plan = slices.plan_slices(family + odd, cap=8192)
    holding_odd = [s for s in plan if "odd" in s.candidate_ids]
    assert len(holding_odd) == 1
    # every other member of the odd slice shares its signature, or the slice
    # holds it alone -- what must never happen is the family being split
    # around it.
    fam_slices = {s.id for s in plan for cid in s.candidate_ids if cid.startswith("f")}
    assert len(fam_slices) == len({s.id for s in plan}) - 1 or "odd" not in \
        next(s for s in plan if s.id in fam_slices).candidate_ids


def test_provenance_states_how_much_of_a_group_a_slice_holds():
    # The homogeneous worst case: a member holding part of an identical family
    # cannot otherwise know it. Code knows; stating it takes no judgment away.
    cands = [_cand(f"h{i}", kind="trace", container="big",
                   sig=(["names"], ["same"]), pad=900) for i in range(60)]
    plan = slices.plan_slices(cands, cap=8192)
    assert len(plan) > 1
    for s in plan:
        entry = next(p for p in s.provenance if p["group"].startswith("container:big"))
        assert entry["in_this_slice"] == len(s.candidate_ids)
        assert entry["in_group_total"] == 60
        assert entry["other_slices"]
        assert s.id not in entry["other_slices"]


def test_a_flat_corpus_falls_through_to_kind_then_bytes():
    cands = [_cand(f"c{i}", path=f"all/f{i}.py") for i in range(120)]
    plan = slices.plan_slices(cands, cap=8192)
    assert len(plan) > 1
    assert sum(len(s.candidate_ids) for s in plan) == 120


def test_a_single_row_over_cap_is_reported_not_silently_split():
    big = _cand("mega", path="d/mega.json", kind="other", pad=40000)
    small = [_cand(f"n{i}", path="d/n.py") for i in range(3)]
    assert slices.oversized_rows([big] + small, cap=8192) == [("mega", slices.row_bytes(big))]
    assert slices.oversized_rows(small, cap=8192) == []


def test_planning_is_deterministic():
    cands = [_cand(f"c{i}", path=f"src/x{i % 7}/m{i}.py") for i in range(90)]
    first = slices.plan_slices(cands, cap=8192)
    second = slices.plan_slices(list(reversed(cands)), cap=8192)
    assert [(s.id, s.candidate_ids) for s in first] == [(s.id, s.candidate_ids) for s in second]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_slices.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rubrica.slices'`.

- [ ] **Step 3: Implement `slices.py`**

Write the module with a header comment stating *why* the algorithm is shaped this way, citing the measurements in the task header above (the rejected bottom-up roll-up and FFD packing, and the one `error_markers` element). Structure:

```python
"""Cutting a catalogue into slices a dispatch can hold.

The catalogue is the only input triage has, and on a real corpus it does not fit
one dispatch: 595KB / 351 candidates killed three of them, one in context
compaction and one by exhausting its whole dollar budget. Chunked reads do not
help -- reading 595KB in thirty pieces is still having read 595KB -- so the fix
is to bound what any single dispatch reads, which means partitioning the
candidates rather than summarising them.

Code rather than a prompt, and that inverts the reconcile family on purpose:
cutting requires seeing every candidate, so a prompt that cut the slices would
itself be the unbounded dispatch. What makes it acceptable where a heuristic
filter would not is that nothing here *decides* anything -- every candidate
still reaches a member, still gets a reasoned disposition, and is still
overrulable per candidate by a human at gate 0. A slice is a reading unit, not
a decision unit.
"""
```

- `row_bytes(candidate)` — `len(canonical_bytes(candidate))`.
- `_signature(candidate)` — the clustering key from §5 step 5; returns a stable tuple, tolerating a missing `digest`, a missing `heuristics_fired`, or a `names` that is not a list (a malformed digest is `check-refs`' finding, not a crash here).
- `_split_tree(prefix, members, cap)` — the top-down recursion, §5 step 3.
- `_split_by_kind_then_bytes(label, members, cap)` — §5 step 4, sorting by `candidate_id` so the result is deterministic.
- `_split_container(label, members, cap)` — §5 step 5, largest family first.
- `_pack_adjacent(units, cap)` — §5 step 6.
- `plan_slices(candidates, *, cap)` — groups per §5 step 1, dispatches to the splitters, packs whole small containers together (§5 step 7), then mints `s01…` ids, derives each `label` from the units it covers, and computes `provenance` (§5.2) as one entry per group the slice touches: `{"group": str, "in_this_slice": int, "in_group_total": int, "other_slices": tuple[str, ...]}`.
- `oversized_rows(candidates, *, cap)` — Task 3's input.

Determinism is a requirement, not an accident: sort every group's members by `candidate_id` and every group key before iterating, so `plan_slices` is invariant to input order (`test_planning_is_deterministic`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_slices.py -v`
Expected: PASS.

- [ ] **Step 5: Add the corpus-shape table as tests**

Spec §5.3 lists ten synthetic shapes. Add one test per shape asserting, for each, that **every candidate is accounted for exactly once** and **no slice exceeds the cap** — except the "one 200KB row" shape, which asserts `oversized_rows` reports it (the cap cannot hold, and Task 3 is what refuses it). Build the shapes with the `_cand` helper; do not import the throwaway prototype.

```python
import pytest

SHAPES = {
    "flat": lambda: [_cand(f"c{i}", path=f"all/f{i}.py") for i in range(400)],
    "dominant_subtree": lambda: ([_cand(f"d{i}", path=f"src/a/b/c/d{i}.py") for i in range(380)]
                                 + [_cand(f"t{i}", path=f"t{i}.md", kind="design_doc")
                                    for i in range(20)]),
    "deep_narrow": lambda: [_cand(f"n{i}", path="/".join(f"l{j}" for j in range(12)) + f"/n{i}.py")
                            for i in range(300)],
    "many_containers": lambda: [_cand(f"c{c}e{e}", kind="trace", container=f"cont{c}",
                                      sig=(["names"], [f"op{c}"]))
                                for c in range(40) for e in range(15)],
    "homogeneous_container": lambda: [_cand(f"h{i}", kind="trace", container="big",
                                            sig=(["names"], ["same"])) for i in range(500)],
    "unique_signatures": lambda: [_cand(f"u{i}", kind="trace", container="big",
                                        sig=(["names"], [f"u{i}"])) for i in range(500)],
    "multi_root": lambda: ([_cand(f"r{r}s{i}", path=f"src/m{i}.py", root=r)
                            for r in range(3) for i in range(60)]
                           + [_cand(f"r{r}t{i}", path=f"tests/t{i}.py", root=r)
                              for r in range(3) for i in range(40)]),
    "few_huge_rows": lambda: [_cand(f"g{i}", path=f"d/g{i}.json", kind="other", pad=30000)
                              for i in range(20)],
    "tiny": lambda: [_cand(f"s{i}", path=f"s{i}.md", kind="design_doc") for i in range(5)],
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_corpus_shape_partitions_within_the_cap(name):
    cands = SHAPES[name]()
    plan = slices.plan_slices(cands, cap=slices.DEFAULT_SLICE_BYTES)
    seen = [cid for s in plan for cid in s.candidate_ids]
    assert sorted(seen) == sorted(c["candidate_id"] for c in cands)
    by_id = {c["candidate_id"]: c for c in cands}
    for s in plan:
        assert sum(slices.row_bytes(by_id[cid]) for cid in s.candidate_ids) \
            <= slices.DEFAULT_SLICE_BYTES
```

- [ ] **Step 6: Run the shape tests**

Run: `uv run pytest tests/unit/test_slices.py -v`
Expected: PASS, every shape.

- [ ] **Step 7: All three gates, then commit**

```bash
make test && make check && uv run rubrica check-skills
git add src/rubrica/slices.py tests/unit/test_slices.py
git commit -S -s -m "feat: Cut a catalogue into byte-bounded slices, keyed on structure survey already knows

Measured across four real catalogues and ten synthetic shapes at a 64KB cap:
every candidate accounted for in all fourteen. Rejects bottom-up roll-up, which
produced an 85-file kind-split mega-slice and eight 1-candidate orphans on
parsec, and first-fit-decreasing packing, which spends the coherence the key
buys. Containers cluster on digest signature -- 44 signatures over parsec's 130
elements, with error_markers firing on exactly one, so the run's only failure
evidence becomes a singleton by construction rather than by luck.

Slices carry provenance about the group they are part of, because a member
holding 42 of 500 identical-signature elements cannot otherwise know it, and
code can say so for free.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: `survey` refuses a candidate row larger than a slice

Implements spec §6 item 2. A misconfigured run, so **exit 2**, in the same shape as the existing candidate and byte guards.

**Files:**
- Modify: `src/rubrica/survey.py` (the guard block at :464–:513, beside the `max_candidates` and `max_catalogue_bytes` checks)
- Test: `tests/unit/test_survey.py`

**Interfaces:**
- Consumes: `slices.oversized_rows`, `slices.DEFAULT_SLICE_BYTES` (Task 2).
- Produces: nothing new for later tasks. `survey()` gains no parameter — the cap is the module default, because a survey that produced rows too large for the default slice would mint a run no `triage-slices` invocation could partition.

- [ ] **Step 1: Write the failing test**

```python
def test_survey_refuses_a_corpus_whose_digest_row_exceeds_a_slice(tmp_path):
    # A file wide and deep enough to survive the Task 1 clamp and still exceed
    # one slice would have to be pathological; construct the condition directly
    # by lowering nothing and raising the corpus instead.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # 128 pointers of very long key names: the clamp bounds the node count, not
    # each node's width, so a row can still be large.
    payload = {("k" * 900) + str(i): {"a": 1} for i in range(200)}
    (corpus / "wide.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(UsageError) as exc:
        survey.survey(corpus_roots=[corpus], runs_dir=tmp_path / "runs",
                      target_name="t", target_interface="http", objective="breadth")
    message = str(exc.value)
    assert "wide-json" in message           # names the candidate
    assert str(slices.DEFAULT_SLICE_BYTES) in message   # names both numbers
    assert not (tmp_path / "runs").exists()  # leaves no directory behind


def test_survey_leaves_a_normal_corpus_alone(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "notes.md").write_text("# A\nprose\n", encoding="utf-8")
    run = survey.survey(corpus_roots=[corpus], runs_dir=tmp_path / "runs",
                        target_name="t", target_interface="http", objective="breadth")
    assert run.catalogue.is_file()
```

- [ ] **Step 2: Run to verify the first fails**

Run: `uv run pytest tests/unit/test_survey.py -k "digest_row_exceeds or normal_corpus" -v`
Expected: FAIL — no `UsageError` raised; the run is minted.

- [ ] **Step 3: Implement the guard**

Insert **before** the `max_catalogue_bytes` check and before `mkdir`, so a rejected run leaves no directory behind — the same ordering and the same reasoning the two existing guards already carry:

```python
    # Before the byte cap, because this one is not about the catalogue's total:
    # a candidate row larger than one slice cannot be partitioned at all, and
    # no repair prompt can shrink it. `triage-slices` would have to either
    # exceed its cap or drop the candidate, and dropping one silently is the
    # failure this whole stage exists to prevent.
    oversized = slices_module.oversized_rows(candidates)
    if oversized:
        named = ", ".join(f"{cid} at {size} bytes" for cid, size in oversized[:5])
        raise UsageError(
            f"{len(oversized)} candidate row(s) exceed one slice of "
            f"{slices_module.DEFAULT_SLICE_BYTES} bytes: {named}; narrow --corpus or "
            "--exclude these files -- a row this large cannot be sliced, so triage "
            "could never be dispatched over it"
        )
```

Import as `from rubrica import slices as slices_module` at the top, matching the file's existing `from rubrica import digest as digest_module` idiom.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_survey.py -v`
Expected: PASS.

- [ ] **Step 5: Confirm no real catalogue regresses**

Run:
```bash
uv run rubrica survey --corpus tests/fixtures/toy --runs-dir /tmp/t3 \
  --target-name toy --target-interface http --objective breadth && echo "toy OK"
```
Expected: prints a run path, then `toy OK`. If it raises, the cap or the clamp is wrong — stop and report rather than raising `DEFAULT_SLICE_BYTES` to make it pass.

- [ ] **Step 6: All three gates, then commit**

```bash
make test && make check && uv run rubrica check-skills
git add src/rubrica/survey.py tests/unit/test_survey.py
git commit -S -s -m "fix: Refuse at survey a candidate row larger than one slice

Boundedness by construction requires that no candidate row exceed the slice cap:
a slice holding one candidate is already minimal, so no partitioning scheme can
fix it and no repair prompt can shrink a corpus. Exit 2 with both numbers and the
candidate named, before mkdir, so a rejected run leaves no directory behind --
the ordering the max_candidates and max_catalogue_bytes guards already use.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: Promote `triage-0.1.json`'s element definitions to `$defs`

Implements spec §7's first paragraph. A refactor with **no semantic change**: the sealed schema must accept and reject exactly what it did before. Nothing in Task 5 can `$ref` these until it is done.

**Files:**
- Modify: `src/rubrica/schema/triage-0.1.json`
- Test: `tests/unit/test_schemas_planning.py` (or the module that already validates triage documents — find it with `grep -rl "triage-0.1" tests/`)

**Interfaces:**
- Produces: four new `$defs` in `triage-0.1.json`, `$ref`-able from part schemas as `triage-0.1.json#/$defs/<name>`:
  - `disposition` — today inline at `properties.dispositions.items`, `required: ["candidate_id", "disposition", "reason", "authority"]`
  - `surface` — today inline at `properties.objective_review.properties.surfaces.items`
  - `deficiency` — today inline at `properties.deficiencies.items`, `required: ["deficiency_id", "subject", "statement"]`
  - `projection` — today inline at `properties.projections.items`, `required: ["projection_id", "closes", "sources", "wanted", "method", "acceptance", "boundary"]`
- The existing `$defs` (`id`, `kind`, `decline_reason`) are untouched.

**Rejected:** `$ref`-ing an inline subschema by pointer (`#/properties/dispositions/items`). Valid JSON Schema, and it couples every part schema to the sealed schema's *layout* rather than to a named definition — a later reshuffle of `properties` would break four files silently.

- [ ] **Step 1: Write the equivalence test first**

```python
def test_promoting_definitions_did_not_change_what_triage_accepts():
    """The refactor's whole claim. A document that validated before must
    validate now, and one that failed must still fail for the same reason."""
    schema = json.loads((SCHEMA_DIR / "triage-0.1.json").read_text())
    assert set(schema["$defs"]) >= {"disposition", "surface", "deficiency", "projection"}
    # The four properties now reference rather than restate.
    assert schema["properties"]["dispositions"]["items"] == \
        {"$ref": "#/$defs/disposition"}
    assert schema["properties"]["deficiencies"]["items"] == {"$ref": "#/$defs/deficiency"}
    assert schema["properties"]["projections"]["items"] == {"$ref": "#/$defs/projection"}
    assert schema["properties"]["objective_review"]["properties"]["surfaces"]["items"] == \
        {"$ref": "#/$defs/surface"}
    # And the definitions kept their contracts.
    assert schema["$defs"]["disposition"]["required"] == \
        ["candidate_id", "disposition", "reason", "authority"]
    assert schema["$defs"]["deficiency"]["required"] == \
        ["deficiency_id", "subject", "statement"]
    assert schema["$defs"]["projection"]["required"] == \
        ["projection_id", "closes", "sources", "wanted", "method", "acceptance", "boundary"]


def test_a_disposition_missing_authority_still_fails(tmp_path):
    """The strongest evidence that the move was semantic-free is a negative
    case: promote-and-forget-a-constraint validates everything."""
    run = build_toy_run(tmp_path / "runs")
    build_toy_catalogue_and_triage(run)
    record = read_json(run.triage)
    del record["dispositions"][0]["authority"]
    write_json(run.triage, record)
    findings = validate.validate_stage(run, "triage")
    assert findings, "a disposition without authority must still fail layer 1"
```

- [ ] **Step 2: Run to verify the first fails, the second passes**

Run: `uv run pytest tests/unit -k "promoting_definitions or missing_authority" -v`
Expected: the first FAILS (`KeyError: 'disposition'`); the second already PASSES and must keep passing.

- [ ] **Step 3: Do the move**

Cut each of the four inline `items` objects into `$defs` under its name, replace each with `{"$ref": "#/$defs/<name>"}`, and change nothing else — no added constraint, no removed one, no reordered `required`. Keep every `description` with the definition it describes: a schema is read by people, and the branch's own limitation entries cite schema descriptions as where a reader of the schema rather than the prompt finds a rule.

- [ ] **Step 4: Run the tests, plus every existing triage-schema test**

Run: `uv run pytest tests/unit -k "triage or schema" -v`
Expected: PASS, all of them.

- [ ] **Step 5: All three gates, then commit**

```bash
make test && make check && uv run rubrica check-skills
git add src/rubrica/schema/triage-0.1.json tests/unit/test_schemas_planning.py
git commit -S -s -m "refactor: Promote triage's element definitions to \$defs so part schemas can reference them

Four staged-triage part schemas need a disposition, a surface, a deficiency and a
projection, and all four were defined inline under properties where nothing can
\$ref them. Derive, do not restate -- so they move to \$defs rather than being
copied into four files. Referencing them by pointer into properties was
considered and rejected: it couples the part schemas to this schema's layout, so
a later reshuffle would break four files silently.

No semantic change, and the negative case is what says so: a disposition missing
authority still fails layer 1.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 5: The five part schemas and the `$ref` registry

Implements spec §7. **Coordinate with the `staged-reconcile` branch**: it makes the same `validate._validator_for` change for its own part schemas. If it has landed on `main`, skip Step 3 and verify the registry works; if not, this is a shared prerequisite implemented once here.

**Files:**
- Create: `src/rubrica/schema/slices-0.1.json`, `objective-0.1.json`, `dispositions-part-0.1.json`, `audit-0.1.json`, `adoptions-0.1.json`
- Modify: `src/rubrica/validate.py` (`ARTIFACT_SCHEMAS` at :34, `_validator_for` at :132)
- Test: `tests/unit/test_validate_registry.py` (new), `tests/unit/test_schemas_instance.py`

**Interfaces:**
- Consumes: Task 4's `$defs`.
- Produces: `ARTIFACT_SCHEMAS` entries for kinds `slices`, `objective`, `dispositions-part`, `audit`, `adoptions`. `STAGE_ARTIFACTS` is **not** touched here — Tasks 7–13 add each stage with its kind, so layer 1 never demands an artifact from a stage that does not yet exist.

**Document shapes** (all carry `schema_version: "0.1"` and `run_id`, and all set `additionalProperties: false` at the root, matching the house style):

- `slices-0.1.json` — `slices: [{id, label, groups: [str], bytes: int, candidate_ids: [id], provenance: [{group, in_this_slice, in_group_total, other_slices: [str]}]}]`, plus `cap_bytes: int`. `id` `$ref`s `triage-0.1.json#/$defs/id`, so a slice id is held to the same path-segment rule every id in this pipeline is. `slices` has `minItems: 1` — a catalogue with candidates always yields at least one slice, and zero slices is a slicer defect rather than a judgment.
- `objective-0.1.json` — `objective_review: {declared_objective, supported, notes, recommended_objective, surfaces: [$ref surface]}` (the same object the sealed record carries, so the seal copies rather than transforms it), plus `predicted_surface_count: int` for §4.1's divergence.
- `dispositions-part-0.1.json` — `slice_id: $ref id`, `dispositions: [$ref disposition]` with `minItems: 1`, `observed_surfaces: [$ref surface]`, `deficiency_notes: [{candidate_id, statement}]`. `minItems: 1` because a slice always holds at least one candidate and every candidate is ruled: an empty part is a member that wrote nothing, not a member with nothing to say.
- `audit-0.1.json` — `deficiencies: [$ref deficiency]`, `projections: [$ref projection]`. Both required, both may be empty — spec §2's rule that an empty block is still written, and is itself a claim.
- `adoptions-0.1.json` — `adoptions: [{candidate_id, disposition: {$ref disposition}, projection_id, closed_deficiency_ids: [id]}]`. Required, may be empty.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_new_kind_has_a_schema_that_loads():
    for kind in ("slices", "objective", "dispositions-part", "audit", "adoptions"):
        assert kind in validate.ARTIFACT_SCHEMAS
        path = SCHEMA_DIR / validate.ARTIFACT_SCHEMAS[kind]
        assert path.is_file(), path
        json.loads(path.read_text())


def test_a_part_schema_resolves_its_cross_file_ref_without_network():
    """The registry's whole job. Without it Draft202012Validator would try to
    resolve triage-0.1.json over the network and fail on an offline box."""
    part = {"schema_version": "0.1", "run_id": "run-1", "slice_id": "s01",
            "dispositions": [{"candidate_id": "c1", "disposition": "admit",
                              "reason": "behavioural evidence", "authority": "triage",
                              "priority": 1}],
            "observed_surfaces": [], "deficiency_notes": []}
    assert validate.validate_document(part, "dispositions-part") == []


def test_a_part_schema_rejects_a_disposition_the_shared_def_rejects():
    """Proves the $ref is load-bearing rather than decorative: the constraint
    that fails here is defined only in triage-0.1.json."""
    part = {"schema_version": "0.1", "run_id": "run-1", "slice_id": "s01",
            "dispositions": [{"candidate_id": "c1", "disposition": "admit",
                              "reason": "x"}],  # no authority
            "observed_surfaces": [], "deficiency_notes": []}
    assert validate.validate_document(part, "dispositions-part")


def test_the_registry_still_honours_RUBRICA_SCHEMA_DIR(tmp_path, monkeypatch):
    """The cache key is (kind, schema_root); a registry keyed on kind alone
    would serve a stale validator after the override changed."""
    shutil.copytree(SCHEMA_DIR, tmp_path / "schema")
    stub = json.loads((tmp_path / "schema" / "audit-0.1.json").read_text())
    stub["required"] = ["schema_version", "run_id", "deficiencies", "projections", "sentinel"]
    stub["properties"]["sentinel"] = {"type": "string"}
    (tmp_path / "schema" / "audit-0.1.json").write_text(json.dumps(stub))
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path / "schema"))
    doc = {"schema_version": "0.1", "run_id": "r", "deficiencies": [], "projections": []}
    assert validate.validate_document(doc, "audit"), "the overridden schema must take effect"


def test_an_unreadable_schema_dir_exits_two_not_one(tmp_path, monkeypatch):
    """validate.py is on the list of modules whose unreadable-input paths must
    be tested: a misconfigured run is 2, a stage defect is 1."""
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path / "nope"))
    with pytest.raises(UsageError):
        validate.validate_document({"schema_version": "0.1"}, "audit")
```

Adapt the two helper names (`validate_document`, `SCHEMA_DIR`) to whatever `validate.py` actually exports — read it rather than assuming; if there is no document-level entry point, drive the tests through `validate_stage` against a run built by `tests/toy.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_validate_registry.py -v`
Expected: FAIL — the kinds are absent from `ARTIFACT_SCHEMAS`.

- [ ] **Step 3: Add the `referencing` registry to `_validator_for`**

`_validator_for(kind, schema_root)` currently builds `Draft202012Validator(schema)` with no registry, so a cross-file `$ref` attempts network resolution. Populate a `referencing.Registry` from every `*.json` in `schema_root`, keyed by filename, and pass it. Keep the existing `(kind, schema_root)` cache key so `RUBRICA_SCHEMA_DIR` still takes effect — a registry cached under `kind` alone would serve a stale validator after the override changed, which is what the fourth test above pins.

Add `referencing` to `pyproject.toml` dependencies if it is not already a transitive pin you can rely on directly; `uv lock` afterwards and commit `uv.lock`.

- [ ] **Step 4: Write the five schemas**

Follow the house style in an existing schema: `$schema`, `$id`, `title`, `type: object`, `required`, `additionalProperties: false`, `properties`, and a `description` on every property that a reader would otherwise have to infer. `description` is where a rule lands for someone reading the schema rather than the prompt.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_validate_registry.py tests/unit/test_schemas_instance.py -v`
Expected: PASS.

- [ ] **Step 6: All three gates, then commit**

```bash
make test && make check && uv run rubrica check-skills
git add src/rubrica/schema/ src/rubrica/validate.py tests/unit/ pyproject.toml uv.lock
git commit -S -s -m "feat: Add the staged-triage part schemas, referencing triage's shared definitions

Five kinds, one per artifact the split produces, because layer 1 is what stops a
stage passing trivially. Each part schema \$refs triage-0.1.json's \$defs rather
than restating a disposition or a projection, which needs a referencing registry
in _validator_for -- it built a validator with none, so a cross-file \$ref would
have attempted network resolution. Keyed on (kind, schema_root) as before, so
RUBRICA_SCHEMA_DIR still takes effect and a stale validator is not served after
the override changes.

STAGE_ARTIFACTS is deliberately untouched: each stage claims its kind when the
stage itself lands, so layer 1 never demands an artifact from a stage that does
not exist yet.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: `RunPaths` members for the new artifacts

Implements spec §7's path list. Additive: no stage claims them yet, so every gate stays green.

**Files:**
- Modify: `src/rubrica/paths.py` (properties after `triage` at :134; id-taking methods after `claims` at :189)
- Test: `tests/unit/test_paths.py`

**Interfaces:**
- Produces, on `RunPaths`:

| member | path |
|---|---|
| `slices` (property) | `00-slices.json` |
| `slices_dir` (property) | `00-slices/` |
| `slice_shard(slice_id)` | `00-slices/<slice_id>.json` |
| `objective` (property) | `00-objective.json` |
| `dispositions_dir` (property) | `00-dispositions/` |
| `disposition_part(slice_id)` | `00-dispositions/<slice_id>.json` |
| `audit` (property) | `00-audit.json` |
| `adoptions` (property) | `00-adoptions.json` |
| `slice_ids_with_parts()` | sorted slice ids that have a file in `00-dispositions/` |

- [ ] **Step 1: Write the failing tests**

```python
def test_the_new_triage_paths_sit_in_the_double_zero_band(tmp_path):
    run = RunPaths(tmp_path / "run-1")
    assert run.slices.name == "00-slices.json"
    assert run.slices_dir.name == "00-slices"
    assert run.objective.name == "00-objective.json"
    assert run.dispositions_dir.name == "00-dispositions"
    assert run.audit.name == "00-audit.json"
    assert run.adoptions.name == "00-adoptions.json"


def test_a_slice_id_that_would_escape_the_run_is_refused(tmp_path):
    run = RunPaths(tmp_path / "run-1")
    for evil in ("../etc", "a/b", "..", ""):
        with pytest.raises(UnsafeSegment):
            run.slice_shard(evil)
        with pytest.raises(UnsafeSegment):
            run.disposition_part(evil)


def test_slice_ids_with_parts_lists_only_what_is_on_disk(tmp_path):
    run = RunPaths(tmp_path / "run-1")
    assert run.slice_ids_with_parts() == []
    run.dispositions_dir.mkdir(parents=True)
    (run.dispositions_dir / "s02.json").write_text("{}", encoding="utf-8")
    (run.dispositions_dir / "s01.json").write_text("{}", encoding="utf-8")
    (run.dispositions_dir / "notes.txt").write_text("x", encoding="utf-8")
    assert run.slice_ids_with_parts() == ["s01", "s02"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_paths.py -k "double_zero_band or would_escape or with_parts" -v`
Expected: FAIL — `AttributeError: 'RunPaths' object has no attribute 'slices'`.

- [ ] **Step 3: Implement the members**

Route every id through `safe_segment` — the same way `claims`, `instance_dir` and `verdict` already do — so an id from an artifact cannot escape the run directory. Use `list_json` for `slice_ids_with_parts`, following `_contradiction_part_stems`' shape on the `staged-reconcile` branch and `_instance_dir_names` on `main`: listing is done in one place because callers were getting it wrong in two ways.

Give `slices` a docstring saying **why** it is in the `00-` band — the band means "what this run will be allowed to know", the numbering stays intake's, and everything between the catalogue and the sealed record is one logical step engineered as substeps. `catalogue`'s docstring at :124 is the model.

- [ ] **Step 4: Run the tests, then all three gates, then commit**

```bash
uv run pytest tests/unit/test_paths.py -v
make test && make check && uv run rubrica check-skills
git add src/rubrica/paths.py tests/unit/test_paths.py
git commit -S -s -m "feat: Add RunPaths members for the staged-triage artifacts

All in the 00- band, whose meaning -- what this run will be allowed to know --
covers the whole family rather than the catalogue alone. Every id-taking member
routes through safe_segment, so a slice id read out of an artifact cannot escape
the run directory.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 7: `rubrica triage-slices`

Implements spec §5's write side and adds the first new stage. **This is the first task that changes `paths.STAGES`** — read the sequencing note at the top of this plan before starting.

**Files:**
- Modify: `src/rubrica/slices.py` (add the write side), `src/rubrica/cli.py`, `src/rubrica/paths.py` (`STAGES`), `src/rubrica/validate.py` (`STAGE_ARTIFACTS`), `src/rubrica/skills.py` (`CODE_ONLY_STAGES`), `scripts/render-pipeline-diagram.py` (`ROWS`), `scripts/render-readme-diagram.py` (`PHASES`), `docs/reference/cli.md`, `docs/concepts/pipeline.md`, `docs/reference/artifacts.md`
- Regenerate: `docs/concepts/pipeline-diagram.html`, `docs/assets/how-it-works.svg`, `docs/assets/how-it-works-dark.svg`
- Test: `tests/unit/test_slices.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `plan_slices`, `Slice`, `oversized_rows` (Task 2); `RunPaths.slices`, `.slices_dir`, `.slice_shard` (Task 6); the `slices` schema (Task 5).
- Produces: `slices.write_slices(run: RunPaths, *, cap: int = DEFAULT_SLICE_BYTES) -> tuple[Path, list[Slice]]`, and the CLI subcommand `("triage-slices", "partition a catalogue into byte-bounded slices a dispatch can read")`.

**What a shard holds:** the run's `request` and `policy` verbatim from the catalogue, `run_id`, `slice_id`, the slice's `provenance`, and that slice's full candidate records. So a member's whole input is **one `Read`** under the harness's 256KB refusal, and the tail-metadata hunt disappears — the head fields are in every shard by construction, rather than 608KB into a file a chunk reader has to seek through.

- [ ] **Step 1: Write the failing tests**

```python
def test_writing_slices_produces_one_shard_per_slice_each_readable_whole(tmp_path):
    run = survey.survey(corpus_roots=[Path("tests/fixtures/toy")], runs_dir=tmp_path / "runs",
                        target_name="toy", target_interface="http", objective="breadth")
    path, plan = slices.write_slices(run, cap=2048)   # small cap: forces several
    assert path == run.slices
    assert len(plan) > 1
    for s in plan:
        shard = read_json(run.slice_shard(s.id))
        assert shard["slice_id"] == s.id
        assert shard["run_id"] == read_json(run.catalogue)["run_id"]
        # The head fields every member needs, in every shard, by construction.
        assert shard["request"] == read_json(run.catalogue)["request"]
        assert shard["policy"] == read_json(run.catalogue)["policy"]
        assert [c["candidate_id"] for c in shard["candidates"]] == list(s.candidate_ids)
        assert len(canonical_bytes(shard)) < 256 * 1024   # one Read
    assert validate.validate_stage(run, "triage-slices") == []


def test_writing_slices_is_idempotent(tmp_path):
    """Re-runnable, because Task 9's adoption path re-mints the plan after a
    human admits a projection."""
    run = survey.survey(corpus_roots=[Path("tests/fixtures/toy")], runs_dir=tmp_path / "runs",
                        target_name="toy", target_interface="http", objective="breadth")
    slices.write_slices(run)
    first = run.slices.read_bytes()
    shards_first = sorted(p.name for p in run.slices_dir.iterdir())
    slices.write_slices(run)
    assert run.slices.read_bytes() == first
    assert sorted(p.name for p in run.slices_dir.iterdir()) == shards_first


def test_a_stale_shard_from_a_previous_plan_is_removed(tmp_path):
    """Otherwise a re-plan leaves an orphan shard on disk that check_slices
    would report against a plan that no longer names it."""
    run = survey.survey(corpus_roots=[Path("tests/fixtures/toy")], runs_dir=tmp_path / "runs",
                        target_name="toy", target_interface="http", objective="breadth")
    slices.write_slices(run)
    (run.slices_dir / "s99.json").write_text("{}", encoding="utf-8")
    slices.write_slices(run)
    assert not (run.slices_dir / "s99.json").exists()


def test_triage_slices_exits_two_on_a_catalogue_with_no_candidates(tmp_path):
    """Spec 10.2: a refusal condition that moves from the prompt to code. It is
    a survey defect or a broken run, and code detects it without a dispatch."""
    run = RunPaths(tmp_path / "run-1")
    run.root.mkdir(parents=True)
    write_json(run.catalogue, {"schema_version": "0.1", "run_id": "run-1", "created_utc": "z",
                               "request": {}, "policy": {}, "candidates": [], "excluded": []})
    assert main(["triage-slices", "--run", str(run.root)]) == 2


def test_triage_slices_exits_two_on_an_unreadable_catalogue(tmp_path):
    run = RunPaths(tmp_path / "run-1")
    run.root.mkdir(parents=True)
    run.catalogue.write_text("{not json", encoding="utf-8")
    assert main(["triage-slices", "--run", str(run.root)]) == 2


def test_triage_slices_exits_zero_and_prints_the_plan(tmp_path, capsys):
    run = survey.survey(corpus_roots=[Path("tests/fixtures/toy")], runs_dir=tmp_path / "runs",
                        target_name="toy", target_interface="http", objective="breadth")
    assert main(["triage-slices", "--run", str(run.root)]) == 0
    out = capsys.readouterr().out
    assert "s01" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_slices.py tests/unit/test_cli.py -k "shard or idempotent or stale or triage_slices" -v`
Expected: FAIL — `AttributeError: module 'rubrica.slices' has no attribute 'write_slices'`.

- [ ] **Step 3: Implement `write_slices`**

Reads the catalogue via `read_json` (so an `ArtifactError` carries the path), raises `UsageError` on zero candidates and on any `oversized_rows` result, plans, then writes `00-slices.json` and one shard per slice through `write_json` — atomic, canonical, so `diff-runs` does not report formatting as variance. **Deletes any shard in `slices_dir` not named by the new plan**, which is what makes a re-plan safe.

- [ ] **Step 4: Wire the subcommand**

Add to `cli.SUBCOMMANDS`, add `--run` (required) in `_build_parser`, and add a dispatch block. It is a code stage over a run artifact, so it follows `validate`/`check-refs`' shape, **not** `survey`'s: `UsageError` and `ArtifactError` become exit 2 with `error: …` on stderr, and a successful plan prints one line per slice (`id  bytes  n  label`) on stdout and exits 0. It reports no findings, so it never exits 1 — say that in a comment, because the exit-code contract is where this repository has been bitten before.

- [ ] **Step 5: Add the stage**

- `paths.STAGES` — insert `"triage-slices"` **after** `"triage"` and before `"intake"`. (`triage` stays until Task 14; see the sequencing note.)
- `validate.STAGE_ARTIFACTS` — `"triage-slices": ("slices",)`.
- `skills.CODE_ONLY_STAGES` — add `"triage-slices"`, so `check-skills` does not demand an `rb-triage-slices` skill.
- `scripts/render-pipeline-diagram.py` — one `ROWS` entry. Re-render; **never hand-edit the page.**
- `scripts/render-readme-diagram.py` — add the stage to the first phase's `stages` list, which is the coverage claim the partition test checks. Re-render both SVGs.

- [ ] **Step 6: Update the three documents `test_docs_accuracy.py` polices**

`docs/reference/cli.md` (a `rubrica triage-slices` section), `docs/concepts/pipeline.md` (the stage and what it does), `docs/reference/artifacts.md` (the `slices` kind, named as its kind). The test failing until you do is the guard working — update the document, not the assertion.

- [ ] **Step 7: All three gates, then commit**

```bash
uv run python scripts/render-pipeline-diagram.py && uv run python scripts/render-readme-diagram.py
make test && make check && uv run rubrica check-skills
git add -A
git commit -S -s -m "feat: Add rubrica triage-slices, which partitions a catalogue into readable shards

Each shard carries the run's request and policy verbatim alongside its own
candidates, so a member's whole input is one Read under the harness's 256KB
refusal and the tail-metadata hunt disappears -- canonical_bytes sorts keys, so
run_id sat 608KB into the file and a chunk reader had to seek for it, which is
where a large share of one budget-exhausted dispatch went.

Re-running replans and removes shards the new plan does not name, because a
human adopting a projection at gate 0 adds a candidate and the plan must be
mintable again. Zero candidates and an unreadable catalogue are exit 2: a survey
defect or a broken run, detected by code without spending a dispatch. It reports
no findings, so it never exits 1.

paths.STAGES keeps triage alongside for now; it is removed once the three new
skills exist, because expected_skill_names derives from STAGES and neither order
is green in one step.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 8: `refs.check_slices`

Implements spec §9's first checker. Layer 2, so **exit 1 with one finding per line**, never 2.

**Files:**
- Modify: `src/rubrica/refs.py` (add the checker, wire it into `check_all` at :1716 beside `check_catalogue`)
- Test: `tests/unit/test_refs_slices.py` (new)

**Interfaces:**
- Consumes: `RunPaths.slices`, `.slices_dir`, `.slice_shard`; the catalogue.
- Produces: `def check_slices(run: RunPaths) -> list[Finding]`, called by `check_all` **after** `check_catalogue` (an unreadable catalogue is that checker's finding; this one must not double-report it).

**What it checks:**
1. Every catalogue candidate id appears in exactly one slice — reporting `no slice covers <id>` and `<id> is in slices s01 and s04` as distinct findings.
2. Every slice `candidate_ids` entry resolves to a real catalogue candidate — `no such candidate`.
3. Slice ids are unique.
4. Every slice has a shard on disk, and every shard on disk is named by the plan.
5. Each slice's recorded `bytes` equals the arithmetic over its shard's candidates — a number a reader recomputes, following the `weight`-is-arithmetic rule the triage record already carries.
6. Every shard's `candidates` match its slice's `candidate_ids`, in order.

- [ ] **Step 1: Write the failing tests** — one per numbered check above, each mutating a good run minimally so the finding it expects is the *only* one reported:

```python
def _sliced_run(tmp_path):
    run = survey.survey(corpus_roots=[Path("tests/fixtures/toy")], runs_dir=tmp_path / "runs",
                        target_name="toy", target_interface="http", objective="breadth")
    slices.write_slices(run, cap=2048)
    return run


def test_a_clean_sliced_run_reports_nothing(tmp_path):
    assert refs.check_slices(_sliced_run(tmp_path)) == []


def test_a_candidate_no_slice_covers_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    dropped = plan["slices"][0]["candidate_ids"].pop()
    write_json(run.slices, plan)
    findings = refs.check_slices(run)
    assert any(dropped in f.message and "no slice" in f.message for f in findings)


def test_a_candidate_in_two_slices_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    dupe = plan["slices"][0]["candidate_ids"][0]
    plan["slices"][1]["candidate_ids"].append(dupe)
    write_json(run.slices, plan)
    assert any(dupe in f.message for f in refs.check_slices(run))


def test_a_slice_naming_an_unknown_candidate_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    plan["slices"][0]["candidate_ids"].append("ghost")
    write_json(run.slices, plan)
    assert any("ghost" in f.message and "no such candidate" in f.message
               for f in refs.check_slices(run))


def test_a_missing_shard_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    sid = read_json(run.slices)["slices"][0]["id"]
    run.slice_shard(sid).unlink()
    assert any(sid in f.message for f in refs.check_slices(run))


def test_an_orphan_shard_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    (run.slices_dir / "s99.json").write_text("{}", encoding="utf-8")
    assert any("s99" in f.message for f in refs.check_slices(run))


def test_a_slice_whose_recorded_bytes_are_wrong_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    plan["slices"][0]["bytes"] += 1
    write_json(run.slices, plan)
    assert any("bytes" in f.message for f in refs.check_slices(run))


def test_an_absent_plan_reports_nothing_rather_than_crashing(tmp_path):
    """check_all runs every checker the run has inputs for, so a run before
    triage-slices must produce no findings here at all."""
    run = survey.survey(corpus_roots=[Path("tests/fixtures/toy")], runs_dir=tmp_path / "runs",
                        target_name="toy", target_interface="http", objective="breadth")
    assert refs.check_slices(run) == []


def test_an_unreadable_plan_is_one_finding_not_a_traceback(tmp_path):
    run = _sliced_run(tmp_path)
    run.slices.write_text("{not json", encoding="utf-8")
    findings = refs.check_slices(run)
    assert len(findings) == 1
    assert str(run.slices) in str(findings[0].path)
```

- [ ] **Step 2: Run to verify they fail.** `uv run pytest tests/unit/test_refs_slices.py -v` → `AttributeError: check_slices`.

- [ ] **Step 3: Implement.** Follow the nearest existing checker's shape (`check_catalogue`) for how it reads, guards absence, and constructs `Finding`. Treat an unreadable document as an absent one *except* that a present-but-unparseable plan is exactly one finding naming it — the `1` must name the **right** artifact, which is the rule `check-refs` over an unreadable `01-claims/` once violated by reporting four fabricated findings against a correct world model.

- [ ] **Step 4: Wire into `check_all`** immediately after `check_catalogue(run)`.

- [ ] **Step 5: Verify the exit-code contract end to end**

```bash
uv run rubrica check-refs --run /tmp/t8-clean; echo "clean: $?"     # expect 0
uv run rubrica check-refs --run /tmp/t8-broken; echo "broken: $?"   # expect 1, stdout non-empty
```
Build the two runs with `write_slices` and one mutation. **A `1` with empty stdout is the failure class `cli.py`'s catch-all and `findings.py` exist to prevent** — check stdout, not just the code.

- [ ] **Step 6: All three gates, then commit** (`feat: Check that the slice plan partitions the catalogue`).

---

### Task 9: `rubrica triage-seal` and the adoptions move

Implements spec §8 and §8.1. Two changes in one task because they are one hazard: the seal makes `00-triage.json` derived, and `adopt_projection` mutates it in place.

**Files:**
- Create: `src/rubrica/seal.py`
- Modify: `src/rubrica/cli.py`, `src/rubrica/triage.py` (`adopt_projection` at :167), `src/rubrica/paths.py` (`STAGES`), `src/rubrica/validate.py` (`STAGE_ARTIFACTS`), `src/rubrica/skills.py` (`CODE_ONLY_STAGES`), both render scripts, the three docs
- Test: `tests/unit/test_seal.py` (new), `tests/unit/test_triage_adopt.py` (existing — find with `grep -rl adopt_projection tests/`)

**Interfaces:**
- Consumes: every part path from Task 6; `slices` (Task 7).
- Produces: `def seal(run: RunPaths) -> tuple[Path | None, list[Finding]]` — the same signature `reconcile.seal` uses on the `staged-reconcile` branch, so the two code seals are read the same way. CLI: `("triage-seal", "assemble the triage record from the staged parts")`.

**The refusal class (spec §8) — it writes nothing at all when it reports anything:**
1. a part absent, unparseable, or not an object carrying its declared payload keys;
2. a candidate with no disposition, or with more than one (invariant 1, now across parts);
3. a disposition naming a candidate outside its own part's slice;
4. **no `admit` anywhere across all parts** (spec §10.2 — the condition that inverts: a member may legitimately decline its whole slice, so this belongs here and not to any member);
5. a `digest_insufficient` decline with no deficiency, or a `needs_projection` decline with no projection, the two now living in different artifacts.

Use a `_UNREADABLE = object()` sentinel rather than `None` for read failures, and say why in a comment: `null` is a legitimate JSON document and `read_json` returns `None` for it, which made `document is not None` mean two things at once — measured on the reconcile seal, where a `null` part skipped the payload-key check and raised a `KeyError` that the CLI catch-all then reported against the run root.

**`priority` composition (spec §8):** a member ranks within its slice; `00-objective.json` ranks the surfaces; the seal composes them into the global order. Sort dispositions by `(surface_rank, member_priority, candidate_id)` and rewrite `priority` as the 1-based position. `candidate_id` is the final tiebreak so the output is deterministic.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_seal_assembles_a_record_that_validates(tmp_path):
    run = _staged_run(tmp_path)          # helper: writes objective, parts, audit
    path, findings = seal.seal(run)
    assert findings == []
    assert path == run.triage
    assert validate.validate_stage(run, "triage") == []


def test_the_seal_writes_nothing_when_it_reports_anything(tmp_path):
    run = _staged_run(tmp_path)
    run.audit.unlink()
    path, findings = seal.seal(run)
    assert path is None
    assert findings
    assert not run.triage.exists(), "a half-assembled record clears layer 1 and reads as complete"


def test_a_candidate_ruled_twice_across_parts_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    parts = sorted(run.dispositions_dir.iterdir())
    first = read_json(parts[0]); second = read_json(parts[1])
    second["dispositions"].append(first["dispositions"][0])
    write_json(parts[1], second)
    _, findings = seal.seal(run)
    assert any("more than one disposition" in f.message for f in findings)


def test_a_candidate_ruled_by_nobody_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    part = sorted(run.dispositions_dir.iterdir())[0]
    doc = read_json(part); dropped = doc["dispositions"].pop()["candidate_id"]
    write_json(part, doc)
    _, findings = seal.seal(run)
    assert any(dropped in f.message for f in findings)


def test_a_part_ruling_outside_its_slice_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    parts = sorted(run.dispositions_dir.iterdir())
    doc = read_json(parts[0])
    doc["dispositions"][0]["candidate_id"] = read_json(parts[1])["dispositions"][0]["candidate_id"]
    write_json(parts[0], doc)
    _, findings = seal.seal(run)
    assert any("not in slice" in f.message for f in findings)


def test_zero_admits_across_every_part_is_refused_by_the_seal(tmp_path):
    """Spec 10.2's inversion: a member declining its whole slice is legitimate
    and must write its part; only the union can say the scoping failed."""
    run = _staged_run(tmp_path)
    for part in run.dispositions_dir.iterdir():
        doc = read_json(part)
        for d in doc["dispositions"]:
            d["disposition"] = "decline"
            d["reason_code"] = "off_objective"
            d.pop("priority", None)
        write_json(part, doc)
    _, findings = seal.seal(run)
    assert any("no admit" in f.message.lower() for f in findings)
    assert not run.triage.exists()


def test_a_single_part_declining_everything_is_not_refused(tmp_path):
    """The other half of the same rule, and the one a naive port gets wrong."""
    run = _staged_run(tmp_path)
    part = sorted(run.dispositions_dir.iterdir())[0]
    doc = read_json(part)
    for d in doc["dispositions"]:
        d["disposition"] = "decline"
        d["reason_code"] = "off_objective"
        d.pop("priority", None)
    write_json(part, doc)
    _, findings = seal.seal(run)
    assert findings == []


def test_a_null_part_is_one_finding_not_a_key_error(tmp_path):
    run = _staged_run(tmp_path)
    run.audit.write_text("null\n", encoding="utf-8")
    _, findings = seal.seal(run)
    assert findings and all(f.message for f in findings)


def test_priority_is_composed_across_slices_without_collision(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run)
    admits = [d for d in read_json(run.triage)["dispositions"] if d["disposition"] == "admit"]
    priorities = [d["priority"] for d in admits]
    assert priorities == sorted(priorities)
    assert len(priorities) == len(set(priorities)), "ranks minted per slice must not collide"


def test_sealing_twice_produces_identical_bytes(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run); first = run.triage.read_bytes()
    seal.seal(run)
    assert run.triage.read_bytes() == first


def test_an_adoption_survives_a_re_seal(tmp_path):
    """Spec 8.1's whole point: a re-seal must not erase a gate-0 admission."""
    run = _staged_run(tmp_path)
    seal.seal(run)
    source = tmp_path / "made.json"
    source.write_text(json.dumps({"tools": [{"name": "t", "result_shape": {}}]}), encoding="utf-8")
    findings = triage.adopt_projection(run, projection_id="prj-1", source=source)
    assert findings == []
    assert run.adoptions.is_file()
    seal.seal(run)
    record = read_json(run.triage)
    human = [d for d in record["dispositions"] if d["authority"] == "human"]
    assert len(human) == 1


def test_adopt_projection_does_not_write_the_sealed_record(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run)
    before = run.triage.read_bytes()
    source = tmp_path / "made.json"
    source.write_text(json.dumps({"tools": [{"name": "t", "result_shape": {}}]}), encoding="utf-8")
    triage.adopt_projection(run, projection_id="prj-1", source=source)
    assert run.triage.read_bytes() == before, "the seal owns 00-triage.json"
```

Write `_staged_run(tmp_path)` in the test module: survey the toy fixture, `write_slices`, then hand-write `00-objective.json`, one `00-dispositions/<id>.json` per slice, and `00-audit.json`. Task 16 moves it into `tests/toy.py`; keep it local here so this task is self-contained.

- [ ] **Step 2: Run to verify they fail.** `uv run pytest tests/unit/test_seal.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `seal.py`.** Header comment: code rather than a prompt for the reason `emit` is code — two runs with identical parts must produce a byte-identical record, or variance stops being attributable to the pass that caused it — plus the second reason, that a code step streams nothing and so cannot be killed by the gateway's idle reset. State that it assembles and does not check, and that layer 2 owns cross-artifact checking. State which refusals overlap `refs` deliberately and why refusing *before the write* is not redundant with reporting after it.

- [ ] **Step 4: Move adoptions out of the sealed record.** In `adopt_projection`: keep the catalogue append (the catalogue is the enumeration of the population, and an adopted artifact is part of it); replace the `00-triage.json` mutation with an append to `00-adoptions.json`. It still reads `00-triage.json` for the projection it was asked to adopt — that is a read, not a write. Update the docstring, which currently says `00-triage.json` gains the disposition, and preserve every existing `UsageError` distinction: an absent projection id is still 2, a malformed `projections` is still 1.

- [ ] **Step 5: Wire the subcommand and add the stage.** As Task 7 Step 5, with `"triage-seal": ("triage",)` in `STAGE_ARTIFACTS` — it writes the `triage` kind, which is exactly why `triage-0.1.json` needed no revision. Insert `"triage-seal"` after `"triage-slices"`. Re-render both diagrams. Update the three docs, including `cli.md`'s existing `adopt-projection` section, which now describes a different write.

- [ ] **Step 6: All three gates, then commit** (`feat: Add rubrica triage-seal, and move adoptions out of the record it owns`).

---

### Task 10: The three remaining layer-2 checkers

Implements spec §9. **`check_disposition_parts` carries the `check_verdicts` caveat** — it reports every slice without a part from the moment `00-dispositions/` exists, so mid-fan-out most are missing by construction. Document that in the function's docstring exactly as `check_verdicts` documents its own, and say there is no stage-scoped `check-refs`.

**Files:** Modify `src/rubrica/refs.py`; Test: `tests/unit/test_refs_triage_parts.py` (new)

**Interfaces:**
- `def check_disposition_parts(run: RunPaths) -> list[Finding]` — every slice has a part; every disposition names a candidate in that slice; no candidate ruled twice across parts; the union of parts and adoptions covers the catalogue.
- `def check_objective(run: RunPaths) -> list[Finding]` — every surface's `evidence` resolves to a real candidate id; each surface's `weight` is arithmetic over the catalogue that a reader recomputes.
- `def check_audit(run: RunPaths) -> list[Finding]` — every `digest_insufficient` decline in any part is referenced by a deficiency; every `needs_projection` decline by a projection; every `closes` names a real deficiency.
- All three wired into `check_all` after `check_slices`, in this order.

- [ ] **Step 1: Write the failing tests.** One per clause, each on a minimally mutated good run. Include these three specifically:

```python
def test_disposition_parts_reports_every_missing_part_mid_fan_out(tmp_path):
    """The check_verdicts caveat, pinned rather than merely documented."""
    run = _staged_run(tmp_path)
    parts = sorted(run.dispositions_dir.iterdir())
    for p in parts[1:]:
        p.unlink()
    findings = refs.check_disposition_parts(run)
    assert len(findings) == len(parts) - 1


def test_a_surface_weight_that_is_not_arithmetic_is_reported(tmp_path):
    run = _staged_run(tmp_path)
    doc = read_json(run.objective)
    doc["objective_review"]["surfaces"][0]["weight"]["candidates"] += 3
    write_json(run.objective, doc)
    assert any("weight" in f.message for f in refs.check_objective(run))


def test_a_digest_insufficient_decline_with_no_deficiency_is_reported(tmp_path):
    run = _staged_run(tmp_path)
    part = sorted(run.dispositions_dir.iterdir())[0]
    doc = read_json(part)
    doc["dispositions"][0] |= {"disposition": "decline",
                               "reason_code": "digest_insufficient",
                               "reason": "no result shape in the digest"}
    doc["dispositions"][0].pop("priority", None)
    write_json(part, doc)
    assert any("digest_insufficient" in f.message for f in refs.check_audit(run))
```

- [ ] **Step 2–4:** Run to verify failure; implement following `check_verdicts`' shape; wire into `check_all`.

- [ ] **Step 5: Verify both exit codes with non-empty stdout**, as Task 8 Step 5.

- [ ] **Step 6: All three gates, then commit** (`feat: Check the staged-triage parts, the objective's arithmetic, and the audit's obligations`).

---

### Tasks 11–13: the three skills

**Read `src/rubrica/skills/rb-triage/SKILL.md` in full before starting Task 11.** It is the source material, not something to paraphrase (spec §10). Three rules govern all three tasks:

- **Every skill carries a `## Contract` block (TOML, exactly one fence)** with `stage`, `reads`, `writes`, `schemas`, `invokes`, and the five mandatory sections **in order**: `1. Inputs  2. Output  3. Method  4. Invariants  5. Refusal conditions`. `check-skills` holds each contract to `paths.RunPaths` attribute names, `validate.STAGE_ARTIFACTS` and `cli.SUBCOMMANDS`, and enforces `skill.name == f"rb-{stage}"`.
- **Test assertions must be scoped with `skills.section_body(skill, "<heading>")`.** `skills.load()` sets `body` to the **entire file text** and the five headings are mandatory, so `"refusal" in body.lower()` is vacuous for every conforming skill. Assert co-occurrence *within* the owning section.
- **Measure every predicate in both directions before committing it.** Copy the skill to `/tmp`, point `RUBRICA_SKILLS_DIR` at it, blank the prose the assertion claims to check and confirm the test goes red; then reword that prose meaning-preservingly and confirm it stays green. A predicate nobody has watched fail is not yet a guard, and a phrase pin that breaks on an innocuous reformat is the mirror failure.

Each task's Step 5 is: add the stage to `paths.STAGES` (after the previous one, before `intake`), add its `STAGE_ARTIFACTS` entry, add a `ROWS` entry and the README `stages` entry, re-render both diagrams, update `docs/concepts/pipeline.md` and `docs/reference/artifacts.md`. Each task's Step 6 is all three gates, then commit.

---

### Task 11: `rb-triage-objective`

Implements spec §4.1. **Files:** Create `src/rubrica/skills/rb-triage-objective/SKILL.md`; Test: `tests/unit/test_skills_triage_family.py` (new).

**Contract:**
```toml
stage = "triage-objective"
reads = ["slices", "catalogue"]
writes = ["objective"]
schemas = ["objective"]
invokes = ["validate"]
```

`reads` is `slices` plus `catalogue` and **not** the shards: the pass needs the corpus map — the slice labels, groups, byte and candidate counts, and the catalogue's `request`, `policy` and `excluded` — but not a single candidate digest. Say so in §1 and say why: reading the digests is what makes a dispatch grow with the corpus, and this pass exists to rule the objective before that happens.

**Prose this pass must carry:**
- The current §1's `request` paragraph — target name and interface, `objective`, `objective_note`, `scope_note` — and its `excluded` instruction: a mechanical exclusion you believe was wrong is a `deficiencies[]` entry, not something to stay quiet about. Here the deficiency it implies is recorded by `rb-triage-audit`, so this pass states the concern in `objective_review.notes` and names it for the audit.
- The current Step 1 verbatim in force: read `request` first, before anything else, because a reading that starts from the candidates arrives at a scope and then rationalises the objective to fit it.
- The current §2 `objective_review` block: what a *surface* is, that `weight` is arithmetic a reader recomputes, and that `recommended_objective` is a recommendation the pass **may not act on**.
- **New, and the reason this pass exists separately:** `predicted_surface_count` is a prediction from the corpus map, and the members will observe surfaces from the digests. A divergence is a fact about the map's adequacy, not an error — say that, so a later reader does not treat it as a defect.
- From §5, unchanged in force: **refuse if `request.objective` is absent or contradicts `scope_note`** (and refuse *before* the fan-out is dispatched, which is the point of running first); and **do not refuse when the declared objective is unsupported** — write the record, set `supported: false`, let the gate rule.

**§1 must also carry the honest limitation** (spec §12 item 3): `supported` is ruled from a map of labels and counts, not from digests, so it can be wrong in ways a reading of the digests would not have been. A pass that does not know its own blind spot cannot flag it.

- [ ] **Step 1:** Write the failing tests. Scope every assertion with `section_body`:

```python
def test_the_objective_pass_forbids_reading_candidate_digests():
    skill = skills.load("rb-triage-objective")
    assert skill.contract["reads"] == ["slices", "catalogue"]
    inputs = skills.section_body(skill, "1. Inputs").lower()
    assert "digest" in inputs and ("not" in inputs or "never" in inputs)


def test_the_objective_pass_states_that_it_may_not_act_on_its_recommendation():
    body = skills.section_body(skills.load("rb-triage-objective"), "2. Output").lower()
    assert "recommended_objective" in body
    assert "may not act" in body or "not act on" in body


def test_the_objective_pass_refuses_on_an_absent_objective_and_not_on_an_unsupported_one():
    body = skills.section_body(skills.load("rb-triage-objective"), "5. Refusal conditions").lower()
    assert "absent" in body and "scope_note" in body
    assert "do not refuse" in body and "unsupported" in body


def test_the_objective_pass_admits_that_a_map_is_thinner_than_the_digests():
    body = skills.section_body(skills.load("rb-triage-objective"), "1. Inputs").lower()
    assert "supported" in body and ("thinner" in body or "wrong" in body)
```

- [ ] **Step 2:** Run to verify they fail. **Step 3:** Write the skill. **Step 4:** Run them, then measure each predicate in both directions per the rules above. **Step 5:** Add the stage. **Step 6:** Gates, commit.

---

### Task 12: `rb-triage-rule`

Implements spec §4's fan-out row and §10.2's inversion. **Files:** Create `src/rubrica/skills/rb-triage-rule/SKILL.md`; Modify `scripts/dispatch-stage.sh`; Test: `tests/unit/test_skills_triage_family.py`, `tests/unit/test_dispatch_harness.py`.

**Contract:**
```toml
stage = "triage-rule"
reads = ["slice_shard", "objective"]
writes = ["disposition_part"]
schemas = ["dispositions-part"]
invokes = ["validate"]
```

`reads` names the shard, **not** `catalogue` and **not** `slices`: a member reads its own slice and nothing else, and the shard already carries `request` and `policy`. Never a sibling's shard, never another member's part.

**Prose this pass must carry** — it is the pass that declines things, so most of the current skill lands here:

- **The header's measured failure, in full.** On 2026-08-13 a run selected sixteen inputs by hand and excluded the files declaring what each of the target's thirteen tools returns; six scenarios later died because no artifact carried those shapes, and the world model recorded the absence as four gaps indistinguishable from gaps nothing could close. The information that would have distinguished them — *this was declined, and here is why* — existed only in a conversation that no longer exists. This is why the output records a reason for **every** candidate rather than a list of the kept ones.
- **§1's two arguments for not opening a candidate file**, both: cost (the catalogue exists so judgment costs one bounded digest per candidate instead of the whole corpus), and comparability (the digests are the same width for every candidate, so "declined, no tool schema in the digest" means the same thing about candidate 3 and candidate 300; once some were read in full the record no longer says what it appears to say). Add spec §10.1's note that the width is now comparable *in fact* because the digest's total size is clamped, not merely by assumption.
- **`heuristics_fired` is the field that matters most**, and a heuristic missing from that list found nothing — a fact about the digest, not about the candidate. **`keys_truncated: true`** is likewise a fact about the digest, and ruling a wide object `no_evidence_value` because its visible keys look thin is the skeleton's version of the same mistake. **Add `skeleton_nodes_truncated`** from Task 1 to that paragraph, with the same reasoning: a clamped skeleton is a fact about the digest.
- **The repeated-signal warning:** measured on a real 130-element trace capture, `error_markers` fired on exactly one element and resolved through the same value already reported under `status`; the independent error-key path fired zero times. `status` and `error_markers` both firing is one fact stated twice, and counting it twice inflates a single failure into two.
- **§2's disposition rules:** one entry per candidate **in this slice**, exactly once, including inadmissible ones (a container is inadmissible because its elements are the real candidates — decline it and say that is why); `authority: "triage"` on every disposition this pass writes; an `admit` carries `reason` and a `priority`; the eight `reason_code` values with the table of when to use each.
- **`priority` is now rank within this slice**, and the seal composes it with the surface ranking into the run's global order. Say it, or a member will try to guess at a global rank it cannot see.
- **§3 Step 4's judgment rules:** prefer behavioural evidence over prose about behaviour; a conflict between a trace and a spec is worth admitting rather than resolving, because `rb-reconcile-contradict` records contradictions and is better placed to. For near-duplicates admit the one with the most distinct shape rather than the largest or newest — on the 2026-08-13 corpus seven traces of 130 were kept for distinct shape, and that last one was the run's only evidence of what the target does when something goes wrong. **A failing trace is almost never a near-duplicate of a successful one.**
- **New, and the reason §5.2 exists:** the shard's `provenance` says how much of a group this slice holds and which other slices hold the rest. A near-duplicate whose twin is in a sibling slice is one this member **cannot** see, so `near_duplicate` is a judgment about candidates *in this shard*, and where provenance says the group is split the member says so in `reason` rather than implying it compared against the whole group.
- **§5's inversion, stated as an instruction not a footnote:** if you would decline every candidate in your slice, **write the part anyway**. A slice may legitimately be all declines — a tests subtree, a docs subtree — and refusing would strand the run. Only the union across every slice can say the corpus, the objective or the scope is wrong, and `triage-seal` is what says it.
- **§5, unchanged in force:** do not refuse for a candidate you cannot judge — decline `digest_insufficient`, name the field you needed in `reason`. State that the matching deficiency is `rb-triage-audit`'s to write from your `deficiency_notes`, and that `check-refs` rejects the record if the pair never appears.

- [ ] **Step 1:** Write the failing tests, all `section_body`-scoped:

```python
def test_the_rule_pass_reads_only_its_own_shard():
    skill = skills.load("rb-triage-rule")
    assert skill.contract["reads"] == ["slice_shard", "objective"]
    inputs = skills.section_body(skill, "1. Inputs").lower()
    assert "sibling" in inputs or "another member" in inputs


def test_the_rule_pass_inverts_the_decline_everything_refusal():
    body = skills.section_body(skills.load("rb-triage-rule"), "5. Refusal conditions").lower()
    assert "write the part" in body
    assert "seal" in body            # names who owns the union judgment


def test_the_rule_pass_ties_provenance_to_the_near_duplicate_judgment():
    body = skills.section_body(skills.load("rb-triage-rule"), "3. Method").lower()
    assert "provenance" in body and "near_duplicate" in body


def test_the_rule_pass_keeps_the_failing_trace_rule():
    body = skills.section_body(skills.load("rb-triage-rule"), "3. Method").lower()
    assert "failing trace" in body and "near-duplicate" in body


def test_the_rule_pass_names_all_three_digest_truncation_facts():
    body = skills.section_body(skills.load("rb-triage-rule"), "1. Inputs")
    for field in ("heuristics_fired", "keys_truncated", "skeleton_nodes_truncated"):
        assert field in body


def test_the_rule_pass_says_priority_is_within_the_slice():
    body = skills.section_body(skills.load("rb-triage-rule"), "2. Output").lower()
    assert "priority" in body and ("within" in body or "in this slice" in body)


def test_dispatch_hands_a_rule_member_its_slice_id():
    script = Path("scripts/dispatch-stage.sh").read_text()
    assert "triage-rule)" in script
    assert "Your slice_id" in script
```

- [ ] **Step 2:** Run to verify failure. **Step 3:** Write the skill and add the `dispatch-stage.sh` case beside the existing `extract` and `instantiate|challenge` cases:

```bash
    triage-rule)           SLICE_LINE="Your slice_id:     $SLICE" ;;
```

- [ ] **Step 4:** Run the tests, then measure every predicate in both directions. **Step 5:** Add the stage. **Step 6:** Gates, commit.

---

### Task 13: `rb-triage-audit`

Implements spec §4.2. **Files:** Create `src/rubrica/skills/rb-triage-audit/SKILL.md`; Test: `tests/unit/test_skills_triage_family.py`.

**Contract:**
```toml
stage = "triage-audit"
reads = ["objective", "dispositions_dir"]
writes = ["audit"]
schemas = ["audit"]
invokes = ["validate", "check-refs"]
```

Reads the parts, **not** the candidates: the question it asks is about the admitted *set*, which no member could see.

**Prose this pass must carry:**
- **Why it is last, and why it is a prompt.** It is the self-audit: the refusal conditions across this family overwhelmingly resolve to "record it rather than stay quiet", so the pass that writes deficiencies is the right one to audit what its predecessors admitted. And "does anything in the admitted set declare what this capability returns" is semantic — code computing it would be the coverage-denominator mistake.
- **The current §2 `deficiencies[]` block**, including the question asked directly, every time: *for each capability the admitted set implies, does anything in the admitted set declare what it returns?* If not, that is a deficiency, and writing it costs one paragraph now instead of six dead scenarios later.
- **The current Step 5:** walk the capabilities the admitted set implies and ask what each one's result shape is declared in; walk the surfaces and ask which have no behavioural evidence. Each empty answer is a `deficiencies[]` entry.
- **The current Step 6 and §2's `projections[]` block in full** — all seven required fields, `confidence: unknown` being an honest value, and `acceptance.prose` being where *correct* is defined, with the four structural fields necessary and never sufficient.
- **Both blocks are required and an empty one is still written**, and an empty `deficiencies` is itself a claim: it says the admitted set covers everything the objective needs, which is how a human at gate 0 will read it.
- **Its obligations from the members:** every `digest_insufficient` decline in any part owes a deficiency, every `needs_projection` decline owes a projection, and `check-refs` rejects the record if either is missing. The members wrote `deficiency_notes`; turning them into deficiencies is this pass's job and nobody else's.
- **The divergence to report:** compare `predicted_surface_count` against the surfaces the parts observed and state what the difference means, in `deficiencies` where it implies a loss and in prose where it does not.

- [ ] **Step 1:** Write the failing tests:

```python
def test_the_audit_pass_reads_the_parts_and_not_the_candidates():
    skill = skills.load("rb-triage-audit")
    assert skill.contract["reads"] == ["objective", "dispositions_dir"]


def test_the_audit_pass_asks_the_result_shape_question_directly():
    body = skills.section_body(skills.load("rb-triage-audit"), "3. Method").lower()
    assert "result shape" in body or "what it returns" in body
    assert "capabilit" in body


def test_the_audit_pass_writes_both_blocks_even_when_empty():
    body = skills.section_body(skills.load("rb-triage-audit"), "2. Output").lower()
    assert "empty" in body and "still" in body
    assert "is also a claim" in body or "is itself a claim" in body


def test_the_audit_pass_owns_the_members_obligations():
    body = skills.section_body(skills.load("rb-triage-audit"), "4. Invariants").lower()
    assert "digest_insufficient" in body and "needs_projection" in body
```

- [ ] **Steps 2–6:** as Task 11.

---

### Task 14: Remove the `triage` stage

The shrink half of the sequencing note. Everything the flip needs now exists and is tested.

**Files:** Modify `src/rubrica/paths.py` (`STAGES`), `src/rubrica/validate.py` (`STAGE_ARTIFACTS`), both render scripts, `CLAUDE.md`, `docs/concepts/pipeline.md`; Delete `src/rubrica/skills/rb-triage/`; Test: `tests/unit/test_skills_triage.py` (retarget), `tests/unit/test_docs_accuracy.py`.

- [ ] **Step 1:** Delete `src/rubrica/skills/rb-triage/` **outright** — directory and `SKILL.md`. This differs from `rb-reconcile/`, which survived its `SKILL.md` because it holds an `exercise.md` and this repository's rule is that evidence lives beside the skill. `rb-triage` carries no `exercise.md`; `limitations.md` records that, and records that the evidence it would hold is not in the repository. There is nothing to preserve, so a `SUPERSEDED.md` would assert a stage's history while holding none of it. **Verify before deleting:** `ls src/rubrica/skills/rb-triage/` must show `SKILL.md` and nothing else.

- [ ] **Step 2:** Remove `"triage"` from `paths.STAGES` and its `STAGE_ARTIFACTS` entry. `"triage-seal": ("triage",)` keeps the *kind*, which is why the sealed artifact needs no revision.

- [ ] **Step 3:** Fold the family in the README drawing. `stages` stays the **complete** coverage claim, so the partition test still reproduces `paths.STAGES` exactly; the renderer *derives* the drawn label, folding the `triage-` prefix into one starred line with a `CAPTIONS` footnote saying it is one logical step engineered as substeps. Listing five stage lines is the wrong altitude for a newcomer's drawing and does not fit — `phase()` draws one 14px line per entry from a fixed `BOX_H`. Add a test asserting the fold is total **in both directions**: every `triage-` stage is covered by the folded label, and no unfolded stage is hidden. Without it the fold becomes a way to drop a stage from the drawing silently.

- [ ] **Step 4:** Update `CLAUDE.md`'s stage table and the prose around it: which gate brackets what, and that `survey` and the `triage-*` family have no `0N` prefix of their own. `CLAUDE.md` is **not** ruff-excluded — run `make check`.

- [ ] **Step 5:** Retarget `tests/unit/test_skills_triage.py` at the new family (or delete it if Tasks 11–13 fully replace it), and confirm `check-skills` reports neither a missing nor an unexpected skill.

- [ ] **Step 6:** Re-render both diagrams, run all three gates, commit (`feat!: Remove the single triage stage in favour of the staged family`).

---

### Task 15: Gate 0's brief

Implements spec §11's `brief.py` bullet. `brief.GATES` does not change.

**Files:** Modify `src/rubrica/brief.py` (`_gate_0`); Test: `tests/unit/test_brief.py`

**Adds to gate 0's reading surface**, keeping the objective verdict and grouped declines it already reports:
- the slice table — id, label, candidates, bytes;
- **the predicted-vs-observed surface divergence** (spec §4.1): `predicted_surface_count` from `00-objective.json` against the distinct surfaces the parts observed;
- the provenance summary — every group split across more than one slice, with how many slices hold it, since that is where the near-duplicate residue lives and gate 0 is the only place a human can act on it.

- [ ] **Step 1:** Write the failing tests. Use `_quietly`'s tolerance as the model — a malformed or absent artifact is some other command's finding, so the brief states what it could not read rather than crashing:

```python
def test_gate_zero_reports_the_slice_table(tmp_path):
    run = _staged_and_sealed_run(tmp_path)
    text = brief.gate_brief(run, 0)
    for sid in [s["id"] for s in read_json(run.slices)["slices"]]:
        assert sid in text


def test_gate_zero_reports_the_surface_divergence(tmp_path):
    run = _staged_and_sealed_run(tmp_path)
    doc = read_json(run.objective)
    doc["predicted_surface_count"] = 99
    write_json(run.objective, doc)
    assert "99" in brief.gate_brief(run, 0)


def test_gate_zero_names_a_group_split_across_slices(tmp_path):
    run = _staged_and_sealed_run(tmp_path)
    text = brief.gate_brief(run, 0)
    split = [p for s in read_json(run.slices)["slices"] for p in s["provenance"]
             if p["other_slices"]]
    if split:
        assert split[0]["group"] in text


def test_gate_zero_still_works_before_the_family_has_run(tmp_path):
    run = survey.survey(corpus_roots=[Path("tests/fixtures/toy")], runs_dir=tmp_path / "runs",
                        target_name="toy", target_interface="http", objective="breadth")
    text = brief.gate_brief(run, 0)      # no crash, and says what is missing
    assert text
```

- [ ] **Steps 2–5:** Run to verify failure; implement; run; all three gates; commit.

---

### Task 16: `tests/toy.py` checkpoints and a multi-slice fixture

Implements spec §11's last two bullets. **Check the module before adding a helper** — nearly every request for a new checkpoint during the build turned out to be for one that already existed.

**Files:** Modify `tests/toy.py` (`_UPTO_STAGES` at :1020, `build_toy_catalogue_and_triage` at :1111); Test: `tests/unit/test_toy_split.py` (new), `tests/unit/test_toy_end_to_end.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("upto", ["triage-slices", "triage-objective", "triage-rule",
                                  "triage-audit", "triage-seal"])
def test_each_new_checkpoint_stops_where_it_says(tmp_path, upto):
    run = build_toy_run(tmp_path / "runs", upto=upto)
    assert validate.validate_stage(run, upto) == []


def test_the_multi_slice_fixture_actually_fans_out(tmp_path):
    """The golden catalogue is small enough to be one slice, which leaves the
    fan-out unexercised by the toy world -- so the builder overrides the cap
    and drives the real slicer rather than hand-writing a plan."""
    run = build_toy_run(tmp_path / "runs", upto="triage-seal", slice_cap=1024)
    assert len(read_json(run.slices)["slices"]) > 1
    assert len(list(run.dispositions_dir.iterdir())) == len(read_json(run.slices)["slices"])
    assert refs.check_all(run) == []


def test_the_sealed_toy_record_is_what_the_old_builder_produced(tmp_path):
    """The seal's output must be a record the rest of the pipeline already
    accepts, or every downstream fixture silently changes meaning."""
    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    record = read_json(run.triage)
    assert set(record) >= {"schema_version", "run_id", "objective_review",
                           "dispositions", "deficiencies", "projections"}
    assert validate.validate_stage(run, "triage-seal") == []
```

- [ ] **Step 2:** Run to verify failure. **Step 3:** Extend `_UPTO_STAGES` with the five new names in `paths.STAGES` order and have `build_toy_run` write each artifact at its checkpoint. Give it a `slice_cap` keyword that reaches `slices.write_slices`, and **drive the real slicer** rather than hand-writing a plan — a hand-written plan only ever satisfies a check that was not looking. Keep `build_toy_catalogue_and_triage` working for the fixtures that call it, and make it write the parts and seal so its `00-triage.json` is produced by the code that produces one in a real run.

- [ ] **Step 4:** Run the whole suite — this task touches every fixture consumer, so `uv run pytest -q` in full, not a `-k` subset. **Step 5:** All three gates, commit.

---

### Task 17: The record — limitations, glossary, and the corrected arithmetic

Implements spec §12 and §11's glossary bullet. Documentation only, and it is the task that keeps this design falsifiable.

**Files:** Modify `docs/design/limitations.md`, `docs/concepts/glossary.md`, `docs/design/rationale.md`; Test: `tests/unit/test_docs_accuracy.py`

- [ ] **Step 1: Write the six `limitations.md` entries**, each with its measurement rather than a gesture at one. Spec §12 has the full text of what each must say; the short form:
  1. **Two near-duplicate candidates in different slices are both admitted.** Say why this is materially gentler than the cross-subject contradiction — it is *over*-admission, visible downstream in `claim-utilisation`, not an invisible absence — and **do not claim kinship with `survey`'s digest**, which is the argument the reconcile entry warns against.
  2. **Signature clustering is conditional and trace-specific.** 44 signatures over 130 real elements (works); 500 identical (degenerates to byte-splitting); 500 unique (degenerates to arbitrary packing). On a corpus whose elements classify as `other` it does not apply at all — cite issue #4.
  3. **`supported` is ruled from a corpus map, not from digests.** The instrument is the predicted-vs-observed divergence at gate 0.
  4. **Slice coherence is a code judgment no test can rule on.** `check_slices` verifies the partition is total and disjoint; nothing verifies it is meaningful, and the only instrument is the labels a human reads at gate 0.
  5. **The digest clamp is a second truncation.** File it *under* the existing "The catalogue digest is the single point of failure for triage" entry rather than beside it.
  6. **One prototype, four corpora, ten synthetic shapes, and no dispatch.** Everything measured is arithmetic over catalogues. Whether a member over a 64KB shard produces a *better* record than one over 595KB is unmeasured, and it is the claim the whole design rests on.

- [ ] **Step 2: Correct the existing entry's arithmetic.** "The catalogue digest is the single point of failure for triage" says "roughly 400 bytes of digest each". Measured on the same corpus: mean candidate row 1,645 bytes, mean digest 1,186, digests 72% of the candidates array. Correct it, and state that the entry's closing prediction — "if real corpora routinely exceed it, triage needs a clustering pass, and that is a redesign rather than a parameter" — is what this work is.

- [ ] **Step 3: Add the glossary entries**, each naming the pass that writes it: **slice**, **shard**, **slice provenance**, **surface** (already in the triage schema, not yet in the glossary), **seal** (the reconcile work adds this too — whichever lands first writes it, and the second checks the entry covers both code steps).

- [ ] **Step 4: Check `rationale.md`.** Section 5 of a skill is described there as the most important prompt-level decision in the design; Task 12's inversion of the decline-everything refusal is a worked example of a condition moving to the layer that can act on it. Add it only if it earns its place — do not pad.

- [ ] **Step 5: All three gates**, then commit (`docs: Record what staging triage costs, and correct the digest entry's arithmetic`).

---

## Self-Review

**Spec coverage:** §1 → Tasks 1–3 (the measurements land in commit messages and Task 17). §2 → the whole plan; `00-triage.json`'s stability is pinned by Task 16's third test. §3 → Task 2's rejected alternatives, recorded in the module header and the commit. §4 → Tasks 7, 9, 11–13. §4.1 → Task 11 + Task 15's divergence. §4.2 → Task 13. §5, §5.1, §5.2 → Task 2. §5.3 → Task 2 Step 5. §6 → Tasks 1 and 3. §7 → Tasks 4, 5, 6. §8 → Task 9. §8.1 → Task 9 Steps 4 and its two adoption tests. §9 → Tasks 8 and 10. §10 → Tasks 11–13. §10.1 → Task 12's digest-truncation test. §10.2 → Task 9's zero-admit pair, Task 11's refusal test, Task 12's inversion test, Task 7's exit-2 test. §11 → Tasks 7, 9, 14, 15, 16, 17. §12 → Task 17. §13 → Task 17 entry 2. §14 → this plan's task order.

**Gap found and closed:** spec §7 lists an `adoptions` path and §8.1 requires the artifact, but the spec's own kind list names only four. This plan adds a fifth kind and schema, `adoptions`, in Task 5 — without it `adopt_projection` would write an unvalidated artifact, which is exactly the "a stage that produced none of its kinds passes trivially" hole layer 1 exists to close.

**Type consistency:** `plan_slices`/`write_slices`/`row_bytes`/`oversized_rows`/`Slice`/`DEFAULT_SLICE_BYTES` (Task 2, consumed in 3, 7, 8, 16) — one spelling throughout. `seal(run) -> tuple[Path | None, list[Finding]]` (Task 9, consumed in 15, 16). `check_slices`/`check_disposition_parts`/`check_objective`/`check_audit` (Tasks 8, 10). `slice_shard(slice_id)`/`disposition_part(slice_id)`/`slice_ids_with_parts()` (Task 6, consumed in 7, 8, 9, 10, 15, 16). Stage names are `triage-slices`, `triage-objective`, `triage-rule`, `triage-audit`, `triage-seal` everywhere; skill names are those with an `rb-` prefix, which is what `check-skills` enforces. Artifact kinds are `slices`, `objective`, `dispositions-part`, `audit`, `adoptions`, and `triage-seal` writes the pre-existing `triage` kind.

**Out of scope, deliberately:** issue #4 (chat-message trajectories neither exploding nor classifying as traces). Task 17 entry 2 cites it; nothing here fixes it, and spec §13 says why fixing it first would make things worse.
