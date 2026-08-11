"""refs.check_inputs: the bytes in 00-inputs/ against the manifest's digests.

Nothing checked this before, and the reproducibility claim rests on it. A run
whose registered copy has been edited since intake makes every claim derived
from that input unattributable, while validate, check-refs and emit all stay
green -- the numbers are simply confidently wrong.
"""

from __future__ import annotations

import hashlib

from rubrica.artifacts import write_json
from rubrica.paths import RunPaths
from rubrica.refs import check_all, check_inputs
from tests.builders import MINIMAL_INPUT_BYTES, MINIMAL_INPUT_NAME, minimal_manifest


def _run(tmp_path, *, manifest=None, body=MINIMAL_INPUT_BYTES, name=MINIMAL_INPUT_NAME):
    run = RunPaths(tmp_path)
    write_json(run.manifest, manifest if manifest is not None else minimal_manifest())
    if body is not None:
        run.inputs_dir.mkdir(parents=True, exist_ok=True)
        (run.inputs_dir / name).write_bytes(body)
    return run


def test_a_registered_input_whose_stored_bytes_match_is_clean(tmp_path):
    assert check_inputs(_run(tmp_path)) == []


def test_no_manifest_is_not_a_finding(tmp_path):
    """The state before intake. check_all runs in it and must stay silent."""
    assert check_inputs(RunPaths(tmp_path)) == []


def test_a_registered_input_with_no_stored_copy_is_reported(tmp_path):
    findings = check_inputs(_run(tmp_path, body=None))
    assert len(findings) == 1
    assert findings[0].pointer == "/inputs/0/stored_as"
    assert "no stored copy" in findings[0].message


def test_an_edited_stored_input_is_reported(tmp_path):
    run = _run(tmp_path, body=b'{"tools": [{"name": "tampered"}]}\n')
    findings = check_inputs(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.input_file(MINIMAL_INPUT_NAME)
    assert "has been edited since intake" in findings[0].message
    assert hashlib.sha256(MINIMAL_INPUT_BYTES).hexdigest() in findings[0].message


def test_a_stored_copy_whose_recorded_size_is_wrong_is_reported(tmp_path):
    """Reachable only by hand-editing the manifest, and still worth a finding.

    A digest match all but guarantees a size match, so this fires on a manifest
    someone edited `bytes` in -- which is the manifest field a reader skims
    instead of hashing.
    """
    manifest = minimal_manifest()
    manifest["inputs"][0]["bytes"] = 999999
    findings = check_inputs(_run(tmp_path, manifest=manifest))
    assert len(findings) == 1
    assert "999999" in findings[0].message


def test_an_unsafe_stored_as_is_reported_rather_than_raised(tmp_path):
    """paths.input_file raises UnsafeSegment, which cli.py would map to exit 2.

    A manifest is a stage output, so a bad value in it is a repairable defect and
    must arrive as a finding. Returning it raw would report a repairable defect
    as a misconfigured harness and discard every other finding in the run.
    """
    manifest = minimal_manifest()
    manifest["inputs"][0]["stored_as"] = "../../etc/passwd"
    findings = check_inputs(_run(tmp_path, manifest=manifest))
    assert len(findings) == 1
    assert "not a safe path segment" in findings[0].message


def test_two_bad_inputs_are_both_reported(tmp_path):
    """The orchestrator gets one bounded repair attempt, so it needs every reason."""
    manifest = minimal_manifest()
    manifest["inputs"].append(
        {
            "artifact_id": "aap2-schema",
            "source_path": "harness-skills/parsec-aap2/schema.json",
            "stored_as": "aap2-schema.json",
            "sha256": "b" * 64,
            "kind": "entity_schema",
            "bytes": 2,
        }
    )
    run = _run(tmp_path, manifest=manifest)
    (run.inputs_dir / "aap2-schema.json").write_bytes(b"{}")
    assert len(check_inputs(run)) == 1  # only the second: digest mismatch
    (run.inputs_dir / MINIMAL_INPUT_NAME).write_bytes(b"edited\n")
    assert len(check_inputs(run)) == 2


def test_check_all_runs_the_input_digest_check(tmp_path):
    run = _run(tmp_path, body=b"edited\n")
    assert any("edited since intake" in f.message for f in check_all(run))
