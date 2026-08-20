# Staged Reconcile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace rubrica's single `reconcile` dispatch with a sequence of bounded
passes closed by a code seal, so no dispatch has to think for five minutes before
emitting its first byte.

**Architecture:** Six prompt passes each write one *partial* into the `01-` band;
a code stage (`reconcile-seal`) assembles them into the unchanged
`01-world-model.json` and computes the coverage denominator. Every pass still
reads all of `01-claims/`, so the barrier property is untouched — the split is on
output, not on claims. Partial schemas `$ref` the element definitions already in
`world-model-0.1.json` rather than restating them.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `jsonschema` 4.26 with `referencing`
registries, `ruff` (line-length 100, `select = ["E","F","I","UP","B","SIM"]`).

**Spec:** [`docs/superpowers/specs/2026-08-19-staged-reconcile-design.md`](../specs/2026-08-19-staged-reconcile-design.md)

## Global Constraints

- **Every commit is signed and DCO'd: `git commit -S -s`.** Both flags. If signing
  fails, **stop and report it** — never fall back to unsigned, never work around it.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`.
  **Never** `Co-Authored-By` or `Made-with`.
- The three gates that must be green before any commit: `make test`, `make check`,
  and `uv run rubrica check-skills` exiting 0.
- **Never write a test count into any document.**
- **Exit-code contract, load-bearing:** `0` clean; `1` findings, one per line on
  **stdout**; `2` usage error or an unreadable/misconfigured run. A stage defect
  must never surface as `2`. A `1` must never have empty stdout.
- `ruff` formats Python code blocks inside Markdown, so `docs/` is excluded — but
  `README.md` and `CLAUDE.md` are **not**. Run `make check` after editing either.
- Comment density in this repo is high and deliberate: comments explain *why*,
  usually citing a measurement. Match it; do not strip existing comments.
- Artifact ids in schemas anchor with `\A` and `\Z`, never `^`/`$`. Copy that
  idiom in any new pattern.
- Never hand-edit `docs/concepts/pipeline-diagram.html`, `docs/assets/how-it-works.svg`
  or `docs/assets/how-it-works-dark.svg`. Edit the renderer's table and re-render.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `src/rubrica/schema/subjects-0.1.json` | the claim subject cover |
| `src/rubrica/schema/contradictions-part-0.1.json` | one subject's contradictions |
| `src/rubrica/schema/capabilities-part-0.1.json` | capabilities without outcome classes |
| `src/rubrica/schema/outcomes-part-0.1.json` | outcome classes keyed by capability id |
| `src/rubrica/schema/entities-part-0.1.json` | entities with invariants and relations |
| `src/rubrica/schema/goals-part-0.1.json` | actors and goals |
| `src/rubrica/schema/gaps-part-0.1.json` | gaps |
| `src/rubrica/reconcile.py` | the seal: assemble partials, compute the denominator |
| `src/rubrica/skills/rb-reconcile-subjects/SKILL.md` | the subject cover pass |
| `src/rubrica/skills/rb-reconcile-contradict/SKILL.md` | contradictions, fan-out per subject |
| `src/rubrica/skills/rb-reconcile-capabilities/SKILL.md` | capabilities and bindings |
| `src/rubrica/skills/rb-reconcile-outcomes/SKILL.md` | outcome classes per capability |
| `src/rubrica/skills/rb-reconcile-entities/SKILL.md` | entities, invariants, relations |
| `src/rubrica/skills/rb-reconcile-goals/SKILL.md` | actors and goals |
| `src/rubrica/skills/rb-reconcile-gaps/SKILL.md` | gaps, and the cross-pass audit |
| `src/rubrica/skills/rb-reconcile/SUPERSEDED.md` | what the surviving directory holds and why |
| `tests/unit/test_reconcile_seal.py` | the seal, including the round-trip property |
| `tests/unit/test_refs_reconcile_parts.py` | the three new layer-2 checkers |
| `tests/unit/test_schema_part_sharing.py` | partial schemas stay in step with world-model's `$defs` |

**Modified:**

| Path | Change |
|---|---|
| `src/rubrica/validate.py` | a `referencing` registry so cross-file `$ref` resolves; new kinds; new `_artifact_paths` arms |
| `src/rubrica/schema/world-model-0.1.json` | extract `outcome_class`, `param`, `binding` into `$defs` |
| `src/rubrica/paths.py` | `STAGES`; seven new `RunPaths` members |
| `src/rubrica/refs.py` | three checkers, `_readable_targets`, `check_all` |
| `src/rubrica/cli.py` | `reconcile-seal` subcommand |
| `src/rubrica/skills.py` | `CODE_ONLY_STAGES` gains `reconcile-seal` |
| `src/rubrica/brief.py` | gate 1 gains the cover, the per-subject tally, the unresolved count |
| `src/rubrica/skills/rb-orchestrate/SKILL.md` | dispatches the new sequence, three at a time |
| `scripts/render-readme-diagram.py` | fold a prefix family into one starred line |
| `scripts/render-pipeline-diagram.py` | one `ROWS` entry per new stage |
| `tests/toy.py` | `split_world_model`, partial checkpoints |
| `docs/concepts/pipeline.md`, `docs/reference/cli.md`, `docs/reference/artifacts.md`, `docs/concepts/glossary.md`, `docs/concepts/artifact-contract.md`, `docs/guides/running-a-stage-by-hand.md`, `docs/getting-started.md`, `docs/design/limitations.md`, `CLAUDE.md` | the stage is a sequence now |

**Deleted:** `src/rubrica/skills/rb-reconcile/SKILL.md` only. **`src/rubrica/skills/rb-reconcile/exercise.md` is preserved in place** — see Task 7.

**Sequencing rationale.** Tasks 1–6 add code and tests without touching
`paths.STAGES`, so the tree stays green and coherent throughout: schemas, paths,
the seal and the checkers all exist and are tested before anything about the
pipeline's shape changes. Task 7 is the one atomic flip, and by then everything
it needs is already proven. That ordering is deliberate — `check-skills` enforces
a 1:1 bijection between stage name and skill directory, and this repo has already
learned that a partial rename makes it reject every correctly named skill.

---

### Task 1: Cross-file `$ref` resolution in `validate.py`

The partial schemas must reuse `world-model-0.1.json`'s `$defs` rather than
restate them. Today `_validator_for` builds `Draft202012Validator(schema)` with no
registry, so a `$ref` into another file would attempt network resolution. Every
schema already carries an `$id` equal to its filename, which is what makes a
filename-keyed registry work.

**Files:**
- Modify: `src/rubrica/validate.py:132-144` (`_validator_for`)
- Test: `tests/unit/test_validate_registry.py` (create)

**Interfaces:**
- Consumes: `validate.schema_dir()`, `validate.ARTIFACT_SCHEMAS`, `artifacts.read_json`
- Produces: `validate._schema_registry(schema_root: Path) -> referencing.Registry`,
  and `_validator_for(kind: str, schema_root: Path)` now resolving cross-file
  `$ref`. No signature changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_validate_registry.py
"""Cross-file $ref resolution, which every partial schema depends on.

Measured before this existed: a $ref of "world-model-0.1.json#/$defs/entity"
raised referencing.exceptions.Unresolvable, which is neither an ArtifactError nor
an OSError, so cli.py's catch-all turned a schema wiring mistake into an exit-1
[internal] finding blaming the artifact.
"""

from __future__ import annotations

import json

import pytest

from rubrica import validate
from rubrica.artifacts import ArtifactError

PART = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "probe-part-0.1.json",
    "type": "object",
    "required": ["schema_version", "entities"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "0.1"},
        "entities": {
            "type": "array",
            "items": {"$ref": "world-model-0.1.json#/$defs/entity"},
        },
    },
}


@pytest.fixture
def probe_schema_dir(tmp_path, monkeypatch):
    """A schema dir holding the real world model schema plus one probe that
    $refs into it, so the test exercises the shipped $defs rather than a copy."""
    for name in ("world-model-0.1.json", "manifest-0.1.json"):
        (tmp_path / name).write_text(
            (validate.schema_dir() / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / "probe-part-0.1.json").write_text(json.dumps(PART), encoding="utf-8")
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    monkeypatch.setitem(validate.ARTIFACT_SCHEMAS, "probe-part", "probe-part-0.1.json")
    return tmp_path


def test_a_cross_file_ref_resolves_against_the_schema_directory(probe_schema_dir, tmp_path):
    from tests.toy import toy_world_model

    doc = tmp_path / "probe.json"
    doc.write_text(
        json.dumps({"schema_version": "0.1", "entities": toy_world_model()["entities"]}),
        encoding="utf-8",
    )
    assert validate.validate_artifact(doc, "probe-part") == []


def test_a_cross_file_ref_still_rejects_a_bad_element(probe_schema_dir, tmp_path):
    """The mirror direction. A registry that resolved to an empty schema would
    make every document valid, which the passing test above cannot distinguish."""
    doc = tmp_path / "probe.json"
    doc.write_text(
        json.dumps({"schema_version": "0.1", "entities": [{"id": "ent-x"}]}), encoding="utf-8"
    )
    findings = validate.validate_artifact(doc, "probe-part")
    assert findings, "a truncated entity must fail against world-model's $defs/entity"
    assert any("required" in f.message for f in findings)


def test_an_unreadable_schema_file_is_not_a_stage_defect(tmp_path, monkeypatch):
    """`chmod 000` on a schema the registry globs. The registry reads *every*
    schema in the directory rather than only the one being compiled, so it widens
    the surface on which a filesystem problem can occur -- and a filesystem problem
    must stay exit 2. An OSError escaping as an exit-1 finding would tell the
    orchestrator to repair an artifact that is fine, which is the family this
    repo kept rediscovering.
    """
    import os
    import stat

    for name in ("world-model-0.1.json", "manifest-0.1.json"):
        (tmp_path / name).write_text(
            (validate.schema_dir() / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    target = tmp_path / "world-model-0.1.json"
    os.chmod(target, 0)
    try:
        if os.access(target, os.R_OK):  # pragma: no cover - running as root
            pytest.skip("cannot make a file unreadable as this user")
        doc = tmp_path / "probe.json"
        doc.write_text("{}", encoding="utf-8")
        with pytest.raises((OSError, ArtifactError)):
            validate.validate_artifact(doc, "world-model")
    finally:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)


def test_an_unreadable_schema_directory_is_not_a_stage_defect(tmp_path, monkeypatch):
    """RUBRICA_SCHEMA_DIR pointing somewhere with no schemas must raise
    ArtifactError, which cli.py maps to exit 2. A registry built by globbing an
    empty directory must not silently produce a validator that passes everything.
    """
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    doc = tmp_path / "probe.json"
    doc.write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactError):
        validate.validate_artifact(doc, "world-model")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_registry.py -v`
Expected: the two `$ref` tests FAIL with a `referencing.exceptions.Unresolvable`
(or `RefResolutionError`) naming `world-model-0.1.json`. The two unreadable-input
tests should already PASS — they pin existing behaviour that must survive, and
they are here because `validate.py` is one of the modules whose unreadable paths
must be tested rather than only its happy path.

- [ ] **Step 3: Add the registry**

In `src/rubrica/validate.py`, add to the imports:

```python
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
```

Then insert above `_validator_for` and change that function's last line:

```python
@functools.cache
def _schema_registry(schema_root: Path) -> Registry:
    """Every schema in `schema_root`, keyed by filename, for cross-file `$ref`.

    The partial schemas the reconcile passes write are made of the *same*
    elements as the world model -- a capability, an entity, a gap -- so they
    `$ref` `world-model-0.1.json#/$defs/...` rather than restate the definitions.
    Restating them is the drift this package already refuses elsewhere ("derive,
    do not restate"), and a duplicated `$defs/entity` that fell behind would make
    a partial accept an element the assembled world model then rejects.

    Keyed on schema_root for the same reason _validator_for is: a plain
    zero-argument cache would pin the first directory it ever saw, so a test
    overriding RUBRICA_SCHEMA_DIR would validate against the old one.

    Registered by filename rather than relying on each schema's `$id` alone,
    even though every shipped schema carries one equal to its filename: a new
    schema that forgets `$id` then still resolves, instead of failing only for
    the file that refs it.
    """
    return Registry().with_resources(
        [
            (
                path.name,
                Resource.from_contents(read_json(path), default_specification=DRAFT202012),
            )
            for path in sorted(schema_root.glob("*.json"))
        ]
    )
```

and in `_validator_for`, replace the final `return Draft202012Validator(schema)` with:

```python
    return Draft202012Validator(schema, registry=_schema_registry(schema_root))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_registry.py -v`
Expected: all three PASS.

- [ ] **Step 5: Run the full suite and the gates**

Run: `make test && make check && uv run rubrica check-skills; echo "check-skills:$?"`
Expected: tests pass, ruff clean, `check-skills:0`. The registry changes no
existing schema's meaning, so nothing else should move.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/validate.py tests/unit/test_validate_registry.py
git commit -S -s -m "feat: Resolve cross-file schema refs through a referencing registry

The reconcile partials are made of the same elements as the world model -- a
capability, an entity, a gap -- so their schemas ref world-model-0.1.json's
\$defs rather than restate them. _validator_for built a validator with no
registry, so such a ref attempted network resolution and raised Unresolvable,
which is neither ArtifactError nor OSError: cli.py's catch-all would have
turned a schema wiring mistake into an exit-1 finding blaming the artifact.

Keyed on schema_root like _validator_for and _manifest_stage_efforts, so a
RUBRICA_SCHEMA_DIR override is not served a validator built from the old root.
Registered by filename rather than trusting each schema's \$id, so a new schema
that forgets one still resolves.

Both directions measured: the golden entities validate through the ref, and a
truncated entity still fails -- a registry resolving to an empty schema would
pass the first test and fail the second.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: Partial schemas, artifact kinds, and run paths

Seven new artifact kinds. Six of them `$ref` a whole element definition that
already exists. Two need small, semantics-preserving extractions in
`world-model-0.1.json` first, and one — `capabilities-part` — carries a bounded
duplication that a test pins, because JSON Schema cannot express
"`$defs/capability` minus one property" while `additionalProperties: false` holds.

**Files:**
- Modify: `src/rubrica/schema/world-model-0.1.json` (extract three `$defs`)
- Create: `src/rubrica/schema/subjects-0.1.json`, `contradictions-part-0.1.json`,
  `capabilities-part-0.1.json`, `outcomes-part-0.1.json`,
  `entities-part-0.1.json`, `goals-part-0.1.json`, `gaps-part-0.1.json`
- Modify: `src/rubrica/validate.py` (`ARTIFACT_SCHEMAS`, `_artifact_paths`)
- Modify: `src/rubrica/paths.py` (new `RunPaths` members)
- Test: `tests/unit/test_schema_part_sharing.py` (create)

**Interfaces:**
- Produces, on `RunPaths`: `subjects`, `contradictions_dir`,
  `contradiction_part(subject_id: str) -> Path`, `subject_part_ids() -> list[str]`,
  `capabilities_part`, `outcomes_part`, `entities_part`, `goals_part`, `gaps_part`
  — all `Path`-valued properties except the two named as callables.
- Produces, in `validate.ARTIFACT_SCHEMAS`: kinds `subjects`,
  `contradictions-part`, `capabilities-part`, `outcomes-part`, `entities-part`,
  `goals-part`, `gaps-part`.
- Consumes: `paths.safe_segment`, `paths.list_json`, Task 1's registry.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_schema_part_sharing.py
"""The partial schemas share the world model's element definitions.

Two properties, and the second is the one with teeth. Sharing by `$ref` is
checkable by construction -- if the ref broke, validation would raise. What is
*not* checkable by construction is capabilities-part, which cannot `$ref`
`$defs/capability`: that definition requires `outcome_classes`, which a separate
pass writes, and `additionalProperties: false` makes "the same object minus one
property" inexpressible as an allOf. So its property set is restated, and this
module is what keeps the restatement honest.
"""

from __future__ import annotations

import json

import pytest

from rubrica import validate
from tests.toy import toy_world_model


def _schema(name: str) -> dict:
    return json.loads((validate.schema_dir() / name).read_text(encoding="utf-8"))


PARTS_REFERENCING_WORLD_MODEL = [
    ("contradictions-part-0.1.json", "contradiction"),
    ("entities-part-0.1.json", "entity"),
    ("gaps-part-0.1.json", "gap"),
    ("goals-part-0.1.json", "goal"),
    ("goals-part-0.1.json", "actor"),
    ("outcomes-part-0.1.json", "outcome_class"),
]


@pytest.mark.parametrize("filename,definition", PARTS_REFERENCING_WORLD_MODEL)
def test_a_partial_refs_the_world_model_definition_rather_than_copying_it(filename, definition):
    text = (validate.schema_dir() / filename).read_text(encoding="utf-8")
    assert f"world-model-0.1.json#/$defs/{definition}" in text, (
        f"{filename} must reuse world-model-0.1.json#/$defs/{definition}, not restate it"
    )
    assert f'"{definition}":' not in json.dumps(_schema(filename).get("$defs", {})), (
        f"{filename} defines its own {definition!r}; that is the drift the $ref avoids"
    )


def test_capabilities_part_carries_exactly_the_capability_minus_outcome_classes():
    """The restatement this file exists for. Measured red by adding a property to
    world-model's $defs/capability and not to the partial, and by the reverse."""
    world = _schema("world-model-0.1.json")["$defs"]["capability"]
    part = _schema("capabilities-part-0.1.json")["$defs"]["capability_core"]

    assert set(part["properties"]) == set(world["properties"]) - {"outcome_classes"}, (
        "capabilities-part's capability_core has drifted from world-model's $defs/capability"
    )
    assert set(part["required"]) == set(world["required"]) - {"outcome_classes"}, (
        "capabilities-part's required list has drifted from world-model's $defs/capability"
    )
    assert part["additionalProperties"] is False


def test_every_extracted_definition_is_actually_referenced_by_the_capability():
    """The extractions must be wiring, not dead copies left beside the inline
    shapes they replaced -- which would validate identically and drift silently."""
    world = _schema("world-model-0.1.json")
    capability = json.dumps(world["$defs"]["capability"])
    for definition in ("outcome_class", "param", "binding"):
        assert definition in world["$defs"], f"world-model-0.1.json has no $defs/{definition}"
        assert f"#/$defs/{definition}" in capability, (
            f"$defs/capability does not reference $defs/{definition}; the extraction left the "
            "inline shape in place"
        )


def test_the_golden_world_model_still_validates_after_the_extractions(tmp_path):
    """Extracting an inline subschema into $defs must change nothing about what
    the world model accepts."""
    doc = tmp_path / "01-world-model.json"
    doc.write_text(json.dumps(toy_world_model()), encoding="utf-8")
    assert validate.validate_artifact(doc, "world-model") == []


def test_a_bad_outcome_class_still_fails_after_the_extraction(tmp_path):
    """The mirror direction: an extraction that produced an empty $defs/outcome_class
    would pass the test above and check nothing."""
    world = toy_world_model()
    world["capabilities"][0]["outcome_classes"][0]["kind"] = "not-a-real-kind"
    doc = tmp_path / "01-world-model.json"
    doc.write_text(json.dumps(world), encoding="utf-8")
    assert validate.validate_artifact(doc, "world-model") != []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_schema_part_sharing.py -v`
Expected: FAIL — the partial schema files do not exist, and
`world-model-0.1.json` has no `$defs/outcome_class`. The two golden-world-model
tests should PASS already, pinning behaviour that must survive Step 3.

- [ ] **Step 3a: Extract three definitions in `world-model-0.1.json`**

Move the three inline subschemas out of `$defs/capability` into `$defs`, replacing
each with a `$ref`. Copy the existing objects verbatim — do not retype them, and
keep the `binding` description, which records why `emit` needs it.

Add to `$defs` (alphabetical, matching the file's existing order):

```json
"binding": {
  "type": "object",
  "description": "How this capability is invoked on the target: the tool name a transcript will show, plus the arguments that identify this capability rather than a sibling sharing the tool. Optional in the schema and required by emit, which reports a finding for an accepted scenario whose capability has none.",
  "required": ["tool", "fixed_args"],
  "additionalProperties": false,
  "properties": {
    "tool": {"type": "string", "minLength": 1},
    "fixed_args": {"type": "object"}
  }
},
"outcome_class": {
  "type": "object",
  "required": ["id", "kind", "description"],
  "additionalProperties": false,
  "properties": {
    "id": {"$ref": "#/$defs/id"},
    "kind": {"enum": ["success", "empty", "not_found", "error", "underspecified"]},
    "description": {"type": "string", "minLength": 1}
  }
},
"param": {
  "type": "object",
  "required": ["name", "type", "required"],
  "additionalProperties": false,
  "properties": {
    "name": {"type": "string", "minLength": 1},
    "type": {"type": "string", "minLength": 1},
    "required": {"type": "boolean"}
  }
}
```

Then in `$defs/capability`, replace the three inline shapes:

```json
"binding": {"$ref": "#/$defs/binding"},
"params": {"type": "array", "items": {"$ref": "#/$defs/param"}},
"outcome_classes": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/outcome_class"}}
```

- [ ] **Step 3b: Create the seven partial schemas**

`src/rubrica/schema/subjects-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "subjects-0.1.json",
  "title": "The claim subject cover",
  "description": "Every claim in 01-claims/, assigned to one or more subjects. A cover rather than a partition: a claim may appear under several subjects, and rb-reconcile-subjects is instructed to over-assign when the subject is unclear, because over-assignment is the safe direction. refs.check_subjects holds it to totality -- every claim id in the run appears here -- which is the property a heuristic pair filter could never have had.",
  "type": "object",
  "required": ["schema_version", "subjects"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "subjects": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "label", "claims"],
        "additionalProperties": false,
        "properties": {
          "id": {"$ref": "world-model-0.1.json#/$defs/id"},
          "label": {"type": "string", "minLength": 1},
          "note": {"type": "string", "minLength": 1},
          "claims": {"$ref": "world-model-0.1.json#/$defs/claim_refs"}
        }
      }
    }
  }
}
```

`src/rubrica/schema/contradictions-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "contradictions-part-0.1.json",
  "title": "One subject's contradictions",
  "description": "What one rb-reconcile-contradict fan-out member found within its own subject, across every input file. An empty contradictions array is a real record -- it says this member swept this subject and found no disagreement -- which is why the array has no minItems and why refs.check_contradiction_parts requires a file per subject rather than a non-empty one.",
  "type": "object",
  "required": ["schema_version", "subject_id", "contradictions"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "subject_id": {"$ref": "world-model-0.1.json#/$defs/id"},
    "contradictions": {
      "type": "array",
      "items": {"$ref": "world-model-0.1.json#/$defs/contradiction"}
    }
  }
}
```

`src/rubrica/schema/capabilities-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "capabilities-part-0.1.json",
  "title": "Capabilities, before their outcome classes",
  "description": "What rb-reconcile-capabilities declares: each capability's identity, params and binding, with no outcome classes -- those are rb-reconcile-outcomes' output, quantified over this list, and reconcile-seal folds them in. capability_core restates $defs/capability's property set minus outcome_classes because JSON Schema cannot express that subtraction while additionalProperties is false; tests/unit/test_schema_part_sharing.py pins the two in step.",
  "type": "object",
  "required": ["schema_version", "capabilities"],
  "additionalProperties": false,
  "$defs": {
    "capability_core": {
      "type": "object",
      "required": ["id", "operation", "params", "claims", "confidence"],
      "additionalProperties": false,
      "properties": {
        "id": {"$ref": "world-model-0.1.json#/$defs/id"},
        "operation": {"type": "string", "minLength": 1},
        "binding": {"$ref": "world-model-0.1.json#/$defs/binding"},
        "params": {
          "type": "array",
          "items": {"$ref": "world-model-0.1.json#/$defs/param"}
        },
        "claims": {"$ref": "world-model-0.1.json#/$defs/claim_refs"},
        "confidence": {"enum": ["high", "medium", "low"]}
      }
    }
  },
  "properties": {
    "schema_version": {"const": "0.1"},
    "capabilities": {
      "type": "array",
      "minItems": 1,
      "items": {"$ref": "#/$defs/capability_core"}
    }
  }
}
```

`src/rubrica/schema/outcomes-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "outcomes-part-0.1.json",
  "title": "Outcome classes, keyed by capability",
  "description": "A join table, not a collection: outcome_classes is nested inside the capability object in the world model, so this pass cannot write a sibling array and reconcile-seal folds each entry into its capability. Keeping it a separate pass makes the capability list a file rather than a memory of having just written one -- the quantification the 45% measurement in rb-reconcile's method step 4 rests on.",
  "type": "object",
  "required": ["schema_version", "outcomes"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "outcomes": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["capability_id", "outcome_classes"],
        "additionalProperties": false,
        "properties": {
          "capability_id": {"$ref": "world-model-0.1.json#/$defs/id"},
          "outcome_classes": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "world-model-0.1.json#/$defs/outcome_class"}
          }
        }
      }
    }
  }
}
```

`src/rubrica/schema/entities-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "entities-part-0.1.json",
  "title": "Entities, with their invariants and relations",
  "description": "rb-reconcile-entities' output, quantified over the capabilities already declared in 01-capabilities.json: if a claim spells out the shape a capability returns, that shape becomes an entity here.",
  "type": "object",
  "required": ["schema_version", "entities"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "entities": {
      "type": "array",
      "items": {"$ref": "world-model-0.1.json#/$defs/entity"}
    }
  }
}
```

`src/rubrica/schema/goals-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "goals-part-0.1.json",
  "title": "Actors, and the goals they hold",
  "description": "Its own pass rather than folded into entities because goals are half the frozen denominator: reconcile-seal counts them, rb-propose designs against exactly this list, and a later stage may only request an amendment. Actors travel with goals because every goal needs a real actor_id to resolve.",
  "type": "object",
  "required": ["schema_version", "actors", "goals"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "actors": {
      "type": "array",
      "items": {"$ref": "world-model-0.1.json#/$defs/actor"}
    },
    "goals": {
      "type": "array",
      "items": {"$ref": "world-model-0.1.json#/$defs/goal"}
    }
  }
}
```

`src/rubrica/schema/gaps-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "gaps-part-0.1.json",
  "title": "Gaps, and the cross-pass audit",
  "description": "Last of the prompt passes on purpose: it reads every prior partial as well as every claim, because the refusal conditions of every pass before it resolve to 'record a gap instead', so the pass that writes gaps is the one positioned to audit what its predecessors declared. An empty gaps array is legal and is a strong claim -- a world model with no gaps, built from claims that leave things unstated, has erased the silence rather than recorded it.",
  "type": "object",
  "required": ["schema_version", "gaps"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "gaps": {
      "type": "array",
      "items": {"$ref": "world-model-0.1.json#/$defs/gap"}
    }
  }
}
```

- [ ] **Step 3c: Register the kinds in `validate.py`**

In `ARTIFACT_SCHEMAS`, after the `"triage"` entry and before the config-kinds
comment block, add:

```python
    # The reconcile partials. Each is one pass's slice of what was once a single
    # world model, and every one of them $refs world-model-0.1.json's $defs
    # rather than restating an element definition.
    "subjects": "subjects-0.1.json",
    "contradictions-part": "contradictions-part-0.1.json",
    "capabilities-part": "capabilities-part-0.1.json",
    "outcomes-part": "outcomes-part-0.1.json",
    "entities-part": "entities-part-0.1.json",
    "goals-part": "goals-part-0.1.json",
    "gaps-part": "gaps-part-0.1.json",
```

In `_artifact_paths`, add these arms before the final `raise KeyError`. Note the
two shapes: a singleton reports itself when absent so the finding names the file
(the `catalogue` reasoning), while the fan-out directory globs.

```python
    if kind == "subjects":
        # Returned even when absent, like catalogue: read_json's ArtifactError
        # names the path, so a pass that wrote nothing fails its own gate by name
        # rather than passing trivially.
        return [run.subjects]
    if kind == "contradictions-part":
        return list_json(run.contradictions_dir)
    if kind == "capabilities-part":
        return [run.capabilities_part]
    if kind == "outcomes-part":
        return [run.outcomes_part]
    if kind == "entities-part":
        return [run.entities_part]
    if kind == "goals-part":
        return [run.goals_part]
    if kind == "gaps-part":
        return [run.gaps_part]
```

- [ ] **Step 3d: Add the `RunPaths` members in `paths.py`**

In the singleton-artifacts block, after `claims_dir` and before `world_model`:

```python
    @property
    def subjects(self) -> Path:
        """The claim subject cover: every claim, assigned to one or more subjects.

        In the 01 family with the rest of world-model construction, because that
        is what the band means -- the numbering stays intake's, and everything
        between 01-claims/ and 01-world-model.json is one logical step engineered
        as substeps.
        """
        return self.root / "01-subjects.json"

    @property
    def contradictions_dir(self) -> Path:
        return self.root / "01-contradictions"

    @property
    def capabilities_part(self) -> Path:
        return self.root / "01-capabilities.json"

    @property
    def outcomes_part(self) -> Path:
        return self.root / "01-outcomes.json"

    @property
    def entities_part(self) -> Path:
        return self.root / "01-entities.json"

    @property
    def goals_part(self) -> Path:
        return self.root / "01-goals.json"

    @property
    def gaps_part(self) -> Path:
        return self.root / "01-gaps.json"
```

In the per-id block, beside `claims`:

```python
    def contradiction_part(self, subject_id: str) -> Path:
        return self.contradictions_dir / f"{safe_segment(subject_id)}.json"

    def subject_part_ids(self) -> list[str]:
        """Subject ids that have a contradictions part on disk, from the filenames.

        Derived from the directory rather than from 01-subjects.json on purpose:
        this is what the fan-out actually produced, and comparing it against the
        cover is exactly the check refs.check_contradiction_parts performs. A
        helper that read the cover instead could never report a part nobody
        asked for.
        """
        return [path.stem for path in list_json(self.contradictions_dir)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_schema_part_sharing.py tests/unit/test_validate_registry.py -v`
Expected: all PASS.

- [ ] **Step 5: Confirm the new kinds are wired both ways**

Run:
```bash
uv run python -c "
from rubrica import validate
for kind in ('subjects','contradictions-part','capabilities-part','outcomes-part','entities-part','goals-part','gaps-part'):
    validate._validator_for(kind, validate.schema_dir())
    print('compiled', kind)
"
```
Expected: seven `compiled ...` lines and no exception — every partial schema is a
valid Draft 2020-12 schema whose refs resolve.

- [ ] **Step 6: Run the gates**

Run: `make test && make check && uv run rubrica check-skills; echo "check-skills:$?"`
Expected: green. `test_docs_accuracy.py::test_every_artifact_kind_is_documented`
**will fail** — it holds `ARTIFACT_SCHEMAS` to `docs/reference/artifacts.md`. That
failure is the guard working. Document the seven kinds now, in the same commit:
add a short section per kind to `docs/reference/artifacts.md` naming, for each,
which stage writes it, which read it, and its fields. Then re-run.

- [ ] **Step 7: Commit**

```bash
git add src/rubrica/schema src/rubrica/validate.py src/rubrica/paths.py \
        tests/unit/test_schema_part_sharing.py docs/reference/artifacts.md
git commit -S -s -m "feat: Add the reconcile partial artifact kinds and their paths

Seven kinds, one per pass of the staged reconcile. Six ref a whole element
definition that already exists in world-model-0.1.json; three inline subschemas
(outcome_class, param, binding) are extracted into \$defs so they can be, which
changes nothing about what the world model accepts -- pinned in both directions
by revalidating the golden world model and by breaking an outcome class.

capabilities-part is the exception and carries a restatement: it needs
\$defs/capability minus outcome_classes, which a separate pass writes, and JSON
Schema cannot express that subtraction while additionalProperties is false. A
test holds its property and required sets to the world model's, so the
restatement cannot drift silently.

Singleton partials report themselves when absent, following catalogue's
reasoning: read_json names the path, so a pass that wrote nothing fails its own
gate by name instead of passing trivially.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: Cut the golden world model into partials, in one place

`tests/fixtures/toy/` is the model answer a skill imitates, so a defect there
teaches a skill the wrong thing. A second, hand-authored copy of that answer in
partial form would be a second answer to keep correct. Derive instead — which also
turns the seal into a checkable property rather than a hand-checked example.

**Files:**
- Modify: `tests/toy.py` (add `split_world_model`, extend `_UPTO_STAGES` usage is Task 7's)
- Test: `tests/unit/test_toy_split.py` (create)

**Interfaces:**
- Produces: `toy.split_world_model(world: dict | None = None, *, claim_ids: Iterable[str] | None = None) -> dict[str, Any]`
  returning keys `subjects`, `contradictions` (a `dict[str, dict]` keyed by
  subject id), `capabilities`, `outcomes`, `entities`, `goals`, `gaps` — each value
  a document conforming to the matching partial schema.
- Consumes: `toy.toy_world_model()`, `toy.toy_claims()`, `toy.ARTIFACT_IDS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_toy_split.py
"""The split is derived from the golden world model, and it is total.

Totality is the property with teeth: the subject cover must name every claim in
the run, because refs.check_subjects holds a real run to exactly that and a
fixture that could not satisfy its own gate would be a fixture-cannot-reach
weakness rather than a test.
"""

from __future__ import annotations

from rubrica import validate
from tests.toy import ARTIFACT_IDS, split_world_model, toy_claims, toy_world_model

_KIND_FOR_KEY = {
    "subjects": "subjects",
    "capabilities": "capabilities-part",
    "outcomes": "outcomes-part",
    "entities": "entities-part",
    "goals": "goals-part",
    "gaps": "gaps-part",
}


def _all_claim_ids() -> set[str]:
    return {
        claim["id"]
        for artifact_id in ARTIFACT_IDS
        for claim in toy_claims(artifact_id)["claims"]
    }


def test_every_partial_validates_against_its_own_schema(tmp_path):
    import json

    parts = split_world_model()
    for key, kind in _KIND_FOR_KEY.items():
        doc = tmp_path / f"{key}.json"
        doc.write_text(json.dumps(parts[key]), encoding="utf-8")
        assert validate.validate_artifact(doc, kind) == [], f"{key} does not match {kind}"
    for subject_id, part in parts["contradictions"].items():
        doc = tmp_path / f"contradiction-{subject_id}.json"
        doc.write_text(json.dumps(part), encoding="utf-8")
        assert validate.validate_artifact(doc, "contradictions-part") == []


def test_the_subject_cover_names_every_claim_in_the_run():
    covered = {
        claim_id
        for subject in split_world_model()["subjects"]["subjects"]
        for claim_id in subject["claims"]
    }
    assert covered == _all_claim_ids(), (
        "the cover must be total: refs.check_subjects reports any claim it omits"
    )


def test_every_subject_has_a_contradictions_part():
    """Even an empty one. The file's existence is the record that the sweep
    visited that subject, which is the check the single-turn stage never had."""
    parts = split_world_model()
    subject_ids = {subject["id"] for subject in parts["subjects"]["subjects"]}
    assert set(parts["contradictions"]) == subject_ids


def test_the_split_carries_every_contradiction_the_world_model_declares():
    """A split that dropped one would make the round-trip in
    tests/unit/test_reconcile_seal.py pass against a world model missing it."""
    split_ids = {
        c["id"]
        for part in split_world_model()["contradictions"].values()
        for c in part["contradictions"]
    }
    assert split_ids == {c["id"] for c in toy_world_model()["contradictions"]}


def test_outcomes_covers_every_declared_capability():
    parts = split_world_model()
    assert {o["capability_id"] for o in parts["outcomes"]["outcomes"]} == {
        c["id"] for c in parts["capabilities"]["capabilities"]
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_toy_split.py -v`
Expected: FAIL — `ImportError: cannot import name 'split_world_model'`.

- [ ] **Step 3: Add `split_world_model` to `tests/toy.py`**

Place it directly after `toy_world_model`, so the answer and its cut sit together.

```python
def split_world_model(
    world: dict[str, Any] | None = None,
    *,
    claim_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The golden world model, cut into the partials the reconcile passes write.

    Derived rather than hand-authored beside toy_world_model: tests/fixtures/toy/
    is the model answer a skill imitates, and a second copy of that answer in
    partial form would be a second thing to keep correct -- the drift this module
    already avoids by building every checkpoint from one source. Deriving is also
    what makes the seal's round trip a *property* (seal(split(w)) == w) rather
    than a worked example: a hand-authored pair could satisfy it while both
    drifted together.

    `claim_ids` defaults to every claim the toy run actually contains, because the
    cover has to be total -- refs.check_subjects reports any claim it omits, and a
    fixture that could not pass its own gate would be untestable against it.

    The subject assignment is deliberately mechanical (one subject per capability,
    one per entity, one for the actors and goals, one catch-all): it stands in for
    a judgment a prompt makes, and a fixture that guessed cleverly here would be
    claiming more than it can know.
    """
    world = toy_world_model() if world is None else world
    if claim_ids is None:
        claim_ids = [
            claim["id"] for artifact_id in ARTIFACT_IDS for claim in toy_claims(artifact_id)["claims"]
        ]
    remaining = list(dict.fromkeys(claim_ids))

    subjects: list[dict[str, Any]] = []

    def take(subject_id: str, label: str, cited: list[str]) -> None:
        """Record one subject, and strike its claims off the catch-all's list.

        Struck rather than left, so a claim cited by two elements lands in both
        subjects (the cover is a cover) while the catch-all holds only what no
        element cites at all.
        """
        if not cited:
            return
        subjects.append({"id": subject_id, "label": label, "claims": list(cited)})
        for claim_id in cited:
            if claim_id in remaining:
                remaining.remove(claim_id)

    for capability in world["capabilities"]:
        take(f"sub-{capability['id']}", capability["operation"], capability["claims"])
    for entity in world["entities"]:
        take(f"sub-{entity['id']}", entity["name"], entity["claims"])
    take(
        "sub-actors-and-goals",
        "who uses the target, and what for",
        [cid for item in (*world["actors"], *world["goals"]) for cid in item["claims"]],
    )
    take("sub-uncited", "claims no element of the world model cites", remaining)

    # Every subject gets a part, empty or not: the file is the record that the
    # fan-out member visited that subject, which is what
    # refs.check_contradiction_parts checks and what the single-turn stage could
    # never show. A contradiction lands under the first subject holding its
    # claim_a, so the assignment is a function of the cover rather than a second
    # judgment.
    by_subject: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in subjects}
    for contradiction in world["contradictions"]:
        owner = next(
            (s["id"] for s in subjects if contradiction["claim_a"] in s["claims"]),
            subjects[-1]["id"],
        )
        by_subject[owner].append(contradiction)

    return {
        "subjects": {"schema_version": "0.1", "subjects": subjects},
        "contradictions": {
            subject_id: {
                "schema_version": "0.1",
                "subject_id": subject_id,
                "contradictions": found,
            }
            for subject_id, found in by_subject.items()
        },
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
        "gaps": {"schema_version": "0.1", "gaps": world["gaps"]},
    }
```

Add `Iterable` to the module's `typing`/`collections.abc` imports if it is not
already there.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_toy_split.py -v`
Expected: all PASS. If `test_the_subject_cover_names_every_claim_in_the_run`
fails, the catch-all subject is empty and was skipped — check whether the toy
claims really are all cited, and if so delete that subject from the assertion
rather than inventing a claim to fill it.

- [ ] **Step 5: Run the gates**

Run: `make test && make check`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add tests/toy.py tests/unit/test_toy_split.py
git commit -S -s -m "test: Derive the reconcile partials from the golden world model

tests/fixtures/toy/ is the model answer a skill imitates, so a hand-authored
set of partials beside toy_world_model would be a second copy of that answer to
keep correct. split_world_model cuts the one answer instead, which also turns
the seal into a property -- seal(split(w)) == w -- rather than a worked example
a drifting pair could satisfy together.

The subject cover is total over the claims the toy run actually contains,
because refs.check_subjects holds a real run to exactly that and a fixture that
could not pass its own gate would be untestable against it. Every subject gets a
contradictions part, empty or not: the file is the record that the sweep visited
that subject.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: `reconcile-seal` — assemble the partials, compute the denominator

Code, not a prompt, for the reason `emit` is: two runs with identical partials
must produce byte-identical world models, or variance can no longer be attributed
to a pass. Being code it also streams nothing, so it cannot hit the 301s reset
however large the assembled model is.

**Files:**
- Create: `src/rubrica/reconcile.py`
- Modify: `src/rubrica/findings.py` (the layer list in the docstring)
- Modify: `src/rubrica/cli.py` (`SUBCOMMANDS`, `_build_parser`, one handler)
- Modify: `docs/reference/cli.md` (a `rubrica reconcile-seal` section)
- Test: `tests/unit/test_reconcile_seal.py` (create)

**Interfaces:**
- Produces: `reconcile.seal(run: RunPaths, *, denominator_version: int = 1) -> tuple[Path | None, list[Finding]]`.
  Returns `(world_model_path, [])` on success, `(None, findings)` on failure, and
  writes nothing in the failure case.
- Consumes: `RunPaths` members from Task 2, `artifacts.read_json` / `write_json`,
  `findings.Finding`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_reconcile_seal.py
"""The seal, and the one property that makes the split safe.

The round trip is the whole point: if seal(split(w)) != w, then staging reconcile
changed what the pipeline produces, and every fixture and recording downstream of
01-world-model.json is describing a world the new passes cannot rebuild.
"""

from __future__ import annotations

import json

import pytest

from rubrica import reconcile, validate
from rubrica.artifacts import read_json, write_json
from tests.toy import build_toy_run, split_world_model, toy_world_model


def _write_parts(run, parts: dict) -> None:
    write_json(run.capabilities_part, parts["capabilities"])
    write_json(run.outcomes_part, parts["outcomes"])
    write_json(run.entities_part, parts["entities"])
    write_json(run.goals_part, parts["goals"])
    write_json(run.gaps_part, parts["gaps"])
    write_json(run.subjects, parts["subjects"])
    for subject_id, part in parts["contradictions"].items():
        write_json(run.contradiction_part(subject_id), part)


def test_the_seal_rebuilds_the_golden_world_model_exactly(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())

    path, findings = reconcile.seal(run)

    assert findings == []
    assert path == run.world_model
    assert read_json(run.world_model) == toy_world_model()


def test_the_sealed_world_model_passes_layer_one(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)
    assert validate.validate_artifact(run.world_model, "world-model") == []


def test_the_denominator_is_computed_not_copied(tmp_path):
    """The arithmetic is the seal's job. A partial cannot assert it, and nothing
    in the partials carries a number for the seal to trust."""
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    _write_parts(run, parts)
    reconcile.seal(run)

    world = read_json(run.world_model)
    expected_cells = sum(len(o["outcome_classes"]) for o in parts["outcomes"]["outcomes"])
    assert world["denominator"] == {
        "version": 1,
        "capability_cells": expected_cells,
        "goals": len(parts["goals"]["goals"]),
    }


def test_the_denominator_version_can_be_bumped_for_an_amendment(tmp_path):
    """An amendment costs an explicit orchestrator decision and a version bump.
    The seal takes the bumped number rather than inventing or incrementing one,
    so the record of why it moved stays in decisions.md."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run, denominator_version=2)
    assert read_json(run.world_model)["denominator"]["version"] == 2


def test_the_target_comes_from_the_manifest(tmp_path):
    """No pass restates it. Today reconcile writes `target` itself and nothing
    checks it against the manifest, so this removes an unchecked restatement."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)
    assert read_json(run.world_model)["target"] == read_json(run.manifest)["target"]


@pytest.mark.parametrize(
    "attribute",
    ["capabilities_part", "outcomes_part", "entities_part", "goals_part", "gaps_part"],
)
def test_a_missing_partial_is_a_finding_and_writes_nothing(tmp_path, attribute):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    getattr(run, attribute).unlink()

    path, findings = reconcile.seal(run)

    assert path is None
    assert findings, f"a missing {attribute} must be reported"
    assert not run.world_model.is_file(), "the seal must not write a partial world model"
    assert all(f.message for f in findings), "a finding with an empty message is an empty exit-1"


def test_a_capability_with_no_outcome_record_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["outcomes"]["outcomes"] = parts["outcomes"]["outcomes"][:1]
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert path is None
    assert any("no outcome classes" in f.message for f in findings)
    assert not run.world_model.is_file()


def test_an_outcome_record_for_an_unknown_capability_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["outcomes"]["outcomes"].append(
        {
            "capability_id": "cap-invented",
            "outcome_classes": [
                {"id": "oc-x", "kind": "success", "description": "invented"}
            ],
        }
    )
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert path is None
    assert any("cap-invented" in f.message for f in findings)


def test_the_cli_exits_clean_and_prints_the_world_model_path(tmp_path, capsys):
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())

    assert main(["reconcile-seal", "--run", str(run.root)]) == 0
    assert capsys.readouterr().out.strip() == str(run.world_model)


def test_the_cli_exits_one_with_findings_on_stdout(tmp_path, capsys):
    """The exit-code contract: a stage defect is 1, one finding per line, on
    stdout -- never 2, and never an empty stdout."""
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    _write_parts(run, parts)
    run.gaps_part.unlink()

    assert main(["reconcile-seal", "--run", str(run.root)]) == 1
    assert capsys.readouterr().out.strip(), "exit 1 with empty stdout is the failure this forbids"


def test_a_missing_run_directory_is_a_usage_error(tmp_path, capsys):
    from rubrica.cli import main

    assert main(["reconcile-seal", "--run", str(tmp_path / "nope")]) == 2


def test_a_malformed_partial_is_a_finding_naming_that_partial(tmp_path, capsys):
    """Not exit 2, and not a finding against some other artifact. This repo has
    reported four fabricated `no such claim` findings against a correct world
    model because an unreadable input was blamed on the wrong file."""
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.entities_part.write_text("{not json", encoding="utf-8")

    code = main(["reconcile-seal", "--run", str(run.root)])
    out = capsys.readouterr().out
    assert code == 1
    assert "01-entities.json" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_reconcile_seal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rubrica.reconcile'`.

- [ ] **Step 3: Create `src/rubrica/reconcile.py`**

```python
"""The seal: assemble the reconcile partials into one world model.

Code rather than a prompt, for the reason emit is code: two runs with identical
partials must produce a byte-identical world model, or variance stops being
attributable to the pass that caused it. There is a second reason here, specific
to this pipeline's gateway: a code step streams nothing, so it cannot be killed
by the ~300s idle reset that splitting reconcile exists to avoid, however large
the assembled model gets.

This module assembles; it does not check. Cross-artifact checking is layer 2 and
lives in refs.py. What it *does* report is the narrow class that makes assembly
impossible -- a partial that is absent or unparseable, a declared capability with
no outcome classes, an outcome record naming a capability nobody declared -- and
it writes nothing at all when it reports any of them. A half-assembled world
model would be worse than none: it would clear layer 1 for the collections it did
manage to fill.
"""

from __future__ import annotations

from pathlib import Path

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.findings import Finding
from rubrica.paths import RunPaths, list_json

# (RunPaths attribute, the key inside that partial) in the order the passes run,
# so a run missing several partials names the earliest pass first -- the one a
# repair should start from, the same ordering _readable_targets uses.
_SINGLETON_PARTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("capabilities_part", ("capabilities",)),
    ("outcomes_part", ("outcomes",)),
    ("entities_part", ("entities",)),
    ("goals_part", ("actors", "goals")),
    ("gaps_part", ("gaps",)),
)


def _read_part(path: Path, out: list[Finding]) -> dict | None:
    """One partial, or None with a finding naming *that* partial.

    Naming the right artifact is the third rule of the exit-code contract, learned
    the hard way here: check-refs over an unreadable 01-claims/ once reported four
    fabricated `no such claim` findings against a world model that was correct.
    """
    try:
        return read_json(path)
    except ArtifactError as exc:
        out.append(Finding(path, "reconcile", "", str(exc)))
        return None


def seal(run: RunPaths, *, denominator_version: int = 1) -> tuple[Path | None, list[Finding]]:
    """Assemble 01-world-model.json from the partials, or report why it cannot be.

    `denominator_version` is passed in rather than inferred: an amendment costs an
    explicit orchestrator decision recorded in decisions.md, and a seal that
    incremented a version it found on disk would let the number move without one.
    """
    findings: list[Finding] = []

    # The manifest, not a partial, is where `target` comes from. The single-turn
    # stage wrote it itself and nothing ever checked it against the manifest, so
    # sourcing it here removes an unchecked restatement rather than moving one.
    manifest = _read_part(run.manifest, findings)

    parts: dict[str, dict] = {}
    for attribute, _keys in _SINGLETON_PARTS:
        document = _read_part(getattr(run, attribute), findings)
        if document is not None:
            parts[attribute] = document

    contradictions: list[dict] = []
    for path in list_json(run.contradictions_dir):
        part = _read_part(path, findings)
        if part is not None:
            contradictions.extend(part.get("contradictions", []))

    if findings:
        return None, findings

    capabilities = [dict(item) for item in parts["capabilities_part"]["capabilities"]]
    outcomes = {
        entry["capability_id"]: entry["outcome_classes"]
        for entry in parts["outcomes_part"]["outcomes"]
    }
    declared = {capability["id"] for capability in capabilities}

    for capability_id in sorted(set(outcomes) - declared):
        findings.append(
            Finding(
                run.outcomes_part,
                "reconcile",
                "/outcomes",
                f"outcome classes for {capability_id}, which no capability in "
                f"{run.capabilities_part.name} declares",
            )
        )
    for capability in capabilities:
        if capability["id"] not in outcomes:
            findings.append(
                Finding(
                    run.outcomes_part,
                    "reconcile",
                    "/outcomes",
                    f"capability {capability['id']} has no outcome classes; every declared "
                    "capability needs its capability x outcome-class cells, which is what the "
                    "coverage denominator counts",
                )
            )
        else:
            capability["outcome_classes"] = outcomes[capability["id"]]

    if findings:
        return None, findings

    world = {
        "schema_version": "0.1",
        "target": manifest["target"],
        "capabilities": capabilities,
        "entities": parts["entities_part"]["entities"],
        "actors": parts["goals_part"]["actors"],
        "goals": parts["goals_part"]["goals"],
        "contradictions": contradictions,
        "gaps": parts["gaps_part"]["gaps"],
        "denominator": {
            "version": denominator_version,
            # Counted from the joined capabilities, so the number cannot disagree
            # with the cells it describes. refs.check_world_model still recomputes
            # it -- now against a number code wrote, which is one fewer checkable
            # claim about a prompt's output and is recorded as such in
            # docs/design/limitations.md.
            "capability_cells": sum(len(c["outcome_classes"]) for c in capabilities),
            "goals": len(parts["goals_part"]["goals"]),
        },
    }
    write_json(run.world_model, world)
    return run.world_model, []
```

- [ ] **Step 4: Wire the subcommand in `cli.py`**

Add to `SUBCOMMANDS`, after the `("check-refs", ...)` entry:

```python
    ("reconcile-seal", "assemble the reconcile partials into one world model"),
```

Add to `_build_parser`, beside `p_emit`:

```python
    p_seal = parsers["reconcile-seal"]
    p_seal.add_argument("--run", required=True)
    # Passed rather than inferred: an amendment to the frozen goal list costs an
    # explicit orchestrator decision, and a seal that incremented a version it
    # found on disk would let the denominator move without one on the record.
    p_seal.add_argument("--denominator-version", type=int, default=1)
```

Add the handler beside `emit`'s, inside the same `try`:

```python
        if args.command == "reconcile-seal":
            run = _run_dir(args.run)
            world, findings = reconcile.seal(
                run, denominator_version=args.denominator_version
            )
            if world is not None:
                print(world)
            return _report(findings)
```

Add `from rubrica import reconcile` to the imports, in the existing import block
and in alphabetical position so `ruff` (with `I`) is satisfied.

- [ ] **Step 5: Add the layer name in `findings.py`**

In `Finding`'s docstring, extend the layer list so the closed set stays a real
list:

```
    The layers: "schema" | "refs" | "invariant" | "emit" | "reconcile" |
    "internal" | "recall" | "review" | "skill".
```

and add, after the "internal" paragraph:

```
    "reconcile" is the seal's layer: the artifacts are the world-model partials
    and the failure is that they cannot be assembled at all -- a partial absent or
    unparseable, a declared capability with no outcome classes. Distinct from
    "refs" because refs checks a run someone may still be building, while this
    names the reason one command produced no output.
```

- [ ] **Step 6: Document it in `docs/reference/cli.md`**

Add a `rubrica reconcile-seal` section in the same shape as the others: what it
takes (`--run`, `--denominator-version`), what it reads (the seven partials and
the manifest), what it writes (`01-world-model.json`), what it prints (the path on
success), and its exit codes. State plainly that it assembles and does not check,
and that it writes nothing when it reports a finding.
`tests/unit/test_docs_accuracy.py::test_every_subcommand_has_its_own_section`
fails until this exists — that failure is the guard working.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_reconcile_seal.py -v`
Expected: all PASS. If the round-trip test fails on array order, compare with
`json.dumps(..., indent=1)` on both sides — the likely cause is contradictions
being concatenated in a different order than the golden world model declares them.

- [ ] **Step 8: Run the gates**

Run: `make test && make check && uv run rubrica check-skills; echo "check-skills:$?"`
Expected: green, `check-skills:0`.

- [ ] **Step 9: Commit**

```bash
git add src/rubrica/reconcile.py src/rubrica/cli.py src/rubrica/findings.py \
        tests/unit/test_reconcile_seal.py docs/reference/cli.md
git commit -S -s -m "feat: Add reconcile-seal, which assembles the partials and counts the denominator

Code for the reason emit is code: two runs with identical partials must produce
a byte-identical world model or variance stops being attributable to a pass. And
a code step streams nothing, so it cannot be killed by the ~300s idle reset the
staging exists to avoid, however large the assembled model gets.

It assembles and does not check -- cross-artifact checking is layer 2 -- but it
does report the narrow class that makes assembly impossible, and writes nothing
at all when it does. A half-assembled world model would clear layer 1 for the
collections it managed to fill, which is worse than none.

The round trip is the property that makes the split safe: seal(split(w)) == w
against the golden world model, so every fixture and recording downstream of
01-world-model.json still describes a world the new passes can rebuild.

target now comes from the manifest instead of being restated by a pass, which
removes a restatement nothing checked. denominator_version is passed rather than
incremented, so the frozen goal list cannot move without an orchestrator
decision on the record.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 5: Layer-2 checks for the partials

Three checkers. The one that matters most is `check_contradiction_parts`: it turns
"was the sweep thorough?", unobservable in the single-turn stage, into "did it
visit every subject", which is structural.

**Files:**
- Modify: `src/rubrica/refs.py` (three checkers, `_readable_targets`, `check_all`)
- Test: `tests/unit/test_refs_reconcile_parts.py` (create)

**Interfaces:**
- Produces: `refs.check_subjects(run) -> list[Finding]`,
  `refs.check_contradiction_parts(run) -> list[Finding]`,
  `refs.check_outcomes(run) -> list[Finding]`. Every one returns `[]` when its
  inputs are absent, following every existing checker.
- Consumes: `refs._load`, `refs._claim_ids`, `refs._dupes`, `refs._as_list`,
  `RunPaths.subject_part_ids`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_refs_reconcile_parts.py
"""Layer 2 over the reconcile partials.

Each checker is measured in both directions: red on the defect it names, and green
on a clean run. A predicate nobody has watched fail is not yet a guard.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import read_json, write_json
from tests.toy import build_toy_run, split_world_model


def _seeded(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    write_json(run.subjects, parts["subjects"])
    write_json(run.capabilities_part, parts["capabilities"])
    write_json(run.outcomes_part, parts["outcomes"])
    for subject_id, part in parts["contradictions"].items():
        write_json(run.contradiction_part(subject_id), part)
    return run, parts


def test_a_complete_cover_is_clean(tmp_path):
    run, _ = _seeded(tmp_path)
    assert refs.check_subjects(run) == []


def test_an_absent_cover_is_not_a_finding(tmp_path):
    """A pass that has not run yet is validate_stage's finding, not this one's --
    the rule every checker in this module follows."""
    run = build_toy_run(tmp_path, upto="extract")
    assert refs.check_subjects(run) == []


def test_a_claim_no_subject_covers_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    dropped = parts["subjects"]["subjects"][0]["claims"].pop()
    write_json(run.subjects, parts["subjects"])

    findings = refs.check_subjects(run)

    assert any(dropped in f.message for f in findings), (
        "totality is the property that makes the cover acceptable where a pair filter was not"
    )


def test_a_subject_citing_an_unextracted_claim_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["subjects"]["subjects"][0]["claims"].append("clm-invented-999")
    write_json(run.subjects, parts["subjects"])
    assert any("clm-invented-999" in f.message for f in refs.check_subjects(run))


def test_a_duplicate_subject_id_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["subjects"]["subjects"].append(dict(parts["subjects"]["subjects"][0]))
    write_json(run.subjects, parts["subjects"])
    assert any("duplicate" in f.message for f in refs.check_subjects(run))


def test_every_subject_visited_is_clean(tmp_path):
    run, _ = _seeded(tmp_path)
    assert refs.check_contradiction_parts(run) == []


def test_a_subject_with_no_part_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    subject_id = next(iter(parts["contradictions"]))
    run.contradiction_part(subject_id).unlink()
    assert any(subject_id in f.message for f in refs.check_contradiction_parts(run))


def test_a_part_for_an_undeclared_subject_is_reported(tmp_path):
    run, _ = _seeded(tmp_path)
    write_json(
        run.contradiction_part("sub-invented"),
        {"schema_version": "0.1", "subject_id": "sub-invented", "contradictions": []},
    )
    assert any("sub-invented" in f.message for f in refs.check_contradiction_parts(run))


def test_a_part_whose_subject_id_disagrees_with_its_filename_is_reported(tmp_path):
    """The filename is what the fan-out was dispatched with; the field is what the
    member believed it was working on. A mismatch means one member wrote another's
    slice, which is the failure the fourth dispatch argument exists to prevent."""
    run, parts = _seeded(tmp_path)
    subject_id = next(iter(parts["contradictions"]))
    part = read_json(run.contradiction_part(subject_id))
    part["subject_id"] = "sub-somebody-else"
    write_json(run.contradiction_part(subject_id), part)
    assert any("sub-somebody-else" in f.message for f in refs.check_contradiction_parts(run))


def test_a_contradiction_naming_an_unextracted_claim_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    subject_id, part = next(
        (sid, p) for sid, p in parts["contradictions"].items() if p["contradictions"]
    )
    part["contradictions"][0]["claim_a"] = "clm-invented-999"
    write_json(run.contradiction_part(subject_id), part)
    assert any("clm-invented-999" in f.message for f in refs.check_contradiction_parts(run))


def test_matched_capabilities_and_outcomes_are_clean(tmp_path):
    run, _ = _seeded(tmp_path)
    assert refs.check_outcomes(run) == []


def test_a_capability_with_no_outcome_record_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["outcomes"]["outcomes"] = parts["outcomes"]["outcomes"][:1]
    write_json(run.outcomes_part, parts["outcomes"])
    findings = refs.check_outcomes(run)
    assert findings, "an unswept capability shrinks the denominator silently"


def test_an_outcome_record_for_an_unknown_capability_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["outcomes"]["outcomes"].append(
        {
            "capability_id": "cap-invented",
            "outcome_classes": [{"id": "oc-x", "kind": "success", "description": "x"}],
        }
    )
    write_json(run.outcomes_part, parts["outcomes"])
    assert any("cap-invented" in f.message for f in refs.check_outcomes(run))


def test_check_all_reaches_the_new_checkers(tmp_path):
    """check_all runs every checker the run has inputs for, so a checker that is
    written but not wired in is invisible to `rubrica check-refs`."""
    run, parts = _seeded(tmp_path)
    parts["subjects"]["subjects"][0]["claims"].append("clm-invented-999")
    write_json(run.subjects, parts["subjects"])
    assert any("clm-invented-999" in f.message for f in refs.check_all(run))


def test_an_unparseable_partial_short_circuits_everything_below_it(tmp_path):
    """check_readable must name the broken partial and stop. Continuing produces
    findings that blame artifacts which are fine -- and the orchestrator's single
    repair attempt then rewrites the wrong file."""
    run, _ = _seeded(tmp_path)
    run.subjects.write_text("{not json", encoding="utf-8")
    findings = refs.check_all(run)
    assert len(findings) == 1
    assert "01-subjects.json" in str(findings[0].artifact)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_reconcile_parts.py -v`
Expected: FAIL — `AttributeError: module 'rubrica.refs' has no attribute 'check_subjects'`.

- [ ] **Step 3: Add the three checkers**

Insert into `src/rubrica/refs.py` immediately before `check_world_model`, so the
file reads in pipeline order:

```python
def check_subjects(run: RunPaths) -> list[Finding]:
    """The claim subject cover, and its totality.

    Totality is the whole reason a subject cover is acceptable where a
    code-proposed pair filter was not. A filter drops one of ~n^2/2 pairs that
    appear nowhere on disk, so nothing can report the omission and no human can
    overrule it; a cover names every claim, so a claim it misses is a finding
    here. That difference is why the cover exists in this shape, and this checker
    is the half of it that is mechanical.
    """
    cover = _load(run.subjects)
    if cover is None:
        return []
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.subjects, "refs", pointer, message))

    subjects = _as_list(cover.get("subjects"))
    for dupe in _dupes([s["id"] for s in subjects if isinstance(s, dict)]):
        report("/subjects", f"duplicate subject id {dupe!r}")

    known = _claim_ids(run)
    covered: set[str] = set()
    for i, subject in enumerate(subjects):
        if not isinstance(subject, dict):
            continue
        for j, claim_id in enumerate(_as_list(subject.get("claims"))):
            covered.add(claim_id)
            if claim_id not in known:
                report(f"/subjects/{i}/claims/{j}", f"no such claim: {claim_id}")

    for claim_id in sorted(known - covered):
        report(
            "/subjects",
            f"no subject covers claim {claim_id}; the cover must be total, or the "
            "contradiction sweep never compares that claim against anything",
        )
    return out


def check_contradiction_parts(run: RunPaths) -> list[Finding]:
    """One contradictions part per subject in the cover, and its references.

    **Meaningful only once every fan-out member has finished.** This reports every
    subject without a part from the moment 01-contradictions/ exists, so mid-
    fan-out most of them are missing by construction -- exactly the caveat
    check_verdicts carries, and for the same reason. There is no stage-scoped
    check-refs: check_all runs every checker the run has inputs for.

    The subject_id *field* is checked against the *filename* because they answer
    different questions: the filename is the slice the member was dispatched with,
    the field is the slice it believed it was working on. A mismatch means one
    member wrote a sibling's slice, which is the failure the fourth dispatch
    argument exists to prevent and which no schema can see.
    """
    cover = _load(run.subjects)
    if cover is None or not run.contradictions_dir.is_dir():
        return []
    out: list[Finding] = []
    declared = {
        s["id"] for s in _as_list(cover.get("subjects")) if isinstance(s, dict) and "id" in s
    }
    on_disk = set(run.subject_part_ids())

    for subject_id in sorted(declared - on_disk):
        out.append(
            Finding(
                run.contradictions_dir,
                "refs",
                "",
                f"no contradictions part for subject {subject_id}; every subject needs one, "
                "even one recording that no disagreement was found there",
            )
        )
    for subject_id in sorted(on_disk - declared):
        out.append(
            Finding(
                run.contradiction_part(subject_id),
                "refs",
                "",
                f"contradictions part for subject {subject_id}, which 01-subjects.json does "
                "not declare",
            )
        )

    known = _claim_ids(run)
    seen: list[str] = []
    for path in list_json(run.contradictions_dir):
        part = _load(path)
        if part is None:
            continue
        field = _str_or_none(part.get("subject_id"))
        if field is not None and field != path.stem:
            out.append(
                Finding(
                    path,
                    "refs",
                    "/subject_id",
                    f"declares subject_id {field!r} but is the part for {path.stem!r}",
                )
            )
        for i, contradiction in enumerate(_as_list(part.get("contradictions"))):
            if not isinstance(contradiction, dict):
                continue
            seen.append(str(contradiction.get("id")))
            for side in ("claim_a", "claim_b"):
                claim_id = contradiction.get(side)
                if claim_id not in known:
                    out.append(
                        Finding(
                            path,
                            "refs",
                            f"/contradictions/{i}/{side}",
                            f"no such claim: {claim_id}",
                        )
                    )
    for dupe in _dupes(seen):
        out.append(
            Finding(
                run.contradictions_dir,
                "refs",
                "",
                f"duplicate contradiction id {dupe!r} across parts",
            )
        )
    return out


def check_outcomes(run: RunPaths) -> list[Finding]:
    """Every declared capability has outcome classes, and no others do.

    The completeness half is what splitting the outcomes pass out bought: an
    unswept capability shrinks the coverage denominator, and a run can reach high
    coverage that way without ever testing anything hard. Nothing checked it while
    both lived in one turn.
    """
    capabilities = _load(run.capabilities_part)
    outcomes = _load(run.outcomes_part)
    if capabilities is None or outcomes is None:
        return []
    out: list[Finding] = []
    declared = [
        c["id"]
        for c in _as_list(capabilities.get("capabilities"))
        if isinstance(c, dict) and "id" in c
    ]
    recorded = {
        e["capability_id"]
        for e in _as_list(outcomes.get("outcomes"))
        if isinstance(e, dict) and "capability_id" in e
    }
    for capability_id in sorted(set(declared) - recorded):
        out.append(
            Finding(
                run.outcomes_part,
                "refs",
                "/outcomes",
                f"no outcome classes for declared capability {capability_id}; the coverage "
                "denominator counts capability x outcome-class cells, so a capability left "
                "unswept shrinks the surface every later percentage is measured against",
            )
        )
    for capability_id in sorted(recorded - set(declared)):
        out.append(
            Finding(
                run.outcomes_part,
                "refs",
                "/outcomes",
                f"outcome classes for {capability_id}, which 01-capabilities.json does not "
                "declare",
            )
        )
    return out
```

- [ ] **Step 4: Wire them into `_readable_targets` and `check_all`**

In `_readable_targets`, in pipeline order, replace the world-model line:

```python
    targets += list_json(run.claims_dir)
    targets += [run.subjects]
    targets += list_json(run.contradictions_dir)
    targets += [
        run.capabilities_part,
        run.outcomes_part,
        run.entities_part,
        run.goals_part,
        run.gaps_part,
    ]
    targets += [run.world_model, run.scenarios]
```

In `check_all`, before `check_world_model`:

```python
    findings.extend(check_subjects(run))
    findings.extend(check_contradiction_parts(run))
    findings.extend(check_outcomes(run))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_refs_reconcile_parts.py -v`
Expected: all PASS.

- [ ] **Step 6: Confirm the both-directions discipline on one predicate**

Pick `test_a_claim_no_subject_covers_is_reported` and confirm the mirror: revert
the dropped claim, re-run, and see it green. A predicate that has only ever been
watched pass is not yet a guard.

Run: `uv run pytest tests/unit/test_refs_reconcile_parts.py -k "cover" -v`

- [ ] **Step 7: Run the gates**

Run: `make test && make check && uv run rubrica check-skills; echo "check-skills:$?"`
Expected: green. `tests/unit/test_refs_readable.py` breaks each readable target in
turn — if it has a hard-coded list, extend it with the new partials; that module's
completeness is what keeps a truncated artifact from misdirecting a repair.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs_reconcile_parts.py tests/unit/test_refs_readable.py
git commit -S -s -m "feat: Check the reconcile partials at layer 2

Three checkers. check_subjects holds the cover to totality, which is the property
that makes a subject cover acceptable where a code-proposed pair filter was not:
a filter drops one of ~n^2/2 pairs that appear nowhere on disk, so nothing can
report it and no human can overrule it, while a cover that misses a claim is a
finding here.

check_contradiction_parts requires a part per subject, empty or not, which turns
'was the sweep thorough' -- unobservable in the single-turn stage -- into 'did it
visit every subject'. It carries check_verdicts' caveat for check_verdicts'
reason: it reports every missing subject from the moment the directory exists, so
it means something only once the fan-out has finished. It also checks each part's
subject_id field against its filename, because those answer different questions
and a mismatch means one member wrote a sibling's slice.

check_outcomes reports a declared capability with no outcome classes -- an
unswept capability shrinks the denominator, and nothing checked that while both
lived in one turn.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: Fold a prefix family in the README drawing

Landed **inert**: nothing in `paths.STAGES` starts with `reconcile-` yet, so the
committed SVGs do not change and their byte-compare test passes untouched. Task 7's
flip is then the single commit that moves the drawing.

**Files:**
- Modify: `scripts/render-readme-diagram.py`
- Test: `tests/unit/test_docs_accuracy.py` (add two tests)

**Interfaces:**
- Produces: `render_readme_diagram.FOLD_PREFIX: str`, `FOLD_LABEL: str`,
  `FOLD_NOTE: str`, and `drawn_stages(spec: dict) -> list[str]`.
- Consumes: the existing `PHASES`, `phase()`, `txt()`, `CAP_Y`, `H`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_docs_accuracy.py`:

```python
def test_the_readme_diagram_fold_is_total_in_both_directions():
    """The fold collapses a stage family into one drawn line. That is a way to
    make a stage disappear from the drawing, so it is checked both ways: every
    folded stage is represented by the fold's label, and no stage outside the
    family is hidden by it. Without this the fold would silently defeat the
    partition test next door, which is the drift that test exists to catch.
    """
    renderer = _readme_renderer()
    for phase in renderer.PHASES:
        drawn = renderer.drawn_stages(phase)
        folded = [s for s in phase["stages"] if s.startswith(renderer.FOLD_PREFIX)]
        unfolded = [s for s in phase["stages"] if not s.startswith(renderer.FOLD_PREFIX)]
        assert all(stage in drawn for stage in unfolded), (
            f"the fold hid a stage outside the {renderer.FOLD_PREFIX!r} family: {drawn}"
        )
        assert (renderer.FOLD_LABEL in drawn) == bool(folded), (
            f"the fold label must appear exactly when the phase holds a folded stage: {drawn}"
        )
        assert len(drawn) == len(set(drawn)), f"the fold produced a repeated line: {drawn}"


def test_the_readme_diagram_footnote_appears_only_when_something_folds():
    """A footnote explaining a star that is not drawn is worse than no footnote."""
    renderer = _readme_renderer()
    folds = any(
        stage.startswith(renderer.FOLD_PREFIX)
        for phase in renderer.PHASES
        for stage in phase["stages"]
    )
    for theme in renderer.OUTPUTS:
        assert (renderer.FOLD_NOTE in renderer.svg(theme)) is folds
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -k fold -v`
Expected: FAIL — `AttributeError: module has no attribute 'drawn_stages'`.

- [ ] **Step 3: Add the fold to the renderer**

Add below `PHASES`:

```python
# A stage family drawn as one line. paths.STAGES holds each reconcile pass
# separately -- it has to, because check-skills binds one skill to one stage and
# manifest.stages records model, effort and digest per stage -- but they are one
# logical step engineered as substeps, and this drawing is the newcomer's
# altitude. Listing them all would also not fit: phase() draws one line per entry
# from a fixed BOX_H, so the family would overflow its box rather than crowd it.
#
# PHASES["stages"] stays complete, because it is also the coverage claim
# test_the_readme_diagram_covers_every_stage_in_contract_order asserts against
# paths.STAGES. The drawn labels are derived from it, never restated beside it.
FOLD_PREFIX = "reconcile-"
FOLD_LABEL = "reconcile*"
FOLD_NOTE = "* one logical step, engineered as substeps"


def drawn_stages(spec: dict) -> list[str]:
    """The stage lines one phase draws: its stages, with the family folded once."""
    drawn: list[str] = []
    for stage in spec["stages"]:
        label = FOLD_LABEL if stage.startswith(FOLD_PREFIX) else stage
        if label not in drawn:
            drawn.append(label)
    return drawn


def any_folded() -> bool:
    return any(
        stage.startswith(FOLD_PREFIX) for phase in PHASES for stage in phase["stages"]
    )
```

In `phase()`, replace the stage loop:

```python
    for n, stage in enumerate(drawn_stages(spec)):
        out.append(txt(x + 11, BOX_Y + 82 + n * 14, stage, "stage", 11.5))
```

Change the canvas height so the footnote has a line of its own rather than being
appended to the caption row, which is laid out left-to-right and would overflow
the viewBox invisibly:

```python
CAP_Y = BOX_Y + BOX_H + CAP_GAP
# The footnote sits on its own line under the captions, and only when something
# folds -- so a run of this script before the reconcile family exists produces
# byte-identical output to the committed pair.
H = CAP_Y + 16 + (15 if any_folded() else 0)
```

In `svg()`, after `body.append(captions())`:

```python
    if any_folded():
        body.append(txt(PAD + 2, CAP_Y + 15, FOLD_NOTE, "cap", 11.5))
```

and extend `desc` so the alt text does not promise a list it no longer gives:

```python
    covers = (
        "Each phase lists the stages it covers; a starred line is one logical step "
        "engineered as substeps."
        if any_folded()
        else "Each phase lists the stages it covers."
    )
```
then use `covers` in place of the final sentence of `desc`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -k "fold or readme" -v`
Expected: all PASS, **including the byte-compare tests** — nothing folds yet, so
the committed SVGs must be unchanged.

- [ ] **Step 5: Prove it is inert**

Run: `uv run python scripts/render-readme-diagram.py --check; echo "check:$?"`
Expected: `check:0`. If it reports the files as stale, the fold changed output
before any stage folds, which means `any_folded()` is wrong.

- [ ] **Step 6: Commit**

```bash
git add scripts/render-readme-diagram.py tests/unit/test_docs_accuracy.py
git commit -S -s -m "feat: Let the README drawing fold a stage family into one line

The reconcile passes are separate stages -- check-skills binds one skill to one
stage, and manifest.stages records model, effort and digest per stage -- but they
are one logical step engineered as substeps, and this drawing is a newcomer's
altitude. Listing them all also would not fit: phase() draws one line per entry
from a fixed BOX_H, so the family would overflow its box.

PHASES['stages'] stays complete because it is also the coverage claim the
partition test asserts against paths.STAGES; the drawn labels are derived from it
rather than restated beside it. Two new tests keep the fold honest in both
directions, since a fold is otherwise a way to make a stage vanish from the
drawing and defeat the partition test next door.

Inert as committed: nothing starts with the folded prefix yet, so --check still
reports the committed SVGs current.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 7: The flip — `reconcile` becomes a sequence

One atomic task, because `check-skills` binds stage names to skill directory names
one-to-one and `expected_skill_names()` derives from `paths.STAGES`. A partial
update makes it reject every correctly named skill — this repo has already paid
that price once, during the `tg-` → `rb-` rename.

**Files:**
- Modify: `src/rubrica/paths.py` (`STAGES`), `src/rubrica/validate.py`
  (`STAGE_ARTIFACTS`), `src/rubrica/skills.py` (`CODE_ONLY_STAGES`)
- Create: seven `SKILL.md` files and `rb-reconcile/SUPERSEDED.md`
- Delete: `src/rubrica/skills/rb-reconcile/SKILL.md` **only**
- Modify: `scripts/render-pipeline-diagram.py` (`ROWS`),
  `scripts/render-readme-diagram.py` (`PHASES`), and re-render all three drawings
- Modify: `tests/toy.py` (`_UPTO_STAGES`, the build), plus the ten test modules
  that name the stage as a literal
- Modify: `docs/concepts/pipeline.md`, `docs/concepts/glossary.md`,
  `docs/concepts/artifact-contract.md`, `docs/reference/artifacts.md`,
  `docs/guides/running-a-stage-by-hand.md`, `docs/getting-started.md`, `CLAUDE.md`
- Rename: `tests/unit/test_skills_reconcile.py` → one module per pass, or one
  module parameterised over the family (see Step 6)

**Interfaces:**
- Produces: `paths.STAGES` containing, between `extract` and `propose`:
  `reconcile-subjects`, `reconcile-contradict`, `reconcile-capabilities`,
  `reconcile-outcomes`, `reconcile-entities`, `reconcile-goals`,
  `reconcile-gaps`, `reconcile-seal`.
- Produces: `toy.build_toy_run(upto=...)` accepting `"reconcile-gaps"` (partials
  written, no world model) and `"reconcile-seal"` (world model sealed).
  **`upto="reconcile"` stops existing** — five call sites in
  `tests/unit/test_brief.py` and `tests/unit/test_sizing.py` must move to
  `"reconcile-seal"`.

- [ ] **Step 1: Change the three constants**

`src/rubrica/paths.py`:

```python
STAGES = (
    "survey",
    "triage",
    "intake",
    "extract",
    # One logical step, engineered as substeps. Separate stages rather than one
    # skill branching on a slice id, for two reasons that are both load-bearing:
    # check-skills binds one skill file to one stage name, and manifest.stages
    # records model, effort and skill digest per stage -- which is what lets a
    # think-heavy pass carry a different budget from a mechanical one. The name
    # prefix keeps the family legible here, where the ordering is the pipeline's
    # documentation.
    "reconcile-subjects",
    "reconcile-contradict",
    "reconcile-capabilities",
    "reconcile-outcomes",
    "reconcile-entities",
    "reconcile-goals",
    "reconcile-gaps",
    "reconcile-seal",
    "propose",
    "score",
    "instantiate",
    "challenge",
    "emit",
    "smoke",
)
```

`src/rubrica/validate.py`, in `STAGE_ARTIFACTS`, replacing the `"reconcile"` row:

```python
    "reconcile-subjects": ("subjects",),
    "reconcile-contradict": ("contradictions-part",),
    "reconcile-capabilities": ("capabilities-part",),
    "reconcile-outcomes": ("outcomes-part",),
    "reconcile-entities": ("entities-part",),
    "reconcile-goals": ("goals-part",),
    "reconcile-gaps": ("gaps-part",),
    "reconcile-seal": ("world-model",),
```

`src/rubrica/skills.py`:

```python
CODE_ONLY_STAGES: frozenset[str] = frozenset({"intake", "smoke", "survey", "reconcile-seal"})
```

- [ ] **Step 2: Run `check-skills` to see exactly what the flip owes**

Run: `uv run rubrica check-skills; echo "exit:$?"`
Expected: exit 1, with a finding per missing skill directory (seven names) and one
for `rb-reconcile` declaring a stage that is no longer in `STAGES`. That list is
the checklist for Step 3 — work it until the command exits 0.

- [ ] **Step 3: Write the seven skills**

Each gets the five mandatory sections in order — `1. Inputs`, `2. Output`,
`3. Method`, `4. Invariants`, `5. Refusal conditions` — and the contract block
below verbatim. The prose is **redistributed from `rb-reconcile/SKILL.md`, not
paraphrased**: read that file first (it is still on disk until Step 4), and move
the paragraph that owns each rule.

Two rules from its §1 must survive the split, and one of them needs rewriting:

- **Carried unchanged into `rb-reconcile-contradict` and into every pass that
  could settle a disagreement** (`-capabilities`, `-outcomes`, `-entities`): the
  rule that a resolution may rest only on what the claims establish, never on what
  a system "like this" usually does — including the worked `get_ticket` example and
  the tell that convention reasoning "would have produced the same resolution even
  if `notes.md` had never been extracted at all."
- **Rewritten:** the prohibition on rereading your own last answer was written for
  a single-pass stage. In a sequence, a later pass reading an earlier pass's
  partial *is* the design. What survives is narrower: **no pass reads
  `01-world-model.json`, and a re-dispatched pass does not read its own previous
  output.** Put that sentence in every pass's §1.

```toml
# rb-reconcile-subjects
stage = "reconcile-subjects"
reads = ["manifest", "claims_dir"]
writes = ["subjects"]
schemas = ["subjects"]
invokes = ["validate", "check-refs"]
```
§3 must say: assign **every** claim to at least one subject; a claim may go to
several; when unsure which subject a claim belongs to, assign it to all plausible
ones. §4: `refs.check_subjects` reports any claim no subject covers and any
subject citing a claim that was never extracted. §5: if a claim's subject cannot
be determined at all, over-assign rather than guess one — and never drop it,
because a claim in no subject is never compared against anything.

```toml
# rb-reconcile-contradict
stage = "reconcile-contradict"
reads = ["manifest", "claims_dir", "subjects"]
writes = ["contradiction_part"]
schemas = ["contradictions-part"]
invokes = ["validate", "check-refs"]
```
§1 must state it is one fan-out member, dispatched with **one `subject_id`**, and
that it reads every claim in its own subject **across all input files** — which is
what preserves cross-artifact contradiction detection. §2: write the part even
when nothing was found; an empty `contradictions` array is the record that this
subject was swept. §3 and §5 carry rb-reconcile's method step 6 and its first,
second and last refusal conditions verbatim, `unresolved` included as "the value
under the most pressure to be dropped by a model that wants to look decisive."

```toml
# rb-reconcile-capabilities
stage = "reconcile-capabilities"
reads = ["manifest", "claims_dir", "contradictions_dir"]
writes = ["capabilities_part"]
schemas = ["capabilities-part"]
invokes = ["validate", "check-refs"]
```
Carries rb-reconcile's method steps 1, 2 and 5 (grouping and citing; the
`binding` requirement, including that `emit` reports a finding for an accepted
scenario whose capability has none, which costs a shipped test). §1 must say the
contradictions already recorded are a **constraint**: a disagreement recorded
`unresolved` may not be quietly settled by how this pass models the capability.
**Do not** write `outcome_classes` — they are the next pass's output.

```toml
# rb-reconcile-outcomes
stage = "reconcile-outcomes"
reads = ["manifest", "claims_dir", "contradictions_dir", "capabilities_part"]
writes = ["outcomes_part"]
schemas = ["outcomes-part"]
invokes = ["validate", "check-refs"]
```
Carries method step 3 whole, including the measurement that harvesting outcome
classes only from claims already tagged `outcome_class` misses them — the real run
that filed the same fact as `outcome_class` from one input and as `invariant`,
twice, from another — and the instruction to fold two `kind` labels for one fact
into one outcome class citing both. §3 opens by quantifying over the capability
list in `01-capabilities.json`: for each, what happens on success, on a
legitimately empty result, when the lookup target does not exist, on a bad or
missing argument, and whether any of those is addressed nowhere
(`underspecified`, not silence). §4: `refs.check_outcomes` reports any declared
capability with no entry.

```toml
# rb-reconcile-entities
stage = "reconcile-entities"
reads = ["manifest", "claims_dir", "contradictions_dir", "capabilities_part"]
writes = ["entities_part"]
schemas = ["entities-part"]
invokes = ["validate", "check-refs"]
```
Carries method steps 4 and 10 and the third refusal condition. Step 4's
quantification is over the capabilities in `01-capabilities.json`. Step 10's
`machine:`/`prose:` reasoning must be carried in full, both directions: a real
invariant filed as `prose:` leaves the reachability gate nothing to check, while a
`machine:` invariant promoted from an inference fails **every** seed that is
actually correct, because `check-refs` evaluates it as ground truth.

```toml
# rb-reconcile-goals
stage = "reconcile-goals"
reads = ["manifest", "claims_dir", "contradictions_dir", "capabilities_part", "entities_part"]
writes = ["goals_part"]
schemas = ["goals-part"]
invokes = ["validate", "check-refs"]
```
Carries method step 8 and the fourth refusal condition. §2 must say the goal list
is frozen the moment it is written: `rb-propose` designs against exactly this list
and may only *request* an amendment, which costs an explicit orchestrator decision
and a `denominator_version` bump passed to `reconcile-seal`. So write every goal
the claims honestly support now — writing too few is a request-and-wait later, not
a quiet fix.

```toml
# rb-reconcile-gaps
stage = "reconcile-gaps"
reads = ["manifest", "claims_dir", "subjects", "contradictions_dir", "capabilities_part", "outcomes_part", "entities_part", "goals_part"]
writes = ["gaps_part"]
schemas = ["gaps-part"]
invokes = ["validate", "check-refs"]
```
Carries method step 7 and the remaining refusal conditions, including the
confabulation one ("you are the last stage that does" becomes "you are the last
pass that reads the claims closely"). §3 has a second half no other pass has: read
every prior partial and audit it — a capability with no supporting claim, an
invariant promoted to `machine:` on an inference, an outcome class nothing states —
and record what it finds as a gap. §5 keeps the `blocks` rule verbatim: a gap that
blocks `propose` is what makes the orchestrator halt, so name `blocks` honestly
rather than narrowly, and never leave it empty to avoid triggering a halt.

- [ ] **Step 4: Retire `rb-reconcile/SKILL.md`, keep the evidence**

```bash
git rm src/rubrica/skills/rb-reconcile/SKILL.md
```

**Do not touch `src/rubrica/skills/rb-reconcile/exercise.md`.** It is the record of
two real dispatches, including the disagreement about which stages a gap blocks
that this whole design argues from. Create beside it:

```markdown
# This directory is a record, not a skill

`rb-reconcile` was one stage that read every claims file and wrote the whole
world model in one dispatch. It was replaced by the `reconcile-*` family and a
code seal, because a single dispatch had to think for minutes before writing its
first byte and the gateway closes a silent stream at ~300s.

`exercise.md` beside this file records what two real dispatches of that stage
measurably did. It is **not** an exercise record for any current skill and was
not relocated into one: moving it would assert that a dispatch of some
`rb-reconcile-*` pass did what the superseded stage actually did, which is the
misattribution this project has already retracted once.

There is no `SKILL.md` here, and nothing looks for one: `skills._skill_dirs`
keeps only children that have one, `expected_skill_names` derives from
`paths.STAGES`, and no code in this repository reads an `exercise.md`.

The design that replaced it: `docs/superpowers/specs/2026-08-19-staged-reconcile-design.md`.
```

- [ ] **Step 5: Confirm the retired directory is inert**

Run: `uv run rubrica check-skills; echo "exit:$?"`
Expected: `exit:0`. A finding naming `rb-reconcile` here means `_skill_dirs` is
picking the directory up after all — stop and re-read it rather than deleting the
record.

- [ ] **Step 6: Move the test call sites and the prose module**

Run first, to get the list: `grep -rn '"reconcile"' tests/ src/ | grep -v rb-reconcile`

- The five `upto="reconcile"` call sites in `tests/unit/test_brief.py` and
  `tests/unit/test_sizing.py` become `upto="reconcile-seal"`.
- `tests/unit/test_skills_reconcile.py` asserted against one skill's prose. Split
  it so each assertion sits with the pass that now owns the rule it checks, and
  keep every assertion scoped with `skills.section_body(skill, "<heading>")` —
  `"refusal" in body.lower()` is vacuous for every conforming skill, because
  `load()` sets `body` to the entire file text and the five headings are mandatory.
- In `tests/toy.py`, `_UPTO_STAGES` becomes:

```python
_UPTO_STAGES: tuple[str, ...] = (
    "intake",
    "extract",
    # Two checkpoints for the reconcile family rather than eight: "reconcile-gaps"
    # is every partial written with no world model yet -- the state the seal and
    # the layer-2 part checkers are tested against -- and "reconcile-seal" is the
    # assembled world model every later stage reads. The intermediate states
    # between passes have no consumer, and a checkpoint nobody stops at is a
    # helper this module already has too many requests for.
    "reconcile-gaps",
    "reconcile-seal",
    "propose",
    "score",
    "instantiate",
    "challenge",
)
```

and in `build_toy_run`, replace the single `write_json(run.world_model, ...)` line:

```python
    parts = split_world_model()
    write_json(run.subjects, parts["subjects"])
    for subject_id, part in parts["contradictions"].items():
        write_json(run.contradiction_part(subject_id), part)
    write_json(run.capabilities_part, parts["capabilities"])
    write_json(run.outcomes_part, parts["outcomes"])
    write_json(run.entities_part, parts["entities"])
    write_json(run.goals_part, parts["goals"])
    write_json(run.gaps_part, parts["gaps"])
    if stop < _UPTO_INDEX["reconcile-seal"]:
        return run

    # Sealed by the real seal, not by writing toy_world_model() here. Same reason
    # intake is real in this builder: the artifact every later stage reads is
    # produced by the code that produces it in a real run, so a defect in the
    # join or the denominator cannot hide behind a hand-written answer.
    from rubrica.reconcile import seal

    sealed, findings = seal(run)
    assert not findings, f"the toy partials must seal cleanly: {findings}"
    assert sealed == run.world_model
```

- [ ] **Step 7: Update both drawings**

`scripts/render-pipeline-diagram.py` — replace the single `reconcile` row in
`ROWS` with eight, keeping the `01` dir band and the existing key names. The first
carries the barrier note, the second the fan-out note:

```python
    dict(
        kind="stage",
        dir="01b",
        name="reconcile-subjects",
        runs="rb-reconcile-subjects",
        art=["01-subjects.json"],
        gates=["validate", "check-refs"],
        barrier="barrier · every extract member has finished",
        note="every claim, assigned to one or more subjects; a cover, not a partition",
    ),
    dict(
        kind="stage",
        dir="01c",
        name="reconcile-contradict",
        runs="rb-reconcile-contradict",
        art=["01-contradictions/<subject_id>.json"],
        gates=["validate", "check-refs"],
        fan="fan-out · one member per subject, at most three at a time",
        note="claim vs claim, across every input; resolutions bind every pass below",
    ),
```

then one row each for `reconcile-capabilities` (`01d`, `01-capabilities.json`),
`reconcile-outcomes` (`01e`, `01-outcomes.json`), `reconcile-entities` (`01f`,
`01-entities.json`), `reconcile-goals` (`01g`, `01-goals.json`),
`reconcile-gaps` (`01h`, `01-gaps.json`), and:

```python
    dict(
        kind="stage",
        dir="01i",
        name="reconcile-seal",
        runs="code · assembles the partials",
        art=["01-world-model.json"],
        gates=["validate", "check-refs"],
        note="joins outcome classes into capabilities; counts the denominator once",
    ),
```

Leave the `Human gate 1` band exactly where it is — immediately below the seal.

`scripts/render-readme-diagram.py` — the `understand` phase's `stages` list only:

```python
        stages=[
            "intake",
            "extract",
            "reconcile-subjects",
            "reconcile-contradict",
            "reconcile-capabilities",
            "reconcile-outcomes",
            "reconcile-entities",
            "reconcile-goals",
            "reconcile-gaps",
            "reconcile-seal",
        ],
```

Then re-render all three, never hand-edit:

```bash
uv run python scripts/render-pipeline-diagram.py
uv run python scripts/render-readme-diagram.py
```

- [ ] **Step 8: Update the documents**

- `docs/concepts/pipeline.md` — the stage list and what each pass does. Say why
  they are separate stages (per-pass repair, per-pass model and effort, per-pass
  observability) and that they are one logical step.
- `docs/concepts/glossary.md` — **subject**, **subject cover**, **partial**,
  **seal**, each naming the pass that writes or consumes it. Update the existing
  `reconcile` entry rather than leaving it describing a stage that is gone.
- `docs/concepts/artifact-contract.md` — the fan-out slice id list gains
  `subject_id` beside `artifact_id` and `scenario_id`.
- `docs/reference/artifacts.md` — already updated in Task 2; re-read it now that
  the stage names exist and fix "written by `reconcile`".
- `docs/guides/running-a-stage-by-hand.md` — seven mentions; the worked example
  needs to dispatch one pass and name the `subject_id` argument for the fan-out.
- `docs/getting-started.md` — one mention.
- `CLAUDE.md` — the stage table's `01b` row becomes the eight rows, and the
  sentence about `rb-orchestrate` dispatching "`extract` through `emit`" still
  holds. **`CLAUDE.md` is not ruff-excluded**, so run `make check` after.

- [ ] **Step 9: Run everything**

Run: `make test && make check && uv run rubrica check-skills; echo "check-skills:$?"`
Expected: green and `check-skills:0`. Expect real work here:
`test_docs_accuracy.py` will name every document still describing the old shape,
and the two diagram byte-compare tests will fail until Step 7's re-render is
committed. Each of those failures is the guard working — fix the document or
re-render, never the assertion.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -S -s -m "feat!: Replace the reconcile stage with a sequence of bounded passes

One dispatch had to hold ~590 claims, plan an eight-collection merge, and then
write -- the shape most exposed to the gateway's ~300s idle reset, which kills a
stream that has produced no bytes regardless of how long a producing stream is
allowed to run. Six prompt passes and a code seal replace it. Every pass still
reads all of 01-claims/, so the barrier property is untouched: the split is on
output, not on claims.

Separate stages rather than one skill branching on a slice id, because
check-skills binds one skill file to one stage and manifest.stages records model,
effort and digest per stage -- which is what lets a think-heavy pass carry a
different budget from a mechanical one. Atomic because that binding is
one-to-one: a partial rename makes check-skills reject every correctly named
skill, as this repo learned during the tg- to rb- rename.

01-world-model.json keeps its path, schema and byte shape, so propose, score,
instantiate, the golden toy world and the committed live recordings are all
untouched. Human gate 1 stays immediately after the seal.

rb-reconcile/SKILL.md is retired; rb-reconcile/exercise.md stays exactly where it
is, with a SUPERSEDED.md saying what it records. Relocating it into a new pass
would assert that a dispatch of that pass did what the superseded stage did.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 8: Gate 1's reading surface, and the orchestrator's sequence

**Files:**
- Modify: `src/rubrica/brief.py` (`_gate_1`)
- Modify: `src/rubrica/skills/rb-orchestrate/SKILL.md`
- Test: `tests/unit/test_brief.py`

**Interfaces:**
- Consumes: `refs`-adjacent readers already in `brief.py` (`_quietly`, `_dicts`),
  `RunPaths` members from Task 2.
- Produces: no new public function; `gate_brief(run, 1)` gains three lines.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_brief.py`:

```python
def test_gate_one_shows_the_cover_and_the_contradiction_tally(tmp_path):
    """Gate 1 is where a human sees the contradictions beside what was modelled.
    That reading is the only instrument for cross-pass incoherence -- a later pass
    quietly settling what an earlier one recorded unresolved -- because whether a
    claim *supports* an element is semantic and layer 2 is forbidden to guess.
    """
    from rubrica.brief import gate_brief

    run = build_toy_run(tmp_path, upto="reconcile-seal")
    text = gate_brief(run, 1)

    assert "subjects" in text.lower()
    assert "unresolved" in text.lower()


def test_gate_one_still_reads_on_a_run_with_no_partials(tmp_path):
    """A report always exits clean on a readable run. gate-brief is a report, not
    a gate, and a missing partial must not make it raise."""
    from rubrica.brief import gate_brief

    run = build_toy_run(tmp_path, upto="extract")
    assert gate_brief(run, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_brief.py -k gate_one -v`
Expected: FAIL on the missing text.

- [ ] **Step 3: Extend `_gate_1`**

Insert this block in `src/rubrica/brief.py` immediately after the
`lines = [f"GATE 1 -- {run.root}", ...]` assignment and before the claim
utilisation block, so the sweep is the first thing read. Everything goes through
`_quietly`, `_mapping` and `_dicts` for the reason the rest of this module does:
`gate-brief` is a report, it always exits 0 on a readable run, and a hand-edited
partial must not turn it into a fabricated `[internal]` finding.

```python
    # The reconcile sweep, read before anything derived from it. Cross-pass
    # incoherence -- a later pass modelling what rb-reconcile-contradict recorded
    # `unresolved` -- has no mechanical check and must not be given a fake one:
    # whether a claim *supports* an element is semantic, which is the hole layer 2
    # is forbidden to paper over. This report is the instrument, so it puts the
    # contradictions in front of the human who is about to read what was modelled.
    cover = _mapping(_quietly(run.subjects))
    subjects = _dicts(cover.get("subjects"))
    covered = {cid for subject in subjects for cid in _as_list(subject.get("claims"))}
    lines.append("Reconcile sweep")
    if subjects:
        lines.append(f"  {len(subjects)} subjects over {len(covered)} claims")
    else:
        lines.append("  (no subject cover yet; nothing to report)")

    swept, found = 0, []
    for path in list_json(run.contradictions_dir):
        part = _mapping(_quietly(path))
        swept += 1
        found.extend(_dicts(part.get("contradictions")))
    # Both numbers, always. "12 subjects swept, 0 contradictions" is a strong
    # claim about the corpus and has to be legible as one -- a brief that printed
    # only a non-empty list would render a sweep that found nothing anywhere as
    # silence, which is the reading this stage most needs a human to question.
    lines.append(f"  {swept} subjects swept, {len(found)} contradictions recorded")
    if found:
        tally: dict[str, int] = {}
        for contradiction in found:
            resolution = contradiction.get("resolution")
            key = resolution if isinstance(resolution, str) else "(no resolution)"
            tally[key] = tally.get(key, 0) + 1
        # unresolved first and always shown, including as a zero: it is the value
        # under the most pressure to be dropped by a pass that wants to look
        # decisive, so a run with none of them should be visibly odd rather than
        # merely unremarked.
        ordered = ["unresolved", *sorted(k for k in tally if k != "unresolved")]
        lines.append(
            "  " + ", ".join(f"{key}: {tally.get(key, 0)}" for key in ordered)
        )
    lines.append("")
```

`_as_list` and `list_json` may not be imported in `brief.py` yet — add them from
`rubrica.refs` and `rubrica.paths` respectively, matching whichever the module
already uses for its other helpers.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_brief.py -v`
Expected: PASS.

- [ ] **Step 5: Update `rb-orchestrate/SKILL.md`**

It dispatches the prompt stages from `extract` through `emit`, so the sequence in
its prose becomes the eight new stage names in order. Three things it must say:

- **The `reconcile-contradict` fan-out runs at most three members at a time.**
  Envoy returns `upstream connect error ... reset reason: connection timeout`
  intermittently at five or more concurrent streaming requests. Unrelated to the
  301s reset, and real.
- **`check-refs` after `reconcile-contradict` is meaningful only once every member
  has finished**, exactly as for `challenge`: `refs.check_contradiction_parts`
  reports every subject without a part from the moment the directory exists.
- **`reconcile-seal` is code, invoked as `rubrica reconcile-seal --run <run>`**, and
  takes `--denominator-version` only when an amendment has been decided and
  recorded in `decisions.md`.

It still holds gates 1 through 3, and gate 1 still sits after the seal.

- [ ] **Step 6: Run the gates and commit**

```bash
make test && make check && uv run rubrica check-skills; echo "check-skills:$?"
git add src/rubrica/brief.py src/rubrica/skills/rb-orchestrate/SKILL.md tests/unit/test_brief.py
git commit -S -s -m "feat: Show the cover and the contradiction tally at gate 1

Cross-pass incoherence -- a later pass quietly modelling what an earlier one
recorded unresolved -- has no mechanical check and must not be given a fake one:
whether a claim supports an element is semantic, and that is the hole layer 2 is
forbidden to paper over. The instrument is a human at gate 1 reading the
contradictions beside what was modelled, so the brief now carries the cover's
size, the per-subject sweep tally and the resolution tally with unresolved named.

Read through _quietly and _dicts like every other line in this module: a report
always exits clean on a readable run, and a hand-edited partial must not turn one
into a fabricated internal finding.

rb-orchestrate dispatches the new sequence, holds the contradict fan-out to three
concurrent members against the envoy 503 that is unrelated to the 301s reset, and
invokes the seal as code.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 9: Record what this design costs

Three entries are owed. An entry that is not written is a defect someone will
rediscover and re-litigate — this repo has lost two fix rounds to exactly that.

**Files:**
- Modify: `docs/design/limitations.md`

- [ ] **Step 1: Write the three entries**

Each in the house shape: what is wrong or missing, then the ruling that parked it.

1. **The subject cover can file two disagreeing claims under different subjects,
   so a contradiction can be missed.** State how this differs from triage's digest
   rather than claiming kinship with it: triage's loss is a recorded decision on a
   named candidate that a human can overrule at gate 0, while a cross-subject pair
   is an absence. Then state why it is still the right shape — the cover is total
   and mechanically checked for totality, over-assignment is instructed, and the
   cover is readable at gate 1 — and why the rejected alternative was worse: a
   code-proposed pair filter drops one of ~n²/2 pairs that appear nowhere on disk,
   and compounded with triage it costs attribution, so a thin contradiction set
   could no longer be traced to a stage.
2. **`denominator` is written by code, so it is no longer a checkable claim about
   a prompt's output.** `refs.check_world_model` still recomputes it, but against a
   number `reconcile-seal` computed, which makes that check an identity. Ruling:
   arithmetic is not judgment, so this is the right trade — but it is one fewer
   observation and should not be rediscovered as a gap in coverage.
3. **Whether the gateway's contended connection pool is per-API-key or global is
   unknown.** It decides whether the `reconcile-contradict` fan-out degrades other
   people's runs, which is why it is capped at three rather than at whatever this
   machine can drive. Attributed, not confirmed: nobody has read the envoy config.

- [ ] **Step 2: Also record what must still be measured**

Add, as its own entry: the design's central premise — that a bounded pass needs a
shallower think, so time to first byte stays under 300s — **is a hypothesis, not a
measurement.** Nothing in the repository measures TTFB. If a pass still stalls,
the split has narrowed the problem to one pass rather than solved it, which is
progress but is not the same claim. Name the second untested premise beside it:
the 45% measurement behind the outcomes pass's quantification was taken with the
capabilities in the same turn, and reading them from a file is plausibly stronger
but is not known to be.

- [ ] **Step 3: Run the gates and commit**

```bash
make test && make check
git add docs/design/limitations.md
git commit -S -s -m "docs: Record what staging reconcile costs, and what is still unmeasured

Four entries. The subject cover can still miss a cross-subject contradiction, and
the entry says how that differs from triage's digest rather than claiming kinship:
triage declines a named candidate a human can overrule, while a cross-subject
pair is an absence. It also records why the rejected pair-filter alternative was
worse -- compounded with triage it costs attribution, so a thin contradiction set
could no longer be traced to a stage.

The denominator written by code is one fewer checkable claim about a prompt's
output, and check_world_model recomputing it is now an identity. Right trade,
recorded so it is not rediscovered as a coverage gap.

And the two premises nobody has measured: that a bounded pass keeps time to first
byte under 300s, and that quantifying over a capability list read from a file is
at least as strong as over one just written. Both are hypotheses this design
rests on.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## After the plan

Two things this plan deliberately does **not** do, both because they need a real
dispatch and cost money:

- **The seven `exercise.md` records.** Each pass owes one, stating what **one real
  dispatch measurably did** — never a reasoned number presented as an observed
  one. They cannot be written before the passes are dispatched.
- **Measuring time to first byte per pass**, which is the only thing that confirms
  the premise in Task 9 Step 2.

The one open editorial point from the spec stays open and no test can rule on it:
whether `reconcile-goals` and `reconcile-entities` should be a single pass. They are
separate here because `goals` is half the frozen denominator and deserves its own
artifact and its own gate-1 visibility.
