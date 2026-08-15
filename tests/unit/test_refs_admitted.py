"""Layer 2 over manifest.inputs[] against 00-triage.json's admits.

The one failure mode where both artifacts are individually well formed and the
run is still wrong: an admission intake dropped, or an input that entered the
run from outside the gate. Silent on a run with no triage record at all --
spec §7.1's ruling, and every intake --input run's normal state.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import write_json
from rubrica.paths import RunPaths


def _catalogue(run_id: str) -> dict:
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "created_utc": "2026-08-14T21:30:00Z",
        "request": {
            "target": {"name": "t", "interface": "i"},
            "objective": "breadth",
            "corpus_roots": ["/tmp/c"],
            "limits": {"max_rounds": 2, "max_scenarios": 128},
        },
        "policy": {
            "exclusion_reasons": ["binary"],
            "explode_min_elements": 3,
            "explode_min_common_keys": 3,
            "digest_body_chars": 2000,
            "max_candidates": 500,
        },
        "candidates": [
            {
                "candidate_id": "readme-md",
                "origin": "corpus",
                "path": "README.md",
                "bytes": 10,
                "sha256": "a" * 64,
                "kind": "design_doc",
                "admissible": True,
                "digest": {},
            },
            {
                "candidate_id": "api-json",
                "origin": "corpus",
                "path": "api.json",
                "bytes": 10,
                "sha256": "b" * 64,
                "kind": "mcp_tool_schema",
                "admissible": True,
                "digest": {},
            },
        ],
        "excluded": [],
    }


def _triage(run_id: str, *, admit_api_json: bool) -> dict:
    dispositions = [
        {
            "candidate_id": "readme-md",
            "disposition": "admit",
            "reason": "carries the target's shape",
            "authority": "triage",
        },
    ]
    if admit_api_json:
        dispositions.append(
            {
                "candidate_id": "api-json",
                "disposition": "admit",
                "reason": "the tool schema itself",
                "authority": "triage",
            }
        )
    else:
        dispositions.append(
            {
                "candidate_id": "api-json",
                "disposition": "decline",
                "reason_code": "no_evidence_value",
                "reason": "redundant with readme-md",
                "authority": "triage",
            }
        )
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {"name": "s", "evidence": ["readme-md"], "weight": {"candidates": 1, "bytes": 1}}
            ],
        },
        "dispositions": dispositions,
        "deficiencies": [],
        "projections": [],
    }


def _manifest(run_id: str, artifact_ids: list[str]) -> dict:
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "created_utc": "2026-08-14T21:30:00Z",
        "target": {"name": "t", "interface": "i"},
        "inputs": [
            {
                "artifact_id": aid,
                "source_path": f"/tmp/{aid}",
                "stored_as": f"{aid}.md",
                "sha256": "c" * 64,
                "kind": "design_doc",
                "bytes": 1,
            }
            for aid in artifact_ids
        ],
        "stages": {},
        "limits": {"max_rounds": 2, "max_scenarios": 128},
    }


def _run(tmp_path, *, admit_api_json: bool, artifact_ids: list[str]) -> RunPaths:
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    write_json(run.catalogue, _catalogue(run.root.name))
    write_json(run.triage, _triage(run.root.name, admit_api_json=admit_api_json))
    write_json(run.manifest, _manifest(run.root.name, artifact_ids))
    return run


def test_an_admitted_candidate_missing_from_the_manifest_is_a_finding(tmp_path):
    """This is what catches an admission intake dropped -- the only failure mode
    where both artifacts are individually well formed and the run is still wrong."""
    # Both readme-md and api-json are admitted at triage, but only readme-md
    # was registered -- api-json's admission never reached the manifest.
    run = _run(tmp_path, admit_api_json=True, artifact_ids=["readme-md"])
    findings = refs.check_admitted_inputs(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.manifest
    assert "api-json" in findings[0].message
    assert "dropped" in findings[0].message


def test_a_manifest_input_that_was_never_admitted_is_a_finding(tmp_path):
    """The other direction: an input nobody ruled on is an input that entered the
    run outside the gate."""
    # api-json is declined, so only readme-md was ever admitted, but the
    # manifest also carries "ghost-input", which no disposition names.
    run = _run(tmp_path, admit_api_json=False, artifact_ids=["readme-md", "ghost-input"])
    findings = refs.check_admitted_inputs(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.manifest
    assert "ghost-input" in findings[0].message
    assert "outside the gate" in findings[0].message


def test_the_check_is_silent_on_a_run_with_no_triage_record(tmp_path):
    """intake --input runs have a manifest and no triage record, and spec §7.1
    rules that this is not a finding."""
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    write_json(run.manifest, _manifest(run.root.name, ["readme-md"]))
    assert not run.triage.exists()
    assert refs.check_admitted_inputs(run) == []


def test_a_clean_admission_reports_nothing(tmp_path):
    """The negative-negative case: both admitted candidates are registered and
    nothing extra is, so there is nothing for either direction to report."""
    run = _run(tmp_path, admit_api_json=True, artifact_ids=["readme-md", "api-json"])
    assert refs.check_admitted_inputs(run) == []
