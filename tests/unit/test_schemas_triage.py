"""Layer-1 shape checks for the triage record.

The negative cases matter more than the positive one: this schema is the
contract rb-triage writes and rb-instantiate's admit_from_triage and
adopt_projection read, so a document that is wrong in a way layer 1 accepts
becomes a prompt's problem, or a later stage's, instead of a gate's.
"""

from __future__ import annotations

import json

import pytest

from rubrica import validate
from rubrica.paths import RunPaths


def _triage(**over):
    payload = {
        "schema_version": "0.1",
        "run_id": "run-20260814-000000",
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {
                    "name": "tool schemas",
                    "evidence": ["cand-1"],
                    "weight": {"candidates": 3, "bytes": 1200},
                }
            ],
        },
        "dispositions": [
            {
                "candidate_id": "cand-1",
                "disposition": "admit",
                "reason": "core api surface",
                "authority": "triage",
            }
        ],
        "deficiencies": [
            {
                "deficiency_id": "def-1",
                "subject": "tool return shapes",
                "statement": "no candidate describes what each tool actually returns",
            }
        ],
        "projections": [
            {
                "projection_id": "proj-1",
                "closes": ["def-1"],
                "sources": [
                    {"candidate_id": "cand-1", "digest_note": "digest showed only the request side"}
                ],
                "wanted": {
                    "kind": "mcp_tool_schema",
                    "statement": "the full return schema for each tool",
                    "why": "needed to ground assertions against a real response shape",
                },
                "method": {
                    "confidence": "medium",
                    "steps": ["read the source handler", "infer the return type from its callers"],
                },
                "acceptance": {
                    "classifies_as": "mcp_tool_schema",
                    "prose": "the projection lists every field the tool actually returns, "
                    "matched against one real trace",
                },
                "boundary": "does not cover error responses",
            }
        ],
    }
    payload.update(over)
    return payload


def _write(tmp_path, payload):
    run = RunPaths(tmp_path / "run-20260814-000000")
    run.root.mkdir(parents=True)
    run.triage.write_text(json.dumps(payload), encoding="utf-8")
    return run


def test_a_well_formed_triage_record_validates(tmp_path):
    run = _write(tmp_path, _triage())
    assert validate.validate_stage(run, "triage") == []


def test_a_triage_with_no_surfaces_is_a_finding(tmp_path):
    """Spec §6.1: enumerating the surfaces is the job, not a courtesy. It is
    what would have made parsec's excluded-surface problem visible at gate 0."""
    review = _triage()["objective_review"] | {"surfaces": []}
    assert validate.validate_stage(_write(tmp_path, _triage(objective_review=review)), "triage")


def test_a_free_text_decline_reason_code_is_a_finding(tmp_path):
    """The codes are an enum so declines can be counted by shape. A free-text
    code makes 'what did this run drop' unanswerable."""
    dispositions = [_triage()["dispositions"][0] | {"reason_code": "seemed_irrelevant"}]
    assert validate.validate_stage(_write(tmp_path, _triage(dispositions=dispositions)), "triage")


def test_every_decline_reason_code_the_spec_names_is_accepted(tmp_path):
    """A code the schema rejects is a code the skill cannot use, which turns a
    declared decline into a schema failure at the gate."""
    import json

    enum = json.loads((validate.schema_dir() / "triage-0.1.json").read_text(encoding="utf-8"))[
        "$defs"
    ]["decline_reason"]["enum"]
    assert set(enum) == {
        "off_objective",
        "out_of_scope",
        "near_duplicate",
        "superseded",
        "implementation_detail",
        "no_evidence_value",
        "digest_insufficient",
        "needs_projection",
    }


def test_a_projection_without_acceptance_prose_is_a_finding(tmp_path):
    """Structural acceptance is necessary, not sufficient. A brief with only
    mechanical criteria has not said what correct means, and the same rule
    forbids inventing a mechanical check for support in layer 2."""
    projection = _triage()["projections"][0]
    del projection["acceptance"]["prose"]
    assert validate.validate_stage(_write(tmp_path, _triage(projections=[projection])), "triage")


def test_a_missing_triage_record_is_itself_a_finding(tmp_path):
    run = RunPaths(tmp_path / "run-20260814-000000")
    run.root.mkdir(parents=True)
    findings = validate.validate_stage(run, "triage")
    assert findings and "produced no triage artifact" in findings[0].message


@pytest.mark.parametrize("kind", ["deficiencies", "projections"])
def test_deficiencies_and_projections_may_be_empty(tmp_path, kind):
    """Unlike surfaces and dispositions, these two carry no minItems: a run
    with a clean corpus may have nothing to declare a gap or a projection
    against."""
    run = _write(tmp_path, _triage(**{kind: []}))
    assert validate.validate_stage(run, "triage") == []
