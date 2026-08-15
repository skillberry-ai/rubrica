"""Layer-1 shape checks for the catalogue.

The negative cases matter more than the positive one: this schema is the
contract rb-triage reads, so a document that is wrong in a way layer 1 accepts
becomes a prompt's problem instead of a gate's.
"""

from __future__ import annotations

import json

import pytest

from rubrica import validate
from rubrica.paths import RunPaths


def _catalogue(**over):
    payload = {
        "schema_version": "0.1",
        "run_id": "run-20260814-000000",
        "created_utc": "2026-08-14T00:00:00Z",
        "request": {
            "target": {"name": "parsec", "interface": "http-sse"},
            "objective": "breadth",
            "corpus_roots": ["/tmp/parsec"],
            "limits": {"max_rounds": 2, "max_scenarios": 128},
        },
        "policy": {
            "exclusion_reasons": ["binary", "vendored"],
            "explode_min_elements": 3,
            "explode_min_common_keys": 3,
            "digest_body_chars": 2000,
            "max_candidates": 500,
            "max_catalogue_bytes": 1_048_576,
        },
        "candidates": [
            {
                "candidate_id": "readme-md",
                "origin": "corpus",
                "path": "parsec/README.md",
                "bytes": 8179,
                "sha256": "a" * 64,
                "kind": "design_doc",
                "admissible": True,
                "digest": {"headings": ["# parsec"], "lines": 200},
            }
        ],
        "excluded": [{"path": "parsec/logo.png", "reason": "binary"}],
    }
    payload.update(over)
    return payload


def _write(tmp_path, payload):
    run = RunPaths(tmp_path / "run-20260814-000000")
    run.root.mkdir(parents=True)
    run.catalogue.write_text(json.dumps(payload), encoding="utf-8")
    return run


def test_a_well_formed_catalogue_validates(tmp_path):
    run = _write(tmp_path, _catalogue())
    assert validate.validate_stage(run, "survey") == []


def test_an_unknown_exclusion_reason_is_a_finding(tmp_path):
    """The reason codes are an enum because a free-text reason cannot be
    counted, and the whole point of recording exclusions is that a reader can
    see what shape of thing was dropped."""
    run = _write(tmp_path, _catalogue(excluded=[{"path": "x", "reason": "too_big"}]))
    findings = validate.validate_stage(run, "survey")
    assert findings and "too_big" in str(findings[0])


def test_a_size_based_exclusion_reason_does_not_exist(tmp_path):
    """Spec §2: size was never the binding constraint, shape was.

    tool_definitions.py at 74KB was the parsec run's most load-bearing input.
    An 'oversize' reason code would make dropping it a one-word decision.
    """
    reasons = json.loads(
        (validate.schema_dir() / "catalogue-0.1.json").read_text(encoding="utf-8")
    )["$defs"]["exclusion_reason"]["enum"]
    assert "oversize" not in reasons
    assert "too_big" not in reasons


def test_a_missing_catalogue_is_itself_a_finding(tmp_path):
    run = RunPaths(tmp_path / "run-20260814-000000")
    run.root.mkdir(parents=True)
    findings = validate.validate_stage(run, "survey")
    assert findings and "00-catalogue.json" in str(findings[0])


@pytest.mark.parametrize(
    "objective",
    ["", "coverage", "BREADTH", "depth-ish"],
)
def test_only_the_two_declared_objectives_are_accepted(tmp_path, objective):
    """Spec §5 defines exactly two, and triage is held to whichever is set."""
    request = _catalogue()["request"] | {"objective": objective}
    run = _write(tmp_path, _catalogue(request=request))
    assert validate.validate_stage(run, "survey") != []
