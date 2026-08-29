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
    ("services-part-0.1.json", "service"),
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


def _normalise_refs(node):
    """`node` with every cross-file ref into world-model rewritten to a local one.

    `world-model-0.1.json#/$defs/param` and `#/$defs/param` name the same element
    once validate._schema_registry has resolved them, so normalising is what lets
    the two definitions be compared for equality at all. Without it `params` --
    whose ref is nested inside `items`, not at the top of the property -- reads as
    a difference when it is the same array of the same element.
    """
    if isinstance(node, dict):
        return {
            key: (
                value.removeprefix("world-model-0.1.json")
                if key == "$ref" and isinstance(value, str)
                else _normalise_refs(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_normalise_refs(item) for item in node]
    return node


def _pure_literals(definition: dict) -> set[str]:
    """Properties of `definition` carrying no `$ref` at any depth.

    These are the sanctioned duplication in the strict sense: nothing links them
    to the world model, so only a test can hold them in step.
    """
    return {
        name for name, shape in definition["properties"].items() if "$ref" not in json.dumps(shape)
    }


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


def test_the_restated_properties_are_identical_and_not_merely_identically_named():
    """The name sets above are not enough, and the gap is not hypothetical.

    `operation` and `confidence` are copied subschemas, not `$ref`s, so their
    *contents* are the sanctioned duplication -- and capabilities-part-0.1.json's
    own description, docs/reference/artifacts.md and this module's docstring all
    claim the duplication cannot drift silently. On names alone that claim was
    false for exactly the two properties it was written about: a fourth value in
    world-model's `confidence` enum would leave every name check passing while
    capabilities-part rejected a document reconcile-seal accepts, failing the
    pass's own gate for a reason nothing explains.

    Compares whole property shapes with refs normalised, which is stronger than
    checking the two literals alone: the wrapper around a shared element is
    duplicated too, so a `minItems` added to world-model's `params` is caught here
    as well.

    Measured red in both directions by adding a fourth value to $defs/capability's
    `confidence` enum and not to the partial's, and by the reverse; and by
    tightening `operation` in one file only.
    """
    world = _schema("world-model-0.1.json")["$defs"]["capability"]
    part = _schema("capabilities-part-0.1.json")["$defs"]["capability_core"]

    expected = _normalise_refs(world)["properties"]
    expected.pop("outcome_classes", None)
    assert _normalise_refs(part)["properties"] == expected, (
        "capability_core's properties no longer match world-model-0.1.json's "
        "$defs/capability, element for element"
    )

    # Recorded rather than derived, so converting one of these to a $ref -- or
    # adding a third literal -- is a visible decision rather than a quiet one.
    # If this set ever empties, the duplication is gone and the test above is
    # holding identically; delete it then rather than leave it passing on {}.
    assert _pure_literals(part) == {"operation", "confidence"}, (
        "the set of properties capability_core restates outright has changed; "
        "check that the duplication is still what this test compensates for"
    )


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
