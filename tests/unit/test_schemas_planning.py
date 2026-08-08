from testgen.artifacts import write_json
from testgen.validate import validate_artifact
from tests.builders import minimal_coverage, minimal_manifest, minimal_scenarios


def _findings(tmp_path, kind, payload):
    path = tmp_path / f"{kind}.json"
    write_json(path, payload)
    return validate_artifact(path, kind)


def test_minimal_scenarios_is_valid(tmp_path):
    assert _findings(tmp_path, "scenarios", minimal_scenarios()) == []


def test_minimal_coverage_is_valid(tmp_path):
    assert _findings(tmp_path, "coverage", minimal_coverage()) == []


def test_minimal_manifest_is_valid(tmp_path):
    assert _findings(tmp_path, "manifest", minimal_manifest()) == []


def test_duplicate_status_requires_a_target(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    assert _findings(tmp_path, "scenarios", payload)


def test_duplicate_status_with_a_target_is_valid(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    payload["scenarios"][0]["duplicate_of"] = "scn-000"
    assert _findings(tmp_path, "scenarios", payload) == []


def test_rejected_status_requires_a_reason(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "rejected"
    assert _findings(tmp_path, "scenarios", payload)


def test_rejected_reason_is_a_closed_set(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "rejected"
    payload["scenarios"][0]["rejected_reason"] = "did not like it"
    assert _findings(tmp_path, "scenarios", payload)


def test_scenario_must_target_at_least_one_hole(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = []
    findings = _findings(tmp_path, "scenarios", payload)
    assert any(f.pointer == "/scenarios/0/provenance/hole_refs" for f in findings)


def test_malformed_hole_ref_is_rejected(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = ["cap-find-jobs"]
    assert _findings(tmp_path, "scenarios", payload)


def test_goal_hole_ref_is_accepted(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = ["goal:goal-triage"]
    assert _findings(tmp_path, "scenarios", payload) == []


def test_hop_depth_above_five_is_rejected(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["hop_depth"] = 6
    assert _findings(tmp_path, "scenarios", payload)


def test_every_hole_needs_a_justification(tmp_path):
    payload = minimal_coverage()
    del payload["holes"][0]["justification"]
    assert _findings(tmp_path, "coverage", payload)


def test_blocked_by_gap_hole_must_name_the_gap(tmp_path):
    payload = minimal_coverage()
    payload["holes"][0]["reason"] = "blocked_by_gap"
    assert _findings(tmp_path, "coverage", payload)


def test_blocked_by_gap_hole_with_a_gap_id_is_valid(tmp_path):
    payload = minimal_coverage()
    payload["holes"][0]["reason"] = "blocked_by_gap"
    payload["holes"][0]["gap_id"] = "gap-1"
    assert _findings(tmp_path, "coverage", payload) == []


def test_pct_is_a_fraction_not_a_percentage(tmp_path):
    payload = minimal_coverage()
    payload["capability_matrix"]["pct"] = 50
    assert _findings(tmp_path, "coverage", payload)


def test_coverage_verdict_is_a_closed_set(tmp_path):
    assert _findings(tmp_path, "coverage", minimal_coverage(verdict="keep_going"))


def test_manifest_requires_at_least_one_input(tmp_path):
    assert _findings(tmp_path, "manifest", minimal_manifest(inputs=[]))


def test_manifest_rejects_a_short_sha(tmp_path):
    payload = minimal_manifest()
    payload["inputs"][0]["sha256"] = "abc123"
    assert _findings(tmp_path, "manifest", payload)


def test_manifest_requires_stored_as(tmp_path):
    """stored_as is what makes the manifest self-describing for refs.check_inputs.

    Without it, a reader re-verifying a digest would have to re-derive
    intake's naming rule instead of reading the name intake actually used.
    """
    payload = minimal_manifest()
    del payload["inputs"][0]["stored_as"]
    assert _findings(tmp_path, "manifest", payload)


def test_manifest_rejects_an_unsafe_stored_as(tmp_path):
    payload = minimal_manifest()
    payload["inputs"][0]["stored_as"] = "../../etc/passwd"
    assert _findings(tmp_path, "manifest", payload)


def test_manifest_rejects_an_unknown_stage_name(tmp_path):
    payload = minimal_manifest()
    payload["stages"]["reconsile"] = payload["stages"].pop("reconcile")
    assert _findings(tmp_path, "manifest", payload)


def test_manifest_stage_entry_needs_the_full_comparability_triple(tmp_path):
    payload = minimal_manifest()
    del payload["stages"]["reconcile"]["skill_sha256"]
    assert _findings(tmp_path, "manifest", payload)


def test_a_capability_may_declare_a_tool_binding(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    path = tmp_path / "01-world-model.json"
    write_json(path, minimal_world_model())
    assert validate_artifact(path, "world-model") == []
    assert minimal_world_model()["capabilities"][0]["binding"] == {
        "tool": "query_aap2",
        "fixed_args": {"action": "find_jobs"},
    }


def test_a_capability_without_a_binding_still_validates(tmp_path):
    """Optional, so no artifact that validated before this change stops validating."""
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    assert validate_artifact(path, "world-model") == []


def test_a_binding_missing_its_tool_is_rejected(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    world = minimal_world_model()
    world["capabilities"][0]["binding"] = {"fixed_args": {}}
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    assert validate_artifact(path, "world-model") != []


def test_a_binding_with_an_unknown_key_is_rejected(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    world = minimal_world_model()
    world["capabilities"][0]["binding"] = {
        "tool": "query_aap2",
        "fixed_args": {},
        "endpoint": "https://example.invalid",
    }
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    assert validate_artifact(path, "world-model") != []
