"""The propose/score loop's code steps.

Every number asserted here that is not obviously arithmetic came off
runs/run-20260825-094033 on 2026-08-26: 148 capability cells plus 22 goals,
86 closable holes of 151, mean 1,162 bytes per scenario and max 1,579.
"""

from __future__ import annotations

import json

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


# Pinned on the manifest PATH, not merely on UsageError, and that is what makes
# these two assertions able to fail. Measured: 0, -1 and True are each below
# DEFAULT_BYTES_PER_SCENARIO, so partition refuses them on its own -- dropping
# _cap_bytes' whole range-and-bool half left a bare `pytest.raises(UsageError)`
# green, passing on a refusal raised by different code about a different thing.
# partition's message carries no path, so the path is the discriminator, and it
# is also the property actually at stake: the exit-code contract's third rule is
# that a finding must name the right artifact.
_MANIFEST_BUDGET_REFUSAL = r"manifest\.json's limits\.max_scenario_part_bytes must be an integer"


def test_a_non_integer_manifest_budget_is_a_usage_error(tmp_path):
    # UsageError naming the manifest, not the TypeError a string raises inside
    # partition's comparison: that reaches cli.py's catch-all as an exit-1
    # [internal] finding against the run root -- wrong exit code and wrong
    # artifact -- and manifest.json is intake's own code output, so a finding
    # against it is unrepairable by any re-dispatch.
    run = _run_with_world(tmp_path, _world())
    for bad in ("28000", 28000.0, None, [28000]):
        write_json(run.manifest, {"limits": {"max_scenario_part_bytes": bad}})
        with pytest.raises(UsageError, match=_MANIFEST_BUDGET_REFUSAL):
            rounds.write_batches(run, round_n=1)


def test_a_manifest_budget_outside_the_schema_range_is_a_usage_error(tmp_path):
    # Range beside type, matching manifest-0.1.json's `integer, minimum: 1` for a
    # manifest that reached here without layer 1. True is the case Python makes
    # easy to miss: isinstance(True, int) is True, so a bool would otherwise cap
    # every batch at one byte.
    run = _run_with_world(tmp_path, _world())
    for bad in (0, -1, True):
        write_json(run.manifest, {"limits": {"max_scenario_part_bytes": bad}})
        with pytest.raises(UsageError, match=_MANIFEST_BUDGET_REFUSAL):
            rounds.write_batches(run, round_n=1)


def test_a_malformed_manifest_document_is_a_usage_error(tmp_path):
    # The manifest document itself, not only its limits: without the container
    # door a manifest of `[]` or `7` reaches `.get` and raises AttributeError or
    # TypeError out of a code step, which names the run root instead.
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
    # Pinned on "is not an array", because a string or a dict here passes for the
    # wrong reason: `enumerate("x")` yields characters and `enumerate({"a": 1})`
    # yields keys, neither of which is a dict, so the unshaped-row refusal fires
    # and a bare `pytest.raises(UsageError)` stayed green with the array guard
    # deleted. Measured. A number is the case that genuinely needs the guard --
    # `enumerate(7)` raises TypeError, which from a code step names the run root.
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


def test_a_sealed_scenarios_file_of_the_wrong_shape_is_a_usage_error(tmp_path):
    run = _run_with_world(tmp_path, _world())
    write_json(run.scenarios, [])
    with pytest.raises(UsageError):
        rounds.bytes_per_scenario(run)
