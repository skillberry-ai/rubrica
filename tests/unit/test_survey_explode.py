"""When a file is many candidates rather than one.

The parsec run's 130-trace MLflow capture was split by hand and seven elements
picked. This is that split, and only that split: selecting among the elements is
rb-triage's judgment, not this function's.
"""

from __future__ import annotations

from rubrica import survey


def _traces(n, *, drop_key_on_last=False):
    out = []
    for i in range(n):
        element = {"trace_id": f"tr-{i}", "status": "OK", "spans": [], "extra": i}
        if drop_key_on_last and i == n - 1:
            del element["extra"]
        out.append(element)
    return out


def test_a_homogeneous_array_becomes_one_candidate_per_element():
    exploded = survey.explode(_traces(130))
    assert exploded is not None
    assert len(exploded) == 130
    assert exploded[0][0] == "/0"
    assert exploded[47][0] == "/47"
    assert exploded[47][1]["trace_id"] == "tr-47"


def test_an_optional_field_does_not_defeat_homogeneity():
    """Key-set intersection, not identity.

    Measured on the real parsec capture: 130 elements, 12 common keys, zero
    union-only keys -- so identity would have worked there. The tolerant rule
    costs nothing and survives the capture where one element lacks a field.
    """
    exploded = survey.explode(_traces(130, drop_key_on_last=True))
    assert exploded is not None and len(exploded) == 130


def test_an_object_of_objects_explodes_by_key():
    payload = {
        "t1": {"a": 1, "b": 2, "c": 3},
        "t2": {"a": 4, "b": 5, "c": 6},
        "t3": {"a": 7, "b": 8, "c": 9},
    }
    exploded = survey.explode(payload)
    assert exploded is not None
    assert [pointer for pointer, _ in exploded] == ["/t1", "/t2", "/t3"]


def test_a_two_element_array_is_left_whole():
    """Exploding a small config array produces candidates nobody wanted."""
    assert survey.explode(_traces(2)) is None


def test_a_heterogeneous_array_is_left_whole():
    """Three keys in common is the floor; unrelated objects share fewer."""
    assert survey.explode([{"a": 1}, {"b": 2}, {"c": 3}]) is None


def test_scalars_arrays_of_scalars_and_openapi_documents_are_left_whole():
    """Only containers of independent records explode.

    An OpenAPI document is one contract with many paths, not many contracts --
    splitting it would hand rb-extract fragments that cannot be read alone.
    """
    assert survey.explode(42) is None
    assert survey.explode(["a", "b", "c", "d"]) is None
    assert survey.explode({"openapi": "3.1.0", "paths": {}, "info": {}}) is None


def test_a_pointer_escapes_a_slash_in_a_key():
    """RFC 6901: ~1 for /, ~0 for ~. refs.resolve_pointer already expects this,
    and a raw slash would make the pointer address a level that does not exist."""
    payload = {
        "a/b": {"x": 1, "y": 2, "z": 3},
        "c": {"x": 1, "y": 2, "z": 3},
        "d": {"x": 1, "y": 2, "z": 3},
    }
    exploded = survey.explode(payload)
    assert exploded is not None
    assert "/a~1b" in [pointer for pointer, _ in exploded]
