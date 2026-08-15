"""Satisfying a projection without throwing the run away.

Appending a candidate to the catalogue is the same append-and-record move
02-scenarios.json makes round by round, and a human authoring an admission at
their own gate is what gate 0 is.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import cli, intake, refs, triage
from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths

NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)


def _acceptance() -> dict:
    """The mechanical half of prj-tools' acceptance contract.

    `prose` is the semantic half check_acceptance never touches -- see
    test_structural_acceptance_never_claims_the_file_is_accepted.
    """
    return {
        "classifies_as": "mcp_tool_schema",
        "pointers_required": ["/tools/0/name", "/tools/0/result_shape"],
        "must_contain": ["query_aap2"],
        "must_not_contain": ["TODO"],
        "prose": "Each tool's result_shape truly describes what a caller receives.",
    }


def _catalogue(run_id: str, stamp: datetime) -> dict:
    """One declined candidate, src-notes, the sole source prj-tools projects from."""
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "created_utc": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request": {
            "target": {"name": "ticketq", "interface": "mcp"},
            "objective": "breadth",
            "corpus_roots": ["/tmp/rubrica-nonexistent-corpus"],
            "limits": {"max_rounds": 2, "max_scenarios": 128},
        },
        "policy": {
            "exclusion_reasons": ["binary"],
            "explode_min_elements": 2,
            "explode_min_common_keys": 1,
            "digest_body_chars": 2000,
            "max_candidates": 500,
            "max_catalogue_bytes": 1_000_000,
        },
        "candidates": [
            {
                "candidate_id": "src-notes",
                "origin": "corpus",
                "path": "notes.md",
                "root_index": 0,
                "bytes": 42,
                "sha256": "0" * 64,
                "kind": "design_doc",
                "admissible": True,
                "digest": {},
            }
        ],
        "excluded": [],
    }


def _triage_record(run_id: str) -> dict:
    """src-notes declined needs_projection; prj-tools projects from it, closing def-shapes."""
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {
                    "name": "tool shapes",
                    "evidence": ["src-notes"],
                    "weight": {"candidates": 1, "bytes": 42},
                }
            ],
        },
        "dispositions": [
            {
                "candidate_id": "src-notes",
                "disposition": "decline",
                "reason_code": "needs_projection",
                "reason": "describes tools in prose; no machine-readable result shape",
                "authority": "triage",
            }
        ],
        "deficiencies": [
            {
                "deficiency_id": "def-shapes",
                "subject": "tool result shapes",
                "statement": "no candidate carries a machine-readable result_shape per tool",
            }
        ],
        "projections": [
            {
                "projection_id": "prj-tools",
                "closes": ["def-shapes"],
                "sources": [{"candidate_id": "src-notes", "digest_note": "prose tool list only"}],
                "wanted": {
                    "kind": "mcp_tool_schema",
                    "statement": "an mcp_tool_schema file with each tool's result_shape",
                    "why": "closes def-shapes",
                },
                "method": {
                    "confidence": "medium",
                    "steps": ["read src-notes", "write one JSON object per tool"],
                },
                "acceptance": _acceptance(),
                "boundary": "no implementation code, only the shapes",
            }
        ],
    }


def _run_with_projection(tmp_path) -> RunPaths:
    run, stamp = intake.mint_run(tmp_path / "runs", now=NOW)
    write_json(run.catalogue, _catalogue(run.root.name, stamp))
    write_json(run.triage, _triage_record(run.root.name))
    return run


def _good(tmp_path) -> Path:
    """A file that meets prj-tools' acceptance contract exactly."""
    path = tmp_path / "tools-list.json"
    path.write_text(
        json.dumps({"tools": [{"name": "query_aap2", "result_shape": {}}]}),
        encoding="utf-8",
    )
    return path


def test_a_file_meeting_every_structural_criterion_is_adopted(tmp_path):
    run = _run_with_projection(tmp_path)
    projected = tmp_path / "tools-list.json"
    projected.write_text(
        json.dumps({"tools": [{"name": "query_aap2", "result_shape": {}}]}), encoding="utf-8"
    )
    assert triage.adopt_projection(run, projection_id="prj-tools", source=projected) == []
    catalogue = read_json(run.catalogue)
    adopted = next(c for c in catalogue["candidates"] if c["origin"] == "projection")
    assert adopted["provenance"]["projection_id"] == "prj-tools"
    assert adopted["kind"] == "mcp_tool_schema"
    record = read_json(run.triage)
    disposition = next(
        d for d in record["dispositions"] if d["candidate_id"] == adopted["candidate_id"]
    )
    assert disposition["disposition"] == "admit"
    # The human's authority, not triage's -- and recorded as such, so a reader can
    # tell which admissions the gate authored.
    assert disposition["authority"] == "human"
    assert (
        next(d for d in record["deficiencies"] if d["deficiency_id"] == "def-shapes")["closed_by"]
        == "prj-tools"
    )


def test_the_adopted_candidates_digest_is_computed_not_empty(tmp_path):
    """digest.digest_for_path, not `{}` -- gate-brief (a later stage) renders a
    candidate's digest for the human at gate 0, and a re-dispatched rb-triage
    reading the catalogue fresh would be obliged to decline an empty-digest
    candidate as digest_insufficient, naming the field it needed, for the very
    file a human just manufactured and admitted. That is the failure this test
    pins.

    mcp_tool_schema is not "trace", so digest_for_payload's generic branch
    fires: `{"skeleton": {...}}`, a flat dict keyed by JSON-pointer-shaped
    strings rather than a nested structure -- so the way to confirm it "carries"
    a pointer is membership, not refs.resolve_pointer (which walks nested
    containers, and would not resolve a flat pointer-string key at all). Both
    pointers_required entries land in the skeleton at _SKELETON_DEPTH=3, which
    ties the two halves of the acceptance contract together: the same pointers
    check_acceptance already required resolvable are exactly what triage's own
    reader gets to see.
    """
    run = _run_with_projection(tmp_path)
    assert triage.adopt_projection(run, projection_id="prj-tools", source=_good(tmp_path)) == []
    catalogue = read_json(run.catalogue)
    adopted = next(c for c in catalogue["candidates"] if c["origin"] == "projection")
    assert adopted["digest"]
    skeleton = adopted["digest"]["skeleton"]
    for pointer in _acceptance()["pointers_required"]:
        assert pointer in skeleton, f"{pointer!r} missing from the adopted candidate's skeleton"


def test_the_adopted_run_still_passes_check_all(tmp_path):
    """The seven checks above pin the fields the brief names; this one pins the
    shapes it does not: a wrong provenance, a candidate_id collision, or a
    closes/satisfied_by mismatch would pass every assertion above while still
    leaving the run referentially broken. check_all is the guard that would
    catch what the named-field assertions cannot.
    """
    run = _run_with_projection(tmp_path)
    assert triage.adopt_projection(run, projection_id="prj-tools", source=_good(tmp_path)) == []
    assert refs.check_all(run) == []
    catalogue = read_json(run.catalogue)
    adopted = next(c for c in catalogue["candidates"] if c["origin"] == "projection")
    record = read_json(run.triage)
    projection = next(p for p in record["projections"] if p["projection_id"] == "prj-tools")
    assert projection["satisfied_by"] == adopted["candidate_id"]


def test_a_missing_required_string_is_one_finding_per_failed_check(tmp_path):
    """Exit 1 with findings the worker reads and retries against -- and the same
    findings a future rb-project member would read as its gate."""
    run = _run_with_projection(tmp_path)
    bad = tmp_path / "tools-list.json"
    # Drops must_contain's "query_aap2" AND pointers_required's /tools/0/name --
    # two independent failed checks, so this pins "one finding per check", not
    # just "at least one finding".
    bad.write_text(json.dumps({"tools": [{"result_shape": {}}]}), encoding="utf-8")

    findings = triage.adopt_projection(run, projection_id="prj-tools", source=bad)

    assert len(findings) == 2
    assert all(f.artifact == bad for f in findings)
    assert any("query_aap2" in f.message for f in findings)
    assert any("/tools/0/name" in f.message for f in findings)
    # Nothing was written: a repairable finding must never look like a
    # completed admission.
    assert read_json(run.triage) == _triage_record(run.root.name)


def test_a_forbidden_string_is_a_finding(tmp_path):
    """must_not_contain is the boundary. A projection that dragged in
    implementation defeats the objective it was requested for."""
    run = _run_with_projection(tmp_path)
    bad = tmp_path / "tools-list.json"
    bad.write_text(
        json.dumps(
            {"tools": [{"name": "query_aap2", "result_shape": {}}], "note": "TODO wire this"}
        ),
        encoding="utf-8",
    )

    findings = triage.adopt_projection(run, projection_id="prj-tools", source=bad)

    assert len(findings) == 1
    assert "TODO" in findings[0].message
    assert findings[0].artifact == bad


def test_a_file_of_the_wrong_kind_is_a_finding(tmp_path):
    """classifies_as, checked through intake.classify -- the same classifier
    intake will use, so adoption cannot promise a kind admission then disagrees with."""
    run = _run_with_projection(tmp_path)
    # Otherwise identical to _good()'s content -- passes must_contain,
    # must_not_contain and every pointer -- but intake.classify reads the
    # suffix before it ever looks at the content, so a .md-suffixed file
    # classifies as design_doc regardless of what is inside it. Isolates
    # classifies_as as the one failing check, rather than conflating it with
    # a content failure that would also fail on its own.
    bad = tmp_path / "tools-list.md"
    bad.write_text(
        json.dumps({"tools": [{"name": "query_aap2", "result_shape": {}}]}), encoding="utf-8"
    )

    findings = triage.adopt_projection(run, projection_id="prj-tools", source=bad)

    assert len(findings) == 1
    assert "design_doc" in findings[0].message
    assert "mcp_tool_schema" in findings[0].message


def test_check_only_writes_nothing(tmp_path):
    run = _run_with_projection(tmp_path)
    before = run.catalogue.read_bytes()
    triage.adopt_projection(run, projection_id="prj-tools", source=_good(tmp_path), check_only=True)
    assert run.catalogue.read_bytes() == before


def test_check_only_on_a_failing_file_still_writes_nothing(tmp_path):
    """check_only guards the write path even when acceptance itself would have
    failed anyway -- otherwise this branch would be exercised only by the
    happy path above, and a regression that writes on failure regardless of
    check_only would slip through untested."""
    run = _run_with_projection(tmp_path)
    before_catalogue = run.catalogue.read_bytes()
    before_triage = run.triage.read_bytes()
    bad = tmp_path / "tools-list.json"
    bad.write_text(json.dumps({"tools": [{"result_shape": {}}]}), encoding="utf-8")

    findings = triage.adopt_projection(run, projection_id="prj-tools", source=bad, check_only=True)

    assert findings
    assert run.catalogue.read_bytes() == before_catalogue
    assert run.triage.read_bytes() == before_triage


def test_an_unknown_projection_id_is_a_usage_error(tmp_path):
    """Not a finding: nothing in the run is defective, the caller names something
    that does not exist."""
    run = _run_with_projection(tmp_path)

    with pytest.raises(UsageError, match="prj-nonexistent"):
        triage.adopt_projection(run, projection_id="prj-nonexistent", source=_good(tmp_path))


def test_an_unreadable_source_file_is_a_usage_error(tmp_path):
    """The other UsageError trigger: adopt-projection cannot repair a file that
    is not there to read, so this is a misconfigured invocation, not a
    structural finding against it."""
    run = _run_with_projection(tmp_path)

    with pytest.raises(UsageError):
        triage.adopt_projection(
            run, projection_id="prj-tools", source=tmp_path / "does-not-exist.json"
        )


def test_structural_acceptance_never_claims_the_file_is_accepted(tmp_path):
    """Whether result_shape truly describes what a caller receives is semantic,
    and the rule against inventing a mechanical check for support applies here as
    it applies to layer 2. The prose criterion is the human's to judge."""
    findings = triage.check_acceptance(_good(tmp_path), _acceptance())
    assert findings == []
    # And the CLI's success line says so:
    assert "structural" in triage.ACCEPTANCE_PASS_MESSAGE.lower()
    assert "accepted" not in triage.ACCEPTANCE_PASS_MESSAGE.lower()


def test_adopt_projection_via_the_cli_prints_the_pass_message_and_exits_clean(tmp_path, capsys):
    run = _run_with_projection(tmp_path)
    good = _good(tmp_path)
    code = cli.main(
        [
            "adopt-projection",
            "--run",
            str(run.root),
            "--projection",
            "prj-tools",
            "--file",
            str(good),
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == triage.ACCEPTANCE_PASS_MESSAGE
    catalogue = read_json(run.catalogue)
    assert any(c["origin"] == "projection" for c in catalogue["candidates"])


def test_adopt_projection_via_the_cli_reports_findings_at_exit_one(tmp_path, capsys):
    run = _run_with_projection(tmp_path)
    bad = tmp_path / "tools-list.json"
    bad.write_text(json.dumps({"tools": [{"result_shape": {}}]}), encoding="utf-8")
    code = cli.main(
        [
            "adopt-projection",
            "--run",
            str(run.root),
            "--projection",
            "prj-tools",
            "--file",
            str(bad),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out.strip()
    assert read_json(run.triage) == _triage_record(run.root.name)


def test_adopt_projection_via_the_cli_reports_an_unknown_projection_as_exit_two(tmp_path, capsys):
    run = _run_with_projection(tmp_path)
    good = _good(tmp_path)
    code = cli.main(
        [
            "adopt-projection",
            "--run",
            str(run.root),
            "--projection",
            "prj-nonexistent",
            "--file",
            str(good),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.strip()
