"""The toy world's artifacts are valid, mutually consistent, and reviewable.

This file checks the fixture itself. The end-to-end run through the real code
is test_toy_end_to_end.py (Task 5); if the fixture is wrong, that file's
failures would blame the pipeline for a bad fixture, so the fixture gets its
own gate first.
"""

from __future__ import annotations

from testgen.invariants import evaluate
from testgen.validate import validate_artifact
from tests.toy import (
    ARTIFACT_IDS,
    INPUT_FILES,
    SIDS,
    TOY_DIR,
    toy_claims,
    toy_coverage,
    toy_expected,
    toy_scenarios,
    toy_seed,
    toy_verdict,
    toy_world_model,
)


def test_the_three_input_files_exist_and_are_distinct_kinds():
    from testgen.intake import classify

    assert all(p.parent == TOY_DIR for p in INPUT_FILES)
    assert sorted(p.name for p in INPUT_FILES) == ["api.json", "notes.md", "trace.json"]
    kinds = {p.name: classify(p) for p in INPUT_FILES}
    assert kinds == {
        "api.json": "mcp_tool_schema",
        "notes.md": "design_doc",
        "trace.json": "trace",
    }


def test_every_toy_artifact_validates_against_its_schema(tmp_path):
    from testgen.artifacts import write_json

    def valid(payload, kind):
        path = tmp_path / f"{kind}.json"
        write_json(path, payload)
        return validate_artifact(path, kind)

    for artifact_id in ARTIFACT_IDS:
        assert valid(toy_claims(artifact_id), "claims") == [], artifact_id
    assert valid(toy_world_model(), "world-model") == []
    assert valid(toy_scenarios(), "scenarios") == []
    assert valid(toy_coverage(), "coverage") == []
    for sid in SIDS:
        assert valid(toy_seed(sid), "seed") == [], sid
        assert valid(toy_expected(sid), "expected") == [], sid
        assert valid(toy_verdict(sid), "verdict") == [], sid


def test_the_world_model_has_four_cells_and_two_goals():
    """The shape the coverage matrices are built against. Pinned here so a later
    edit that adds an outcome class fails the fixture test rather than silently
    making the matrices wrong.
    """
    world = toy_world_model()
    cells = [
        (cap["id"], oc["id"]) for cap in world["capabilities"] for oc in cap["outcome_classes"]
    ]
    assert len(cells) == 4
    assert world["denominator"] == {"version": 1, "capability_cells": 4, "goals": 2}
    assert [g["id"] for g in world["goals"]] == ["goal-locate", "goal-explain"]


def test_the_world_model_records_the_contradiction_rather_than_resolving_it_silently():
    """notes.md says an unknown id is an error; the trace shows an empty object.
    A world model that picked one and moved on is the failure the extract/
    reconcile split exists to prevent.
    """
    world = toy_world_model()
    assert len(world["contradictions"]) == 1
    contradiction = world["contradictions"][0]
    claims = {claim["id"] for aid in ARTIFACT_IDS for claim in toy_claims(aid)["claims"]}
    assert contradiction["claim_a"] in claims
    assert contradiction["claim_b"] in claims
    assert contradiction["resolution"] == "preferred_a"


def test_the_world_model_has_no_gaps():
    """A gap blocks a downstream stage and the orchestrator halts. The golden
    fixture must run to completion, so it has none by construction; the gap
    fixture is tests/fixtures/toy-gap/.
    """
    assert toy_world_model()["gaps"] == []


def test_every_claim_id_is_unique_across_the_three_claims_files():
    """check_manifest reports a claim id defined twice, because every
    world-model reference to it would resolve ambiguously. Three claims files
    is the smallest fixture in which that can happen at all.
    """
    ids = [claim["id"] for aid in ARTIFACT_IDS for claim in toy_claims(aid)["claims"]]
    assert len(ids) == len(set(ids))


def test_every_world_model_claim_reference_resolves():
    known = {claim["id"] for aid in ARTIFACT_IDS for claim in toy_claims(aid)["claims"]}
    world = toy_world_model()
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world[group]:
            for claim_id in item["claims"]:
                assert claim_id in known, f"{group}: {claim_id}"


def test_the_machine_invariants_hold_over_every_seed():
    """Two forms, `count` and `unique`, over four seeds. builders.py uses no
    machine invariant at all, so this is the first fixture that exercises
    invariants.py through refs at all.
    """
    world = toy_world_model()
    machines = [
        inv["machine"]
        for entity in world["entities"]
        for inv in entity.get("invariants", [])
        if "machine" in inv
    ]
    assert len(machines) == 2, "the fixture must carry both forms"
    for sid in SIDS:
        collections = toy_seed(sid)["collections"]
        for machine in machines:
            assert evaluate(machine, collections) == [], f"{sid}: {machine['form']}"


def test_a_broken_seed_would_be_caught_by_those_invariants(tmp_path):
    """The dual of the test above: it proves the invariants hold, not that they
    can fail. Without this, an invariant over a collection no seed declares
    would pass vacuously and the fixture would prove nothing -- and that
    applies per form, not just once: a mistyped `collection` makes `_records`
    return [] and every form report no violations regardless of what's
    actually wrong, so each form the fixture uses needs its own corruption.

    Breakers are keyed by form name and checked against the forms the world
    model actually declares, rather than one assertion per form written out
    by hand, so a third `machine:` form added later without a matching
    breaker here fails the coverage assertion below instead of silently
    shipping unverified.
    """
    world = toy_world_model()
    machines = {
        inv["machine"]["form"]: inv["machine"]
        for entity in world["entities"]
        for inv in entity.get("invariants", [])
        if "machine" in inv
    }

    def break_count(collections):
        collections["tickets"][0]["comment_count"] += 1

    def break_unique(collections):
        collections["tickets"][1]["ticket_id"] = collections["tickets"][0]["ticket_id"]

    breakers = {"count": break_count, "unique": break_unique}
    assert set(machines) == set(breakers), (
        "every machine: form the fixture declares needs a corruption case here, "
        "or that form's invariant could pass vacuously and no test would notice"
    )

    for form, machine in machines.items():
        collections = toy_seed("scn-blocked")["collections"]
        breakers[form](collections)
        assert evaluate(machine, collections) != [], form


def test_the_coverage_report_covers_every_cell_and_both_goals():
    coverage = toy_coverage()
    assert coverage["capability_matrix"]["total"] == 4
    assert coverage["capability_matrix"]["covered"] == 4
    assert coverage["goal_matrix"]["total"] == 2
    assert coverage["goal_matrix"]["covered"] == 2
    assert coverage["holes"] == [], "a fully covered report has nothing to justify"
    assert coverage["verdict"] == "converged"


def test_the_expected_oracles_use_the_two_vocabulary_kinds_nothing_else_does():
    """value_equals and answer_excludes. The reason this fixture exists rather
    than another minimal_expected(): two of the five kinds in the closed
    vocabulary had no fixture exercising them end to end.
    """
    from testgen.suite.verify import ASSERTION_KINDS

    used = {assertion["kind"] for sid in SIDS for assertion in toy_expected(sid)["assertions"]}
    assert {"value_equals", "answer_excludes"} <= used
    assert used <= set(ASSERTION_KINDS), "the vocabulary is closed"


def test_each_oracle_copies_its_scenario_discriminating_fact_verbatim():
    """refs.check_instances compares the two strings, because a paraphrase is
    indistinguishable from substituting an easier fact.
    """
    facts = {s["id"]: s["discriminating_fact"] for s in toy_scenarios()["scenarios"]}
    for sid in SIDS:
        assert toy_expected(sid)["discriminating_fact"] == facts[sid]


def test_every_seed_carries_at_least_one_distractor():
    """Section 6 step 2: a world containing exactly one candidate makes the test
    passable by any agent that calls the API once and reads back the only row.
    The distractor set, not hop_depth, is what sets difficulty.
    """
    for sid in SIDS:
        tickets = toy_seed(sid)["collections"]["tickets"]
        assert len(tickets) >= 2, f"{sid} has no near-miss to rule out"


def test_the_folded_scenario_is_not_instantiated():
    """SIDS is the instantiated set; ALL_SCENARIO_IDS includes the duplicate.
    Conflating them would instantiate a folded scenario, which
    refs.check_instances reports -- only a judged scenario should have an
    instance directory.
    """
    from tests.toy import ALL_SCENARIO_IDS

    assert set(SIDS) < set(ALL_SCENARIO_IDS)
    folded = set(ALL_SCENARIO_IDS) - set(SIDS)
    assert folded == {"scn-open-dup"}
    by_id = {s["id"]: s for s in toy_scenarios()["scenarios"]}
    assert by_id["scn-open-dup"]["status"] == "duplicate"
    assert by_id["scn-open-dup"]["duplicate_of"] == "scn-open"


def test_the_duplicate_pair_is_a_dedupe_candidate_before_score_rules_on_it():
    """The reason scn-open-dup exists. candidate_pairs needs a shared goal AND a
    shared cell, and the other four scenarios' cells are disjoint -- so without
    this pair the toy world yields an empty candidate list and the deterministic
    half of stage 3 is exercised against nothing.

    Measured, not predicted: exactly one pair, with identical_cells True.
    """
    from testgen.dedupe import candidate_pairs

    pre_score = []
    for scenario in toy_scenarios()["scenarios"]:
        scenario = dict(scenario)
        scenario["status"] = "proposed"
        scenario.pop("duplicate_of", None)
        pre_score.append(scenario)
    candidates = candidate_pairs(pre_score)
    assert [(c.a, c.b) for c in candidates] == [("scn-open", "scn-open-dup")]
    assert candidates[0].identical_cells is True
    assert candidates[0].shared_cells == ("cell:cap-find-tickets/oc-found",)


def test_the_resolved_pair_is_no_longer_a_candidate():
    """The other direction, and the one that matters for convergence:
    candidate_pairs filters to OPEN_STATUSES, so a settled pair is not
    re-proposed in a later round. Without this test the fixture would prove only
    that a candidate can be found, not that resolving it stops the loop
    rediscovering it.
    """
    from testgen.dedupe import candidate_pairs

    assert candidate_pairs(toy_scenarios()["scenarios"]) == []


def test_the_folded_scenario_is_credited_in_neither_matrix():
    """A folded scenario's credit belongs to the scenario it was folded into. If
    it appeared in a cell's scenario_ids, refs.check_coverage's live-credit rule
    would still pass -- scn-open is live -- so nothing would catch it, and the
    matrix would imply two tests cover a cell that ships one.
    """
    coverage = toy_coverage()
    credited = {
        sid for cell in coverage["capability_matrix"]["cells"] for sid in cell["scenario_ids"]
    } | {sid for row in coverage["goal_matrix"]["rows"] for sid in row["scenario_ids"]}
    assert "scn-open-dup" not in credited


def test_the_open_scenario_count_stays_within_the_manifest_cap():
    """max_scenarios counts proposed and active only, so adding the duplicate
    must not consume cap. build_toy_run passes max_scenarios=8 and there are
    four live scenarios; this pins that the duplicate is genuinely free.
    """
    from testgen.refs import OPEN_STATUSES

    live = [s for s in toy_scenarios()["scenarios"] if s["status"] in OPEN_STATUSES]
    assert len(live) == 4
