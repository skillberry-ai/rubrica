"""Translating an oracle into the scoring contract verify.py consumes."""

from __future__ import annotations

import json

import pytest

from rubrica.artifacts import write_json
from rubrica.emit import bindings, call_spec, emit_run, to_contract
from rubrica.paths import RunPaths
from rubrica.suite.verify import CONTRACT
from tests.builders import (
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_services_part,
    minimal_verdict,
    minimal_world_model,
)
from tests.toy import SIDS, build_toy_run


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


# --- a binding whose tool is not one the agent has ---------------


def _world_with_a_route_bound_capability():
    """The minimal world plus `services` naming query_aap2, and a second
    capability bound to an HTTP route that is not a tool there."""
    world = minimal_world_model()
    world["services"] = minimal_services_part()["services"]
    world["capabilities"].append(
        {
            "id": "cap-route",
            "operation": "GET /x",
            "params": [],
            "outcome_classes": [{"id": "oc-route", "kind": "success", "description": "x"}],
            "claims": ["clm-001"],
            "confidence": "high",
            "binding": {"tool": "GET /x", "fixed_args": {}},
        }
    )
    return world


def _emit(tmp_path, world, expected):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, world)
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.seed("scn-001"), minimal_seed())
    write_json(run.expected("scn-001"), expected)
    write_json(run.verdict("scn-001"), minimal_verdict())
    emitted, findings = emit_run(run)
    return run, emitted, findings


def test_tool_called_on_a_capability_bound_to_a_non_tool_is_one_finding_and_no_package(
    tmp_path,
):
    expected = minimal_expected()
    assert expected["assertions"][1]["kind"] == "tool_called"
    expected["assertions"][1]["capability_id"] = "cap-route"
    run, emitted, findings = _emit(tmp_path, _world_with_a_route_bound_capability(), expected)
    assert emitted == []
    assert len(findings) == 1
    (finding,) = findings
    assert finding.artifact == run.expected("scn-001")
    assert finding.pointer == "/assertions/1/capability_id"
    assert "bound to a tool the agent does not have" in finding.message
    assert "declares no binding" not in finding.message
    assert not run.task_dir("scn-001").exists()


def test_a_trajectory_operation_on_a_non_tool_binding_is_one_finding_and_no_package(tmp_path):
    expected = minimal_expected()
    expected["trajectory"]["operations"][0]["capability_id"] = "cap-route"
    run, emitted, findings = _emit(tmp_path, _world_with_a_route_bound_capability(), expected)
    assert emitted == []
    assert len(findings) == 1
    (finding,) = findings
    assert finding.artifact == run.expected("scn-001")
    assert finding.pointer == "/trajectory/operations/0/capability_id"
    assert "bound to a tool the agent does not have" in finding.message
    assert not run.task_dir("scn-001").exists()


def test_tool_not_called_on_a_non_tool_binding_is_still_allowed():
    """Asserting the agent never calls a tool it does not have is trivially true,
    not wrong, so it is left alone (recorded for the owner to rule on later)."""
    expected = minimal_expected()
    expected["assertions"][1]["kind"] = "tool_not_called"
    expected["assertions"][1]["capability_id"] = "cap-route"
    contract, problems = to_contract(
        *_parts(world=_world_with_a_route_bound_capability(), expected=expected)
    )
    assert problems == []
    assert contract["assertions"][1]["tool"] == "GET /x"


def test_a_route_binding_with_no_services_key_still_translates():
    """No `services` key: nothing to hold the name against, so behaviour is unchanged."""
    world = _world_with_a_route_bound_capability()
    del world["services"]
    expected = minimal_expected()
    expected["assertions"][1]["capability_id"] = "cap-route"
    expected["trajectory"]["operations"][0]["capability_id"] = "cap-route"
    contract, problems = to_contract(*_parts(world=world, expected=expected))
    assert problems == []
    assert contract["trajectory"]["operations"][0]["tool"] == "GET /x"


def test_a_world_whose_services_name_its_tool_translates_cleanly():
    world = _world_with_a_route_bound_capability()
    contract, problems = to_contract(*_parts(world=world))
    assert problems == []
    assert contract["assertions"][1]["tool"] == "query_aap2"


def _suite_bytes(run):
    suite = run.root / "06-suite"
    return {
        str(p.relative_to(suite)): p.read_bytes() for p in sorted(suite.rglob("*")) if p.is_file()
    }


def test_the_toy_suite_emits_byte_identically_with_the_services_rule_live(tmp_path):
    """The golden world carries `services`, so the new rule runs over every toy
    binding. Removing the key takes the pre-rule path (`tools is None`), so the two
    suites being byte-identical is the toy suite being unchanged by the rule.
    Also measured once against the pre-change emit.py: same sha256 over 06-suite."""
    run = build_toy_run(tmp_path / "runs")
    world = json.loads(run.world_model.read_text())
    assert "services" in world, "fixture-cannot-reach: the rule would not run"
    emitted, findings = emit_run(run)
    assert findings == []
    assert emitted == sorted(SIDS)
    with_rule = _suite_bytes(run)

    del world["services"]
    write_json(run.world_model, world)
    emitted, findings = emit_run(run)
    assert findings == []
    assert _suite_bytes(run) == with_rule
