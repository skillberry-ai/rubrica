"""Layer 2 over the catalogue: the conditional constraints the schema cannot say.

Spec §3 (Task 3): `path` / `container` / `provenance` are not mutually required
in JSON Schema because the constraint is conditional on `origin`, which Schema
expresses badly and layer 2 expresses plainly.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import write_json
from rubrica.paths import RunPaths


def _run_with(tmp_path, mutate):
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    catalogue = {
        "schema_version": "0.1",
        "run_id": "run-20260814-213000",
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
                "candidate_id": "cap-json",
                "origin": "corpus",
                "path": "cap.json",
                "bytes": 10,
                "sha256": "a" * 64,
                "kind": "trace",
                "admissible": False,
                "digest": {},
            },
            {
                "candidate_id": "cap-json-0",
                "origin": "container_element",
                "container": {"candidate_id": "cap-json", "json_pointer": "/0"},
                "bytes": 5,
                "sha256": "b" * 64,
                "kind": "trace",
                "admissible": True,
                "digest": {},
            },
        ],
        "excluded": [],
    }
    mutate(catalogue)
    write_json(run.catalogue, catalogue)
    return run


def test_a_clean_catalogue_has_no_findings(tmp_path):
    assert refs.check_catalogue(_run_with(tmp_path, lambda c: None)) == []


def test_a_corpus_candidate_without_a_path_is_a_finding(tmp_path):
    def mutate(c):
        del c["candidates"][0]["path"]

    findings = refs.check_catalogue(_run_with(tmp_path, mutate))
    assert findings and "path" in str(findings[0])


def test_an_element_whose_container_does_not_resolve_is_a_finding(tmp_path):
    def mutate(c):
        c["candidates"][1]["container"]["candidate_id"] = "nope"

    findings = refs.check_catalogue(_run_with(tmp_path, mutate))
    assert findings and "nope" in str(findings[0])


def test_a_duplicate_candidate_id_is_a_finding(tmp_path):
    def mutate(c):
        c["candidates"][1]["candidate_id"] = "cap-json"

    findings = refs.check_catalogue(_run_with(tmp_path, mutate))
    assert findings and "cap-json" in str(findings[0])


def test_an_absent_catalogue_is_not_a_finding(tmp_path):
    """A run built through `intake --input` never had one, and spec §7.1 rules
    that its absence is not a finding -- the same ruling that makes intake's and
    smoke's absence from manifest.stages not a finding."""
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    assert refs.check_catalogue(run) == []
