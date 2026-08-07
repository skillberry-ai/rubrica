"""Translating an oracle into the scoring contract verify.py consumes."""

from __future__ import annotations

import pytest

from testgen.emit import bindings, call_spec, to_contract
from testgen.suite.verify import CONTRACT
from tests.builders import minimal_expected, minimal_scenarios, minimal_world_model


def _parts(**over):
    world = over.get("world", minimal_world_model())
    scenario = over.get("scenario", minimal_scenarios()["scenarios"][0])
    expected = over.get("expected", minimal_expected())
    return world, scenario, expected


def test_bindings_are_indexed_by_capability_id():
    assert bindings(minimal_world_model()) == {
        "cap-find-jobs": {"tool": "query_aap2", "fixed_args": {"action": "find_jobs"}}
    }


def test_a_capability_without_a_binding_is_absent_from_the_index():
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    assert bindings(world) == {}


def test_call_spec_merges_fixed_args_under_the_operations_own_args():
    spec = call_spec(
        {"tool": "query_aap2", "fixed_args": {"action": "find_jobs"}},
        {"controller": "prod0"},
    )
    assert spec == {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}


def test_an_operation_arg_overrides_a_fixed_arg():
    """A collision means the oracle is overriding the call's identity; make it visible."""
    spec = call_spec({"tool": "t", "fixed_args": {"action": "a"}}, {"action": "b"})
    assert spec["args"]["action"] == "b"


def test_a_clean_oracle_translates_with_no_problems():
    contract, problems = to_contract(*_parts())
    assert problems == []
    assert contract["contract"] == CONTRACT
    assert contract["scenario_id"] == "scn-001"
    assert contract["completion"] == {"status": "ok", "nonempty_answer": True}
    assert contract["weights"] == {"assertions": 0.8, "trajectory": 0.2}


def test_a_data_assertion_keeps_its_kind_value_and_rationale_and_drops_its_grounding():
    """seed_pointer grounds the label at authoring time; the container cannot use it."""
    contract, _ = to_contract(*_parts())
    first = contract["assertions"][0]
    assert first == {
        "id": "a0",
        "kind": "answer_contains",
        "target": "answer",
        "value": "90420",
        "rationale": "the failing job id must appear in the answer",
    }


def test_a_trajectory_assertion_becomes_a_tool_and_args_pair():
    contract, _ = to_contract(*_parts())
    second = contract["assertions"][1]
    assert second["id"] == "a1"
    assert second["kind"] == "tool_called"
    assert second["tool"] == "query_aap2"
    assert second["args"] == {"action": "find_jobs"}
    assert "capability_id" not in second


def test_the_trajectory_operations_are_translated_and_the_match_mode_kept():
    contract, _ = to_contract(*_parts())
    assert contract["trajectory"]["match"] == "subset"
    assert contract["trajectory"]["operations"] == [
        {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}
    ]


def test_assertion_ids_follow_the_source_index():
    expected = minimal_expected()
    expected["assertions"].append(
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "DNS",
            "rationale": "nothing in the seed supports a network cause",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/dns_error"},
        }
    )
    contract, _ = to_contract(*_parts(expected=expected))
    assert [a["id"] for a in contract["assertions"]] == ["a0", "a1", "a2"]


def test_an_unbound_capability_in_an_assertion_is_a_problem_and_blocks_the_contract():
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    contract, problems = to_contract(*_parts(world=world))
    assert contract is None
    pointers = [p for p, _ in problems]
    assert "/assertions/1/capability_id" in pointers
    assert any("declares no binding" in message for _, message in problems)


def test_an_unbound_capability_in_the_trajectory_is_a_problem():
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    _, problems = to_contract(*_parts(world=world))
    assert "/trajectory/operations/0/capability_id" in [p for p, _ in problems]


def test_every_problem_is_reported_not_just_the_first():
    """emit gets one bounded repair attempt, so it must report the whole list."""
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    _, problems = to_contract(*_parts(world=world))
    assert len(problems) >= 2


@pytest.mark.parametrize("match", ["subset", "exact-set", "exact-sequence"])
def test_each_match_mode_survives_translation(match):
    expected = minimal_expected()
    expected["trajectory"] = dict(expected["trajectory"], match=match)
    contract, problems = to_contract(*_parts(expected=expected))
    assert problems == []
    assert contract["trajectory"]["match"] == match
