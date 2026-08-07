"""check_suite: an emitted package is complete and addresses a real scenario."""

from __future__ import annotations

from testgen.artifacts import write_json
from testgen.emit import emit_run
from testgen.paths import RunPaths
from testgen.refs import check_suite
from tests.builders import (
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)

SID = "scn-001"

PACKAGE_FILES = (
    "task.toml",
    "instruction.md",
    "seed.json",
    "golden.json",
    "provenance.md",
    "tests/expected.json",
    "tests/verify.py",
    "tests/test.sh",
)


def _emitted_run(tmp_path) -> RunPaths:
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.seed(SID), minimal_seed())
    write_json(run.expected(SID), minimal_expected())
    write_json(run.verdict(SID), minimal_verdict())
    emitted, findings = emit_run(run)
    assert (emitted, findings) == ([SID], [])
    return run


def test_a_freshly_emitted_suite_is_clean(tmp_path):
    assert check_suite(_emitted_run(tmp_path)) == []


def test_no_suite_directory_is_not_a_finding(tmp_path):
    """The normal state before emit runs."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    assert check_suite(run) == []


def test_each_missing_package_file_is_reported(tmp_path):
    for name in PACKAGE_FILES:
        run = _emitted_run(tmp_path / name.replace("/", "_"))
        (run.task_dir(SID) / name).unlink()
        findings = check_suite(run)
        assert len(findings) == 1, f"{name}: {findings}"
        assert name in findings[0].message


def test_a_contract_naming_the_wrong_scenario_is_reported(tmp_path):
    run = _emitted_run(tmp_path)
    path = run.task_dir(SID) / "tests" / "expected.json"
    from testgen.artifacts import read_json

    write_json(path, read_json(path) | {"scenario_id": "scn-999"})
    findings = check_suite(run)
    assert len(findings) == 1
    assert "scn-999" in findings[0].message


def test_a_package_for_a_scenario_that_was_never_proposed_is_reported(tmp_path):
    run = _emitted_run(tmp_path)
    write_json(run.scenarios, minimal_scenarios(scenarios=[]))
    messages = " || ".join(f.message for f in check_suite(run))
    assert "was proposed" in messages


def test_a_package_for_a_non_active_scenario_is_reported(tmp_path):
    run = _emitted_run(tmp_path)
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)
    messages = " || ".join(f.message for f in check_suite(run))
    assert "rejected" in messages
