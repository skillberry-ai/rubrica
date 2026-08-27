# Drivable Coverage Denominator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frozen coverage denominator count only cells that can actually
be driven through the target, so the number the experiment is scored against
stops counting capabilities `emit` drops.

**Architecture:** Split one overloaded concept into two functions —
`refs._cells` stays wide as the *reference resolver*, and a new
`refs.drivable_cells` becomes the *scoring* set, keyed on `binding.tool`. Four
consumers narrow to it together (seal arithmetic, its check, the coverage matrix,
the round-1 hole universe). Undrivable cells are still fully accounted for, as
mechanical `unreachable` holes written by `score-seal` in the existing hole
vocabulary — so no schema changes anywhere.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff (`line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`).

**Spec:** [`docs/superpowers/specs/2026-08-27-drivable-denominator-design.md`](../specs/2026-08-27-drivable-denominator-design.md)

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** If signing fails, STOP and report it. Never fall back to unsigned.
- Attribution trailer is exactly `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with`.
- Gates: `make test` green, `make check` clean, `uv run rubrica check-skills` exit 0.
- Exit-code contract: a stage defect is never `2`; a `1` never has empty stdout; a `1` names the *right* artifact.
- **No schema file changes in this plan.** If a task seems to need one, stop and report — it means the design was wrong.
- **`denominator.version` stays at 1.** It is a per-run amendment counter (`reconcile.seal:183`), not an arithmetic generation.
- `drivable_cells` and `_cells` are **set** comprehensions over distinct pairs. Never a sum of per-capability counts (`limitations.md:1330`).
- Comment density here is high and deliberate: comments explain *why*, usually citing a measurement. Match it.
- Do not write a test count into any document.

## Test helpers: what exists, and the five this plan adds

**These already exist. Use them; do not reinvent them.**

| Helper | Where |
|---|---|
| `minimal_world_model`, `minimal_coverage`, `minimal_claims`, `minimal_scenarios`, `minimal_capabilities_part`, `minimal_outcomes_part`, `minimal_goals_part` | `tests/builders.py` |
| `_write_parts(run, parts)` | `tests/unit/test_reconcile_seal.py` |
| `_world(caps, ocs, goals)`, `_run_with_world(tmp_path, world)` | `tests/unit/test_rounds.py` |
| `_run_with_world_for_refs(tmp_path)`, `_scenario(...)` | `tests/unit/test_refs_rounds.py` |
| `_run(tmp_path, *, claims=True, world=True, ...)` | `tests/unit/test_refs_planning.py` |
| `_section(text, header)`, `_full_run(tmp_path)` | `tests/unit/test_brief.py` |

**Match the import style of the file you are editing — it differs between them,
and both styles are already in the tree.** `tests/unit/test_refs_planning.py`,
`test_refs_rounds.py`, `test_rounds.py` and `test_brief.py` import bare names
(`from rubrica.refs import check_world_model, ...`), so write `drivable_cells(world)`
there. `tests/unit/test_reconcile_seal.py` imports the module
(`from rubrica import reconcile, refs, validate`), so write `refs.drivable_cells(world)`
there. `src/rubrica/rounds.py` and `src/rubrica/brief.py` both import bare names from
`rubrica.refs`, so the sources use the bare form. Add each new name to the existing
import list; ruff `I` will order it, and ruff `F` catches you if you get it wrong.

**None of the run builders this plan needs exist yet.** Add each to the test file
named beside it, on top of the helpers above, and reuse it across that file's
tasks rather than inlining a second copy.

`tests/unit/test_reconcile_seal.py` — Tasks 2:

```python
def _bound_capability() -> dict:
    return {
        "id": "cap-bound",
        "operation": "search",
        "params": [],
        "binding": {"tool": "search_restaurants", "fixed_args": {}},
        "claims": ["clm-001"],
        "confidence": "high",
    }


def _unbound_capability() -> dict:
    """The shape 19 of 24 capabilities had on run-20260827-070444: a real claim, no
    tool anyone could name from it. rb-reconcile-capabilities' refusal conditions
    require exactly this rather than a guessed tool name."""
    return {
        "id": "cap-unbound",
        "operation": "Integrate with Keycloak for identity or authentication",
        "params": [],
        "claims": ["clm-001"],
        "confidence": "medium",
    }


def _bound_outcomes() -> dict:
    return {"capability_id": "cap-bound", "outcome_classes": [
        {"id": "oc-ok", "kind": "success", "description": "d", "claims": ["clm-001"]},
        {"id": "oc-empty", "kind": "empty", "description": "d", "claims": ["clm-001"]},
    ]}


def _unbound_outcomes() -> dict:
    return {"capability_id": "cap-unbound", "outcome_classes": [
        {"id": "oc-ok", "kind": "underspecified", "description": "d", "claims": ["clm-001"]},
    ]}


def _sealed_run_with(tmp_path, *, capabilities: list[dict], outcomes: list[dict]) -> RunPaths:
    """The golden split, with the capabilities and outcomes partials overridden.

    build_toy_run + split_world_model rather than hand-written partials, which is
    what every other test in this file does: the other five partials stay exactly
    the golden ones, so anything this test measures is attributable to the two it
    replaced. _write_parts' keys are `capabilities`, `outcomes`, `entities`,
    `goals`, `gaps`, `subjects`, `contradictions` -- read it at the top of the file
    rather than guessing.
    """
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["capabilities"] = {**parts["capabilities"], "capabilities": capabilities}
    parts["outcomes"] = {**parts["outcomes"], "outcomes": outcomes}
    _write_parts(run, parts)
    return run
```

`build_toy_run(tmp_path, upto="extract")` writes the toy claims, so the claim ids
the two capability builders cite **must be ones the toy corpus declares** — read
`tests/fixtures/toy/` or `tests/toy.py` and use a real claim id in place of
`clm-001` above. Cite an id that does not exist and `check_world_model` reports an
unresolvable claim, and the Task 2 identity test then measures that instead of the
denominator.

`tests/unit/test_refs_rounds.py` — Task 3:

```python
def _coverage_run_with(tmp_path, *, capabilities: list[dict], matrix_cells: list[dict],
                       holes: list[dict]) -> RunPaths:
    """A run whose world model carries `capabilities` and whose coverage document
    carries exactly `matrix_cells` and `holes`."""
    run = _run_with_world_for_refs(tmp_path)
    world = minimal_world_model(capabilities=capabilities, goals=[])
    write_json(run.world_model, world)
    coverage = minimal_coverage(
        capability_matrix={
            "cells": matrix_cells,
            "covered": sum(1 for c in matrix_cells if c["covered"]),
            "total": len(matrix_cells),
            "pct": (sum(1 for c in matrix_cells if c["covered"]) / len(matrix_cells))
            if matrix_cells else 0.0,
        },
        goal_matrix={"rows": [], "covered": 0, "total": 0, "pct": 0.0},
        holes=holes,
        denominator_version=world["denominator"]["version"],
    )
    write_json(run.coverage_latest, coverage)
    return run
```

`tests/unit/test_rounds.py` — Tasks 4 and 5:

```python
def _world_run_with(tmp_path, *, capabilities: list[dict], goals: list[dict]) -> RunPaths:
    """_run_with_world, but with the capability and goal lists named outright rather
    than generated by _world's counts -- these tests turn on which capabilities are
    BOUND, which _world does not vary."""
    return _run_with_world(tmp_path, minimal_world_model(capabilities=capabilities, goals=goals))


def _score_run_with(tmp_path, *, capabilities: list[dict], score_holes: list[dict]) -> RunPaths:
    """A run ready for seal_score(round_n=1): a world model, no scenarios, and a
    score part carrying `score_holes` and a verdict."""
    run = _world_run_with(tmp_path, capabilities=capabilities, goals=[])
    write_json(run.score_part(1), {
        "schema_version": "0.1",
        "holes": score_holes,
        # `continue` rather than `converged`, so the verdict never becomes the thing
        # under test -- these tests are about which holes reach the document.
        "verdict": "continue",
    })
    return run
```

`tests/unit/test_brief.py` — Task 7:

```python
def _unbound_run(tmp_path) -> RunPaths:
    """_full_run, with one unbound capability added and a claim traceable to the
    input that asserted it -- the pyproject-toml case that is 10 of the 19 on
    run-20260827-070444."""
    run = _full_run(tmp_path)
    world = read_json(run.world_model)
    world["capabilities"].append({
        "id": "cap-keycloak",
        "operation": "Integrate with Keycloak for identity or authentication",
        "params": [],
        "claims": ["clm-kc"],
        "confidence": "medium",
        "outcome_classes": [{
            "id": "oc-under", "kind": "underspecified",
            "description": "No outcome_class claim addresses Keycloak integration behavior.",
            "claims": ["clm-kc"],
        }],
    })
    write_json(run.world_model, world)
    write_json(run.claims_dir / "pyproject-toml.json", minimal_claims(
        artifact_id="pyproject-toml",
        claims=[{
            "id": "clm-kc", "kind": "capability",
            "statement": "The system integrates with Keycloak via python-keycloak.",
            "evidence": [{"input_id": "pyproject-toml", "pointer": "/project/dependencies"}],
            "confidence": "medium",
        }],
    ))
    return run
```

Match `minimal_claims`' actual claim shape when writing that last one — read it in
`tests/builders.py:22` rather than trusting the fields above, and adjust if the
schema has moved.

## Background the executor needs

`binding` is optional in `world-model-0.1.json` and shaped `{tool, fixed_args}`,
both required when present. A capability with no binding cannot be driven:
`emit.bindings` (`emit.py:60`) omits it, and `emit.py:105` reports a finding at
stage 06 — the only report that exists today.

Measured on `run-20260827-070444`: 24 capabilities, 5 bound, 37 of 56 cells
undrivable, both gate layers exiting 0.

**Every capability in every fixture (`toy/`, `toy-gap/`, `toy-contradiction/`,
`tests/toy.py`) declares a binding.** So the narrowing is a no-op on all of them
and no existing test breaks — including `test_sizing.py`'s real-run pin, whose
run (`run-20260813-204203`) is 14 capabilities all bound. It also means **no
existing test reaches the unbound path**, so every task below constructs its own
unbound capability.

Use `(cap.get("binding") or {}).get("tool")` throughout. Both the absent key and
an explicit `null` must read as unbound; a bare `cap.get("binding", {})` returns
`None` for the null case and raises on `.get`.

---

### Task 1: `refs.drivable_cells`

The scoring set, added with no consumer yet so it lands independently reviewable.

**Files:**
- Modify: `src/rubrica/refs.py:244-250` (add beneath `_cells`)
- Test: `tests/unit/test_refs_planning.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `refs.drivable_cells(world: dict) -> set[tuple[str, str]]`. Public (no leading underscore) because `reconcile.py` and `rounds.py` both import it in later tasks. `refs.py` imports neither, and `rounds.py` already imports `from rubrica.refs import OPEN_STATUSES`, so there is no cycle.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_refs_planning.py`:

```python
def test_drivable_cells_keeps_only_cells_whose_capability_names_a_tool():
    """The scoring set, as distinct from refs._cells' resolver set.

    Measured on run-20260827-070444: 24 capabilities, 5 bound, 37 of 56 cells on
    capabilities emit.bindings drops. Both spellings are needed at once -- a hole
    ref on an undrivable cell still has to RESOLVE (refs._cells) while the
    denominator must not COUNT it (this function), which is why narrowing _cells
    in place would fabricate findings against correct artifacts.
    """
    world = {
        "capabilities": [
            {
                "id": "cap-bound",
                "binding": {"tool": "query_tickets", "fixed_args": {}},
                "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-empty"}],
            },
            # Key absent -- the shape 19 of 24 capabilities had on the measured run.
            {"id": "cap-absent", "outcome_classes": [{"id": "oc-ok"}]},
            # Explicit null. Not schema-legal (binding is an object), but a
            # hand-edit at gate 1 produces it and `.get("binding", {}).get` raises
            # AttributeError on it rather than reading as unbound.
            {"id": "cap-null", "binding": None, "outcome_classes": [{"id": "oc-ok"}]},
            # Present but no tool: also undrivable, because emit.call_spec reads
            # binding["tool"] and nothing else identifies the call.
            {"id": "cap-no-tool", "binding": {"fixed_args": {}}, "outcome_classes": [{"id": "oc-ok"}]},
        ]
    }
    assert drivable_cells(world) == {("cap-bound", "oc-ok"), ("cap-bound", "oc-empty")}
    # The resolver stays wide over the same input: five cells, not two.
    assert len(_cells(world)) == 5


def test_drivable_cells_counts_distinct_pairs_rather_than_summing():
    """limitations.md:1330 -- a sum of per-capability outcome-class counts agrees
    with the set only until an id repeats, at which point the sum is the wrong
    number. A repeated outcome-class id is schema-legal.
    """
    world = {
        "capabilities": [
            {
                "id": "cap-a",
                "binding": {"tool": "t", "fixed_args": {}},
                "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-ok"}],
            }
        ]
    }
    assert drivable_cells(world) == {("cap-a", "oc-ok")}
    assert len(drivable_cells(world)) == 1  # a sum would say 2


def test_drivable_cells_tolerates_a_world_model_missing_its_collections():
    """check_all has no ordering guarantee that layer 1 rejected a malformed
    document first, which is the argument refs._as_list already carries.
    """
    assert drivable_cells({}) == set()
    assert drivable_cells({"capabilities": []}) == set()
    assert drivable_cells(
        {"capabilities": [{"id": "c", "binding": {"tool": "t", "fixed_args": {}}}]}
    ) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_refs_planning.py -k drivable -v`
Expected: FAIL, `AttributeError: module 'rubrica.refs' has no attribute 'drivable_cells'`

- [ ] **Step 3: Write minimal implementation**

In `src/rubrica/refs.py`, directly beneath `_cells` (which ends at line 250), add:

```python
def drivable_cells(world: dict) -> set[tuple[str, str]]:
    """The cells a scenario could actually be driven through the target on.

    `_cells` above and this are deliberately two functions, and collapsing them
    is the mistake this split exists to prevent. `_cells` answers "does this
    reference resolve" -- it backs hole refs, scenario capability_refs and batch
    hole_refs -- so it must stay wide, or a scenario on an undrivable cell reads
    as naming a cell the world model does not declare. This one answers "is this
    cell in the denominator", which is a narrower question with a different right
    answer.

    Keyed on `binding.tool` because that is exactly the predicate emit.bindings
    applies (emit.py:60), so the denominator equals what the pipeline can ship.
    Measured on run-20260827-070444: 24 capabilities, 5 bound, 37 of 56 cells
    counted against a suite that could never contain them, with both gate layers
    exiting 0.

    The proxy is lossy and knowingly so: of the 37 excluded cells on that run, 29
    were correctly excluded (dependency declarations from pyproject.toml, and real
    surfaces on another interface) and 8 were real agent-level behaviour that
    `binding`'s tool shape cannot express at all -- see docs/design/limitations.md
    on why that is recorded rather than fixed here.

    `(cap.get("binding") or {})` rather than `cap.get("binding", {})`: an explicit
    `binding: null` is what a hand-edit at gate 1 produces, and the second
    spelling returns None and raises AttributeError on the chained `.get`.

    A set of distinct pairs, for _cells' reason: the seal writes len() of this and
    check_world_model recomputes it, so a sum of per-capability counts would
    diverge the moment an id repeated.
    """
    return {
        (cap["id"], oc["id"])
        for cap in world.get("capabilities", [])
        if (cap.get("binding") or {}).get("tool")
        for oc in cap.get("outcome_classes", [])
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_refs_planning.py -k drivable -v && make check`
Expected: PASS, and `make check` clean.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs_planning.py
git commit -S -s -m "$(cat <<'EOF'
feat: Add refs.drivable_cells, the scoring half of the cell set

refs._cells answers whether a reference resolves and backs hole refs, scenario
capability_refs and batch hole_refs, so it has to stay wide. Whether a cell
belongs in the denominator is a narrower question, and issue 17 is what happens
when one function answers both: measured on run-20260827-070444, 37 of 56 cells
sat on capabilities emit.bindings drops, with both gate layers exiting 0.

No consumer yet -- the four that narrow onto this land in later commits.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Narrow the seal's arithmetic and its check together

The issue's core. Both spellings move in one commit or every sealed world model
reports a finding against itself.

**Files:**
- Modify: `src/rubrica/reconcile.py:297-317` (the `denominator` block) and its import block at `:54-56`
- Modify: `src/rubrica/refs.py:1873` (inside `check_world_model`)
- Test: `tests/unit/test_reconcile_seal.py`

**Interfaces:**
- Consumes: `refs.drivable_cells` from Task 1.
- Produces: `01-world-model.json`'s `denominator.capability_cells` now counts drivable cells only. `denominator.version` is untouched.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_reconcile_seal.py`. Read the existing helpers at the top
of that file first and build the partials the way its neighbours do; the
capabilities part is what needs an unbound member added.

```python
def test_the_sealed_denominator_counts_only_drivable_cells(tmp_path):
    """Issue 17. The denominator is frozen at the seal by design, so a wrong one
    is not corrected later -- it is scored against for the rest of the run and
    recorded in every coverage document.

    Measured on run-20260827-070444: 24 capabilities, 5 bound, denominator 56
    against 19 drivable cells, and `rubrica check-refs` exited 0 on it.
    """
    run = _sealed_run_with(
        tmp_path,
        capabilities=[
            {
                "id": "cap-bound",
                "operation": "search",
                "params": {},
                "binding": {"tool": "search_restaurants", "fixed_args": {}},
                "claims": ["c-1"],
                "confidence": "high",
            },
            # The shape 19 of 24 capabilities had on the measured run: a real
            # claim, no tool anyone could name from it. rb-reconcile-capabilities'
            # refusal conditions require exactly this rather than a guessed tool.
            {
                "id": "cap-unbound",
                "operation": "integrate with Keycloak",
                "params": {},
                "claims": ["c-1"],
                "confidence": "medium",
            },
        ],
        outcomes=[
            {"capability_id": "cap-bound", "outcome_classes": [
                {"id": "oc-ok", "kind": "success", "description": "d", "claims": ["c-1"]},
                {"id": "oc-empty", "kind": "empty", "description": "d", "claims": ["c-1"]},
            ]},
            {"capability_id": "cap-unbound", "outcome_classes": [
                {"id": "oc-ok", "kind": "underspecified", "description": "d", "claims": ["c-1"]},
            ]},
        ],
    )

    path, findings = reconcile.seal(run)

    assert findings == []
    world = json.loads(path.read_text())
    # Two drivable cells, not the three the world model declares.
    assert world["denominator"]["capability_cells"] == 2
    # The unbound capability is still IN the world model. It is not a lie, and
    # some such capabilities are real surfaces worth recording -- it just stops
    # setting the target coverage is scored against.
    assert {c["id"] for c in world["capabilities"]} == {"cap-bound", "cap-unbound"}
    # version is a per-run amendment counter (reconcile.seal:183), not an
    # arithmetic generation, so narrowing the arithmetic must not move it.
    assert world["denominator"]["version"] == 1


def test_check_world_model_agrees_with_the_narrowed_seal(tmp_path):
    """The seal writes this field and check_world_model recomputes it, which makes
    it an identity. Both spellings had to change in one commit or every sealed
    world model reports a finding against itself -- the hazard issue 17's own
    suggested patch named and then reintroduced one layer down.
    """
    run = _sealed_run_with(
        tmp_path,
        capabilities=[_bound_capability(), _unbound_capability()],
        outcomes=[_bound_outcomes(), _unbound_outcomes()],
    )
    path, findings = reconcile.seal(run)
    assert findings == []
    assert check_world_model(run) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_reconcile_seal.py -k drivable_cells -v`
Expected: FAIL — `assert 3 == 2` on the first test.

- [ ] **Step 3: Write the implementation**

In `src/rubrica/reconcile.py`, add to the import block (ruff `I` will order it):

```python
from rubrica.refs import drivable_cells
```

Replace the `capability_cells` entry and rewrite its comment (the old comment
described the wide arithmetic and is now wrong; leaving it would teach the next
reader the superseded rule):

```python
            # *Distinct* (capability_id, outcome_class_id) pairs among the
            # capabilities that declare a tool binding -- the cells this suite can
            # actually be scored against, not every cell the model declares. A
            # capability with no binding cannot be driven through the target:
            # emit.bindings drops it outright, so a cell on one is a target no
            # emitted test could ever hit. Measured on run-20260827-070444, before
            # this narrowed: 37 of 56 cells (66%) sat on unbound capabilities and
            # both gate layers exited 0 on the result.
            #
            # refs.drivable_cells and not a local comprehension, because
            # refs.check_world_model recomputes this field through that same
            # function. The recomputation is what makes the field an identity:
            # whatever is written here has to be what the check derives, or
            # check-refs reports a finding against a world model this seal had just
            # produced. A set and not a sum for the reason limitations.md:1330
            # records -- the two agree only until a capability id or an
            # outcome-class id repeats, at which point a sum is simply wrong.
            "capability_cells": len(drivable_cells({"capabilities": capabilities})),
```

In `src/rubrica/refs.py:1873`, change the recomputation and note why:

```python
    # drivable_cells, not _cells: the denominator counts what the suite can be
    # scored against, while _cells stays wide because it resolves references. The
    # seal writes len() of this same function, which is what keeps the field an
    # identity rather than two spellings that can drift.
    actual_cells = len(drivable_cells(world))
    if denominator.get("capability_cells") != actual_cells:
        report(
            "/denominator/capability_cells",
            f"declared capability_cells={denominator.get('capability_cells')} but the world "
            f"model declares {actual_cells} drivable capability x outcome-class cells",
        )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_reconcile_seal.py tests/unit/test_refs_planning.py tests/unit/test_toy_fixture.py -v && make test`
Expected: all PASS. Every fixture capability is bound, so no fixture expectation moves.

- [ ] **Step 5: Verify against the real run that motivated the issue**

Run:

```bash
uv run python -c "
import json, sys; sys.path.insert(0, 'src')
from rubrica import refs
w = json.load(open('runs/run-20260827-070444/01-world-model.json'))
print('declared', w['denominator']['capability_cells'], 'wide', len(refs._cells(w)), 'drivable', len(refs.drivable_cells(w)))
"
```

Expected: `declared 56 wide 56 drivable 19`. The run is sealed at the old
arithmetic, so `check-refs` against it now reports one finding on
`/denominator/capability_cells` — that is correct and expected for a
pre-existing run, not a regression. Skip this step if `runs/` is absent.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/reconcile.py src/rubrica/refs.py tests/unit/test_reconcile_seal.py
git commit -S -s -m "$(cat <<'EOF'
fix: Count only drivable cells in the frozen denominator

denominator.capability_cells is the number the whole experiment is scored
against, and it counted every capability x outcome-class pair without consulting
binding. A capability with no binding cannot be driven through the target --
emit.bindings drops it -- so those cells were a target no emitted test could hit.
Measured on run-20260827-070444: 37 of 56 cells (66%), both gate layers clean.

The seal's arithmetic and check_world_model's recomputation move together,
because that pair is an identity: changing one alone makes every sealed world
model report a finding against itself. refs._cells is untouched and stays wide --
it resolves hole refs, scenario capability_refs and batch hole_refs, so narrowing
it would fabricate findings against correct artifacts.

denominator.version stays 1: it is a per-run amendment counter tied to
decisions.md, and nothing in the repository compares capability_cells across runs.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Teach `check_coverage`'s matrix completeness the same distinction

The guard that must exist **before** Task 5 narrows the matrix, or that narrowing
reports 37 fabricated findings against a correct document.

**Files:**
- Modify: `src/rubrica/refs.py:2744-2750` (inside `check_coverage`)
- Test: `tests/unit/test_refs_rounds.py`

**Interfaces:**
- Consumes: `refs.drivable_cells` from Task 1.
- Produces: `check_coverage` accepts a matrix enumerating exactly the drivable cells, while still resolving hole refs against every declared cell.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_refs_rounds.py`, following that file's existing coverage-document builders:

```python
def test_check_coverage_accepts_a_matrix_of_drivable_cells_with_holes_on_the_rest(tmp_path):
    """The fabricated-finding guard for issue 17's narrowing.

    check_coverage compared matrix rows against the WIDE cell set, so a matrix
    that correctly enumerates only drivable cells reported one 'matrix omits
    cell' finding per undrivable cell -- 37 of them on run-20260827-070444,
    against a document that was right. That is the class CLAUDE.md's rule about a
    `1` naming the right artifact exists over.

    The undrivable cell is still carried, as an `unreachable` hole, so nothing
    disappears from the report. Its ref has to RESOLVE, which is why _cells stays
    wide.
    """
    run = _coverage_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}]},
        ],
        matrix_cells=[
            # Drivable cells only -- what rounds.capability_matrix produces after
            # Task 5.
            {"capability_id": "cap-bound", "outcome_class_id": "oc-ok",
             "scenario_ids": [], "covered": False},
        ],
        holes=[
            {"ref": "cell:cap-bound/oc-ok", "reason": "not_yet_attempted",
             "justification": "no scenario proposed yet"},
            {"ref": "cell:cap-unbound/oc-ok", "reason": "unreachable",
             "justification": "capability declares no binding.tool"},
        ],
    )

    findings = check_coverage(run)

    assert [f.message for f in findings] == []


def test_check_coverage_still_reports_a_matrix_that_omits_a_drivable_cell(tmp_path):
    """The other direction, so the loosened comparison is not loosened into
    vacuity: dropping a DRIVABLE cell from the matrix is still a finding. Without
    this, a matrix holding only the cells some scenario happened to claim would
    report 100% of a denominator it shrank to fit -- the failure
    rounds.capability_matrix' docstring ranks first.
    """
    run = _coverage_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-empty"}]},
        ],
        matrix_cells=[
            {"capability_id": "cap-bound", "outcome_class_id": "oc-ok",
             "scenario_ids": [], "covered": False},
        ],
        holes=[{"ref": "cell:cap-bound/oc-ok", "reason": "not_yet_attempted",
                "justification": "no scenario yet"}],
    )

    findings = check_coverage(run)

    assert any("matrix omits cell cell:cap-bound/oc-empty" in f.message for f in findings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_refs_rounds.py -k check_coverage_accepts_a_matrix -v`
Expected: FAIL with `matrix omits cell cell:cap-unbound/oc-ok` in the findings.

- [ ] **Step 3: Write the implementation**

In `check_coverage`, the local `cells = _cells(world)` at `:2696` **stays** — hole
refs resolve against it at `:2841`. Add a second local and use it for the
completeness comparison only:

```python
    matrix = coverage.get("capability_matrix", {})
    matrix_cells = matrix.get("cells", [])
    seen = {(c["capability_id"], c["outcome_class_id"]) for c in matrix_cells}
    # drivable_cells here and `cells` (wide) for the hole refs below, which is the
    # whole point of the split. The matrix is the SCORED surface, so it enumerates
    # what a scenario could be driven on; a hole is an ACCOUNT of a cell, so its
    # ref only has to resolve. Compared against the wide set, a correctly narrowed
    # matrix reported one 'matrix omits cell' per undrivable cell -- 37 of them on
    # run-20260827-070444, every one of them fabricated.
    drivable = drivable_cells(world)
    for missing in sorted(drivable - seen):
        report("/capability_matrix/cells", f"matrix omits cell {cell_ref(*missing)}")
    for invented in sorted(seen - drivable):
        report("/capability_matrix/cells", f"matrix invents cell {cell_ref(*invented)}")
```

Note `seen - drivable` rather than `seen - cells`: a matrix row on an undrivable
cell is now *also* wrong, because that cell belongs in the holes instead. This
tightens the invented-cell direction rather than loosening it.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_refs_rounds.py tests/unit/test_refs_planning.py -v && make test`
Expected: all PASS.

- [ ] **Step 5: Measure the guard in both directions**

Revert just the `drivable - seen` line to `cells - seen`, re-run
`test_check_coverage_accepts_a_matrix_of_drivable_cells_with_holes_on_the_rest`,
and confirm it goes RED. Restore the line. CLAUDE.md requires every predicate be
watched fail before it counts as a guard.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs_rounds.py
git commit -S -s -m "$(cat <<'EOF'
fix: Compare the coverage matrix against drivable cells, not every cell

check_coverage held the matrix to the WIDE cell set, so a matrix that correctly
enumerates only the cells a scenario can be driven on reported one 'matrix omits
cell' finding per undrivable cell -- 37 of them on run-20260827-070444, every one
fabricated against a correct document. That is the class the exit-code contract's
third rule exists over, and it is the guard the next commit's narrowing needs.

Hole refs keep resolving against the wide set, because a hole is an account of a
cell rather than a scored row. The invented-cell direction tightens rather than
loosens: a matrix ROW on an undrivable cell is now a finding too, since that cell
belongs in the holes.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Account for undrivable cells as mechanical `unreachable` holes

Written by `score-seal`, in the existing vocabulary, so the coverage report still
accounts for every declared cell after Task 5 removes them from the matrix.

**Files:**
- Modify: `src/rubrica/rounds.py:1182-1216` (inside `seal_score`, the `every_row`/hole reconciliation and the `document` composition)
- Test: `tests/unit/test_rounds.py`

**Interfaces:**
- Consumes: `refs.drivable_cells` (Task 1). `rounds.py` already imports from `rubrica.refs`.
- Produces: `03-coverage/round-N.json` `holes` contains one `unreachable` entry per undrivable cell that the score part did not already justify.

- [ ] **Step 1: Write the failing test**

```python
def test_seal_score_accounts_for_undrivable_cells_as_unreachable_holes(tmp_path):
    """rb-score §411 already defines `unreachable` as "no scenario could exercise
    this row against this target at all". An unbound capability is exactly that,
    mechanically -- binding absence is a fact on disk, not a judgment -- so
    score-seal computes these rather than asking the prompt for them.

    Nothing disappears from the report: the matrix narrows to drivable rows and
    the holes carry the rest, so a human at gate 2 still sees every cell.
    """
    run = _score_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-empty"}]},
        ],
        score_holes=[
            {"ref": "cell:cap-bound/oc-ok", "reason": "not_yet_attempted",
             "justification": "no scenario yet"},
        ],
    )

    path, findings = rounds.seal_score(run, round_n=1)

    assert findings == []
    doc = json.loads(path.read_text())
    injected = {h["ref"]: h for h in doc["holes"] if h["reason"] == "unreachable"}
    assert set(injected) == {"cell:cap-unbound/oc-ok", "cell:cap-unbound/oc-empty"}
    assert "binding" in injected["cell:cap-unbound/oc-ok"]["justification"]
    # The prompt's own hole is copied through untouched, which is what seal_score's
    # docstring promises about everything score decides.
    assert {"ref": "cell:cap-bound/oc-ok", "reason": "not_yet_attempted",
            "justification": "no scenario yet"} in doc["holes"]


def test_seal_score_leaves_a_score_authored_hole_on_an_undrivable_cell_alone(tmp_path):
    """"What score decides is copied through untouched" (seal_score's docstring).
    If the prompt already justified an undrivable cell -- with any reason, and
    out_of_scope is a defensible one -- the injection must not overwrite or
    duplicate it. Deduped by ref, prompt wins.
    """
    run = _score_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}]},
        ],
        score_holes=[
            {"ref": "cell:cap-bound/oc-ok", "reason": "not_yet_attempted",
             "justification": "no scenario yet"},
            {"ref": "cell:cap-unbound/oc-ok", "reason": "out_of_scope",
             "justification": "deployment concern, deliberately outside this suite"},
        ],
    )

    path, findings = rounds.seal_score(run, round_n=1)

    assert findings == []
    doc = json.loads(path.read_text())
    matching = [h for h in doc["holes"] if h["ref"] == "cell:cap-unbound/oc-ok"]
    assert len(matching) == 1
    assert matching[0]["reason"] == "out_of_scope"


def test_seal_score_does_not_call_a_score_hole_on_an_undrivable_cell_undeclared(tmp_path):
    """seal_score's `holed - every_row` check said "the world model does not
    declare" that ref. Once the matrix narrows, an undrivable cell is absent from
    every_row while the world model DOES declare it -- so the message would have
    been false, and the finding would have blocked a correct document.
    """
    run = _score_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}]},
        ],
        score_holes=[
            {"ref": "cell:cap-bound/oc-ok", "reason": "not_yet_attempted",
             "justification": "no scenario yet"},
            {"ref": "cell:cap-unbound/oc-ok", "reason": "unreachable",
             "justification": "no tool binding"},
        ],
    )

    _, findings = rounds.seal_score(run, round_n=1)

    assert [f.message for f in findings] == []


def test_seal_score_still_reports_a_hole_naming_a_cell_no_capability_declares(tmp_path):
    """The direction that must survive: a ref matching neither a drivable row nor
    an undrivable cell is still undeclared, so the loosened check is not vacuous.
    """
    run = _score_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
        ],
        score_holes=[
            {"ref": "cell:cap-bound/oc-ok", "reason": "not_yet_attempted",
             "justification": "no scenario yet"},
            {"ref": "cell:cap-ghost/oc-ok", "reason": "unreachable",
             "justification": "invented"},
        ],
    )

    _, findings = rounds.seal_score(run, round_n=1)

    assert any("cell:cap-ghost/oc-ok" in f.message and "does not declare" in f.message
               for f in findings)
```

Add to `tests/unit/test_sizing.py`, because Task 4 is what creates the hazard:

```python
def test_implied_size_does_not_subtract_unreachable_holes(tmp_path):
    """The spec's one arithmetic trap. implied_size subtracts blocked_by_gap holes
    from the denominator, and score-seal now writes an `unreachable` hole for every
    undrivable cell -- but those cells are ALREADY outside capability_cells, so
    subtracting them too would under-report the implied size twice over.

    Pinned on numbers this test controls, the way
    test_the_formula_is_pinned_on_synthetic_numbers already is.
    """
    run = _run_with(
        tmp_path,
        world={"denominator": {"version": 1, "capability_cells": 10, "goals": 1},
               "goals": [{"id": "g-1", "expected_hop_depths": [1, 2]}]},
        coverage={"holes": [
            {"ref": "cell:cap-unbound/oc-ok", "reason": "unreachable",
             "justification": "no binding.tool"},
            {"ref": "cell:cap-bound/oc-gap", "reason": "blocked_by_gap",
             "justification": "world model lacks it", "gap_id": "gap-1"},
        ]},
    )

    size = sizing.implied_size(run)

    # One blocked cell subtracted, the unreachable one ignored: 10 + 2 - 1 = 11.
    assert size["blocked_cells"] == 1
    assert size["denominator"] == 11
```

Build the run with whatever scaffold `tests/unit/test_sizing.py` already uses for
its synthetic tests — read `test_the_formula_is_pinned_on_synthetic_numbers` and
follow it rather than adding a new builder.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_rounds.py -k undrivable or unreachable -v`
Expected: FAIL — no `unreachable` holes are injected.

- [ ] **Step 3: Write the implementation**

In `seal_score`, after `cap` and `goals` are computed and **before** the
`every_row` reconciliation, build the undrivable set and the injected holes:

```python
    # Every declared cell the narrowed matrix leaves out. rb-score §411 defines
    # `unreachable` as "no scenario could exercise this row against this target at
    # all", and a capability with no binding.tool is exactly that: emit.bindings
    # drops it, so no emitted test could ever hit the cell. Computed here rather
    # than asked of the prompt because binding absence is a fact on disk and not a
    # judgment -- and score-seal already owns the matrices for the same reason.
    #
    # The report therefore still accounts for every cell the world model declares:
    # the matrix carries the drivable ones and these holes carry the rest, which is
    # what keeps the narrowing an honest denominator rather than a silent cap.
    undrivable = sorted(_cells(world) - drivable_cells(world))
    undrivable_refs = {f"cell:{cap_id}/{oc_id}" for cap_id, oc_id in undrivable}
    injected = [
        {
            "ref": f"cell:{cap_id}/{oc_id}",
            "reason": "unreachable",
            "justification": (
                f"capability {cap_id!r} declares no binding.tool, so emit.bindings cannot turn "
                "it into a tool call and no scenario could exercise this row"
            ),
        }
        for cap_id, oc_id in undrivable
        # Deduped against what score wrote, and score wins: seal_score's contract
        # is that every hole's reason and justification is copied through
        # untouched, and out_of_scope is a defensible reading a prompt may prefer.
        if f"cell:{cap_id}/{oc_id}" not in holed
    ]
```

`refs._cells` is a private name being reached from `rounds.py`. Import it
explicitly beside the public one so the coupling is visible rather than
incidental, and extend the existing import line:

```python
from rubrica.refs import OPEN_STATUSES, _cells, drivable_cells
```

Then extend `every_row` so an undrivable cell counts as declared:

```python
    every_row = {f"cell:{c['capability_id']}/{c['outcome_class_id']}" for c in cap["cells"]}
    every_row |= {f"goal:{r['goal_id']}" for r in goals["rows"]}
    # The undrivable cells too, because this set backs the "which the world model
    # does not declare" finding below and the world model DOES declare them --
    # they are simply not scored rows. Without this the message would be false and
    # would block a correct document. `uncovered` deliberately does NOT grow the
    # same way: only a drivable row has to be justified by a hole, and these are
    # justified by the injection above.
    every_row |= undrivable_refs
```

Finally, in the `document` dict, replace `"holes": part["holes"],` with:

```python
        # score's own holes first and in their order, then the computed ones, so a
        # reader sees what the prompt decided before what code added.
        "holes": [*part["holes"], *injected],
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_rounds.py tests/unit/test_refs_rounds.py -v && make test`
Expected: all PASS. Fixtures are fully bound, so `injected` is empty there and behaviour is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/rounds.py tests/unit/test_rounds.py
git commit -S -s -m "$(cat <<'EOF'
feat: Account for undrivable cells as computed unreachable holes

Narrowing the coverage matrix to drivable rows would drop undrivable cells out of
the report entirely, which trades one silent cap for another. rb-score §411
already defines `unreachable` as "no scenario could exercise this row against this
target at all", and an unbound capability is exactly that -- so score-seal
computes one such hole per undrivable cell and the report still accounts for every
cell the world model declares.

Computed rather than asked of the prompt because binding absence is a fact on
disk, not a judgment. A hole score already wrote for the same ref wins, since
seal_score's contract is that what score decides is copied through untouched.

every_row grows to include undrivable cells so the "world model does not declare"
finding stays true; uncovered deliberately does not, because only a drivable row
needs justifying.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Narrow the coverage matrix and the round-1 hole universe

The risky change, landing only now that Tasks 3 and 4 guard it.

**Files:**
- Modify: `src/rubrica/rounds.py:799-844` (`capability_matrix`) and `:187-222` (`closable_holes`' round-1 branch)
- Test: `tests/unit/test_rounds.py`

**Interfaces:**
- Consumes: `refs.drivable_cells` (already imported in Task 4).
- Produces: `capability_matrix` emits rows for drivable cells only, so `total`/`pct` divide by the same number the denominator holds. `closable_holes` no longer offers undrivable cells to `propose` on round 1.

- [ ] **Step 1: Write the failing test**

```python
def test_capability_matrix_enumerates_only_drivable_cells(tmp_path):
    """pct has to divide by the same number the denominator holds, or one run
    carries two disagreeing denominators -- the flaw in issue 17's own suggested
    patch, which narrowed the seal and left the matrix at 56.
    """
    world = {
        "capabilities": [
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-empty"}]},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}]},
        ],
        "goals": [],
    }
    matrix = rounds.capability_matrix(world, [])

    assert matrix["total"] == 2
    assert {(c["capability_id"], c["outcome_class_id"]) for c in matrix["cells"]} == {
        ("cap-bound", "oc-ok"), ("cap-bound", "oc-empty")
    }


def test_capability_matrix_pct_divides_by_drivable_cells(tmp_path):
    """The arithmetic the whole issue is about: one covered drivable cell out of
    one is 100%, not 50% because an undrivable cell sits beside it.
    """
    world = {
        "capabilities": [
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}]},
        ],
        "goals": [],
    }
    scenarios = [{
        "id": "s-1", "status": "accepted",
        "capability_refs": [{"capability_id": "cap-bound", "outcome_class_id": "oc-ok"}],
    }]
    matrix = rounds.capability_matrix(world, scenarios)

    assert (matrix["covered"], matrix["total"], matrix["pct"]) == (1, 1, 1.0)


def test_closable_holes_does_not_offer_an_undrivable_cell_on_round_one(tmp_path):
    """Round 1 enumerates the worklist from the world model, so an undrivable cell
    became a hole rb-propose was told to close -- and instantiate could not
    honestly seed. rb-reconcile-capabilities §3 step 3 already says a scenario on
    an unbound capability "costs a shipped test".
    """
    run = _world_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}]},
        ],
        goals=[{"id": "g-1", "expected_hop_depths": [1]}],
    )

    assert rounds.closable_holes(run) == ["cell:cap-bound/oc-ok", "goal:g-1"]


def test_closable_holes_still_refuses_a_capability_with_no_outcome_classes(tmp_path):
    """The door stays wide. _declared_cells raises on a capability missing
    outcome_classes -- measured: such a capability contributed zero cells in
    silence, and a world model of only those made write_batches return None,
    manufacturing the loop's normal terminal state out of a malformed artifact.
    Filtering by binding must not skip that check for unbound capabilities.
    """
    run = _world_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}]},
            {"id": "cap-unbound"},  # no outcome_classes at all
        ],
        goals=[],
    )

    with pytest.raises(UsageError, match="outcome_classes"):
        rounds.closable_holes(run)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_rounds.py -k drivable or closable_holes -v`
Expected: FAIL — `assert 3 == 2` on the matrix, and the undrivable cell present in `closable_holes`.

- [ ] **Step 3: Write the implementation**

In `capability_matrix`, filter the outer loop and extend the docstring's two
load-bearing rules with a third:

```python
    * Enumerate the DRIVABLE cells, not every declared one. A capability with no
      binding.tool cannot be driven through the target -- emit.bindings drops it --
      so a row for it is a scored target no emitted test could hit, and pct would
      divide by a number the denominator does not hold. seal_score records those
      cells as `unreachable` holes instead, so the report still accounts for all of
      them. Measured on run-20260827-070444: 37 of 56 rows were undrivable.
```

```python
    live_statuses = _live_statuses()
    live = {s["id"] for s in scenarios if s.get("status") in live_statuses}
    drivable = drivable_cells(world)
    cells = []
    for cap in world.get("capabilities", []):
        for oc in cap.get("outcome_classes", []):
            if (cap["id"], oc["id"]) not in drivable:
                continue
```

The rest of the loop body is unchanged.

In `closable_holes`' round-1 branch, filter the enumeration — **not**
`_declared_cells` itself, which is the malformed-artifact door and must keep
walking every capability:

```python
        # _declared_cells is called unfiltered on purpose: it is the door that
        # refuses a capability with no outcome_classes, and an UNBOUND capability
        # missing them is exactly as malformed as a bound one. Filter the
        # enumeration afterwards, so narrowing the worklist cannot narrow the check.
        drivable = drivable_cells(world)
        refs: list[str] = [
            f"cell:{cap_id}/{oc_id}"
            for cap_id, oc_id in _declared_cells(run, world)
            # An undrivable cell is not closable by proposing: rb-instantiate could
            # not seed it and emit would drop the test, so offering it spends a
            # round to produce nothing. This is the same judgment the coverage
            # branch below already makes for `unreachable`.
            if (cap_id, oc_id) in drivable
        ]
```

`closable_holes`' round-1 branch already names its local list `refs`. That is
**not** a conflict: `rounds.py` imports bare names from `rubrica.refs` and never
binds the module, so leave the local name alone rather than churning it. Verify
with `make check` — ruff `F` catches it if this is ever wrong.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_rounds.py tests/unit/test_refs_rounds.py tests/unit/test_rounds_cli.py -v && make test`
Expected: all PASS.

- [ ] **Step 5: Verify the four numbers now agree**

Run:

```bash
uv run python -c "
import json, sys; sys.path.insert(0, 'src')
from rubrica import refs, rounds
w = json.load(open('runs/run-20260827-070444/01-world-model.json'))
print('drivable', len(refs.drivable_cells(w)), 'matrix total', rounds.capability_matrix(w, [])['total'])
"
```

Expected: `drivable 19 matrix total 19`. Skip if `runs/` is absent.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/rounds.py tests/unit/test_rounds.py
git commit -S -s -m "$(cat <<'EOF'
fix: Score and propose against drivable cells only

capability_matrix enumerated every declared cell, so pct divided by a number the
denominator no longer holds -- two disagreeing denominators in one run, which is
the flaw in the fix issue 17 suggested for itself. closable_holes had the matching
defect on round 1: it offered undrivable cells to rb-propose, which spends a round
to produce scenarios rb-instantiate cannot seed and emit would drop.

Both narrow to refs.drivable_cells, so the seal's number, the matrix total, the
round-1 worklist and sizing's implied size all agree. _declared_cells is called
unfiltered on purpose -- it is the door that refuses a capability with no
outcome_classes, and an unbound capability missing them is exactly as malformed as
a bound one, so the filter goes on the enumeration and not on the check.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Report unbound capabilities at the seal

Moves the earliest signal from stage 06 to gate 1.

**Files:**
- Modify: `src/rubrica/refs.py` (inside `check_world_model`, after the denominator block ending at `:1886`)
- Test: `tests/unit/test_refs_planning.py`

**Interfaces:**
- Consumes: `refs.drivable_cells` (Task 1).
- Produces: one `check-refs` finding per unbound capability, on pointer `/capabilities/<index>`.

- [ ] **Step 1: Write the failing test**

```python
def test_check_world_model_reports_a_capability_with_no_tool_binding(tmp_path):
    """The earliest signal today is emit.py:105, at stage 06 -- after propose,
    score, instantiate and challenge have all run against the narrowed
    denominator, and after gates 1, 2 and 3. Its remediation ("add binding.tool
    and binding.fixed_args in the world model") asks a human to hand-edit a
    frozen, sealed artifact.

    An unbound capability is a bounded-coverage decision, and the repository's "no
    silent caps" discipline says it is logged where it is made.
    """
    run = _world_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}], "claims": []},
            {"id": "cap-unbound", "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-empty"}],
             "claims": []},
        ],
    )

    findings = check_world_model(run)
    unbound = [f for f in findings if "binding" in f.message]

    assert len(unbound) == 1
    assert "cap-unbound" in unbound[0].message
    # The cell count, because that is the number a reader at gate 1 is deciding
    # about -- two cells excluded, not one capability.
    assert "2" in unbound[0].message


def test_check_world_model_says_nothing_about_a_fully_bound_world_model(tmp_path):
    """The negative direction. Every fixture in the tree is fully bound, so a
    finding here would fire on all of them."""
    run = _world_run_with(
        tmp_path,
        capabilities=[
            {"id": "cap-bound", "binding": {"tool": "t", "fixed_args": {}},
             "outcome_classes": [{"id": "oc-ok"}], "claims": []},
        ],
    )

    assert [f for f in check_world_model(run) if "binding" in f.message] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_planning.py -k tool_binding or fully_bound -v`
Expected: FAIL — `assert 0 == 1`.

- [ ] **Step 3: Write the implementation**

In `check_world_model`, after the `goals` denominator comparison and before
`return out`:

```python
    # An unbound capability is a bounded-coverage decision, so it is reported where
    # it is made rather than five stages later. Until this existed the earliest
    # signal was emit.py:105 at stage 06 -- after propose, score, instantiate and
    # challenge had all run against the frozen denominator, and after gates 1, 2
    # and 3 -- and its remediation asks a human to hand-edit a sealed artifact.
    #
    # A finding and not a refusal: the world model is not malformed, and the
    # capability is not a lie. Some unbound capabilities are real surfaces worth
    # recording; they simply cannot set the target coverage is scored against, and
    # a human at gate 1 is who decides what to do about that.
    for i, cap in enumerate(world.get("capabilities", [])):
        if (cap.get("binding") or {}).get("tool"):
            continue
        classes = len({oc["id"] for oc in cap.get("outcome_classes", []) if "id" in oc})
        report(
            f"/capabilities/{i}",
            f"capability {cap.get('id')!r} declares no binding.tool, so its {classes} "
            "outcome-class cells cannot be driven through the target and are excluded from "
            "denominator.capability_cells",
        )
    return out
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_refs_planning.py tests/unit/test_reconcile_seal.py -v && make test`
Expected: all PASS. Fixtures are fully bound, so nothing new fires on them.

- [ ] **Step 5: Confirm the finding lands on the real run**

Run: `uv run rubrica check-refs --run runs/run-20260827-070444; echo "exit=$?"`
Expected: exit 1, with 19 `declares no binding.tool` lines on stdout plus the
`/denominator/capability_cells` line (that run was sealed at the old arithmetic).
Confirm **stdout is non-empty** — a `1` with empty stdout is the contract breach
`findings.py` exists to prevent. Skip if `runs/` is absent.

- [ ] **Step 5b: Cover the unreadable-input paths for every check this plan touched**

CLAUDE.md requires this whenever `cli.py`, `validate.py`, `refs.py` or `paths.py`
is touched, and the rule exists because `check-refs` over an unreadable
`01-claims/` once reported four fabricated `no such claim` findings against a
correct world model.

```python
def test_the_unbound_report_survives_an_unreadable_claims_directory(tmp_path):
    """check_world_model reads 01-claims/ for known_claims and 01-world-model.json
    for capabilities. An unreadable claims directory must not turn the
    unbound-capability report into a fabricated claim finding, and must not raise."""
    run = _world_run_with(tmp_path, capabilities=[_unbound_capability_with_classes()], goals=[])
    run.claims_dir.chmod(0o000)
    try:
        findings = check_world_model(run)
    finally:
        run.claims_dir.chmod(0o755)  # restored in a finally, or the tmp_path teardown fails

    # The binding finding still lands, and nothing invents a claim defect.
    assert any("declares no binding.tool" in f.message for f in findings)
    assert not any("no such claim" in f.message for f in findings)


def test_check_refs_over_a_write_protected_run_still_exits_one_with_output(tmp_path):
    """The exit-code contract's second invariant: a `1` must never have empty
    stdout. An exception escaping the handler produces exactly that."""
    run = _world_run_with(tmp_path, capabilities=[_unbound_capability_with_classes()], goals=[])
    run.root.chmod(0o555)
    try:
        findings = check_all(run)
    finally:
        run.root.chmod(0o755)

    assert findings, "a readable-but-unwritable run must still report, not raise"
```

Add `_unbound_capability_with_classes()` beside the other builders in
`tests/unit/test_refs_planning.py`: a capability with no `binding`, two outcome
classes, and `claims: []`.

Run: `uv run pytest tests/unit/test_refs_planning.py -k unreadable or write_protected -v`
Expected: PASS. If either raises instead of reporting, that is a real defect in
this plan's change — stop and report it rather than adjusting the test.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs_planning.py
git commit -S -s -m "$(cat <<'EOF'
feat: Report an unbound capability at the seal instead of at stage 06

An unbound capability bounds what the suite can ever cover, and the only report
was emit.py:105 -- stage 06, after propose, score, instantiate and challenge had
all run against the frozen denominator and after all three of gates 1, 2 and 3.
Its remediation asks a human to hand-edit a sealed artifact, which is not a repair
anything downstream can make.

check_world_model now names each one and the cell count it carries, so the
decision is legible at gate 1 where it can still be acted on. A finding and not a
refusal: the world model is not malformed and the capability is not a lie -- some
are real surfaces worth recording.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: List the excluded capabilities in the gate-1 brief

The reading surface. Makes the *cause* legible without asserting it, since code
cannot classify it.

**Files:**
- Modify: `src/rubrica/brief.py` (add a header constant near `:91-93`, and a section in `_gate_1`)
- Test: `tests/unit/test_brief.py`

**Interfaces:**
- Consumes: `refs.drivable_cells` (Task 1).
- Produces: `brief.EXCLUDED_HEADER`, and a gate-1 section listing each unbound capability with its cell count, `operation`, and citing input ids.

- [ ] **Step 1: Write the failing test**

```python
def test_gate_one_lists_the_capabilities_excluded_from_the_denominator(tmp_path):
    """Code cannot classify WHY a binding is absent -- that is semantic, and layer
    2 never mechanises semantics. So the brief lists what it can read and lets a
    human group them: on run-20260827-070444, 10 of the 19 excluded capabilities
    cite pyproject-toml and nothing else, which is legible from this listing and
    is the actual cause of the magnitude.
    """
    run = _unbound_run(tmp_path)
    text = brief.gate_brief(run, 1)
    section = _section(text, brief.EXCLUDED_HEADER)

    assert "cap-keycloak" in section
    assert "1 cell" in section                      # its cell count
    assert "Integrate with Keycloak" in section     # its operation
    assert "pyproject-toml" in section              # the input its claim came from


def test_gate_one_says_so_when_every_capability_is_drivable(tmp_path):
    """Both numbers, always -- the argument the reconcile sweep's line already
    makes. A brief that printed the section only when non-empty would render "every
    capability is drivable" as silence, and that is a strong claim a reader should
    see stated."""
    run = _full_run(tmp_path)  # fixtures are fully bound
    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    assert "all 2 capabilities are drivable" in section


def test_gate_one_does_not_raise_on_an_unreadable_claims_directory(tmp_path):
    """gate_brief must never fail on a readable run -- this module's docstring, and
    the ruling _quietly already carries. A claims file that is present but
    malformed must degrade to a missing source, not raise."""
    run = _unbound_run(tmp_path)
    next(run.claims_dir.glob("*.json")).write_text("{not json")

    text = brief.gate_brief(run, 1)  # must not raise

    assert "cap-keycloak" in _section(text, brief.EXCLUDED_HEADER)
```

Use the file's existing `_section` helper if it has one; otherwise add one that
slices `text` from the header line to the next blank-line-delimited header, and
reuse it rather than asserting against the whole document — CLAUDE.md's rule
about scoping an assertion to the section that owns the rule.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_brief.py -k excluded or drivable -v`
Expected: FAIL, `AttributeError: module 'rubrica.brief' has no attribute 'EXCLUDED_HEADER'`

- [ ] **Step 3: Write the implementation**

Beside the gate-0 header constants at `brief.py:91-93`:

```python
# Gate 1's excluded-capability section header. A named constant for the reason the
# three above are: it is the anchor a reader and a test both scope to.
EXCLUDED_HEADER = "Capabilities excluded from the denominator (no tool binding)"
```

In `_gate_1`, after the reconcile-sweep section and before the per-input
utilisation block, add:

```python
    # What the denominator does NOT count, and why a human has to read it rather
    # than a checker. Absence of binding.tool has three causes on the one run this
    # was measured against -- a dependency declaration that is not target
    # behaviour at all, a real surface on another interface, and real agent-level
    # behaviour that binding's tool shape cannot express -- and telling them apart
    # is semantic, which layer 2 is forbidden to mechanise. So this lists the
    # operation and the citing inputs and lets the reader group them: 10 of the 19
    # on run-20260827-070444 cite pyproject-toml and nothing else, which is the
    # actual cause of the magnitude and is visible here without being asserted.
    world = _mapping(_quietly(run.world_model))
    capabilities = _dicts(world.get("capabilities"))
    unbound = [cap for cap in capabilities if not (cap.get("binding") or {}).get("tool")]
    lines.append("")
    lines.append(EXCLUDED_HEADER)
    if not capabilities:
        lines.append("  (no world model yet; nothing to report)")
    elif not unbound:
        # Stated rather than omitted, for the reconcile sweep's reason: rendering
        # "every capability is drivable" as silence hides a strong claim.
        lines.append(f"  all {len(capabilities)} capabilities are drivable")
    else:
        source = _claim_sources(run)
        excluded = len(_cells(world) - drivable_cells(world))
        lines.append(
            f"  {len(unbound)} of {len(capabilities)} capabilities, {excluded} of "
            f"{len(_cells(world))} cells"
        )
        for cap in unbound:
            classes = len({oc["id"] for oc in _dicts(cap.get("outcome_classes")) if "id" in oc})
            inputs = sorted({source[cid] for cid in _as_list(cap.get("claims"))
                             if isinstance(cid, str) and cid in source})
            plural = "cell" if classes == 1 else "cells"
            lines.append(f"  {cap.get('id')}  {classes} {plural}  [{', '.join(inputs) or '?'}]")
            lines.append(f"    {cap.get('operation', '(no operation)')}")
```

Add the helper beside `_dicts`:

```python
def _claim_sources(run: RunPaths) -> dict[str, str]:
    """claim id -> the input id that asserted it, for every readable claims file.

    Its own walk rather than utilisation.claim_utilisation, which aggregates to
    cited/total per artifact and never exposes the per-claim mapping this needs.
    `_quietly` per file rather than per directory, so one malformed member costs
    its own claims and not the whole listing -- the promise this module's docstring
    makes, that a report states what it could not read instead of crashing.
    """
    sources: dict[str, str] = {}
    for path in list_json(run.claims_dir):
        payload = _mapping(_quietly(path))
        artifact_id = payload.get("artifact_id")
        if not isinstance(artifact_id, str):
            artifact_id = path.stem
        for claim in _dicts(payload.get("claims")):
            claim_id = claim.get("id")
            if isinstance(claim_id, str):
                sources[claim_id] = artifact_id
    return sources
```

Import `refs` in `brief.py` if it is not already imported.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_brief.py -v && make test`
Expected: all PASS.

- [ ] **Step 5: Read the real brief**

Run: `uv run rubrica gate-brief --run runs/run-20260827-070444 --gate 1`
Expected: exit 0, and the new section lists 19 capabilities — `cap-keycloak`,
`cap-langchain-community`, `cap-ollama-backend` and `cap-openai-backend` each
citing only `pyproject-toml`. Confirm the sizing line now reads 19 capability
cells and an implied size of 38 rather than 87. Skip if `runs/` is absent.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/brief.py tests/unit/test_brief.py
git commit -S -s -m "$(cat <<'EOF'
feat: List the denominator's excluded capabilities at gate 1

The narrowed denominator is honest but silent about what it dropped, and the
repository's discipline is that a bounded-coverage decision is visible where it is
made. Gate 1 now lists each excluded capability with its cell count, its
operation, and the inputs whose claims it rests on.

The listing states the cause without asserting it, because code cannot classify
it: absence of binding.tool covers a pyproject dependency declaration that is not
target behaviour, a real surface on another interface, and real agent-level
behaviour binding's tool shape cannot express, and telling those apart is
semantic. On run-20260827-070444 ten of the nineteen cite pyproject-toml and
nothing else, which a reader can now see for themselves.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Record what the narrowing costs, and reconcile the docs

**Files:**
- Modify: `docs/design/limitations.md` (append a new `###` entry)
- Modify: `docs/reference/cli.md` (the `gate-brief` and `check-refs` entries)
- Test: `tests/unit/test_docs_accuracy.py` (run it; do not weaken it)

**Interfaces:**
- Consumes: nothing.
- Produces: documentation only.

- [ ] **Step 1: Run the docs gate to see what it demands**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -v`
Expected: PASS or a specific failure naming the document to update. If it fails,
**update the document, not the assertion** — that failure is the guard working.

- [ ] **Step 2: Append the limitations entry**

Add to `docs/design/limitations.md`. Do not edit anything under the dated
recorded-history tree, and do not cite it.

```markdown
### `binding` is tool-shaped, so real agent-level behaviour cannot be driven or counted

`capability.binding` is `{tool, fixed_args}`, and `emit.bindings` turns a
capability into a tool call or drops it. That makes `binding.tool` the predicate
the drivable denominator is keyed on, and for most undrivable capabilities it is
the right one: a `pyproject.toml` dependency declaration is not target behaviour,
and a JSON-RPC surface on an `http-sse` run is genuinely out of reach.

For one group it is the wrong answer, and the narrowing makes that group
invisible. Measured on `run-20260827-070444`, 8 of the 37 excluded cells sat on
capabilities that are real, observed, and drivable through the declared
interface — they simply are not single tool calls.
`cap-empty-search-guidance` is the clearest: its operation is "When
`search_restaurants` returns no results, offer to search other cuisines or nearby
cities", and its claim cites an observed trajectory capture. That is agent
behaviour after a tool returns, not a tool invocation, so there is no tool name to
put in a binding and no way for `emit` to drive it. `cap-text-io` and
`cap-multi-turn` are the same shape.

So the pipeline structurally cannot emit a test for non-tool agent behaviour, and
the drivable denominator now excludes such behaviour rather than reporting that it
cannot reach it. The exclusion is at least visible: `check_world_model` reports
each unbound capability at the seal and `gate-brief` lists it at gate 1 with its
operation, which is what lets a human see that this group is not the same as the
`pyproject.toml` group.

**Why it is parked.** The fix is a second binding kind — a conversational turn
rather than a tool call — and it reaches much further than the denominator: the
world-model schema, `emit`, and the emitted verifier contract, which is what
`suite/verify.py` executes. That is a change to what a shipped test *is*, and it
wants its own design rather than a field added under a denominator fix. The
narrowing is still the right move meanwhile, because the alternative is scoring
against cells nothing can drive; what the narrowing must not do is imply those 8
cells are junk, which is why they are written down here.

Worth keeping separate from the magnitude question. On the same run 10 of the 19
unbound capabilities rest on `pyproject-toml` alone, which is a
`rb-reconcile-capabilities` accounting question and has its own entry — this one
is about the 4 that would be real tests if `binding` could express them.
```

- [ ] **Step 3: Update `docs/reference/cli.md`**

Extend the `check-refs` entry to mention the unbound-capability finding, and the
`gate-brief` entry's gate-1 list to include the excluded-capability section.
Match the surrounding entries' voice and length; do not add a heading that counts
something that grows.

- [ ] **Step 4: Run every gate**

Run: `make test && make check && uv run rubrica check-skills; echo "check-skills exit=$?"`
Expected: tests green, check clean, `check-skills` exit 0.

- [ ] **Step 5: Commit**

```bash
git add docs/design/limitations.md docs/reference/cli.md
git commit -S -s -m "$(cat <<'EOF'
docs: Record what the drivable denominator cannot express

binding is {tool, fixed_args}-shaped, so the drivable denominator's key is right
for a pyproject dependency declaration and wrong for real agent behaviour that is
not a single tool call. Measured on run-20260827-070444, 8 of the 37 excluded
cells were the second kind: cap-empty-search-guidance cites an observed trajectory
capture and describes what the agent says after a tool returns empty.

The pipeline structurally cannot emit a test for that, and the narrowing would
otherwise absorb it silently. Parked rather than fixed because a second binding
kind reaches the schema, emit and the emitted verifier contract -- a change to
what a shipped test is, which wants its own design.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] `make test` green
- [ ] `make check` clean
- [ ] `uv run rubrica check-skills` exit 0
- [ ] `uv run rubrica gate-brief --run runs/run-20260827-070444 --gate 1` reads 19 capability cells, implied 38, and lists 19 excluded capabilities (skip if `runs/` absent)
- [ ] `git log --format="%h %G? %s"` shows `G` on every new commit
- [ ] `git log --format="%(trailers)"` shows `Assisted-By` and `Signed-off-by` on every new commit, and **no** `Co-Authored-By`
