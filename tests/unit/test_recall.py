"""compare-gold: matching a generated suite against authored bench tasks.

Recall here is a smoke signal. The tests below pin the *rules* -- goal identity
required, cell overlap scored, one gold task to at most one scenario -- because
those are what make the number mean anything, not the number itself.
"""

from __future__ import annotations

import json

import pytest

from testgen.artifacts import write_json
from testgen.emit import emit_run
from testgen.errors import UsageError
from testgen.paths import RunPaths
from testgen.recall import (
    MATCH_JACCARD_FLOOR,
    NOVELTY_KINDS,
    assign_matches,
    cells,
    classify_novelty,
    compare,
    compare_run,
    generated_tasks,
    load_gold,
    render,
)
from tests.builders import (
    minimal_expected,
    minimal_gold,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)
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


# -- classify_novelty --------------------------------------------------------


def _kind(scenario, gold=None):
    return classify_novelty(scenario, gold if gold is not None else [_gold("bench-001")])[0]


def test_a_capability_gold_never_touches_is_the_headline():
    assert _kind(_generated("scn-9", refs=(("cap-unknown", "oc-success"),))) == "new_capability"


def test_a_known_capability_in_an_unknown_outcome_class_is_a_new_outcome_class():
    assert _kind(_generated("scn-9", refs=(("cap-find-jobs", "oc-empty"),))) == "new_outcome_class"


def test_a_known_cell_at_an_unauthored_hop_depth_is_a_new_hop_depth():
    assert _kind(_generated("scn-9", hop_depth=4)) == "new_hop_depth"


def test_a_goal_gold_never_covers_is_a_new_hop_depth_too():
    """A goal absent from gold has no authored depths, so every depth is new.

    Folding it in here rather than adding a fifth category keeps the vocabulary
    the spec fixed, and the `why` string names the goal so the reason is not lost.
    """
    kind, why = classify_novelty(_generated("scn-9", goal_id="goal-unseen"), [_gold("bench-001")])
    assert kind == "new_hop_depth"
    assert "goal-unseen" in why


def test_a_recombination_of_authored_coverage_is_spurious():
    """Last in the precedence, and a real category.

    Every cell and the (goal, hop depth) pair already appear in gold -- spread
    across two authored tasks -- so this adds no coverage axis. It looks new only
    because no single gold task overlapped it enough to pair.
    """
    gold = [
        _gold("bench-001", refs=(("cap-a", "oc-1"),) * 1),
        _gold("bench-002", refs=(("cap-b", "oc-1"),) * 1),
    ]
    scenario = _generated("scn-9", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-a", "oc-1")))
    kind, why = classify_novelty(scenario, gold)
    assert kind == "spurious"
    assert why


def test_the_precedence_is_capability_then_class_then_depth():
    """A scenario that is new on every axis at once must report the strongest.

    Reporting new_hop_depth for a scenario that reached a capability nobody
    authored buries the most interesting result compare-gold can produce.
    """
    scenario = _generated("scn-9", refs=(("cap-unknown", "oc-unknown"),), hop_depth=5)
    assert _kind(scenario) == "new_capability"
    assert NOVELTY_KINDS[0] == "new_capability"


def test_every_scenario_gets_exactly_one_kind_from_the_closed_vocabulary():
    for scenario in (
        _generated("a"),
        _generated("b", refs=(("cap-x", "oc-1"),)),
        _generated("c", hop_depth=1),
        _generated("d", goal_id="goal-other"),
    ):
        assert _kind(scenario) in NOVELTY_KINDS


# -- compare -----------------------------------------------------------------


def test_compare_reports_recall_over_the_gold_denominator(tmp_path):
    run = build_state(tmp_path, "emit")
    report = compare(run, minimal_gold())
    assert report["gold_denominator"] == 1
    assert report["recall"] == 1.0
    assert report["matched"][0]["scenario_id"] == "scn-001"
    assert report["unmatched_gold"] == []
    assert report["novel"] == []
    assert report["human_confirmation_required"] is True
    assert "schema_version" not in report


def test_compare_categorizes_what_matched_nothing(tmp_path):
    run = build_state(tmp_path, "emit")
    gold = minimal_gold(tasks=[_gold("bench-001", goal_id="goal-elsewhere")])
    report = compare(run, gold)
    assert report["recall"] == 0.0
    assert report["unmatched_gold"] == ["bench-001"]
    assert [entry["kind"] for entry in report["novel"]] == ["new_hop_depth"]
    assert report["novel"][0]["scenario_id"] == "scn-001"


def test_an_empty_gold_list_reports_no_recall_rather_than_a_zero(tmp_path):
    """0.0 would read as "the pipeline found none of them"."""
    run = build_state(tmp_path, "emit")
    report = compare(run, minimal_gold(tasks=[]))
    assert report["gold_denominator"] == 0
    assert report["recall"] is None


def test_compare_is_deterministic(tmp_path):
    run = build_state(tmp_path, "emit")
    assert compare(run, minimal_gold()) == compare(run, minimal_gold())


# -- render ------------------------------------------------------------------


def test_the_rendered_report_states_the_noise_caveat_with_the_real_denominator(tmp_path):
    """Mandated by design spec section 7, and derived rather than boilerplate.

    A recall number without this sentence beside it will be optimized, and with a
    denominator of ten it is ten points per task.
    """
    run = build_state(tmp_path, "emit")
    text = render(compare(run, minimal_gold(tasks=[_gold(f"bench-{i:03d}") for i in range(10)])))
    assert "denominator of 10" in text
    assert "noise" in text
    assert "not a metric to optimize" in text


def test_the_caveat_changes_with_the_denominator(tmp_path):
    run = build_state(tmp_path, "emit")
    text = render(compare(run, minimal_gold()))
    assert "denominator of 1" in text
    assert "denominator of 10" not in text


def test_an_empty_gold_list_renders_a_different_sentence(tmp_path):
    run = build_state(tmp_path, "emit")
    text = render(compare(run, minimal_gold(tasks=[])))
    assert "no gold tasks" in text
    assert "noise" not in text


def test_the_rendered_report_says_matches_need_human_confirmation(tmp_path):
    run = build_state(tmp_path, "emit")
    assert "human confirmation" in render(compare(run, minimal_gold()))


def test_every_novel_scenario_appears_in_the_rendering(tmp_path):
    run = build_state(tmp_path, "emit")
    gold = minimal_gold(tasks=[_gold("bench-001", goal_id="goal-elsewhere")])
    text = render(compare(run, gold))
    assert "scn-001" in text
    assert "new_hop_depth" in text


# -- compare_run's /novel finding ---------------------------------------------


def _scenario_doc(sid, refs):
    return {
        "id": sid,
        "round": 1,
        "goal_id": "goal-triage",
        "actor_id": "act-sre",
        "title": f"title for {sid}",
        "user_intent": "intent",
        "hop_depth": 2,
        "capability_refs": [{"capability_id": c, "outcome_class_id": o} for c, o in refs],
        "discriminating_fact": "fact",
        "status": "active",
        "provenance": {"hole_refs": [], "claim_ids": ["clm-001"], "round": 1},
    }


def _emitted_run(tmp_path, scenario_refs):
    """A run with one emitted package per (sid, refs) pair in scenario_refs.

    Builds only what emit_run reads (world model, scenario list, seed,
    expected, verdict) -- there is no coverage document here because nothing
    in this test reads one.
    """
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.world_model, minimal_world_model())
    write_json(
        run.scenarios,
        minimal_scenarios(scenarios=[_scenario_doc(sid, refs) for sid, refs in scenario_refs]),
    )
    for sid, _refs in scenario_refs:
        write_json(run.seed(sid), minimal_seed())
        write_json(run.expected(sid), minimal_expected(scenario_id=sid))
        write_json(run.verdict(sid), minimal_verdict(scenario_id=sid))
    emitted, findings = emit_run(run)
    assert findings == [], findings
    assert sorted(emitted) == sorted(sid for sid, _ in scenario_refs)
    return run


def test_the_novel_finding_names_only_the_spurious_entries_not_every_novel_one(tmp_path):
    """The /novel finding is a filter over report["novel"], not a pass-through.

    Three single-cell gold tasks, spread so no one of them alone clears the
    match floor against a scenario that recombines all three -- that scenario
    is spurious. scn-new-cap reaches a capability none of them touch, so it is
    new_capability, not spurious. Without a fixture that puts both kinds in the
    same run, a filter that let every novel entry through -- reporting the
    new_capability scenario as if it added no coverage axis -- would pass every
    other test in this file untouched.
    """
    gold = minimal_gold(
        tasks=[
            _gold("bench-001", refs=(("cap-a", "oc-1"),)),
            _gold("bench-002", refs=(("cap-b", "oc-1"),)),
            _gold("bench-003", refs=(("cap-c", "oc-1"),)),
        ]
    )
    run = _emitted_run(
        tmp_path,
        [
            ("scn-spurious", (("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-c", "oc-1"))),
            ("scn-new-cap", (("cap-z", "oc-1"),)),
        ],
    )
    gold_path = tmp_path / "gold.json"
    write_json(gold_path, gold)

    report, findings = compare_run(run, gold_path)
    assert {entry["scenario_id"]: entry["kind"] for entry in report["novel"]} == {
        "scn-spurious": "spurious",
        "scn-new-cap": "new_capability",
    }

    novel_findings = [f for f in findings if f.pointer == "/novel"]
    assert len(novel_findings) == 1
    assert "scn-spurious" in novel_findings[0].message
    assert "scn-new-cap" not in novel_findings[0].message
