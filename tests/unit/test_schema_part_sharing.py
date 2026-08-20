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
