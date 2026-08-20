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
