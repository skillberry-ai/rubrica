from rubrica.dedupe import Candidate, candidate_pairs


def _scn(sid, goal, cells, status="active"):
    return {
        "id": sid,
        "goal_id": goal,
        "status": status,
        "capability_refs": [{"capability_id": c, "outcome_class_id": o} for c, o in cells],
    }


def test_no_candidates_for_a_single_scenario():
    assert candidate_pairs([_scn("s1", "g1", [("cap-a", "oc-1")])]) == []


def test_same_goal_and_identical_cells_is_a_candidate():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1")]),
    ]
    assert candidate_pairs(scenarios) == [
        Candidate(a="s1", b="s2", shared_cells=("cell:cap-a/oc-1",), identical_cells=True)
    ]


def test_same_goal_with_partial_overlap_is_a_candidate_but_not_identical():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1"), ("cap-b", "oc-2")]),
        _scn("s2", "g1", [("cap-a", "oc-1")]),
    ]
    candidate = candidate_pairs(scenarios)[0]
    assert candidate.shared_cells == ("cell:cap-a/oc-1",)
    assert candidate.identical_cells is False


def test_different_goals_are_never_candidates():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g2", [("cap-a", "oc-1")]),
    ]
    assert candidate_pairs(scenarios) == []


def test_same_goal_with_no_shared_cells_is_not_a_candidate():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-b", "oc-2")]),
    ]
    assert candidate_pairs(scenarios) == []


def test_already_resolved_scenarios_are_excluded():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1")], status="duplicate"),
        _scn("s3", "g1", [("cap-a", "oc-1")], status="rejected"),
    ]
    assert candidate_pairs(scenarios) == []


def test_proposed_and_active_scenarios_are_both_considered():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")], status="proposed"),
        _scn("s2", "g1", [("cap-a", "oc-1")], status="active"),
    ]
    assert len(candidate_pairs(scenarios)) == 1


def test_pairs_are_ordered_and_each_appears_once():
    scenarios = [
        _scn("s3", "g1", [("cap-a", "oc-1")]),
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1")]),
    ]
    pairs = [(c.a, c.b) for c in candidate_pairs(scenarios)]
    assert pairs == [("s1", "s2"), ("s1", "s3"), ("s2", "s3")]


def test_shared_cells_are_sorted_for_stable_output():
    scenarios = [
        _scn("s1", "g1", [("cap-b", "oc-2"), ("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1"), ("cap-b", "oc-2")]),
    ]
    assert candidate_pairs(scenarios)[0].shared_cells == ("cell:cap-a/oc-1", "cell:cap-b/oc-2")
