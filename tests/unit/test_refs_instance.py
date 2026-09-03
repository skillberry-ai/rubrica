import pytest

from rubrica.artifacts import write_json
from rubrica.paths import RunPaths
from rubrica.refs import UNSET, check_all, check_instances, check_verdicts, resolve_pointer
from tests.builders import (
    minimal_claims,
    minimal_expected,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)


def _run(tmp_path, *, seed=None, expected=None, verdict=None, world=None, sid="scn-001"):
    run = RunPaths(tmp_path)
    write_json(run.claims("aap2-api"), minimal_claims())
    write_json(run.world_model, world if world is not None else minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.seed(sid), seed if seed is not None else minimal_seed())
    write_json(run.expected(sid), expected if expected is not None else minimal_expected())
    if verdict is not None:
        write_json(run.verdict(sid), verdict)
    return run


# -- pointer resolver ---------------------------------------------------
def test_pointer_resolves_nested_objects_and_arrays():
    doc = {"collections": {"jobs": [{"job_id": 7}]}}
    assert resolve_pointer(doc, "/collections/jobs/0/job_id") == 7


def test_empty_pointer_is_the_whole_document():
    doc = {"a": 1}
    assert resolve_pointer(doc, "") == doc


def test_pointer_unescapes_rfc6901_sequences():
    assert resolve_pointer({"a/b": {"c~d": 1}}, "/a~1b/c~0d") == 1


@pytest.mark.parametrize(
    "pointer",
    ["/collections/absent", "/collections/jobs/9", "/collections/jobs/x", "/collections/jobs/0/x"],
)
def test_unresolvable_pointers_return_unset(pointer):
    doc = {"collections": {"jobs": [{"job_id": 7}]}}
    assert resolve_pointer(doc, pointer) is UNSET


def test_pointer_without_a_leading_slash_raises():
    with pytest.raises(ValueError):
        resolve_pointer({"a": 1}, "a")


# -- seed conformance ---------------------------------------------------
def test_a_conformant_instance_has_no_findings(tmp_path):
    assert check_instances(_run(tmp_path)) == []


def test_an_instance_for_no_such_scenario_is_reported(tmp_path):
    run = _run(tmp_path, sid="scn-ghost")
    assert any("scn-ghost" in f.message for f in check_instances(run))


def test_an_instance_for_a_scenario_marked_duplicate_is_reported(tmp_path):
    run = _run(tmp_path)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    payload["scenarios"][0]["duplicate_of"] = "scn-000"
    write_json(run.scenarios, payload)
    findings = check_instances(run)
    assert any("'duplicate'" in f.message and "judged" in f.message for f in findings)


def test_an_instance_for_a_rejected_scenario_is_tolerated(tmp_path):
    """The state the design spec's reject path prescribes, so not a finding.

    challenge marks a scenario `rejected` in 02-scenarios.json *after* it has
    been instantiated and judged, and the instance directory stays as the record
    the honest-hole report is built from. Reporting it made check-refs
    permanently dirty with no repair able to clear it. See refs.JUDGED_STATUSES.
    """
    run = _run(tmp_path)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "rejected"
    payload["scenarios"][0]["rejected_reason"] = "out_of_scope"
    write_json(run.scenarios, payload)
    assert check_instances(run) == []


def test_an_instance_for_a_still_proposed_scenario_is_reported(tmp_path):
    """score has not judged this scenario yet, so instantiate jumped the gun."""
    run = _run(tmp_path)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "proposed"
    write_json(run.scenarios, payload)
    findings = check_instances(run)
    assert any("'proposed'" in f.message and "judged" in f.message for f in findings)


@pytest.mark.parametrize("status", ["proposed", "duplicate"])
def test_an_unfit_status_yields_exactly_one_finding_per_instance(tmp_path, status):
    """`rejected` is deliberately absent: it is judged, so it is admitted."""
    run = _run(tmp_path)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = status
    payload["scenarios"][0]["duplicate_of"] = "scn-001"
    write_json(run.scenarios, payload)
    findings = [f for f in check_instances(run) if "judged" in f.message]
    assert len(findings) == 1
    assert findings[0].artifact == run.instance_dir("scn-001")


# -- fan-out completeness -----------------------------------------------
def test_an_active_scenario_with_no_instance_directory_is_reported(tmp_path):
    """The instantiate fan-out's missing member: a sibling landed, this one wrote nothing."""
    scenarios = minimal_scenarios()
    second = dict(scenarios["scenarios"][0])
    second["id"] = "scn-002"
    scenarios["scenarios"].append(second)
    run = _run(tmp_path)
    write_json(run.scenarios, scenarios)
    findings = check_instances(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.instances_dir
    assert "scn-002" in findings[0].message
    assert "has no instance directory on disk" in findings[0].message


def test_a_rejected_scenario_with_no_instance_directory_is_not_reported(tmp_path):
    """The exclusion `rejected` earns, and the regression this file already shipped once.

    A rejected scenario reaches that status by either of two prescribed routes:
    score can rule it `rejected` during the loop, in which case instantiate was
    never dispatched for it and it has no directory at all, or challenge can
    reject it after the fact, in which case it has one. Requiring a directory
    would make check-refs permanently dirty in the first state, with no repair
    able to clear it -- which is the failure JUDGED_STATUSES' own comment
    records having shipped.
    """
    scenarios = minimal_scenarios()
    second = dict(scenarios["scenarios"][0])
    second["id"] = "scn-002"
    second["status"] = "rejected"
    second["rejected_reason"] = "out_of_scope"
    scenarios["scenarios"].append(second)
    run = _run(tmp_path)
    write_json(run.scenarios, scenarios)
    assert not run.instance_dir("scn-002").exists()
    assert check_instances(run) == []


def test_an_active_scenario_is_not_reported_before_the_instances_directory_exists(tmp_path):
    """The guard: with no 04-instances/ at all the run has not reached instantiate, and
    reporting every active scenario there would spend the orchestrator's one repair attempt
    on a phantom."""
    run = RunPaths(tmp_path)
    write_json(run.claims("aap2-api"), minimal_claims())
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    assert not run.instances_dir.exists()
    assert check_instances(run) == []


# -- unsafe instance directory names ------------------------------------
def test_an_unsafe_instance_directory_name_is_a_finding_not_an_exception(tmp_path):
    """A stage that wrote a badly-named directory is repairable at exit 1.

    Before this was partitioned in paths.py, the later run.seed(sid) call
    raised UnsafeSegment from inside check_instances; cli.py catches ValueError
    and returned 2, telling the orchestrator the harness was misconfigured.
    """
    run = _run(tmp_path)
    (run.instances_dir / "scn 001").mkdir(parents=True, exist_ok=True)
    findings = check_instances(run)
    assert any("'scn 001'" in f.message and "scenario id" in f.message for f in findings)
    assert all(f.layer == "refs" for f in findings)


def test_an_unsafe_instance_directory_is_filed_against_the_instances_directory(tmp_path):
    run = _run(tmp_path)
    (run.instances_dir / "scn 001").mkdir(parents=True, exist_ok=True)
    unsafe = [f for f in check_instances(run) if "scn 001" in f.message]
    assert len(unsafe) == 1
    assert unsafe[0].artifact == run.instances_dir


def test_an_unsafe_directory_does_not_discard_the_other_instances_findings(tmp_path):
    """One bad name must not cost the operator every other finding.

    The repair prompt gets the whole list, so losing the valid instance's
    genuine defect to an unrelated bad directory name is the real damage.
    """
    expected = minimal_expected()
    expected["assertions"][0]["grounded_in"]["seed_pointer"] = "/collections/jobs/9/job_id"
    run = _run(tmp_path, expected=expected)
    (run.instances_dir / "scn 001").mkdir(parents=True, exist_ok=True)
    messages = [f.message for f in check_instances(run)]
    assert any("scn 001" in m for m in messages)
    assert any("does not resolve" in m for m in messages)


@pytest.mark.parametrize("name", ["scn 001", ".hidden", "scn:001", "-leading"])
def test_check_all_survives_an_unsafe_instance_directory(tmp_path, name):
    run = _run(tmp_path)
    (run.instances_dir / name).mkdir(parents=True, exist_ok=True)
    assert any(repr(name) in f.message for f in check_all(run))


def test_a_seed_collection_the_world_model_does_not_declare_is_reported(tmp_path):
    seed = minimal_seed(collections={"widgets": [{"x": 1}]})
    assert any("widgets" in f.message for f in check_instances(_run(tmp_path, seed=seed)))


def test_a_record_missing_a_declared_field_is_reported(tmp_path):
    seed = minimal_seed(collections={"jobs": [{"job_id": 1, "status": "failed"}]})
    findings = check_instances(_run(tmp_path, seed=seed))
    assert any("controller" in f.message for f in findings)


def test_a_record_with_an_undeclared_field_is_reported(tmp_path):
    seed = minimal_seed(
        collections={
            "jobs": [{"job_id": 1, "status": "failed", "controller": "prod0", "invented": 1}]
        }
    )
    findings = check_instances(_run(tmp_path, seed=seed))
    assert any("invented" in f.message for f in findings)


def test_a_field_of_the_wrong_declared_type_is_reported(tmp_path):
    seed = minimal_seed(
        collections={"jobs": [{"job_id": "one", "status": "failed", "controller": "prod0"}]}
    )
    findings = check_instances(_run(tmp_path, seed=seed))
    assert any("job_id" in f.message and "integer" in f.message for f in findings)


def test_a_boolean_does_not_satisfy_an_integer_field(tmp_path):
    seed = minimal_seed(
        collections={"jobs": [{"job_id": True, "status": "failed", "controller": "prod0"}]}
    )
    assert any("job_id" in f.message for f in check_instances(_run(tmp_path, seed=seed)))


def test_a_violated_machine_invariant_is_reported_at_the_invariant_layer(tmp_path):
    world = minimal_world_model()
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-unique-job",
            "statement": "job_id is unique",
            "machine": {"form": "unique", "collection": "jobs", "field": "job_id"},
        }
    ]
    seed = minimal_seed(
        collections={
            "jobs": [
                {"job_id": 1, "status": "failed", "controller": "prod0"},
                {"job_id": 1, "status": "failed", "controller": "prod0"},
            ]
        }
    )
    findings = check_instances(_run(tmp_path, seed=seed, world=world))
    assert any(f.layer == "invariant" and "duplicate" in f.message for f in findings)


# -- the reachability gate ----------------------------------------------
def test_an_unresolvable_seed_pointer_is_reported(tmp_path):
    expected = minimal_expected()
    expected["assertions"][0]["grounded_in"]["seed_pointer"] = "/collections/jobs/9/job_id"
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("does not resolve" in f.message for f in findings)


def test_an_asserted_value_absent_from_the_seed_is_reported(tmp_path):
    expected = minimal_expected()
    expected["assertions"][0]["value"] = "99999"
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("not present" in f.message for f in findings)


def test_value_equals_requires_an_exact_match(tmp_path):
    expected = minimal_expected()
    expected["assertions"][0] = {
        "kind": "value_equals",
        "target": "job_id",
        "value": "9042",
        "rationale": "prefix is not equality",
        "grounded_in": {"seed_pointer": "/collections/jobs/0/job_id"},
    }
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("does not equal" in f.message for f in findings)


def test_answer_excludes_holds_when_the_pointer_resolves_to_nothing(tmp_path):
    expected = minimal_expected()
    expected["assertions"] = [
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "root cause",
            "rationale": "the seed carries no error_msg, so no root cause is derivable",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/error_msg"},
        }
    ]
    assert check_instances(_run(tmp_path, expected=expected)) == []


def test_answer_excludes_is_reported_when_the_data_is_actually_there(tmp_path):
    world = minimal_world_model()
    world["entities"][0]["fields"].append({"name": "error_msg", "type": "string"})
    seed = minimal_seed(
        collections={
            "jobs": [
                {
                    "job_id": 90420,
                    "status": "failed",
                    "controller": "prod0",
                    "error_msg": "datastream file not found",
                }
            ]
        }
    )
    expected = minimal_expected()
    expected["assertions"] = [
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "root cause",
            "rationale": "claims the data is silent",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/error_msg"},
        }
    ]
    findings = check_instances(_run(tmp_path, seed=seed, expected=expected, world=world))
    assert any("resolves to a value" in f.message for f in findings)


def test_a_trajectory_assertion_naming_an_unknown_capability_is_reported(tmp_path):
    expected = minimal_expected()
    expected["assertions"][1]["capability_id"] = "cap-ghost"
    assert any("cap-ghost" in f.message for f in check_instances(_run(tmp_path, expected=expected)))


def test_a_trajectory_operation_naming_an_unknown_capability_is_reported(tmp_path):
    expected = minimal_expected()
    expected["trajectory"]["operations"][0]["capability_id"] = "cap-ghost"
    assert any("cap-ghost" in f.message for f in check_instances(_run(tmp_path, expected=expected)))


def test_an_expected_document_naming_a_different_scenario_is_reported(tmp_path):
    expected = minimal_expected(scenario_id="scn-002")
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("scn-002" in f.message for f in findings)


def test_an_expected_whose_discriminating_fact_differs_is_reported(tmp_path):
    """The field is the contract stage 4 builds to; a paraphrase hides a substitution."""
    expected = minimal_expected(discriminating_fact="some prod0 job failed at some point")
    messages = " || ".join(f.message for f in check_instances(_run(tmp_path, expected=expected)))
    assert "discriminating_fact" in messages
    assert "verbatim" in messages


def test_a_matching_discriminating_fact_is_clean(tmp_path):
    scenario_fact = minimal_scenarios()["scenarios"][0]["discriminating_fact"]
    expected = minimal_expected(discriminating_fact=scenario_fact)
    assert check_instances(_run(tmp_path, expected=expected)) == []


def test_a_trajectory_operation_outside_the_scenarios_capability_refs_is_reported(tmp_path):
    """Coverage credits the scenario for cells the instance never exercises."""
    world = minimal_world_model()
    world["capabilities"].append(
        {
            "id": "cap-get-log",
            "operation": "query_aap2.get_job_log",
            "params": [{"name": "job_id", "type": "integer", "required": True}],
            "outcome_classes": [
                {"id": "oc-success", "kind": "success", "description": "log returned"}
            ],
            "claims": ["clm-001"],
            "confidence": "high",
        }
    )
    world["denominator"] = {"version": 1, "capability_cells": 3, "goals": 1}
    expected = minimal_expected(
        discriminating_fact=minimal_scenarios()["scenarios"][0]["discriminating_fact"],
        trajectory={
            "match": "subset",
            "operations": [{"capability_id": "cap-get-log", "args": {"job_id": 90420}}],
        },
    )
    findings = check_instances(_run(tmp_path, world=world, expected=expected))
    assert [f.pointer for f in findings] == ["/trajectory/operations/0/capability_id"]
    assert "the scenario does not claim" in findings[0].message


def test_a_tool_called_assertion_outside_the_capability_refs_is_reported(tmp_path):
    expected = minimal_expected(
        discriminating_fact=minimal_scenarios()["scenarios"][0]["discriminating_fact"]
    )
    expected["assertions"][1]["capability_id"] = "cap-nowhere"
    messages = " || ".join(f.message for f in check_instances(_run(tmp_path, expected=expected)))
    assert "no such capability: cap-nowhere" in messages


def test_a_tool_called_assertion_naming_a_real_capability_outside_the_refs_is_reported(tmp_path):
    """The assertion-level mirror of the trajectory-operations scoping check.

    cap-nowhere (used above) is absent from the world model entirely, so it is
    caught by the sibling "no such capability" branch and never reaches the
    scoping check. This uses a capability that *is* in the world model but is
    not in the scenario's capability_refs, which is the only way to exercise
    the `kind == "tool_called" and capability_id not in scenario_caps` branch.
    """
    world = minimal_world_model()
    world["capabilities"].append(
        {
            "id": "cap-get-log",
            "operation": "query_aap2.get_job_log",
            "params": [{"name": "job_id", "type": "integer", "required": True}],
            "outcome_classes": [
                {"id": "oc-success", "kind": "success", "description": "log returned"}
            ],
            "claims": ["clm-001"],
            "confidence": "high",
        }
    )
    world["denominator"] = {"version": 1, "capability_cells": 3, "goals": 1}
    expected = minimal_expected(
        discriminating_fact=minimal_scenarios()["scenarios"][0]["discriminating_fact"]
    )
    expected["assertions"].append(
        {
            "kind": "tool_called",
            "target": "query_aap2.get_job_log",
            "value": "at least once",
            "rationale": "the scenario never claimed this capability",
            "capability_id": "cap-get-log",
        }
    )
    findings = check_instances(_run(tmp_path, world=world, expected=expected))
    assert [f.pointer for f in findings] == ["/assertions/2/capability_id"]
    assert "the scenario does not claim" in findings[0].message


def test_a_tool_not_called_assertion_may_name_a_capability_outside_the_refs(tmp_path):
    """A forbidden-call check about an unclaimed capability is the point of the kind."""
    world = minimal_world_model()
    world["capabilities"].append(
        {
            "id": "cap-delete-job",
            "operation": "query_aap2.delete_job",
            "params": [{"name": "job_id", "type": "integer", "required": True}],
            "outcome_classes": [{"id": "oc-success", "kind": "success", "description": "deleted"}],
            "claims": ["clm-001"],
            "confidence": "high",
        }
    )
    world["denominator"] = {"version": 1, "capability_cells": 3, "goals": 1}
    expected = minimal_expected(
        discriminating_fact=minimal_scenarios()["scenarios"][0]["discriminating_fact"]
    )
    expected["assertions"].append(
        {
            "kind": "tool_not_called",
            "target": "query_aap2.delete_job",
            "value": "never",
            "rationale": "a read-only triage task must not mutate state",
            "capability_id": "cap-delete-job",
        }
    )
    assert check_instances(_run(tmp_path, world=world, expected=expected)) == []


def test_a_pointer_cannot_reach_another_scenarios_seed(tmp_path):
    """Cross-contamination is impossible by construction, not by convention."""
    run = _run(tmp_path)
    write_json(run.seed("scn-002"), minimal_seed(collections={"jobs": []}))
    write_json(run.expected("scn-002"), minimal_expected(scenario_id="scn-002"))
    payload = minimal_scenarios()
    second = dict(payload["scenarios"][0])
    second["id"] = "scn-002"
    payload["scenarios"].append(second)
    write_json(run.scenarios, payload)
    findings = check_instances(run)
    assert any("scn-002" in str(f.artifact) and "does not resolve" in f.message for f in findings)


# -- verdicts -----------------------------------------------------------
def test_a_matching_verdict_has_no_findings(tmp_path):
    assert check_verdicts(_run(tmp_path, verdict=minimal_verdict())) == []


def test_an_instance_with_no_verdict_is_reported_once_challenge_has_run(tmp_path):
    """The property is "every instance has a verdict", not "verdicts exist".

    Two instances, one verdict: the un-challenged instance is named. A run
    with no verdicts directory at all is the normal post-instantiate state
    and is covered by test_check_all_is_clean_on_an_un_challenged_run.
    """
    run = _run(tmp_path, verdict=minimal_verdict())
    write_json(run.seed("scn-002"), minimal_seed())
    write_json(run.expected("scn-002"), minimal_expected(scenario_id="scn-002"))
    payload = minimal_scenarios()
    second = dict(payload["scenarios"][0])
    second["id"] = "scn-002"
    payload["scenarios"].append(second)
    write_json(run.scenarios, payload)

    findings = check_verdicts(run)
    assert [f.message for f in findings] == ["instance scn-002 has no verdict"]


def test_no_verdicts_directory_means_challenge_has_not_run_yet(tmp_path):
    """The pre-challenge state is not a finding; reporting it burns the
    orchestrator's one repair attempt on a phantom."""
    assert check_verdicts(_run(tmp_path)) == []


def test_a_verdict_naming_a_different_scenario_is_reported(tmp_path):
    run = _run(tmp_path, verdict=minimal_verdict(scenario_id="scn-999"))
    assert any("scn-999" in f.message for f in check_verdicts(run))


def test_an_accept_that_admits_the_test_is_not_derivable_is_reported(tmp_path):
    verdict = minimal_verdict(derivable_without_guessing=False)
    findings = check_verdicts(_run(tmp_path, verdict=verdict))
    assert any("derivable" in f.message for f in findings)


def test_an_accept_that_admits_the_test_is_ambiguous_is_reported(tmp_path):
    verdict = minimal_verdict(
        uniquely_determined=False,
        alternative_answers=[{"answer": "other", "world_consistent_reason": "also fits"}],
    )
    findings = check_verdicts(_run(tmp_path, verdict=verdict))
    assert any("uniquely determined" in f.message for f in findings)


def test_an_easier_than_claimed_test_must_carry_the_flag(tmp_path):
    verdict = minimal_verdict(minimum_tool_calls_found=1)
    findings = check_verdicts(_run(tmp_path, verdict=verdict))
    assert any("difficulty_overstated" in f.message for f in findings)


def test_an_easier_than_claimed_test_with_the_flag_is_accepted(tmp_path):
    verdict = minimal_verdict(minimum_tool_calls_found=1, flags=["difficulty_overstated"])
    assert check_verdicts(_run(tmp_path, verdict=verdict)) == []


# -- aggregation --------------------------------------------------------
def test_check_all_now_includes_instance_and_verdict_findings(tmp_path):
    """A genuinely warranted verdict finding reaches check_all's output.

    challenge has run — there is a verdicts directory holding one verdict —
    but it names the wrong scenario, so the pairing check fires.
    """
    run = _run(tmp_path, verdict=minimal_verdict(scenario_id="scn-999"))
    assert any("scn-999" in f.message for f in check_all(run))


def test_check_all_is_clean_on_an_un_challenged_run(tmp_path):
    """The state between instantiate and challenge warrants no finding."""
    run = _run(tmp_path)
    assert not run.verdicts_dir.exists()
    assert check_all(run) == []
