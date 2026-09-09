import json
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
    minimal_adoptions,
    minimal_agents,
    minimal_audit,
    minimal_batches,
    minimal_capabilities_part,
    minimal_catalogue,
    minimal_claims,
    minimal_contradictions_part,
    minimal_coverage,
    minimal_dispositions_part,
    minimal_entities_part,
    minimal_expected,
    minimal_gaps_part,
    minimal_goals_part,
    minimal_gold,
    minimal_interface,
    minimal_manifest,
    minimal_objective,
    minimal_outcomes_part,
    minimal_report,
    minimal_scenarios,
    minimal_scenarios_part,
    minimal_score_part,
    minimal_seed,
    minimal_services_part,
    minimal_slices,
    minimal_subjects,
    minimal_suite_expected,
    minimal_triage,
    minimal_verdict,
    minimal_waivers,
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
    "services-part": minimal_services_part,
    "interface": minimal_interface,
    "batches": minimal_batches,
    "scenarios-part": minimal_scenarios_part,
    "score-part": minimal_score_part,
    "slices": minimal_slices,
    "objective": minimal_objective,
    "dispositions-part": minimal_dispositions_part,
    "audit": minimal_audit,
    "adoptions": minimal_adoptions,
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
    "waivers": minimal_waivers,
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


# The one artifact whose root is deliberately open, and the reason the check
# below excludes it rather than being weakened for everybody. `interface` is an
# OpenAPI document: its top-level vocabulary is OpenAPI's, not ours, so
# `components` or `servers` appearing there is a later step adding a key the
# format already defines rather than a stage inventing contract. What this
# project *does* own inside that document -- its `x-rubrica` provenance block,
# and each path item, where a second HTTP method would be a synthesis defect --
# is closed, and test_the_interface_document_closes_the_blocks_this_project_owns
# below is what holds that half, so the property is moved rather than dropped.
OPEN_ROOT_KINDS = frozenset({"interface"})


@pytest.mark.parametrize("kind", sorted(set(ARTIFACT_SCHEMAS) - OPEN_ROOT_KINDS))
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


def test_the_interface_document_closes_the_blocks_this_project_owns(tmp_path):
    """The open root above, bounded: open at the top, closed where we own it.

    Both halves are asserted, because the open root is only defensible if the
    parts that are ours are shut. A second HTTP method on a path is a synthesis
    defect -- the carrier convention is one `post` per tool -- and an
    unrecognised key inside `x-rubrica` is a stage inventing provenance.
    """
    # The exemption is a singleton, pinned here rather than left implicit: this
    # test is hand-written for `interface` and not parameterised, so a second
    # kind added to OPEN_ROOT_KINDS would silently lose the closed-root property
    # with nothing going red. Extending the exemption now forces whoever does it
    # to extend the replacement too.
    # `sorted(...)` rather than `== frozenset({"interface"})`: ruff SIM300 reads an
    # ALL_CAPS name as the constant and calls that form a Yoda condition. Same
    # predicate -- a set equals a one-element set exactly when its sorted list does.
    assert sorted(OPEN_ROOT_KINDS) == ["interface"]

    path = tmp_path / "interface.json"

    # Open at the root: an OpenAPI key we do not model is carried, not rejected.
    write_json(path, minimal_interface(servers=[{"url": "https://example.invalid"}]))
    assert validate_artifact(path, "interface") == []

    payload = minimal_interface()
    payload["paths"]["/query_aap2"]["get"] = {"operationId": "query_aap2"}
    write_json(path, payload)
    findings = validate_artifact(path, "interface")
    assert findings, "a second HTTP method on a path item must be rejected"
    # The QUOTED form, and the pointer beside it. A bare `"get" in f.message` is
    # the substring-of-message shape CLAUDE.md names: the word "target" contains
    # "get", so any future finding mentioning a target would satisfy it for the
    # wrong reason. The pointer also pins _pointer's RFC 6901 escaping -- an
    # interface document's path keys all begin with `/`, so `/paths//query_aap2`
    # would be indistinguishable from a property named "" followed by one named
    # "query_aap2".
    assert any("'get'" in f.message for f in findings), [f.message for f in findings]
    assert [f.pointer for f in findings] == ["/paths/~1query_aap2"], [f.pointer for f in findings]

    payload = minimal_interface()
    payload["x-rubrica"]["surprise_key"] = 1
    write_json(path, payload)
    findings = validate_artifact(path, "interface")
    assert findings, "x-rubrica accepted an unknown key"
    assert any("surprise_key" in f.message for f in findings), [f.message for f in findings]


def test_minimal_claims_is_valid(tmp_path):
    path = tmp_path / "c.json"
    write_json(path, minimal_claims())
    assert validate_artifact(path, "claims") == []


def test_minimal_world_model_is_valid(tmp_path):
    path = tmp_path / "wm.json"
    write_json(path, minimal_world_model())
    assert validate_artifact(path, "world-model") == []


def test_the_world_model_carries_services_optionally_and_still_checks_them(tmp_path):
    """`services` is optional, and the optional key is the one that needs a test.

    Optional because a target declaring no tools has nothing to say, and because
    both committed live recordings predate the key -- requiring it would
    invalidate the only behavioural evidence the refusal conditions have and
    oblige a paid re-record. The consequence is that minimal_world_model omits
    it, so nothing else follows `#/$defs/service`: jsonschema resolves a $ref
    only when the instance reaches it, so an unresolvable one would sit here
    unnoticed for as long as every tested world model left the key out. Both
    directions, because "accepted" alone would also be true of a key nothing
    constrains.
    """
    path = tmp_path / "wm.json"
    services = minimal_services_part()["services"]
    write_json(path, minimal_world_model(services=services))
    assert validate_artifact(path, "world-model") == []

    del services[0]["signals"]
    write_json(path, minimal_world_model(services=services))
    findings = validate_artifact(path, "world-model")
    assert findings, "a service with no signals must be rejected"
    assert any("signals" in f.message for f in findings), [f.message for f in findings]


def test_claim_without_evidence_is_rejected(tmp_path):
    payload = minimal_claims()
    payload["claims"][0]["evidence"] = []
    path = tmp_path / "c.json"
    write_json(path, payload)
    findings = validate_artifact(path, "claims")
    assert findings
    assert findings[0].layer == "schema"
    assert findings[0].pointer == "/claims/0/evidence"


def test_a_tool_claim_carrying_its_input_schema_validates(tmp_path):
    """The seventh kind, and the payload the whole design rests on reaching synthesis.

    `payload` is `{"type": "object"}` in claims-0.1.json -- free-form on purpose,
    because a tool's input schema is whatever the target declared. So this asserts
    the *kind* is admitted and that a nested schema survives the round trip; the
    shape of the schema itself is not layer 1's business.
    """
    path = tmp_path / "01-claims" / "api-json.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "artifact_id": "api-json",
                "claims": [
                    {
                        "id": "clm-api-010",
                        "kind": "tool",
                        "statement": "query_tickets is the only tool the target declares",
                        "payload": {
                            "type": "object",
                            "required": ["action"],
                            "properties": {"action": {"type": "string"}},
                        },
                        "evidence": [
                            {"artifact_id": "api-json", "locator": "#/tools/0/input_schema"}
                        ],
                        "confidence": "high",
                        "derivation": "stated",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert validate_artifact(path, "claims") == []


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
            # $defs/invariant has required `claims` since the read-coverage
            # variance (docs/design/findings.md) was closed. The one id
            # minimal_claims declares: this test is about the `machine` form
            # validating, so the rest of the invariant is the minimum the schema
            # accepts rather than anything the test asserts on.
            "claims": ["clm-001"],
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


def test_validate_stage_walks_every_disposition_part(tmp_path):
    """Same shape as extract's claims check above, one directory over: a
    triage-rule dispatch's own `invokes = ["validate"]` runs `rubrica validate
    --stage triage-rule`, which has to resolve `dispositions-part` to
    `00-dispositions/*.json` or that gate cannot run at all."""
    run = RunPaths(tmp_path)
    write_json(run.disposition_part("s01"), minimal_dispositions_part(slice_id="s01"))
    bad = minimal_dispositions_part(slice_id="s02")
    bad["dispositions"][0]["authority"] = "not-a-real-authority"
    write_json(run.disposition_part("s02"), bad)
    findings = validate_stage(run, "triage-rule")
    assert len(findings) == 1
    assert findings[0].artifact == run.disposition_part("s02")


def test_validate_stage_reports_a_stage_that_produced_nothing(tmp_path):
    findings = validate_stage(RunPaths(tmp_path), "reconcile-seal")
    assert len(findings) == 1
    assert "produced no world-model artifact" in findings[0].message


@pytest.mark.parametrize("stage", sorted(STAGE_ARTIFACTS))
def test_every_stage_reports_findings_without_raising_on_a_bare_run(stage, tmp_path):
    """Systemic guard against a missing `_artifact_paths` branch.

    Two artifact kinds have now shipped with no matching branch in
    `_artifact_paths` -- `dispositions-part` (fixed before this test existed)
    and `objective` (fixed alongside this test). Both failures had the same
    shape: `validate_stage` calls `_artifact_paths(run, kind)`, which falls
    through to `raise KeyError(f"unknown artifact kind {kind!r}")` -- an
    exception `validate_stage` does not catch, so it escapes past the
    findings-or-clean contract this module exists to hold. A member whose own
    `invokes = ["validate"]` step hits this does not get a repairable finding
    naming its own artifact; it gets a raw crash that, wrapped by whatever
    dispatched it, can surface as a fabricated finding blaming the run for a
    defect that lives here instead.

    A bare run -- no artifacts written at all -- is deliberately the
    strictest input: every kind's `_artifact_paths` branch must both exist
    and return cleanly (typically `[]` or a path list) rather than raise, so
    `validate_stage` can turn "nothing produced" into an honest finding
    instead of an unhandled exception. The next kind added to
    `STAGE_ARTIFACTS` without a matching branch fails here, by the stage's
    own name, rather than three stages later as a mystery crash.
    """
    findings = validate_stage(RunPaths(tmp_path), stage)
    assert isinstance(findings, list)
    assert findings, f"stage {stage!r} reported nothing at all for a bare run"


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


# -- score-seal's two coverage artifacts ------------------------------------
# The "coverage" kind is score-seal's gate, not score's: score writes only the
# rulings, the holes and the verdict, and the matrices and the report around them
# are the seal's arithmetic.
def test_the_score_seal_reports_a_coverage_directory_with_no_latest(tmp_path):
    """Every coverage check added in Tasks 2 and 4 was bypassable without this.

    _artifact_paths globbed 03-coverage/*.json, so round-1.json alone satisfied
    the gate -- while refs.check_limits and refs.check_coverage both read
    coverage_latest and return [] when it is absent. A score-seal that wrote the
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

    findings = validate_stage(run, "score-seal")

    assert len(findings) == 1, [str(f) for f in findings]
    assert findings[0].artifact == run.coverage_latest
    assert "missing artifact" in findings[0].message


def test_the_score_seal_still_validates_the_round_files(tmp_path):
    """Requiring latest.json must not stop the round files being checked."""
    from rubrica.artifacts import write_json
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage
    from tests.builders import minimal_coverage

    run = RunPaths(tmp_path)
    write_json(run.coverage_latest, minimal_coverage())
    write_json(run.coverage_round(1), minimal_coverage(schema_version="0.9"))

    findings = validate_stage(run, "score-seal")

    assert len(findings) == 1, [str(f) for f in findings]
    assert findings[0].artifact == run.coverage_round(1)


def test_the_score_seal_is_clean_with_latest_and_its_rounds(tmp_path):
    from rubrica.artifacts import write_json
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage
    from tests.builders import minimal_coverage

    run = RunPaths(tmp_path)
    write_json(run.coverage_latest, minimal_coverage())
    write_json(run.coverage_round(1), minimal_coverage())
    assert validate_stage(run, "score-seal") == []


def test_the_score_seal_reports_a_run_with_no_coverage_directory(tmp_path):
    """No 03-coverage/ at all is still "produced no coverage artifact"."""
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "score-seal")
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


def test_a_structurally_invalid_schema_is_a_usage_error_not_a_finding(tmp_path, monkeypatch):
    """A readable-but-invalid schema file is a misconfigured run: exit 2, not 1.

    It is the same class as a schema file that is *absent*, which read_json one
    line above already turns into ArtifactError and cli.py already exits 2 for.
    Measured before this door existed, against a copied schema/ whose
    slices-0.1.json was replaced by {"type": 7}: exit 1, nine stdout lines, and
    an [internal] finding anchored on the run directory -- three violations of
    the exit-code contract at once, the last of them naming an artifact that was
    not the broken one and in fact was not broken at all.
    """
    from jsonschema.exceptions import SchemaError

    from rubrica.artifacts import read_json
    from rubrica.errors import UsageError
    from rubrica.validate import ARTIFACT_SCHEMAS, _validator_for, schema_dir

    for filename in ARTIFACT_SCHEMAS.values():
        write_json(tmp_path / filename, read_json(schema_dir() / filename))
    write_json(tmp_path / ARTIFACT_SCHEMAS["slices"], {"type": 7})
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path))

    with pytest.raises(UsageError) as caught:
        _validator_for("slices", tmp_path)
    # The path, so the operator knows which file to fix -- the [internal]
    # finding this replaced named the run root instead.
    assert str(tmp_path / ARTIFACT_SCHEMAS["slices"]) in str(caught.value)
    # UsageError, not SchemaError: what escapes decides the exit code, and
    # SchemaError is neither in cli.py's usage tuple nor a subclass of anything
    # in it, so it would reach the catch-all and become a 1 again.
    assert not isinstance(caught.value, SchemaError)
    # One line. SchemaError's own str is eleven, dumping the metaschema branch.
    assert "\n" not in str(caught.value)


# The propose/score loop's part kinds. Registered here rather than only in
# test_schemas_planning.py because the registration itself -- kind -> filename,
# and the filename present as package data -- is what this module owns.
@pytest.mark.parametrize("kind", ["batches", "scenarios-part", "score-part"])
def test_the_new_round_kinds_resolve_to_a_shipped_schema(kind):
    assert kind in ARTIFACT_SCHEMAS
    assert (schema_dir() / ARTIFACT_SCHEMAS[kind]).is_file()


def test_a_batches_document_validates(tmp_path):
    path = tmp_path / "batches.json"
    write_json(
        path,
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {"id": "b01", "hole_refs": ["cell:cap-a/oc-success"], "projected_bytes": 1600},
            ],
        },
    )
    assert validate_artifact(path, "batches") == []


def test_a_batches_document_with_no_batches_is_refused(tmp_path):
    # Zero batches means nothing to dispatch. propose-batches writes no
    # document at all when there are no closable holes, so a batches file that
    # exists and is empty is a partition defect rather than a quiet round.
    path = tmp_path / "batches.json"
    write_json(
        path,
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [],
        },
    )
    assert validate_artifact(path, "batches") != []


def test_the_batches_gate_walks_the_rounds_that_have_a_plan(tmp_path):
    """`_artifact_paths("batches")` iterates `batches_rounds()`, so two rounds are
    two gated documents anchored on their own files rather than one shared path.

    Per-round is the whole reason the plan is not a singleton: a `02-batches.json`
    overwritten by round 2 would have round 1's parts checked against round 2's
    assignment. Round 3 is written broken and round 2 correct, so a gate that
    validated only the first or only the last would come back green.
    """
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage

    run = RunPaths(tmp_path)
    plan = {
        "schema_version": "0.1",
        "round": 2,
        "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [{"id": "b01", "hole_refs": ["cell:cap-a/oc-success"], "projected_bytes": 1600}],
    }
    write_json(run.batches(2), plan)
    write_json(run.batches(3), dict(plan, round=3, batches=[]))
    findings = validate_stage(run, "propose-batches")
    assert [f.artifact for f in findings] == [run.batches(3)], [str(f) for f in findings]


def test_the_batches_gate_over_a_run_with_no_plan_names_the_run_root(tmp_path):
    """The iterated resolver returns `[]` when no round has a plan, and
    `validate_stage`'s "produced no X artifact" arm then fires against the run
    root.

    **So this gate must not be run on a terminal round.** `propose-batches` writes
    no document at all when no hole is closable, which is how the loop learns it is
    over -- and this is what that state costs if the gate is run anyway, which is
    why `rb-orchestrate`'s loop step 1 gates only when a plan was written.

    Pinned rather than left implicit, because Task 8's brief and its Ruling R2 both
    justified the iterated resolver by claiming it "would" avoid failing layer 1 on
    a correct terminal round -- and it does not. What it actually avoids is naming a
    `02-batches/round-N.json` that was never written, since `_artifact_paths` has no
    round number to build one from. The resolver's own comment now says so; this
    test is what keeps the two from drifting apart again.
    """
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "propose-batches")
    assert [f.artifact for f in findings] == [run.root]
    assert "produced no batches artifact" in findings[0].message


def test_the_interface_gate_over_a_run_with_no_services_names_the_run_root(tmp_path):
    """The batches trap, one band earlier, and the mirror of the test above.

    `01-interfaces/` holds one document per service, so the iterated resolver
    returns `[]` for a run with no service -- and `validate_stage`'s "produced no X
    artifact" arm then fires against the run root.

    **So this gate must not be run when synthesis printed no path.** A target whose
    corpus declares no tool at all is a real target: `rb-reconcile-services` is
    instructed to write `services: []` for one rather than invent a service, and
    `interfaces.synthesise` then correctly writes nothing and exits 0. Measured on
    such a run before `rb-orchestrate` was told to gate conditionally:
    `synthesise-interfaces` exited 0 printing nothing, `validate --stage
    reconcile-services` exited 0, `check-refs` exited 0, and this gate exited 1
    naming the run root -- a finding against a run with no defect, which would then
    have cost the run its one repair attempt on a pass that would honestly write
    `services: []` again.

    Pinned rather than left to the prose, for the reason the batches test above is:
    the resolver's comment and the orchestrator's instruction are the only two
    places this rule lives, and neither is executable.
    """
    from rubrica.paths import RunPaths
    from rubrica.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "synthesise-interfaces")
    assert [f.artifact for f in findings] == [run.root]
    assert "produced no interface artifact" in findings[0].message


def test_a_batch_projecting_zero_bytes_is_refused(tmp_path):
    """`minimum: 1`, because 0 is unreachable by the formula the field states.

    projected_bytes is hole_refs length times bytes_per_scenario, and both factors
    carry their own floor -- minItems: 1 and minimum: 1 -- so a product of 0 can
    only come from a partition that did not compute what it claims to have
    computed. Layer 1 refuses it outright rather than leaving the sole objection
    to a recompute a run may never reach.
    """
    payload = minimal_batches()
    payload["batches"][0]["projected_bytes"] = 0
    path = tmp_path / "batches.json"
    write_json(path, payload)
    assert validate_artifact(path, "batches") != []


def test_a_scenarios_part_validates_and_carries_its_own_batch_id(tmp_path):
    path = tmp_path / "scenarios-part.json"
    write_json(path, {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []})
    # An empty array is a real record: this member swept its batch and closed
    # nothing, the same reading contradictions-part-0.1.json gives its own.
    assert validate_artifact(path, "scenarios-part") == []


def test_a_scenarios_part_holds_its_scenarios_to_the_shared_definition(tmp_path):
    """The cross-file $ref both resolves and constrains.

    The empty-array case above cannot reach it -- `items` is never applied to an
    empty array, so scenarios-part-0.1.json would pass that test with its $ref
    pointing at nothing. This is the fixture-cannot-reach weakness, and the two
    directions here are the fix: minimal_scenarios_part carries a real scenario
    (so the ref must resolve at all), and this document breaks it in a way only
    scenarios-0.1.json#/$defs/scenario knows about.
    """
    payload = minimal_scenarios_part()
    # `duplicate` without `duplicate_of`: a conditional that lives in the shared
    # $def and nowhere in this part's own file.
    payload["scenarios"][0]["status"] = "duplicate"
    path = tmp_path / "scenarios-part.json"
    write_json(path, payload)
    assert validate_artifact(path, "scenarios-part") != []


@pytest.mark.parametrize(
    "reason,expected_findings",
    [("out_of_scope", False), ("because_i_said_so", True)],
)
def test_a_score_part_rejected_reason_is_the_scenario_enum(tmp_path, reason, expected_findings):
    """score-part's rejected_reason $refs the sealed scenario's own enum.

    Both directions in one parametrization, because neither alone proves the ref
    *binds*: the valid case shows it resolves at all (an unresolvable ref raises
    out of iter_errors rather than returning findings), and the invalid case shows
    it constrains. Before this predicate existed nothing reached the enum at all
    -- every other score-part case here rules `active`, and minimal_score_part
    carries no rejected_reason -- so the five values could have been a copy that
    had silently fallen behind scenarios-0.1.json.

    The drift this closes is concrete: score-seal writes a ruling's
    rejected_reason straight onto the scenario it names, so a sixth value on one
    side alone would either make the ruling unrecordable in a part or make the
    assembled 02-scenarios.json schema-invalid -- a finding against an artifact
    code wrote, and no repair prompt fixes one of those.
    """
    payload = minimal_score_part()
    payload["rulings"] = [
        {"scenario_id": "sc-b01-002", "status": "rejected", "rejected_reason": reason}
    ]
    path = tmp_path / "score-part.json"
    write_json(path, payload)
    assert bool(validate_artifact(path, "score-part")) is expected_findings


def test_the_score_part_status_enum_is_a_subset_of_the_scenario_status_enum(tmp_path):
    """The one deliberate non-$ref in these part schemas, pinned as a subset.

    `status` is restated rather than shared *because* it subtracts `proposed`: a
    ruling exists to change a status, and `proposed` is what a scenario already
    carries out of its propose member. A $ref would widen the part back to the
    value it exists to exclude, so this asserts both halves -- proper subset, and
    `proposed` specifically absent -- rather than leaving the asymmetry with
    rejected_reason above readable only as an oversight.
    """
    scenario = json.loads(
        (schema_dir() / ARTIFACT_SCHEMAS["scenarios"]).read_text(encoding="utf-8")
    )
    part = json.loads((schema_dir() / ARTIFACT_SCHEMAS["score-part"]).read_text(encoding="utf-8"))
    sealed = set(scenario["$defs"]["scenario"]["properties"]["status"]["enum"])
    ruling = set(part["properties"]["rulings"]["items"]["properties"]["status"]["enum"])

    assert ruling < sealed, "score-part's status is no longer a proper subset of the scenario's"
    assert sealed - ruling == {"proposed"}, (
        "the subtraction has changed; `proposed` is the only value a ruling may not name"
    )


def test_a_score_part_verdict_is_the_coverage_enum(tmp_path):
    """score-part's verdict $refs coverage-0.1.json's *property*, not a $def.

    That is an unusual ref target -- a property subschema rather than a `$defs`
    entry -- so it gets its own guard: a ref that silently resolved to nothing
    would accept any string here, and the loop's whole control flow is this one
    value. `halted_forever` is not one of the four the coverage report defines.
    """
    payload = minimal_score_part()
    payload["verdict"] = "halted_forever"
    path = tmp_path / "score-part.json"
    write_json(path, payload)
    assert validate_artifact(path, "score-part") != []


def test_a_score_part_validates(tmp_path):
    path = tmp_path / "score-part.json"
    write_json(
        path,
        {
            "schema_version": "0.1",
            "round": 1,
            "rulings": [{"scenario_id": "sc-b01-001", "status": "active"}],
            "holes": [],
            "verdict": "converged",
        },
    )
    assert validate_artifact(path, "score-part") == []


def test_a_fold_ruling_must_name_its_survivor(tmp_path):
    path = tmp_path / "score-part.json"
    write_json(
        path,
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-b01-002", "status": "duplicate"}],
        },
    )
    assert validate_artifact(path, "score-part") != []


def test_a_rejection_ruling_must_name_a_reason(tmp_path):
    path = tmp_path / "score-part.json"
    write_json(
        path,
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-b01-002", "status": "rejected"}],
        },
    )
    assert validate_artifact(path, "score-part") != []


def test_a_services_part_validates_and_a_tool_with_no_schema_claim_does_not(tmp_path):
    """`schema_claim` is required, and the requirement is the whole reason the
    field exists: two claims can describe one tool, they can disagree about its
    input schema, and deterministic synthesis cannot pick a winner. Making it
    optional would put that choice back into code.
    """
    good = {
        "schema_version": "0.1",
        "services": [
            {
                "id": "svc-tickets",
                "statement": "The support ticket backend the one declared tool addresses",
                "grouping_evidence": ["shared_mcp_server_entry"],
                "tools": [
                    {
                        "name": "query_tickets",
                        "claims": ["clm-api-010"],
                        "schema_claim": "clm-api-010",
                    }
                ],
                "signals": [
                    {
                        "kind": "no_outward_evidence_found",
                        "locator": "api-json, notes-md, trace-json",
                    }
                ],
            }
        ],
        "inputs_seen": [
            {"artifact_id": "api-json", "own_kind_total": 1, "cited": 1, "dropped": 0},
            {"artifact_id": "notes-md", "own_kind_total": 0, "cited": 0, "dropped": 0},
            {"artifact_id": "trace-json", "own_kind_total": 0, "cited": 0, "dropped": 0},
        ],
    }
    path = tmp_path / "01-services.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert validate_artifact(path, "services-part") == []

    bad = json.loads(json.dumps(good))
    del bad["services"][0]["tools"][0]["schema_claim"]
    path.write_text(json.dumps(bad), encoding="utf-8")
    findings = validate_artifact(path, "services-part")
    assert findings, "a tool with no schema_claim must be rejected by layer 1"
    assert any("schema_claim" in f.message for f in findings)


def test_an_interface_document_validates_and_a_missing_request_body_does_not(tmp_path):
    """The carrier convention is pinned here rather than left to the code that
    writes it: one path per tool, `post`, an operationId matching the survival
    predicate, and a requestBody. `responses` is deliberately absent -- the
    harness's inline_schema_evidence feeds request bodies as entity evidence, so
    a request-only document is its intended input, not a degraded one.
    """
    good = {
        "openapi": "3.1.0",
        "info": {"title": "svc-tickets", "version": "0.1.0"},
        "paths": {
            "/query_tickets": {
                "post": {
                    "operationId": "query_tickets",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "required": ["action"]}
                            }
                        },
                    },
                }
            }
        },
        "x-rubrica": {
            "service_id": "svc-tickets",
            "tools": [
                {
                    "name": "query_tickets",
                    "claims": ["clm-api-010"],
                    "schema_claim": "clm-api-010",
                }
            ],
        },
    }
    path = tmp_path / "svc-tickets.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert validate_artifact(path, "interface") == []

    bad = json.loads(json.dumps(good))
    del bad["paths"]["/query_tickets"]["post"]["requestBody"]
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert validate_artifact(path, "interface"), "an operation with no requestBody must be rejected"

    worse = json.loads(json.dumps(good))
    worse["paths"]["/query_tickets"]["post"]["operationId"] = "_query_tickets"
    path.write_text(json.dumps(worse), encoding="utf-8")
    assert validate_artifact(path, "interface"), (
        "an operationId the harness would rewrite must be rejected by layer 1 too"
    )
