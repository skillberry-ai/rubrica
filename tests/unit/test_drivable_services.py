"""A cell is drivable only if its capability's `binding.tool` is a tool in services.

On hermes run-20261110-150134, 117 capabilities were bound and only 7
of those bindings named one of the 21 tools the world model's `services` listed;
the other 110 named an HTTP route or a function (`POST /api/sessions`), and every
one of them still counted as drivable and got tests no agent could pass.

The rule the owner set (2026-11-23), and what each test below holds:

- a world model with no `services` key keeps the older rule (any `binding.tool`
  counts), so the tau2 run and both committed `recorded/` world models stay valid;
- with a `services` key present, even `[]`, a binding must name a service tool
  *exactly* -- no prefix or case folding;
- a cell excluded that way is still accounted for, as an injected `unreachable`
  hole whose justification says the binding names something that is not a tool.
"""

from __future__ import annotations

import copy

from rubrica import brief, cli, reconcile, refs, rounds
from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths
from rubrica.validate import validate_artifact
from tests.toy import build_toy_run


def _cap(cap_id: str, tool: str | None, ocs: tuple[str, ...] = ("oc-ok",)) -> dict:
    cap: dict = {"id": cap_id, "outcome_classes": [{"id": oc} for oc in ocs]}
    if tool is not None:
        cap["binding"] = {"tool": tool, "fixed_args": {}}
    return cap


def _services(*names: str) -> list[dict]:
    return [{"id": "svc", "tools": [{"name": name} for name in names]}]


# -- the rule itself ----------------------------------------------------
def test_without_a_services_key_any_binding_tool_still_counts():
    """The older rule, kept on purpose for world models sealed before services."""
    world = {"capabilities": [_cap("cap-a", "GET /x"), _cap("cap-b", "t"), _cap("cap-c", None)]}
    assert refs.drivable_cells(world) == {("cap-a", "oc-ok"), ("cap-b", "oc-ok")}


def test_with_services_present_only_a_listed_tool_counts():
    world = {
        "capabilities": [
            _cap("cap-tool", "mcp__builtin__jira_search", ("oc-ok", "oc-empty")),
            _cap("cap-route", "GET /x"),
            _cap("cap-none", None),
        ],
        "services": _services("mcp__builtin__jira_search"),
    }
    assert refs.drivable_cells(world) == {("cap-tool", "oc-ok"), ("cap-tool", "oc-empty")}
    # The resolver set stays wide, so a hole on the route cell still resolves.
    assert ("cap-route", "oc-ok") in refs._cells(world)


def test_an_empty_services_list_is_held_to_rather_than_read_as_absent():
    world = {"capabilities": [_cap("cap-a", "t")], "services": []}
    assert refs.drivable_cells(world) == set()


def test_the_match_is_exact_with_no_prefix_or_case_folding():
    """suite/verify.py's call_matches compares tool names exactly, so a folded
    match here would count a cell no emitted test could pass."""
    world = {
        "capabilities": [
            _cap("cap-short", "jira_search"),
            _cap("cap-case", "MCP__builtin__jira_search"),
            _cap("cap-exact", "mcp__builtin__jira_search"),
        ],
        "services": _services("mcp__builtin__jira_search"),
    }
    assert refs.drivable_cells(world) == {("cap-exact", "oc-ok")}


def test_a_malformed_services_value_narrows_rather_than_raises():
    """check_all has no ordering guarantee that layer 1 rejected it first."""
    caps = [_cap("cap-a", "t")]
    for services in (5, "t", None, [5, {"tools": 3}, {"tools": [7, {"name": 9}]}]):
        assert refs.drivable_cells({"capabilities": caps, "services": services}) == set()
    # A non-string binding.tool is not a tool name, and must not raise on `in`.
    odd = [{"id": "cap-a", "binding": {"tool": ["t"]}, "outcome_classes": [{"id": "oc"}]}]
    assert refs.drivable_cells({"capabilities": odd, "services": _services("t")}) == set()


# -- the toy run is unchanged -------------------------------------------
def test_the_toy_run_is_unchanged_because_query_tickets_is_a_service_tool(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    world = read_json(run.world_model)
    assert "services" in world, "the toy seal must carry services for this to test anything"
    assert world["denominator"]["capability_cells"] == 4
    assert len(refs.drivable_cells(world)) == 4


# -- the seal -----------------------------------------------------------
def test_the_seal_counts_against_the_services_part_it_folds_in(tmp_path):
    """reconcile.seal used to pass drivable_cells only the capabilities, so the
    tool list it had just read could not narrow the number it wrote."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile-services")
    part = read_json(run.services_part)
    part["services"][0]["tools"][0]["name"] = "mcp__ticketq__query_tickets"
    write_json(run.services_part, part)

    path, findings = reconcile.seal(run)

    assert findings == []
    world = read_json(path)
    assert world["denominator"]["capability_cells"] == 0
    # And check_world_model, recomputing through the same function, agrees.
    assert [f for f in refs.check_world_model(run) if "denominator" in str(f)] == []


# -- the loop: worklist, matrix, holes, check-refs ----------------------
def _toy_with_a_route_bound_capability(tmp_path) -> RunPaths:
    run = build_toy_run(tmp_path / "runs", upto="score")
    world = read_json(run.world_model)
    route = copy.deepcopy(world["capabilities"][0])
    route["id"] = "cap-route"
    route["binding"] = {"tool": "GET /x", "fixed_args": {}}
    route["outcome_classes"] = route["outcome_classes"][:1]
    world["capabilities"].append(route)
    write_json(run.world_model, world)
    assert validate_artifact(run.world_model, "world-model") == []
    # Off-tool, so the sealed denominator the toy wrote is still the right one.
    assert world["denominator"]["capability_cells"] == len(refs.drivable_cells(world)) == 4
    return run


def test_a_capability_bound_to_a_route_is_accounted_for_but_never_scored(tmp_path):
    run = _toy_with_a_route_bound_capability(tmp_path)
    oc_id = read_json(run.world_model)["capabilities"][-1]["outcome_classes"][0]["id"]
    ref = f"cell:cap-route/{oc_id}"

    # No worklist ref: propose is never asked to close it.
    worklist = rounds.closable_holes(run)
    assert ref not in worklist
    assert any(r.startswith("cell:cap-find-tickets/") for r in worklist)

    path, findings = rounds.seal_score(run, round_n=1)
    assert findings == []
    doc = read_json(path)

    # No matrix row.
    rows = {c["capability_id"] for c in doc["capability_matrix"]["cells"]}
    assert "cap-route" not in rows
    assert "cap-find-tickets" in rows

    # An injected unreachable hole, with the new reason -- not the "declares no
    # binding.tool" one, which would be false of this capability.
    hole = next(h for h in doc["holes"] if h["ref"] == ref)
    assert hole["reason"] == "unreachable"
    justification = hole["justification"]
    assert "'GET /x'" in justification
    assert "not a tool" in justification and "services" in justification
    assert "declares no binding.tool" not in justification
    assert validate_artifact(path, "coverage") == []

    assert cli.main(["check-refs", "--run", str(run.root)]) == 0


def test_an_unbound_capability_keeps_the_old_justification(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="score")
    world = read_json(run.world_model)
    loose = copy.deepcopy(world["capabilities"][0])
    loose["id"] = "cap-loose"
    loose.pop("binding")
    world["capabilities"].append(loose)
    write_json(run.world_model, world)

    path, findings = rounds.seal_score(run, round_n=1)

    assert findings == []
    holes = [h for h in read_json(path)["holes"] if h["ref"].startswith("cell:cap-loose/")]
    assert holes
    assert all("declares no binding.tool" in h["justification"] for h in holes)


# -- gate 1 -------------------------------------------------------------
def _gate_one_section(run: RunPaths) -> str:
    text = brief.gate_brief(run, 1)
    lines = text.split(brief.EXCLUDED_HEADER, 1)[1].splitlines()
    body = lines[:1]
    for line in lines[1:]:
        if line and not line.startswith(" "):
            break
        body.append(line)
    return "\n".join(body)


def _rebind(run: RunPaths, tools: dict[str, str | None]) -> None:
    world = read_json(run.world_model)
    for cap in world["capabilities"]:
        if cap["id"] in tools:
            if tools[cap["id"]] is None:
                cap.pop("binding", None)
            else:
                cap["binding"]["tool"] = tools[cap["id"]]
    world["denominator"]["capability_cells"] = len(refs.drivable_cells(world))
    write_json(run.world_model, world)


def test_gate_one_banner_says_bound_but_not_to_a_tool_and_never_zero_declare(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    _rebind(run, {"cap-find-tickets": "POST /api/find", "cap-get-ticket": "GET /api/t"})

    section = _gate_one_section(run)
    banner = [line for line in section.splitlines() if line.strip().startswith("***")]
    assert "NOTHING IS DRIVABLE" in banner[0]
    assert "bound, but not to any tool in services" in banner[0]
    # Both capabilities DO declare binding.tool, so the old sentence would be false.
    assert "declare binding.tool" not in section
    assert "'POST /api/find'" in section
    for line in banner:
        assert len(line) <= 100, line
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


def test_gate_one_banner_names_both_causes_when_both_apply(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    _rebind(run, {"cap-find-tickets": "POST /api/find", "cap-get-ticket": None})

    banner = " ".join(
        line for line in _gate_one_section(run).splitlines() if line.strip().startswith("***")
    )
    assert "NOTHING IS DRIVABLE" in banner
    assert "bound, but not to any tool in services" in banner
    assert "declare no binding.tool" in banner
    assert "0 of 2 capabilities declare" not in banner


def test_gate_one_counts_off_tool_capabilities_apart_from_unbound_ones(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    _rebind(run, {"cap-get-ticket": "GET /api/t"})

    section = _gate_one_section(run)
    assert "1 of 2 capabilities are drivable" in section
    assert "bound, but not to any tool in services" in section
    assert "NOTHING IS DRIVABLE" not in section
