"""seal.seal: assemble 00-triage.json from the staged parts.

Every mutation test edits exactly the staged part(s) its own defect lives in,
survey + write_slices + _staged_run's hand-written objective/parts/audit
otherwise held fixed, so a finding is attributable to the one thing that
changed -- the same discipline test_refs_slices.py uses for check_slices.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rubrica import seal, survey, triage, validate
from rubrica.artifacts import read_json, write_json
from rubrica.slices import write_slices


def _staged_run(tmp_path):
    """A run staged all the way through triage-audit, by hand.

    survey + write_slices(cap=2500) gives the toy fixture's three candidates
    one slice each (measured: s01/notes-md, s02/api-json, s03/trace-json).
    Two surfaces cover api-json and notes-md; trace-json is declined
    needs_projection, closed by a projection ("prj-1") whose acceptance
    contract is deliberately lenient -- classifies_as only, no
    must_contain/pointers_required -- so a hand-written `made.json` carrying
    `{"tools": [...]}` (which intake.classify resolves to mcp_tool_schema via
    its "tools" in payload rule, regardless of filename) passes structural
    acceptance trivially in the adoption tests below.
    """
    run = survey.survey(
        corpus_roots=[Path("tests/fixtures/toy")],
        runs_dir=tmp_path / "runs",
        target_name="toy",
        target_interface="http",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
    )
    write_slices(run, cap=2500)
    run_id = read_json(run.catalogue)["run_id"]

    write_json(
        run.objective,
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "predicted_surface_count": 2,
            "objective_review": {
                "declared_objective": "breadth",
                "supported": True,
                "surfaces": [
                    {
                        "name": "tool calls",
                        "evidence": ["api-json"],
                        "weight": {"candidates": 1, "bytes": 1231},
                    },
                    {
                        "name": "narrative notes",
                        "evidence": ["notes-md"],
                        "weight": {"candidates": 1, "bytes": 898},
                    },
                ],
            },
        },
    )

    write_json(
        run.disposition_part("s01"),
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "slice_id": "s01",
            "dispositions": [
                {
                    "candidate_id": "notes-md",
                    "disposition": "admit",
                    "reason": "covers the narrative-notes surface",
                    "priority": 1,
                    "authority": "triage",
                }
            ],
            "observed_surfaces": [],
            "deficiency_notes": [],
        },
    )
    write_json(
        run.disposition_part("s02"),
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "slice_id": "s02",
            "dispositions": [
                {
                    "candidate_id": "api-json",
                    "disposition": "admit",
                    "reason": "covers the tool-calls surface",
                    "priority": 1,
                    "authority": "triage",
                }
            ],
            "observed_surfaces": [],
            "deficiency_notes": [],
        },
    )
    write_json(
        run.disposition_part("s03"),
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "slice_id": "s03",
            "dispositions": [
                {
                    "candidate_id": "trace-json",
                    "disposition": "decline",
                    "reason": "a trace alone needs a projection to be usable",
                    "reason_code": "needs_projection",
                    "authority": "triage",
                }
            ],
            "observed_surfaces": [],
            "deficiency_notes": [
                {
                    "candidate_id": "trace-json",
                    "statement": (
                        "a bare trace has no tool-call surface without a manufactured schema"
                    ),
                }
            ],
        },
    )

    write_json(
        run.audit,
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "deficiencies": [
                {
                    "deficiency_id": "def-1",
                    "subject": "trace-json",
                    "statement": (
                        "a bare trace has no tool-call surface without a manufactured schema"
                    ),
                }
            ],
            "projections": [
                {
                    "projection_id": "prj-1",
                    "closes": ["def-1"],
                    "sources": [
                        {
                            "candidate_id": "trace-json",
                            "digest_note": "the trace names calls with no accompanying schema",
                        }
                    ],
                    "wanted": {
                        "kind": "mcp_tool_schema",
                        "statement": "a tool schema for the calls the trace observed",
                        "why": "so tool calls become checkable claims",
                    },
                    "method": {
                        "confidence": "medium",
                        "steps": ["read the trace's call names", "author a matching tool schema"],
                    },
                    "acceptance": {
                        "classifies_as": "mcp_tool_schema",
                        "prose": "result_shape should describe what a caller actually receives",
                    },
                    "boundary": (
                        "structural acceptance only; whether result_shape is right is a "
                        "human's call"
                    ),
                }
            ],
        },
    )
    return run


def test_the_seal_assembles_a_record_that_validates(tmp_path):
    run = _staged_run(tmp_path)
    path, findings = seal.seal(run)
    assert findings == []
    assert path == run.triage
    assert validate.validate_stage(run, "triage-seal") == []


def test_the_seal_writes_nothing_when_it_reports_anything(tmp_path):
    run = _staged_run(tmp_path)
    run.audit.unlink()
    path, findings = seal.seal(run)
    assert path is None
    assert findings
    assert not run.triage.exists(), "a half-assembled record clears layer 1 and reads as complete"


def test_a_candidate_ruled_twice_across_parts_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    parts = sorted(run.dispositions_dir.iterdir())
    first = read_json(parts[0])
    second = read_json(parts[1])
    second["dispositions"].append(first["dispositions"][0])
    write_json(parts[1], second)
    _, findings = seal.seal(run)
    assert any("more than one disposition" in f.message for f in findings)


def test_a_candidate_ruled_by_nobody_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    part = sorted(run.dispositions_dir.iterdir())[0]
    doc = read_json(part)
    dropped = doc["dispositions"].pop()["candidate_id"]
    write_json(part, doc)
    _, findings = seal.seal(run)
    assert any(dropped in f.message for f in findings)


def test_a_part_ruling_outside_its_slice_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    parts = sorted(run.dispositions_dir.iterdir())
    doc = read_json(parts[0])
    doc["dispositions"][0]["candidate_id"] = read_json(parts[1])["dispositions"][0]["candidate_id"]
    write_json(parts[0], doc)
    _, findings = seal.seal(run)
    assert any("not in slice" in f.message for f in findings)


def test_zero_admits_across_every_part_is_refused_by_the_seal(tmp_path):
    """Spec 10.2's inversion: a member declining its whole slice is legitimate
    and must write its part; only the union can say the scoping failed."""
    run = _staged_run(tmp_path)
    for part in run.dispositions_dir.iterdir():
        doc = read_json(part)
        for d in doc["dispositions"]:
            d["disposition"] = "decline"
            d["reason_code"] = "off_objective"
            d.pop("priority", None)
        write_json(part, doc)
    _, findings = seal.seal(run)
    assert any("no admit" in f.message.lower() for f in findings)
    assert not run.triage.exists()


def test_a_single_part_declining_everything_is_not_refused(tmp_path):
    """The other half of the same rule, and the one a naive port gets wrong."""
    run = _staged_run(tmp_path)
    part = sorted(run.dispositions_dir.iterdir())[0]
    doc = read_json(part)
    for d in doc["dispositions"]:
        d["disposition"] = "decline"
        d["reason_code"] = "off_objective"
        d.pop("priority", None)
    write_json(part, doc)
    _, findings = seal.seal(run)
    assert findings == []


def test_a_digest_insufficient_decline_with_no_deficiency_is_refused(tmp_path):
    """Item 5, limb 1 -- the weak form, ported unchanged from check_triage:
    the check is "does any deficiency exist at all", never "does one name
    this candidate", because triage-0.1.json's deficiencies[] carries no
    candidate-reference field for a stronger check to key on (see
    check_triage's identical comment). Isolated by re-labelling the
    fixture's one decline and clearing the deficiency list wholesale --
    nothing else seal.py reads treats "deficiencies" as anything but this
    one set, so emptying it cannot trip a second check.
    """
    run = _staged_run(tmp_path)
    part = run.disposition_part("s03")
    doc = read_json(part)
    doc["dispositions"][0]["reason_code"] = "digest_insufficient"
    write_json(part, doc)
    audit = read_json(run.audit)
    audit["deficiencies"] = []
    write_json(run.audit, audit)
    _, findings = seal.seal(run)
    assert len(findings) == 1
    assert "digest_insufficient" in findings[0].message
    assert "trace-json" in findings[0].message


def test_a_needs_projection_decline_with_no_projection_is_refused(tmp_path):
    """Item 5, limb 2 -- the strong form: projections[].sources[] does name a
    candidate, so this checks the decline's *own* candidate is sourced, not
    merely that some projection exists for something else. Isolated by
    re-pointing the fixture's one projection's one source away from
    trace-json -- projected_candidate_ids is built from exactly that field
    and nothing else, so no other check can notice the change.
    """
    run = _staged_run(tmp_path)
    audit = read_json(run.audit)
    audit["projections"][0]["sources"][0]["candidate_id"] = "notes-md"
    write_json(run.audit, audit)
    _, findings = seal.seal(run)
    assert len(findings) == 1
    assert "needs_projection" in findings[0].message
    assert "trace-json" in findings[0].message


def test_a_null_part_is_one_finding_not_a_key_error(tmp_path):
    run = _staged_run(tmp_path)
    run.audit.write_text("null\n", encoding="utf-8")
    _, findings = seal.seal(run)
    assert findings and all(f.message for f in findings)


def test_priority_is_composed_across_slices_without_collision(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run)
    admits = [d for d in read_json(run.triage)["dispositions"] if d["disposition"] == "admit"]
    priorities = [d["priority"] for d in admits]
    assert priorities == sorted(priorities)
    assert len(priorities) == len(set(priorities)), "ranks minted per slice must not collide"


def test_sealing_twice_produces_identical_bytes(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run)
    first = run.triage.read_bytes()
    seal.seal(run)
    assert run.triage.read_bytes() == first


def test_an_adoption_survives_a_re_seal(tmp_path):
    """Spec 8.1's whole point: a re-seal must not erase a gate-0 admission."""
    run = _staged_run(tmp_path)
    seal.seal(run)
    source = tmp_path / "made.json"
    source.write_text(json.dumps({"tools": [{"name": "t", "result_shape": {}}]}), encoding="utf-8")
    findings = triage.adopt_projection(run, projection_id="prj-1", source=source)
    assert findings == []
    assert run.adoptions.is_file()
    seal.seal(run)
    record = read_json(run.triage)
    human = [d for d in record["dispositions"] if d["authority"] == "human"]
    assert len(human) == 1


def test_adopt_projection_does_not_write_the_sealed_record(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run)
    before = run.triage.read_bytes()
    source = tmp_path / "made.json"
    source.write_text(json.dumps({"tools": [{"name": "t", "result_shape": {}}]}), encoding="utf-8")
    triage.adopt_projection(run, projection_id="prj-1", source=source)
    assert run.triage.read_bytes() == before, "the seal owns 00-triage.json"


# One case per container this module indexes with a bare `[...]`, each edited
# in the part its own defect lives in. Every one of these was measured taking a
# KeyError or TypeError out of seal(), reaching cli.py's catch-all as an
# [internal] finding naming the RUN ROOT -- the exit-code contract's "a 1 must
# name the right artifact" breached, and the outcome _read_part's docstring
# cites as the thing to avoid one level up.
_NESTED_DEFECTS = [
    ("slices", lambda d: d.__setitem__("slices", "nope")),
    ("slices", lambda d: d["slices"][0].pop("id")),
    ("slices", lambda d: d["slices"][0].__setitem__("candidate_ids", 7)),
    ("audit", lambda d: d["deficiencies"][0].pop("deficiency_id")),
    ("audit", lambda d: d["projections"][0].__setitem__("sources", 5)),
    ("audit", lambda d: d["projections"][0]["sources"][0].pop("candidate_id")),
    ("objective", lambda d: d["objective_review"].__setitem__("surfaces", "nope")),
]


@pytest.mark.parametrize("attribute,break_it", _NESTED_DEFECTS, ids=range(len(_NESTED_DEFECTS)))
def test_a_nested_container_of_the_wrong_shape_names_its_own_part(tmp_path, attribute, break_it):
    run = _staged_run(tmp_path)
    path = getattr(run, attribute)
    document = read_json(path)
    break_it(document)
    write_json(path, document)
    sealed, findings = seal.seal(run)
    assert findings, "a nested shape defect produced no finding at all"
    assert all(f.message for f in findings), "a finding with no message is a 1 with empty stdout"
    # The part, not the run root. This is the half that was actually broken:
    # the old behaviour reported a finding, but against run.root.
    assert {f.artifact for f in findings} == {path}
    # And a pointer into it, so a reader lands on the field rather than
    # searching the document.
    assert all(f.pointer for f in findings)
    assert sealed is None, "a part this seal cannot index must not produce a sealed record"


def test_a_disposition_part_missing_a_candidate_id_names_the_shard(tmp_path):
    """The fan-out half, which is per-slice rather than a singleton part."""
    run = _staged_run(tmp_path)
    slice_id = next(iter(run.slice_ids_with_parts()))
    path = run.disposition_part(slice_id)
    document = read_json(path)
    document["dispositions"][0].pop("candidate_id")
    write_json(path, document)
    sealed, findings = seal.seal(run)
    assert findings and all(f.message for f in findings)
    assert {f.artifact for f in findings} == {path}
    assert sealed is None


def test_one_broken_container_is_one_finding_not_one_per_field_beneath_it(tmp_path):
    """Why _nested_shape recurses instead of walking a flat list of read sites.

    A `slices` that is a string is a single defect; reporting it once per field
    the seal would have read underneath it turns one broken part into a wall of
    findings an operator has to read to discover they all say the same thing.
    """
    run = _staged_run(tmp_path)
    document = read_json(run.slices)
    document["slices"] = "nope"
    write_json(run.slices, document)
    _, findings = seal.seal(run)
    assert len(findings) == 1
