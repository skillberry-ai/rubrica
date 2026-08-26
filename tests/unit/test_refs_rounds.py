"""Layer 2 over the bounded propose/score loop's staged parts.

check_batches, check_scenario_parts and check_score_parts. The load-bearing one
is check_scenario_parts' own-batch clause: a member that proposed against a
sibling's hole writes a part that is schema-valid, hashes like any other, and is
byte-identical to one that stayed inside its batch, so no schema and no digest
can see it. Only the plan beside it says whose hole that was.

Every assertion here pins `Finding.pointer` or echoes a fixture value alongside
the brief's prose check, because a message substring alone is satisfiable by the
wrong guard in a multi-clause checker -- measured repeatedly on this branch.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import write_json
from rubrica.paths import RunPaths


def _run_with_world_for_refs(tmp_path):
    """A run holding the minimal world model test_rounds_cli._minimal writes.

    One capability cell (cap-0/cap-0-oc-0) and one goal (goal-0), so a hole ref
    naming anything else resolves to nothing and the resolution clauses have a
    negative to find.

    Two fields _minimal does not carry are added here: an `actors` list and the
    goal's `actor_id`. check_all reaches check_world_model, which indexes
    `goal["actor_id"]` bare -- layer 1 requires it, and layer 2's precondition is
    that layer 1 ran first -- so the _minimal world model makes check_all raise
    KeyError before it reaches any checker under test. The ids every assertion
    below resolves against are unchanged.
    """
    run = RunPaths(tmp_path)
    write_json(
        run.world_model,
        {
            "schema_version": "0.1",
            "denominator": {"capability_cells": 1, "goals": 1, "version": 1},
            "capabilities": [{"id": "cap-0", "outcome_classes": [{"id": "cap-0-oc-0"}]}],
            "actors": [{"id": "a"}],
            "goals": [{"id": "goal-0", "actor_id": "a", "expected_hop_depths": [1]}],
        },
    )
    return run


def _scenario(sid, *, goal="goal-0", cells=(("cap-0", "cap-0-oc-0"),), round_n=1):
    return {
        "id": sid,
        "round": round_n,
        "goal_id": goal,
        "actor_id": "a",
        "title": "t",
        "user_intent": "u",
        "hop_depth": 1,
        "capability_refs": [{"capability_id": cap, "outcome_class_id": oc} for cap, oc in cells],
        "discriminating_fact": "f",
        "status": "proposed",
        "provenance": {"round": round_n},
    }


# --------------------------------------------------------------------------
# check_batches
# --------------------------------------------------------------------------


def test_check_batches_is_silent_on_a_run_with_no_plan(tmp_path):
    # A run that has not reached propose has no plan to check, and reporting one
    # would spend the orchestrator's single repair attempt on a phantom.
    assert refs.check_batches(_run_with_world_for_refs(tmp_path)) == []


def test_check_batches_accepts_a_plan_that_recomputes(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {
                    "id": "b01",
                    "hole_refs": ["cell:cap-0/cap-0-oc-0", "goal:goal-0"],
                    "projected_bytes": 3200,
                }
            ],
        },
    )
    assert refs.check_batches(run) == []


def test_check_batches_recomputes_projected_bytes(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {"id": "b01", "hole_refs": ["cell:cap-0/cap-0-oc-0"], "projected_bytes": 99}
            ],
        },
    )
    findings = refs.check_batches(run)
    assert any("projected_bytes" in f.message for f in findings)
    # Pointer pin: "projected_bytes" also appears in the over-cap message, and a
    # prose-only assertion would pass on that one instead.
    assert [f.pointer for f in findings] == ["/batches/0/projected_bytes"]
    assert all(f.artifact == run.batches(1) for f in findings)


def test_check_batches_reports_a_batch_over_its_own_cap(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 1600,
            "bytes_per_scenario": 1600,
            "batches": [
                {
                    "id": "b01",
                    "hole_refs": ["cell:cap-0/cap-0-oc-0", "goal:goal-0"],
                    "projected_bytes": 3200,
                }
            ],
        },
    )
    findings = refs.check_batches(run)
    assert any("cap_bytes" in f.message for f in findings)
    # The projection itself recomputes (2 x 1600 = 3200), so the ONLY defect here
    # is the budget -- and the over-cap finding is anchored on hole_refs, the
    # field a repartition would change.
    assert [f.pointer for f in findings] == ["/batches/0/hole_refs"]


def test_check_batches_reports_a_hole_ref_the_world_model_does_not_declare(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["cell:cap-9/nope"], "projected_bytes": 1600}],
        },
    )
    findings = refs.check_batches(run)
    assert any("cap-9" in f.message for f in findings)
    assert [f.pointer for f in findings] == ["/batches/0/hole_refs/0"]


def test_check_batches_reports_a_goal_ref_the_world_model_does_not_declare(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-9"], "projected_bytes": 1600}],
        },
    )
    findings = refs.check_batches(run)
    assert any("goal-9" in f.message for f in findings)
    assert [f.pointer for f in findings] == ["/batches/0/hole_refs/0"]


def test_check_batches_reports_a_hole_assigned_to_two_batches(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
                {"id": "b02", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
            ],
        },
    )
    # A partition, not a covering: two members proposing against one hole is a
    # guaranteed duplicate that score then has to fold.
    findings = refs.check_batches(run)
    assert any("goal:goal-0" in f.message for f in findings)
    assert [f.pointer for f in findings] == ["/batches"]
    assert any("b01 and b02" in f.message for f in findings)


def test_check_batches_reports_a_hole_repeated_inside_one_batch(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {
                    "id": "b01",
                    "hole_refs": ["goal:goal-0", "goal:goal-0"],
                    "projected_bytes": 3200,
                }
            ],
        },
    )
    findings = refs.check_batches(run)
    assert [f.pointer for f in findings] == ["/batches"]
    assert "2 times in batch b01" in findings[0].message


def test_check_batches_reports_two_batches_sharing_one_id(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
                {"id": "b01", "hole_refs": ["cell:cap-0/cap-0-oc-0"], "projected_bytes": 1600},
            ],
        },
    )
    # A batch id is a part filename, so two batches sharing one share a part and
    # one member's output silently replaces the other's.
    findings = refs.check_batches(run)
    assert any("duplicate batch id 'b01'" in f.message for f in findings)


def test_check_batches_reports_a_plan_whose_round_field_disagrees_with_its_name(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(2),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
        },
    )
    findings = refs.check_batches(run)
    assert [f.pointer for f in findings] == ["/round"]
    assert [f.artifact for f in findings] == [run.batches(2)]


def test_check_batches_anchors_each_rounds_findings_on_that_rounds_own_plan(tmp_path):
    # R9: the plan is per-round precisely so round 1's parts are never checked
    # against round 2's assignment, and so a defect in round 2 never names round
    # 1's file. This repo has twice shipped a checker that named the wrong one.
    run = _run_with_world_for_refs(tmp_path)
    good = {
        "schema_version": "0.1",
        "round": 1,
        "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
    }
    write_json(run.batches(1), good)
    write_json(
        run.batches(2),
        {
            "schema_version": "0.1",
            "round": 2,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["cell:cap-9/nope"], "projected_bytes": 1600}],
        },
    )
    findings = refs.check_batches(run)
    assert [f.artifact for f in findings] == [run.batches(2)]


def test_check_batches_names_an_unreadable_plan_rather_than_returning_clean(tmp_path):
    # A checker that comes back empty because it could not read its input is the
    # module docstring's 01-claims incident wearing a checker's clothes.
    run = _run_with_world_for_refs(tmp_path)
    run.batches(1).parent.mkdir(parents=True, exist_ok=True)
    run.batches(1).write_text("{not json", encoding="utf-8")
    findings = refs.check_batches(run)
    assert [f.artifact for f in findings] == [run.batches(1)]
    assert "malformed JSON" in findings[0].message


# --------------------------------------------------------------------------
# check_scenario_parts
# --------------------------------------------------------------------------


def _two_batch_plan():
    return {
        "schema_version": "0.1",
        "round": 1,
        "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [
            {"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
            {"id": "b02", "hole_refs": ["cell:cap-0/cap-0-oc-0"], "projected_bytes": 1600},
        ],
    }


def test_check_scenario_parts_is_silent_before_the_fan_out_starts(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches(1), _two_batch_plan())
    assert refs.check_scenario_parts(run) == []


def test_check_scenario_parts_wants_a_file_per_batch(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches(1), _two_batch_plan())
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []},
    )
    # Reports every missing batch from the moment the directory exists, which is
    # why the orchestrator runs this only once the fan-out has finished -- the
    # property check_verdicts and check_contradiction_parts already have.
    findings = refs.check_scenario_parts(run)
    assert any("b02" in f.message for f in findings)
    assert [f.artifact for f in findings] == [run.scenario_round_dir(1)]


def test_check_scenario_parts_reports_a_part_for_a_batch_the_plan_never_declared(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
        },
    )
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []},
    )
    write_json(
        run.scenario_part(1, "b09"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b09", "scenarios": []},
    )
    findings = refs.check_scenario_parts(run)
    assert [f.artifact for f in findings] == [run.scenario_part(1, "b09")]
    assert "does not declare" in findings[0].message


def test_check_scenario_parts_reports_a_scenario_outside_its_own_batch(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches(1), _two_batch_plan())
    write_json(
        run.scenario_part(1, "b01"),
        {
            "schema_version": "0.1",
            "round": 1,
            "batch_id": "b01",
            # goal-0 is b01's, but this cell belongs to b02.
            "scenarios": [_scenario("sc-b01-001")],
        },
    )
    write_json(
        run.scenario_part(1, "b02"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b02", "scenarios": []},
    )
    findings = refs.check_scenario_parts(run)
    assert any("b02" in f.message and "sc-b01-001" in f.message for f in findings)
    assert [f.pointer for f in findings] == ["/scenarios/0/capability_refs/0"]
    assert [f.artifact for f in findings] == [run.scenario_part(1, "b01")]


def test_check_scenario_parts_accepts_a_scenario_inside_its_own_batch(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {
                    "id": "b01",
                    "hole_refs": ["cell:cap-0/cap-0-oc-0", "goal:goal-0"],
                    "projected_bytes": 3200,
                }
            ],
        },
    )
    write_json(
        run.scenario_part(1, "b01"),
        {
            "schema_version": "0.1",
            "round": 1,
            "batch_id": "b01",
            "scenarios": [_scenario("sc-b01-001")],
        },
    )
    assert refs.check_scenario_parts(run) == []


def test_check_scenario_parts_ignores_a_ref_no_batch_in_the_round_owns(tmp_path):
    # The clause bounds itself to refs this round actually partitioned: a cell
    # already covered is not in any batch, so referencing it is not a raid on a
    # sibling's holes.
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
        },
    )
    write_json(
        run.scenario_part(1, "b01"),
        {
            "schema_version": "0.1",
            "round": 1,
            "batch_id": "b01",
            "scenarios": [_scenario("sc-b01-001")],
        },
    )
    assert refs.check_scenario_parts(run) == []


def test_check_scenario_parts_reports_a_goal_belonging_to_another_batch(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches(1), _two_batch_plan())
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []},
    )
    write_json(
        run.scenario_part(1, "b02"),
        {
            "schema_version": "0.1",
            "round": 1,
            "batch_id": "b02",
            # b02 owns the cell; goal-0 is b01's.
            "scenarios": [_scenario("sc-b02-001")],
        },
    )
    findings = refs.check_scenario_parts(run)
    assert [f.pointer for f in findings] == ["/scenarios/0/goal_id"]
    assert "b01" in findings[0].message and "sc-b02-001" in findings[0].message


def test_check_scenario_parts_reports_a_mismatched_batch_id_header(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
        },
    )
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b99", "scenarios": []},
    )
    findings = refs.check_scenario_parts(run)
    assert any("b99" in f.message for f in findings)
    assert [f.pointer for f in findings] == ["/batch_id"]


def test_check_scenario_parts_reports_a_part_whose_round_field_disagrees(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
        },
    )
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 2, "batch_id": "b01", "scenarios": []},
    )
    findings = refs.check_scenario_parts(run)
    assert [f.pointer for f in findings] == ["/round"]


def test_check_scenario_parts_reports_an_unsafe_part_name(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
        },
    )
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []},
    )
    (run.scenario_round_dir(1) / ".hidden.json").write_text("{}", encoding="utf-8")
    findings = refs.check_scenario_parts(run)
    assert any(".hidden" in f.message for f in findings)
    assert all(f.artifact == run.scenario_round_dir(1) for f in findings)


def test_check_scenario_parts_names_the_missing_plan_rather_than_skipping_the_round(tmp_path):
    # A round with parts and no plan cannot be checked at all, and a silent skip
    # would make the own-batch clause -- the only enforceable one -- vanish.
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []},
    )
    findings = refs.check_scenario_parts(run)
    assert [f.artifact for f in findings] == [run.batches(1)]
    assert "missing artifact" in findings[0].message


def test_check_scenario_parts_checks_each_round_against_its_own_plan(tmp_path):
    # R9 in executable form. Round 2 partitions the same hole differently; with a
    # single shared plan round 1's correct part would be reported against round
    # 2's assignment.
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [
                {
                    "id": "b01",
                    "hole_refs": ["cell:cap-0/cap-0-oc-0", "goal:goal-0"],
                    "projected_bytes": 3200,
                }
            ],
        },
    )
    write_json(
        run.scenario_part(1, "b01"),
        {
            "schema_version": "0.1",
            "round": 1,
            "batch_id": "b01",
            "scenarios": [_scenario("sc-b01-001")],
        },
    )
    write_json(run.batches(2), {**_two_batch_plan(), "round": 2})
    write_json(
        run.scenario_part(2, "b01"),
        {"schema_version": "0.1", "round": 2, "batch_id": "b01", "scenarios": []},
    )
    write_json(
        run.scenario_part(2, "b02"),
        {"schema_version": "0.1", "round": 2, "batch_id": "b02", "scenarios": []},
    )
    assert refs.check_scenario_parts(run) == []


def test_check_scenario_parts_names_an_unreadable_part(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
        },
    )
    run.scenario_round_dir(1).mkdir(parents=True, exist_ok=True)
    run.scenario_part(1, "b01").write_text("{not json", encoding="utf-8")
    findings = refs.check_scenario_parts(run)
    assert [f.artifact for f in findings] == [run.scenario_part(1, "b01")]
    assert "malformed JSON" in findings[0].message


# --------------------------------------------------------------------------
# check_score_parts
# --------------------------------------------------------------------------


def test_check_score_parts_is_silent_with_no_score_part(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1, "scenarios": []})
    assert refs.check_score_parts(run) == []


def test_check_score_parts_accepts_a_ruling_that_resolves(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": 1,
            "scenarios": [{**_scenario("sc-001"), "status": "active"}],
        },
    )
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-001", "status": "active"}],
        },
    )
    assert refs.check_score_parts(run) == []


def test_check_score_parts_reports_a_ruling_for_an_unknown_scenario(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1, "scenarios": []})
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-ghost", "status": "active"}],
        },
    )
    findings = refs.check_score_parts(run)
    assert any("sc-ghost" in f.message for f in findings)
    assert [f.pointer for f in findings] == ["/rulings/0/scenario_id"]
    assert [f.artifact for f in findings] == [run.score_part(1)]


def test_check_score_parts_reports_a_fold_onto_a_scenario_that_is_itself_a_duplicate(tmp_path):
    # A fold chain leaves no shipped test for either cell, and check_scenarios'
    # guard on the sealed document only asks whether duplicate_of RESOLVES -- this
    # one names the part a re-dispatch can actually repair.
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": 1,
            "scenarios": [
                {**_scenario("sc-001"), "status": "duplicate", "duplicate_of": "sc-002"},
            ],
        },
    )
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-001", "status": "duplicate", "duplicate_of": "sc-001"}],
        },
    )
    assert refs.check_score_parts(run) != []
    findings = refs.check_score_parts(run)
    # The self-fold short-circuits, so exactly one clause fires and a test can
    # tell which: a second finding on the same pointer would make that impossible.
    assert [f.pointer for f in findings] == ["/rulings/0/duplicate_of"]
    assert "onto itself" in findings[0].message


def test_check_score_parts_reports_a_fold_onto_a_rejected_scenario(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": 1,
            "scenarios": [
                {**_scenario("sc-001"), "status": "duplicate", "duplicate_of": "sc-002"},
                {**_scenario("sc-002"), "status": "rejected", "rejected_reason": "ambiguous"},
            ],
        },
    )
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-001", "status": "duplicate", "duplicate_of": "sc-002"}],
        },
    )
    findings = refs.check_score_parts(run)
    assert [f.pointer for f in findings] == ["/rulings/0/duplicate_of"]
    assert "itself rejected" in findings[0].message


def test_check_score_parts_reports_a_fold_onto_a_scenario_the_seal_does_not_carry(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": 1,
            "scenarios": [{**_scenario("sc-001"), "status": "duplicate", "duplicate_of": "sc-002"}],
        },
    )
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-001", "status": "duplicate", "duplicate_of": "sc-002"}],
        },
    )
    findings = refs.check_score_parts(run)
    assert [f.pointer for f in findings] == ["/rulings/0/duplicate_of"]
    assert "sc-002" in findings[0].message


def test_check_score_parts_reports_a_part_whose_round_field_disagrees(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1, "scenarios": []})
    write_json(
        run.score_part(2),
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [],
        },
    )
    findings = refs.check_score_parts(run)
    assert [f.pointer for f in findings] == ["/round"]
    assert [f.artifact for f in findings] == [run.score_part(2)]


def test_check_score_parts_names_an_unreadable_part(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1, "scenarios": []})
    run.score_parts_dir.mkdir(parents=True, exist_ok=True)
    run.score_part(1).write_text("{not json", encoding="utf-8")
    findings = refs.check_score_parts(run)
    assert [f.artifact for f in findings] == [run.score_part(1)]
    assert "malformed JSON" in findings[0].message


# --------------------------------------------------------------------------
# check_all wiring
# --------------------------------------------------------------------------


def test_check_all_runs_the_new_checkers(tmp_path):
    # check_all runs every checker the run has inputs for -- there is no such
    # thing as a stage-scoped check-refs -- so a checker not wired in is a checker
    # that never runs on a real run.
    run = _run_with_world_for_refs(tmp_path)
    write_json(
        run.batches(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "cap_bytes": 28000,
            "bytes_per_scenario": 1600,
            "batches": [{"id": "b01", "hole_refs": ["cell:cap-9/nope"], "projected_bytes": 1600}],
        },
    )
    assert any("cap-9" in f.message for f in refs.check_all(run))


def test_check_all_runs_check_scenario_parts(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches(1), _two_batch_plan())
    write_json(
        run.scenario_part(1, "b01"),
        {
            "schema_version": "0.1",
            "round": 1,
            "batch_id": "b01",
            "scenarios": [_scenario("sc-b01-001")],
        },
    )
    write_json(
        run.scenario_part(1, "b02"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b02", "scenarios": []},
    )
    assert any(
        f.artifact == run.scenario_part(1, "b01") and "b02" in f.message
        for f in refs.check_all(run)
    )


def test_check_all_runs_check_score_parts(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1, "scenarios": []})
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "holes": [],
            "verdict": "converged",
            "rulings": [{"scenario_id": "sc-ghost", "status": "active"}],
        },
    )
    assert any(
        f.artifact == run.score_part(1) and "sc-ghost" in f.message for f in refs.check_all(run)
    )
