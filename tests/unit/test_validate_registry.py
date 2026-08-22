"""The registry that resolves the triage part schemas' cross-file $refs.

Every part schema (slices, objective, dispositions-part, audit, adoptions)
$refs triage-0.1.json's $defs instead of restating a disposition, a surface,
a deficiency, or a projection. That only works if _validator_for's compiled
validator carries a referencing.Registry built from every schema file in the
active schema_dir() -- these tests are what stands behind "instead of
restating them" actually holding, rather than the part schemas quietly
accepting whatever additionalProperties: false alone would let through.
"""

from __future__ import annotations

import pytest

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.validate import ARTIFACT_SCHEMAS, schema_dir, validate_artifact
from tests.builders import minimal_audit, minimal_dispositions_part

# The five kinds this task adds. A literal tuple rather than a slice of
# ARTIFACT_SCHEMAS: the point of several tests below is to notice if one of
# these stopped existing, which a set difference computed from the same
# dict under test could not do.
PART_KINDS = ("slices", "objective", "dispositions-part", "audit", "adoptions")


def _copy_schemas_to(target):
    """A private schema_root a test can then edit without touching the shipped copy."""
    for path in schema_dir().glob("*.json"):
        (target / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def test_every_new_kind_has_a_schema_that_loads():
    for kind in PART_KINDS:
        filename = ARTIFACT_SCHEMAS[kind]
        schema = read_json(schema_dir() / filename)
        assert schema["$id"] == filename


def test_a_part_schema_resolves_its_cross_file_ref_without_network(tmp_path):
    """dispositions-part's dispositions items $ref triage-0.1.json#/$defs/disposition.

    A minimal_dispositions_part() document is sliced out of minimal_triage(),
    so its one disposition is exactly the shape the shared $def accepts. If
    the registry did not resolve the cross-file $ref at all, jsonschema would
    raise a resolution error before ever reaching iter_errors -- so this also
    covers "the $ref resolves", not just "the document is accepted".
    """
    path = tmp_path / "dispositions-part.json"
    write_json(path, minimal_dispositions_part())
    assert validate_artifact(path, "dispositions-part") == []


def test_a_part_schema_rejects_a_disposition_the_shared_def_rejects(tmp_path):
    """The other half: the $ref is load-bearing, not merely resolvable.

    triage-0.1.json#/$defs/disposition requires authority. Dropping it here
    must fail for exactly the reason it would fail inside a sealed
    00-triage.json -- the two are validated against the same $def, not two
    copies of a shape that could drift apart.
    """
    payload = minimal_dispositions_part()
    del payload["dispositions"][0]["authority"]
    path = tmp_path / "dispositions-part.json"
    write_json(path, payload)
    findings = validate_artifact(path, "dispositions-part")
    assert findings
    assert any("'authority' is a required property" in f.message for f in findings), [
        f.message for f in findings
    ]


def test_a_permissive_cross_file_ref_would_wrongly_accept_the_missing_authority(
    tmp_path, monkeypatch
):
    """Evidence the $ref above is load-bearing, not decorative.

    Swap dispositions-part-0.1.json's items $ref for a permissive
    {"type": "object"} -- the shape an unchecked $ref would functionally be
    -- and rerun the exact document the previous test correctly rejects. If
    it now passes, the previous test's rejection really was coming from
    triage-0.1.json#/$defs/disposition's `required: [..., "authority"]`, and
    not from some other constraint (additionalProperties, minItems, ...)
    that would have rejected it regardless of what the $ref pointed at.
    """
    _copy_schemas_to(tmp_path)
    part_schema = read_json(tmp_path / ARTIFACT_SCHEMAS["dispositions-part"])
    part_schema["properties"]["dispositions"]["items"] = {"type": "object"}
    write_json(tmp_path / ARTIFACT_SCHEMAS["dispositions-part"], part_schema)

    payload = minimal_dispositions_part()
    del payload["dispositions"][0]["authority"]
    doc_path = tmp_path / "dispositions-part.json"
    write_json(doc_path, payload)

    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    findings = validate_artifact(doc_path, "dispositions-part")
    assert findings == [], (
        "the permissive stand-in should have wrongly accepted the missing-authority "
        f"document; got {[f.message for f in findings]} instead, which means the earlier "
        "rejection was not actually coming from the $ref target"
    )


def test_the_registry_still_honours_RUBRICA_SCHEMA_DIR(tmp_path, monkeypatch):
    """A candidate schema set is validated against, not the shipped one.

    Copies every shipped schema into tmp_path, then tightens the copy of
    audit-0.1.json's projections item so it additionally requires a sentinel
    field no shipped triage-0.1.json#/$defs/projection has. If the registry
    were built once from the real schema_dir() and cached across the
    override -- the exact bug _schema_registry's cache-key docstring warns
    about -- this document would validate clean under the override too.
    """
    _copy_schemas_to(tmp_path)
    audit_schema = read_json(tmp_path / ARTIFACT_SCHEMAS["audit"])
    audit_schema["properties"]["projections"]["items"] = {
        "allOf": [
            {"$ref": "triage-0.1.json#/$defs/projection"},
            {"type": "object", "required": ["sentinel"]},
        ]
    }
    write_json(tmp_path / ARTIFACT_SCHEMAS["audit"], audit_schema)

    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    payload = minimal_audit(
        projections=[
            {
                "projection_id": "prj-1",
                "closes": ["def-1"],
                "sources": [{"candidate_id": "aap2-api", "digest_note": "n"}],
                "wanted": {"kind": "other", "statement": "s", "why": "w"},
                "method": {"confidence": "high", "steps": ["look"]},
                "acceptance": {"classifies_as": "other", "prose": "p"},
                "boundary": "b",
            }
        ]
    )
    doc_path = tmp_path / "audit.json"
    write_json(doc_path, payload)
    findings = validate_artifact(doc_path, "audit")
    assert findings, "the override schema_dir()'s tightened $def was not consulted"
    assert any("sentinel" in f.message for f in findings), [f.message for f in findings]


def test_an_unreadable_schema_dir_exits_two_not_one(tmp_path, monkeypatch):
    """A misconfigured RUBRICA_SCHEMA_DIR is a harness problem, not a stage one.

    validate_artifact does not itself catch ArtifactError from schema loading
    (only from the artifact being validated) -- it propagates uncaught to
    cli.py's (OSError, UsageError, ArtifactError, UnknownStage) catch, which
    maps to exit 2. Exercised here as the raised exception directly, since
    this module does not go through cli.main(); the CLI-level exit code was
    confirmed by hand against `rubrica validate --run ... --stage triage`
    with RUBRICA_SCHEMA_DIR pointed at an empty directory, and matches the
    brief's expectation -- deviating only in exception type, ArtifactError
    rather than UsageError, since schema_dir() itself never raises UsageError
    and there is nothing here for validate.py to catch and re-wrap.
    """
    empty_dir = tmp_path / "no-schemas-here"
    empty_dir.mkdir()
    doc_path = tmp_path / "dispositions-part.json"
    write_json(doc_path, minimal_dispositions_part())

    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(empty_dir))
    with pytest.raises(ArtifactError):
        validate_artifact(doc_path, "dispositions-part")


def test_an_unreadable_schema_file_is_an_oserror_not_a_finding(tmp_path, monkeypatch):
    """chmod 000 on the schema itself -- not the document -- is the same shape.

    read_json distinguishes "missing" from "malformed" but not "unreadable";
    a permission-denied schema file surfaces as a bare PermissionError out of
    Path.read_text, an OSError, which still reaches cli.py's exit-2 catch, just
    via a different member of that tuple than ArtifactError. Both this and the
    ArtifactError case above are asserted so a future change that wraps one and
    not the other is caught immediately, rather than only in a real deployment.
    """
    _copy_schemas_to(tmp_path)
    locked = tmp_path / ARTIFACT_SCHEMAS["dispositions-part"]
    locked.chmod(0o000)
    doc_path = tmp_path / "dispositions-part.json"
    write_json(doc_path, minimal_dispositions_part())

    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    try:
        with pytest.raises(OSError):
            validate_artifact(doc_path, "dispositions-part")
    finally:
        locked.chmod(0o644)


def test_an_unreadable_sibling_schema_reached_only_via_the_registry_glob(tmp_path, monkeypatch):
    """The document's own schema is readable; triage-0.1.json (the $ref target) is not.

    dispositions-part-0.1.json itself opens fine -- read_json in _validator_for
    never touches triage-0.1.json directly -- so this failure can only come
    from inside _schema_registry's glob-and-load loop, proving that loop's own
    read is on the same unreadable-input hook as the direct read above, not
    exempt from it because it is one step removed from the artifact kind asked
    for.
    """
    _copy_schemas_to(tmp_path)
    locked = tmp_path / ARTIFACT_SCHEMAS["triage"]
    locked.chmod(0o000)
    doc_path = tmp_path / "dispositions-part.json"
    write_json(doc_path, minimal_dispositions_part())

    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    try:
        with pytest.raises(OSError):
            validate_artifact(doc_path, "dispositions-part")
    finally:
        locked.chmod(0o644)
