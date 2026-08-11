"""check_manifest: the manifest against 01-claims, and evidence against the manifest."""

from __future__ import annotations

from rubrica.artifacts import write_json
from rubrica.paths import RunPaths
from rubrica.refs import check_manifest
from tests.builders import minimal_claims, minimal_manifest


def _run(tmp_path, manifest=None, claims=None) -> RunPaths:
    """A run holding a manifest and zero or more claims files keyed by artifact id."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, manifest if manifest is not None else minimal_manifest())
    for artifact_id, payload in (claims or {}).items():
        write_json(run.claims(artifact_id), payload)
    return run


def _messages(findings) -> str:
    return " || ".join(f.message for f in findings)


def test_a_consistent_manifest_and_claims_file_is_clean(tmp_path):
    run = _run(tmp_path, claims={"aap2-api": minimal_claims()})
    assert check_manifest(run) == []


def test_no_manifest_is_not_a_finding(tmp_path):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    assert check_manifest(run) == []


def test_a_registered_input_with_no_claims_file_is_not_a_finding(tmp_path):
    """The normal state during the extract fan-out; firing here is a phantom."""
    run = _run(tmp_path)
    assert check_manifest(run) == []


def test_a_claims_file_naming_an_unregistered_artifact_is_reported(tmp_path):
    run = _run(tmp_path, claims={"ghost": minimal_claims(artifact_id="ghost")})
    findings = check_manifest(run)
    assert len(findings) == 1
    assert "not registered in the manifest" in findings[0].message


def test_a_claims_filename_that_disagrees_with_its_artifact_id_is_reported(tmp_path):
    run = _run(tmp_path, claims={"aap2-api": minimal_claims(artifact_id="something-else")})
    messages = _messages(check_manifest(run))
    assert "is named aap2-api.json" in messages


def test_evidence_citing_an_unregistered_artifact_is_reported(tmp_path):
    claims = minimal_claims()
    claims["claims"][0]["evidence"][0]["artifact_id"] = "never-registered"
    run = _run(tmp_path, claims={"aap2-api": claims})
    findings = check_manifest(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/claims/0/evidence/0/artifact_id"
    assert "never-registered" in findings[0].message


def test_the_same_claim_id_in_two_files_is_reported(tmp_path):
    """The reconciliation hazard: a set would merge these and read as clean."""
    manifest = minimal_manifest()
    manifest["inputs"].append(
        {
            "artifact_id": "aap2-schema",
            "source_path": "harness-skills/parsec-aap2/schema.json",
            "sha256": "c" * 64,
            "kind": "entity_schema",
            "bytes": 2048,
        }
    )
    second = minimal_claims(artifact_id="aap2-schema")
    second["claims"][0]["evidence"][0]["artifact_id"] = "aap2-schema"
    run = _run(
        tmp_path,
        manifest=manifest,
        claims={"aap2-api": minimal_claims(), "aap2-schema": second},
    )
    messages = _messages(check_manifest(run))
    assert "'clm-001' is defined more than once" in messages
    assert "aap2-api.json, aap2-schema.json" in messages


def test_the_same_claim_id_twice_in_one_file_is_reported(tmp_path):
    claims = minimal_claims()
    claims["claims"].append(dict(claims["claims"][0]))
    run = _run(tmp_path, claims={"aap2-api": claims})
    messages = _messages(check_manifest(run))
    assert "'clm-001' is defined more than once" in messages


def test_a_duplicate_registered_artifact_id_is_reported(tmp_path):
    manifest = minimal_manifest()
    manifest["inputs"].append(dict(manifest["inputs"][0]))
    run = _run(tmp_path, manifest=manifest)
    messages = _messages(check_manifest(run))
    assert "already registered at /inputs/0" in messages


def test_an_unparseable_created_utc_is_reported(tmp_path):
    """The schema's pattern catches shape; only a parse catches month 13."""
    run = _run(tmp_path, manifest=minimal_manifest(created_utc="2026-13-45T99:99:99Z"))
    findings = check_manifest(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/created_utc"
