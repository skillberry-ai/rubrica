"""intake --run: admitting the triage record's admits into 00-inputs/.

survey.survey over tests/fixtures/corpus-toy/ produces eleven candidates
(gitignore, readme-md, api-json, capture-json plus its four exploded
elements, notes-md, locked-md, tool-defs-py -- see test_survey_fixture.py for
the same corpus). Every test here hand-writes a triage record admitting the
prose file and two of the four trace elements and declining the rest, since
check_triage requires one disposition per candidate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import cli, intake, refs, survey, validate
from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths

FIXTURE = Path(__file__).parent.parent / "fixtures" / "corpus-toy"
NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)

# Every candidate_id survey.survey produces over corpus-toy that is not one of
# the three admitted below (readme-md, capture-json-0, capture-json-1).
_DECLINED = (
    "gitignore",
    "api-json",
    "capture-json",
    "capture-json-2",
    "capture-json-3",
    "notes-md",
    "locked-md",
    "tool-defs-py",
)
_ADMITTED = ("readme-md", "capture-json-0", "capture-json-1")


def _surveyed(tmp_path) -> RunPaths:
    return survey.survey(
        corpus_roots=[FIXTURE],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )


def _triage_record(run_id: str, *, drop_a_disposition: bool, decline_everything: bool) -> dict:
    admitted = () if decline_everything else _ADMITTED
    dispositions = []
    for cid in admitted:
        dispositions.append(
            {
                "candidate_id": cid,
                "disposition": "admit",
                "reason": "carries evidence of the target's shape",
                "authority": "triage",
            }
        )
    for cid in (*_DECLINED, *(_ADMITTED if decline_everything else ())):
        dispositions.append(
            {
                "candidate_id": cid,
                "disposition": "decline",
                "reason_code": "no_evidence_value",
                "reason": "adds nothing the admitted set does not already carry",
                "authority": "triage",
            }
        )
    if drop_a_disposition:
        dispositions = [d for d in dispositions if d["candidate_id"] != "tool-defs-py"]
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {
                    "name": "the admitted set",
                    "evidence": ["readme-md"],
                    "weight": {"candidates": len(admitted), "bytes": 1},
                }
            ],
        },
        "dispositions": dispositions,
        "deficiencies": [],
        "projections": [],
    }


def _surveyed_and_triaged(
    tmp_path, *, drop_a_disposition: bool = False, decline_everything: bool = False
) -> RunPaths:
    run = _surveyed(tmp_path)
    write_json(
        run.triage,
        _triage_record(
            run.root.name,
            drop_a_disposition=drop_a_disposition,
            decline_everything=decline_everything,
        ),
    )
    return run


def test_admitting_writes_inputs_and_a_valid_manifest(tmp_path):
    run = _surveyed_and_triaged(tmp_path)
    assert intake.admit_from_triage(run) == []
    manifest = read_json(run.manifest)
    assert {e["artifact_id"] for e in manifest["inputs"]} == set(_ADMITTED)
    assert validate.validate_stage(run, "intake") == []
    assert refs.check_all(run) == []


def test_the_manifest_takes_its_parameters_from_the_catalogue(tmp_path):
    """Not from argv. One file the human edits at gate 0, one file intake reads."""
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    manifest = read_json(run.manifest)
    catalogue = read_json(run.catalogue)
    assert manifest["target"] == catalogue["request"]["target"]
    assert manifest["limits"] == catalogue["request"]["limits"]
    assert manifest["created_utc"] == catalogue["created_utc"]


def test_a_declined_candidate_is_not_admitted(tmp_path):
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    stored = {p.name for p in run.inputs_dir.iterdir()}
    assert not any("logo" in name or "lock" in name for name in stored)


def test_an_inconsistent_triage_record_is_findings_and_writes_nothing(tmp_path):
    """Exit 1, repairable by re-dispatching triage -- never exit 2. A stage defect
    surfacing as 2 makes the orchestrator halt instead of spending its one repair.
    """
    run = _surveyed_and_triaged(tmp_path, drop_a_disposition=True)
    findings = intake.admit_from_triage(run)
    assert findings
    assert all("00-triage.json" in str(f.artifact) for f in findings)
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


def test_zero_admits_is_findings_rather_than_an_empty_manifest(tmp_path):
    """inputs.minItems is 1, so writing the manifest anyway would surface a
    scoping failure as a schema error against an artifact no prompt wrote."""
    run = _surveyed_and_triaged(tmp_path, decline_everything=True)
    findings = intake.admit_from_triage(run)
    assert findings and not run.manifest.exists()


def test_admitting_twice_refuses_rather_than_rewriting(tmp_path):
    """A re-run gets a new run id so old artifacts stay diffable -- the rule
    intake() already holds for its run directory."""
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    with pytest.raises(FileExistsError):
        intake.admit_from_triage(run)


def test_a_missing_triage_record_is_a_usage_error(tmp_path):
    """Stages run out of order is a misconfigured harness, which is exit 2."""
    run = _surveyed(tmp_path)
    with pytest.raises(UsageError, match="00-triage.json"):
        intake.admit_from_triage(run)


def test_run_and_input_are_mutually_exclusive():
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["intake", "--run", "r", "--input", "x"])


def test_run_mode_rejects_the_parameters_the_catalogue_already_carries():
    """Refused in the CLI rather than resolved by precedence: minting from an
    ambiguous parameter set is the shape that produced findings against an
    unfixable artifact. argparse cannot express "illegal only alongside --run"
    directly, so this is checked in cli.main after parsing and raises
    UsageError rather than exiting through argparse's own SystemExit path.
    """
    with pytest.raises(UsageError):
        cli.main(["intake", "--run", "r", "--target-name", "t"])


def test_intake_run_via_the_cli_prints_the_run_and_exits_clean(tmp_path, capsys):
    run = _surveyed_and_triaged(tmp_path)
    code = cli.main(["intake", "--run", str(run.root)])
    assert code == 0
    assert capsys.readouterr().out.strip() == str(run.root)


def test_intake_run_via_the_cli_reports_findings_at_exit_one(tmp_path, capsys):
    run = _surveyed_and_triaged(tmp_path, drop_a_disposition=True)
    code = cli.main(["intake", "--run", str(run.root)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out.strip()
    assert not run.manifest.exists()
