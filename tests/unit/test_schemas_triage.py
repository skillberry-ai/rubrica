"""Layer-1 shape checks for the triage record.

The negative cases matter more than the positive one: this schema is the
contract `triage-seal` assembles and rb-instantiate's admit_from_triage and
adopt_projection read, so a document that is wrong in a way layer 1 accepts
becomes a prompt's problem, or a later stage's, instead of a gate's.

The stage name every `validate_stage` call here passes is `triage-seal`, not
`triage`: the record's *kind* is still `triage` and still lands at
`00-triage.json`, but the stage that writes it is the family's seal. The
monolithic `triage` stage that used to own both no longer exists.
"""

from __future__ import annotations

import json

import pytest

from rubrica import validate
from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths
from tests.toy import build_toy_catalogue_and_triage, build_toy_run


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
    assert validate.validate_stage(run, "triage-seal") == []


def test_a_triage_with_no_surfaces_is_a_finding(tmp_path):
    """Spec §6.1: enumerating the surfaces is the job, not a courtesy. It is
    what would have made parsec's excluded-surface problem visible at gate 0."""
    review = _triage()["objective_review"] | {"surfaces": []}
    assert validate.validate_stage(
        _write(tmp_path, _triage(objective_review=review)), "triage-seal"
    )


def test_a_free_text_decline_reason_code_is_a_finding(tmp_path):
    """The codes are an enum so declines can be counted by shape. A free-text
    code makes 'what did this run drop' unanswerable."""
    dispositions = [_triage()["dispositions"][0] | {"reason_code": "seemed_irrelevant"}]
    assert validate.validate_stage(
        _write(tmp_path, _triage(dispositions=dispositions)), "triage-seal"
    )


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
        # A defer's code shares this enum because `reason_code` is one field with
        # one $ref, but it is never a decline's: refs.check_triage holds each
        # disposition to its own half of the set. The $defs name stays
        # `decline_reason` on purpose -- renaming it would move every $ref for no
        # gain -- so this membership is the one place the widening looks odd, and
        # the schema's own description is where it is argued.
        "deferred_to_phase",
    }


def test_a_projection_without_acceptance_prose_is_a_finding(tmp_path):
    """Structural acceptance is necessary, not sufficient. A brief with only
    mechanical criteria has not said what correct means, and the same rule
    forbids inventing a mechanical check for support in layer 2."""
    projection = _triage()["projections"][0]
    del projection["acceptance"]["prose"]
    assert validate.validate_stage(
        _write(tmp_path, _triage(projections=[projection])), "triage-seal"
    )


def test_a_missing_triage_record_is_itself_a_finding(tmp_path):
    run = RunPaths(tmp_path / "run-20260814-000000")
    run.root.mkdir(parents=True)
    findings = validate.validate_stage(run, "triage-seal")
    assert findings and "produced no triage artifact" in findings[0].message


@pytest.mark.parametrize("kind", ["deficiencies", "projections"])
def test_deficiencies_and_projections_may_be_empty(tmp_path, kind):
    """Unlike surfaces and dispositions, these two carry no minItems: a run
    with a clean corpus may have nothing to declare a gap or a projection
    against."""
    run = _write(tmp_path, _triage(**{kind: []}))
    assert validate.validate_stage(run, "triage-seal") == []


def test_promoting_definitions_did_not_change_what_triage_accepts():
    """The refactor's whole claim. A document that validated before must
    validate now, and one that failed must still fail for the same reason."""
    schema = json.loads((validate.schema_dir() / "triage-0.1.json").read_text(encoding="utf-8"))
    assert set(schema["$defs"]) >= {"disposition", "surface", "deficiency", "projection"}
    # The four properties now reference rather than restate.
    assert schema["properties"]["dispositions"]["items"] == {"$ref": "#/$defs/disposition"}
    assert schema["properties"]["deficiencies"]["items"] == {"$ref": "#/$defs/deficiency"}
    assert schema["properties"]["projections"]["items"] == {"$ref": "#/$defs/projection"}
    assert schema["properties"]["objective_review"]["properties"]["surfaces"]["items"] == {
        "$ref": "#/$defs/surface"
    }
    # And the definitions kept their contracts.
    assert schema["$defs"]["disposition"]["required"] == [
        "candidate_id",
        "disposition",
        "reason",
        "authority",
    ]
    assert schema["$defs"]["deficiency"]["required"] == ["deficiency_id", "subject", "statement"]
    assert schema["$defs"]["projection"]["required"] == [
        "projection_id",
        "closes",
        "sources",
        "wanted",
        "method",
        "acceptance",
        "boundary",
    ]


def test_a_disposition_missing_authority_still_fails(tmp_path):
    """The strongest evidence that the move was semantic-free is a negative
    case: promote-and-forget-a-constraint validates everything."""
    run = build_toy_run(tmp_path / "runs")
    build_toy_catalogue_and_triage(run)
    record = read_json(run.triage)
    del record["dispositions"][0]["authority"]
    write_json(run.triage, record)
    findings = validate.validate_stage(run, "triage-seal")
    assert findings, "a disposition without authority must still fail layer 1"


# The four defs promoted in this task, and the `required` list each one had
# *before* the move -- pinned here so a later edit to a def four part schemas
# will `$ref` cannot silently drop a field or loosen `additionalProperties`
# without a test noticing. Data-driven so a fifth promoted def is one line,
# not four hand-written blocks.
_PROMOTED_DEFS_REQUIRED = {
    "disposition": ["candidate_id", "disposition", "reason", "authority"],
    "surface": ["name", "evidence", "weight"],
    "deficiency": ["deficiency_id", "subject", "statement"],
    "projection": [
        "projection_id",
        "closes",
        "sources",
        "wanted",
        "method",
        "acceptance",
        "boundary",
    ],
}


@pytest.mark.parametrize("name", sorted(_PROMOTED_DEFS_REQUIRED))
def test_a_promoted_def_pins_its_required_fields_and_closed_shape(name):
    """The equivalence test above only checks $ref shape and three of the four
    required lists -- surface had none. Pin all four here, plus
    additionalProperties, since the next task makes four part schemas $ref
    these defs: a silently dropped constraint would degrade all four at once
    with nothing here to catch it."""
    schema = json.loads((validate.schema_dir() / "triage-0.1.json").read_text(encoding="utf-8"))
    definition = schema["$defs"][name]
    assert definition["required"] == _PROMOTED_DEFS_REQUIRED[name]
    assert definition["additionalProperties"] is False


def test_the_disposition_enum_is_exactly_admit_decline_or_defer():
    """The field that decides what a run can ever know is worth pinning to its
    exact permitted set, not merely confirming an enum exists.

    `defer` joined it as a third value rather than as a decline with a special
    reason code because the two make opposite promises -- a decline says this
    input has no evidence value, a defer says it has value this phase cannot
    spend -- and refs.check_triage now branches three ways on exactly this list.
    A fourth value appearing here without a branch there is the drift the pin
    exists to catch.
    """
    schema = json.loads((validate.schema_dir() / "triage-0.1.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["disposition"]["properties"]["disposition"]["enum"] == [
        "admit",
        "decline",
        "defer",
    ]


def test_a_surface_missing_weight_still_fails(tmp_path):
    """Same evidence as the authority case above, for the surface def promoted
    alongside it: dropping a required field must still fail layer 1."""
    review = _triage()["objective_review"]
    del review["surfaces"][0]["weight"]
    assert validate.validate_stage(
        _write(tmp_path, _triage(objective_review=review)), "triage-seal"
    )


def test_a_deficiency_missing_statement_still_fails(tmp_path):
    """Same evidence as the authority case above, for the deficiency def."""
    deficiencies = [_triage()["deficiencies"][0]]
    del deficiencies[0]["statement"]
    assert validate.validate_stage(
        _write(tmp_path, _triage(deficiencies=deficiencies)), "triage-seal"
    )


def test_a_projection_missing_acceptance_still_fails(tmp_path):
    """Same evidence as the authority case above, for the projection def."""
    projections = [_triage()["projections"][0]]
    del projections[0]["acceptance"]
    assert validate.validate_stage(
        _write(tmp_path, _triage(projections=projections)), "triage-seal"
    )


def test_a_disposition_with_an_unknown_key_still_fails(tmp_path):
    """additionalProperties: false on a promoted def is a claim about what
    validation enforces, not just what the schema text says -- distinct
    claims, so this needs its own case rather than riding on the required-list
    assertion above."""
    dispositions = [_triage()["dispositions"][0] | {"unexpected_field": "surprise"}]
    assert validate.validate_stage(
        _write(tmp_path, _triage(dispositions=dispositions)), "triage-seal"
    )


# The disposition a deferred candidate carries, and the block that explains it.
# Written out here rather than added to _triage()'s baseline: every other test in
# this module reads that baseline, and a defer in it would silently change what
# they are each measuring.
_DEFER = {
    "candidate_id": "cand-2",
    "disposition": "defer",
    "reason_code": "deferred_to_phase",
    "reason": "trace is deferred to phase 3",
    "authority": "policy",
}
_PHASE = {"number": 1, "deferred_kinds": ["trace"], "deferred_count": 68}


def _with_a_defer(**over):
    """The baseline record plus one defer and a well-formed phase block."""
    payload = _triage(dispositions=[*_triage()["dispositions"], _DEFER], phase=_PHASE)
    payload.update(over)
    return payload


def test_a_record_carrying_a_defer_and_a_phase_block_validates(tmp_path):
    """The positive control the seven negatives below are measured against.

    Without it each of those could be passing because the *record* is malformed
    for some unrelated reason -- a defer, a policy authority and a phase block are
    three new shapes at once, and a rejection proves nothing about the block if the
    document would have been rejected anyway.
    """
    assert validate.validate_stage(_write(tmp_path, _with_a_defer()), "triage-seal") == []


def test_a_record_with_no_phase_block_still_validates(tmp_path):
    """Optional, on max_scenario_part_bytes' precedent: making it required would
    invalidate every record already on disk. Absent means no phase was declared."""
    payload = _with_a_defer()
    del payload["phase"]
    assert validate.validate_stage(_write(tmp_path, payload), "triage-seal") == []


@pytest.mark.parametrize(
    ("case", "block"),
    [
        # Held to the catalogue's own kind enum, so a declaration cannot name a
        # kind no candidate can carry -- the failure the schema exists to stop is
        # a --defer-kind that silently defers nothing while the run pays in full.
        ("unknown kind", {"number": 1, "deferred_kinds": ["nope"]}),
        # A label, minimum 1: phase 0 is nobody's phase.
        ("number below one", {"number": 0, "deferred_kinds": ["trace"]}),
        # minItems 1: a phase deferring nothing is what the absent block says.
        ("no kinds at all", {"number": 1, "deferred_kinds": []}),
        ("a kind twice", {"number": 1, "deferred_kinds": ["trace", "trace"]}),
        ("an unknown key", {"number": 1, "deferred_kinds": ["trace"], "extra": 1}),
        ("no number", {"deferred_kinds": ["trace"]}),
        ("no kinds key", {"number": 1}),
    ],
)
def test_a_malformed_phase_block_is_a_finding(tmp_path, case, block):
    """Every constraint the new $def declares actually bites.

    A $def whose constraints were never exercised is the same defect as an
    unwatched predicate: `uniqueItems`, `minItems`, `minimum` and
    `additionalProperties` each cost one line to write and none of them announces
    itself if it is missing.
    """
    assert validate.validate_stage(_write(tmp_path, _with_a_defer(phase=block)), "triage-seal"), (
        f"a phase block with {case} was wrongly accepted"
    )


def test_a_defer_carrying_a_declines_reason_code_is_still_layer_1_valid(tmp_path):
    """The seam between the layers, stated so a reader does not look for this
    check in the wrong place. `reason_code` is one field with one $ref, so layer 1
    cannot tell a defer's half of that enum from a decline's -- which is why
    refs.check_triage owns it (tests/unit/test_refs_triage.py). Recording the
    permissiveness here is what stops somebody 'fixing' layer 1 by splitting the
    $def and breaking every other $ref to it."""
    payload = _with_a_defer()
    payload["dispositions"][-1] = _DEFER | {"reason_code": "no_evidence_value"}
    assert validate.validate_stage(_write(tmp_path, payload), "triage-seal") == []
