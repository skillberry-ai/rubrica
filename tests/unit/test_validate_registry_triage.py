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
from tests.builders import (
    minimal_adoptions,
    minimal_audit,
    minimal_dispositions_part,
    minimal_objective,
)
from tests.toy import split_world_model

# The five kinds this task adds. A literal tuple rather than a slice of
# ARTIFACT_SCHEMAS: the point of several tests below is to notice if one of
# these stopped existing, which a set difference computed from the same
# dict under test could not do.
PART_KINDS = ("slices", "objective", "dispositions-part", "audit", "adoptions")


# Every *substantive* cross-file $ref site among the five part schemas -- one
# row per place a part schema points at one of triage-0.1.json's $defs rather
# than restating it. `slices` is absent: every $ref it carries points at
# $defs/id, which every other site's id fields already exercise too, and the
# id pattern is already covered by test_schemas_instance's ref-following
# anchor check.
#
# Each row's `mutate` drops a field that exists *only* in the shared $def's
# `required` list -- never a constraint the part schema also states locally
# (additionalProperties: false would reject an unknown field regardless of
# what $ref pointed where, which proves nothing about the $ref itself). A
# missing-`weight`/`statement`/`acceptance`/`authority` document is invalid
# *only* because the $ref resolved to a $def that says so.
def _full_projection(**over):
    payload = {
        "projection_id": "prj-1",
        "closes": ["def-1"],
        "sources": [{"candidate_id": "aap2-api", "digest_note": "n"}],
        "wanted": {"kind": "other", "statement": "s", "why": "w"},
        "method": {"confidence": "high", "steps": ["look"]},
        "acceptance": {"classifies_as": "other", "prose": "p"},
        "boundary": "b",
    }
    payload.update(over)
    return payload


def _full_adoption(**over):
    payload = {
        "candidate_id": "aap2-api",
        "disposition": {
            "candidate_id": "aap2-api",
            "disposition": "admit",
            "reason": "a human overrode triage's decline at gate 0",
            "authority": "human",
        },
        "projection_id": "prj-1",
        "closed_deficiency_ids": ["def-1"],
    }
    payload.update(over)
    return payload


REF_SITES = [
    {
        "id": "dispositions-part.dispositions[]->disposition",
        "kind": "dispositions-part",
        "path": ("properties", "dispositions", "items"),
        "build": lambda: minimal_dispositions_part(),
        "mutate": lambda doc: doc["dispositions"][0].pop("authority"),
        "dropped_field": "authority",
    },
    {
        "id": "objective.surfaces[]->surface",
        "kind": "objective",
        "path": ("properties", "objective_review", "properties", "surfaces", "items"),
        "build": lambda: minimal_objective(),
        "mutate": lambda doc: doc["objective_review"]["surfaces"][0].pop("weight"),
        "dropped_field": "weight",
    },
    {
        "id": "audit.deficiencies[]->deficiency",
        "kind": "audit",
        "path": ("properties", "deficiencies", "items"),
        "build": lambda: minimal_audit(
            deficiencies=[{"deficiency_id": "def-1", "subject": "s", "statement": "st"}]
        ),
        "mutate": lambda doc: doc["deficiencies"][0].pop("statement"),
        "dropped_field": "statement",
    },
    {
        "id": "audit.projections[]->projection",
        "kind": "audit",
        "path": ("properties", "projections", "items"),
        "build": lambda: minimal_audit(projections=[_full_projection()]),
        "mutate": lambda doc: doc["projections"][0].pop("acceptance"),
        "dropped_field": "acceptance",
    },
    {
        "id": "adoptions.adoptions[].disposition->disposition",
        "kind": "adoptions",
        "path": ("properties", "adoptions", "items", "properties", "disposition"),
        "build": lambda: minimal_adoptions(adoptions=[_full_adoption()]),
        "mutate": lambda doc: doc["adoptions"][0]["disposition"].pop("authority"),
        "dropped_field": "authority",
    },
]


def _invalid_document_for(site):
    """The site's minimal valid document, with its one shared-$def-only field dropped."""
    doc = site["build"]()
    site["mutate"](doc)
    return doc


def _set_at(schema, path, value):
    """schema[path[0]][path[1]]...[path[-1]] = value, in place."""
    node = schema
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


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


@pytest.mark.parametrize("site", REF_SITES, ids=[s["id"] for s in REF_SITES])
def test_a_ref_site_rejects_what_its_shared_def_requires(site, tmp_path):
    """The $ref is load-bearing at every site, not merely at dispositions-part's.

    Each site's document is invalid *only* because the field dropped in
    `mutate` is required by the $def the $ref points at -- nothing else in
    the part schema states that requirement. A refactor that pointed a site
    at the wrong $def (audit's projection slot aimed at #/$defs/deficiency,
    say) would still resolve cleanly and would still reject *some* malformed
    document, but not this one: it would reject a document missing
    `deficiency_id`, not one missing `acceptance`. Asserting the dropped
    field's name appears in the finding, not just that findings is non-empty,
    is what tells the two apart.
    """
    path = tmp_path / "doc.json"
    write_json(path, _invalid_document_for(site))
    findings = validate_artifact(path, site["kind"])
    assert findings, f"{site['id']}: dropping {site['dropped_field']!r} was wrongly accepted"
    field = site["dropped_field"]
    assert any(f"'{field}' is a required property" in f.message for f in findings), (
        f"{site['id']}: expected a finding naming {field!r}, got "
        f"{[f.message for f in findings]} -- findings being non-empty is not enough, since a "
        "$ref aimed at the wrong $def would also produce findings, just not this one"
    )


@pytest.mark.parametrize("site", REF_SITES, ids=[s["id"] for s in REF_SITES])
def test_a_permissive_stand_in_at_each_ref_site_would_wrongly_accept_the_document(
    site, tmp_path, monkeypatch
):
    """Evidence every site's $ref is load-bearing, not decorative.

    Swap *that one site's* $ref for a permissive {"type": "object"} -- the
    shape an unchecked $ref would functionally be -- and rerun the exact
    document the test above correctly rejects for this site. If it now
    passes, the earlier rejection really was coming from the $ref target's
    `required` list, and not from some other constraint (additionalProperties,
    minItems, ...) on the part schema that would have rejected the document
    regardless of what the $ref pointed at.
    """
    _copy_schemas_to(tmp_path)
    filename = ARTIFACT_SCHEMAS[site["kind"]]
    schema = read_json(tmp_path / filename)
    _set_at(schema, site["path"], {"type": "object"})
    write_json(tmp_path / filename, schema)

    doc_path = tmp_path / "doc.json"
    write_json(doc_path, _invalid_document_for(site))

    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    findings = validate_artifact(doc_path, site["kind"])
    assert findings == [], (
        f"{site['id']}: the permissive stand-in should have wrongly accepted the "
        f"{site['dropped_field']!r}-missing document; got {[f.message for f in findings]} "
        "instead, so this site's earlier rejection was not actually coming from the $ref"
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


# The reconcile partials whose pass owns a claim kind, and so must account for
# every input the manifest names. A literal tuple for the same reason PART_KINDS
# above is one: a set computed from ARTIFACT_SCHEMAS could not notice one of
# these ceasing to exist. gaps-part is deliberately absent --
# rb-reconcile-gaps owns no claim kind, and a gap asserts what no input
# contains, so no output shape can force its read coverage.
_INPUTS_SEEN_PARTS = (
    "capabilities-part",
    "entities-part",
    "outcomes-part",
    "goals-part",
    "services-part",
)

# Part kind -> the key split_world_model files that partial under.
_PART_FIXTURE_KEYS = {
    "capabilities-part": "capabilities",
    "entities-part": "entities",
    "outcomes-part": "outcomes",
    "goals-part": "goals",
    "services-part": "services",
}


def _minimal_part(kind):
    """The golden partial for `kind`, taken from the fixture.

    A thin lookup rather than a second hand-authored part document: several
    tests in this module exist to notice when a schema and its fixture drift,
    and a local copy of the document would be the drift instead of the detector.
    """
    return split_world_model()[_PART_FIXTURE_KEYS[kind]]


@pytest.mark.parametrize("kind", _INPUTS_SEEN_PARTS)
def test_a_partial_without_inputs_seen_is_rejected(tmp_path, kind):
    """Every pass that owns a claim kind must account for every input.

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
