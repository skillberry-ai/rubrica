import pytest

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.validate import (
    ARTIFACT_SCHEMAS,
    STAGE_ARTIFACTS,
    UnknownStage,
    schema_dir,
    validate_artifact,
    validate_stage,
)
from tests.builders import minimal_claims, minimal_world_model


def test_every_stage_has_an_artifact_mapping():
    from testgen.paths import STAGES

    assert set(STAGE_ARTIFACTS) == set(STAGES)


def test_every_mapped_kind_has_a_registered_schema():
    mapped = {k for kinds in STAGE_ARTIFACTS.values() for k in kinds}
    assert mapped <= set(ARTIFACT_SCHEMAS)


def test_this_tasks_schemas_exist_on_disk():
    """Only the two schemas this task creates.

    The other six registered kinds arrive in Tasks 4 and 5; Task 5 adds the
    test that every registered kind has a file.
    """
    for kind in ("claims", "world-model"):
        assert (schema_dir() / ARTIFACT_SCHEMAS[kind]).is_file(), kind


def test_minimal_claims_is_valid(tmp_path):
    path = tmp_path / "c.json"
    write_json(path, minimal_claims())
    assert validate_artifact(path, "claims") == []


def test_minimal_world_model_is_valid(tmp_path):
    path = tmp_path / "wm.json"
    write_json(path, minimal_world_model())
    assert validate_artifact(path, "world-model") == []


def test_claim_without_evidence_is_rejected(tmp_path):
    payload = minimal_claims()
    payload["claims"][0]["evidence"] = []
    path = tmp_path / "c.json"
    write_json(path, payload)
    findings = validate_artifact(path, "claims")
    assert findings
    assert findings[0].layer == "schema"
    assert findings[0].pointer == "/claims/0/evidence"


def test_traversal_shaped_id_is_rejected_by_the_schema(tmp_path):
    payload = minimal_claims()
    payload["claims"][0]["id"] = "../../etc/passwd"
    path = tmp_path / "c.json"
    write_json(path, payload)
    assert any(f.pointer == "/claims/0/id" for f in validate_artifact(path, "claims"))


def test_wrong_schema_version_is_rejected(tmp_path):
    path = tmp_path / "c.json"
    write_json(path, minimal_claims(schema_version="0.2"))
    assert any(f.pointer == "/schema_version" for f in validate_artifact(path, "claims"))


def test_unknown_top_level_key_is_rejected(tmp_path):
    path = tmp_path / "c.json"
    write_json(path, minimal_claims(surprise=1))
    assert validate_artifact(path, "claims")


def test_structured_machine_invariant_is_valid(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {
            "id": "inv-event-count",
            "statement": "event_count equals the number of matching job_events",
            "machine": {
                "form": "count",
                "collection": "jobs",
                "field": "event_count",
                "of": "job_events",
                "local_key": "job_id",
                "foreign_key": "job_id",
            },
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model") == []


def test_machine_invariant_with_an_unknown_form_is_rejected(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {"id": "inv-1", "statement": "s", "machine": {"form": "regex", "pattern": ".*"}}
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_machine_compare_needs_exactly_one_of_field_or_literal(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "s",
            "machine": {
                "form": "compare",
                "collection": "jobs",
                "left": "log_trimmed_size",
                "op": "<=",
                "right": {"field": "log_original_size", "literal": 0},
            },
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_invariant_with_both_machine_and_prose_is_rejected(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "both",
            "machine": {"form": "unique", "collection": "jobs", "field": "job_id"},
            "prose": "also prose",
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_invariant_with_neither_machine_nor_prose_is_rejected(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [{"id": "inv-1", "statement": "neither"}]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_gap_must_name_what_it_blocks(tmp_path):
    payload = minimal_world_model()
    payload["gaps"] = [
        {
            "id": "gap-1",
            "subject": "error semantics",
            "unknown": "what happens on an unknown controller",
            "why_it_matters": "cannot build not_found scenarios",
            "blocks": [],
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert any(f.pointer == "/gaps/0/blocks" for f in validate_artifact(path, "world-model"))


def test_missing_artifact_is_reported_not_raised(tmp_path):
    findings = validate_artifact(tmp_path / "absent.json", "claims")
    assert len(findings) == 1
    assert "missing artifact" in findings[0].message


def test_malformed_artifact_is_reported_not_raised(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    findings = validate_artifact(path, "claims")
    assert len(findings) == 1
    assert "malformed JSON" in findings[0].message


def test_validate_stage_walks_every_claims_file(tmp_path):
    run = RunPaths(tmp_path)
    write_json(run.claims("good"), minimal_claims(artifact_id="good"))
    bad = minimal_claims(artifact_id="bad")
    bad["claims"][0]["confidence"] = "certain"
    write_json(run.claims("bad"), bad)
    findings = validate_stage(run, "extract")
    assert len(findings) == 1
    assert findings[0].artifact == run.claims("bad")


def test_validate_stage_reports_a_stage_that_produced_nothing(tmp_path):
    findings = validate_stage(RunPaths(tmp_path), "reconcile")
    assert len(findings) == 1
    assert "produced no world-model artifact" in findings[0].message


def test_validate_stage_rejects_an_unknown_stage(tmp_path):
    with pytest.raises(UnknownStage):
        validate_stage(RunPaths(tmp_path), "reconsile")


def test_stages_with_no_json_artifact_pass_trivially(tmp_path):
    assert validate_stage(RunPaths(tmp_path), "emit") == []


def test_validate_stage_does_not_raise_on_an_unsafe_instance_directory(tmp_path):
    """_artifact_paths simply never sees an unsafe name any more.

    It builds seed/expected paths from scenario_ids_with_instances(), which
    now excludes them; refs.check_instances reports them instead. Previously
    the join raised UnsafeSegment out of validate_stage.
    """
    from tests.builders import minimal_expected, minimal_seed

    run = RunPaths(tmp_path)
    write_json(run.seed("scn-001"), minimal_seed())
    write_json(run.expected("scn-001"), minimal_expected())
    (run.instances_dir / "scn 001").mkdir(parents=True, exist_ok=True)
    assert validate_stage(run, "instantiate") == []
