"""`rubrica overrule` and the seal's handling of the human overrides it writes.

Built on test_seal's `_staged_run`: the toy fixture's three candidates, one
slice each, with triage admitting api-json and notes-md and declining
trace-json as needs_projection. Every test overrules on that one staged run, so
a difference in the sealed record is attributable to the override alone.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rubrica import brief, cli, intake, overrides, refs, seal, validate
from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from tests.unit.test_seal import _staged_run


def _sealed(run):
    path, findings = seal.seal(run)
    assert findings == [], findings
    return {d["candidate_id"]: d for d in read_json(path)["dispositions"]}


def _parts_bytes(run) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(run.dispositions_dir.iterdir())}


def test_overruling_a_decline_admits_it_and_intake_materialises_it(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(run, ["trace-json"], action="admit", reason="the traces show real calls")
    sealed = _sealed(run)
    assert sealed["trace-json"]["disposition"] == "admit"
    assert sealed["trace-json"]["authority"] == "human"
    assert sealed["trace-json"]["reason"] == "the traces show real calls"
    assert "reason_code" not in sealed["trace-json"]
    assert refs.check_all(run) == []
    intake.admit_from_triage(run)
    assert "trace-json" in {i["artifact_id"] for i in read_json(run.manifest)["inputs"]}


def test_overruling_an_admit_declines_it_with_the_human_reason_code(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(
        run, ["notes-md"], action="decline", reason="prose only", reason_code="no_evidence_value"
    )
    sealed = _sealed(run)
    assert sealed["notes-md"]["disposition"] == "decline"
    assert sealed["notes-md"]["reason_code"] == "no_evidence_value"
    assert "priority" not in sealed["notes-md"]
    assert sealed["api-json"]["priority"] == 1
    assert refs.check_all(run) == []


def test_the_triage_parts_are_never_rewritten(tmp_path):
    run = _staged_run(tmp_path)
    before = _parts_bytes(run)
    overrides.overrule(run, ["trace-json"], action="admit", reason="r")
    seal.seal(run)
    assert _parts_bytes(run) == before


def test_the_adoptions_file_validates_and_resealing_is_byte_identical(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(run, ["trace-json"], action="admit", reason="r")
    assert validate.validate_artifact(run.adoptions, "adoptions") == []
    seal.seal(run)
    first = run.triage.read_bytes()
    seal.seal(run)
    assert run.triage.read_bytes() == first


def test_clear_restores_triages_own_disposition(tmp_path):
    run = _staged_run(tmp_path)
    original = _sealed(run)
    overrides.overrule(run, ["trace-json"], action="admit", reason="r")
    overrides.overrule(run, ["trace-json"], action=None, reason="undo", clear=True)
    assert "overrides" not in read_json(run.adoptions)
    assert _sealed(run) == original


def test_several_candidates_are_one_all_or_nothing_write(tmp_path):
    run = _staged_run(tmp_path)
    with pytest.raises(UsageError, match="nothing to overrule"):
        overrides.overrule(run, ["trace-json", "no-such-file"], action="admit", reason="r")
    assert not run.adoptions.exists()
    overrides.overrule(
        run, ["api-json", "notes-md"], action="decline", reason="r", reason_code="superseded"
    )
    assert [o["candidate_id"] for o in read_json(run.adoptions)["overrides"]] == [
        "api-json",
        "notes-md",
    ]


def test_each_ruling_is_logged_in_decisions_without_reading_as_the_gate_approval(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(run, ["trace-json"], action="admit", reason="the traces matter")
    (line,) = run.decisions.read_text(encoding="utf-8").splitlines()
    assert "overrule at gate 0: trace-json: decline -> admit -- the traces matter" in line
    # The console counts a gate passed on `- <stamp> gate N` / `human gate N`; a
    # ruling must not look like the approval it precedes.
    stamp_and_rest = line.split(" ", 2)
    assert not stamp_and_rest[2].startswith(("gate", "human gate"))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"candidates": ["api-json"], "action": "admit"}, "triage already decided admit"),
        ({"candidates": ["no-such"], "action": "admit"}, "nothing to overrule"),
        ({"candidates": ["notes-md"], "action": "decline"}, "needs --reason-code"),
        (
            {"candidates": ["notes-md"], "action": "decline", "reason_code": "needs_projection"},
            "needs --reason-code",
        ),
        (
            {"candidates": ["trace-json"], "action": "admit", "reason_code": "superseded"},
            "takes no --reason-code",
        ),
        ({"candidates": ["trace-json"], "action": None, "clear": True}, "no override to clear"),
        ({"candidates": ["trace-json", "trace-json"], "action": "admit"}, "named twice"),
    ],
)
def test_requests_that_cannot_be_a_ruling_are_refused(tmp_path, kwargs, message):
    run = _staged_run(tmp_path)
    candidates = kwargs.pop("candidates")
    with pytest.raises(UsageError, match=message):
        overrides.overrule(run, candidates, reason="r", **kwargs)
    assert not run.adoptions.exists()


@pytest.mark.parametrize("reason", ["", "   ", "two\nlines"])
def test_a_blank_or_multi_line_reason_is_refused(tmp_path, reason):
    run = _staged_run(tmp_path)
    with pytest.raises(UsageError, match="reason"):
        overrides.overrule(run, ["trace-json"], action="admit", reason=reason)


def test_a_second_override_of_the_same_candidate_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(run, ["trace-json"], action="admit", reason="r")
    with pytest.raises(UsageError, match="already overridden"):
        overrides.overrule(run, ["trace-json"], action="admit", reason="r")


def test_an_inadmissible_candidate_cannot_be_admitted(tmp_path):
    run = _staged_run(tmp_path)
    catalogue = read_json(run.catalogue)
    for candidate in catalogue["candidates"]:
        if candidate["candidate_id"] == "trace-json":
            candidate["admissible"] = False
    write_json(run.catalogue, catalogue)
    with pytest.raises(UsageError, match="inadmissible"):
        overrides.overrule(run, ["trace-json"], action="admit", reason="r")


def test_overruling_after_intake_is_refused(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run)
    intake.admit_from_triage(run)
    with pytest.raises(UsageError, match="already been approved"):
        overrides.overrule(run, ["trace-json"], action="admit", reason="r")


def test_a_malformed_adoptions_file_is_a_usage_error(tmp_path):
    run = _staged_run(tmp_path)
    run.adoptions.write_text('{"adoptions": "not a list"}', encoding="utf-8")
    with pytest.raises(UsageError, match="unusable adoptions"):
        overrides.overrule(run, ["trace-json"], action="admit", reason="r")


def _override(cid, **disposition):
    return {
        "candidate_id": cid,
        "disposition": {
            "candidate_id": cid,
            "disposition": "admit",
            "reason": "r",
            "authority": "human",
            **disposition,
        },
        "replaces": "decline",
        "recorded_at": "2026-10-14T00:00:00Z",
    }


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([_override("no-such")], "no staged part rules on"),
        ([_override("trace-json"), _override("trace-json")], "more than one override"),
        ([_override("trace-json", authority="triage")], "authority 'human'"),
        ([_override("trace-json", reason_code="superseded")], "admitting 'trace-json' carries"),
        (
            [_override("notes-md", disposition="decline", reason_code="needs_projection")],
            "needs a reason_code",
        ),
        ([_override("trace-json", candidate_id="api-json")], "its disposition names"),
    ],
)
def test_the_seal_refuses_an_override_it_cannot_apply(tmp_path, entries, message):
    run = _staged_run(tmp_path)
    write_json(
        run.adoptions,
        {"schema_version": "0.1", "run_id": "x", "adoptions": [], "overrides": entries},
    )
    path, findings = seal.seal(run)
    assert path is None
    assert any(f.artifact == run.adoptions and message in f.message for f in findings), findings
    assert not run.triage.exists()


def test_a_malformed_overrides_list_is_one_finding_against_the_adoptions_file(tmp_path):
    run = _staged_run(tmp_path)
    write_json(
        run.adoptions, {"schema_version": "0.1", "run_id": "x", "adoptions": [], "overrides": {}}
    )
    path, findings = seal.seal(run)
    assert path is None
    assert [(f.artifact, f.pointer) for f in findings] == [(run.adoptions, "/overrides")]


def test_check_disposition_parts_does_not_count_an_override_as_a_second_disposition(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(run, ["trace-json"], action="admit", reason="r")
    assert refs.check_disposition_parts(run) == []


def test_the_cli_prints_one_line_per_ruling_and_refuses_at_exit_two(tmp_path, capsys):
    run = _staged_run(tmp_path)
    code = cli.main(
        [
            "overrule",
            "--run",
            str(run.root),
            "--candidate",
            "trace-json",
            "--admit",
            "--reason",
            "r",
        ]
    )
    out = capsys.readouterr()
    assert code == 0
    assert out.out.strip() == "trace-json: decline -> admit"
    assert "triage-seal" in out.err
    code = cli.main(
        ["overrule", "--run", str(run.root), "--candidate", "api-json", "--admit", "--reason", "r"]
    )
    out = capsys.readouterr()
    assert code == 2
    assert out.out == ""
    assert "triage already decided admit" in out.err


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through chmod 000")
def test_an_unreadable_adoptions_file_is_exit_two_naming_it(tmp_path, capsys):
    run = _staged_run(tmp_path)
    write_json(run.adoptions, {"schema_version": "0.1", "run_id": "x", "adoptions": []})
    run.adoptions.chmod(0o000)
    try:
        code = cli.main(
            [
                "overrule",
                "--run",
                str(run.root),
                "--candidate",
                "trace-json",
                "--admit",
                "--reason",
                "r",
            ]
        )
    finally:
        run.adoptions.chmod(0o644)
    out = capsys.readouterr()
    assert code == 2
    assert out.out == ""
    assert Path(run.adoptions).name in out.err


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes through chmod 0444")
def test_a_read_only_run_is_exit_two_and_logs_nothing(tmp_path, capsys):
    run = _staged_run(tmp_path)
    run.root.chmod(0o555)
    try:
        code = cli.main(
            [
                "overrule",
                "--run",
                str(run.root),
                "--candidate",
                "trace-json",
                "--admit",
                "--reason",
                "r",
            ]
        )
    finally:
        run.root.chmod(0o755)
    assert code == 2
    assert capsys.readouterr().out == ""
    assert not run.decisions.exists()


# -- what a human sees at gate 0 ----------------------------------------------


def test_the_text_brief_marks_a_human_ruling_and_sizes_every_admit(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(run, ["trace-json"], action="admit", reason="the traces show real calls")
    seal.seal(run)
    text = brief.gate_brief(run, 0)
    admits = text.split("Admits, by priority")[1].split("\n\n")[0]
    assert "trace-json, 318 bytes (human ruling): the traces show real calls" in admits
    assert "api-json, 1231 bytes: " in admits
    assert "api-json, 1231 bytes (human ruling)" not in admits


def test_a_gap_closed_by_an_unsupplied_projection_still_reads_open(tmp_path):
    run = _staged_run(tmp_path)
    audit = read_json(run.audit)
    audit["deficiencies"][0]["closed_by"] = "prj-1"
    write_json(run.audit, audit)
    seal.seal(run)
    section = brief.gate_brief(run, 0).split("Open deficiencies")[1]
    assert "def-1 [OPEN: fix suggested by prj-1, not supplied]" in section
    assert "[closed by prj-1]" not in section
    gaps = [n for n in brief.gate_data(run, 0)["needs_you"] if n["kind"] == "gap"]
    assert [g["deficiency_id"] for g in gaps] == ["def-1"]


def test_gate_data_lists_every_decline_and_the_effective_and_triage_rulings(tmp_path):
    run = _staged_run(tmp_path)
    overrides.overrule(
        run, ["notes-md"], action="decline", reason="prose only", reason_code="no_evidence_value"
    )
    seal.seal(run)
    data = brief.gate_data(run, 0)
    assert data["sealed"] and not data["locked"]
    declined = {n["candidate_id"] for n in data["needs_you"] if n["kind"] == "decline"}
    assert declined == {f["candidate_id"] for f in data["files"] if f["decision"] == "decline"}
    assert declined == {"notes-md", "trace-json"}
    notes = next(f for f in data["files"] if f["candidate_id"] == "notes-md")
    assert (notes["decision"], notes["authority"], notes["triage_decision"]) == (
        "decline",
        "human",
        "admit",
    )
    assert data["summary"]["overridden"] == 1
    assert [o["candidate_id"] for o in data["overrides"]] == ["notes-md"]
    assert data["decline_codes"] == list(seal.HUMAN_DECLINE_CODES)


def test_gate_data_is_locked_once_intake_has_run(tmp_path):
    run = _staged_run(tmp_path)
    seal.seal(run)
    intake.admit_from_triage(run)
    assert brief.gate_data(run, 0)["locked"] is True


def test_gate_brief_json_parses_and_an_unbuilt_gate_is_exit_two(tmp_path, capsys):
    run = _staged_run(tmp_path)
    seal.seal(run)
    code = cli.main(["gate-brief", "--run", str(run.root), "--gate", "0", "--format", "json"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["gate"] == 0
    code = cli.main(["gate-brief", "--run", str(run.root), "--gate", "1", "--format", "json"])
    out = capsys.readouterr()
    assert code == 2
    assert out.out == ""
    assert "no structured brief" in out.err
