"""The propose/score loop's code steps.

Every number asserted here that is not obviously arithmetic came off
runs/run-20260825-094033 on 2026-08-26: 148 capability cells plus 22 goals,
86 closable holes of 151, mean 1,162 bytes per scenario and max 1,579.
"""

from __future__ import annotations

import json
import re

import pytest

from rubrica import rounds
from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths
from rubrica.validate import validate_artifact


def _world(caps: int = 2, ocs: int = 2, goals: int = 1) -> dict:
    return {
        "schema_version": "0.1",
        "denominator": {"capability_cells": caps * ocs, "goals": goals, "version": 1},
        "capabilities": [
            {
                "id": f"cap-{c}",
                "outcome_classes": [{"id": f"cap-{c}-oc-{o}"} for o in range(ocs)],
            }
            for c in range(caps)
        ],
        "goals": [{"id": f"goal-{g}", "expected_hop_depths": [1]} for g in range(goals)],
    }


def _run_with_world(tmp_path, world: dict) -> RunPaths:
    run = RunPaths(tmp_path)
    write_json(run.world_model, world)
    return run


def test_round_one_treats_every_cell_and_goal_as_open(tmp_path):
    # No coverage report exists in round 1, which is the normal shape rather
    # than a missing file: rb-propose's own Inputs section says to treat every
    # cell and goal as open, and the partition has to build the same worklist.
    run = _run_with_world(tmp_path, _world(caps=2, ocs=2, goals=1))
    assert rounds.closable_holes(run) == [
        "cell:cap-0/cap-0-oc-0",
        "cell:cap-0/cap-0-oc-1",
        "cell:cap-1/cap-1-oc-0",
        "cell:cap-1/cap-1-oc-1",
        "goal:goal-0",
    ]


def test_later_rounds_take_only_the_not_yet_attempted_holes(tmp_path):
    # The other three reasons are not closable by proposing, whatever the
    # scenario: unreachable and out_of_scope are outside the suite's surface,
    # and blocked_by_gap needs an earlier stage's gap resolved first.
    run = _run_with_world(tmp_path, _world())
    write_json(
        run.coverage_latest,
        {
            "schema_version": "0.1",
            "round": 1,
            "denominator_version": 1,
            "capability_matrix": {"cells": [], "covered": 0, "total": 0, "pct": 0.0},
            "goal_matrix": {"rows": [], "covered": 0, "total": 0, "pct": 0.0},
            "progress": {"new_cells_this_round": 0, "rounds_without_progress": 0},
            "verdict": "continue",
            "holes": [
                {
                    "ref": "cell:cap-0/cap-0-oc-0",
                    "reason": "not_yet_attempted",
                    "justification": "x",
                },
                {"ref": "goal:goal-0", "reason": "not_yet_attempted", "justification": "x"},
                {"ref": "cell:cap-1/cap-1-oc-0", "reason": "unreachable", "justification": "x"},
                {"ref": "cell:cap-1/cap-1-oc-1", "reason": "out_of_scope", "justification": "x"},
                {
                    "ref": "cell:cap-0/cap-0-oc-1",
                    "reason": "blocked_by_gap",
                    "gap_id": "gap-1",
                    "justification": "x",
                },
            ],
        },
    )
    assert rounds.closable_holes(run) == ["cell:cap-0/cap-0-oc-0", "goal:goal-0"]


def test_the_scenario_byte_estimate_falls_back_before_any_round_lands(tmp_path):
    run = _run_with_world(tmp_path, _world())
    assert rounds.bytes_per_scenario(run) == rounds.DEFAULT_BYTES_PER_SCENARIO


def test_the_scenario_byte_estimate_self_calibrates_from_the_sealed_file(tmp_path):
    run = _run_with_world(tmp_path, _world())
    small = {"id": "sc-b01-001", "round": 1, "title": "a"}
    write_json(
        run.scenarios,
        {"schema_version": "0.1", "denominator_version": 1, "scenarios": [small, small]},
    )
    expected = len(json.dumps(small, sort_keys=True))
    assert rounds.bytes_per_scenario(run) == expected


def test_an_empty_sealed_file_falls_back_rather_than_dividing_by_zero(tmp_path):
    run = _run_with_world(tmp_path, _world())
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1, "scenarios": []})
    assert rounds.bytes_per_scenario(run) == rounds.DEFAULT_BYTES_PER_SCENARIO


def test_the_partition_keeps_every_batch_inside_the_budget():
    refs = [f"cell:cap-{i}/oc" for i in range(86)]
    batches = rounds.partition(refs, cap_bytes=28000, per_scenario=1600)
    # 28000 // 1600 == 17 holes per batch, so 86 holes become 6 batches -- the
    # measured case from run-20260825-094033.
    assert len(batches) == 6
    assert [len(b) for b in batches] == [17, 17, 17, 17, 17, 1]
    for batch in batches:
        assert len(batch) * 1600 <= 28000
    # No hole is dropped and none is duplicated: the partition is a partition.
    assert [ref for batch in batches for ref in batch] == refs


def test_the_partition_of_nothing_is_nothing():
    assert rounds.partition([], cap_bytes=28000, per_scenario=1600) == []


def test_a_budget_smaller_than_one_scenario_is_a_usage_error():
    # max(1, cap // per) would silently produce a batch that cannot fit, which
    # is the silent cap this whole change exists to remove. Refuse instead.
    with pytest.raises(UsageError):
        rounds.partition(["cell:a/b"], cap_bytes=100, per_scenario=1600)


def test_write_batches_writes_a_schema_valid_document(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=2, ocs=2, goals=1))
    path = rounds.write_batches(run, round_n=1)
    assert path == run.batches(1)
    # Actually validate, rather than only asserting fields: the kind is
    # registered in Task 2, and a test named "schema valid" that never reaches
    # the validator is the shape of an assertion nobody has watched fail.
    assert validate_artifact(path, "batches") == []
    doc = read_json(path)
    assert doc["round"] == 1
    assert doc["cap_bytes"] == rounds.DEFAULT_SCENARIO_PART_BYTES
    assert doc["bytes_per_scenario"] == rounds.DEFAULT_BYTES_PER_SCENARIO
    assert [b["id"] for b in doc["batches"]] == ["b01"]
    assert doc["batches"][0]["hole_refs"] == rounds.closable_holes(run)
    assert doc["batches"][0]["projected_bytes"] == 5 * rounds.DEFAULT_BYTES_PER_SCENARIO


def test_write_batches_honours_the_manifest_budget(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=4, ocs=4, goals=4))
    write_json(
        run.manifest,
        {"limits": {"max_rounds": 2, "max_scenarios": 128, "max_scenario_part_bytes": 3200}},
    )
    doc = read_json(rounds.write_batches(run, round_n=1))
    assert doc["cap_bytes"] == 3200
    # 3200 // 1600 == 2 holes per batch over 20 holes -> 10 batches, zero-padded
    # ids so b10 sorts after b09 as a path segment and in any listing.
    assert [b["id"] for b in doc["batches"]] == [f"b{i:02d}" for i in range(1, 11)]


def test_write_batches_writes_nothing_when_no_hole_is_closable(tmp_path):
    # Distinct from an empty batches array, which the schema refuses: no
    # document at all is how the orchestrator learns there is no round to run.
    run = _run_with_world(
        tmp_path,
        {
            "schema_version": "0.1",
            "capabilities": [],
            "goals": [],
            "denominator": {"capability_cells": 0, "goals": 0, "version": 1},
        },
    )
    assert rounds.write_batches(run, round_n=1) is None
    assert not run.batches(1).exists()


def test_write_batches_reports_an_unreadable_world_model(tmp_path):
    run = RunPaths(tmp_path)
    # ArtifactError, not a bare Exception: a bare Exception also passes when the
    # call under test has a typo, so it is an assertion that cannot fail.
    with pytest.raises(ArtifactError):
        rounds.write_batches(run, round_n=1)


def test_the_default_member_budget_leaves_half_the_output_ceiling_free():
    # Half the ceiling, not all of it: OUTPUT_TOKEN_CEILING counts thinking
    # tokens as well, and a member also emits its report back to the
    # orchestrator, neither of which a byte budget bounds. Relational rather than
    # a value pin, so retuning the budget inside the safe band survives this
    # while a raise past the band does not -- measured both ways, red at 120,000
    # bytes and green at 28,000. The conversion is load-bearing: the ceiling is
    # in tokens and the budget is in bytes, so comparing them without
    # BYTES_PER_TOKEN is a unit error rather than a guard.
    assert (
        rounds.DEFAULT_SCENARIO_PART_BYTES / rounds.BYTES_PER_TOKEN
        <= rounds.OUTPUT_TOKEN_CEILING * 0.5
    )


# Pinned on the field name AND the value echo, not merely on UsageError, and both
# halves are load-bearing. Why a pin at all: 0, -1 and True are each below
# DEFAULT_BYTES_PER_SCENARIO, so partition refuses them on its own, and a bare
# `pytest.raises(UsageError)` stayed green with _cap_bytes' whole range-and-bool
# half deleted -- passing on a refusal raised by different code about a different
# thing.
#
# Why not the field name alone: partition's refusal now NAMES the cap source, and
# for a manifest-set budget that source string is that same field. Measured -- the
# field name alone matches both refusals, so it stopped discriminating the moment
# the source was added to partition's message. `found {cap!r}` is unique to
# _cap_bytes, so the value echo is what separates them.
#
# Why it stops there: the pin once ran through "must be an integer", which is
# prose rather than identity, and measured, it broke on a meaning-preserving
# reword to "must be a positive integer". `.*` spans the prose instead of pinning
# it, so this survives that reword and still goes red when either guard half is
# deleted. A pin that breaks on an innocuous reword is as much a defect as one
# that never fails, and only measuring both directions tells them apart.
def _budget_refusal(value: object) -> str:
    return rf"limits\.max_scenario_part_bytes.*found {re.escape(repr(value))}"


def test_a_non_integer_manifest_budget_is_a_usage_error(tmp_path):
    # UsageError naming the manifest, not the TypeError a string raises inside
    # partition's comparison: that reaches cli.py's catch-all as an exit-1
    # [internal] finding against the run root -- wrong exit code and wrong
    # artifact -- and manifest.json is intake's own code output, so a finding
    # against it is unrepairable by any re-dispatch.
    run = _run_with_world(tmp_path, _world())
    for bad in ("28000", 28000.0, None, [28000]):
        write_json(run.manifest, {"limits": {"max_scenario_part_bytes": bad}})
        with pytest.raises(UsageError, match=_budget_refusal(bad)):
            rounds.write_batches(run, round_n=1)


def test_a_manifest_budget_outside_the_schema_range_is_a_usage_error(tmp_path):
    # Range beside type, matching manifest-0.1.json's `integer, minimum: 1` for a
    # manifest that reached here without layer 1. True is the case Python makes
    # easy to miss: isinstance(True, int) is True, so a bool would otherwise cap
    # every batch at one byte.
    run = _run_with_world(tmp_path, _world())
    for bad in (0, -1, True):
        write_json(run.manifest, {"limits": {"max_scenario_part_bytes": bad}})
        with pytest.raises(UsageError, match=_budget_refusal(bad)):
            rounds.write_batches(run, round_n=1)


def test_a_malformed_manifest_document_is_a_usage_error(tmp_path):
    # The manifest document itself, not only its limits: without the container
    # door a manifest of `[]` or `7` reaches `.get` and raises AttributeError or
    # TypeError out of a code step, which names the run root instead.
    #
    # Held by these CASES, not by the match= pin: measured, relaxing this to a
    # bare `pytest.raises(UsageError)` and deleting the container door still goes
    # red, because a non-dict manifest cannot reach any other refusal. The two
    # mechanisms are worth keeping straight -- a comment that credits the wrong
    # guard is how the right one gets deleted later.
    run = _run_with_world(tmp_path, _world())
    for bad in ([], "hi", None, 7, {"limits": "none"}, {"limits": 7}):
        write_json(run.manifest, bad)
        with pytest.raises(UsageError, match=r"manifest\.json"):
            rounds.write_batches(run, round_n=1)


def test_a_world_model_of_the_wrong_shape_is_a_usage_error(tmp_path):
    # All four wrong top-level shapes, because they fail differently: [] and "hi"
    # answer `key not in payload` correctly, while None and 7 raise TypeError --
    # the split slices.write_slices' container-door comment records. The last two
    # are objects missing a key this function indexes.
    run = RunPaths(tmp_path)
    for bad in ([], "hi", None, 7, {"schema_version": "0.1"}, {"capabilities": []}):
        write_json(run.world_model, bad)
        with pytest.raises(UsageError):
            rounds.closable_holes(run)


def test_a_capability_or_goal_without_a_string_id_is_a_usage_error(tmp_path):
    # An id absent, not a string, or empty all reach the same f-string, where a
    # non-string interpolates silently into a plausible and wrong hole ref and an
    # empty one mints `cell:/oc`, which coverage-0.1.json's hole_ref pattern
    # refuses -- so the only place it could surface is layer 1 against this
    # module's own output.
    run = RunPaths(tmp_path)
    for bad in (
        {"capabilities": [{"outcome_classes": []}], "goals": []},
        {"capabilities": [{"id": 7, "outcome_classes": []}], "goals": []},
        {"capabilities": [{"id": "", "outcome_classes": []}], "goals": []},
        {"capabilities": [{"id": "cap-0", "outcome_classes": [{}]}], "goals": []},
        {"capabilities": [{"id": "cap-0", "outcome_classes": "x"}], "goals": []},
        {"capabilities": [], "goals": [{"title": "no id"}]},
    ):
        write_json(run.world_model, bad)
        with pytest.raises(UsageError):
            rounds.closable_holes(run)


def test_a_capability_or_goal_array_that_is_not_an_array_is_a_usage_error(tmp_path):
    # Pinned on "is not an array" because a string or a dict here passes for the
    # wrong reason: `enumerate("x")` yields characters and `enumerate({"a": 1})`
    # yields keys, neither of which is a dict, so the unshaped-row refusal fires
    # instead -- with only those cases, a bare `pytest.raises(UsageError)` stayed
    # green when the array guard was deleted. Measured.
    #
    # The `7` cases are what actually hold the guard, pin or no pin: `enumerate(7)`
    # raises TypeError, which from a code step names the run root. So the pin
    # rules out the wrong-reason pass and the number rules out deletion; keeping
    # the division straight is the point of saying so here.
    run = RunPaths(tmp_path)
    for bad in (
        {"capabilities": 7, "goals": []},
        {"capabilities": "x", "goals": []},
        {"capabilities": {"cap-0": {}}, "goals": []},
        {"capabilities": [], "goals": 7},
        {"capabilities": [], "goals": "x"},
        {"capabilities": [{"id": "cap-0", "outcome_classes": 7}], "goals": []},
        {"capabilities": [{"id": "cap-0", "outcome_classes": "x"}], "goals": []},
    ):
        write_json(run.world_model, bad)
        with pytest.raises(UsageError, match="is not an array"):
            rounds.closable_holes(run)


def test_a_capability_without_outcome_classes_is_a_usage_error(tmp_path):
    # world-model-0.1.json lists outcome_classes in capability.required with
    # minItems 1. Measured before the guard: such a capability contributed zero
    # cells in silence, and a world model of only such capabilities made
    # write_batches return None -- manufacturing the loop's NORMAL TERMINAL STATE
    # out of a malformed artifact, which is worse than a crash because nothing
    # downstream can tell it from a converged run. The refusal names the
    # capability, not just the file, because a real world model has 148 cells.
    run = RunPaths(tmp_path)
    write_json(run.world_model, {"capabilities": [{"id": "cap-0"}], "goals": []})
    with pytest.raises(UsageError, match=r"capabilities\[cap-0\]"):
        rounds.closable_holes(run)
    # And end to end: no batch plan, and no None either.
    with pytest.raises(UsageError):
        rounds.write_batches(run, round_n=1)
    assert not run.batches(1).exists()


def test_an_empty_outcome_class_array_is_a_usage_error(tmp_path):
    # minItems 1 in the schema: a capability with an empty array contributes no
    # cell either, so requiring the key without checking it is empty would leave
    # half the silent-zero-cells hole open. Measured: this case returns [] with
    # only the presence check.
    run = RunPaths(tmp_path)
    write_json(
        run.world_model,
        {"capabilities": [{"id": "cap-0", "outcome_classes": []}], "goals": []},
    )
    with pytest.raises(UsageError, match=r"capabilities\[cap-0\]"):
        rounds.closable_holes(run)


def test_a_coverage_report_of_the_wrong_shape_is_a_usage_error(tmp_path):
    # Including a hole with no `ref`, which used to raise a bare KeyError -- and
    # a KeyError from a code step names the run root, not the coverage report.
    run = _run_with_world(tmp_path, _world())
    for bad in (
        [],
        None,
        {"round": 1},
        {"holes": "x"},
        {"holes": 7},
        {"holes": [{"reason": "not_yet_attempted"}]},
        {"holes": [{"ref": 7, "reason": "not_yet_attempted"}]},
        {"holes": [{"ref": "", "reason": "not_yet_attempted"}]},
    ):
        write_json(run.coverage_latest, bad)
        with pytest.raises(UsageError):
            rounds.closable_holes(run)


def test_the_undersized_budget_refusal_names_where_the_budget_came_from(tmp_path):
    # Measured before this split: a run with no manifest was refused with
    # `max_scenario_part_bytes=28000 is below the 40023-byte estimate`, sending a
    # reader to a manifest field that does not exist -- and the operator's actual
    # lever there is to SET that key, not to correct it. Two cases because the
    # message must differ between them, which a single case cannot show.
    world = _world(caps=1, ocs=1, goals=0)
    run = _run_with_world(tmp_path, world)
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": 1,
            "scenarios": [{"id": "sc-b01-001", "body": "x" * 40000}],
        },
    )
    with pytest.raises(UsageError, match="no manifest limit set"):
        rounds.write_batches(run, round_n=1)
    write_json(
        run.manifest,
        {"limits": {"max_rounds": 2, "max_scenarios": 8, "max_scenario_part_bytes": 1000}},
    )
    # The source string here, not _budget_refusal: this test is about which cap
    # SOURCE partition names, and the value 1000 is legitimately set, not refused
    # by _cap_bytes at all.
    with pytest.raises(UsageError, match=r"limits\.max_scenario_part_bytes"):
        rounds.write_batches(run, round_n=1)


def test_duplicate_holes_cost_one_batch_slot_not_two(tmp_path):
    # coverage-0.1.json puts no uniqueItems on `holes`, so a duplicate is a
    # score-stage defect arriving from upstream -- but the cost lands here: one
    # hole would take two batch slots, so a member writes two scenarios for the
    # same cell and rb-instantiate seeds both. This is the last code that can drop
    # it before it is paid for in dispatches. Not a refusal, because unlike the
    # malformed shapes a duplicate has one unambiguous correct reading.
    run = _run_with_world(tmp_path, _world())
    write_json(
        run.coverage_latest,
        {
            "schema_version": "0.1",
            "holes": [
                {
                    "ref": "cell:cap-0/cap-0-oc-0",
                    "reason": "not_yet_attempted",
                    "justification": "x",
                },
                {
                    "ref": "cell:cap-0/cap-0-oc-0",
                    "reason": "not_yet_attempted",
                    "justification": "a second, differently justified copy",
                },
                {"ref": "goal:goal-0", "reason": "not_yet_attempted", "justification": "y"},
            ],
        },
    )
    assert rounds.closable_holes(run) == ["cell:cap-0/cap-0-oc-0", "goal:goal-0"]


def test_duplicate_cells_in_the_world_model_cost_one_batch_slot(tmp_path):
    # The round-1 branch needs the same collapse: two capabilities sharing an id,
    # or one carrying the same outcome class twice, would otherwise cost two
    # dispatched writes for one cell.
    run = _run_with_world(
        tmp_path,
        {
            "schema_version": "0.1",
            "goals": [],
            "capabilities": [
                {"id": "cap-0", "outcome_classes": [{"id": "oc-0"}, {"id": "oc-0"}]},
                {"id": "cap-0", "outcome_classes": [{"id": "oc-0"}]},
            ],
        },
    )
    assert rounds.closable_holes(run) == ["cell:cap-0/oc-0"]


def test_a_sealed_scenarios_file_of_the_wrong_shape_is_a_usage_error(tmp_path):
    # `scenarios` required rather than defaulted, matching scenarios-0.1.json,
    # plus every row shape-checked: a scenario with no string `id` is the row
    # shape layer 1 requires, and the estimate is a mean over these objects.
    run = _run_with_world(tmp_path, _world())
    for bad in (
        [],
        None,
        7,
        {"schema_version": "0.1"},
        {"scenarios": 7},
        {"scenarios": "eighteen scenarios"},
        {"scenarios": [7]},
        {"scenarios": [{"round": 1}]},
        {"scenarios": [{"id": "", "round": 1}]},
    ):
        write_json(run.scenarios, bad)
        with pytest.raises(UsageError):
            rounds.bytes_per_scenario(run)


def test_a_string_scenarios_array_cannot_produce_a_projection_that_does_not_bind(tmp_path):
    # The module's worst-shaped hole, and the only one that produced a plausible
    # wrong number rather than a refusal. Measured before the guard existed: a
    # `scenarios` of "eighteen scenarios" iterated the string's CHARACTERS to a
    # 3-byte estimate, so 86 closable holes became ONE batch projecting 258 bytes
    # against a real write of ~99,932 -- 387x under, and exactly the cap that does
    # not bind, silently, that this module exists to close. Asserted end to end
    # through write_batches rather than on bytes_per_scenario alone, because the
    # projection is where the damage showed.
    run = _run_with_world(
        tmp_path,
        {
            "schema_version": "0.1",
            "goals": [],
            "capabilities": [
                {
                    "id": f"cap-{i:02d}",
                    "outcome_classes": [{"id": f"cap-{i:02d}-oc-0"}],
                }
                for i in range(86)
            ],
        },
    )
    assert len(rounds.closable_holes(run)) == 86
    write_json(
        run.scenarios,
        {"schema_version": "0.1", "denominator_version": 1, "scenarios": "eighteen scenarios"},
    )
    with pytest.raises(UsageError, match="is not an array"):
        rounds.write_batches(run, round_n=1)
    assert not run.batches(1).exists()


def _part(run, round_n, batch, scenarios):
    write_json(
        run.scenario_part(round_n, batch),
        {
            "schema_version": "0.1",
            "round": round_n,
            "batch_id": batch,
            "scenarios": scenarios,
        },
    )


def _scenario(sid, *, round_n=1, goal="goal-0", status="proposed", refs=None, depth=1):
    return {
        "id": sid,
        "round": round_n,
        "goal_id": goal,
        "actor_id": "actor-0",
        "title": f"title {sid}",
        "user_intent": f"intent {sid}",
        "hop_depth": depth,
        "capability_refs": refs
        if refs is not None
        else [{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0"}],
        "discriminating_fact": f"fact {sid}",
        "status": status,
        # Schema-valid rather than the bare {"round": n} the brief sketched:
        # scenarios-0.1.json puts hole_refs (minItems 1) and claim_ids in
        # provenance.required, and one test below validates the sealed document
        # against that schema, which a bare provenance would fail for a reason
        # that has nothing to do with the seal.
        "provenance": {
            "hole_refs": ["cell:cap-0/cap-0-oc-0"],
            "claim_ids": ["cl-0"],
            "round": round_n,
        },
    }


def _score_part(run, round_n, rulings, verdict="continue"):
    write_json(
        run.score_part(round_n),
        {
            "schema_version": "0.1",
            "round": round_n,
            "holes": [],
            "verdict": verdict,
            "rulings": rulings,
        },
    )


def _refuse(run, note=None):
    """seal_scenarios' findings, with the two properties every refusal shares.

    Every finding this module raises carries layer "rounds" -- a reader triaging
    a failed round has to know which assembler refused without reading the
    message -- and no refusal returns a path. Asserted through one helper rather
    than once per test because the layer is set at every call site independently,
    and a single spot check leaves the rest unpinned: measured, replacing only the
    FIRST `"rounds"` in rounds.py with `"refs"` left the whole suite green. The
    sweep that mutates each site in turn is the record of how many there are;
    a number written here would drift the next time one is added.
    """
    path, findings = rounds.seal_scenarios(run)
    assert path is None, note
    assert findings, note
    assert {f.layer for f in findings} == {"rounds"}, note
    return findings


def test_the_seal_assembles_every_round_in_order(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b02", [_scenario("sc-b02-001")])
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _part(run, 2, "b01", [_scenario("sc-b01-002", round_n=2)])
    path, findings = rounds.seal_scenarios(run)
    assert findings == []
    assert path == run.scenarios
    doc = read_json(path)
    # Ordered by (round, batch id, position in part): deterministic, and it is
    # the order a reader scanning rounds expects.
    assert [s["id"] for s in doc["scenarios"]] == [
        "sc-b01-001",
        "sc-b02-001",
        "sc-b01-002",
    ]
    assert doc["denominator_version"] == 1


def test_the_sealed_document_is_schema_valid(tmp_path):
    # The seal's output is code output, so a layer-1 finding against it is
    # unrepairable by any re-dispatch -- which makes "does it clear its own
    # schema" the one property no other test in this module was asserting.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001"), _scenario("sc-b01-002")])
    _score_part(
        run,
        1,
        [{"scenario_id": "sc-b01-002", "status": "duplicate", "duplicate_of": "sc-b01-001"}],
    )
    path, findings = rounds.seal_scenarios(run)
    assert findings == []
    assert validate_artifact(path, "scenarios") == []


def test_the_seal_is_byte_identical_across_two_runs(tmp_path):
    # The property emit and both existing seals exist to hold: identical parts
    # must produce identical bytes, or variance stops being attributable.
    first = _run_with_world(tmp_path / "a", _world())
    second = _run_with_world(tmp_path / "b", _world())
    for run in (first, second):
        _part(run, 1, "b01", [_scenario("sc-b01-001"), _scenario("sc-b01-002")])
        _part(run, 1, "b02", [_scenario("sc-b02-001")])
        rounds.seal_scenarios(run)
    assert first.scenarios.read_bytes() == second.scenarios.read_bytes()


def test_the_seal_is_idempotent(tmp_path):
    # It runs twice per round -- after propose and after score -- so a second
    # run must not be able to disagree with the first. It reads only parts,
    # never its own output, which is what makes that true by construction.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    rounds.seal_scenarios(run)
    once = run.scenarios.read_bytes()
    rounds.seal_scenarios(run)
    assert run.scenarios.read_bytes() == once


def test_the_seal_applies_a_rounds_rulings(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001"), _scenario("sc-b01-002")])
    _score_part(
        run,
        1,
        [
            {"scenario_id": "sc-b01-001", "status": "active"},
            {"scenario_id": "sc-b01-002", "status": "duplicate", "duplicate_of": "sc-b01-001"},
        ],
        verdict="converged",
    )
    _, findings = rounds.seal_scenarios(run)
    assert findings == []
    by_id = {s["id"]: s for s in read_json(run.scenarios)["scenarios"]}
    assert by_id["sc-b01-001"]["status"] == "active"
    assert by_id["sc-b01-002"]["status"] == "duplicate"
    assert by_id["sc-b01-002"]["duplicate_of"] == "sc-b01-001"


def test_a_scenario_with_no_ruling_keeps_the_status_its_member_gave_it(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _score_part(run, 1, [])
    rounds.seal_scenarios(run)
    assert read_json(run.scenarios)["scenarios"][0]["status"] == "proposed"


def test_a_later_round_may_overturn_an_earlier_ruling(tmp_path):
    # rb-score's Output section: "do not re-open a ruling that nothing new bears
    # on", never "statuses are frozen after the round that set them". A
    # rejection notice carried into a re-dispatch is exactly the case.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _score_part(run, 1, [{"scenario_id": "sc-b01-001", "status": "active"}])
    _score_part(
        run,
        2,
        [{"scenario_id": "sc-b01-001", "status": "rejected", "rejected_reason": "ambiguous"}],
        verdict="converged",
    )
    rounds.seal_scenarios(run)
    only = read_json(run.scenarios)["scenarios"][0]
    assert only["status"] == "rejected"
    assert only["rejected_reason"] == "ambiguous"


def test_overturning_a_fold_clears_the_duplicate_pointer_it_left(tmp_path):
    # Set only what the new status requires and clear the other: a scenario
    # rejected after having been folded would otherwise keep a stale
    # duplicate_of, which check_scenarios resolves happily -- it only asks
    # whether the target exists -- so nothing downstream would report it.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001"), _scenario("sc-b01-002")])
    _score_part(
        run,
        1,
        [{"scenario_id": "sc-b01-002", "status": "duplicate", "duplicate_of": "sc-b01-001"}],
    )
    _score_part(
        run,
        2,
        [{"scenario_id": "sc-b01-002", "status": "rejected", "rejected_reason": "out_of_scope"}],
        verdict="converged",
    )
    rounds.seal_scenarios(run)
    by_id = {s["id"]: s for s in read_json(run.scenarios)["scenarios"]}
    assert "duplicate_of" not in by_id["sc-b01-002"]
    assert by_id["sc-b01-002"]["rejected_reason"] == "out_of_scope"


def test_the_seal_refuses_two_parts_claiming_one_scenario_id(tmp_path):
    # Members mint their own ids, so a collision is possible in a way it never
    # was for a single dispatch. It has to be caught here: the merged array
    # would simply carry the id twice, and check_scenarios indexes that array,
    # so it would agree with whatever it was handed.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-001")])
    _part(run, 1, "b02", [_scenario("sc-001")])
    findings = _refuse(run)
    assert not run.scenarios.exists()
    assert any("sc-001" in f.message for f in findings)


def test_the_seal_refuses_a_ruling_for_a_scenario_no_part_wrote(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _score_part(run, 1, [{"scenario_id": "sc-nope", "status": "active"}])
    assert any("sc-nope" in f.message for f in _refuse(run))


def test_a_ruling_with_no_usable_scenario_id_is_a_finding_not_a_traceback(tmp_path):
    # A KeyError out of a code step reaches cli.py's catch-all as an exit-1
    # [internal] finding anchored on the RUN ROOT -- the exit-code contract's
    # third rule breached against an artifact no re-dispatch can repair.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    # Pointer, not the word "scenario_id" in the message. The trap: a pin on
    # message prose breaks on a meaning-preserving reword, and a field name the
    # pointer already carries is the first thing a reword drops -- so pin the
    # pointer, or a value echo from the fixture, and never a prose word. The two
    # pointers differ because a ruling that is not an object at all has no
    # /scenario_id member to point at, so the guard is split and the table
    # records which fires.
    for bad, pointer in (
        ({}, "/rulings/0/scenario_id"),
        ({"status": "active"}, "/rulings/0/scenario_id"),
        ({"scenario_id": 7, "status": "active"}, "/rulings/0/scenario_id"),
        (7, "/rulings/0"),
        (None, "/rulings/0"),
        ([], "/rulings/0"),
    ):
        _score_part(run, 1, [bad])
        assert [f.pointer for f in _refuse(run, bad)] == [pointer], bad
    assert not run.scenarios.exists()


def test_a_ruling_status_outside_the_parts_own_enum_is_a_finding(tmp_path):
    # The whitelist is score-part-0.1.json's own enum, not merely "a string":
    # an arbitrary value would be written straight onto the scenario and make
    # 02-scenarios.json fail scenarios-0.1.json, which is code output too. That
    # enum excludes `proposed` deliberately -- a ruling naming it would be a
    # no-op that still had to be honoured -- so it is refused here as well.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    for bad in (
        {"scenario_id": "sc-b01-001"},
        {"scenario_id": "sc-b01-001", "status": "proposed"},
        {"scenario_id": "sc-b01-001", "status": 7},
        {"scenario_id": "sc-b01-001", "status": "ACTIVE"},
    ):
        _score_part(run, 1, [bad])
        # The pointer, for the reason the test above gives, and this is the case
        # that proved it: a reviewer reworded this message meaning-preservingly,
        # dropping the field name the pointer already carried, and the old
        # `"status" in f.message` pin went red.
        assert [f.pointer for f in _refuse(run, bad)] == ["/rulings/0/status"], bad
    assert not run.scenarios.exists()


def test_a_fold_or_rejection_missing_its_required_field_is_a_finding(tmp_path):
    # The other half of the same KeyError class: score-part-0.1.json requires
    # duplicate_of with `duplicate` and rejected_reason with `rejected` through
    # an if/then, and `ruling[field]` would raise for a part that reached here
    # without layer 1.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    for bad, field in (
        ({"scenario_id": "sc-b01-001", "status": "duplicate"}, "duplicate_of"),
        ({"scenario_id": "sc-b01-001", "status": "duplicate", "duplicate_of": 7}, "duplicate_of"),
        ({"scenario_id": "sc-b01-001", "status": "rejected"}, "rejected_reason"),
    ):
        _score_part(run, 1, [bad])
        # The pointer names the member that should have been there, which is how
        # refs.check_catalogue_facts points at an absent candidate_bytes entry.
        # It carries `field` from the table, so it also discriminates the
        # duplicate_of row from the rejected_reason one.
        assert [f.pointer for f in _refuse(run, bad)] == [f"/rulings/0/{field}"], bad
    assert not run.scenarios.exists()


def test_the_seal_refuses_a_score_part_that_is_not_an_object_with_rulings(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    # Two pointers, because `/rulings` does not resolve in a document that is not
    # an object at all -- the same split the propose-part guard carries.
    for bad, pointer in (
        (None, ""),
        (7, ""),
        ([], ""),
        ("hi", ""),
        ({"round": 1}, "/rulings"),
        ({"rulings": 7}, "/rulings"),
        ({"rulings": "two"}, "/rulings"),
    ):
        write_json(run.score_part(1), bad)
        assert [f.pointer for f in _refuse(run, bad)] == [pointer], bad
    assert not run.scenarios.exists()


def test_two_rulings_in_one_part_naming_one_scenario_are_refused(tmp_path):
    # Measured before the guard: this exact part is layer-1 VALID --
    # score-part-0.1.json puts no uniqueness constraint on `rulings` -- and
    # seal_scenarios returned (path, []) with sealed status `active`, the
    # rejection and its rejected_reason gone. The scenario-id collision hole in
    # the other artifact: the merged document agrees with whatever it was handed,
    # check_scenarios indexes that merged document, so the seal is the only place
    # it can be caught.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-1")])
    _score_part(
        run,
        1,
        [
            {"scenario_id": "sc-1", "status": "rejected", "rejected_reason": "out_of_scope"},
            {"scenario_id": "sc-1", "status": "active"},
        ],
        verdict="converged",
    )
    # Layer 1 asserted here, not assumed: the guard's whole justification is that
    # the schema cannot see this, so a schema that grew a uniqueItems later should
    # make this line fail and send a reader back to the guard.
    assert validate_artifact(run.score_part(1), "score-part") == []
    findings = _refuse(run)
    assert [f.pointer for f in findings] == ["/rulings/1/scenario_id"]
    assert [str(f.artifact) for f in findings] == [str(run.score_part(1))]
    # Both indexes named, so a re-dispatch knows which pair contradicted.
    assert "sc-1" in findings[0].message and "/rulings/0" in findings[0].message
    assert not run.scenarios.exists()


def test_the_within_part_rule_does_not_reach_across_two_parts(tmp_path):
    # The scoping, asserted in the direction a global register would break:
    # rb-score's Output section sanctions a later round overturning an earlier
    # ruling outright, so the register resets per part. Same scenario, same two
    # statuses as the test above, split across two rounds -- and this must SEAL.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-1")])
    _score_part(
        run, 1, [{"scenario_id": "sc-1", "status": "rejected", "rejected_reason": "out_of_scope"}]
    )
    _score_part(run, 2, [{"scenario_id": "sc-1", "status": "active"}], verdict="converged")
    path, findings = rounds.seal_scenarios(run)
    assert findings == []
    only = read_json(path)["scenarios"][0]
    assert only["status"] == "active"
    assert "rejected_reason" not in only


def test_the_seal_refuses_an_unparseable_score_part(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    run.score_part(1).parent.mkdir(parents=True, exist_ok=True)
    run.score_part(1).write_text("{not json", encoding="utf-8")
    assert [str(f.artifact) for f in _refuse(run)] == [str(run.score_part(1))]


def test_the_seal_refuses_an_unparseable_part(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    run.scenario_part(1, "b02").write_text("{not json", encoding="utf-8")
    findings = _refuse(run)
    assert any("b02" in str(f.artifact) or "b02" in f.message for f in findings)


def test_an_unparseable_part_does_not_blame_the_score_part_for_its_scenarios(tmp_path):
    # The cascade an unconditional ruling pass would produce: a part that does
    # not parse means every scenario it held is absent from the index, so every
    # ruling naming one is reported as "no propose part wrote it" -- a finding
    # against 03-score for a defect in 02-scenarios. This package has twice
    # shipped a checker that named the wrong artifact.
    run = _run_with_world(tmp_path, _world())
    run.scenario_round_dir(1).mkdir(parents=True, exist_ok=True)
    run.scenario_part(1, "b01").write_text("{not json", encoding="utf-8")
    _score_part(run, 1, [{"scenario_id": "sc-b01-001", "status": "active"}])
    findings = _refuse(run)
    assert [str(f.artifact) for f in findings] == [str(run.scenario_part(1, "b01"))]


def test_the_seal_refuses_a_part_that_is_not_an_object_with_scenarios(tmp_path):
    run = _run_with_world(tmp_path, _world())
    for bad, pointer in (
        (None, ""),
        (7, ""),
        ([], ""),
        ("hi", ""),
        ({"round": 1}, "/scenarios"),
        ({"scenarios": 7}, "/scenarios"),
        ({"scenarios": "two"}, "/scenarios"),
    ):
        write_json(run.scenario_part(1, "b01"), bad)
        assert [f.pointer for f in _refuse(run, bad)] == [pointer], bad
    assert not run.scenarios.exists()


def test_the_seal_refuses_a_scenario_with_no_string_id(tmp_path):
    run = _run_with_world(tmp_path, _world())
    for bad, pointer in (({"round": 1}, "/scenarios/0/id"), (7, "/scenarios/0")):
        _part(run, 1, "b01", [bad])
        assert [f.pointer for f in _refuse(run, bad)] == [pointer], bad


def test_the_seal_refuses_a_part_whose_name_is_not_a_safe_segment(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    (run.scenario_round_dir(1) / "..bad.json").write_text("{}", encoding="utf-8")
    assert any("..bad" in f.message for f in _refuse(run))


def test_the_seal_writes_nothing_when_no_part_exists(tmp_path):
    # Not a refusal: a run that has not dispatched propose yet simply has no
    # scenarios, and reporting a finding would make the orchestrator retry a
    # stage that has not run.
    run = _run_with_world(tmp_path, _world())
    path, findings = rounds.seal_scenarios(run)
    assert path is None
    assert findings == []


def test_a_round_directory_holding_no_part_is_still_the_not_run_branch(tmp_path):
    # The discriminator is whether a PART exists, not whether a round directory
    # does: an empty 02-scenarios/round-1/ is a dispatch that produced nothing,
    # which is the never-ran case rather than the every-member-declined one.
    run = _run_with_world(tmp_path, _world())
    run.scenario_round_dir(1).mkdir(parents=True)
    path, findings = rounds.seal_scenarios(run)
    assert path is None
    assert findings == []


def test_every_member_declining_its_batch_seals_an_empty_document(tmp_path):
    # The second, DIFFERENT terminal signal, and the reason the branch above is
    # not `if not scenarios`: every member read its batch and could close none of
    # it, which is a real outcome the refusal conditions exist to produce.
    # Withholding the document would make an honest total refusal
    # indistinguishable from a stage that never ran, and rb-score needs a
    # document to read -- score computing a verdict over zero scenarios is how
    # the loop learns it made no progress.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [])
    _part(run, 1, "b02", [])
    path, findings = rounds.seal_scenarios(run)
    assert findings == []
    assert path == run.scenarios
    doc = read_json(path)
    assert doc["scenarios"] == []
    assert doc["denominator_version"] == 1
    # Schema-valid, not merely written: scenarios-0.1.json puts no minItems on
    # `scenarios`, and this document is code output, so a layer-1 finding against
    # it is unrepairable by any re-dispatch.
    assert validate_artifact(path, "scenarios") == []


def test_an_empty_seal_is_not_the_same_signal_as_an_empty_batch_plan(tmp_path):
    # Three terminal signals, not two, and a reader must not collapse them:
    # write_batches returning None says the worklist was empty before any member
    # was dispatched, while the empty seal says members ran and declined.
    run = _run_with_world(tmp_path, _world())
    write_json(
        run.coverage_latest,
        {
            "schema_version": "0.1",
            "holes": [{"ref": "goal:goal-0", "reason": "unreachable", "justification": "x"}],
        },
    )
    assert rounds.write_batches(run, round_n=1) is None
    assert not run.batches(1).exists()
    # No part was dispatched, so the seal is silent rather than empty.
    assert rounds.seal_scenarios(run) == (None, [])


def test_collect_scenarios_hands_back_rows_a_later_fold_cannot_reach(tmp_path, monkeypatch):
    # The deepcopy per row. It is defensive rather than load-bearing today --
    # read_json re-parses, so two collections are already unaliased -- so the
    # only way to WATCH it fail is to make the alias real, which is exactly what
    # a part-document cache added to this module later would do. Without the
    # copy, `first` holds the cached document's own rows and the fold below
    # rewrites them under a caller that had already read the list.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    cache: dict[str, object] = {}
    real = rounds.read_json

    def cached(path):
        return cache.setdefault(str(path), real(path))

    monkeypatch.setattr(rounds, "read_json", cached)
    first, findings = rounds.collect_scenarios(run)
    assert findings == []
    assert first[0]["status"] == "proposed"
    _score_part(run, 1, [{"scenario_id": "sc-b01-001", "status": "active"}])
    assert rounds.seal_scenarios(run)[1] == []
    assert read_json(run.scenarios)["scenarios"][0]["status"] == "active"
    assert first[0]["status"] == "proposed"
    # DEEP, not dict(): measured, a shallow copy passes every assertion above,
    # because _apply_rulings happens to touch only top-level keys today. It leaves
    # provenance and capability_refs shared with the cached document, so the first
    # nested write anyone adds reaches back into a caller's list in the same
    # silence. Identity is the only direction that can see the difference.
    second, _ = rounds.collect_scenarios(run)
    assert first[0] is not second[0]
    assert first[0]["provenance"] is not second[0]["provenance"]
    assert first[0]["capability_refs"][0] is not second[0]["capability_refs"][0]


def test_the_denominator_version_is_the_world_models_own(tmp_path):
    # Echoed, never defaulted: refs.check_scenarios compares this field to
    # world["denominator"]["version"] for equality, so a default of 1 against a
    # world model at 2 is a check-refs finding against a document this code
    # wrote -- unrepairable by re-dispatch.
    world = _world()
    world["denominator"]["version"] = 3
    run = _run_with_world(tmp_path, world)
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    path, _ = rounds.seal_scenarios(run)
    assert read_json(path)["denominator_version"] == 3


def test_a_world_model_with_no_denominator_version_is_a_usage_error(tmp_path):
    # Required rather than defaulted for the reason capabilities and goals are
    # in closable_holes: world-model-0.1.json lists denominator in `required`
    # and version in denominator.required, so a document reaching here without
    # one is a hand-edit, and refusing names the artifact that carries it.
    # Each pin is a VALUE ECHO rather than a phrase from _object_or_refuse, for
    # two reasons at once: "denominator" alone appears in all three messages, so
    # it discriminates none of them from the others, and pinning that helper's
    # wording would break this test on a reword that changes nothing here.
    for i, (world, pin) in enumerate(
        (
            ({"schema_version": "0.1"}, r"\['denominator'\]"),
            ({"schema_version": "0.1", "denominator": {}}, r"\['version'\]"),
            ({"schema_version": "0.1", "denominator": 7}, "found 7"),
        )
    ):
        run = _run_with_world(tmp_path / f"w{i}", world)
        _part(run, 1, "b01", [_scenario("sc-b01-001")])
        with pytest.raises(UsageError, match=pin):
            rounds.seal_scenarios(run)
        assert not run.scenarios.exists()
