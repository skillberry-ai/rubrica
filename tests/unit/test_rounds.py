"""The propose/score loop's code steps.

Every number asserted here that is not obviously arithmetic came off
runs/run-20260825-094033 on 2026-08-26: 148 capability cells plus 22 goals,
86 closable holes of 151, mean 1,162 bytes per scenario and max 1,579.
"""

from __future__ import annotations

import json
import re

import pytest

from rubrica import refs, rounds
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


def _score_part(run, round_n, rulings=None, *, holes=None, verdict="continue"):
    """One score part, whichever half of it the test under way cares about.

    `rulings` stays positional because the seal_scenarios tests below read as a
    list of rulings and nothing else, while `holes` is keyword-only because the
    seal_score tests name both halves. One helper rather than two: the two would
    write the same four fields, and a second definition of this name would shadow
    the first for every test after it -- silently, since the shadowed calls are
    positional and would only fail on the argument count.
    """
    write_json(
        run.score_part(round_n),
        {
            "schema_version": "0.1",
            "round": round_n,
            "holes": [] if holes is None else holes,
            "verdict": verdict,
            "rulings": [] if rulings is None else rulings,
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


def test_a_capability_cell_lists_every_claimant_but_is_covered_only_by_a_live_one():
    # Asymmetric on purpose, and rb-score's Method step 4 is where it comes
    # from: scenario_ids lists the scenarios *claiming* the cell, covered is
    # true only if one of them is proposed or active. A cell claimed only by
    # folded or rejected scenarios is a hole again, because no test will ship.
    world = _world(caps=1, ocs=1, goals=0)
    refs_to = [{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0"}]
    scenarios = [
        _scenario("sc-001", status="duplicate", refs=refs_to),
        _scenario("sc-002", status="rejected", refs=refs_to),
    ]
    matrix = rounds.capability_matrix(world, scenarios)
    assert matrix["cells"][0]["scenario_ids"] == ["sc-001", "sc-002"]
    assert matrix["cells"][0]["covered"] is False
    assert matrix == {"cells": matrix["cells"], "covered": 0, "total": 1, "pct": 0.0}

    scenarios.append(_scenario("sc-003", status="active", refs=refs_to))
    matrix = rounds.capability_matrix(world, scenarios)
    assert matrix["cells"][0]["covered"] is True
    assert matrix["covered"] == 1 and matrix["pct"] == 1.0


def test_every_declared_cell_appears_even_with_no_scenarios():
    # The dangerous direction, per Method step 4: a matrix holding only the
    # cells some scenario happens to claim reports 100% of a denominator it
    # shrank to fit. Enumerate from the world model, never from the scenarios.
    matrix = rounds.capability_matrix(_world(caps=2, ocs=2, goals=0), [])
    assert matrix["total"] == 4
    assert matrix["covered"] == 0
    assert matrix["pct"] == 0.0
    assert [c["capability_id"] for c in matrix["cells"]] == [
        "cap-0",
        "cap-0",
        "cap-1",
        "cap-1",
    ]


def test_a_goal_row_carries_only_live_scenarios():
    # Method step 5: leaving a duplicate in a goal row credits the goal with a
    # depth no shipped test reaches.
    world = _world(caps=1, ocs=1, goals=1)
    world["goals"][0]["expected_hop_depths"] = [1, 2]
    scenarios = [
        _scenario("sc-001", status="active", depth=1),
        _scenario("sc-002", status="duplicate", depth=2),
    ]
    row = rounds.goal_matrix(world, scenarios)["rows"][0]
    assert row["scenario_ids"] == ["sc-001"]
    assert row["hop_depths_present"] == [1]
    assert row["hop_depths_expected"] == [1, 2]
    # A goal exercised at one depth of two is a partial row, not a covered one.
    assert row["covered"] is False


def test_a_goal_is_covered_only_when_every_expected_depth_is_present():
    world = _world(caps=1, ocs=1, goals=1)
    world["goals"][0]["expected_hop_depths"] = [1, 2]
    scenarios = [
        _scenario("sc-001", status="active", depth=1),
        _scenario("sc-002", status="active", depth=2),
    ]
    row = rounds.goal_matrix(world, scenarios)["rows"][0]
    assert row["hop_depths_present"] == [1, 2]
    assert row["covered"] is True


def test_expected_hop_depths_are_copied_not_trimmed():
    # Method step 5 says copied, not re-derived and not trimmed to what the
    # scenarios reached -- trimming is how a partial row looks complete.
    world = _world(caps=1, ocs=1, goals=1)
    world["goals"][0]["expected_hop_depths"] = [3, 1]
    row = rounds.goal_matrix(world, [])["rows"][0]
    assert row["hop_depths_expected"] == [1, 3]
    assert row["covered"] is False


def test_an_empty_denominator_gives_pct_zero_not_a_zero_division():
    empty = {
        "schema_version": "0.1",
        "capabilities": [],
        "goals": [],
        "denominator": {"capability_cells": 0, "goals": 0, "version": 1},
    }
    assert rounds.capability_matrix(empty, [])["pct"] == 0.0
    assert rounds.goal_matrix(empty, [])["pct"] == 0.0


def test_the_live_status_set_is_the_one_refs_recomputes_coverage_against(tmp_path):
    # One home, not two spellings that agree today. refs.check_coverage builds
    # its own live_ids from OPEN_STATUSES and reports every row a seal marks
    # covered whose every credit is dead, so a second spelling here would make
    # this module write a document check-refs then refuses -- with the
    # disagreement invisible in either file. The identity pin is the cheap half;
    # the round trip below is what would catch a wrapper that widened the set.
    assert rounds._live_statuses() is refs.OPEN_STATUSES

    run = _run_with_world(tmp_path, _world(caps=2, ocs=1, goals=1))
    survivor = _scenario("sc-b01-001")
    folded = _scenario(
        "sc-b01-002", refs=[{"capability_id": "cap-1", "outcome_class_id": "cap-1-oc-0"}]
    )
    _part(run, 1, "b01", [survivor, folded])
    _score_part(
        run,
        1,
        rulings=[
            {"scenario_id": "sc-b01-001", "status": "active"},
            {
                "scenario_id": "sc-b01-002",
                "status": "duplicate",
                "duplicate_of": "sc-b01-001",
            },
        ],
        # cap-1's only claimant is the fold, so no test ships for that cell and
        # it is a hole again -- the asymmetry _live_statuses names.
        holes=[
            {
                "ref": "cell:cap-1/cap-1-oc-0",
                "reason": "not_yet_attempted",
                "justification": "its only claimant was folded",
            }
        ],
    )
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert findings == []
    assert validate_artifact(path, "coverage") == []
    assert refs.check_coverage(run) == []
    assert read_json(path)["capability_matrix"]["covered"] == 1


def test_round_one_progress_counts_the_cells_it_covered(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=2, goals=0))
    matrix = rounds.capability_matrix(
        read_json(run.world_model),
        [
            _scenario(
                "sc-001",
                status="active",
                refs=[{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0"}],
            ),
        ],
    )
    assert rounds.progress(run, 1, matrix) == {
        "new_cells_this_round": 1,
        "rounds_without_progress": 0,
    }


def test_round_one_that_covered_nothing_starts_the_no_progress_count(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=2, goals=0))
    matrix = rounds.capability_matrix(read_json(run.world_model), [])
    assert rounds.progress(run, 1, matrix) == {
        "new_cells_this_round": 0,
        "rounds_without_progress": 1,
    }


def test_new_cells_is_a_set_difference_not_a_count_difference(tmp_path):
    # Method step 8: "covered now and were *not* covered before". A count
    # difference reports zero when one cell is gained and another lost, which
    # is real progress the loop would then halt on.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=2, goals=0))
    write_json(
        run.coverage_round(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "denominator_version": 1,
            "capability_matrix": {
                "cells": [
                    {
                        "capability_id": "cap-0",
                        "outcome_class_id": "cap-0-oc-0",
                        "scenario_ids": ["sc-001"],
                        "covered": True,
                    },
                    {
                        "capability_id": "cap-0",
                        "outcome_class_id": "cap-0-oc-1",
                        "scenario_ids": [],
                        "covered": False,
                    },
                ],
                "covered": 1,
                "total": 2,
                "pct": 0.5,
            },
            "goal_matrix": {"rows": [], "covered": 0, "total": 0, "pct": 0.0},
            "holes": [],
            "verdict": "continue",
            "progress": {"new_cells_this_round": 1, "rounds_without_progress": 0},
        },
    )
    now = rounds.capability_matrix(
        read_json(run.world_model),
        [
            _scenario(
                "sc-002",
                status="active",
                round_n=2,
                refs=[{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-1"}],
            ),
        ],
    )
    assert now["covered"] == 1  # same count as round 1
    assert rounds.progress(run, 2, now)["new_cells_this_round"] == 1
    assert rounds.progress(run, 2, now)["rounds_without_progress"] == 0


def test_a_round_with_no_new_cell_increments_the_prior_no_progress_count(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    write_json(
        run.coverage_round(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "denominator_version": 1,
            "capability_matrix": {"cells": [], "covered": 0, "total": 0, "pct": 0.0},
            "goal_matrix": {"rows": [], "covered": 0, "total": 0, "pct": 0.0},
            "holes": [],
            "verdict": "continue",
            "progress": {"new_cells_this_round": 0, "rounds_without_progress": 1},
        },
    )
    matrix = rounds.capability_matrix(read_json(run.world_model), [])
    assert rounds.progress(run, 2, matrix)["rounds_without_progress"] == 2


def test_a_prior_coverage_document_of_the_wrong_shape_cannot_baseline_a_round(tmp_path):
    # 03-coverage/round-N.json is seal_score's own code output, so a malformed
    # one is a hand-edit no re-dispatch could repair -- exit 2, not a finding.
    # Every case here reaches `prior[...]` or `carried + 1` bare without the
    # guards, which cli.py's catch-all would report as an exit-1 [internal]
    # finding against the RUN ROOT.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    matrix = rounds.capability_matrix(read_json(run.world_model), [])
    fine = {"rounds_without_progress": 0}
    for payload, expected in (
        (["cells"], "is not a JSON object"),
        ({"progress": fine}, "missing required field(s): ['capability_matrix']"),
        ({"capability_matrix": 7, "progress": fine}, "capability_matrix is not a JSON object"),
        (
            {"capability_matrix": {"cells": "one"}, "progress": fine},
            "capability_matrix.cells is not an array",
        ),
        (
            {
                "capability_matrix": {"cells": [{"capability_id": "cap-0", "covered": True}]},
                "progress": fine,
            },
            "non-empty string outcome_class_id",
        ),
        (
            {"capability_matrix": {"cells": []}, "progress": {}},
            "missing required field(s): ['rounds_without_progress']",
        ),
        (
            {"capability_matrix": {"cells": []}, "progress": {"rounds_without_progress": "two"}},
            "must be an integer >= 0: found 'two'",
        ),
        (
            {"capability_matrix": {"cells": []}, "progress": {"rounds_without_progress": True}},
            "must be an integer >= 0: found True",
        ),
    ):
        write_json(run.coverage_round(1), payload)
        with pytest.raises(UsageError, match=re.escape(expected)):
            rounds.progress(run, 2, matrix)


def test_seal_score_composes_a_schema_valid_coverage_document(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=1))
    # Two expected depths against the one the scenario reaches, so the goal row
    # is partial and the hole below justifies it. With the fixture's single
    # expected depth the scenario covers the goal outright, which would make that
    # hole name a covered row -- the refusal three tests down, not this one.
    world = read_json(run.world_model)
    world["goals"][0]["expected_hop_depths"] = [1, 2]
    write_json(run.world_model, world)
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _score_part(
        run,
        1,
        holes=[
            {"ref": "goal:goal-0", "reason": "not_yet_attempted", "justification": "nobody yet"}
        ],
        verdict="continue",
        rulings=[{"scenario_id": "sc-b01-001", "status": "active"}],
    )
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert findings == []
    assert path == run.coverage_round(1)
    assert validate_artifact(path, "coverage") == []
    doc = read_json(path)
    assert doc["round"] == 1
    assert doc["verdict"] == "continue"
    assert doc["capability_matrix"]["covered"] == 1
    assert doc["goal_matrix"]["covered"] == 0
    assert doc["holes"] == [
        {"ref": "goal:goal-0", "reason": "not_yet_attempted", "justification": "nobody yet"},
    ]
    # latest.json is a code-written copy, so it cannot drift from round-N.json
    # the way two model writes of "identical content" can.
    assert run.coverage_latest.read_bytes() == path.read_bytes()


def test_the_score_seal_echoes_the_world_models_denominator_version(tmp_path):
    # Invariant 7, and the reason seal_scenarios refuses to default its own copy:
    # refs.check_coverage compares this field to the world model's for EQUALITY,
    # so a fallback of 1 is a check-refs finding against a document this code
    # just wrote, unrepairable by any re-dispatch.
    world = _world(caps=1, ocs=1, goals=0)
    world["denominator"]["version"] = 2
    run = _run_with_world(tmp_path, world)
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    _score_part(run, 1, verdict="converged")
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert findings == []
    assert read_json(path)["denominator_version"] == 2


def test_a_world_model_with_no_denominator_version_cannot_be_scored(tmp_path):
    world = _world(caps=1, ocs=1, goals=0)
    del world["denominator"]["version"]
    run = _run_with_world(tmp_path, world)
    _score_part(run, 1, verdict="converged")
    # Written by hand rather than sealed, because seal_scenarios refuses the same
    # absence one step earlier -- this leaves seal_score the only thing under test.
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": 1,
            "scenarios": [_scenario("sc-b01-001", status="active")],
        },
    )
    with pytest.raises(UsageError, match=re.escape("denominator is missing required")):
        rounds.seal_score(run, round_n=1)
    assert not run.coverage_round(1).exists()


def test_a_capability_with_no_outcome_classes_cannot_shrink_the_scored_denominator(tmp_path):
    # The one arithmetic error rb-score's refusal conditions rank above every
    # other: a report reading 100% against a denominator it quietly shrank. Left
    # unguarded, cap-1 contributes zero cells, the matrix reads 1 of 1 covered
    # with no hole owed, and the seal is clean.
    world = _world(caps=2, ocs=1, goals=0)
    world["capabilities"][1]["outcome_classes"] = []
    run = _run_with_world(tmp_path, world)
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    _score_part(run, 1, verdict="converged")
    rounds.seal_scenarios(run)
    with pytest.raises(
        UsageError, match=re.escape("capabilities[cap-1].outcome_classes has 0 entries")
    ):
        rounds.seal_score(run, round_n=1)
    assert not run.coverage_round(1).exists()


def test_a_sealed_scenario_list_of_the_wrong_shape_cannot_be_scored(tmp_path):
    # bytes_per_scenario's measurement, arriving at the other reader of the same
    # file: a string `scenarios` is iterable, so without the guard every matrix
    # here is computed over its characters.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _score_part(
        run,
        1,
        holes=[
            {"ref": "cell:cap-0/cap-0-oc-0", "reason": "not_yet_attempted", "justification": "x"}
        ],
    )
    write_json(
        run.scenarios,
        {"schema_version": "0.1", "denominator_version": 1, "scenarios": "eighteen scenarios"},
    )
    with pytest.raises(UsageError, match=re.escape("scenarios is not an array")):
        rounds.seal_score(run, round_n=1)
    assert not run.coverage_round(1).exists()


def test_seal_score_refuses_an_uncovered_row_with_no_hole(tmp_path):
    # refs.check_coverage checks both directions after the fact; the seal
    # refuses before the write, because a coverage document missing a hole is
    # otherwise perfectly assemblable and reads as complete at gate 2.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=1))
    _part(run, 1, "b01", [])
    _score_part(run, 1, holes=[])
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert not run.coverage_round(1).exists()
    assert not run.coverage_latest.exists()
    refs_named = " ".join(f.message for f in findings)
    assert "cell:cap-0/cap-0-oc-0" in refs_named
    assert "goal:goal-0" in refs_named
    assert {(f.layer, f.pointer) for f in findings} == {("rounds", "/holes")}


def test_seal_score_refuses_a_hole_naming_a_covered_row(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    _score_part(
        run,
        1,
        holes=[
            {"ref": "cell:cap-0/cap-0-oc-0", "reason": "not_yet_attempted", "justification": "x"}
        ],
        verdict="converged",
    )
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert any("cell:cap-0/cap-0-oc-0" in f.message for f in findings)


def test_seal_score_refuses_a_hole_naming_a_row_the_world_model_does_not_have(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    _score_part(
        run,
        1,
        holes=[{"ref": "cell:cap-9/nope", "reason": "unreachable", "justification": "x"}],
        verdict="converged",
    )
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert any("cap-9" in f.message for f in findings)


def test_seal_score_refuses_a_missing_score_part(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert [(f.layer, f.pointer) for f in findings] == [("rounds", "")]
    assert "missing artifact" in findings[0].message


def test_a_score_part_that_is_not_a_json_object_names_the_document_root(tmp_path):
    # Split from the field checks for the reason _apply_rulings splits its own:
    # `/holes` does not resolve in a part that is not an object at all. Left
    # unsplit, `part.get("holes")` raises AttributeError out of a code step.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    rounds.seal_scenarios(run)
    write_json(run.score_part(1), ["holes"])
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert [(f.layer, f.pointer) for f in findings] == [("rounds", "")]


def test_a_score_part_missing_holes_or_a_verdict_names_each_field_it_lacks(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    rounds.seal_scenarios(run)
    write_json(run.score_part(1), {"schema_version": "0.1", "round": 1, "rulings": []})
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert sorted(f.pointer for f in findings) == ["/holes", "/verdict"]
    assert {f.layer for f in findings} == {"rounds"}


def test_a_hole_with_no_usable_ref_is_a_finding_not_a_traceback(tmp_path):
    # 03-score/round-N.json is MODEL output, so this is exit 1 naming the part
    # rather than the exit 2 the world model's own defects get: re-dispatching
    # score alone is exactly the repair. Left unguarded, `hole["ref"]` raises
    # TypeError on the first case and KeyError on the second.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    rounds.seal_scenarios(run)
    rest = {"reason": "unreachable", "justification": "x"}
    for holes, pointer in (
        ([7], "/holes/0"),
        ([rest], "/holes/0/ref"),
        ([{"ref": "", **rest}], "/holes/0/ref"),
        ([{"ref": 3, **rest}], "/holes/0/ref"),
        ([{"ref": "cell:cap-0/cap-0-oc-0", **rest}, 7], "/holes/1"),
    ):
        _score_part(run, 1, holes=holes, verdict="converged")
        path, findings = rounds.seal_score(run, round_n=1)
        assert path is None, holes
        assert [(f.layer, f.pointer) for f in findings] == [("rounds", pointer)], holes
        assert not run.coverage_round(1).exists(), holes


def test_the_score_seal_is_idempotent(tmp_path):
    # The byte-identity guarantee this module exists for, at its second seal: the
    # matrices are recomputed from the same parts, and progress reads round N-1
    # rather than its own output, so nothing here can drift on a second call.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _score_part(
        run, 1, rulings=[{"scenario_id": "sc-b01-001", "status": "active"}], verdict="converged"
    )
    rounds.seal_scenarios(run)
    first = rounds.seal_score(run, round_n=1)[0].read_bytes()
    assert rounds.seal_score(run, round_n=1)[0].read_bytes() == first


def test_a_re_score_after_a_rejection_reopens_the_row_the_scenario_credited(tmp_path):
    # Invariant 5, and the reason the arithmetic moved into code at all: recompute
    # without the status edit and the row keeps covered:true on the strength of a
    # test that will never ship. Here the recompute is not a step score can skip.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _score_part(
        run, 1, rulings=[{"scenario_id": "sc-b01-001", "status": "active"}], verdict="converged"
    )
    rounds.seal_scenarios(run)
    before = read_json(rounds.seal_score(run, round_n=1)[0])
    assert before["capability_matrix"]["cells"][0]["covered"] is True
    assert before["holes"] == []

    # rb-challenge found the scenario ambiguous, so score is re-dispatched for the
    # same round and rules on it again.
    _score_part(
        run,
        1,
        rulings=[
            {"scenario_id": "sc-b01-001", "status": "rejected", "rejected_reason": "ambiguous"}
        ],
        holes=[
            {
                "ref": "cell:cap-0/cap-0-oc-0",
                "reason": "not_yet_attempted",
                "justification": "its only scenario was rejected as ambiguous",
            }
        ],
        verdict="continue",
    )
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert findings == []
    after = read_json(path)
    cell = after["capability_matrix"]["cells"][0]
    # Still listed as a claimant -- the asymmetry -- but no longer covered.
    assert cell["scenario_ids"] == ["sc-b01-001"]
    assert cell["covered"] is False
    assert after["capability_matrix"]["pct"] == 0.0
    assert refs.check_coverage(run) == []


def test_a_missing_prior_coverage_document_is_refused_rather_than_reset(tmp_path):
    """Ruling R20, and both halves of it on one run so they cannot collapse.

    Measured before the refusal existed: round 5 with round-4's document absent
    returned {'new_cells_this_round': 1, 'rounds_without_progress': 0}, erasing
    four rounds of accumulated history -- so halted_no_progress could never fire
    from it and the loop would run to the round cap. That is the failure Method
    step 8 warns about in its own words. Round 1's absence is the legitimate case
    and stays one, which is why both are asserted here rather than in two tests
    that could drift apart.
    """
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    matrix = rounds.capability_matrix(
        read_json(run.world_model),
        [
            _scenario(
                "sc-001",
                status="active",
                refs=[{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0"}],
            )
        ],
    )
    assert matrix["covered"] == 1

    # Round 1: no prior document is normal, and the covered cell is new.
    assert rounds.progress(run, 1, matrix) == {
        "new_cells_this_round": 1,
        "rounds_without_progress": 0,
    }

    # Round 2 onward: the same absence is an inconsistent run. UsageError rather
    # than a Finding because 03-coverage/round-N.json is seal_score's own code
    # output -- no re-dispatch of any prompt can produce it.
    for round_n in (2, 5):
        with pytest.raises(UsageError, match=re.escape(str(run.coverage_round(round_n - 1)))):
            rounds.progress(run, round_n, matrix)
    assert not run.coverage_round(1).exists()

    # And it is the absence that is refused, not the round number: write round 1's
    # document and round 2 measures against it.
    write_json(
        run.coverage_round(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "denominator_version": 1,
            "capability_matrix": matrix,
            "goal_matrix": {"rows": [], "covered": 0, "total": 0, "pct": 0.0},
            "holes": [],
            "verdict": "continue",
            "progress": {"new_cells_this_round": 1, "rounds_without_progress": 0},
        },
    )
    assert rounds.progress(run, 2, matrix) == {
        "new_cells_this_round": 0,
        "rounds_without_progress": 1,
    }


def test_a_second_round_seal_refuses_when_the_first_rounds_document_is_absent(tmp_path):
    # R20 reaching seal_score, which is where the orchestrator meets it: the
    # compose is otherwise clean, so without the refusal this round would publish
    # a coverage document carrying a reset halt signal.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 2, "b01", [_scenario("sc-b01-001", round_n=2, status="active")])
    _score_part(run, 2, verdict="converged")
    rounds.seal_scenarios(run)
    with pytest.raises(UsageError, match=re.escape(str(run.coverage_round(1)))):
        rounds.seal_score(run, round_n=2)
    assert not run.coverage_round(2).exists()
    assert not run.coverage_latest.exists()
