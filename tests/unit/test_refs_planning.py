import pytest

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import (
    cell_ref,
    check_all,
    check_coverage,
    check_scenarios,
    check_world_model,
    goal_ref,
    parse_hole_ref,
)
from tests.builders import minimal_claims, minimal_coverage, minimal_scenarios, minimal_world_model


def _run(tmp_path, *, claims=True, world=True, scenarios=False, coverage=False):
    run = RunPaths(tmp_path)
    if claims:
        write_json(run.claims("aap2-api"), minimal_claims())
    if world:
        write_json(run.world_model, minimal_world_model())
    if scenarios:
        write_json(run.scenarios, minimal_scenarios())
    if coverage:
        write_json(run.coverage_latest, minimal_coverage())
    return run


def _scored_run(tmp_path, *, coverage):
    """A run holding a world model, scenarios, and the given coverage payload."""
    run = RunPaths(tmp_path)
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.coverage_latest, coverage)
    return run


# -- hole refs ----------------------------------------------------------
def test_cell_and_goal_refs_round_trip():
    assert parse_hole_ref(cell_ref("cap-a", "oc-b")) == ("cell", ("cap-a", "oc-b"))
    assert parse_hole_ref(goal_ref("goal-x")) == ("goal", ("goal-x",))


def test_cell_ref_has_the_documented_string_form():
    assert cell_ref("cap-a", "oc-b") == "cell:cap-a/oc-b"
    assert goal_ref("goal-x") == "goal:goal-x"


@pytest.mark.parametrize("bad", ["cap-a", "cell:cap-a", "goal:", "cell:a/b/c", ""])
def test_malformed_hole_refs_raise(bad):
    with pytest.raises(ValueError):
        parse_hole_ref(bad)


# -- world model --------------------------------------------------------
def test_a_consistent_world_model_has_no_findings(tmp_path):
    assert check_world_model(_run(tmp_path)) == []


def test_a_claim_reference_with_no_matching_claim_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["capabilities"][0]["claims"] = ["clm-999"]
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert any("clm-999" in f.message for f in findings)
    assert all(f.layer == "refs" for f in findings)


def test_a_goal_pointing_at_an_unknown_actor_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["goals"][0]["actor_id"] = "act-ghost"
    write_json(run.world_model, world)
    assert any("act-ghost" in f.message for f in check_world_model(run))


def test_a_relation_pointing_at_an_unknown_entity_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["entities"][0]["relations"] = [
        {"name": "events", "target_entity_id": "ent-ghost", "cardinality": "many"}
    ]
    write_json(run.world_model, world)
    assert any("ent-ghost" in f.message for f in check_world_model(run))


def test_a_contradiction_citing_an_unknown_claim_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["contradictions"] = [
        {
            "id": "con-1",
            "claim_a": "clm-001",
            "claim_b": "clm-ghost",
            "nature": "return shape",
            "resolution": "unresolved",
            "rationale": "cannot tell which source is current",
        }
    ]
    write_json(run.world_model, world)
    assert any("clm-ghost" in f.message for f in check_world_model(run))


def test_an_invariant_over_an_undeclared_collection_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "s",
            "machine": {"form": "unique", "collection": "widgets", "field": "x"},
        }
    ]
    write_json(run.world_model, world)
    assert any("widgets" in f.message for f in check_world_model(run))


def test_a_miscounted_capability_cell_denominator_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["capability_cells"] = 5
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert any("capability_cells" in f.message and "5" in f.message for f in findings)


def test_a_miscounted_goal_denominator_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["goals"] = 4
    write_json(run.world_model, world)
    assert any("goals" in f.message for f in check_world_model(run))


def test_duplicate_capability_ids_are_reported(tmp_path):
    """capability_cells stays 2: _cells is a set of (capability_id,
    outcome_class_id) pairs, so duplicating a capability wholesale adds no new
    cell. Bumping the denominator to 4 would provoke a second, unrelated
    finding rather than silence one, so this asserts on the exact list."""
    run = _run(tmp_path)
    world = minimal_world_model()
    world["capabilities"].append(dict(world["capabilities"][0]))
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert [(f.pointer, f.message) for f in findings] == [
        ("/capabilities", "duplicate id 'cap-find-jobs'")
    ]


# -- scenarios ----------------------------------------------------------
def test_consistent_scenarios_have_no_findings(tmp_path):
    assert check_scenarios(_run(tmp_path, scenarios=True)) == []


def test_a_capability_ref_to_an_unknown_capability_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-ghost", "outcome_class_id": "oc-success"}
    ]
    write_json(run.scenarios, payload)
    assert any("cap-ghost" in f.message for f in check_scenarios(run))


def test_a_capability_ref_to_a_wrong_outcome_class_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-ghost"}
    ]
    write_json(run.scenarios, payload)
    assert any("oc-ghost" in f.message for f in check_scenarios(run))


def test_a_scenario_with_an_unknown_goal_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["goal_id"] = "goal-ghost"
    write_json(run.scenarios, payload)
    assert any("goal-ghost" in f.message for f in check_scenarios(run))


def test_a_duplicate_pointing_at_no_such_scenario_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    payload["scenarios"][0]["duplicate_of"] = "scn-ghost"
    write_json(run.scenarios, payload)
    assert any("scn-ghost" in f.message for f in check_scenarios(run))


def test_a_hole_ref_naming_no_real_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = ["cell:cap-ghost/oc-success"]
    write_json(run.scenarios, payload)
    assert any("cap-ghost" in f.message for f in check_scenarios(run))


def test_a_stale_denominator_version_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    write_json(run.scenarios, minimal_scenarios(denominator_version=2))
    assert any("denominator_version" in f.message for f in check_scenarios(run))


def test_duplicate_scenario_ids_are_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"].append(dict(payload["scenarios"][0]))
    write_json(run.scenarios, payload)
    assert any("duplicate" in f.message for f in check_scenarios(run))


# -- coverage -----------------------------------------------------------
def test_consistent_coverage_has_no_findings(tmp_path):
    assert check_coverage(_run(tmp_path, scenarios=True, coverage=True)) == []


def test_a_coverage_matrix_missing_a_real_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"] = payload["capability_matrix"]["cells"][:1]
    payload["capability_matrix"]["total"] = 1
    payload["capability_matrix"]["pct"] = 1.0
    write_json(run.coverage_latest, payload)
    assert any("oc-empty" in f.message for f in check_coverage(run))


def test_a_coverage_matrix_inventing_a_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"].append(
        {
            "capability_id": "cap-ghost",
            "outcome_class_id": "oc-success",
            "scenario_ids": [],
            "covered": False,
        }
    )
    # Both total and pct must follow the added row, or the arithmetic check
    # fires too and the test would pass on the wrong finding.
    payload["capability_matrix"]["total"] = 3
    payload["capability_matrix"]["pct"] = 1 / 3
    write_json(run.coverage_latest, payload)
    findings = check_coverage(run)
    # The invented cell isn't a real cell, so no hole can name it either -- it
    # is also uncovered and unjustified, which is a second, legitimate finding
    # now that holes are related to the matrices.
    assert [f.message for f in findings] == [
        "matrix invents cell cell:cap-ghost/oc-success",
        "cell:cap-ghost/oc-success is uncovered but no hole justifies it",
    ]


def test_inconsistent_covered_arithmetic_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["covered"] = 2
    write_json(run.coverage_latest, payload)
    assert any("covered" in f.message for f in check_coverage(run))


def test_a_pct_that_disagrees_with_the_counts_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["pct"] = 0.9
    write_json(run.coverage_latest, payload)
    assert any("pct" in f.message for f in check_coverage(run))


def test_a_cell_citing_an_unknown_scenario_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"][0]["scenario_ids"] = ["scn-ghost"]
    write_json(run.coverage_latest, payload)
    assert any("scn-ghost" in f.message for f in check_coverage(run))


def test_a_cell_marked_covered_with_no_scenarios_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"][1]["covered"] = True
    payload["capability_matrix"]["covered"] = 2
    payload["capability_matrix"]["pct"] = 1.0
    write_json(run.coverage_latest, payload)
    assert any("no scenarios" in f.message for f in check_coverage(run))


def test_a_blocked_by_gap_hole_naming_no_real_gap_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["holes"][0]["reason"] = "blocked_by_gap"
    payload["holes"][0]["gap_id"] = "gap-ghost"
    write_json(run.coverage_latest, payload)
    assert any("gap-ghost" in f.message for f in check_coverage(run))


def test_an_uncovered_cell_with_no_hole_is_reported(tmp_path):
    """Without this, a report can claim zero holes while cells sit uncovered."""
    coverage = minimal_coverage(holes=[])
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "cell:cap-find-jobs/oc-empty is uncovered but no hole justifies it" in messages
    assert "goal:goal-triage is uncovered but no hole justifies it" in messages


def test_a_hole_naming_a_covered_row_is_reported(tmp_path):
    coverage = minimal_coverage()
    coverage["holes"].append(
        {
            "ref": "cell:cap-find-jobs/oc-success",
            "reason": "not_yet_attempted",
            "justification": "claims a hole in a cell the same report marks covered",
        }
    )
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "cell:cap-find-jobs/oc-success" in messages
    assert "the matrix marks covered" in messages


def test_hop_depths_expected_must_match_the_world_model(tmp_path):
    coverage = minimal_coverage()
    coverage["goal_matrix"]["rows"][0]["hop_depths_expected"] = [1]
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if "hop_depths_expected" in f.pointer]
    assert len(findings) == 1
    assert "[1, 2]" in findings[0].message


def test_hop_depths_present_must_be_derived_from_the_listed_scenarios(tmp_path):
    coverage = minimal_coverage()
    coverage["goal_matrix"]["rows"][0]["hop_depths_present"] = [1, 2]
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if "hop_depths_present" in f.pointer]
    assert len(findings) == 1
    assert "scn-001" in findings[0].message or "[2]" in findings[0].message


def test_a_goal_row_marked_covered_without_scenarios_is_reported(tmp_path):
    coverage = minimal_coverage()
    row = coverage["goal_matrix"]["rows"][0]
    row["scenario_ids"] = []
    row["hop_depths_present"] = []
    row["covered"] = True
    coverage["goal_matrix"]["covered"] = 1
    coverage["goal_matrix"]["pct"] = 1.0
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if f.pointer.endswith("/covered")]
    assert len(findings) == 1
    assert "lists no scenarios" in findings[0].message


def test_a_goal_row_covered_at_only_some_expected_hop_depths_is_not_covered(tmp_path):
    """The builder payload is exactly this case: expected [1, 2], present [2]."""
    coverage = minimal_coverage()
    row = coverage["goal_matrix"]["rows"][0]
    row["covered"] = True
    coverage["goal_matrix"]["covered"] = 1
    coverage["goal_matrix"]["pct"] = 1.0
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "hop depth" in messages


def test_the_builder_coverage_payload_is_clean(tmp_path):
    """Guards the builders: every later state test depends on this staying true."""
    run = _scored_run(tmp_path, coverage=minimal_coverage())
    assert check_coverage(run) == []


# -- check_all ----------------------------------------------------------
def test_check_all_tolerates_a_run_that_has_only_reached_reconcile(tmp_path):
    assert check_all(_run(tmp_path)) == []


def test_check_all_tolerates_an_empty_run_directory(tmp_path):
    assert check_all(RunPaths(tmp_path)) == []


def test_check_all_aggregates_findings_from_every_present_artifact(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    world = minimal_world_model()
    world["denominator"]["goals"] = 9
    write_json(run.world_model, world)
    payload = minimal_scenarios()
    payload["scenarios"][0]["goal_id"] = "goal-ghost"
    write_json(run.scenarios, payload)
    messages = " ".join(f.message for f in check_all(run))
    assert "goals" in messages
    assert "goal-ghost" in messages
