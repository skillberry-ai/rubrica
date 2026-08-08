"""compare-gold: matching a generated suite against authored bench tasks.

Recall here is a smoke signal. The tests below pin the *rules* -- goal identity
required, cell overlap scored, one gold task to at most one scenario -- because
those are what make the number mean anything, not the number itself.
"""

from __future__ import annotations

import json

import pytest

from testgen.errors import UsageError
from testgen.recall import (
    MATCH_JACCARD_FLOOR,
    assign_matches,
    cells,
    generated_tasks,
    load_gold,
)
from tests.builders import minimal_gold, minimal_scenarios
from tests.unit.test_refs_states import build_state


def _gold_file(tmp_path, payload=None):
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(payload if payload is not None else minimal_gold()), "utf-8")
    return path


def _generated(sid, goal_id="goal-triage", hop_depth=2, refs=(("cap-find-jobs", "oc-success"),)):
    return {
        "id": sid,
        "goal_id": goal_id,
        "hop_depth": hop_depth,
        "capability_refs": [{"capability_id": c, "outcome_class_id": o} for c, o in refs],
    }


def _gold(gid, goal_id="goal-triage", hop_depth=2, refs=(("cap-find-jobs", "oc-success"),)):
    return {**_generated(gid, goal_id, hop_depth, refs), "id": gid}


# -- load_gold ---------------------------------------------------------------


def test_a_valid_gold_file_loads(tmp_path):
    assert load_gold(_gold_file(tmp_path))["tasks"][0]["id"] == "bench-001"


def test_an_absent_gold_file_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError, match="unusable gold"):
        load_gold(tmp_path / "nope.json")


def test_a_gold_file_that_fails_the_schema_is_a_usage_error(tmp_path):
    payload = minimal_gold()
    payload["tasks"][0]["hop_depth"] = 99
    with pytest.raises(UsageError):
        load_gold(_gold_file(tmp_path, payload))


def test_an_empty_gold_list_is_allowed(tmp_path):
    """ "We have no bench tasks yet" is a real state, and refusing it would make
    compare-gold unusable on a second target before anyone authored one."""
    assert load_gold(_gold_file(tmp_path, minimal_gold(tasks=[])))["tasks"] == []


# -- generated_tasks ---------------------------------------------------------


def test_only_emitted_scenarios_count_as_generated(tmp_path):
    """Recall is about the suite that shipped.

    A scenario the adversary rejected produced no package, so counting it would
    credit the pipeline with finding a test it did not deliver.
    """
    run = build_state(tmp_path, "emit")
    assert [task["id"] for task in generated_tasks(run)] == ["scn-001"]


def test_a_package_whose_scenario_vanished_is_skipped(tmp_path):
    from testgen.artifacts import write_json

    run = build_state(tmp_path, "emit")
    write_json(run.scenarios, minimal_scenarios(scenarios=[]))
    assert generated_tasks(run) == []


def test_a_scenario_present_but_not_emitted_is_excluded(tmp_path):
    """Recall is about the suite that shipped.

    scn-001 is still listed in 02-scenarios.json here -- challenge rejected it,
    so emit pruned its 06-suite/ package. Crediting the pipeline with a scenario
    the adversary rejected would count a test it did not deliver, so a scenario
    present but not emitted must be excluded, not merely one absent from 02
    entirely (that is test_a_package_whose_scenario_vanished_is_skipped above).
    """
    run = build_state(tmp_path, "post-rejection")
    assert generated_tasks(run) == []


# -- cells -------------------------------------------------------------------


def test_cells_is_the_set_of_capability_outcome_pairs():
    assert cells(_generated("s")["capability_refs"]) == frozenset({("cap-find-jobs", "oc-success")})


def test_a_repeated_ref_collapses():
    refs = (("cap-a", "oc-1"), ("cap-a", "oc-1"))
    assert len(cells(_generated("s", refs=refs)["capability_refs"])) == 1


# -- assign_matches ----------------------------------------------------------


def test_an_exact_pair_matches():
    matches, unmatched_gold, unmatched_generated = assign_matches(
        [_gold("bench-001")], [_generated("scn-001")]
    )
    assert [(m["gold_id"], m["scenario_id"], m["jaccard"]) for m in matches] == [
        ("bench-001", "scn-001", 1.0)
    ]
    assert (unmatched_gold, unmatched_generated) == ([], [])


def test_a_different_goal_never_matches_however_similar_the_cells():
    """Goal identity is required, not scored.

    The two tasks below share every capability cell. They are still different
    tests: the goal is what a test is *about*, and scoring it would let a
    find-the-failing-job scenario partially match a check-inventory bench task
    because both happen to call query_aap2.
    """
    matches, unmatched_gold, unmatched_generated = assign_matches(
        [_gold("bench-001", goal_id="goal-triage")],
        [_generated("scn-001", goal_id="goal-inventory")],
    )
    assert matches == []
    assert unmatched_gold == ["bench-001"]
    assert [s["id"] for s in unmatched_generated] == ["scn-001"]


def test_overlap_below_the_floor_does_not_match():
    gold = _gold("bench-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-c", "oc-1")))
    generated = _generated(
        "scn-001", refs=(("cap-a", "oc-1"), ("cap-x", "oc-1"), ("cap-y", "oc-1"))
    )
    assert assign_matches([gold], [generated])[0] == []
    assert MATCH_JACCARD_FLOOR > 0.2


def test_overlap_at_the_floor_matches():
    gold = _gold("bench-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1")))
    generated = _generated(
        "scn-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-c", "oc-1"))
    )
    matches, _, _ = assign_matches([gold], [generated])
    assert len(matches) == 1
    assert matches[0]["jaccard"] == pytest.approx(2 / 3)


def test_one_gold_task_matches_at_most_one_scenario():
    """Otherwise recall inflates: eight paraphrases of one test would each be
    credited against the same bench task."""
    gold = [_gold("bench-001")]
    matches, _, unmatched_generated = assign_matches(
        gold, [_generated("scn-001"), _generated("scn-002")]
    )
    assert len(matches) == 1
    assert len(unmatched_generated) == 1


def test_one_scenario_matches_at_most_one_gold_task():
    matches, unmatched_gold, _ = assign_matches(
        [_gold("bench-001"), _gold("bench-002")], [_generated("scn-001")]
    )
    assert len(matches) == 1
    assert len(unmatched_gold) == 1


def test_the_best_available_pair_wins_and_the_assignment_is_deterministic():
    """Greedy on descending overlap, ties broken by id.

    Without a total order the same inputs could produce two different match sets
    across runs, and recall would look like it moved when nothing did.
    """
    gold = [_gold("bench-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1")))]
    close = _generated("scn-close", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1")))
    loose = _generated("scn-loose", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-c", "oc-1")))
    for order in ([close, loose], [loose, close]):
        matches, _, _ = assign_matches(gold, order)
        assert [m["scenario_id"] for m in matches] == ["scn-close"]


def test_ties_are_broken_by_id_not_input_order():
    """The best-pair test above never ties: close (1.0) and loose (2/3) differ in
    score, so descending-score ordering alone would satisfy it with no tie-break
    at all. A tie is not contrived -- two near-duplicate bench tasks over the same
    goal sharing one capability cell, against two near-duplicate generated
    scenarios, is a plausible shape for a ten-task gold set, and without a total
    order the same inputs could resolve to two different match sets across runs,
    making recall look like it moved when nothing did.
    """
    gold = [_gold("bench-b"), _gold("bench-a")]
    for gens in (
        [_generated("scn-y"), _generated("scn-x")],
        [_generated("scn-x"), _generated("scn-y")],
    ):
        matches, _, _ = assign_matches(gold, gens)
        assert sorted((m["gold_id"], m["scenario_id"]) for m in matches) == [
            ("bench-a", "scn-x"),
            ("bench-b", "scn-y"),
        ]
