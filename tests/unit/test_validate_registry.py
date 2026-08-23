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
from rubrica.artifacts import ArtifactError, write_json
from rubrica.cli import main

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
    """`chmod 000` on the *own* schema file that `_validator_for`'s direct
    `read_json(schema_root / filename)` reads (validate.py:94, which runs before
    `_schema_registry` is ever called) must still surface as a filesystem
    problem, not a stage defect.

    This does not reach `_schema_registry` -- kind="world-model" makes the
    unreadable file the same one that direct read already opens, so this pins
    the pre-existing single-file read path, unrelated to the registry this
    task adds. `test_a_sibling_schemas_unreadability_is_not_a_stage_defect`
    below is the one that reaches the registry's own glob-and-read.
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


def test_a_sibling_schemas_unreadability_is_not_a_stage_defect(tmp_path, monkeypatch):
    """The registry-specific case. `_schema_registry` globs and reads *every*
    `*.json` in the directory (validate.py's registry-building loop), not only
    the one file `_validator_for`'s direct read targets -- so it widens the
    surface on which a filesystem problem can occur to files a given kind's own
    schema never mentions.

    Validates kind="manifest", whose own schema file stays readable and has no
    `$ref` into world-model-0.1.json (checked: only local `#/$defs/...` refs),
    while a *different* file in the same directory, world-model-0.1.json, is
    chmod'd 0. Nothing about compiling or running the manifest validator should
    ever need to open that file directly -- if it still raises, the raise came
    from the registry's unconditional glob, not from any read `_validator_for`
    already did before this task. `read_json` (artifacts.py) catches only
    FileNotFoundError and JSONDecodeError, so the PermissionError here
    propagates raw as OSError, which cli.py's catch-all maps to exit 2 -- not a
    returned Finding, which would be exit 1 and would blame the manifest
    document for a filesystem problem it has nothing to do with.

    Measured both directions per this repo's discipline (see
    task-1-report.md, "Fix round 1"): red with the registry removed from
    _validator_for (nothing then reads world-model-0.1.json while validating
    "manifest", so nothing raises and the test fails on the missing
    exception), green with it restored.
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
            validate.validate_artifact(doc, "manifest")
    finally:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)


def test_an_unreadable_schema_directory_is_not_a_stage_defect(tmp_path, monkeypatch):
    """RUBRICA_SCHEMA_DIR pointing somewhere with no schemas must raise
    ArtifactError, which cli.py maps to exit 2. This does not reach
    _schema_registry either: _validator_for's own direct
    read_json(schema_root / "world-model-0.1.json") raises ArtifactError (via
    FileNotFoundError, since the directory is empty) before _schema_registry
    is ever called, so this pins that pre-existing direct read, not the
    registry's glob. `test_a_sibling_schemas_unreadability_is_not_a_stage_defect`
    above is the one that reaches the registry's own glob-and-read.
    """
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    doc = tmp_path / "probe.json"
    doc.write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactError):
        validate.validate_artifact(doc, "world-model")


def test_an_incomplete_schema_directory_is_not_a_stage_defect(tmp_path, monkeypatch):
    """A schema dir holding a partial's schema but *not* the one it `$ref`s.

    This module's docstring names the failure the registry closed. The registry
    closes it only for a *complete* schema directory: with world-model-0.1.json
    absent, the `$ref` compiles fine (resolution is lazy) and raises
    `jsonschema.exceptions._WrappedReferencingError` from inside `iter_errors`
    -- outside cli.py's catch tuple, so it reached the catch-all as exit 1 with
    an `[internal]` finding against the run root, telling the orchestrator to
    repair an artifact that is fine.

    Measured both directions at the CLI before this test was written: with the
    `except Unresolvable` arm removed, `rubrica validate --stage
    reconcile-capabilities` printed the traceback plus
    `[internal] <run root>: validate raised _WrappedReferencingError` and exited
    1; with it, exit 2 and one `error:` line naming the schema directory.

    The message must name the **schema directory**, because that is the thing
    that is misconfigured -- naming the document would be the wrong-artifact
    failure this repo already has a rule against.
    """
    from tests.toy import split_world_model

    (tmp_path / "capabilities-part-0.1.json").write_text(
        (validate.schema_dir() / "capabilities-part-0.1.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    doc = tmp_path / "01-capabilities.json"
    doc.write_text(json.dumps(split_world_model()["capabilities"]), encoding="utf-8")

    with pytest.raises(ArtifactError) as caught:
        validate.validate_artifact(doc, "capabilities-part")
    assert str(tmp_path) in str(caught.value)
    # The unresolved reference itself stays visible: a human fixing
    # RUBRICA_SCHEMA_DIR needs to know *which* schema file is missing.
    assert "world-model-0.1.json" in str(caught.value)


def test_an_incomplete_schema_directory_exits_2_at_the_cli(tmp_path, monkeypatch, capsys):
    """The same misconfiguration through `main`, where the contract is stated.

    A `1` is a repairable stage defect and costs the orchestrator its one repair
    attempt; a misconfigured run is a `2`, which retrying cannot help. Held at
    the CLI as well as at validate_artifact because the mapping from
    ArtifactError to 2 lives in cli.py, and the unit test above cannot see it.
    """
    from tests.toy import build_toy_run, split_world_model

    run = build_toy_run(tmp_path / "runs", upto="extract")
    write_json(run.capabilities_part, split_world_model()["capabilities"])

    schemas = tmp_path / "schemas"
    schemas.mkdir()
    for name in ("manifest-0.1.json", "capabilities-part-0.1.json"):
        # manifest-0.1.json is needed for parser construction alone:
        # `record-stage`'s argparse choices come from manifest_stage_efforts().
        (schemas / name).write_text(
            (validate.schema_dir() / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(schemas))

    code = main(["validate", "--run", str(run.root), "--stage", "reconcile-capabilities"])

    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a misconfigured schema set must not print a finding line"
    assert captured.err.startswith("error: ")
    assert str(schemas) in captured.err
    # Never the run root: that is the fabricated-[internal]-finding shape.
    assert str(run.root) not in captured.err
