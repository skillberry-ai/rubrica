"""Writing an accepted instance out as a Harbor task package."""

from __future__ import annotations

import json
import tomllib

from testgen.artifacts import write_json
from testgen.emit import emit_run, suite_template_dir
from testgen.paths import RunPaths
from tests.builders import (
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)

SID = "scn-001"


def _run(tmp_path, *, verdict=..., scenarios=None, world=None, expected=None) -> RunPaths:
    """A run populated through challenge, ready for emit."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, world if world is not None else minimal_world_model())
    write_json(run.scenarios, scenarios if scenarios is not None else minimal_scenarios())
    write_json(run.seed(SID), minimal_seed())
    write_json(run.expected(SID), expected if expected is not None else minimal_expected())
    if verdict is not ...:
        if verdict is not None:
            write_json(run.verdict(SID), verdict)
    else:
        write_json(run.verdict(SID), minimal_verdict())
    return run


def test_an_accepted_instance_produces_all_eight_files(tmp_path):
    run = _run(tmp_path)
    emitted, findings = emit_run(run)
    assert findings == []
    assert emitted == [SID]
    task = run.task_dir(SID)
    for name in ("task.toml", "instruction.md", "seed.json", "golden.json", "provenance.md"):
        assert (task / name).is_file(), name
    for name in ("expected.json", "verify.py", "test.sh"):
        assert (task / "tests" / name).is_file(), name


def test_the_task_toml_is_parseable_and_names_the_target(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    payload = tomllib.loads((run.task_dir(SID) / "task.toml").read_text())
    assert payload["schema_version"] == "1.3"
    assert payload["task"]["name"].endswith(SID)
    assert payload["metadata"]["agent_type"] == "aap2"
    assert payload["environment"]["mcp_servers"][0]["url"] == "${BACKEND_MCP_URL}"
    assert payload["verifier"]["timeout_sec"] > 0
    assert payload["agent"]["timeout_sec"] > 0


def test_the_instruction_is_the_scenarios_user_intent(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    text = (run.task_dir(SID) / "instruction.md").read_text()
    assert text.strip() == minimal_scenarios()["scenarios"][0]["user_intent"]


def test_the_seed_is_copied_verbatim(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    assert (run.task_dir(SID) / "seed.json").read_text() == run.seed(SID).read_text()


def test_the_verifier_and_entrypoint_are_copied_verbatim(tmp_path):
    """The tested file and the executed file must not differ."""
    run = _run(tmp_path)
    emit_run(run)
    for name in ("verify.py", "test.sh"):
        assert (run.task_dir(SID) / "tests" / name).read_bytes() == (
            suite_template_dir() / name
        ).read_bytes()


def test_the_golden_holds_the_reference_answer_and_the_expected_calls(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    golden = json.loads((run.task_dir(SID) / "golden.json").read_text())
    assert golden["answer"] == minimal_expected()["answer_reference"]
    assert golden["tool_calls"] == [
        {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}
    ]


def test_the_provenance_records_the_discriminating_fact_and_the_adversarys_finding(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    text = (run.task_dir(SID) / "provenance.md").read_text()
    assert "exactly one prod0 job failed inside the window" in text
    assert "cell:cap-find-jobs/oc-success" in text
    assert "minimum_tool_calls_found" in text


def test_the_emitted_contract_validates_against_verify_pys_expectations(tmp_path):
    from testgen.suite.verify import CONTRACT, compute_reward

    run = _run(tmp_path)
    emit_run(run)
    contract = json.loads((run.task_dir(SID) / "tests" / "expected.json").read_text())
    assert contract["contract"] == CONTRACT
    reward, _ = compute_reward(
        contract,
        [("query_aap2", {"action": "find_jobs", "controller": "prod0"})],
        "Job 90420.",
        True,
    )
    assert reward["reward"] == 1.0


def test_a_rejected_scenario_is_skipped_without_a_finding(tmp_path):
    """The coverage report already accounts for the cell it lost."""
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    run = _run(tmp_path, scenarios=scenarios, verdict=minimal_verdict(verdict="reject"))
    emitted, findings = emit_run(run)
    assert emitted == []
    assert findings == []
    assert not run.task_dir(SID).exists()


def test_an_instance_with_no_verdict_is_a_finding(tmp_path):
    """emit runs once, after challenge, so here the absence is real."""
    run = _run(tmp_path, verdict=None)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert len(findings) == 1
    assert "has no verdict" in findings[0].message


def test_a_re_seed_verdict_is_a_finding(tmp_path):
    run = _run(tmp_path, verdict=minimal_verdict(verdict="re-seed"))
    emitted, findings = emit_run(run)
    assert emitted == []
    assert any("re-seed" in f.message for f in findings)


def test_an_unbound_capability_becomes_a_finding_and_writes_no_package(tmp_path):
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    run = _run(tmp_path, world=world)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert findings
    assert all(f.layer == "emit" for f in findings)
    assert not run.task_dir(SID).exists(), "a package must not be half-written"


def test_a_missing_world_model_is_a_finding_not_a_crash(tmp_path):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert len(findings) == 1


def test_re_emitting_replaces_a_stale_package(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    stale = run.task_dir(SID) / "stale.txt"
    stale.write_text("left over from an earlier emit")
    emit_run(run)
    assert not stale.exists()


def test_emit_is_byte_stable_across_runs(tmp_path):
    """Two emits of one run directory must produce identical bytes."""
    run = _run(tmp_path)
    emit_run(run)
    first = {
        p.relative_to(run.suite_dir): p.read_bytes()
        for p in sorted(run.suite_dir.rglob("*"))
        if p.is_file()
    }
    emit_run(run)
    second = {
        p.relative_to(run.suite_dir): p.read_bytes()
        for p in sorted(run.suite_dir.rglob("*"))
        if p.is_file()
    }
    assert first == second
