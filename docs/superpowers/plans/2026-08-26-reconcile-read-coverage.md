# Forced reconcile read coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a reconcile pass that did not read every claims file produce a
*reportable* artifact, by requiring `claims` on the three world-model child
elements that lack it and an `inputs_seen` accounting on the four partials whose
passes own a claim kind.

**Architecture:** Two schema increments and one new layer-2 checker. Nothing in
the pipeline's control flow changes: the passes stay single dispatches, the seal
is untouched because it reads named arrays out of each part, and
`01-world-model.json` keeps its path, schema and byte shape. The forcing function
is arithmetic — `refs.check_input_dispositions` recomputes each declared count
from `01-claims/` and from the part itself, so a count for a file the pass never
opened is a finding.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `jsonschema` (Draft 2020-12) with a
`referencing` Registry, `ruff`.

**Spec:** `docs/superpowers/specs/2026-08-26-reconcile-read-coverage-design.md` —
read it first. It carries the measurements every ruling here rests on, and this
plan argues from it rather than restating it.

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags. If signing
  fails, **stop and report it** — never fall back to unsigned, never work around
  it.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`.
  **Never** `Co-Authored-By` or `Made-with`.
- Three gates, all of which must be green before any commit: `make test`,
  `make check` (ruff check + ruff format --check, no changes), and
  `uv run rubrica check-skills` exiting 0.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. `docs/` is
  excluded; `README.md` and `CLAUDE.md` are not.
- **Never write a test count into any prose.** `tests/unit/test_docs_accuracy.py`
  fails on one, and the number grows with every capability.
- **No file under `src/`, `docs/design/`, `docs/concepts/` or `docs/reference/`
  may contain the token `superpowers`.** Two tests enforce it
  (`test_no_shipped_markdown_cites_recorded_history`,
  `test_only_the_docs_index_cites_recorded_history`). Cite issue #6 and the code,
  never this plan or its spec.
- Comment density in this repo is high and deliberate: comments explain *why*,
  usually citing a measurement. Match it; do not strip existing ones.
- The exit-code contract is load-bearing: `0` clean, `1` findings one per line on
  stdout, `2` usage error or an unreadable run. **A stage defect must never
  surface as `2`, and a `1` must never have empty stdout.**
- Prefer the env overrides to editing repo files when probing:
  `RUBRICA_SCHEMA_DIR`, `RUBRICA_SKILLS_DIR`, `RUBRICA_SUITE_DIR`, `RUBRICA_LIVE`.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/rubrica/utilisation.py` | `_cited_claim_ids` learns the three nested citation sites | 1 |
| `src/rubrica/schema/world-model-0.1.json` | `claims` required on `$defs/invariant`, `$defs/outcome_class`, `$defs/gap` | 2 |
| `src/rubrica/refs.py` | resolve the new citation sites; new `check_input_dispositions`; wire into `check_all` | 2, 4 |
| `tests/toy.py` | golden fixture: citations move to the child elements; `inputs_seen` derived, never hand-authored | 2, 3 |
| `src/rubrica/schema/inputs-seen-0.1.json` | **new** — the shared `$defs/row`, the first schema file that is not an artifact kind | 3 |
| `src/rubrica/schema/{capabilities,entities,outcomes,goals}-part-0.1.json` | each requires `inputs_seen` | 3 |
| `src/rubrica/validate.py` | comment recording why `inputs-seen` is absent from `ARTIFACT_SCHEMAS` | 3 |
| `src/rubrica/skills/rb-reconcile-{capabilities,entities,outcomes,goals}/SKILL.md` | §2/§3/§4/§5 prose for `inputs_seen` | 5 |
| `src/rubrica/skills/rb-reconcile-gaps/SKILL.md` | §2/§4 prose for a gap's own `claims` | 5 |
| `src/rubrica/brief.py` | gate 1 gains the per-pass block | 6 |
| `docs/reference/artifacts.md`, `docs/reference/cli.md` | the new field and the new gate-1 surface | 6 |
| `docs/design/limitations.md` | issue #6's measurement folded in; two new entries | 7 |

---

### Task 1: `_cited_claim_ids` counts the three nested citation sites

`utilisation._cited_claim_ids` walks `capabilities`, `entities`, `actors`,
`goals` and the contradiction sides. It does not walk
`entities[].invariants[].claims`, `capabilities[].outcome_classes[].claims` or
`gaps[].claims` — because no such field exists yet. This task teaches the counter
those sites *before* the schema permits them, so the schema change in Task 2
lands against a counter that already agrees with it. Measured on
`runs/run-20260823-112746`: 38 claim ids appear somewhere in the world model that
this function does not see.

**Files:**
- Modify: `src/rubrica/utilisation.py` (`_cited_claim_ids`)
- Test: `tests/unit/test_utilisation.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `utilisation._cited_claim_ids(run) -> set[str] | None`, unchanged
  signature, now counting nested `claims` arrays. `refs.check_claim_utilisation`
  and `brief._gate_1` consume it through `claim_utilisation` and need no change.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_utilisation.py`. Check the existing imports and helpers
in that module first and reuse them; it already builds toy runs.

```python
def test_a_claim_cited_only_on_a_child_element_counts_as_cited(tmp_path):
    """An invariant's, outcome class's or gap's own claims are citations.

    Measured on run-20260823-112746 before this walk existed: 38 claim ids
    appeared somewhere in the world model and nowhere in this function's
    result, because the only structured place those three elements had to
    record provenance was their parent's `claims` array or their own
    `description` prose. A counter that misses them reports an input as
    uncited while the world model rests on it -- the self-contradicting gate-1
    brief issue #6 reports.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world = read_json(run.world_model)
    # One id per new site, moved *out* of every existing site so the only way
    # it can be counted is the new walk.
    world["capabilities"][0]["claims"] = ["clm-api-001"]
    world["capabilities"][0]["outcome_classes"][0]["claims"] = ["clm-api-005"]
    world["entities"][0]["claims"] = ["clm-api-003"]
    world["entities"][0]["invariants"][0]["claims"] = ["clm-notes-005"]
    world["gaps"] = [
        {
            "id": "gap-x",
            "subject": "x",
            "unknown": "x",
            "why_it_matters": "x",
            "blocks": ["propose"],
            "claims": ["clm-notes-006"],
        }
    ]
    write_json(run.world_model, world)

    cited = _cited_claim_ids(run)
    assert "clm-api-005" in cited, "an outcome class's own claims are not counted"
    assert "clm-notes-005" in cited, "an invariant's own claims are not counted"
    assert "clm-notes-006" in cited, "a gap's own claims are not counted"
```

Import `_cited_claim_ids` from `rubrica.utilisation`, and `read_json` /
`write_json` from `rubrica.artifacts`, following that module's existing imports.

- [ ] **Step 2: Run it and confirm it fails**

```bash
uv run pytest tests/unit/test_utilisation.py::test_a_claim_cited_only_on_a_child_element_counts_as_cited -v
```

Expected: FAIL on the first assertion, `an outcome class's own claims are not
counted`. If it passes, stop — the walk already exists and this task is
misdescribed.

- [ ] **Step 3: Implement the three walks**

In `src/rubrica/utilisation.py`, replace the existing group loop in
`_cited_claim_ids` with this, keeping the contradiction block below it exactly
as it is:

```python
    cited: set[str] = set()
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            cited.update(item.get("claims", []) or [])
    # The three nested sites. `$defs/invariant`, `$defs/outcome_class` and
    # `$defs/gap` carried no `claims` array at all until issue #6, so an
    # invariant's provenance had to go on its entity or into `description`
    # prose. Measured on run-20260823-112746 while that was still true:
    # `invariant` claims were cited 0 of 55 times and `outcome_class` 7 of 62,
    # with 24 more appearing only inside prose -- 117 of 434 claims, 27% of
    # the corpus, that this function could not see. Walking the children is
    # what makes those citations structural rather than prose.
    for capability in world.get("capabilities", []):
        for outcome_class in capability.get("outcome_classes", []) or []:
            cited.update(outcome_class.get("claims", []) or [])
    for entity in world.get("entities", []):
        for invariant in entity.get("invariants", []) or []:
            cited.update(invariant.get("claims", []) or [])
    for gap in world.get("gaps", []) or []:
        cited.update(gap.get("claims", []) or [])
```

`or []` on every nested container for the reason the existing line has it: these
keys are optional in the schema and a JSON `null` reaches here as `None`.

- [ ] **Step 4: Run the new test and the full suite**

```bash
uv run pytest tests/unit/test_utilisation.py -v
make test
```

Expected: the new test PASSES and nothing else moves. The golden fixture has no
child-element citations yet, so `claim_utilisation` over a toy run is unchanged —
that is the point of doing this before Task 2.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/utilisation.py tests/unit/test_utilisation.py
git commit -S -s -m "$(cat <<'MSG'
fix: Count a claim cited on an invariant, outcome class or gap

utilisation._cited_claim_ids walked the four top-level element groups and the
contradiction sides, and nothing else. Measured on run-20260823-112746: 38
claim ids appeared somewhere in the world model and nowhere in its result.

The three child elements had no `claims` array to walk -- that is the schema
half of issue #6 and lands next -- so this teaches the counter the sites first,
and a toy run's utilisation does not move because the golden fixture has no
child-element citation yet.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 2: `claims` required on the three child defs, and the fixture moves its citations down

**Files:**
- Modify: `src/rubrica/schema/world-model-0.1.json` (`$defs/invariant`, `$defs/outcome_class`, `$defs/gap`)
- Modify: `src/rubrica/refs.py` (`check_world_model`)
- Modify: `tests/toy.py` (`toy_world_model`)
- Test: `tests/unit/test_schemas_instance.py`, `tests/unit/test_refs_world_model.py`

**Interfaces:**
- Consumes: Task 1's `_cited_claim_ids` walks — without them this task would drop
  the toy's utilisation from 19/19 to 12/19 and `check_claim_utilisation` would
  fire.
- Produces: `$defs/invariant`, `$defs/outcome_class` and `$defs/gap` each require
  a non-empty `claims`. `refs.check_world_model` reports `no such claim` at
  `/capabilities/{i}/outcome_classes/{j}/claims/{k}`,
  `/entities/{i}/invariants/{j}/claims/{k}` and `/gaps/{i}/claims/{k}`.

**Why the schema and the fixture are one task:** the moment `claims` is required,
every toy-run-based test fails layer 1. Splitting leaves the tree red.

- [ ] **Step 1: Write the failing schema tests**

Add to `tests/unit/test_schemas_instance.py`, reusing that module's existing
helpers for building a minimal world model:

```python
@pytest.mark.parametrize(
    "pointer",
    [
        ("capabilities", 0, "outcome_classes", 0),
        ("entities", 0, "invariants", 0),
        ("gaps", 0),
    ],
)
def test_a_child_element_without_claims_is_rejected(tmp_path, pointer):
    """The three defs that had no `claims` array until issue #6.

    `capability`, `entity`, `actor` and `goal` have always required one. These
    three did not, and `additionalProperties: false` meant a pass could not
    even record provenance voluntarily -- so an invariant's evidence went onto
    its entity, or into `description` prose no counter reads.
    """
    world = _world_with_a_gap()          # every child element carries claims
    node = world
    for key in pointer[:-1]:
        node = node[key]
    del node[pointer[-1]]["claims"]
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    findings = validate_artifact(path, "world-model")
    assert findings, f"a child element at {pointer} with no claims was accepted"


@pytest.mark.parametrize(
    "pointer",
    [
        ("capabilities", 0, "outcome_classes", 0),
        ("entities", 0, "invariants", 0),
        ("gaps", 0),
    ],
)
def test_a_child_element_with_an_empty_claims_array_is_rejected(tmp_path, pointer):
    """minItems 1 comes from $defs/claim_refs, which these now $ref.

    Both directions matter: "the key is present" is not the property. An empty
    array is a pass declaring it has no evidence for an element it declared
    anyway, which is the confabulation every refusal-conditions section warns
    about.
    """
    world = _world_with_a_gap()
    node = world
    for key in pointer[:-1]:
        node = node[key]
    node[pointer[-1]]["claims"] = []
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    assert validate_artifact(path, "world-model"), (
        f"an empty claims array at {pointer} was accepted"
    )
```

Write `_world_with_a_gap()` as a module-level helper in that test file: start
from `tests.toy.toy_world_model()`, give each of the two outcome classes on each
capability and each invariant on `ent-ticket` a `claims` list, and append one gap
with `claims`. The toy world model has no gaps, and the parametrisation needs
one.

- [ ] **Step 2: Run them and confirm they fail**

```bash
uv run pytest tests/unit/test_schemas_instance.py -k child_element -v
```

Expected: all six FAIL — `validate_artifact` returns `[]` because the key is not
required and, for the empty-array case, not even defined.

- [ ] **Step 3: Change the schema**

In `src/rubrica/schema/world-model-0.1.json`, for each of `$defs/invariant`,
`$defs/outcome_class` and `$defs/gap`: add `"claims"` to the end of `required`,
and add to `properties`:

```json
"claims": { "$ref": "#/$defs/claim_refs" }
```

Leave `$defs/invariant`'s `oneOf` (machine-xor-prose) exactly as it is — it
constrains different keys and adding a required property beside it does not
interact.

`$defs/gap` gets it too, and that is deliberate even though a gap records what no
input contains: what a gap's claims cite is the evidence that the *absence
matters*. On run-20260823-112746 the run-1 gate-1 brief reported
`trajectories2-json-14: 0/19 claims cited` while `gap-search-tool-error-response`
in the same brief rested on `clm-trajectories2-json-14-019` in prose.

- [ ] **Step 4: Run the schema tests, then watch the fixture fail**

```bash
uv run pytest tests/unit/test_schemas_instance.py -k child_element -v
uv run pytest tests/unit/test_refs_world_model.py -x -q
```

Expected: the six new tests PASS; many other tests now FAIL because
`tests/toy.py` builds a world model whose outcome classes, invariants and gaps
carry no claims. That failure is the next step's work — do not weaken the schema
to silence it.

- [ ] **Step 5: Move the fixture's citations down to the elements they are about**

This is the highest-risk edit in the plan: `tests/fixtures/toy/` is the model
answer a skill imitates, so a wrong mapping here teaches a skill the wrong thing.
The mapping below is derived from the claim statements in `tests/toy.py`'s
`_CLAIMS` — read each statement before you write the citation, and do not
shortcut by leaving the claim on the parent as well.

In `tests/toy.py`'s `toy_world_model()`:

```python
# cap-find-tickets
"outcome_classes": [
    {
        "id": "oc-found",
        "kind": "success",
        "description": "one or more tickets match the filters",
        # clm-api-005: "find_tickets returns a possibly-empty list of matching
        # tickets". The one claim covers both outcome classes, and citing it
        # twice is correct rather than sloppy -- an outcome class's claims are
        # the evidence for *that outcome*, not a partition of the claim set.
        "claims": ["clm-api-005"],
    },
    {
        "id": "oc-none",
        "kind": "empty",
        "description": "no ticket matches the filters",
        # clm-trace-001 is the observed empty return; clm-api-005 is the stated
        # "possibly-empty".
        "claims": ["clm-api-005", "clm-trace-001"],
    },
],
# The capability's own claims are now the capability-kind ones only.
"claims": ["clm-api-001", "clm-api-007", "clm-api-008"],
```

```python
# cap-get-ticket
"outcome_classes": [
    {
        "id": "oc-detail",
        "kind": "success",
        "description": "the ticket and its comments, ordered by position",
        "claims": ["clm-api-006"],
    },
    {
        "id": "oc-missing",
        "kind": "not_found",
        "description": "no ticket has that id, which is an error",
        # clm-notes-004, the *preferred_a* side of con-missing-semantics. Its
        # losing side, clm-trace-002, is deliberately not cited here: the
        # contradiction records it, and citing the side the resolution rejected
        # would model a disagreement as settled the other way.
        "claims": ["clm-notes-004"],
    },
],
"claims": ["clm-api-002", "clm-api-009"],
```

```python
# ent-ticket's invariants
{
    "id": "inv-comment-count",
    "statement": "comment_count is the number of comments on the ticket",
    "machine": {...unchanged...},
    # clm-notes-005: "comment_count equals the number of comment records on the
    # ticket".
    "claims": ["clm-notes-005"],
},
{
    "id": "inv-ticket-id-unique",
    "statement": "ticket_id is unique across every queue",
    "machine": {...unchanged...},
    # clm-notes-006, whose statement is this invariant verbatim.
    "claims": ["clm-notes-006"],
},
# and the entity's own claims are the entity-kind one only:
"claims": ["clm-api-003"],
```

`"gaps": []` stays empty — the golden world has no gap, and inventing one to
exercise the new requirement would change what the fixture teaches. The gap
requirement is exercised by Task 2 Step 1's `_world_with_a_gap()` helper and by
`tests/fixtures/toy-gap/`.

- [ ] **Step 6: Resolve the new citation sites in `check_world_model`**

`refs.check_world_model` resolves `claims` for the four top-level groups and the
contradiction sides. Add the three nested sites immediately after the existing
group loop, so a fabricated id on a child element is reported the same way as one
on its parent:

```python
    # The three nested citation sites, resolved on the same one-directional rule
    # as every other reference in this module: that the id exists, never that the
    # claim supports the element. Support is semantic and belongs to gate 1.
    for i, capability in enumerate(world.get("capabilities", [])):
        for j, outcome_class in enumerate(capability.get("outcome_classes", []) or []):
            for k, claim_id in enumerate(outcome_class.get("claims", []) or []):
                if claim_id not in known_claims:
                    report(
                        f"/capabilities/{i}/outcome_classes/{j}/claims/{k}",
                        f"no such claim: {claim_id}",
                    )
    for i, entity in enumerate(world.get("entities", [])):
        for j, invariant in enumerate(entity.get("invariants", []) or []):
            for k, claim_id in enumerate(invariant.get("claims", []) or []):
                if claim_id not in known_claims:
                    report(
                        f"/entities/{i}/invariants/{j}/claims/{k}",
                        f"no such claim: {claim_id}",
                    )
    for i, gap in enumerate(world.get("gaps", []) or []):
        for k, claim_id in enumerate(gap.get("claims", []) or []):
            if claim_id not in known_claims:
                report(f"/gaps/{i}/claims/{k}", f"no such claim: {claim_id}")
```

- [ ] **Step 7: Write the failing test for that resolution, then confirm it passes**

Add to `tests/unit/test_refs_world_model.py`, matching the module's existing
style for a fabricated-id test:

```python
@pytest.mark.parametrize(
    "site",
    [
        "/capabilities/0/outcome_classes/0/claims/0",
        "/entities/0/invariants/0/claims/0",
    ],
)
def test_a_fabricated_claim_id_on_a_child_element_is_reported(tmp_path, site):
    """The mirror of the parent-element check, at the three new sites.

    Without this, a pass could satisfy the new `claims` requirement with an id
    it invented, and layer 2 -- whose whole job is that every reference
    resolves -- would not look.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world = read_json(run.world_model)
    node = world
    for key in site.strip("/").split("/")[:-1]:
        node = node[int(key)] if key.isdigit() else node[key]
    node[0] = "clm-does-not-exist"
    write_json(run.world_model, world)
    findings = refs.check_world_model(run)
    assert any("clm-does-not-exist" in f.message for f in findings)
    assert any(f.pointer == site for f in findings), (
        f"reported, but not at {site}: {[f.pointer for f in findings]}"
    )
```

Run it before Step 6 is in place if you want the red — otherwise run it now and
expect PASS.

```bash
uv run pytest tests/unit/test_refs_world_model.py -k child_element -v
```

- [ ] **Step 8: Green the whole tree**

```bash
make test
```

Expect failures in any test that hand-authors a world-model fragment with an
invariant, outcome class or gap. Fix each by adding a real citation, never by
relaxing the schema. Two places to check specifically:

- `tests/unit/test_brief.py` and `tests/unit/test_refs_*.py` build fragments
  inline in several places.
- `tests/unit/test_refusal_fixtures.py` guards the negative fixtures'
  key-path sets with `_key_paths(golden) - _key_paths(fixture)`. The new
  `claims` keys change both sides, and the assertion is one-directional, so it
  should stay green — confirm it does rather than assuming.

Then:

```bash
make check
uv run rubrica check-skills
```

- [ ] **Step 9: Verify the toy's utilisation did not move**

```bash
uv run python - <<'PY'
import json, pathlib, tempfile
from tests.toy import build_toy_run
from rubrica.utilisation import claim_utilisation
with tempfile.TemporaryDirectory() as td:
    run = build_toy_run(pathlib.Path(td), upto="reconcile-seal")
    a = claim_utilisation(run)["artifacts"]
    print(sum(x["cited"] for x in a), "/", sum(x["total"] for x in a))
PY
```

Expected: `19 / 19`. The fixture was at 19/19 before this task by citing child
claims on the parent; it must be at 19/19 after by citing them on the child. A
lower number means a citation was moved and lost rather than moved.

- [ ] **Step 10: Commit**

```bash
git add src/rubrica/schema/world-model-0.1.json src/rubrica/refs.py tests/
git commit -S -s -m "$(cat <<'MSG'
feat: Require claims on an invariant, outcome class and gap

Of the world model's element defs, capability, entity, actor and goal have
always required a non-empty claims array. invariant, outcome_class and gap
required none and, being additionalProperties: false, could not carry one at
all -- so an invariant's provenance went onto its entity and an outcome class's
into description prose. Measured on run-20260823-112746: invariant claims cited
0 of 55, outcome_class 7 of 62 with 24 more prose-only. 117 of 434 claims, 27%
of the corpus, with nowhere structured to record where they came from.

check_world_model resolves the three new sites on the same one-directional rule
as every other reference here: that the id exists, never that the claim
supports the element.

The golden fixture moves its citations down to the elements they are about,
which is a correction as much as an adaptation: it was reaching 19/19 by citing
invariant- and outcome_class-kind claims on the parent, a workaround the schema
never required and two real dispatches did not infer. It is still 19/19.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 3: `inputs_seen` on the four partials, derived in the fixture

**Files:**
- Create: `src/rubrica/schema/inputs-seen-0.1.json`
- Modify: `src/rubrica/schema/capabilities-part-0.1.json`, `entities-part-0.1.json`, `outcomes-part-0.1.json`, `goals-part-0.1.json`
- Modify: `src/rubrica/validate.py` (`ARTIFACT_SCHEMAS`, comment only)
- Modify: `tests/toy.py` (`split_world_model`, new `_inputs_seen` helper)
- Test: `tests/unit/test_validate_registry_triage.py`, `tests/unit/test_schemas_instance.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 structurally; ordered after them because Task
  2's fixture edit changes which claims each part cites, and `_inputs_seen`
  derives from that.
- Produces:
  - `inputs-seen-0.1.json` with `$defs/row`.
  - Each of the four part schemas requires a document-level `inputs_seen` array.
  - `tests.toy._inputs_seen(part_document, own_kinds) -> list[dict]` — Task 4's
    checker tests build rows with it rather than by hand.

- [ ] **Step 1: Write the failing part-schema test**

Add to `tests/unit/test_validate_registry_triage.py`, which already owns the part
schemas' cross-file `$ref` tests:

```python
_INPUTS_SEEN_PARTS = ("capabilities-part", "entities-part", "outcomes-part", "goals-part")


@pytest.mark.parametrize("kind", _INPUTS_SEEN_PARTS)
def test_a_partial_without_inputs_seen_is_rejected(tmp_path, kind):
    """The four passes that own a claim kind must account for every input.

    Issue #6: read coverage of 01-claims/ varied 3/23 to 23/23 across
    byte-identical dispatches, and nothing in either check layer could see the
    difference -- a skimmed read produces a well-formed partial. The accounting
    is what makes it visible.
    """
    document = _minimal_part(kind)
    del document["inputs_seen"]
    path = tmp_path / f"{kind}.json"
    write_json(path, document)
    assert validate_artifact(path, kind), f"{kind} with no inputs_seen was accepted"


@pytest.mark.parametrize("kind", _INPUTS_SEEN_PARTS)
def test_a_dropped_claim_without_a_note_is_rejected(tmp_path, kind):
    """`dropped >= 1` requires `note`, and layer 1 owns it.

    A property a deterministic gate can enforce belongs to that gate. This one
    is expressible in JSON Schema as if/then, so it is not the checker's.
    """
    document = _minimal_part(kind)
    document["inputs_seen"] = [
        {"artifact_id": "api-json", "own_kind_total": 2, "cited": 1, "dropped": 1}
    ]
    path = tmp_path / f"{kind}.json"
    write_json(path, document)
    assert validate_artifact(path, kind), f"{kind} dropped a claim with no note"


@pytest.mark.parametrize("kind", _INPUTS_SEEN_PARTS)
def test_a_row_with_nothing_dropped_needs_no_note(tmp_path, kind):
    """The other direction, and the reason totality costs nothing.

    Rows are total over manifest.inputs, including inputs holding none of the
    pass's own kind. A 0/0/0 row is the honest record for those, and requiring
    prose beside it would make the totality rule expensive enough to argue
    with.
    """
    document = _minimal_part(kind)
    document["inputs_seen"] = [
        {"artifact_id": "api-json", "own_kind_total": 0, "cited": 0, "dropped": 0}
    ]
    path = tmp_path / f"{kind}.json"
    write_json(path, document)
    assert validate_artifact(path, kind) == []
```

`_minimal_part(kind)` is a new module-level helper: return
`tests.toy.split_world_model()[key]` for the matching key (`"capabilities"`,
`"entities"`, `"outcomes"`, `"goals"`), which after Step 4 already carries
`inputs_seen`. Write it as a thin lookup, not a second copy of a part document —
this module's own comment says the point of several tests is to notice when a
schema and its fixture drift.

- [ ] **Step 2: Run them and confirm they fail**

```bash
uv run pytest tests/unit/test_validate_registry_triage.py -k "inputs_seen or dropped or needs_no_note" -v
```

Expected: FAIL — `_minimal_part` raises `KeyError: 'inputs_seen'`, or the
deletions are accepted because the key is not in the schema. Either is the red
you want; the tests go green together in Step 5.

- [ ] **Step 3: Create the shared schema**

`src/rubrica/schema/inputs-seen-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "inputs-seen-0.1.json",
  "title": "One reconcile pass's accounting of the inputs it read",
  "$defs": {
    "row": {
      "type": "object",
      "required": ["artifact_id", "own_kind_total", "cited", "dropped"],
      "additionalProperties": false,
      "properties": {
        "artifact_id": { "$ref": "world-model-0.1.json#/$defs/id" },
        "own_kind_total": { "type": "integer", "minimum": 0 },
        "cited": { "type": "integer", "minimum": 0 },
        "dropped": { "type": "integer", "minimum": 0 },
        "note": { "type": "string", "minLength": 1 }
      },
      "if": { "properties": { "dropped": { "minimum": 1 } }, "required": ["dropped"] },
      "then": { "required": ["note"] }
    }
  }
}
```

The `if` carries `required: ["dropped"]` as well as the `minimum`: without it, a
document omitting `dropped` entirely satisfies the `if` vacuously and would then
be forced to carry a note. `dropped` is required by the row anyway, so this is
belt-and-braces on a subschema that is easy to copy wrong.

This file **has no artifact kind.** It is `$ref`ed by four part schemas and
produced by no stage. `validate._schema_registry` globs `*.json` under the schema
root and registers each by filename, so the cross-file `$ref` resolves without
any registration.

- [ ] **Step 4: Require it in the four part schemas, and record the omission**

In each of `capabilities-part-0.1.json`, `entities-part-0.1.json`,
`outcomes-part-0.1.json` and `goals-part-0.1.json`: add `"inputs_seen"` to
`required`, and to `properties`:

```json
"inputs_seen": {
  "type": "array",
  "items": { "$ref": "inputs-seen-0.1.json#/$defs/row" }
}
```

No `minItems`: totality over `manifest.inputs` is a cross-artifact property and
belongs to layer 2, which is the layer that can read the manifest. A `minItems: 1`
here would half-enforce it and invite the reading that layer 1 covers it.

Then in `src/rubrica/validate.py`, immediately after the reconcile-partial block
in `ARTIFACT_SCHEMAS`, add:

```python
    # inputs-seen-0.1.json is deliberately absent from this map, and is the only
    # schema in the package that is not an artifact kind. It holds one $defs/row
    # that the four reconcile partials $ref, and no stage produces a document of
    # that shape on its own -- so a kind here would name an artifact
    # `validate --stage X` must never look for. _schema_registry globs the
    # directory and registers by filename, so the cross-file $ref resolves
    # without an entry.
```

- [ ] **Step 5: Derive the rows in the fixture**

`split_world_model` derives every partial from one world model, for the reason its
docstring gives: a second hand-authored copy is a second thing to keep correct.
`inputs_seen` follows the same rule — derive it, never write literals.

Add to `tests/toy.py`, above `split_world_model`:

```python
# Which claim kinds each pass is accountable for. The six kinds in
# claims-0.1.json partition onto the four passes that own one, which is what
# makes an own-kind count a per-pass number rather than an aggregate: measured on
# run-20260823-112746, per-kind citation was capability 110/135 while goal was
# 2/38, and the run's single aggregate figure of 33.6% is the average that hid
# it. reconcile-gaps owns no kind, and reconcile-subjects and
# reconcile-contradict need no accounting -- refs.check_subjects already makes
# the cover total.
OWN_KINDS: dict[str, tuple[str, ...]] = {
    "capabilities": ("capability",),
    "entities": ("entity", "invariant"),
    "outcomes": ("outcome_class",),
    "goals": ("actor", "goal"),
}


def _claim_refs_in(node: Any) -> set[str]:
    """Every id in every `claims` array anywhere in a partial.

    A walk rather than a per-part list of paths: the four partials nest their
    citations differently -- an entity carries them on itself and on each
    invariant, the outcomes part two levels down inside an `outcomes` record --
    and a path list would need revising by whoever nests a new element. Mirrors
    refs._claim_refs_in, and both exist because the fixture must compute what
    the checker recomputes; if they ever disagree, the fixture is what proves
    the checker wrong rather than the other way round.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "claims":
                found.update(v for v in value if isinstance(v, str))
            else:
                found.update(_claim_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            found.update(_claim_refs_in(item))
    return found


def _inputs_seen(part: dict[str, Any], own_kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """One row per artifact in the toy corpus, computed from the part itself.

    Total over every artifact, including those holding none of this pass's kinds
    -- a 0/0/0 row is the honest record for those, and it is what makes the
    accounting an instrument: a pass cannot state a count for a file it never
    opened.
    """
    cited_ids = _claim_refs_in(part)
    rows: list[dict[str, Any]] = []
    for artifact_id in ARTIFACT_IDS:
        own = [c for c in toy_claims(artifact_id)["claims"] if c["kind"] in own_kinds]
        cited = sum(1 for claim in own if claim["id"] in cited_ids)
        row: dict[str, Any] = {
            "artifact_id": artifact_id,
            "own_kind_total": len(own),
            "cited": cited,
            "dropped": len(own) - cited,
        }
        if row["dropped"]:
            # The toy's one drop, and it is the worked example the spec wants on
            # the record: clm-trace-002 is the losing side of
            # con-missing-semantics, resolved `preferred_a`. It is cited by the
            # contradiction and by no partial, so the outcomes pass's row for
            # trace-json reads 2/1/1 -- which is exactly the case a reader at
            # gate 1 should be able to tell apart from a file nobody opened.
            row["note"] = (
                "the side of a recorded contradiction that its resolution did not prefer; "
                "cited by 01-contradictions/, deliberately not modelled here"
            )
        rows.append(row)
    return rows
```

Then in `split_world_model`'s return dict, add the field to the four partials that
take one:

```python
        "capabilities": {
            "schema_version": "0.1",
            "capabilities": [...unchanged...],
        },
```
becomes, for each of `capabilities`, `outcomes`, `entities` and `goals`, a
document built first and then given its rows. The cleanest shape, since
`_inputs_seen` needs the finished part:

```python
    partials: dict[str, Any] = {
        "capabilities": {
            "schema_version": "0.1",
            "capabilities": [
                {k: v for k, v in capability.items() if k != "outcome_classes"}
                for capability in world["capabilities"]
            ],
        },
        "outcomes": {
            "schema_version": "0.1",
            "outcomes": [
                {"capability_id": c["id"], "outcome_classes": c["outcome_classes"]}
                for c in world["capabilities"]
            ],
        },
        "entities": {"schema_version": "0.1", "entities": world["entities"]},
        "goals": {
            "schema_version": "0.1",
            "actors": world["actors"],
            "goals": world["goals"],
        },
    }
    for key, own_kinds in OWN_KINDS.items():
        partials[key]["inputs_seen"] = _inputs_seen(partials[key], own_kinds)
    return {
        "subjects": {"schema_version": "0.1", "subjects": subjects},
        "contradictions": {...unchanged...},
        **partials,
        "gaps": {"schema_version": "0.1", "gaps": world["gaps"]},
    }
```

`gaps` gets no `inputs_seen`: `rb-reconcile-gaps` owns no claim kind, and a gap
asserts what no input contains, so no output shape can force its read coverage.
That hole is real and gets a register entry in Task 7.

- [ ] **Step 6: Confirm the derived rows are the expected arithmetic**

```bash
uv run python - <<'PY'
import json
from tests.toy import split_world_model, OWN_KINDS
parts = split_world_model()
for key in OWN_KINDS:
    print(key)
    for row in parts[key]["inputs_seen"]:
        print("  ", row)
PY
```

Expected, exactly:

| part | api-json | notes-md | trace-json |
|---|---|---|---|
| capabilities | 5/5/0 | 0/0/0 | 0/0/0 |
| entities | 2/2/0 | 2/2/0 | 0/0/0 |
| outcomes | 2/2/0 | 1/1/0 | **2/1/1 + note** |
| goals | 0/0/0 | 5/5/0 | 0/0/0 |

(`own_kind_total`/`cited`/`dropped`.) Any other number means Task 2's citation
move went somewhere unintended — go back and read the claim statements again
rather than adjusting the expectation.

- [ ] **Step 7: Green the tree**

```bash
uv run pytest tests/unit/test_validate_registry_triage.py -v
make test
make check
uv run rubrica check-skills
```

`tests/unit/test_reconcile_seal.py` (or wherever the `seal(split(w)) == w` round
trip lives — grep for `split_world_model`) must still pass: the seal reads named
arrays out of each part, so a document-level `inputs_seen` is dropped for free and
the assembled world model is byte-identical. If that test fails, the seal is
copying a part wholesale somewhere and that is a finding worth reporting before
working around.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/schema/ src/rubrica/validate.py tests/
git commit -S -s -m "$(cat <<'MSG'
feat: Require each reconcile pass to account for every input it read

Issue #6 measured read coverage of 01-claims/ varying 3/23 to 23/23 across
byte-identical dispatches of the same pass, with claims in unread files cited at
exactly 0/167 and nothing in either check layer able to tell the two runs apart.
The prose already said to read every file and named this exact failure mode, so
the change is to the output shape: each of the four partials whose pass owns a
claim kind now carries one inputs_seen row per manifest input, and layer 1 holds
the one rule it can express -- a row that dropped anything must say why.

The pattern is copied from the one pass in the family that is immune.
rb-reconcile-subjects must name every claim id and refs.check_subjects enforces
totality; on the measured run its cover spanned 23 of 23 artifacts in the same
conditions where the goals pass read 3.

inputs-seen-0.1.json is the first schema in the package that is not an artifact
kind, and validate.py now records why it is absent from ARTIFACT_SCHEMAS.

The fixture derives its rows from the partials rather than declaring them, for
the reason split_world_model already derives everything else, and its one
non-zero drop is the worked example: the losing side of a recorded
contradiction, cited by 01-contradictions/ and by no partial.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 4: `refs.check_input_dispositions`

**Files:**
- Modify: `src/rubrica/refs.py` (new helpers, new checker, `check_all`)
- Test: `tests/unit/test_refs_input_dispositions.py` (create)

**Interfaces:**
- Consumes: `tests.toy.split_world_model`'s `inputs_seen` rows and
  `tests.toy.OWN_KINDS` from Task 3.
- Produces: `refs.check_input_dispositions(run) -> list[Finding]`, called from
  `check_all` between `check_outcomes` and `check_world_model`. Findings are
  reported against the partial that declared the row, layer `"refs"`, pointer
  `/inputs_seen` or `/inputs_seen/{i}/<field>`.

- [ ] **Step 1: Write the failing tests, one per finding shape**

Create `tests/unit/test_refs_input_dispositions.py`:

```python
"""The read-coverage accounting, and the five ways a row can be wrong.

Issue #6: three reconcile passes were re-dispatched over a byte-identical run
directory and read 12/23, 10/23 and 9/23 of 01-claims/ the first time, 23/23,
13/23 and 3/23 the second. One improved to full coverage and one got materially
worse, which is what rules out a systematic cause. Both runs reported success
and both passed layer 1.

Every test here mutates one field of a clean toy run and asserts exactly its own
finding, because the five shapes are close enough that a mutation reaching two of
them is the likely bug.
"""

from __future__ import annotations

import pytest

from rubrica import refs
from rubrica.artifacts import read_json, write_json
from tests.toy import build_toy_run


def _rows(run, attribute="outcomes_part"):
    """The outcomes part by default: it is the one whose toy rows are not all
    zero-drop, so a mutation there exercises the note path too."""
    path = getattr(run, attribute)
    return path, read_json(path)


def test_a_clean_run_reports_nothing(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert refs.check_input_dispositions(run) == []


def test_a_missing_row_for_a_manifest_input_is_reported(tmp_path):
    """The denominator is manifest.inputs, not the rows.

    This is the finding a pass that read three of twenty-three files hits
    first, and the reason the rows must be total: an accounting that only
    covers what it read cannot report what it did not.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    dropped_row = part["inputs_seen"].pop()
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert dropped_row["artifact_id"] in findings[0].message
    assert findings[0].artifact == path


def test_a_row_for_an_artifact_the_manifest_does_not_name_is_reported(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    part["inputs_seen"].append(
        {"artifact_id": "no-such-input", "own_kind_total": 0, "cited": 0, "dropped": 0}
    )
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "no-such-input" in findings[0].message


def test_an_own_kind_total_that_disagrees_with_the_claims_file_is_reported(tmp_path):
    """The forcing function.

    own_kind_total is recomputed from 01-claims/, so it is the one number a
    pass cannot state for a file it never opened. Everything else in this
    accounting is bookkeeping on top of it.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    row = next(r for r in part["inputs_seen"] if r["own_kind_total"])
    row["own_kind_total"] += 1
    row["dropped"] += 1
    row["note"] = "a number this pass did not measure"
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "own_kind_total" in findings[0].message


def test_a_cited_count_that_disagrees_with_the_part_is_reported(tmp_path):
    """Recomputed from the part's own claims arrays, nested ones included."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    row = next(r for r in part["inputs_seen"] if r["cited"])
    row["cited"] -= 1
    row["dropped"] += 1
    row["note"] = "a flattering count in the other direction"
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "cited" in findings[0].message


def test_arithmetic_that_does_not_close_is_reported(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    row = next(r for r in part["inputs_seen"] if r["own_kind_total"])
    row["dropped"] += 1
    row["note"] = "one more drop than there are claims to drop"
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "cited + dropped" in findings[0].message


def test_a_deleted_claims_file_is_not_this_checkers_finding(tmp_path):
    """A `1` must name the right artifact.

    check-refs over an unreadable 01-claims/ once produced four fabricated
    "no such claim" findings against a correct world model. A missing claims
    file counts as zero here and stays the finding of the checker that owns it,
    so this one reports the count disagreement it genuinely sees and nothing
    about the absence.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    (run.claims_dir / "trace-json.json").unlink()
    findings = refs.check_input_dispositions(run)
    assert findings, "the rows still declare counts for a file that is gone"
    assert all("no such claim" not in f.message for f in findings)
    assert all(f.artifact != run.claims_dir for f in findings)


def test_a_row_that_cited_nothing_is_not_a_finding_when_the_arithmetic_holds(tmp_path):
    """own_kind_total > 0 and cited == 0 is deliberately not a finding.

    The row already carries a required note, so the drop is on the record.
    Making it a finding would fail a repair round that cannot repair anything,
    and would put a coverage judgment behind an exit code -- the threshold
    check_claim_utilisation refuses on measurement: run-20260812-130056 had 130
    of 287 claims uncited and almost all of those drops were correct.

    So this moves api-json's outcome-class citations onto notes-md's claim and
    restates the row honestly. The pass has now cited nothing from api-json and
    said why, and that is a clean artifact.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    for record in part["outcomes"]:
        for outcome_class in record["outcome_classes"]:
            outcome_class["claims"] = ["clm-notes-004"]
    for row in part["inputs_seen"]:
        if row["artifact_id"] == "api-json":
            row.update(
                {
                    "cited": 0,
                    "dropped": row["own_kind_total"],
                    "note": "both restated by clm-notes-004, which is stated rather than "
                    "reverse_engineered",
                }
            )
        elif row["artifact_id"] == "notes-md":
            row.update({"cited": 1, "dropped": 0})
        elif row["artifact_id"] == "trace-json":
            row.update({"cited": 0, "dropped": 2, "note": "superseded by clm-notes-004"})
    write_json(path, part)
    assert refs.check_input_dispositions(run) == [], [
        str(f) for f in refs.check_input_dispositions(run)
    ]
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
uv run pytest tests/unit/test_refs_input_dispositions.py -v
```

Expected: every test FAILS with `AttributeError: module 'rubrica.refs' has no
attribute 'check_input_dispositions'`.

- [ ] **Step 3: Add the two helpers**

In `src/rubrica/refs.py`, beside `_claim_index` and `_claim_ids`:

```python
def _claims_by_artifact(run: RunPaths) -> dict[str, list[dict]]:
    """artifact_id -> its claim records, from 01-claims/ itself.

    Keyed on the payload's own `artifact_id` rather than the filename, because
    that is the field every other checker resolves against and a mismatch
    between the two is check_manifest's finding, not this reader's.
    """
    out: dict[str, list[dict]] = {}
    for path in list_json(run.claims_dir):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        artifact_id = payload.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        out.setdefault(artifact_id, []).extend(
            claim for claim in _as_list(payload.get("claims")) if isinstance(claim, dict)
        )
    return out


def _claim_refs_in(node: Any) -> list[str]:
    """Every id in every `claims` array anywhere in a document.

    A walk rather than a per-part list of paths: the four reconcile partials nest
    their citations differently -- an entity carries them on itself and on each
    invariant, the outcomes part two levels down inside an `outcomes` record --
    and a path list would need revising by whoever nests a new element, which is
    the drift this module's "$ref, do not restate" rule refuses elsewhere. An
    inputs_seen row has no `claims` key, so the accounting cannot count itself.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "claims":
                found.extend(v for v in _as_list(value) if isinstance(v, str))
            else:
                found.extend(_claim_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_claim_refs_in(item))
    return found
```

- [ ] **Step 4: Add the checker**

Place it immediately before `check_claim_utilisation`, which it is the
non-statistical counterpart of:

```python
# Which claim kinds each reconcile pass is accountable for. The six kinds in
# claims-0.1.json partition onto the four passes that own one, and that is what
# makes a per-pass number possible at all: measured on run-20260823-112746,
# per-kind citation ran capability 110/135 (the pass that read 23/23 files) and
# goal 2/38 (the pass that read 3/23), while the run's one aggregate utilisation
# figure was 33.6% -- the average that hid both. reconcile-gaps owns no kind, and
# reconcile-subjects and reconcile-contradict need no accounting because
# check_subjects already makes the cover total.
PASS_OWN_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("capabilities_part", ("capability",)),
    ("entities_part", ("entity", "invariant")),
    ("outcomes_part", ("outcome_class",)),
    ("goals_part", ("actor", "goal")),
)


def check_input_dispositions(run: RunPaths) -> list[Finding]:
    """Each reconcile pass's accounting of the inputs it read, recomputed.

    Issue #6 measured a pass's read coverage of 01-claims/ varying 3/23 to 23/23
    across byte-identical dispatches, with claims in files it never opened cited
    at exactly 0/167. Neither check layer could see it: a skimmed read produces a
    well-formed partial, and utilisation is a lagging aggregate that averages a
    diligent pass with a skimming one.

    So every number a row declares is recomputed here -- `own_kind_total` from
    the claims file, `cited` from the part's own citations -- and `own_kind_total`
    is the forcing function, because it is the one figure a pass cannot state for
    a file it never opened.

    What this deliberately does *not* report: a row whose own_kind_total is
    positive and whose cited is zero. Such a row already carries a required note,
    so the drop is on the record and belongs to the human at gate 1. Making it a
    finding would fail a repair round that cannot repair anything, and would put
    a coverage judgment behind an exit code -- the threshold
    check_claim_utilisation refuses for a reason its own docstring measures.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    declared = [
        entry["artifact_id"]
        for entry in _as_list(manifest.get("inputs"))
        if isinstance(entry, dict) and isinstance(entry.get("artifact_id"), str)
    ]
    by_artifact = _claims_by_artifact(run)

    out: list[Finding] = []
    for attribute, own_kinds in PASS_OWN_KINDS:
        path = getattr(run, attribute)
        part = _load(path)
        if part is None:
            # An absent or unreadable partial is reconcile.seal's finding and
            # layer 1's; reporting it again here would double-count one defect
            # and name a second artifact for it.
            continue

        def report(pointer: str, message: str, path: Path = path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        rows = [row for row in _as_list(part.get("inputs_seen")) if isinstance(row, dict)]
        cited_ids = set(_claim_refs_in(part))
        seen: set[str] = set()

        for i, row in enumerate(rows):
            artifact_id = row.get("artifact_id")
            if not isinstance(artifact_id, str):
                continue
            seen.add(artifact_id)
            if artifact_id not in declared:
                report(
                    f"/inputs_seen/{i}/artifact_id",
                    f"no such input: {artifact_id}; the accounting must be over "
                    "manifest.inputs, and a row for an artifact the manifest does not "
                    "name is a row about nothing",
                )
                continue
            own = [
                claim
                for claim in by_artifact.get(artifact_id, [])
                if claim.get("kind") in own_kinds
            ]
            actual_cited = sum(1 for claim in own if claim.get("id") in cited_ids)
            if row.get("own_kind_total") != len(own):
                report(
                    f"/inputs_seen/{i}/own_kind_total",
                    f"declared own_kind_total={row.get('own_kind_total')} for "
                    f"{artifact_id} but 01-claims/ holds {len(own)} claim(s) of "
                    f"{', '.join(own_kinds)}",
                )
            if row.get("cited") != actual_cited:
                report(
                    f"/inputs_seen/{i}/cited",
                    f"declared cited={row.get('cited')} for {artifact_id} but this "
                    f"artifact's claims appear {actual_cited} time(s) in this part",
                )
            if row.get("cited", 0) + row.get("dropped", 0) != row.get("own_kind_total"):
                report(
                    f"/inputs_seen/{i}",
                    f"cited + dropped does not equal own_kind_total for {artifact_id}",
                )

        for artifact_id in [a for a in declared if a not in seen]:
            report(
                "/inputs_seen",
                f"no row for input {artifact_id}; the accounting must be total over "
                "manifest.inputs, or a pass that never opened a claims file is "
                "indistinguishable from one that opened it and cited nothing",
            )
    return out
```

`def report(..., path: Path = path)` binds the loop variable deliberately — ruff's
`B023` (function definition does not bind loop variable) fires otherwise, and it
would be a real bug: every finding would be reported against the last partial.

- [ ] **Step 5: Wire it into `check_all`**

In `check_all`, between `check_outcomes` and `check_world_model`:

```python
    findings.extend(check_input_dispositions(run))
```

After the partials are readable, before anything reasons about the assembled
model.

- [ ] **Step 6: Run the tests**

```bash
uv run pytest tests/unit/test_refs_input_dispositions.py -v
make test
make check
```

Expected: all PASS. If a test reports two findings where it expects one, the
mutation is reaching a second shape — narrow the mutation, do not loosen the
assertion.

- [ ] **Step 7: Check the unreadable-input paths**

`cli.py`, `validate.py`, `refs.py` and `paths.py` are the four modules whose
unreadable-input paths must be exercised, not just the happy path. Run each of
these against a toy run and confirm the exit code and that stdout is non-empty
whenever it is 1:

```bash
RUN=$(mktemp -d)/run && uv run python -c "
import pathlib, sys
sys.path.insert(0, '.')
from tests.toy import build_toy_run
print(build_toy_run(pathlib.Path('$RUN').parent, upto='reconcile-seal').root)
" 
# then, against the path it prints:
chmod 000 <run>/01-outcomes.json && uv run rubrica check-refs --run <run>; echo "exit=$?"
chmod 644 <run>/01-outcomes.json
chmod 000 <run>/01-claims && uv run rubrica check-refs --run <run>; echo "exit=$?"
chmod 755 <run>/01-claims
```

Expected in both cases: exit **1** with at least one line on stdout, and the line
must name the unreadable artifact rather than blaming a correct one. An unreadable
`01-outcomes.json` must not produce a row of fabricated `own_kind_total`
disagreements — `_load` returning `None` short-circuits that partial, and
`check_readable` short-circuits `check_all` entirely. Confirm rather than assume;
this is the class of defect the register records four fabricated findings for.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs_input_dispositions.py
git commit -S -s -m "$(cat <<'MSG'
feat: Recompute each reconcile pass's input accounting

check_input_dispositions reports five ways an inputs_seen row can be wrong: no
row for a manifest input, a row for an artifact the manifest does not name, an
own_kind_total that disagrees with 01-claims/, a cited count that disagrees with
the part's own citations, and arithmetic that does not close.

own_kind_total is the forcing function and the reason this is not a
self-report: it is the one figure a pass cannot state for a file it never
opened. Issue #6's suggestion of a declared read_artifacts[] list would have
been prose about its own compliance, the weakness the register already records
for objective_review.

A row whose own_kind_total is positive and whose cited is zero is deliberately
not a finding. It already carries a required note, so the drop is on the record
for gate 1, and a finding there would fail a repair round that cannot repair
anything -- the threshold check_claim_utilisation refuses on the measurement in
its own docstring.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 5: The prose, in five skills

**Files:**
- Modify: `src/rubrica/skills/rb-reconcile-capabilities/SKILL.md` (§2 after line 85, §3, §4, §5)
- Modify: `src/rubrica/skills/rb-reconcile-entities/SKILL.md` (§2 after line 82, §3, §4, §5)
- Modify: `src/rubrica/skills/rb-reconcile-outcomes/SKILL.md` (§2 after line 87, §3, §4, §5)
- Modify: `src/rubrica/skills/rb-reconcile-goals/SKILL.md` (§2 after line 54, §3, §4, §5)
- Modify: `src/rubrica/skills/rb-reconcile-gaps/SKILL.md` (§2, §4 — the gap `claims` requirement only)
- Test: `tests/unit/test_skills_reconcile_family.py`

**Interfaces:**
- Consumes: the schema and checker from Tasks 3–4; the prose must describe what
  they actually enforce.
- Produces: no code interface. `writes` and `schemas` are unchanged in every
  contract — the field is on an artifact each pass already writes — so
  `check-skills` needs nothing new. Confirm that by running it.

**What is deliberately not done here:** the existing "read every file under
`01-claims/` … not one of them, all of them" prose is **not** strengthened. It
already names this exact failure mode ("a merge built from a skill will drop the
claim that only shows up once, in the file you read fastest") and did not prevent
it, so a longer exhortation is the change with the worst measured odds. Do not
add emphasis, do not add a second paragraph saying it harder.

- [ ] **Step 1: Write the failing prose tests**

Add to `tests/unit/test_skills_reconcile_family.py`. Note the module derives
`FAMILY` from `STAGES` rather than restating a list; follow that:

```python
# The four passes that own a claim kind and therefore carry an inputs_seen
# accounting. Derived from the schema rather than restated: a part schema that
# gains the field joins this parametrization without anyone editing a literal.
OWNING = tuple(
    stage
    for stage in FAMILY
    if "inputs_seen"
    in read_json(schema_dir() / ARTIFACT_SCHEMAS[STAGE_ARTIFACTS[stage][0]]).get(
        "properties", {}
    )
)


def test_the_owning_passes_are_the_four_with_a_claim_kind():
    """A guard on the derivation above, not a restatement of it.

    If a fifth partial gains inputs_seen, this fails and someone has to decide
    whether that pass really owns a claim kind -- rb-reconcile-gaps owns none,
    and giving it an accounting would assert a read coverage no output shape can
    force.
    """
    assert OWNING == (
        "reconcile-capabilities",
        "reconcile-outcomes",
        "reconcile-entities",
        "reconcile-goals",
    ), OWNING


@pytest.mark.parametrize("stage", OWNING)
def test_the_output_section_states_the_accounting_is_total_over_the_manifest(stage):
    """Totality is the whole instrument, so the prose that describes it must say
    which set it is total over. A pass told only to "record what you read"
    records what it read, which is the artifact issue #6 already has.
    """
    output = _flat(stage, "2. Output")
    assert "inputs_seen" in output
    assert "manifest.inputs" in output
    assert "every input" in output


@pytest.mark.parametrize("stage", OWNING)
def test_the_method_says_to_record_the_row_as_each_file_is_finished(stage):
    """A row reconstructed at the end is a recollection of having read.

    That is the distinction the accounting exists to draw, so the instruction
    has to be about *when*, not only about *what*.
    """
    method = _flat(stage, "3. Method")
    assert "as you finish" in method
    assert "not" in method and "at the end" in method


@pytest.mark.parametrize("stage", OWNING)
def test_the_invariants_say_the_counts_are_recomputed_rather_than_trusted(stage):
    """A pass that believes its numbers are taken on faith has no reason to
    measure them. Naming the checker is what makes the obligation legible.
    """
    invariants = _flat(stage, "4. Invariants")
    assert "check-refs" in invariants
    assert "recomputes" in invariants
    assert "own_kind_total" in invariants


@pytest.mark.parametrize("stage", OWNING)
def test_a_claims_file_that_cannot_be_read_is_a_refusal_not_a_guessed_count(stage):
    """The one new refusal condition, and the one that can defeat the whole
    change: a pass that guesses four numbers to satisfy the schema has produced
    a clean artifact that means nothing.
    """
    refusals = _flat(stage, "5. Refusal conditions")
    assert "could not read" in refusals
    assert "guess" in refusals
    assert "refuse" in refusals


def test_gaps_says_a_gap_cites_the_claims_that_make_the_absence_matter():
    """rb-reconcile-gaps gets no accounting -- it owns no claim kind -- so the
    gap's own claims array is the whole of what it gained. The distinction the
    prose has to carry: the claims are not evidence *for* the unknown, they are
    evidence the unknown matters.
    """
    output = _flat("reconcile-gaps", "2. Output")
    assert "claims" in output
    assert "absence" in output or "why_it_matters" in output
```

- [ ] **Step 2: Run them and confirm they fail**

```bash
uv run pytest tests/unit/test_skills_reconcile_family.py -k "owning or accounting or recompute or guessed or absence" -v
```

Expected: FAIL. `test_the_owning_passes_are_the_four_with_a_claim_kind` should
already pass after Task 3 — if `OWNING` comes out empty, `STAGE_ARTIFACTS[stage][0]`
is not the kind you expect for some pass; print it and fix the derivation, not the
assertion.

- [ ] **Step 3: Add the §2 Output paragraph to each of the four**

The paragraph below goes at the end of each pass's `## 2. Output` section.
Substitute the pass's own kinds and file each time; the wording is otherwise
shared on purpose, because it describes a shared obligation.

For `rb-reconcile-capabilities` (own kind: `capability`):

```markdown
**The document also carries `inputs_seen`: one row per input, for every input
`manifest.json` names.** Each row is `{artifact_id, own_kind_total, cited,
dropped}`, plus a `note` whenever `dropped` is not zero. `own_kind_total` is how
many `capability`-kind claims that artifact's claims file holds — the kind this
pass is accountable for — `cited` is how many of them appear in a `claims` array
you wrote, and `dropped` is the rest.

Total over `manifest.inputs`, which means **a row for every input including the
ones holding no `capability` claim at all.** Those rows read `0/0/0` and need no
note, so saying "this file held nothing of mine" costs one line. An input with
no row is not a claim about that input; it is a gap in the accounting, and
`check-refs` reports it as one.

The `note` is where a drop stops being a number. "The disputed side of a
contradiction recorded `unresolved`" and "restated by a claim I cited from
another artifact" are both good reasons to drop a claim; a human reads them at
gate 1, and they are the only record that the drop was a decision rather than an
oversight.
```

For the other three, change the kind name and the count clause:

- `rb-reconcile-entities`: "how many `entity`-kind **and** `invariant`-kind claims
  that artifact's claims file holds — the two kinds this pass is accountable for,
  counted together, because both come out of the same read". Its `cited` clause
  must say the citation may be on the entity **or** on one of its invariants.
- `rb-reconcile-outcomes`: `outcome_class`-kind, and the citation sits on an
  outcome class inside an `outcomes` record.
- `rb-reconcile-goals`: `actor`-kind and `goal`-kind, counted together.

- [ ] **Step 4: Add the §3 Method step to each of the four**

Append as the last numbered step in each `## 3. Method`:

```markdown
N. **Fill in one `inputs_seen` row as you finish each claims file, not at the
   end.** A row assembled at the end from what you remember is a recollection of
   having read, and the difference between those two things is exactly what this
   accounting exists to measure. Write the row while the file is in front of you:
   the count of its claims of your kind, how many you cited, and — if you dropped
   any — why, in one sentence. `manifest.json` names every input, so you know how
   many rows there will be before you open the first one.
```

Number it to follow that section's existing steps.

- [ ] **Step 5: Add the §4 Invariant to each of the four**

Append as the last numbered invariant:

```markdown
N. `inputs_seen` has one row per input in `manifest.json`, and in every row
   `cited + dropped == own_kind_total`. `rubrica check-refs` **recomputes** both
   `own_kind_total` (from `01-claims/`) and `cited` (from the `claims` arrays in
   this document), so neither is taken on your word: a count that does not match
   is a finding naming this file, and a missing row is a finding too. Nothing
   here judges *how much* you dropped — that is a human's reading at gate 1 —
   only that the arithmetic is true.
```

- [ ] **Step 6: Add the §5 refusal condition to each of the four**

Append to each `## 5. Refusal conditions`:

```markdown
- **A claims file you could not read.** Do not guess its `own_kind_total` to
  complete the accounting. A guessed count is a number nobody measured presented
  as one somebody did, and it defeats the whole point of the row: a row you
  filled in without opening the file is indistinguishable, in the artifact, from
  one you filled in after reading it. Say which file and what happened, and stop.
  A refusal here is recoverable; a fabricated count is not, because nothing
  downstream can tell it from a real one.
```

- [ ] **Step 7: Add the gap paragraph to `rb-reconcile-gaps` §2 and §4**

`rb-reconcile-gaps` gets **no** `inputs_seen`. In its `## 2. Output`, after the
existing description of a gap's fields:

```markdown
**Each gap also carries a `claims` array, and what it cites is not what you might
expect.** A gap records what no input contains, so its claims cannot be evidence
*for* the unknown — there is none, which is the point. They are the claims that
make the absence **matter**: the capability whose error behaviour nothing
describes, the goal that needs a hop no claim supports. That is the `why_it_matters`
field's evidence, made resolvable. Until this array existed a gap's evidence went
into prose, and a run was measured whose gate-1 brief reported an input at 0
claims cited while a gap in the same brief rested its argument on one of that
input's claims.
```

And as a §4 invariant:

```markdown
N. Every gap carries at least one `claims` entry, and every entry resolves to a
   claim id that exists in `01-claims/`. Layer 1 enforces the first
   (`claim_refs` carries `minItems: 1`); `refs.check_world_model` enforces the
   second, after the seal.
```

- [ ] **Step 8: Measure every predicate in both directions**

This is not optional and it is not the same as the tests passing. For each
assertion added in Step 1:

```bash
# Copy the skills tree somewhere writable and point the loader at it.
cp -r src/rubrica/skills /tmp/skills-probe
export RUBRICA_SKILLS_DIR=/tmp/skills-probe
```

1. **Red on deletion.** Delete or blank the paragraph the predicate claims to
   check, in the `/tmp` copy, and confirm the test fails. A predicate nobody has
   watched fail is not yet a guard.
2. **Green on a meaning-preserving reword.** Reword the same paragraph without
   changing what it says — reflow it, swap a clause order — and confirm the test
   still passes. The mirror failure is equally real here: a phrase pin in this
   repository broke on an innocuous reformat.

If a predicate cannot survive both, it is pinned to phrasing rather than to
meaning. Loosen the predicate to the co-occurring tokens that carry the rule, or
delete it — do not keep a predicate that only one wording satisfies.

Unset the override when you are done: `unset RUBRICA_SKILLS_DIR`.

- [ ] **Step 9: Run every gate**

```bash
make test
make check
uv run rubrica check-skills
```

`check-skills` must exit 0 with no contract change — if it objects, a `reads`,
`writes` or `schemas` list was edited by accident.

- [ ] **Step 10: Commit**

```bash
git add src/rubrica/skills/ tests/unit/test_skills_reconcile_family.py
git commit -S -s -m "$(cat <<'MSG'
docs: Give the reconcile passes the prose their accounting needs

Four sections in each of the four passes that own a claim kind: what inputs_seen
is and that it is total over manifest.inputs, that a row is filled in as each
claims file is finished rather than reconstructed at the end, that check-refs
recomputes both counts, and one new refusal condition -- a claims file that
could not be read is a refusal, not a guessed count.

That last one is the condition that can defeat the change: a pass which guesses
four numbers to satisfy the schema produces a clean artifact that means nothing,
and a guessed count is indistinguishable in the artifact from a measured one.

The existing "read every file, not one of them, all of them" prose is
deliberately untouched. It already names this exact failure mode and did not
prevent it, so the change belongs in the output shape rather than in a longer
exhortation.

rb-reconcile-gaps gets no accounting -- it owns no claim kind, and a gap asserts
absence, so no output shape can force its read coverage. What it gains is prose
for a gap's own claims: not evidence for the unknown, evidence that the absence
matters.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 6: gate 1's per-pass block, and the reference docs

**Files:**
- Modify: `src/rubrica/brief.py` (`_gate_1`)
- Modify: `docs/reference/artifacts.md`, `docs/reference/cli.md`
- Test: `tests/unit/test_brief.py`

**Interfaces:**
- Consumes: `refs.PASS_OWN_KINDS` from Task 4 — imported, never restated, for the
  reason `utilisation.py` exists as its own module: the gate and the report must
  never come to disagree about what the number means. It is public (no leading
  underscore) precisely so this import is not reaching into a private name.
- Produces: `_gate_1`'s output gains a `Read coverage, per pass` block. Still
  always exit 0 on a readable run.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_brief.py`:

```python
def test_gate_1_reports_read_coverage_per_pass(tmp_path):
    """The aggregate is what hid issue #6.

    Measured on run-20260823-112746: utilisation read 33.6% overall while
    per-kind citation ran 110/135 for the pass that read every claims file and
    2/38 for the pass that read three of twenty-three. The brief printed the
    average.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    text = brief.gate_brief(run, gate=1)
    assert "Read coverage, per pass" in text
    for stage in ("capabilities", "entities", "outcomes", "goals"):
        assert stage in text
    # The toy's one drop, with its note, is the line a human is meant to act on.
    assert "trace-json" in text
    assert "contradiction" in text


def test_gate_1_read_coverage_is_quiet_before_the_partials_exist(tmp_path):
    """Every report in this module renders on a run stopped anywhere.

    gate-brief is a report, not a gate: it exits 0 on a readable run, so a run
    with no partials yet must produce a line saying so rather than a traceback.
    """
    run = build_toy_run(tmp_path, upto="extract")
    text = brief.gate_brief(run, gate=1)
    assert "Read coverage, per pass" in text
    assert "nothing to report" in text
```

Check `tests/unit/test_brief.py` for the exact entry point it uses — `gate_brief`
versus `_gate_1` — and match it.

- [ ] **Step 2: Run it and confirm it fails**

```bash
uv run pytest tests/unit/test_brief.py -k read_coverage -v
```

Expected: FAIL on the missing heading.

- [ ] **Step 3: Implement the block**

In `src/rubrica/brief.py`, insert after the `Claim utilisation, per input` block
and before `Implied suite size`:

```python
    # Per pass, not per input. The utilisation block above is an aggregate across
    # every citing pass, and that is what hid issue #6: on run-20260823-112746 it
    # read 33.6% while the pass that had read every claims file was citing
    # 110/135 of its own kind and the pass that had read three of twenty-three
    # was citing 2/38. One diligent pass masks another's skipped file, because a
    # per-artifact number cannot say which pass did the citing.
    lines.append("Read coverage, per pass")
    rendered = False
    for attribute, own_kinds in refs.PASS_OWN_KINDS:
        part = _mapping(_quietly(getattr(run, attribute)))
        rows = _dicts(part.get("inputs_seen"))
        if not rows:
            continue
        rendered = True
        total = sum(r.get("own_kind_total", 0) for r in rows if isinstance(r.get("own_kind_total"), int))
        cited = sum(r.get("cited", 0) for r in rows if isinstance(r.get("cited"), int))
        lines.append(f"  {attribute}: {cited}/{total} claims of {', '.join(own_kinds)} cited")
        # Only the rows that dropped something, and always with the note. A
        # printed list of 0/0/0 rows would bury the one line a human is here to
        # rule on.
        for row in rows:
            if row.get("dropped"):
                note = row.get("note")
                lines.append(
                    f"    {row.get('artifact_id')}: {row.get('cited')}/"
                    f"{row.get('own_kind_total')} cited, {row.get('dropped')} dropped"
                    f" -- {note if isinstance(note, str) else '(no note)'}"
                )
    if not rendered:
        lines.append("  (no reconcile partials yet; nothing to report)")
    lines.append("")
```

Two things to get right:

- Import `PASS_OWN_KINDS` from `refs`; do not copy the four rows into `brief.py`.
  A second copy of the mapping is the drift `utilisation.py`'s module docstring
  exists to refuse, and this one would be a copy of a *judgment* — which pass is
  accountable for which claim kind — not of a constant.
- `_mapping`, `_dicts` and `_quietly` are this module's existing guards. Use them
  rather than raw `.get`: measured three times in this module, an unhashable or
  wrongly-typed member from a hand-edit at the gate raised out of a comprehension
  and surfaced as a fabricated `[internal]` finding at exit 1.

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/unit/test_brief.py -v
make test
```

- [ ] **Step 5: Confirm the report still exits 0 on a hostile run**

`gate-brief` is a report, not a gate: it always exits 0 on a readable run.

```bash
# a run whose partial is a directory where a file should be
uv run rubrica gate-brief --run <toy-run> --gate 1; echo "exit=$?"
rm <toy-run>/01-outcomes.json && mkdir <toy-run>/01-outcomes.json
uv run rubrica gate-brief --run <toy-run> --gate 1; echo "exit=$?"
# and one with a non-integer count
```

Expected: **exit 0** every time, with the block rendering whatever it can. An
exit 1 or 2 here is a contract violation, not a strictness improvement.

- [ ] **Step 6: Update the reference docs**

`docs/reference/artifacts.md`: document `inputs_seen` on the four partials, and
`claims` on invariant, outcome class and gap. Follow the file's existing
per-artifact structure. Do not write a count of anything that grows into a
heading, and do not cite the plan or spec — the token `superpowers` in this file
fails `test_only_the_docs_index_cites_recorded_history`.

`docs/reference/cli.md`: `gate-brief`'s gate-1 surface gains the per-pass block.
The existing sentence describes gate 1 as "the reconcile sweep plus utilisation
and implied size"; extend it. `tests/unit/test_docs_accuracy.py` fails until
`cli.md` and `cli.SUBCOMMANDS` agree.

- [ ] **Step 7: Run every gate**

```bash
make test
make check
uv run rubrica check-skills
```

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/brief.py docs/reference/ tests/unit/test_brief.py
git commit -S -s -m "$(cat <<'MSG'
feat: Read the per-pass coverage at the gate that can act on it

gate 1's utilisation block is an aggregate across every citing pass, and that is
what hid issue #6: on run-20260823-112746 it read 33.6% while the pass that had
read every claims file was citing 110 of 135 claims of its own kind and the pass
that had read three of twenty-three was citing 2 of 38. A per-artifact number
cannot say which pass did the citing, so one diligent pass masks another's
skipped file -- measured on the same run, trajectories-json-9 showed 13 claims
cited, every one a capability claim, while the goals pass never opened it.

The block prints each pass's own-kind rate and only the rows that dropped
something, with their notes: a list of 0/0/0 rows would bury the one line a
human is here to rule on. Still a report, still exit 0 on a readable run.

PASS_OWN_KINDS loses its underscore rather than being copied here, for the
reason utilisation.py is its own module: the gate and the report must not come
to disagree about what the number means.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

### Task 7: The register

**Files:**
- Modify: `docs/design/limitations.md`

**Interfaces:**
- Consumes: everything above; this task records what the change did *not* close.
- Produces: no code.

**Read the register before writing into it.** Most "bugs you just found" are
already in it with a ruling, and re-litigating one has cost this project two fix
rounds.

- [ ] **Step 1: Fold issue #6's measurement into the two variance entries**

`### One exercise is one sample` contains the sentence "Nobody has yet run the
same inputs twice and diffed the result." That premise **no longer holds for the
reconcile family** and the entry must say so — a reader who greps for the
measurement and finds the claim will conclude none exists. Add, inside that
entry, that the reconcile passes were re-dispatched over a byte-identical run
directory on `run-20260823-112746` (23 admitted inputs, 434 claims) and that the
result is issue #6's; keep the entry's ruling, which is about the *rest* of the
chain and still stands.

`### Two runs over the same inputs disagreed on claim count, and on which stages a
gap blocks` gains a sibling paragraph: the same-input pair also disagreed on
**read coverage** by nearly a factor of eight, with a 15-point utilisation swing
and no gate able to tell the two runs apart. Unlike the 2026-08-16 pair, this one
has **no prompt confound** — the skill was byte-identical — so it is the clean
measurement that entry says is still owed, for this family.

Do not delete either entry. Both rulings survive; what changes is a premise
inside them.

- [ ] **Step 2: Add the entry for the gaps pass**

New entry, in the group the other read-coverage and human-gate entries live in:

```markdown
### `rb-reconcile-gaps`' read coverage cannot be forced by any output shape

The four reconcile passes that own a claim kind each carry an `inputs_seen`
accounting whose `own_kind_total` is recomputed from `01-claims/`, so a pass
cannot state a count for a file it never opened. `rb-reconcile-gaps` has no such
accounting and cannot be given one: it owns none of the six claim kinds, and a
gap is an assertion about what no input **contains**. A pass that read three of
twenty-three claims files can write a well-formed, entirely plausible gap about
the other twenty's silence, and every mechanical check will pass — the gap
resolves, its `blocks` list is a legal subset, its `claims` cite real ids.

What it did gain is `claims` on `$defs/gap`, so the evidence that an absence
*matters* is resolvable rather than sitting in prose. That closes the
self-contradicting brief — a run was measured reporting an input at 0 claims
cited while a gap in the same brief rested on one of that input's claims — and it
does not touch read coverage.

**Why it is parked rather than fixed:** every candidate fix asserts something the
pass cannot know. A "claims considered" count would be a self-report, which is
prose about its own compliance. Requiring a gap per uncited claim would
manufacture gaps, which is the confabulation every refusal-conditions section in
this family exists to prevent. The honest instrument is the transcript:
`scripts/audit-reads.sh` over a real dispatch, which is the same answer the
isolation rule gets and for the same reason.

What this means for you: **a gap is the one world-model element whose evidence of
diligence is entirely outside the artifact.** If a run's gaps look thin, read the
transcript rather than the gaps.
```

- [ ] **Step 2b: Add the entry for the owed re-records**

```markdown
### Two committed recordings predate the requirement that every element cite a claim

`tests/fixtures/toy-contradiction/recorded/01-world-model.json` and
`tests/fixtures/toy-gap/recorded/01-world-model.json` are committed live model
output, and between them they carry outcome classes, invariants and gaps that
have no `claims` array — because none was required when they were recorded. They
do not fail: `tests/unit/test_refusals_live.py` reads them with `read_json` and
asserts on content, never against a schema, and `check-refs` against a bare
`recorded/` directory already exits 1 for want of a manifest.

So the gap is evidential, not red. The recordings are evidence of what the skill
did at one commit, which is what a recording is for, and they now describe a
world model shape the schema no longer accepts.

**Why it is parked:** re-recording is a dispatch, and hand-writing `claims`
arrays into committed model output would fabricate the only behavioural evidence
this project has. A reasoned number presented as an observed one has shipped here
once and had to be retracted; a reasoned *citation* is the same defect with a
longer reach, because a later reader would take it as a measurement of what a
pass chose to cite.

What this means for you: **do not read those two files as examples of current
schema shape.** They are records of a dispatch, and the re-record is owed
whenever one of these skills is next dispatched for real.
```

- [ ] **Step 3: Check the register's own drift rules**

The register replaces a decayed pointer with a greppable name rather than a fresh
pointer of the same kind: no line numbers in anything you add, and no count of
something that grows. Both new entries above follow that — check yours does too
if you reword them.

- [ ] **Step 4: Run the gates**

```bash
make test
make check
```

`test_docs_accuracy.py` checks `limitations.md` for a hand-typed test count, a
heading that counts something growing, and a citation of the recorded-history
tree. All three are easy to trip in a long entry.

- [ ] **Step 5: Commit**

```bash
git add docs/design/limitations.md
git commit -S -s -m "$(cat <<'MSG'
docs: Record what forced read coverage did not close

Issue #6 is the clean same-input variance measurement two entries here say is
still owed -- byte-identical run directory, byte-identical skill, no prompt
confound -- so both entries lose a premise and keep their ruling. "Nobody has
yet run the same inputs twice and diffed the result" is no longer true of the
reconcile family, and a reader who greps for the measurement should find it
rather than conclude none exists.

Two new entries. rb-reconcile-gaps' read coverage cannot be forced by any output
shape, because it owns no claim kind and a gap asserts absence: a pass that read
three of twenty-three files can write a well-formed gap about the other
twenty's silence and pass every mechanical check. And the two committed
recordings now predate the requirement that every element cite a claim -- an
evidential debt rather than a red gate, parked because hand-writing citations
into committed model output would fabricate the only behavioural evidence this
project has.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
)"
```

---

## After the plan: what is still owed, and is not a task here

**The dispatch.** `make test` green proves the instrument is wired, not that it
works. The premise — that an output obligation changes read behaviour where an
exhortation did not — rests on one measurement nobody has taken:
`rb-reconcile-goals` dispatched against the reservation-service run with
`inputs_seen` in place, read coverage taken from the transcript with
`scripts/audit-reads.sh`, against its measured 3/23 and 9/23.

Falsification is a pass that satisfies `inputs_seen` and still reads three files,
by guessing counts or reading each file's first bytes. Both are visible in the
transcript and neither is visible in the artifact. Record the result in that
pass's `exercise.md` — no `reconcile-*` pass has one — and **state what happened
rather than what was expected.**

Run it with `scripts/dispatch-stage.sh reconcile-goals <run>`, then
`scripts/audit-reads.sh <transcript>`. Cap parallel dispatches at three: the
shared gateway degrades under concurrent streaming requests that each generate
substantial output, and the symptom is a retry logged with no HTTP status rather
than a 429.

**Not in this plan, by ruling:** the distinct `layer` for fan-out-incomplete
findings (issue #6's suggestion 2 — a real three-line fix, independent of this
one), any percentage floor on utilisation, and strengthening the "read all of
them" prose.
