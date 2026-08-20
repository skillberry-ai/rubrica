from pathlib import Path

import pytest

from rubrica.artifacts import write_json
from rubrica.paths import RunPaths
from rubrica.validate import (
    ARTIFACT_SCHEMAS,
    STAGE_ARTIFACTS,
    UnknownStage,
    schema_dir,
    validate_artifact,
    validate_stage,
)
from tests.builders import (
    minimal_agents,
    minimal_capabilities_part,
    minimal_catalogue,
    minimal_claims,
    minimal_contradictions_part,
    minimal_coverage,
    minimal_entities_part,
    minimal_expected,
    minimal_gaps_part,
    minimal_goals_part,
    minimal_gold,
    minimal_manifest,
    minimal_outcomes_part,
    minimal_report,
    minimal_scenarios,
    minimal_seed,
    minimal_subjects,
    minimal_suite_expected,
    minimal_triage,
    minimal_verdict,
    minimal_world_model,
)


def test_every_stage_has_an_artifact_mapping():
    from rubrica.paths import STAGES

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


def test_the_schemas_live_inside_the_package_so_a_wheel_can_validate():
    """schema_dir() must resolve beside validate.py, not at the repo root.

    Walking up to the repository root only ever worked for the editable
    install make setup performs; in a wheel it resolved to a nonexistent
    path, so an installed copy silently could not validate anything.
    """
    import rubrica

    package_root = Path(rubrica.__file__).resolve().parent
    assert schema_dir() == package_root / "schema"
    assert schema_dir().is_dir()


def test_the_schema_directory_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    assert schema_dir() == tmp_path


# Every registered artifact kind -> the builder for its minimal valid payload.
# Keyed off ARTIFACT_SCHEMAS below, so registering a kind without adding its
# builder here fails loudly rather than silently skipping it.
MINIMAL_BUILDERS = {
    "catalogue": minimal_catalogue,
    "triage": minimal_triage,
    "subjects": minimal_subjects,
    "contradictions-part": minimal_contradictions_part,
    "capabilities-part": minimal_capabilities_part,
    "outcomes-part": minimal_outcomes_part,
    "entities-part": minimal_entities_part,
    "goals-part": minimal_goals_part,
    "gaps-part": minimal_gaps_part,
    "manifest": minimal_manifest,
    "claims": minimal_claims,
    "world-model": minimal_world_model,
    "scenarios": minimal_scenarios,
    "coverage": minimal_coverage,
    "seed": minimal_seed,
    "expected": minimal_expected,
    "verdict": minimal_verdict,
    "suite-expected": minimal_suite_expected,
    "report": minimal_report,
    "agents": minimal_agents,
    "gold": minimal_gold,
}


def test_every_registered_kind_has_a_minimal_builder():
    assert set(MINIMAL_BUILDERS) == set(ARTIFACT_SCHEMAS)


@pytest.mark.parametrize("kind", sorted(ARTIFACT_SCHEMAS))
def test_the_minimal_payload_for_every_kind_is_valid(tmp_path, kind):
    """The other half of the closed-world check below: the baseline is clean,
    so a finding there can only come from the key the next test adds."""
    path = tmp_path / f"{kind}.json"
    write_json(path, MINIMAL_BUILDERS[kind]())
    assert validate_artifact(path, kind) == []


@pytest.mark.parametrize("kind", sorted(ARTIFACT_SCHEMAS))
def test_an_unknown_top_level_key_is_rejected_for_every_kind(tmp_path, kind):
    """additionalProperties: false at every artifact root, not just one.

    A stage that invents a top-level field is inventing contract, and a
    downstream reader that does not know the field would silently ignore it.
    """
    path = tmp_path / f"{kind}.json"
    write_json(path, MINIMAL_BUILDERS[kind](surprise_key=1))
    findings = validate_artifact(path, kind)
    assert findings, f"{kind} accepted an unknown top-level key"
    assert any("surprise_key" in f.message for f in findings), [f.message for f in findings]


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
    findings = validate_stage(RunPaths(tmp_path), "reconcile-seal")
    assert len(findings) == 1
    assert "produced no world-model artifact" in findings[0].message


def test_validate_stage_rejects_an_unknown_stage(tmp_path):
    with pytest.raises(UnknownStage):
        validate_stage(RunPaths(tmp_path), "reconsile")


def test_every_stage_now_has_a_real_gate(tmp_path):
    """Placeholder behaviour this task removes: every stage used to map to
    () and pass trivially. emit and smoke are the last two stages that did,
    and an empty run now fails both -- exit 0 here would tell the
    orchestrator that an empty suite, or a run with no report, was a
    success.
    """
    run = RunPaths(tmp_path)
    assert validate_stage(run, "emit") != []
    assert validate_stage(run, "smoke") != []


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


def test_the_emit_stage_reports_a_run_that_produced_no_package(tmp_path):
    """Exit 0 here would tell the orchestrator an empty suite was a success."""
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "emit")
    assert len(findings) == 1
    assert "produced no suite-expected artifact" in findings[0].message


def test_the_smoke_stage_reports_a_run_with_no_report(tmp_path):
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "smoke")
    assert len(findings) == 1
    assert "produced no report artifact" in findings[0].message


def test_an_emitted_contract_validates(tmp_path):
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    path = tmp_path / "expected.json"
    write_json(path, minimal_suite_expected())
    assert validate_artifact(path, "suite-expected") == []


def test_a_contract_with_the_wrong_contract_string_is_rejected(tmp_path):
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    path = tmp_path / "expected.json"
    write_json(path, minimal_suite_expected(contract="bench/v2"))
    assert validate_artifact(path, "suite-expected") != []


def test_a_data_assertion_carrying_a_tool_is_rejected(tmp_path):
    """The two assertion shapes must stay distinguishable in the emitted file."""
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    payload = minimal_suite_expected()
    payload["assertions"][0]["tool"] = "query_aap2"
    path = tmp_path / "expected.json"
    write_json(path, payload)
    assert validate_artifact(path, "suite-expected") != []


def test_a_trajectory_assertion_without_a_tool_is_rejected(tmp_path):
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    payload = minimal_suite_expected()
    del payload["assertions"][1]["tool"]
    path = tmp_path / "expected.json"
    write_json(path, payload)
    assert validate_artifact(path, "suite-expected") != []


def test_weights_other_than_verifys_defaults_are_rejected(tmp_path):
    """Authoring-time backstop for verify.py's runtime refusal.

    verify.py exits 2 without writing a reward when a contract's weights do
    not sum to 1.0. emit only ever writes verify.DEFAULT_WEIGHTS, so the
    schema pins those exact constants with const -- JSON Schema has no sum
    constraint -- catching the defect at validate time instead of at score
    time.
    """
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    payload = minimal_suite_expected()
    payload["weights"] = {"assertions": 0.5, "trajectory": 0.5}
    path = tmp_path / "expected.json"
    write_json(path, payload)
    assert validate_artifact(path, "suite-expected") != []


def test_a_minimal_report_validates(tmp_path):
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_report

    path = tmp_path / "07-report.json"
    write_json(path, minimal_report())
    assert validate_artifact(path, "report") == []


def test_an_unscored_result_need_not_carry_a_reward(tmp_path):
    """Unscoreable is not zero: verify.py refuses rather than reporting 0.0."""
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_report

    payload = minimal_report()
    payload["tasks"][0]["results"][0] = {"role": "oracle", "scored": False}
    path = tmp_path / "07-report.json"
    write_json(path, payload)
    assert validate_artifact(path, "report") == []


def test_a_scored_result_must_carry_a_reward(tmp_path):
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact
    from tests.builders import minimal_report

    payload = minimal_report()
    payload["tasks"][0]["results"][0] = {"role": "oracle", "scored": True}
    path = tmp_path / "07-report.json"
    write_json(path, payload)
    assert validate_artifact(path, "report") != []


def test_a_report_over_no_tasks_is_rejected(tmp_path):
    """The "passes trivially" defect the emit and smoke gates exist to remove.

    tasks: [] with verdict: "healthy" validated clean and `validate --stage
    smoke` reported success -- a green smoke gate over a suite nobody ran.
    """
    from rubrica.artifacts import write_json
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_artifact, validate_stage
    from tests.builders import minimal_report

    payload = minimal_report(
        tasks=[],
        summary={
            "mean_reward_by_role": {},
            "all_pass_tasks": 0,
            "all_fail_tasks": 0,
            "oracle_failures": 0,
            "unscoreable": 0,
        },
    )
    run = RunPaths(tmp_path)
    write_json(run.report, payload)
    findings = validate_artifact(run.report, "report")
    assert findings
    assert any(f.pointer == "/tasks" for f in findings), [f.pointer for f in findings]
    assert validate_stage(run, "smoke") != [], "the smoke gate must not pass over no tasks"


# -- the coverage stage's two artifacts ------------------------------------
def test_the_score_stage_reports_a_coverage_directory_with_no_latest(tmp_path):
    """Every coverage check added in Tasks 2 and 4 was bypassable without this.

    _artifact_paths globbed 03-coverage/*.json, so round-1.json alone satisfied
    the gate -- while refs.check_limits and refs.check_coverage both read
    coverage_latest and return [] when it is absent. A score stage that wrote the
    round file and forgot the pointer passed both gates with every coverage
    check skipped.
    """
    from rubrica.artifacts import write_json
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage
    from tests.builders import minimal_coverage

    run = RunPaths(tmp_path)
    write_json(run.coverage_round(1), minimal_coverage())
    assert not run.coverage_latest.exists()

    findings = validate_stage(run, "score")

    assert len(findings) == 1, [str(f) for f in findings]
    assert findings[0].artifact == run.coverage_latest
    assert "missing artifact" in findings[0].message


def test_the_score_stage_still_validates_the_round_files(tmp_path):
    """Requiring latest.json must not stop the round files being checked."""
    from rubrica.artifacts import write_json
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage
    from tests.builders import minimal_coverage

    run = RunPaths(tmp_path)
    write_json(run.coverage_latest, minimal_coverage())
    write_json(run.coverage_round(1), minimal_coverage(schema_version="0.9"))

    findings = validate_stage(run, "score")

    assert len(findings) == 1, [str(f) for f in findings]
    assert findings[0].artifact == run.coverage_round(1)


def test_the_score_stage_is_clean_with_latest_and_its_rounds(tmp_path):
    from rubrica.artifacts import write_json
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage
    from tests.builders import minimal_coverage

    run = RunPaths(tmp_path)
    write_json(run.coverage_latest, minimal_coverage())
    write_json(run.coverage_round(1), minimal_coverage())
    assert validate_stage(run, "score") == []


def test_the_score_stage_reports_a_run_with_no_coverage_directory(tmp_path):
    """No 03-coverage/ at all is still "produced no coverage artifact"."""
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "score")
    assert len(findings) == 1
    assert "produced no coverage artifact" in findings[0].message


def test_manifest_stage_efforts_tracks_a_schema_override(tmp_path, monkeypatch):
    """Reads the *active* schema directory, so RUBRICA_SCHEMA_DIR moves it.

    Without this the caching could be hiding a read that happens once against
    the shipped schema and never again -- which would make the "no second copy"
    claim false in exactly the case a candidate schema is being tried.

    No cache_clear() here: the cache is keyed on schema_dir() (same pattern
    _validator_for uses for the same reason), so the override takes effect on
    the very next call with no teardown discipline required to make this test
    meaningful. An earlier version of this test called manifest_stage_efforts
    .cache_clear() before and after -- that only worked because the function
    was cached on zero arguments back then, and it is gone now that the public
    function is not the cached one.
    """
    from rubrica.artifacts import read_json
    from rubrica.validate import ARTIFACT_SCHEMAS, manifest_stage_efforts, schema_dir

    original = read_json(schema_dir() / ARTIFACT_SCHEMAS["manifest"])
    original["properties"]["stages"]["additionalProperties"]["properties"]["effort"]["enum"] = [
        "low",
        "ludicrous",
    ]
    write_json(tmp_path / ARTIFACT_SCHEMAS["manifest"], original)
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))
    assert manifest_stage_efforts() == ("low", "ludicrous")
